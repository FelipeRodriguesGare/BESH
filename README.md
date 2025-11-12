
# BESH

![BESH Logo Banner](images/BESH_LOGO_BANNER.png)

A high-performance batch processing API for large language models with support for both single-GPU and multi-GPU (8-GPU) deployments.

**Now available as a pip-installable CLI tool with S3 support!**

## ✨ New: CLI & S3 Storage

BESH has been transformed into a modern Python package with:
- 🚀 **CLI Interface** - `besh serve`, `besh worker`, `besh api`
- ☁️ **S3 Storage** - Full S3 support with IAM authentication
- 📦 **Pip Installable** - Standard Python package
- ⚡ **UV Support** - 10x faster installation with UV
- 🔧 **Flexible Deployment** - CLI, Docker, or hybrid
- 🎯 **100% API Compatible** - No breaking changes

## Features

🚀 Intelligent Queue Management  
⚡ Advanced Parallel Processing  
🔄 Production-Ready Reliability  
📊 Real-Time Analytics Dashboard  
🎯 Enterprise-Scale Architecture  
💾 Persistent Storage (Local or S3)  
☁️ IAM Role Authentication  
🔧 Uvicorn-Style Process Management

## Quick Start

**📖 Complete guide**: See [QUICKSTART.md](QUICKSTART.md) for detailed setup

### Option 1: Infrastructure in Docker + CLI (Recommended)

```bash
# 1. Start PostgreSQL and Redis
./run-infra.sh
# Or: docker-compose -f docker-compose.infra.yml up -d

# 2. Install BESH with UV (fast)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv pip install -e .

# 3. Configure .env with your BESH_API_BASE and BESH_API_KEY

# 4. Start BESH
besh serve --host 0.0.0.0 --port 8080

# 5. Open http://localhost:8080
```

**Full command (everything loaded from .env):**

```bash
# Just configure .env with BESH_API_BASE, BESH_API_KEY, and BESH_DATABASE_URL
besh serve \
  --host 0.0.0.0 \
  --port 8080 \
  --api-processes 2 \
  --worker-processes 4
```

**Or override specific values:**

```bash
besh serve \
  --host 0.0.0.0 \
  --port 8080 \
  --database-url "postgresql+psycopg://custom:pass@host:5432/db" \
  --storage-backend s3 \
  --s3-bucket production-bucket
```

### Option 2: Full Docker Stack

```bash
# Standard deployment (combined API + workers)
docker-compose -f docker-compose.besh.yml up

# Or with separate worker scaling
docker-compose -f docker-compose.besh.yml up --scale besh-worker=8
```

### Option 3: Hybrid (Docker GPUs + CLI Workers)

```bash
# Terminal 1: Start GPU infrastructure
docker-compose -f docker-compose.gpus-only.yml up

# Terminal 2: Run CLI workers
besh worker --num-workers 12 --storage-backend s3 --s3-bucket prod
```

## Environment Variables

All configuration can be set via environment variables with the `BESH_` prefix. Legacy names (e.g., `NEBIUS_`, `OPENAI_`) are also supported for backward compatibility.

### Complete Configuration Reference

| Category | Variable | Description | Default | Required |
|----------|----------|-------------|---------|----------|
| **🔑 LLM API** |
| | `BESH_API_BASE` | LLM API endpoint (OpenAI-compatible) | `http://localhost:8000/v1` | ✅ Yes |
| | `BESH_API_KEY` | API key for LLM endpoint | `dummy-key` | ✅ Yes |
| | `BESH_MODEL_NAME` | Model name override (optional) | None | No |
| **💾 Database** |
| | `BESH_DATABASE_URL` | PostgreSQL connection URL | None | ✅ Yes |
| | `BESH_DB_POOL_SIZE` | Database connection pool size | `20` | No |
| | `BESH_DB_MAX_OVERFLOW` | Maximum pool overflow | `200` | No |
| **🔴 Redis** |
| | `BESH_REDIS_URL` | Redis connection URL | `redis://localhost:6379` | No |
| **🖥️ Server** |
| | `BESH_HOST` | API bind host | `0.0.0.0` | No |
| | `BESH_PORT` | API bind port | `8080` | No |
| | `BESH_API_WORKERS` | Number of API worker processes | `2` | No |
| | `BESH_BATCH_WORKERS` | Number of batch worker processes | `4` | No |
| **⚡ Worker Performance** |
| | `BESH_CONCURRENT_REQUESTS_PER_WORKER` | Max concurrent LLM requests per worker | `16` | No |
| **📦 Storage** |
| | `BESH_STORAGE_BACKEND` | Storage backend (`local` or `s3`) | `local` | No |
| | `BESH_UPLOAD_FOLDER` | Local storage directory | `/tmp/batch_files` | No |
| **☁️ S3 Configuration** |
| | `BESH_S3_BUCKET` | S3 bucket name | None | Required if `s3` |
| | `BESH_S3_REGION` | AWS region | `us-east-1` | No |
| | `BESH_S3_PROFILE` | AWS profile name (uses IAM role if empty) | None | No |
| | `BESH_S3_ENDPOINT_URL` | Custom S3 endpoint (MinIO, LocalStack) | None | No |
| | `BESH_S3_PRESIGNED_EXPIRY` | Presigned URL expiration (seconds) | `3600` | No |
| **🔐 Authentication** |
| | `BESH_BASIC_AUTH_USERNAME` | Basic auth username for web UI | None | No |
| | `BESH_BASIC_AUTH_PASSWORD` | Basic auth password for web UI | None | No |
| | `BESH_AUTH_API_KEY` | API key for batch endpoints | None | No |
| **🛠️ Development** |
| | `BESH_RELOAD` | Auto-reload on code changes | `false` | No |
| | `BESH_LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` | No |
| **🚀 Multi-GPU** |
| | `BESH_USE_LOAD_BALANCER` | LLM endpoint is a load balancer | `false` | No |
| | `BESH_REMOTE_CLUSTERS` | Remote cluster endpoints (comma-separated) | None | No |

