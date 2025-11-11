# BESH Infrastructure Setup

This guide shows how to run BESH using Docker for infrastructure (PostgreSQL + Redis) and the CLI for the application.

## Quick Start

### 1. Start Infrastructure Services

```bash
# Start PostgreSQL and Redis
docker-compose -f docker-compose.infra.yml up -d

# Verify services are running
docker-compose -f docker-compose.infra.yml ps
```

### 2. Configure Environment Variables

Create a `.env` file in the project root (copy from `.env.example` and edit):

**Minimum Required Configuration:**

```bash
# REQUIRED (only 3 values needed!)
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_api_key_here
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch
```

**That's it!** Everything else has sensible defaults. Optional settings:

```bash
# Redis (default: redis://localhost:6379)
BESH_REDIS_URL=redis://localhost:6379

# Authentication (recommended for production)
BESH_BASIC_AUTH_USERNAME=admin
BESH_BASIC_AUTH_PASSWORD=your_secure_password
BESH_AUTH_API_KEY=your_api_key_here

# Storage (default: local)
BESH_STORAGE_BACKEND=local
BESH_UPLOAD_FOLDER=/tmp/batch_files

# Worker tuning (optional)
BESH_MAX_WORKERS=64
BESH_WORKER_CONCURRENCY=16
```

**✨ All values from `.env` are automatically loaded!** No need to pass them via CLI.

**Note:** Legacy names like `NEBIUS_API_BASE`, `OPENAI_API_BASE`, `SQLALCHEMY_DATABASE_URI` are still supported for backward compatibility.

### 3. Start BESH Application

**Option A: Full Stack (API + Workers) - Simplest**

```bash
# Everything loaded from .env automatically!
besh serve --host 0.0.0.0 --port 8080
```

**Option A with more processes:**

```bash
besh serve \
  --host 0.0.0.0 \
  --port 8080 \
  --api-processes 2 \
  --worker-processes 4
```

**Option B: API and Workers Separately**

Terminal 1 - Start API:
```bash
besh api --host 0.0.0.0 --port 8080
```

Terminal 2 - Start Workers:
```bash
besh worker --num-workers 4
```

### 4. Access the Application

- **Web UI Dashboard**: http://localhost:8080
- **API Documentation**: http://localhost:8080/docs
- **Health Check**: http://localhost:8080/health

## Configuration Priority

BESH reads configuration in this order (highest priority first):

1. **CLI arguments** - Override everything
2. **Environment variables** - From your shell
3. **`.env` file** - Loaded automatically
4. **Defaults** - Sensible built-in values

### Supported Environment Variable Names

BESH uses the `BESH_` prefix for all config (recommended), but also supports legacy names for backward compatibility:

| Config | Recommended | Also Supported (Legacy) |
|--------|------------|------------------------|
| API Base | `BESH_API_BASE` | `NEBIUS_API_BASE`, `OPENAI_API_BASE` |
| API Key | `BESH_API_KEY` | `NEBIUS_API_KEY`, `OPENAI_API_KEY` |
| Database | `BESH_DATABASE_URL` | `SQLALCHEMY_DATABASE_URI`, `DATABASE_URL` |
| Redis | `BESH_REDIS_URL` | `REDIS_URL` |
| Storage | `BESH_STORAGE_BACKEND` | `STORAGE_BACKEND` |
| Auth Username | `BESH_BASIC_AUTH_USERNAME` | `BASIC_AUTH_USERNAME` |
| Auth Password | `BESH_BASIC_AUTH_PASSWORD` | `BASIC_AUTH_PASSWORD` |
| Auth API Key | `BESH_AUTH_API_KEY` | `API_KEY` |

### Override via CLI (Optional)

You can override any `.env` value via command line:

```bash
# Override specific values
besh serve \
  --host 0.0.0.0 \
  --port 8080 \
  --storage-backend s3 \
  --s3-bucket my-production-bucket
```

## Using with S3 Storage

If you want to use S3 instead of local storage:

