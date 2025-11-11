"""
Local filesystem storage implementation for BESH
"""

import os
import aiofiles
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional
from datetime import datetime
import logging

from besh.storage.interface import StorageInterface
from besh.exceptions import (
    StorageNotFoundError,
    StorageUploadError,
    StorageDownloadError,
    StorageException,
)
from besh.constants import JSONL_EXTENSION

logger = logging.getLogger(__name__)


class LocalStorage(StorageInterface):
    """
    Local filesystem storage backend

    Stores files in a local directory with .jsonl extension.
    """

    def __init__(self, upload_folder: str):
        """
        Initialize local storage

        Args:
            upload_folder: Base directory for file storage
        """
        self.upload_folder = Path(upload_folder)
        self.upload_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized LocalStorage at {self.upload_folder}")

    def _get_file_path(self, file_id: str) -> Path:
        """Get full path for a file ID"""
        # Ensure file_id has .jsonl extension
        if not file_id.endswith(JSONL_EXTENSION):
            file_id = f"{file_id}{JSONL_EXTENSION}"
        return self.upload_folder / file_id

    async def upload_stream(
        self,
        file_id: str,
        stream: AsyncIterator[bytes],
        metadata: Optional[Dict] = None,
    ) -> str:
        """Upload file from async byte stream"""
        file_path = self._get_file_path(file_id)

        try:
            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in stream:
                    await f.write(chunk)

            logger.info(f"Uploaded file {file_id} to {file_path}")
            return file_id

        except Exception as e:
            logger.error(f"Failed to upload file {file_id}: {e}")
            # Clean up partial file
            if file_path.exists():
                file_path.unlink()
            raise StorageUploadError(f"Failed to upload file {file_id}: {e}")

    async def download_stream(self, file_id: str) -> AsyncIterator[bytes]:
        """Download file as async byte stream"""
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            raise StorageNotFoundError(f"File {file_id} not found")

        try:
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            raise StorageDownloadError(f"Failed to download file {file_id}: {e}")

    async def read_lines(self, file_id: str) -> AsyncIterator[str]:
        """Stream file line by line"""
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            raise StorageNotFoundError(f"File {file_id} not found")

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                async for line in f:
                    yield line.rstrip("\n")
        except Exception as e:
            logger.error(f"Failed to read lines from file {file_id}: {e}")
            raise StorageDownloadError(f"Failed to read lines from file {file_id}: {e}")

    async def write_lines(self, file_id: str, lines: AsyncIterator[str]) -> str:
        """Write lines to file"""
        file_path = self._get_file_path(file_id)

        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                async for line in lines:
                    await f.write(line)
                    if not line.endswith("\n"):
                        await f.write("\n")

            logger.info(f"Wrote lines to file {file_id}")
            return file_id

        except Exception as e:
            logger.error(f"Failed to write lines to file {file_id}: {e}")
            # Clean up partial file
            if file_path.exists():
                file_path.unlink()
            raise StorageUploadError(f"Failed to write lines to file {file_id}: {e}")

    async def delete(self, file_id: str) -> bool:
        """Delete a file"""
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted file {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            raise StorageException(f"Failed to delete file {file_id}: {e}")

    async def exists(self, file_id: str) -> bool:
        """Check if file exists"""
        file_path = self._get_file_path(file_id)
        return file_path.exists()

    async def get_metadata(self, file_id: str) -> Dict:
        """Get file metadata"""
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            raise StorageNotFoundError(f"File {file_id} not found")

        try:
            stat = file_path.stat()
            return {
                "id": file_id,
                "filename": file_path.name,
                "size": stat.st_size,
                "created_at": stat.st_ctime,
                "modified_at": stat.st_mtime,
            }
        except Exception as e:
            logger.error(f"Failed to get metadata for file {file_id}: {e}")
            raise StorageException(f"Failed to get metadata for file {file_id}: {e}")

    async def list_files(self, prefix: Optional[str] = None) -> List[Dict]:
        """List all files with optional prefix filter"""
        try:
            files = []

            for file_path in self.upload_folder.glob(
                f"{prefix or ''}*{JSONL_EXTENSION}"
            ):
                if file_path.is_file():
                    stat = file_path.stat()
                    # Extract file_id (remove extension)
                    file_id = file_path.stem

                    files.append(
                        {
                            "id": file_id,
                            "filename": file_path.name,
                            "size": stat.st_size,
                            "created_at": stat.st_ctime,
                            "modified_at": stat.st_mtime,
                        }
                    )

            # Sort by created_at descending
            files.sort(key=lambda x: x["created_at"], reverse=True)
            return files

        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            raise StorageException(f"Failed to list files: {e}")

    async def get_download_url(self, file_id: str, expires: int = 3600) -> str:
        """Get download URL (returns file path for local storage)"""
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            raise StorageNotFoundError(f"File {file_id} not found")

        # For local storage, return the absolute path
        # In production with FastAPI, this would be handled by FileResponse
        return str(file_path.absolute())

    async def get_file_path(self, file_id: str) -> str:
        """Get the storage path for a file"""
        return str(self._get_file_path(file_id))
