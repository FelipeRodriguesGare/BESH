"""
Custom exceptions for BESH
"""


class BESHException(Exception):
    """Base exception for all BESH errors"""

    pass


class StorageException(BESHException):
    """Base exception for storage-related errors"""

    pass


class StorageNotFoundError(StorageException):
    """Raised when a file is not found in storage"""

    pass


class StorageUploadError(StorageException):
    """Raised when file upload fails"""

    pass


class StorageDownloadError(StorageException):
    """Raised when file download fails"""

    pass


class StorageConnectionError(StorageException):
    """Raised when storage backend connection fails"""

    pass


class ConfigurationError(BESHException):
    """Raised when configuration is invalid"""

    pass


class WorkerException(BESHException):
    """Base exception for worker-related errors"""

    pass


class ProcessingError(WorkerException):
    """Raised when batch processing fails"""

    pass


class QueueException(BESHException):
    """Raised when Redis queue operations fail"""

    pass
