import asyncpg
import os
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# Database connection pool
_db_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        await init_db_pool()
    return _db_pool


async def init_db_pool(
    database_url: Optional[str] = None,
    pool_size: Optional[int] = None,
    max_overflow: Optional[int] = None,
    auto_migrate: Optional[bool] = None,
):
    """
    Initialize database connection pool

    Args:
        database_url: Database connection URL (optional, will use config/env if not provided)
        pool_size: Connection pool size (optional, will use config/env if not provided)
        max_overflow: Max overflow connections (optional, will use config/env if not provided)
        auto_migrate: Whether to run migrations automatically (optional, will use config/env if not provided)
    """
    global _db_pool

    # Get database URL from config or environment
    try:
        from besh.api.app import get_app_config

        config = get_app_config()
        sqlalchemy_uri = database_url or config.database_url
        pool_size = pool_size or config.db_pool_size
        max_overflow = max_overflow or config.db_max_overflow
        auto_migrate = auto_migrate if auto_migrate is not None else config.auto_migrate
    except:
        # Fallback to environment variables
        sqlalchemy_uri = (
            database_url
            or os.getenv("SQLALCHEMY_DATABASE_URI")
            or os.getenv("BESH_DATABASE_URL")
        )
        if not sqlalchemy_uri:
            raise ValueError("DATABASE_URL not set in config or environment")
        pool_size = pool_size or int(os.getenv("DB_POOL_SIZE", "5"))
        max_overflow = max_overflow or int(os.getenv("DB_MAX_OVERFLOW", "20"))
        auto_migrate = (
            auto_migrate
            if auto_migrate is not None
            else os.getenv("BESH_AUTO_MIGRATE", "true").lower() in ("true", "1", "yes")
        )

    parsed = urllib.parse.urlparse(sqlalchemy_uri)
    db_host = parsed.hostname
    db_port = parsed.port or 5432
    db_user = parsed.username
    db_password = parsed.password
    db_name = parsed.path.lstrip("/")

    _db_pool = await asyncpg.create_pool(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name,
        min_size=pool_size,
        max_size=pool_size + max_overflow,
    )

    # Test connection
    async with _db_pool.acquire() as conn:
        await conn.fetchval("SELECT 1")

    logger.info("Database connection pool initialized")

    # Run migrations if enabled
    if auto_migrate:
        logger.info("Auto-migrate enabled, running migrations...")
        await run_migrations()
    else:
        logger.info(
            "Auto-migrate disabled, skipping migrations. Run 'besh migrate' to apply migrations manually."
        )


async def run_migrations():
    """Run database migrations from SQL files"""
    import os
    from pathlib import Path

    pool = await get_db_pool()
    migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return

    # Get list of SQL files sorted by name
    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        logger.info("No migration files found")
        return

    for sql_file in sql_files:
        logger.info(f"Running migration: {sql_file.name}")

        try:
            with open(sql_file, "r") as f:
                sql_content = f.read()

            async with pool.acquire() as conn:
                await conn.execute(sql_content)

            logger.info(f"Migration {sql_file.name} completed successfully")
        except Exception as e:
            # Log but don't fail - tables might already exist
            logger.warning(
                f"Migration {sql_file.name} had an issue (may already be applied): {e}"
            )


def batch_row_to_dict(row) -> Dict[str, Any]:
    """Convert database row to dictionary for JSON response"""
    if not row:
        return None

    result = {
        "id": row["id"],
        "object": row["object"],
        "endpoint": row["endpoint"],
        "input_file_id": row["input_file_id"],
        "completion_window": row["completion_window"],
        "status": row["status"],
        "created_at": (
            int(row["created_at"].timestamp()) if row.get("created_at") else None
        ),
    }

    # Add optional fields if they exist
    if row.get("output_file_id"):
        result["output_file_id"] = row["output_file_id"]

    if row.get("in_progress_at"):
        result["in_progress_at"] = int(row["in_progress_at"].timestamp())

    if row.get("completed_at"):
        result["completed_at"] = int(row["completed_at"].timestamp())

    if row.get("failed_at"):
        result["failed_at"] = int(row["failed_at"].timestamp())

    if row.get("expired_at"):
        result["expired_at"] = int(row["expired_at"].timestamp())

    if row.get("cancelled_at"):
        result["cancelled_at"] = int(row["cancelled_at"].timestamp())

    if row.get("expires_at"):
        result["expires_at"] = int(row["expires_at"].timestamp())

    if row.get("finalizing_at"):
        result["finalizing_at"] = int(row["finalizing_at"].timestamp())

    # Add token usage fields if they exist
    if row.get("total_tokens") is not None:
        result["total_tokens"] = row["total_tokens"]

    if row.get("prompt_tokens") is not None:
        result["prompt_tokens"] = row["prompt_tokens"]

    if row.get("completion_tokens") is not None:
        result["completion_tokens"] = row["completion_tokens"]

    if row.get("request_failed") is not None:
        result["request_failed"] = row["request_failed"]

    if row.get("request_completed") is not None:
        result["request_completed"] = row["request_completed"]

    if row.get("request_total") is not None:
        result["request_total"] = row["request_total"]

    return result


