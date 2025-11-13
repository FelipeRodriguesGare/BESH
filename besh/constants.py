"""
Shared constants for BESH
"""

# Default configuration values
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_API_WORKERS = 2
DEFAULT_BATCH_WORKERS = 4
DEFAULT_CONCURRENT_REQUESTS_PER_WORKER = 64

# Chunking defaults
DEFAULT_CHUNK_SIZE = 10000  # Lines per chunk
DEFAULT_CHUNK_THRESHOLD = 0  # 0 = chunking disabled (opt-in feature)
DEFAULT_KEEP_CHUNKS = False  # Delete chunks after merge

# Database migration defaults
DEFAULT_AUTO_MIGRATE = True  # Run migrations automatically on startup

# Storage defaults
DEFAULT_UPLOAD_FOLDER = "/tmp/batch_files"
DEFAULT_S3_REGION = "us-east-1"
DEFAULT_S3_PRESIGNED_EXPIRY = 3600
DEFAULT_S3_STREAMING_ENABLED = False  # Start disabled for safety
DEFAULT_S3_PREFIX_INPUT = "besh/input"  # S3 prefix for input files
DEFAULT_S3_PREFIX_OUTPUT = "besh/output"  # S3 prefix for output/result files

# Database defaults
DEFAULT_DB_POOL_SIZE = 20
DEFAULT_DB_MAX_OVERFLOW = 200

# Redis defaults
DEFAULT_REDIS_URL = "redis://localhost:6379"

# Queue names
REDIS_BATCH_QUEUE = "batch_queue"
REDIS_BATCH_PROCESSING = "batch_processing"

# File extensions
JSONL_EXTENSION = ".jsonl"

# Timeouts and retries
SHUTDOWN_TIMEOUT = 3  # seconds - reduced for faster shutdown
S3_RETRY_COUNT = 3
S3_RETRY_BACKOFF_FACTOR = 2

# Multipart upload threshold
S3_MULTIPART_THRESHOLD = 10 * 1024 * 1024  # 10MB
S3_MULTIPART_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB
