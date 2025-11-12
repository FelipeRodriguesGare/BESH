"""
AWS S3 storage implementation for BESH

Supports IAM roles, named profiles, and explicit credentials.
"""

import asyncio
import io
from typing import AsyncIterator, Dict, List, Optional
import logging

from besh.storage.interface import StorageInterface
from besh.exceptions import (
    StorageNotFoundError,
    StorageUploadError,
    StorageDownloadError,
    StorageException,
    StorageConnectionError,
)
from besh.constants import (
    JSONL_EXTENSION,
    S3_RETRY_COUNT,
    S3_RETRY_BACKOFF_FACTOR,
    S3_MULTIPART_THRESHOLD,
    S3_MULTIPART_CHUNK_SIZE,
)

logger = logging.getLogger(__name__)

try:
    import aioboto3
    from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
except ImportError:
    aioboto3 = None
    ClientError = Exception
    NoCredentialsError = Exception
    BotoCoreError = Exception


class S3Storage(StorageInterface):
    """
    AWS S3 storage backend with IAM authentication

    Supports multiple authentication methods:
    1. IAM Role (automatic for EC2/ECS/Lambda)
    2. Named AWS Profile
    3. Explicit credentials (via environment variables)
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        profile: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        presigned_expiry: int = 3600,
    ):
        """
        Initialize S3 storage

        Args:
            bucket: S3 bucket name
            region: AWS region
            profile: AWS profile name for authentication (optional)
            endpoint_url: Custom S3 endpoint (for MinIO, LocalStack, etc.)
            presigned_expiry: Presigned URL expiration time in seconds
        """
        if aioboto3 is None:
            raise ImportError(
                "S3 storage requires aioboto3. Install with: pip install besh[s3]"
            )

        self.bucket = bucket
        self.region = region
        self.profile = profile
        self.endpoint_url = endpoint_url
        self.presigned_expiry = presigned_expiry
        self._session = None

        logger.info(
            f"Initialized S3Storage: bucket={bucket}, region={region}, "
            f"profile={profile}, endpoint={endpoint_url}"
        )

    def _get_session(self):
        """Get or create aioboto3 session"""
        if self._session is None:
            if self.profile:
                # Use named profile
                self._session = aioboto3.Session(profile_name=self.profile)
                logger.info(f"Using AWS profile: {self.profile}")
            else:
                # Use default credentials (IAM role, env vars, etc.)
                self._session = aioboto3.Session()
                logger.info("Using default AWS credentials (IAM role or env vars)")
        return self._session

    def _get_s3_key(self, file_id: str) -> str:
        """Get S3 key for a file ID"""
        # Ensure file_id has .jsonl extension
        if not file_id.endswith(JSONL_EXTENSION):
            file_id = f"{file_id}{JSONL_EXTENSION}"
        return file_id

    async def _get_client(self):
        """Get S3 client with retry logic"""
        session = self._get_session()

        try:
            return session.client(
                "s3", region_name=self.region, endpoint_url=self.endpoint_url
            )
        except (NoCredentialsError, BotoCoreError) as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise StorageConnectionError(f"Failed to connect to S3: {e}")

    async def _retry_operation(self, operation, *args, **kwargs):
        """Execute S3 operation with exponential backoff retry"""
        for attempt in range(S3_RETRY_COUNT):
            try:
                return await operation(*args, **kwargs)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                # Don't retry on non-retryable errors
                if error_code in ["NoSuchKey", "NoSuchBucket", "AccessDenied"]:
                    raise

                # Retry on service errors
                if attempt < S3_RETRY_COUNT - 1:
                    wait_time = S3_RETRY_BACKOFF_FACTOR**attempt
                    logger.warning(
                        f"S3 operation failed (attempt {attempt + 1}/{S3_RETRY_COUNT}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

    async def upload_stream(
        self,
        file_id: str,
        stream: AsyncIterator[bytes],
        metadata: Optional[Dict] = None,
    ) -> str:
        """Upload file from async byte stream with multipart upload for large files"""
        s3_key = self._get_s3_key(file_id)

        try:
            # Collect stream into memory buffer
            # For production with very large files, consider direct multipart streaming
            buffer = io.BytesIO()
            async for chunk in stream:
                buffer.write(chunk)

            buffer.seek(0)
            content = buffer.getvalue()

            async with self._get_client() as s3:
                # Use multipart upload for large files
                if len(content) > S3_MULTIPART_THRESHOLD:
                    await self._multipart_upload(s3, s3_key, content, metadata)
                else:
                    # Simple upload for small files
                    extra_args = {"ServerSideEncryption": "AES256"}
                    if metadata:
                        extra_args["Metadata"] = {
                            k: str(v) for k, v in metadata.items()
                        }

                    await self._retry_operation(
                        s3.put_object,
                        Bucket=self.bucket,
                        Key=s3_key,
                        Body=content,
                        **extra_args,
                    )

            logger.info(f"Uploaded file {file_id} to S3: s3://{self.bucket}/{s3_key}")
            return file_id

        except ClientError as e:
            logger.error(f"Failed to upload file {file_id} to S3: {e}")
            raise StorageUploadError(f"Failed to upload file {file_id} to S3: {e}")
        except Exception as e:
            logger.error(f"Unexpected error uploading file {file_id}: {e}")
            raise StorageUploadError(f"Failed to upload file {file_id}: {e}")

    async def _multipart_upload(
        self, s3, s3_key: str, content: bytes, metadata: Optional[Dict]
    ):
        """Perform multipart upload for large files"""
        try:
            # Initiate multipart upload
            extra_args = {"ServerSideEncryption": "AES256"}
            if metadata:
                extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}

            response = await s3.create_multipart_upload(
                Bucket=self.bucket, Key=s3_key, **extra_args
            )
            upload_id = response["UploadId"]

            # Upload parts
            parts = []
            part_number = 1
            offset = 0

            while offset < len(content):
                chunk = content[offset : offset + S3_MULTIPART_CHUNK_SIZE]

                part_response = await s3.upload_part(
                    Bucket=self.bucket,
                    Key=s3_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )

                parts.append({"PartNumber": part_number, "ETag": part_response["ETag"]})

                part_number += 1
                offset += S3_MULTIPART_CHUNK_SIZE

            # Complete multipart upload
            await s3.complete_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            logger.info(f"Completed multipart upload for {s3_key} ({len(parts)} parts)")

        except Exception as e:
            # Abort multipart upload on failure
            try:
                await s3.abort_multipart_upload(
                    Bucket=self.bucket, Key=s3_key, UploadId=upload_id
                )
            except:
                pass
            raise e

    async def download_stream(self, file_id: str) -> AsyncIterator[bytes]:
        """Download file as async byte stream"""
        s3_key = self._get_s3_key(file_id)

        try:
            async with self._get_client() as s3:
                response = await self._retry_operation(
                    s3.get_object, Bucket=self.bucket, Key=s3_key
                )

                async with response["Body"] as stream:
                    async for chunk in stream.iter_chunks():
                        yield chunk

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageNotFoundError(f"File {file_id} not found in S3")
            logger.error(f"Failed to download file {file_id} from S3: {e}")
            raise StorageDownloadError(
                f"Failed to download file {file_id} from S3: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error downloading file {file_id}: {e}")
            raise StorageDownloadError(f"Failed to download file {file_id}: {e}")

    async def read_lines(self, file_id: str) -> AsyncIterator[str]:
        """Stream file line by line"""
        s3_key = self._get_s3_key(file_id)

        try:
            async with self._get_client() as s3:
                response = await self._retry_operation(
                    s3.get_object, Bucket=self.bucket, Key=s3_key
                )

                # Read and decode stream line by line
                buffer = ""
                async with response["Body"] as stream:
                    async for chunk in stream.iter_chunks():
                        buffer += chunk.decode("utf-8")

                        # Yield complete lines
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            yield line

                # Yield any remaining content
                if buffer:
                    yield buffer

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageNotFoundError(f"File {file_id} not found in S3")
            logger.error(f"Failed to read lines from file {file_id}: {e}")
            raise StorageDownloadError(f"Failed to read lines from file {file_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error reading lines from file {file_id}: {e}")
            raise StorageDownloadError(f"Failed to read lines from file {file_id}: {e}")

    async def write_lines(self, file_id: str, lines: AsyncIterator[str]) -> str:
        """Write lines to file"""
        s3_key = self._get_s3_key(file_id)

        try:
            # Collect lines into buffer
            buffer = io.BytesIO()
            async for line in lines:
                line_bytes = line.encode("utf-8")
                if not line.endswith("\n"):
                    line_bytes += b"\n"
                buffer.write(line_bytes)

            buffer.seek(0)
            content = buffer.getvalue()

            async with self._get_client() as s3:
                await self._retry_operation(
                    s3.put_object,
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=content,
                    ServerSideEncryption="AES256",
                )

            logger.info(f"Wrote lines to file {file_id} in S3")
            return file_id

        except Exception as e:
            logger.error(f"Failed to write lines to file {file_id}: {e}")
            raise StorageUploadError(f"Failed to write lines to file {file_id}: {e}")

    async def delete(self, file_id: str) -> bool:
        """Delete a file"""
        s3_key = self._get_s3_key(file_id)

        try:
            async with self._get_client() as s3:
                # Check if file exists first
                try:
                    await s3.head_object(Bucket=self.bucket, Key=s3_key)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "404":
                        return False
                    raise

                # Delete the file
                await self._retry_operation(
                    s3.delete_object, Bucket=self.bucket, Key=s3_key
                )

                logger.info(f"Deleted file {file_id} from S3")
                return True

        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            raise StorageException(f"Failed to delete file {file_id}: {e}")

    async def exists(self, file_id: str) -> bool:
        """Check if file exists"""
        s3_key = self._get_s3_key(file_id)

        try:
            async with self._get_client() as s3:
                await s3.head_object(Bucket=self.bucket, Key=s3_key)
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    async def get_metadata(self, file_id: str) -> Dict:
        """Get file metadata"""
        s3_key = self._get_s3_key(file_id)

        try:
            async with self._get_client() as s3:
                response = await self._retry_operation(
                    s3.head_object, Bucket=self.bucket, Key=s3_key
                )

                return {
                    "id": file_id,
                    "filename": s3_key,
                    "size": response["ContentLength"],
                    "created_at": response["LastModified"].timestamp(),
                    "modified_at": response["LastModified"].timestamp(),
                    "etag": response["ETag"].strip('"'),
                }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise StorageNotFoundError(f"File {file_id} not found in S3")
            logger.error(f"Failed to get metadata for file {file_id}: {e}")
            raise StorageException(f"Failed to get metadata for file {file_id}: {e}")

    async def list_files(self, prefix: Optional[str] = None) -> List[Dict]:
        """List all files with optional prefix filter"""
        try:
            files = []

            async with self._get_client() as s3:
                # List objects with optional prefix
                paginator = s3.get_paginator("list_objects_v2")

                params = {"Bucket": self.bucket}
                if prefix:
                    params["Prefix"] = prefix

                async for page in paginator.paginate(**params):
                    for obj in page.get("Contents", []):
                        # Extract file_id (remove extension)
                        s3_key = obj["Key"]
                        file_id = s3_key.replace(JSONL_EXTENSION, "")

                        files.append(
                            {
                                "id": file_id,
                                "filename": s3_key,
                                "size": obj["Size"],
                                "created_at": obj["LastModified"].timestamp(),
                                "modified_at": obj["LastModified"].timestamp(),
                                "etag": obj["ETag"].strip('"'),
                            }
                        )

            # Sort by created_at descending
            files.sort(key=lambda x: x["created_at"], reverse=True)
            return files

        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            raise StorageException(f"Failed to list files: {e}")

    async def get_download_url(self, file_id: str, expires: int = None) -> str:
        """Get presigned download URL"""
        s3_key = self._get_s3_key(file_id)
        expires = expires or self.presigned_expiry

        try:
            async with self._get_client() as s3:
                # Check if file exists
                if not await self.exists(file_id):
                    raise StorageNotFoundError(f"File {file_id} not found in S3")

                # Generate presigned URL
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": s3_key},
                    ExpiresIn=expires,
                )

                return url

        except StorageNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for file {file_id}: {e}")
            raise StorageException(
                f"Failed to generate presigned URL for file {file_id}: {e}"
            )

    async def get_file_path(self, file_id: str) -> str:
        """Get the S3 path for a file"""
        s3_key = self._get_s3_key(file_id)
        return f"s3://{self.bucket}/{s3_key}"

    async def count_lines(self, file_id: str) -> int:
        """Count total lines in a file"""
        s3_key = self._get_s3_key(file_id)

        try:
            count = 0
            async with self._get_client() as s3:
                response = await s3.get_object(Bucket=self.bucket, Key=s3_key)
                async with response["Body"] as stream:
                    buffer = b""
                    async for chunk in stream:
                        buffer += chunk
                        while b"\n" in buffer:
                            buffer = buffer.split(b"\n", 1)[1]
                            count += 1
                    if buffer:  # Last line without newline
                        count += 1
            return count
        except Exception as e:
            if "NoSuchKey" in str(e):
                raise StorageNotFoundError(f"File not found: {file_id}")
            logger.error(f"Error counting lines in {file_id}: {e}")
            raise StorageException(f"Failed to count lines: {str(e)}")

    async def read_lines_range(
        self, file_id: str, start: int, end: int
    ) -> AsyncIterator[tuple[int, str]]:
        """Read specific line range from file"""
        s3_key = self._get_s3_key(file_id)

        try:
            line_num = 0
            async with self._get_client() as s3:
                response = await s3.get_object(Bucket=self.bucket, Key=s3_key)
                async with response["Body"] as stream:
                    buffer = b""
                    async for chunk in stream:
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            if line_num >= end:
                                return
                            if line_num >= start:
                                yield (line_num, line.decode("utf-8").strip())
                            line_num += 1
                    # Handle last line without newline
                    if buffer and line_num < end and line_num >= start:
                        yield (line_num, buffer.decode("utf-8").strip())
        except Exception as e:
            if "NoSuchKey" in str(e):
                raise StorageNotFoundError(f"File not found: {file_id}")
            logger.error(f"Error reading line range from {file_id}: {e}")
            raise StorageException(f"Failed to read line range: {str(e)}")
