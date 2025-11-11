# BESH CLI Usage Guide

BESH is now available as a pip-installable CLI tool with flexible deployment options.

## Installation

### Using UV (Recommended - 10x Faster)

UV is a fast Python package manager from Astral (creators of Ruff).

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install BESH with UV
cd /path/to/BESH
uv sync --extra s3

# Run directly with UV (no virtualenv activation needed)
uv run besh serve --database-url postgresql://localhost/besh
```

See [UV Installation Guide](UV_INSTALLATION.md) for detailed instructions.

### Using Pip (Traditional)

```bash
# From PyPI (when published)
pip install besh[s3]

# From source
cd /path/to/BESH
pip install -e ".[s3]"
```

## Quick Start

### 1. Basic Local Deployment

```bash
# Run API + workers together (simplest option)
besh serve \
  --database-url postgresql://user:pass@localhost:5432/besh \
  --storage local \
  --upload-folder /tmp/batch_files
```

### 2. With S3 Storage

```bash
# Using IAM role (EC2/ECS/Lambda)
besh serve \
  --database-url postgresql://user:pass@localhost:5432/besh \
  --storage s3 \
  --s3-bucket my-batch-files \
  --s3-region us-east-1

# Using named AWS profile
besh serve \
  --database-url postgresql://user:pass@localhost:5432/besh \
  --storage s3 \
  --s3-bucket my-batch-files \
  --s3-profile production
```

### 3. From Configuration File

```bash
# Generate sample config
besh init-config --output besh-config.yaml

# Edit config, then run
besh serve --config besh-config.yaml
```

## CLI Commands

### `besh serve`
Run API server and batch workers together (all-in-one deployment).

```bash
besh serve \
  --host 0.0.0.0 \
  --port 8080 \
  --api-workers 2 \
  --batch-workers 4 \
  --storage s3 \
  --s3-bucket my-bucket \
  --database-url postgresql://... \
  --redis-url redis://localhost:6379
```

**Options:**
- `--host`: API server host (default: 0.0.0.0)
- `--port`: API server port (default: 8080)
- `--api-workers`: Number of API worker processes (default: 2)
- `--batch-workers`: Number of batch worker processes (default: 4)
- `--storage`: Storage backend (local or s3, default: local)
- `--upload-folder`: Local storage folder (default: /tmp/batch_files)
- `--s3-bucket`: S3 bucket name (required if storage=s3)
- `--s3-region`: AWS region (default: us-east-1)
- `--s3-profile`: AWS profile name (optional)
- `--s3-endpoint`: Custom S3 endpoint for MinIO/LocalStack
- `--database-url`: PostgreSQL connection URL (required)
- `--redis-url`: Redis connection URL (default: redis://localhost:6379)
- `--openai-api-base`: LLM API endpoint (default: http://localhost:8000/v1)
- `--openai-api-key`: LLM API key (default: dummy-key)
- `--max-workers`: Concurrent tasks per batch worker (default: 64)
- `--reload`: Auto-reload on code changes (development only)
- `--log-level`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `--config`: Load from YAML config file

### `besh worker`
Run batch workers only (no API server).

```bash
besh worker \
  --workers 8 \
  --concurrency 64 \
  --storage s3 \
  --s3-bucket my-bucket \
  --database-url postgresql://... \
  --redis-url redis://localhost:6379
```

**Use cases:**
- Scale workers independently from API
- Hybrid deployment (Docker GPUs + CLI workers)
- Distributed processing across multiple machines

### `besh api`
Run API server only (no batch workers).

```bash
besh api \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 4 \
  --database-url postgresql://... \
  --storage s3 \
  --s3-bucket my-bucket
```

**Use cases:**
- Scale API separately from workers
- Load-balanced API tier with separate worker tier

### `besh test-storage`
Test storage backend connectivity.

```bash
# Test local storage
besh test-storage --storage local --upload-folder /tmp/batch_files

# Test S3 with IAM role
besh test-storage --storage s3 --s3-bucket my-bucket

# Test S3 with profile
besh test-storage --storage s3 --s3-bucket my-bucket --s3-profile prod

# Test MinIO
besh test-storage \
  --storage s3 \
  --s3-bucket my-bucket \
  --s3-endpoint http://localhost:9000
```

### `besh init-config`
Generate a sample configuration file.

```bash
besh init-config --output my-config.yaml
# Edit the file, then use with --config
```

### `besh version`
Show version and system information.

```bash
besh version
```

## Deployment Scenarios

### Scenario 1: Single Machine (Development)

```bash
# Start PostgreSQL and Redis
docker-compose -f docker-compose.gpus-only.yml up postgres redis

# Run BESH
besh serve \
  --database-url postgresql://user:pass@localhost:5432/besh \
  --redis-url redis://localhost:6379 \
  --storage local
```

### Scenario 2: Multi-GPU Cluster with CLI Workers

```bash
# Terminal 1: Start GPU infrastructure (nginx + 8 vLLM instances)
docker-compose -f docker-compose.gpus-only.yml up

# Terminal 2: Run API
besh api \
  --port 8080 \
  --workers 4 \
  --database-url postgresql://user:pass@localhost:5432/besh \
  --storage s3 \
  --s3-bucket prod-batches

# Terminal 3: Run workers (can scale independently)
besh worker \
  --workers 12 \
  --concurrency 64 \
  --database-url postgresql://user:pass@localhost:5432/besh \
  --storage s3 \
  --s3-bucket prod-batches \
  --openai-api-base http://localhost:8000/v1
