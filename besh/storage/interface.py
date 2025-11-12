"""
Abstract storage interface for BESH

Defines the contract that all storage backends must implement.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class StorageInterface(ABC):
    """
    Abstract interface for file storage backends

    All storage implementations (local, S3, etc.) must implement these methods.
    """

    @abstractmethod
    async def upload_stream(
        self,
        file_id: str,
        stream: AsyncIterator[bytes],
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Upload file from async byte stream

        Args:
            file_id: Unique identifier for the file
            stream: Async iterator yielding file content chunks
            metadata: Optional metadata to store with the file

        Returns:
            str: File ID of the uploaded file

        Raises:
            StorageUploadError: If upload fails
        """
        pass

    @abstractmethod
    async def download_stream(self, file_id: str) -> AsyncIterator[bytes]:
        """
        Download file as async byte stream

        Args:
            file_id: Unique identifier for the file

        Yields:
            bytes: Chunks of file content

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageDownloadError: If download fails
        """
        pass

    @abstractmethod
    async def read_lines(self, file_id: str) -> AsyncIterator[str]:
        """
        Stream file line by line (optimized for JSONL files)

        Args:
            file_id: Unique identifier for the file

        Yields:
            str: Individual lines from the file

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageDownloadError: If read fails
        """
        pass

    @abstractmethod
    async def write_lines(self, file_id: str, lines: AsyncIterator[str]) -> str:
        """
        Write lines to file (optimized for JSONL output)

        Args:
            file_id: Unique identifier for the file
            lines: Async iterator yielding lines to write

        Returns:
            str: File ID of the written file

        Raises:
            StorageUploadError: If write fails
        """
        pass

    @abstractmethod
    async def delete(self, file_id: str) -> bool:
        """
        Delete a file

        Args:
            file_id: Unique identifier for the file

        Returns:
            bool: True if file was deleted, False if it didn't exist

        Raises:
            StorageException: If deletion fails
        """
        pass

    @abstractmethod
    async def exists(self, file_id: str) -> bool:
        """
        Check if a file exists

        Args:
            file_id: Unique identifier for the file

        Returns:
            bool: True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_metadata(self, file_id: str) -> Dict:
        """
        Get file metadata (size, created_at, etc.)

        Args:
            file_id: Unique identifier for the file

        Returns:
            dict: File metadata with keys:
                - size (int): File size in bytes
                - created_at (float): Unix timestamp of creation
                - filename (str): Original filename

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def list_files(self, prefix: Optional[str] = None) -> List[Dict]:
        """
        List all files with optional prefix filter

        Args:
            prefix: Optional prefix to filter files

        Returns:
            list: List of file metadata dictionaries
        """
        pass

    @abstractmethod
    async def get_download_url(self, file_id: str, expires: int = 3600) -> str:
        """
        Get download URL for a file

        For S3: Returns presigned URL
        For local: Returns file path or local URL

        Args:
            file_id: Unique identifier for the file
            expires: URL expiration time in seconds (for presigned URLs)

        Returns:
            str: Download URL or file path

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def get_file_path(self, file_id: str) -> str:
        """
        Get the storage path for a file

        Args:
            file_id: Unique identifier for the file

        Returns:
            str: Storage path (local path or S3 key)
        """
        pass

    @abstractmethod
    async def count_lines(self, file_id: str) -> int:
        """
        Count total lines in a file (optimized for JSONL)

        Args:
            file_id: Unique identifier for the file

        Returns:
            int: Total number of lines in the file

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageException: If count fails
        """
        pass

    @abstractmethod
    async def read_lines_range(
        self, file_id: str, start: int, end: int
    ) -> AsyncIterator[tuple[int, str]]:
        """
        Read specific line range from file (for chunked processing)

        Args:
            file_id: Unique identifier for the file
            start: Starting line number (inclusive, 0-based)
            end: Ending line number (exclusive, 0-based)

        Yields:
            tuple[int, str]: (line_number, line_content) for each line in range

        Raises:
            StorageNotFoundError: If file doesn't exist
            StorageException: If read fails
        """
        pass