```bash
# In your .env or environment:
export STORAGE_BACKEND=s3
export S3_BUCKET=your-bucket-name
export S3_REGION=us-east-1
# Optional: for non-AWS S3-compatible storage
export S3_ENDPOINT_URL=https://s3.amazonaws.com
# Optional: use specific AWS profile
export AWS_PROFILE=your-profile

besh serve --host 0.0.0.0 --port 8080
```

Or with command-line arguments:

```bash
besh serve \
  --storage-backend s3 \
  --s3-bucket your-bucket-name \
  --s3-region us-east-1
```

## Connecting to External GPU Infrastructure

If you have vLLM or other GPU services running separately (e.g., via `docker-compose.gpus-only.yml`):

```bash
# In your .env:
NEBIUS_API_BASE=http://localhost:8000/v1  # or your GPU load balancer
NEBIUS_API_KEY=dummy-key

# Then start BESH
besh serve --host 0.0.0.0 --port 8080
```

## Stopping Services

```bash
# Stop BESH CLI (Ctrl+C in the terminal)

# Stop infrastructure
docker-compose -f docker-compose.infra.yml down

# Stop infrastructure and remove volumes (WARNING: deletes all data)
docker-compose -f docker-compose.infra.yml down -v
```

## Customizing Database Credentials

To use different database credentials, edit `docker-compose.infra.yml`:

```yaml
postgres:
  environment:
    - POSTGRES_USER=your_username
    - POSTGRES_PASSWORD=your_password
    - POSTGRES_DB=batch
```

Then update your `.env`:

```bash
SQLALCHEMY_DATABASE_URI=postgresql+psycopg://your_username:your_password@localhost:5432/batch
```

## Scaling Workers

Scale workers dynamically by starting additional worker processes:

```bash
# Terminal 1: API
besh api --port 8080

# Terminal 2: Workers (set 1)
besh worker --num-workers 4

# Terminal 3: More workers (set 2)
besh worker --num-workers 4

# Terminal 4: Even more workers (set 3)
besh worker --num-workers 4
```

All workers will connect to the same Redis queue and process batches in parallel.

## Production Deployment

For production, consider:

1. **Use strong credentials** for PostgreSQL and Redis
2. **Enable SSL/TLS** for database connections
3. **Use S3 storage** for scalability
4. **Run multiple API processes** behind a load balancer
5. **Scale workers** based on queue depth
6. **Set up monitoring** (see logs with `--log-level debug`)
7. **Use systemd or supervisord** to manage BESH processes

Example systemd service file (`/etc/systemd/system/besh.service`):

```ini
[Unit]
Description=BESH Batch Processing Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=besh
WorkingDirectory=/opt/besh
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/besh/.env
ExecStart=/usr/local/bin/besh serve --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Monitoring

Check logs in real-time:

```bash
# Application logs
besh serve --log-level debug

# Infrastructure logs
docker-compose -f docker-compose.infra.yml logs -f

# PostgreSQL logs only
docker-compose -f docker-compose.infra.yml logs -f postgres

# Redis logs only
docker-compose -f docker-compose.infra.yml logs -f redis
```

## Troubleshooting

### Connection refused to PostgreSQL

```bash
# Check if PostgreSQL is running
docker-compose -f docker-compose.infra.yml ps postgres

# Check PostgreSQL logs
docker-compose -f docker-compose.infra.yml logs postgres

# Test connection
psql postgresql://besh:besh_password@localhost:5432/batch
```

### Connection refused to Redis

```bash
# Check if Redis is running
docker-compose -f docker-compose.infra.yml ps redis

# Test Redis connection
redis-cli -h localhost -p 6379 ping
```

### Workers not processing batches

```bash
# Check Redis queue length
redis-cli -h localhost -p 6379 LLEN batch_queue

# Check worker logs (run with debug)
besh worker --log-level debug
```

## Advanced Configuration

See `docs/CLI_USAGE.md` for all available CLI options and configuration details.