async def create_batch(
    batch_id: str,
    object_type: str,
    endpoint: str,
    input_file_id: str,
    completion_window: str,
    status: str,
    created_at: datetime,
    expires_at: datetime,
):
    """Create a new batch record"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO batches (
                id, object, endpoint, input_file_id, completion_window, 
                status, created_at, expires_at, total_tokens, prompt_tokens, 
                completion_tokens, request_failed, request_completed, request_total
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, 0, 0, 0, 0, 0)
        """,
            batch_id,
            object_type,
            endpoint,
            input_file_id,
            completion_window,
            status,
            created_at,
            expires_at,
        )


async def get_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    """Get batch by ID"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM batches WHERE id = $1", batch_id)
        return batch_row_to_dict(row) if row else None


async def get_batches_paginated(
    limit: int = 20, after_created_at: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Get batches with pagination"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if after_created_at:
            rows = await conn.fetch(
                """
                SELECT * FROM batches 
                WHERE created_at < $1 
                ORDER BY created_at DESC 
                LIMIT $2
            """,
                after_created_at,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM batches 
                ORDER BY created_at DESC 
                LIMIT $1
            """,
                limit,
            )

        return [batch_row_to_dict(row) for row in rows]


async def get_batches_in_timerange(
    start_time: datetime, end_time: datetime
) -> List[Dict[str, Any]]:
    """Get batches within a time range"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM batches 
            WHERE created_at >= $1 AND created_at <= $2
            ORDER BY created_at DESC
        """,
            start_time,
            end_time,
        )

        return [batch_row_to_dict(row) for row in rows]


async def get_completed_batches_in_timerange(
    start_time: datetime, end_time: datetime
) -> List[Dict[str, Any]]:
    """Get completed batches within a time range"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM batches 
            WHERE completed_at >= $1 AND completed_at <= $2
            AND completed_at IS NOT NULL
            AND in_progress_at IS NOT NULL
            AND created_at IS NOT NULL
            ORDER BY completed_at DESC
        """,
            start_time,
            end_time,
        )

        return [batch_row_to_dict(row) for row in rows]


async def update_batch_status(batch_id: str, status: str):
    """Update batch status with appropriate timestamp"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if status == "in_progress":
            await conn.execute(
                "UPDATE batches SET status = $1, in_progress_at = NOW() WHERE id = $2",
                status,
                batch_id,
            )
        elif status == "completed":
            await conn.execute(
                "UPDATE batches SET status = $1, completed_at = NOW() WHERE id = $2",
                status,
                batch_id,
            )
        elif status == "failed":
            await conn.execute(
                "UPDATE batches SET status = $1, failed_at = NOW() WHERE id = $2",
                status,
                batch_id,
            )
        elif status == "cancelled":
            await conn.execute(
                "UPDATE batches SET status = $1, cancelled_at = NOW() WHERE id = $2",
                status,
                batch_id,
            )
        else:
            await conn.execute(
                "UPDATE batches SET status = $1 WHERE id = $2", status, batch_id
            )


async def update_batch_completion(
    batch_id: str,
    output_file_path: str,
    request_total: int,
    request_completed: int,
    request_failed: int,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
):
    """Update batch with completion data"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE batches SET 
                status = 'completed',
                completed_at = NOW(),
                output_file_id = $1,
                request_total = $2,
                request_completed = $3,
                request_failed = $4,
                prompt_tokens = $5,
                completion_tokens = $6,
                total_tokens = $7
            WHERE id = $8
        """,
            output_file_path,
            int(request_total),
            int(request_completed),
            int(request_failed),
            int(prompt_tokens),
            int(completion_tokens),
            int(total_tokens),
            batch_id,
        )


async def cancel_batch(batch_id: str):
    """Cancel a batch"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE batches SET status = 'cancelled', cancelled_at = NOW() WHERE id = $1",
            batch_id,
        )


async def delete_batch(batch_id: str):
    """Delete a batch"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM batches WHERE id = $1", batch_id)


async def count_batches() -> int:
    """Count total batches"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM batches")


async def count_batches_by_status(statuses: List[str]) -> int:
    """Count batches by status"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM batches WHERE status = ANY($1)", statuses
        )


async def get_batch_status_counts() -> List[tuple]:
    """Get batch counts grouped by status"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT status, COUNT(*) as count FROM batches GROUP BY status"
        )