```

### Scenario 3: Docker Deployment (Traditional)

```bash
# Use the new unified Docker image
docker-compose -f docker-compose.besh.yml up
```

### Scenario 4: Kubernetes Deployment

```yaml
# API Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: besh-api
spec:
  replicas: 4
  template:
    spec:
      containers:
      - name: besh
        image: besh:latest
        command: ["besh", "api", "--workers", "2"]
        env:
        - name: BESH_DATABASE_URL
          value: postgresql://...
        - name: BESH_STORAGE_BACKEND
          value: s3
        - name: BESH_S3_BUCKET
          value: prod-batches

---
# Worker Deployment (scalable)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: besh-worker
spec:
  replicas: 8
  template:
    spec:
      containers:
      - name: besh
        image: besh:latest
        command: ["besh", "worker", "--workers", "4"]
        env:
        - name: BESH_DATABASE_URL
          value: postgresql://...
        - name: BESH_STORAGE_BACKEND
          value: s3
        - name: BESH_S3_BUCKET
          value: prod-batches
```

## Configuration

### Environment Variables

All configuration can be set via environment variables with `BESH_` prefix:

```bash
export BESH_HOST=0.0.0.0
export BESH_PORT=8080
export BESH_STORAGE_BACKEND=s3
export BESH_S3_BUCKET=my-bucket
export BESH_DATABASE_URL=postgresql://...
export BESH_REDIS_URL=redis://...

# Then just run
besh serve
```

### YAML Configuration

```yaml
# besh-config.yaml
host: 0.0.0.0
port: 8080
api_workers: 4
batch_workers: 8

storage_backend: s3
s3_bucket: prod-batch-files
s3_region: us-east-1
s3_profile: production  # Optional

database_url: postgresql://user:pass@localhost:5432/besh
redis_url: redis://localhost:6379

openai_api_base: http://nginx-lb:8000/v1
openai_api_key: dummy-key

max_workers: 64
worker_concurrency: 16

log_level: INFO
```

### Priority Order

Configuration sources (highest to lowest priority):
1. CLI arguments
2. Environment variables (BESH_ prefix)
3. YAML config file (--config)
4. Defaults

## S3 Storage Configuration

### IAM Role Authentication (Recommended for Production)

```bash
# No credentials needed - uses EC2/ECS/Lambda IAM role
besh serve \
  --storage s3 \
  --s3-bucket my-bucket \
  --s3-region us-east-1 \
  --database-url postgresql://...
```

### Named Profile Authentication

```bash
# Uses ~/.aws/credentials profile
besh serve \
  --storage s3 \
  --s3-bucket my-bucket \
  --s3-profile production \
  --database-url postgresql://...
```

### Environment Variables Authentication

```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1

besh serve \
  --storage s3 \
  --s3-bucket my-bucket \
  --database-url postgresql://...
```

### MinIO / S3-Compatible Storage

```bash
besh serve \
  --storage s3 \
  --s3-bucket my-bucket \
  --s3-endpoint http://minio:9000 \
  --database-url postgresql://...
```

## Monitoring & Logging

### Logs

Logs go to stdout by default. Control level with `--log-level`:

```bash
besh serve --log-level DEBUG
```

### Health Check

```bash
curl http://localhost:8080/health
```

### Process Monitoring

BESH automatically monitors and restarts failed processes:
- API workers auto-restart on crash
- Batch workers auto-restart on crash
- Graceful shutdown on SIGTERM/SIGINT

## Troubleshooting

### Test Storage Connectivity

```bash
besh test-storage --storage s3 --s3-bucket my-bucket
```

### Check Configuration

```bash
# Generate and review config
besh init-config --output test-config.yaml
cat test-config.yaml
```

### Verify Installation

```bash
besh version
```

### Common Issues

**S3 Access Denied:**
```bash
# Check IAM permissions or use profile
besh test-storage --storage s3 --s3-bucket my-bucket --s3-profile prod
```

**Database Connection Failed:**
```bash
# Test connection
psql postgresql://user:pass@host:5432/dbname
```

**Redis Connection Failed:**
```bash
# Test connection
redis-cli -u redis://localhost:6379 ping
```

## Migration from Docker-Only

### Old Way (Docker)
```bash
docker-compose up --scale worker=4
```

### New Way (CLI)
```bash
# Option 1: Still use Docker
docker-compose -f docker-compose.besh.yml up

# Option 2: Use CLI
besh serve --api-workers 2 --batch-workers 4

# Option 3: Hybrid (Docker GPUs + CLI workers)
docker-compose -f docker-compose.gpus-only.yml up
besh worker --workers 12
```

## Advanced Usage

### Custom Worker Concurrency

```bash
# High concurrency for small requests
besh worker --workers 4 --concurrency 128

# Low concurrency for large requests
besh worker --workers 8 --concurrency 32
```

### Separate API and Worker Scaling

```bash
# Machine 1: API tier
besh api --workers 8 --port 8080

# Machines 2-4: Worker tier
besh worker --workers 16  # Run on each machine
```

### Development with Auto-Reload

```bash
besh serve --reload --log-level DEBUG
```

## Next Steps

- [Configuration Reference](CONFIGURATION.md)
- [S3 Setup Guide](S3_SETUP.md)
- [Deployment Guide](DEPLOYMENT.md)
- [API Documentation](API.md)

