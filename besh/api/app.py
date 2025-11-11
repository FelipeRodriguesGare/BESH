"""
FastAPI application for BESH

Initializes the API server with storage backend, routes, and lifecycle management.
"""

import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
import logging

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from besh.config import BESHConfig
from besh.storage import StorageInterface, get_storage

logger = logging.getLogger(__name__)

# Global state
_storage: Optional[StorageInterface] = None
_config: Optional[BESHConfig] = None
_cron_task: Optional[asyncio.Task] = None


def get_app_storage() -> StorageInterface:
    """
    Dependency injection for storage backend

    Returns:
        Configured storage interface
    """
    if _storage is None:
        raise RuntimeError("Storage not initialized. Call create_app() first.")
    return _storage


def get_app_config() -> BESHConfig:
    """
    Dependency injection for configuration

    Returns:
        BESH configuration
    """
    if _config is None:
        raise RuntimeError("Config not initialized. Call create_app() first.")
    return _config


async def cron_job():
    """
    Periodic task to check for lost batches every 5 minutes

    This job looks for batches that are stuck in 'in_progress' state
    and re-queues them for processing.
    """
    # Import here to avoid circular dependency
    from besh.api.routes.batch import add_to_redis_queue, length_of_redis_queue
    from besh.api.models.batch import get_lost_batches

    while True:
        try:
            # Only check if queue is empty
            queue_length = await length_of_redis_queue()
            if queue_length == 0:
                lost_batches = await get_lost_batches()
                if lost_batches:
                    logger.info(
                        f"Found {len(lost_batches)} lost batches, re-queuing..."
                    )
                    for batch_id in lost_batches:
                        await add_to_redis_queue(batch_id)
        except Exception as e:
            logger.error(f"Error in cron job: {e}", exc_info=True)

        # Wait 5 minutes (300 seconds) before next run
        await asyncio.sleep(300)


async def startup_recovery():
    """
    Recovery task to handle lost batches on startup

    Checks for batches that were interrupted during processing
    and re-queues them.
    """
    from besh.api.routes.batch import add_to_redis_queue
    from besh.api.models.batch import get_lost_batches_on_start_up

    try:
        lost_batches = await get_lost_batches_on_start_up()
        if lost_batches:
            logger.info(
                f"Found {len(lost_batches)} lost batches on startup, re-queuing..."
            )
            for batch_id in lost_batches:
                await add_to_redis_queue(batch_id)
        else:
            logger.info("No lost batches found on startup")
    except Exception as e:
        logger.error(f"Error in startup recovery: {e}", exc_info=True)


def create_app(config: Optional[BESHConfig] = None) -> FastAPI:
    """
    Create and configure FastAPI application

    Args:
        config: BESH configuration

    Returns:
        Configured FastAPI application
    """
    global _storage, _config

    # Load config if not provided (for Uvicorn workers)
    if config is None:
        from dotenv import load_dotenv

        load_dotenv()
        config = BESHConfig()

    # Store configuration for dependency injection
    _config = config

    # Initialize storage backend
    _storage = get_storage(config)
    logger.info(f"Initialized storage backend: {config.storage_backend}")

    # Ensure upload directory exists for local storage
    if config.storage_backend == "local":
        os.makedirs(config.upload_folder, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        FastAPI lifespan event handler

        Manages startup and shutdown tasks.
        """
        global _cron_task

        # Initialize database connection pool
        from besh.api.models.batch import init_db_pool

        await init_db_pool()
        logger.info("Database connection pool initialized")

        # Run startup recovery
        await startup_recovery()

        # Start the background cron job
        _cron_task = asyncio.create_task(cron_job())
        logger.info("Background cron job started")

        yield

        # Shutdown: cancel the cron job
        if _cron_task:
            _cron_task.cancel()
            try:
                await _cron_task
            except asyncio.CancelledError:
                logger.info("Background cron job cancelled")
            except Exception as e:
                logger.error(f"Error cancelling cron job: {e}")

    # Create FastAPI app with lifespan
    app = FastAPI(
        title="BESH - Batch Endpoint Service Handler",
        description="Production-ready batch processing for LLMs",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Enable CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    # Note: Importing here to avoid circular dependencies
    from besh.api.routes.batch import router as batch_router
    from besh.api.routes.files import router as files_router

    app.include_router(batch_router, prefix="/v1")
    app.include_router(files_router, prefix="/v1")

    # Mount static files
    static_folder = Path(__file__).parent.parent / "static"
    if static_folder.exists():
        app.mount("/static", StaticFiles(directory=str(static_folder)), name="static")
        logger.info(f"Mounted static files from {static_folder}")

    # Health check endpoint
    @app.get("/health")
    async def health():
        """Health check endpoint"""
        return {"status": "OK", "storage": config.storage_backend, "version": "1.0.0"}

    # Serve static files with auth (for web UI)
    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    async def serve_static(request: Request, path: str = ""):
        """
        Serve files from static folder or fall back to index.html

        Note: Authentication handled by routes if needed
        """
        static_dir = Path(__file__).parent.parent / "static"

        # Try to serve requested file
        if path:
            file_path = static_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)

        # Fall back to index.html
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        raise HTTPException(status_code=404, detail="Page not found")

    logger.info("FastAPI application created successfully")
    return app