### Configuration Best Practices

All configuration uses the `BESH_` prefix for clarity and consistency. Make sure your `.env` file uses these names.

### Example `.env` File

```bash
# ============================================
# REQUIRED (3 values - must be set)
# ============================================
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_api_key_here
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch

# ============================================
# OPTIONAL (everything below has defaults)
# ============================================

# Redis (default: redis://localhost:6379)
BESH_REDIS_URL=redis://localhost:6379

# Server (defaults: 0.0.0.0:8080, 2 API workers, 4 batch workers)
BESH_HOST=0.0.0.0
BESH_PORT=8080
BESH_API_WORKERS=2
BESH_BATCH_WORKERS=4

# Worker Performance (default: 16 concurrent requests per worker)
BESH_CONCURRENT_REQUESTS_PER_WORKER=16

# Storage (default: local)
BESH_STORAGE_BACKEND=local
BESH_UPLOAD_FOLDER=/tmp/batch_files

# S3 Storage (if using S3)
# BESH_STORAGE_BACKEND=s3
# BESH_S3_BUCKET=my-batch-files
# BESH_S3_REGION=us-east-1
# BESH_S3_PROFILE=production  # Optional, uses IAM role if not set

# Authentication (recommended for production)
BESH_BASIC_AUTH_USERNAME=admin
BESH_BASIC_AUTH_PASSWORD=your_secure_password
BESH_AUTH_API_KEY=your_api_key_here

# Database Tuning (optional)
BESH_DB_POOL_SIZE=20
BESH_DB_MAX_OVERFLOW=200

# Development (optional)
BESH_LOG_LEVEL=INFO
# BESH_RELOAD=true  # For development only
```

## Installation Methods

### Using UV (10x Faster)

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install BESH with all features
cd /path/to/BESH
uv sync --extra s3

# Run without virtualenv activation
uv run besh serve
```

### Using Pip

```bash
# Install from source
pip install -e ".[s3]"

# Run
besh serve --database-url postgresql://localhost/besh
```

## Documentation

- **[📚 Quick Start Guide](QUICKSTART.md)** - Get up and running in 3 minutes
- **[🔧 Infrastructure Setup](docs/INFRA_SETUP.md)** - Docker infra + CLI deployment  
- **[💻 CLI Usage](docs/CLI_USAGE.md)** - Complete CLI reference
- **[⚡ UV Installation](docs/UV_INSTALLATION.md)** - Fast package management

## CLI Commands

```bash
# All-in-one (API + workers)
besh serve --host 0.0.0.0 --port 8080 --api-processes 2 --worker-processes 4

# Workers only (for scaling)
besh worker --num-workers 8

# API only
besh api --host 0.0.0.0 --port 8080

# Test S3 connectivity
besh test-storage --storage-backend s3 --s3-bucket my-bucket

# Get help
besh --help
besh serve --help
```

## S3 Storage

```bash
# Using IAM role (EC2/ECS/Lambda)
besh serve --storage s3 --s3-bucket prod-batches

# Using AWS profile
besh serve --storage s3 --s3-bucket prod-batches --s3-profile production

# Using MinIO
besh serve \
  --storage s3 \
  --s3-bucket my-bucket \
  --s3-endpoint http://minio:9000
