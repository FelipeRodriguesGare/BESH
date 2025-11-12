"""
Result Merger for BESH

Handles merging chunk output files into final batch results.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
import redis.asyncio as redis

from besh.config import BESHConfig
from besh.storage import get_storage, StorageInterface
from besh.api.models.batch import (
    init_db_pool,
    get_batch,
    get_batch_chunks,
    update_batch_status,
    update_batch_completion,
)
from besh.exceptions import StorageNotFoundError

logger = logging.getLogger(__name__)


class ResultMerger:
    """
    Merges chunk results into final batch output

    Listens to merge_queue and combines chunk files when all chunks are complete.
    """

    def __init__(self, config: BESHConfig):
        """
        Initialize result merger

        Args:
            config: BESH configuration
        """
        self.config = config
        self.redis_client: Optional[redis.Redis] = None
        self.storage: Optional[StorageInterface] = None

    async def initialize(self):
        """Initialize connections"""
        # Initialize Redis from URL
        self.redis_client = redis.from_url(
            self.config.redis_url,
            decode_responses=True,
        )

        # Initialize storage
        self.storage = get_storage(self.config)

        # Initialize database pool
        await init_db_pool(
            database_url=self.config.database_url,
            pool_size=self.config.db_pool_size,
            max_overflow=self.config.db_max_overflow,
        )

        logger.info("Result merger initialized successfully")

    async def merge_batch_chunks(self, batch_id: str):
        """
        Merge all chunks for a batch into final output file

        Args:
            batch_id: Batch identifier
        """
        start_time = datetime.now()
        logger.info(f"Starting merge for batch: {batch_id}")

        try:
            # Get batch data
            batch = await get_batch(batch_id)
            if not batch:
                logger.error(f"Batch {batch_id} not found")
                return

            # Get all chunks for this batch
            chunks = await get_batch_chunks(batch_id)
            if not chunks:
                logger.error(f"No chunks found for batch {batch_id}")
                return

            # Sort chunks by chunk_id to maintain order
            chunks = sorted(chunks, key=lambda c: c["chunk_id"])

            logger.info(f"Merging {len(chunks)} chunks for batch {batch_id}")

            # Verify all chunks are completed
            incomplete_chunks = [c for c in chunks if c["status"] != "completed"]
            if incomplete_chunks:
                logger.warning(
                    f"Batch {batch_id} has {len(incomplete_chunks)} incomplete chunks. "
                    "Skipping merge."
                )
                return

            # Prepare output file
            output_file_id = f"r_{batch_id}"

            # Aggregate statistics
            total_successful = 0
            total_errors = 0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_total_tokens = 0

            # Merge chunk files into single output
            async def merged_lines():
                """Generator that yields lines from all chunks in order"""
                for chunk in chunks:
                    chunk_output_file = chunk["output_file"]
                    if not chunk_output_file:
                        logger.warning(
                            f"Chunk {chunk['chunk_id']} has no output file, skipping"
                        )
                        continue

                    # Check if chunk file exists
                    if not await self.storage.exists(chunk_output_file):
                        logger.warning(
                            f"Chunk output file {chunk_output_file} not found, skipping"
                        )
                        continue

                    # Stream lines from chunk file
                    try:
                        async for line in self.storage.read_lines(chunk_output_file):
                            yield line
                    except Exception as e:
                        logger.error(
                            f"Error reading chunk file {chunk_output_file}: {e}"
                        )
                        raise

            # Write merged output
            try:
                await self.storage.write_lines(output_file_id, merged_lines())
                logger.info(f"Successfully wrote merged output to {output_file_id}")
            except Exception as e:
                logger.error(f"Failed to write merged output: {e}")
                await update_batch_status(batch_id, "failed")
                return

            # Aggregate statistics from chunks
            for chunk in chunks:
                total_successful += chunk.get("request_counts_completed", 0) or 0
                total_errors += chunk.get("request_counts_failed", 0) or 0
                total_prompt_tokens += chunk.get("prompt_tokens", 0) or 0
                total_completion_tokens += chunk.get("completion_tokens", 0) or 0
                total_total_tokens += chunk.get("total_tokens", 0) or 0

            # Update batch completion status
            await update_batch_completion(
                batch_id,
                output_file_id,
                total_successful,
                total_errors,
                total_prompt_tokens,
                total_completion_tokens,
                total_total_tokens,
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Batch {batch_id} merge completed: "
                f"{total_successful} successful, {total_errors} errors "
                f"({len(chunks)} chunks merged in {duration:.2f}s)"
            )

            # Optionally delete chunk files
            if not self.config.keep_chunks:
                logger.info(f"Deleting chunk files for batch {batch_id}")
                for chunk in chunks:
                    chunk_output_file = chunk["output_file"]
                    if chunk_output_file and await self.storage.exists(
                        chunk_output_file
                    ):
                        try:
                            await self.storage.delete(chunk_output_file)
                            logger.debug(f"Deleted chunk file: {chunk_output_file}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete chunk file {chunk_output_file}: {e}"
                            )

        except Exception as e:
            logger.error(f"Error merging batch {batch_id}: {e}")
            await update_batch_status(batch_id, "failed")


class MergerWorker:
    """
    Worker that processes merge jobs from the merge queue
    """

    def __init__(self, config: BESHConfig):
        """
        Initialize merger worker

        Args:
            config: BESH configuration
        """
        self.config = config
        self.merger = ResultMerger(config)

    async def start(self):
        """Start merger worker (blocking)"""
        await self.merger.initialize()

        logger.info("Merger worker started and waiting for merge jobs...")

        while True:
            try:
                # Wait for merge jobs
                job_data = await self.merger.redis_client.brpoplpush(
                    "merge_queue", "merge_processing", timeout=1
                )

                if job_data:
                    batch_id = job_data
                    logger.info(f"Received merge job for batch: {batch_id}")

                    try:
                        await self.merger.merge_batch_chunks(batch_id)

                        # Remove from processing list
                        await self.merger.redis_client.lrem(
                            "merge_processing", 1, batch_id
                        )
                        logger.info(f"Merge job completed for batch: {batch_id}")

                    except Exception as e:
                        logger.error(
                            f"Error processing merge job for batch {batch_id}: {e}"
                        )
                        # Keep in processing list for potential retry
                        # In production, implement retry logic or dead letter queue

            except asyncio.CancelledError:
                logger.info("Merger worker cancelled, shutting down...")
                break
            except Exception as e:
                logger.error(f"Merger worker error: {e}")
                await asyncio.sleep(1)


async def run_merger_worker(config: BESHConfig):
    """
    Entry point for running merger worker

    Args:
        config: BESH configuration
    """
    worker = MergerWorker(config)
    await worker.start()