async def get_request_counts_sum(start_time: datetime, end_time: datetime) -> tuple:
    """Get sum of request counts within time range"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT 
                COALESCE(SUM(request_total), 0) as total_batches,
                COALESCE(SUM(request_failed), 0) as failed_batches
            FROM batches 
            WHERE created_at >= $1 AND created_at <= $2
        """,
            start_time,
            end_time,
        )
        return result["total_batches"], result["failed_batches"]


async def get_lost_batches() -> List[str]:
    """Get lost batches"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id FROM batches WHERE status in ('validating', 'queued')
        """
        )
        returning_ids = [row["id"] for row in rows]

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE batches SET status = 'queued' WHERE id = ANY($1)
        """,
            returning_ids,
        )

    return returning_ids


async def get_lost_batches_on_start_up() -> List[str]:
    """Get lost batches on start up"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id FROM batches WHERE status in ('validating', 'in_progress', 'queued')
        """
        )
        returning_ids = [row["id"] for row in rows]

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE batches SET status = 'queued' WHERE id = ANY($1)
        """,
            returning_ids,
        )

    return returning_ids


# ============================================================================
# CHUNK CRUD OPERATIONS
# ============================================================================


async def create_batch_chunk(
    batch_id: str,
    chunk_id: int,
    line_start: int,
    line_end: int,
) -> None:
    """Create a new batch chunk record"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO batch_chunks (
                batch_id, chunk_id, status, line_start, line_end,
                request_count, successful_count, failed_count
            ) VALUES ($1, $2, 'pending', $3, $4, 0, 0, 0)
            """,
            batch_id,
            chunk_id,
            line_start,
            line_end,
        )


async def get_batch_chunk(batch_id: str, chunk_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific batch chunk"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM batch_chunks 
            WHERE batch_id = $1 AND chunk_id = $2
            """,
            batch_id,
            chunk_id,
        )
        if not row:
            return None

        return {
            "id": row["id"],
            "batch_id": row["batch_id"],
            "chunk_id": row["chunk_id"],
            "status": row["status"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "output_file_id": row.get("output_file_id"),
            "completed_at": row.get("completed_at"),
            "error": row.get("error"),
            "request_count": row.get("request_count", 0),
            "successful_count": row.get("successful_count", 0),
            "failed_count": row.get("failed_count", 0),
            "created_at": row.get("created_at"),
        }


async def get_batch_chunks(
    batch_id: str, status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all chunks for a batch, optionally filtered by status"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT * FROM batch_chunks 
                WHERE batch_id = $1 AND status = $2
                ORDER BY chunk_id ASC
                """,
                batch_id,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM batch_chunks 
                WHERE batch_id = $1
                ORDER BY chunk_id ASC
                """,
                batch_id,
            )

        return [
            {
                "id": row["id"],
                "batch_id": row["batch_id"],
                "chunk_id": row["chunk_id"],
                "status": row["status"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "output_file_id": row.get("output_file_id"),
                "completed_at": row.get("completed_at"),
                "error": row.get("error"),
                "request_count": row.get("request_count", 0),
                "successful_count": row.get("successful_count", 0),
                "failed_count": row.get("failed_count", 0),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]


async def update_chunk_status(
    batch_id: str, chunk_id: int, status: str, error: Optional[str] = None
) -> None:
    """Update chunk status"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if error:
            await conn.execute(
                """
                UPDATE batch_chunks 
                SET status = $1, error = $2
                WHERE batch_id = $3 AND chunk_id = $4
                """,
                status,
                error,
                batch_id,
                chunk_id,
            )
        else:
            await conn.execute(
                """
                UPDATE batch_chunks 
                SET status = $1
                WHERE batch_id = $2 AND chunk_id = $3
                """,
                status,
                batch_id,
                chunk_id,
            )


async def update_chunk_completion(
    batch_id: str,
    chunk_id: int,
    successful_count: int,
    failed_count: int,
    output_file_id: str,
) -> None:
    """Mark chunk as completed with statistics"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE batch_chunks 
            SET status = 'completed',
                successful_count = $1,
                failed_count = $2,
                request_count = $3,
                output_file_id = $4,
                completed_at = NOW()
            WHERE batch_id = $5 AND chunk_id = $6
            """,
            successful_count,
            failed_count,
            successful_count + failed_count,
            output_file_id,
            batch_id,
            chunk_id,
        )


async def all_chunks_completed(batch_id: str) -> bool:
    """Check if all chunks for a batch are completed"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Count total chunks
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM batch_chunks WHERE batch_id = $1", batch_id
        )

        # Count completed chunks
        completed = await conn.fetchval(
            """
            SELECT COUNT(*) FROM batch_chunks 
            WHERE batch_id = $1 AND status = 'completed'
            """,
            batch_id,
        )

        return total > 0 and total == completed
