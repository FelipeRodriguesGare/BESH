"""
File management routes for BESH

Handles file upload, download, listing, and deletion with storage abstraction.
API contract remains identical to original implementation.
"""

import uuid
import json
import gzip
import zipfile
import bz2
import io
from typing import Iterator
from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse

from besh.api.app import get_app_storage, get_app_config
from besh.api.auth import verify_api_key_flexible
from besh.storage import StorageInterface
from besh.exceptions import StorageNotFoundError, StorageException

logger = logging.getLogger(__name__)

router = APIRouter()


async def stream_jsonl_lines(
    upload_file: UploadFile, compression_format: str | None
) -> Iterator[str]:
    """
    Yield decoded JSONL lines from an uploaded UploadFile object.

    This function streams the uploaded payload chunk-by-chunk to avoid loading
    large files into memory. It supports uncompressed and gzip-compressed
    uploads. Other formats fall back to a simple read which may still require
    additional memory.
    """
    await upload_file.seek(0)  # Reset file pointer to beginning

    if compression_format == "gzip":
        # Read entire content for gzip (FastAPI UploadFile doesn't support streaming gzip well)
        content = await upload_file.read()
        decompressed = gzip.decompress(content)
        for line in decompressed.decode("utf-8").splitlines(True):
            yield line

    elif compression_format in (None, ""):
        # Plain text – read in chunks and decode
        content = await upload_file.read()
        for line in content.decode("utf-8").splitlines(True):
            yield line

    else:
        # Fallback: unsupported streaming compression (zip/bz2). We read the
        # entire content (could be large) and decompress using existing util.
        content = await upload_file.read()
        if compression_format:
            content = decompress_file(content, compression_format)
        for line in content.decode("utf-8").splitlines(True):
            yield line


def detect_compression_format(filename: str):
    """Detect the compression format of a file based on its extension."""
    filename_lower = filename.lower()
    if filename_lower.endswith((".gz", ".gzip")):
        return "gzip"
    if filename_lower.endswith(".zip"):
        return "zip"
    if filename_lower.endswith(".bz2"):
        return "bz2"
    return None


def decompress_file(file_content, compression_format):
    """Decompress file content based on the compression format"""
    try:
        if compression_format == "gzip":
            return gzip.decompress(file_content)
        elif compression_format == "zip":
            with zipfile.ZipFile(io.BytesIO(file_content)) as zip_file:
                # Get the first file in the zip
                file_list = zip_file.namelist()
                if not file_list:
                    raise ValueError("Empty zip file")
                # Use the first file, preferably a .jsonl file
                target_file = None
                for file in file_list:
                    if file.endswith(".jsonl"):
                        target_file = file
                        break
                if not target_file:
                    target_file = file_list[0]
                return zip_file.read(target_file)
        elif compression_format == "bz2":
            return bz2.decompress(file_content)
        else:
            raise ValueError(f"Unsupported compression format: {compression_format}")
    except Exception as e:
        raise ValueError(f"Failed to decompress file: {str(e)}")


@router.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    purpose: str = Form(default="batch"),
    api_key: str = Depends(verify_api_key_flexible),
    storage: StorageInterface = Depends(get_app_storage),
):
    """Upload a file for batch processing"""
    try:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail={"message": "No file selected", "type": "invalid_request_error"},
            )

        # Generate unique file ID
        file_id = f"file_{uuid.uuid4().hex}"
        # Simple filename sanitization (replacing werkzeug's secure_filename)
        filename = "".join(
            c for c in file.filename if c.isalnum() or c in (" ", ".", "_", "-")
        ).rstrip()

        # Determine compression format (by extension only to avoid reading into memory)
        compression_format = detect_compression_format(filename)

        # For compression ratio stats we rely on the raw request payload size if available
        original_size = file.size or 0

        # Stream-decompress / copy while validating each JSONL line
        # Use async generator to stream validated lines to storage
        async def validated_lines():
            try:
                async for raw_line in stream_jsonl_lines(file, compression_format):
                    line = raw_line.rstrip("\n")
                    if line.strip():
                        json.loads(line)  # validate JSON per line
                    yield line
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL format: {e}")

        try:
            # Write to storage using the interface
            await storage.write_lines(file_id, validated_lines())

        except ValueError as e:
            # JSON validation error
            # Try to clean up if file was partially written
            try:
                await storage.delete(file_id)
            except:
                pass
            raise HTTPException(
                status_code=400,
                detail={"message": str(e), "type": "invalid_request_error"},
            )
        except Exception as e:
            # Other errors during upload
            try:
                await storage.delete(file_id)
            except:
                pass
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Failed to process file: {str(e)}",
                    "type": "invalid_request_error",
                },
            )

        # File successfully written, gather stats
        try:
            metadata = await storage.get_metadata(file_id)
            file_size = metadata["size"]
        except Exception as e:
            logger.error(f"Failed to get metadata for uploaded file {file_id}: {e}")
            file_size = 0

        response_data = {
            "id": file_id,
            "object": "file",
            "bytes": file_size,
            "created_at": int(datetime.utcnow().timestamp()),
            "filename": filename,
            "purpose": purpose,
        }

        # Add compression information if file was compressed and original size known
        if compression_format and original_size:
            response_data["compression"] = {
                "format": compression_format,
                "original_size": original_size,
                "decompressed_size": file_size,
                "compression_ratio": (
                    round(original_size / file_size, 2) if file_size > 0 else 1
                ),
            }

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error uploading file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail={"message": str(e), "type": "server_error"}
        )


