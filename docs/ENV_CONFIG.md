# Environment Configuration Guide

## Simple Answer: No, You Don't Need to Specify Everything in the CLI!

**✅ Just use a `.env` file and BESH will automatically load everything.**

## Quick Setup

### 1. Create `.env` file with minimum requirements:

```bash
# Only 3 things are REQUIRED:
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_actual_key_here
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch
```

**Note:** Uses clean `BESH_` prefix. Legacy names like `NEBIUS_API_BASE`, `SQLALCHEMY_DATABASE_URI` also work.

### 2. Start BESH (that's it!)

```bash
besh serve --host 0.0.0.0 --port 8080
```

Everything from `.env` is **automatically loaded**. No need to pass database URL, Redis URL, or API keys in the command!

## What Gets Auto-Loaded from `.env`?

| Setting | Recommended Variable | Legacy Names | Auto-Loaded? | Required? |
|---------|---------------------|--------------|--------------|-----------|
| API Endpoint | `BESH_API_BASE` | `NEBIUS_API_BASE`, `OPENAI_API_BASE` | ✅ Yes | ✅ Yes |
| API Key | `BESH_API_KEY` | `NEBIUS_API_KEY`, `OPENAI_API_KEY` | ✅ Yes | ✅ Yes |
| Database | `BESH_DATABASE_URL` | `SQLALCHEMY_DATABASE_URI`, `DATABASE_URL` | ✅ Yes | ✅ Yes |
| Redis | `BESH_REDIS_URL` | `REDIS_URL` | ✅ Yes | ❌ No (default: `redis://localhost:6379`) |
| Auth Username | `BESH_BASIC_AUTH_USERNAME` | `BASIC_AUTH_USERNAME` | ✅ Yes | ❌ No (optional) |
| Auth Password | `BESH_BASIC_AUTH_PASSWORD` | `BASIC_AUTH_PASSWORD` | ✅ Yes | ❌ No (optional) |
| Auth API Key | `BESH_AUTH_API_KEY` | `API_KEY` | ✅ Yes | ❌ No (optional) |
| Storage | `BESH_STORAGE_BACKEND` | `STORAGE_BACKEND` | ✅ Yes | ❌ No (default: `local`) |
| Upload Folder | `BESH_UPLOAD_FOLDER` | `UPLOAD_FOLDER` | ✅ Yes | ❌ No (default: `/tmp/batch_files`) |
| Max Workers | `BESH_MAX_WORKERS` | `MAX_WORKERS` | ✅ Yes | ❌ No (default: `64`) |

## Complete `.env` Example

**Recommended (Clean BESH_ prefix):**

```bash
# ============================================
# REQUIRED (3 values)
# ============================================
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_api_key_here
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch

# ============================================
# OPTIONAL (everything below has defaults)
# ============================================

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
BESH_DB_POOL_SIZE=20
BESH_DB_MAX_OVERFLOW=200
```

## Supported Naming Conventions

BESH uses `BESH_` prefix (recommended) but also accepts legacy names for backward compatibility:

### API Credentials
```bash
# Recommended (generic, clean):
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_key

# Legacy (also work):
NEBIUS_API_BASE=https://api.nebius.ai/v1
NEBIUS_API_KEY=your_key
OPENAI_API_BASE=https://api.nebius.ai/v1
OPENAI_API_KEY=your_key
```

### Database URL
```bash
# Recommended:
BESH_DATABASE_URL=postgresql://...

# Legacy (also work):
SQLALCHEMY_DATABASE_URI=postgresql://...
DATABASE_URL=postgresql://...
```

### Redis URL
```bash
# Recommended:
BESH_REDIS_URL=redis://localhost:6379

# Legacy (also works):
REDIS_URL=redis://localhost:6379
```

## Configuration Priority

BESH reads config in this order (highest priority first):

```
1. CLI Arguments        (--db-url "postgresql://...")
   ↓
2. Shell Environment    (export DATABASE_URL="...")
   ↓
3. .env File            (DATABASE_URL=...)
   ↓
4. Defaults             (redis://localhost:6379)
```

## Examples

### Example 1: Minimal Setup (Recommended)

