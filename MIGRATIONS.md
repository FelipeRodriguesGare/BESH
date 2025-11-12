# Database Migrations Guide

BESH uses SQL migration files to manage database schema changes. This document explains how migrations work and how to use them.

## Overview

All database schema changes are managed through SQL migration files located in `besh/api/models/migrations/`. Migrations run in alphabetical order based on filename.

## Migration Files

### Current Migrations

1. **`000_create_batches_table.sql`** - Creates the main `batches` table with all columns and indexes
2. **`001_add_batch_chunks.sql`** - Adds the `batch_chunks` table for chunking support

### Adding New Migrations

To create a new migration:

1. Create a new SQL file in `besh/api/models/migrations/` with a sequential number prefix:
   ```
   002_add_new_feature.sql
   ```

2. Write your SQL (supports CREATE TABLE, ALTER TABLE, CREATE INDEX, etc.):
   ```sql
   -- Add description column to batches
   ALTER TABLE batches ADD COLUMN IF NOT EXISTS description TEXT;
   ```

3. The migration will run automatically on next startup (if `BESH_AUTO_MIGRATE=true`)

## Running Migrations

### Automatic Migrations (Default)

Migrations run automatically when the application starts:

```bash
# Default behavior - migrations run on startup
besh serve

# Or with environment variable explicitly set
BESH_AUTO_MIGRATE=true besh serve
```

### Manual Migrations (Opt-Out)

Disable automatic migrations and run them manually:

**Option 1: Environment Variable**
```bash
# Set in .env file
BESH_AUTO_MIGRATE=false

# Start application (no migrations)
besh serve

# Run migrations separately
besh migrate
```

**Option 2: CLI Flag**
```bash
# Run migrations with custom database URL
besh migrate --database-url postgresql://user:pass@localhost/besh

# Or let it use .env configuration
besh migrate
```

## Use Cases for Manual Migrations

### 1. CI/CD Pipelines

Run migrations as a separate step before deployment:

```bash
# deployment-pipeline.sh
echo "Running database migrations..."
besh migrate --database-url $DATABASE_URL

echo "Starting application..."
BESH_AUTO_MIGRATE=false besh serve
```

### 2. Kubernetes Init Containers

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: besh-migrate
spec:
  template:
    spec:
      containers:
      - name: migrate
        image: besh:latest
        command: ["besh", "migrate"]
        env:
        - name: BESH_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
      restartPolicy: OnFailure
```

### 3. Database Initialization

Initialize a new database before first deployment:

```bash
# Initialize database
docker-compose up -d postgres redis

# Run migrations only
besh migrate

# Start application without re-running migrations
BESH_AUTO_MIGRATE=false besh serve
```

### 4. Migration Debugging

Test migrations independently:

```bash
# Disable auto-migrate
export BESH_AUTO_MIGRATE=false

# Run migrations with verbose logging
besh migrate 2>&1 | tee migration.log

# Check results
psql $DATABASE_URL -c "\d batches"
psql $DATABASE_URL -c "\d batch_chunks"
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BESH_AUTO_MIGRATE` | `true` | Run migrations automatically on startup |
| `BESH_DATABASE_URL` | (required) | PostgreSQL connection URL |

### Configuration Priority

1. CLI arguments (`--database-url`)
2. Environment variables (`BESH_DATABASE_URL`)
3. `.env` file
4. Config defaults

## Migration Safety

### Idempotent Migrations

All migrations use `IF NOT EXISTS` and `IF EXISTS` clauses to be safely re-runnable:

```sql
-- Safe to run multiple times
CREATE TABLE IF NOT EXISTS my_table (...);
ALTER TABLE my_table ADD COLUMN IF NOT EXISTS my_column TEXT;
CREATE INDEX IF NOT EXISTS idx_name ON my_table(column);
```

### Error Handling

- Migration errors are logged but don't fail the application startup (for auto-migrate)
- Manual migrations (`besh migrate`) will exit with error code on failure
- Already-applied migrations are skipped with a warning

## Examples

### Development Workflow

```bash
# Start with auto-migrate (default)
besh serve

# Make schema changes
echo "ALTER TABLE batches ADD COLUMN priority INT;" > \
  besh/api/models/migrations/002_add_priority.sql

# Restart (migration runs automatically)
# Press Ctrl+C, then:
besh serve
```

### Production Workflow

```bash
# Disable auto-migrate in production
echo "BESH_AUTO_MIGRATE=false" >> .env

# Deploy new version with migration
git pull
besh migrate
systemctl restart besh

# Or with Docker
docker-compose up -d postgres redis
docker-compose run --rm api besh migrate
docker-compose up -d api worker
```

### Multi-Environment Setup

```bash
# Development - auto-migrate enabled
ENV=development besh serve

# Staging - manual control
ENV=staging BESH_AUTO_MIGRATE=false besh serve
besh migrate --database-url $STAGING_DB_URL

# Production - strict control
ENV=production BESH_AUTO_MIGRATE=false besh serve
# Migrations run separately by DevOps team
```

## Troubleshooting

### Migration Not Running

Check if auto-migrate is enabled:
```bash
# Check configuration
besh version

# Force migration run
besh migrate
```

### Migration Failed

View detailed error:
```bash
# Run with debug logging
LOG_LEVEL=DEBUG besh migrate

# Check PostgreSQL logs
docker-compose logs postgres
```

### Already Applied

Migrations use `IF NOT EXISTS` - safe to re-run. If you see warnings, migrations are already applied.

### Rollback

Migrations don't have automatic rollback. To rollback:

1. Create a new migration that reverses changes:
   ```sql
   -- 003_rollback_feature.sql
   ALTER TABLE batches DROP COLUMN IF EXISTS feature_column;
   ```

2. Or manually revert in database:
   ```bash
   psql $DATABASE_URL -c "ALTER TABLE batches DROP COLUMN feature_column;"
   ```

## Best Practices

1. **Always use `IF NOT EXISTS` / `IF EXISTS`** - Makes migrations idempotent
2. **Test migrations locally first** - Run `besh migrate` on dev database
3. **Backup before migrating** - Take database snapshot before production migrations
4. **Keep migrations small** - One logical change per migration file
5. **Don't modify existing migrations** - Create new ones to fix issues
6. **Use descriptive names** - `002_add_user_roles.sql` not `002_update.sql`
7. **Add comments** - Explain why the change is needed

## FAQ

**Q: Do I need to run migrations manually?**  
A: No, by default they run automatically on startup. Manual mode is optional for advanced deployments.

**Q: What happens if a migration fails?**  
A: With auto-migrate, errors are logged and the app continues. With manual migrate, the command exits with error.

**Q: Can I skip migrations?**  
A: Yes, set `BESH_AUTO_MIGRATE=false` and don't run `besh migrate`.

**Q: How do I know which migrations have run?**  
A: Check your PostgreSQL database for existing tables. Future enhancement could add a migrations tracking table.

**Q: Can I use this with Alembic/Flyway?**  
A: Yes, disable `BESH_AUTO_MIGRATE` and use your preferred migration tool.

