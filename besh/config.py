"""
Configuration management for BESH using Pydantic Settings

Supports multiple configuration sources:
1. CLI arguments
2. Environment variables (with BESH_ prefix)
3. .env file
4. YAML configuration file
"""

from pathlib import Path
from typing import Optional, Literal, List
from pydantic import Field, field_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging
import os

from besh.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_API_WORKERS,
    DEFAULT_BATCH_WORKERS,
    DEFAULT_CONCURRENT_REQUESTS_PER_WORKER,
    DEFAULT_UPLOAD_FOLDER,
    DEFAULT_S3_REGION,
    DEFAULT_S3_PRESIGNED_EXPIRY,
    DEFAULT_DB_POOL_SIZE,
    DEFAULT_DB_MAX_OVERFLOW,
    DEFAULT_REDIS_URL,
)

logger = logging.getLogger(__name__)


class BESHConfig(BaseSettings):
    """
    BESH configuration with validation

    Configuration priority (highest to lowest):
    1. CLI arguments
    2. Environment variables (BESH_ prefix)
    3. .env file
    4. YAML config file
    5. Defaults
    """

    model_config = SettingsConfigDict(
        env_prefix="BESH_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    host: str = Field(default=DEFAULT_HOST, description="API bind host")
    port: int = Field(default=DEFAULT_PORT, description="API bind port")
    api_workers: int = Field(
        default=DEFAULT_API_WORKERS, description="Number of API worker processes"
    )
    batch_workers: int = Field(
        default=DEFAULT_BATCH_WORKERS, description="Number of batch worker processes"
    )

    # Storage Configuration
    storage_backend: Literal["local", "s3"] = Field(
        default="local",
        description="Storage backend to use (local or s3)",
        validation_alias=AliasChoices(
            "storage_backend", "BESH_STORAGE_BACKEND", "STORAGE_BACKEND"
        ),
    )
    upload_folder: str = Field(
        default=DEFAULT_UPLOAD_FOLDER,
        description="Local storage folder (used when storage_backend=local)",
        validation_alias=AliasChoices(
            "upload_folder", "BESH_UPLOAD_FOLDER", "UPLOAD_FOLDER"
        ),
    )

    # S3 Configuration
    s3_bucket: Optional[str] = Field(
        default=None, description="S3 bucket name (required when storage_backend=s3)"
    )
    s3_region: str = Field(default=DEFAULT_S3_REGION, description="AWS region for S3")
    s3_profile: Optional[str] = Field(
        default=None,
        description="AWS profile name for authentication (optional, uses IAM role by default)",
    )
    s3_endpoint_url: Optional[str] = Field(
        default=None, description="Custom S3 endpoint URL (for MinIO, LocalStack, etc.)"
    )
    s3_presigned_expiry: int = Field(
        default=DEFAULT_S3_PRESIGNED_EXPIRY,
        description="Presigned URL expiration time in seconds",
    )

    # Database Configuration
    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (required - set via CLI or env)",
        validation_alias=AliasChoices(
            "database_url",
            "BESH_DATABASE_URL",
            "SQLALCHEMY_DATABASE_URI",
        ),
    )
    db_pool_size: int = Field(
        default=DEFAULT_DB_POOL_SIZE,
        description="Database connection pool size",
        validation_alias=AliasChoices(
            "db_pool_size", "BESH_DB_POOL_SIZE", "DB_POOL_SIZE"
        ),
    )
    db_max_overflow: int = Field(
        default=DEFAULT_DB_MAX_OVERFLOW,
        description="Maximum database connection pool overflow",
        validation_alias=AliasChoices(
            "db_max_overflow", "BESH_DB_MAX_OVERFLOW", "DB_MAX_OVERFLOW"
        ),
    )

    # Redis Configuration
    redis_url: str = Field(
        default=DEFAULT_REDIS_URL,
        description="Redis connection URL",
        validation_alias=AliasChoices("redis_url", "BESH_REDIS_URL", "REDIS_URL"),
    )

    # Worker Configuration
    concurrent_requests_per_worker: int = Field(
        default=DEFAULT_CONCURRENT_REQUESTS_PER_WORKER,
        description="Maximum concurrent LLM requests per batch worker",
        validation_alias=AliasChoices(
            "concurrent_requests_per_worker",
            "BESH_CONCURRENT_REQUESTS_PER_WORKER",
            "CONCURRENT_REQUESTS_PER_WORKER",
            # Legacy aliases for backward compatibility
            "max_workers",
            "BESH_MAX_WORKERS",
            "MAX_WORKERS",
            "worker_concurrency",
            "BESH_WORKER_CONCURRENCY",
            "WORKER_CONCURRENCY",
        ),
    )

    # LLM Configuration
    api_base: str = Field(
        default="http://localhost:8000/v1",
        description="LLM API endpoint (OpenAI-compatible)",
        validation_alias=AliasChoices(
            "api_base",
            "BESH_API_BASE",
            "openai_api_base",
            "BESH_OPENAI_API_BASE",
            "OPENAI_API_BASE",
            "NEBIUS_API_BASE",
        ),
    )
    api_key: str = Field(
        default="dummy-key",
        description="API key for LLM endpoint",
        validation_alias=AliasChoices(
            "api_key",
            "BESH_API_KEY",
            "openai_api_key",
            "BESH_OPENAI_API_KEY",
            "OPENAI_API_KEY",
            "NEBIUS_API_KEY",
        ),
    )
    model_name: Optional[str] = Field(
        default=None, description="Model name to use (optional override)"
    )

    # Authentication
    basic_auth_username: Optional[str] = Field(
        default=None,
        description="Basic auth username for web UI",
        validation_alias=AliasChoices(
            "basic_auth_username", "BESH_BASIC_AUTH_USERNAME", "BASIC_AUTH_USERNAME"
        ),
    )
    basic_auth_password: Optional[str] = Field(
        default=None,
        description="Basic auth password for web UI",
        validation_alias=AliasChoices(
            "basic_auth_password", "BESH_BASIC_AUTH_PASSWORD", "BASIC_AUTH_PASSWORD"
        ),
    )
    auth_api_key: Optional[str] = Field(
        default=None,
        description="API key for batch endpoints",
        validation_alias=AliasChoices("auth_api_key", "BESH_AUTH_API_KEY", "API_KEY"),
    )

    # Development
    reload: bool = Field(
        default=False, description="Auto-reload on code changes (development only)"
    )
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # Multi-GPU Configuration
    use_load_balancer: bool = Field(
        default=False, description="Whether LLM endpoint is a load balancer"
    )
    remote_clusters: List[str] = Field(
        default_factory=list,
        description="List of remote cluster endpoints for multi-cluster deployments",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v):
        """Ensure database URL is provided from somewhere"""
        if not v:
            raise ValueError(
                "Database URL is required. Set BESH_DATABASE_URL in .env or pass --database-url"
            )
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        """Validate port is in valid range"""
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("api_workers", "batch_workers", "concurrent_requests_per_worker")
    @classmethod
    def validate_positive(cls, v):
        """Validate worker counts are positive"""
        if v < 1:
            raise ValueError("Worker count must be positive")
        return v

    @field_validator("storage_backend")
    @classmethod
    def validate_storage(cls, v):
        """Validate storage backend"""
        if v not in ["local", "s3"]:
            raise ValueError('storage_backend must be "local" or "s3"')
        return v

    @field_validator("upload_folder")
    @classmethod
    def validate_upload_folder(cls, v):
        """Ensure upload_folder is an absolute path"""
        import os

        if not os.path.isabs(v):
            # Convert relative path to absolute
            v = os.path.abspath(v)
        return v

    def validate_config(self):
        """
        Validate configuration consistency

        Raises:
            ValueError: If configuration is invalid
        """
        from besh.exceptions import ConfigurationError

        # S3 validation
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ConfigurationError("s3_bucket is required when storage_backend='s3'")

        # Multi-worker storage warning
        if self.batch_workers > 1 and self.storage_backend == "local":
            logger.warning(
                f"Using local storage with {self.batch_workers} workers. "
                "Ensure all workers have access to the same shared volume, "
                "or consider using S3 storage for better scalability."
            )

        # Database URL validation
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            logger.warning(
                "database_url should start with 'postgresql://' or 'postgresql+psycopg://'"
            )

        # Redis URL validation
        if not self.redis_url.startswith("redis://"):
            logger.warning("redis_url should start with 'redis://'")

    @classmethod
    def from_yaml(cls, path: str) -> "BESHConfig":
        """
        Load configuration from YAML file

        Args:
            path: Path to YAML configuration file

        Returns:
            BESHConfig instance

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            ValueError: If YAML is invalid
        """
        import yaml

        yaml_path = Path(path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)

            logger.info(f"Loaded configuration from {path}")
            config = cls(**data)
            config.validate_config()
            return config

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load configuration: {e}")

    @classmethod
    def from_env(cls) -> "BESHConfig":
        """
        Load configuration from environment variables and .env file

        Returns:
            BESHConfig instance
        """
        config = cls()
        config.validate_config()
        return config

    def to_dict(self) -> dict:
        """Export configuration as dictionary"""
        return self.model_dump()

    def to_yaml(self, path: str):
        """
        Export configuration to YAML file

        Args:
            path: Output YAML file path
        """
        import yaml

        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

        logger.info(f"Exported configuration to {path}")

    def __repr__(self) -> str:
        """String representation (hiding sensitive data)"""
        safe_data = self.to_dict()
        # Hide sensitive fields
        for field in [
            "database_url",
            "redis_url",
            "openai_api_key",
            "basic_auth_password",
            "api_key",
        ]:
            if field in safe_data and safe_data[field]:
                safe_data[field] = "***HIDDEN***"

        return f"BESHConfig({safe_data})"


def get_config(**kwargs) -> BESHConfig:
    """
    Get BESH configuration with optional overrides

    Args:
        **kwargs: Configuration overrides

    Returns:
        BESHConfig instance
    """
    # Load from environment/file first
    config = BESHConfig.from_env()

    # Apply overrides from kwargs
    if kwargs:
        for key, value in kwargs.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

    config.validate_config()
    return config