```

## Screenshots

![BESH Dashboard Overview](images/Bashboard_overview_new.png)

Features:
- See throughput per 15min
- See uploads per 15min
- See stats per 24h
- See and delete individual batches

## Architecture

### Multi-GPU with Load Balancing

```mermaid
graph TB
    subgraph "Client Layer"
        Client[Client Applications]
    end
    
    subgraph "API Layer"
        BatchAPI[Batch API<br/>:8080]
    end
    
    subgraph "Queue Layer"
        Queue[Redis Queue<br/>:6379]
    end
    
    subgraph "Worker Layer"
        Worker1[Worker 1]
        Worker2[Worker 2]  
        Worker3[Worker 3]
        Worker4[Worker 4]
    end
    
    subgraph "Load Balancer Layer"
        LB[Nginx Load Balancer<br/>:8000]
    end
    
    subgraph "vLLM Inference Layer"
        GPU0[vLLM GPU-0]
        GPU1[vLLM GPU-1]
        GPU2[vLLM GPU-2]
        GPU3[vLLM GPU-3]
        GPU4[vLLM GPU-4]
        GPU5[vLLM GPU-5]
        GPU6[vLLM GPU-6]
        GPU7[vLLM GPU-7]
    end
    
    subgraph "Storage Layer"
        DB[(PostgreSQL)]
        Storage[(S3 or Local)]
    end
    
    Client --> BatchAPI
    BatchAPI --> Queue
    BatchAPI --> DB
    BatchAPI --> Storage
    
    Queue --> Worker1
    Queue --> Worker2
    Queue --> Worker3
    Queue --> Worker4
    
    Worker1 --> LB
    Worker2 --> LB
    Worker3 --> LB
    Worker4 --> LB
    
    Worker1 --> Storage
    Worker2 --> Storage
    Worker3 --> Storage
    Worker4 --> Storage
    
    LB --> GPU0
    LB --> GPU1
    LB --> GPU2
    LB --> GPU3
    LB --> GPU4
    LB --> GPU5
    LB --> GPU6
    LB --> GPU7
```

## Deployment Scenarios

### 1. Development (Single Machine)
```bash
uv run besh serve --storage local
```

### 2. Production (S3 + Multi-GPU)
```bash
# GPU infrastructure (Docker)
docker-compose -f docker-compose.gpus-only.yml up

# Processing tier (CLI for easy scaling)
uv run besh worker --workers 12 --storage s3 --s3-bucket prod
```

### 3. Kubernetes
```bash
# API tier: kubectl scale deployment besh-api --replicas=4
# Worker tier: kubectl scale deployment besh-worker --replicas=16
```

## Performance Tips

- **Storage**: Use S3 for multi-worker deployments (no shared volume needed)
- **Workers**: Start with `--batch-workers 4`, adjust based on GPU capacity
- **Concurrency**: `BESH_CONCURRENT_REQUESTS_PER_WORKER=64` for small requests, 32 for large
- **Database**: Use connection pooling with `--db-pool-size 20`
- **Redis**: Ensure `maxmemory-policy allkeys-lru` is set

## Documentation

- [CLI Usage Guide](docs/CLI_USAGE.md) - Complete CLI reference
- [UV Installation](docs/UV_INSTALLATION.md) - Fast installation with UV
- [Migration Summary](MIGRATION_SUMMARY.md) - What's new in CLI version

## API Compatibility

**100% backward compatible** - All existing API clients work unchanged:
- ✅ Same endpoints (`/v1/files`, `/v1/batches`)
- ✅ Same request/response formats
- ✅ Same authentication
- ✅ Same web UI

## Examples

### Basic Usage
```bash
# Upload file
curl -X POST http://localhost:8080/v1/files \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@input.jsonl"

# Create batch
curl -X POST http://localhost:8080/v1/batches \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input_file_id": "file_xxx", "endpoint": "/v1/chat/completions"}'

# Check status
curl http://localhost:8080/v1/batches/batch_xxx \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Python Client
```python
import requests

api_base = "http://localhost:8080/v1"
headers = {"Authorization": "Bearer YOUR_API_KEY"}

# Upload file
with open("input.jsonl", "rb") as f:
    response = requests.post(
        f"{api_base}/files",
        headers=headers,
        files={"file": f}
    )
file_id = response.json()["id"]

# Create batch
response = requests.post(
    f"{api_base}/batches",
    headers=headers,
    json={
        "input_file_id": file_id,
        "endpoint": "/v1/chat/completions"
    }
)
batch_id = response.json()["id"]
```

## Testing

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# With coverage
uv run pytest --cov=besh --cov-report=html
```

## Helper Scripts

- [`scripts/check_batch.py`](scripts/check_batch.py) – CLI check batch from ID
- [`scripts/delete_x.py`](scripts/delete_x.py) – CLI delete files and/or batches

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contact

- **Author:** Floris Fok
- **📧 Email:** [floris.fok@prosus.com](mailto:floris.fok@prosus.com)
- **🔗 LinkedIn:** [floris-jan-fok](https://www.linkedin.com/in/floris-jan-fok/)

---

**New in v1.0.0:**
- 🎉 CLI interface with `besh` command
- ☁️ Full S3 storage support with IAM
- ⚡ UV support for 10x faster installation
- 🔧 Flexible deployment modes (CLI, Docker, hybrid)
- 📦 Pip-installable Python package
- 🎯 100% backward compatible API