@router.get("/files/{file_id}")
async def get_file_info(
    file_id: str,
    api_key: str = Depends(verify_api_key_flexible),
    storage: StorageInterface = Depends(get_app_storage),
):
    """Get file information"""
    try:
        # Check if file exists
        if not await storage.exists(file_id):
            raise HTTPException(
                status_code=404,
                detail={
                    "message": f"File {file_id} not found",
                    "type": "not_found_error",
                },
            )

        # Get metadata from storage
        metadata = await storage.get_metadata(file_id)

        return {
            "id": file_id,
            "object": "file",
            "bytes": metadata["size"],
            "created_at": int(metadata["created_at"]),
            "filename": f"{file_id}.jsonl",
            "purpose": "batch",
        }

    except HTTPException:
        raise
    except StorageNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"message": f"File {file_id} not found", "type": "not_found_error"},
        )
    except Exception as e:
        logger.error(f"Error getting file info for {file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail={"message": str(e), "type": "server_error"}
        )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    api_key: str = Depends(verify_api_key_flexible),
    storage: StorageInterface = Depends(get_app_storage),
):
    """Delete a file"""
    try:
        # Delete from storage
        deleted = await storage.delete(file_id)

        return {"id": file_id, "object": "file", "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail={"message": str(e), "type": "server_error"}
        )


@router.get("/files/{file_id}/content")
async def download_file(
    file_id: str,
    api_key: str = Depends(verify_api_key_flexible),
    storage: StorageInterface = Depends(get_app_storage),
    config=Depends(get_app_config),
):
    """Download file content"""
    try:
        # Check if file exists
        if not await storage.exists(file_id):
            raise HTTPException(
                status_code=404,
                detail={
                    "message": f"File {file_id} not found",
                    "type": "not_found_error",
                },
            )

        # For S3: redirect to presigned URL
        # For local: return FileResponse
        if config.storage_backend == "s3":
            # Get presigned URL and redirect
            download_url = await storage.get_download_url(file_id, expires=3600)
            return RedirectResponse(url=download_url, status_code=302)
        else:
            # Local storage: return file directly
            file_path = await storage.get_file_path(file_id)
            return FileResponse(
                path=file_path,
                filename=f"{file_id}.jsonl",
                media_type="application/octet-stream",
            )

    except HTTPException:
        raise
    except StorageNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"message": f"File {file_id} not found", "type": "not_found_error"},
        )
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail={"message": str(e), "type": "server_error"}
        )


@router.get("/files")
async def list_files(
    api_key: str = Depends(verify_api_key_flexible),
    storage: StorageInterface = Depends(get_app_storage),
):
    """List all uploaded files"""
    try:
        # Get files from storage
        storage_files = await storage.list_files()

        # Format to match API contract
        files = []
        for file_meta in storage_files:
            files.append(
                {
                    "id": file_meta["id"],
                    "object": "file",
                    "bytes": file_meta["size"],
                    "created_at": int(file_meta["created_at"]),
                    "filename": file_meta["filename"],
                    "purpose": "batch",
                }
            )

        # Already sorted by storage interface (created_at descending)
        return {"object": "list", "data": files}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail={"message": str(e), "type": "server_error"}
        )
