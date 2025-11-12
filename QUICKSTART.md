# BESH Quick Start Guide

Get BESH up and running in 3 minutes!

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (if running CLI)
- UV (optional, for faster installation)

## Installation

### Option 1: Using UV (Recommended - Fast!)

```bash
# Install UV if you haven't
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install BESH
uv pip install -e .
```

### Option 2: Using pip

```bash
pip install -e .
```

## Setup & Run

### Step 1: Start Infrastructure (PostgreSQL + Redis)

```bash
# Quick start script
./run-infra.sh

# Or manually:
docker-compose -f docker-compose.infra.yml up -d
```

### Step 2: Configure Environment

Create a `.env` file in the project root (or copy from `.env.example`):

```bash
# REQUIRED: Your LLM API credentials
BESH_API_BASE=https://your-llm-provider.com/v1
BESH_API_KEY=your_api_key_here

# REQUIRED: Database (default for docker-compose.infra.yml)
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch

# Optional (all have sensible defaults):
BESH_REDIS_URL=redis://localhost:6379
BESH_BASIC_AUTH_USERNAME=admin
BESH_BASIC_AUTH_PASSWORD=changeme
BESH_AUTH_API_KEY=your_secret_key
BESH_STORAGE_BACKEND=local
BESH_UPLOAD_FOLDER=/tmp/batch_files
```

**✨ That's all you need!** These values will be automatically picked up from `.env`.


### Step 3: Start BESH

```bash
# Start full application (API + Workers)
# All settings from .env are automatically loaded!
besh serve --host 0.0.0.0 --port 8080
```

**No need to specify database URL, Redis URL, or API keys in the command!** They're read from `.env` automatically.

### Step 4: Access the Dashboard

Open your browser and go to:
- **Dashboard**: http://localhost:8080
- **API Docs**: http://localhost:8080/docs

Login with your `BASIC_AUTH_USERNAME` and `BASIC_AUTH_PASSWORD`.

## That's It! 🎉

You now have BESH running with:
- ✅ Web dashboard for monitoring batches
- ✅ REST API for batch processing
- ✅ Background workers processing jobs
- ✅ PostgreSQL for data persistence
- ✅ Redis for job queuing

## Common Commands

```bash
# Start with custom configuration
besh serve \
  --host 0.0.0.0 \
  --port 8080 \
  --api-processes 2 \
  --worker-processes 4

# Run API and workers separately
besh api --port 8080          # Terminal 1
besh worker --num-workers 4   # Terminal 2

# Use S3 storage instead of local
export STORAGE_BACKEND=s3
export S3_BUCKET=your-bucket
besh serve --host 0.0.0.0 --port 8080

# Test storage connection
besh test-storage

# Get help
besh --help
besh serve --help
```

## Example API Usage

```bash
# Upload a batch file
curl -X POST "http://localhost:8080/v1/files" \
  -H "X-API-Key: your_secret_key" \
  -F "file=@requests.jsonl" \
  -F "purpose=batch"

# Create a batch job
curl -X POST "http://localhost:8080/v1/batches" \
  -H "X-API-Key: your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{
    "input_file_id": "file-abc123",
    "endpoint": "/v1/chat/completions",
    "completion_window": "24h"
  }'

# Check batch status
curl "http://localhost:8080/v1/batches/batch-xyz789" \
  -H "X-API-Key: your_secret_key"
```

## Stopping Services

```bash
# Stop BESH CLI (Ctrl+C)

# Stop infrastructure
docker-compose -f docker-compose.infra.yml down
```

## Need Help?

- **Full CLI Documentation**: `docs/CLI_USAGE.md`
- **Infrastructure Setup**: `docs/INFRA_SETUP.md`
- **S3 Configuration**: See `docs/CLI_USAGE.md` Storage section
- **Troubleshooting**: Check `docs/INFRA_SETUP.md` Troubleshooting section

## What's Next?

- **Scale Workers**: Start additional workers with `besh worker`
- **Use S3 Storage**: Configure S3 for production deployments
- **Multi-GPU Setup**: See `docker-compose-multi-gpu.yml` for GPU configurations
- **Production Deployment**: See systemd examples in `docs/INFRA_SETUP.md`

Happy batch processing! 🚀

