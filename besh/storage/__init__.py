"""
Storage abstraction layer for BESH

Supports local filesystem and S3 storage backends.
"""

from besh.storage.interface import StorageInterface
from besh.storage.local import LocalStorage


def get_storage(config) -> StorageInterface:
    """
    Factory function to create storage backend based on configuration

    Args:
        config: BESHConfig instance

    Returns:
        StorageInterface: Configured storage backend

    Raises:
        ConfigurationError: If storage configuration is invalid
    """
    from besh.exceptions import ConfigurationError

    if config.storage_backend == "s3":
        try:
            from besh.storage.s3 import S3Storage
        except ImportError:
            raise ConfigurationError(
                "S3 storage requires aioboto3. Install with: pip install besh[s3]"
            )

        if not config.s3_bucket:
            raise ConfigurationError("S3 bucket name is required when using S3 storage")

        return S3Storage(
            bucket=config.s3_bucket,
            region=config.s3_region,
            profile=config.s3_profile,
            endpoint_url=config.s3_endpoint_url,
            presigned_expiry=config.s3_presigned_expiry,
        )
    else:
        return LocalStorage(config.upload_folder)


__all__ = ["StorageInterface", "LocalStorage", "get_storage"]