**`.env` file:**
```bash
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_key_here
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch
```

**Command:**
```bash
besh serve --host 0.0.0.0 --port 8080
```

### Example 2: Override Storage via CLI

**`.env` file:**
```bash
BESH_API_BASE=https://api.nebius.ai/v1
BESH_API_KEY=your_key_here
BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch
BESH_STORAGE_BACKEND=local
```

**Command (override to use S3):**
```bash
besh serve --host 0.0.0.0 --port 8080 --storage-backend s3 --s3-bucket prod-bucket
```

### Example 3: Development with Custom Redis

**`.env` file:**
```bash
BESH_API_BASE=http://localhost:8000/v1
BESH_API_KEY=dummy-key
BESH_DATABASE_URL=postgresql+psycopg://dev:dev@localhost:5432/batch_dev
BESH_REDIS_URL=redis://localhost:6380
```

**Command:**
```bash
besh serve --host 0.0.0.0 --port 8080 --log-level debug
```

## Common Questions

### Q: Do I need to pass `--db-url` in the CLI?
**A:** No! If `BESH_DATABASE_URL` (or legacy `SQLALCHEMY_DATABASE_URI`, `DATABASE_URL`) is in your `.env`, it's automatically loaded.

### Q: Do I need to pass `--redis-url` in the CLI?
**A:** No! If `BESH_REDIS_URL` (or legacy `REDIS_URL`) is in your `.env`, it's automatically loaded. If not specified anywhere, it defaults to `redis://localhost:6379`.

### Q: Do I need to specify LLM API credentials in the CLI?
**A:** No! Put `BESH_API_BASE` and `BESH_API_KEY` in your `.env` and they're automatically loaded. Legacy names like `NEBIUS_API_BASE`, `OPENAI_API_BASE` also work.

### Q: What if I want to override a .env value?
**A:** Just pass it as a CLI argument:
```bash
besh serve --db-url "postgresql://different-host/db"
```

### Q: Can I use environment variables instead of .env?
**A:** Yes! Set them in your shell:
```bash
export NEBIUS_API_BASE=https://api.nebius.ai/v1
export NEBIUS_API_KEY=your_key
besh serve
```

### Q: What's the minimum command to run BESH?
**A:** If you have a properly configured `.env`:
```bash
besh serve
```

That's it! Default host is `0.0.0.0` and port is `8080`.

## Troubleshooting

### Error: "DATABASE_URL not set"
- Check that your `.env` file exists in the project root
- Verify it contains `BESH_DATABASE_URL=postgresql://...` (or legacy `SQLALCHEMY_DATABASE_URI`)
- Or set it in your shell: `export BESH_DATABASE_URL="postgresql://..."`

### Error: "Could not connect to database"
- Verify PostgreSQL is running: `docker-compose -f docker-compose.infra.yml ps postgres`
- Test connection: `psql postgresql://besh:besh_password@localhost:5432/batch`

### Error: "Could not connect to Redis"
- Verify Redis is running: `docker-compose -f docker-compose.infra.yml ps redis`
- Test connection: `redis-cli -h localhost -p 6379 ping`

### BESH doesn't see my .env file
- Make sure `.env` is in the same directory where you run `besh`
- Check file permissions: `ls -la .env`
- Try setting env vars explicitly: `export BESH_API_BASE=...`

## Summary

**You DON'T need to specify in CLI:**
- ❌ Database URL (auto-loaded from `BESH_DATABASE_URL` in `.env`)
- ❌ Redis URL (auto-loaded from `BESH_REDIS_URL` in `.env` or uses default)
- ❌ LLM API credentials (auto-loaded from `BESH_API_BASE` and `BESH_API_KEY` in `.env`)
- ❌ Authentication settings (auto-loaded from `.env`)
- ❌ Storage settings (auto-loaded from `.env` or uses default)

**You ONLY need to specify in CLI (if you want):**
- ✅ Host and port (defaults are usually fine)
- ✅ Number of API/worker processes (for scaling)
- ✅ Overrides for testing (e.g., different S3 bucket)

**Typical usage:**
```bash
# Everything from .env
besh serve

# Or with custom processes
besh serve --api-processes 2 --worker-processes 4
```

