"""
Batch processing worker for BESH

Processes batch jobs from Redis queue using storage abstraction.
"""

import asyncio
import json
import uuid
import signal
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import os
import litellm

try:
    import uvloop  # type: ignore

    uvloop.install()
except ImportError:
    pass

import redis.asyncio as redis

from besh.config import BESHConfig
from besh.storage import get_storage, StorageInterface
from besh.api.models.batch import (
    init_db_pool,
    get_batch,
    update_batch_status,
    update_batch_completion,
    get_batch_chunk,
    update_chunk_status,
    update_chunk_completion,
    all_chunks_completed,
)
from besh.exceptions import StorageNotFoundError

# Configure logging
logger = logging.getLogger(__name__)

# Configure litellm
litellm.set_verbose = False


class FileProcessor:
    """
    Processes batch files using storage abstraction

    Supports both local and S3 storage backends.
    """

    def __init__(self, config: BESHConfig):
        """
        Initialize file processor

        Args:
            config: BESH configuration
        """
        self.config = config
        self.max_concurrency = config.concurrent_requests_per_worker
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.redis_client: Optional[redis.Redis] = None
        self.storage: Optional[StorageInterface] = None

        # Configure litellm (it expects OPENAI_* env vars)
        # Debug: Log what we're setting
        logger.info(f"Setting OPENAI_API_BASE to: {config.api_base}")
        logger.info(
            f"Setting OPENAI_API_KEY to: {config.api_key[:10]}..."
            if config.api_key
            else "Setting OPENAI_API_KEY to: None"
        )

        # Strip /v1 or /v1/ from the end of api_base if present
        # The OpenAI SDK automatically appends /v1/chat/completions

        os.environ["OPENAI_API_BASE"] = config.api_base
        os.environ["OPENAI_API_KEY"] = config.api_key

        # Verify they're set correctly
        logger.debug(f"Verified OPENAI_API_BASE: {os.environ.get('OPENAI_API_BASE')}")
        logger.debug(
            f"Verified OPENAI_API_KEY: {os.environ.get('OPENAI_API_KEY', '')[:10]}..."
        )

        # Model name override
        self.model_name = config.model_name if hasattr(config, "model_name") else None

    async def initialize(self):
        """Initialize database, Redis, and storage connections"""
        try:
            # Initialize database connection pool
            await init_db_pool()
            logger.info("Database connection successful")

            # Initialize Redis connection
            logger.info(f"Connecting to Redis: {self.config.redis_url}")
            self.redis_client = redis.from_url(
                self.config.redis_url, decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Redis connection successful")

            # Initialize storage backend
            self.storage = get_storage(self.config)
            logger.info(f"Storage backend initialized: {self.config.storage_backend}")

        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            raise

    async def update_job_status(self, batch_id: str, status: str):
        """Update job status in database"""
        # Map processing status to in_progress for consistency
        status_mapping = {"processing": "in_progress"}
        actual_status = status_mapping.get(status, status)
        await update_batch_status(batch_id, actual_status)

    async def get_batch(self, batch_id: str):
        """Get batch from database"""
        return await get_batch(batch_id)

    async def update_batch_completion(
        self,
        batch_id: str,
        output_file_id: str,
        successful_count: int,
        error_count: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ):
        """Update batch with completion data"""
        await update_batch_completion(
            batch_id,
            output_file_id,
            successful_count + error_count,  # request_total
            successful_count,  # request_completed
            error_count,  # request_failed
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

    def _is_chunk_job(self, job_id: str) -> tuple[bool, str, int]:
        """
        Check if job_id is a chunk job

        Returns:
            tuple: (is_chunk, batch_id, chunk_id)
        """
        if ":chunk:" in job_id:
            parts = job_id.split(":chunk:")
            if len(parts) == 2:
                batch_id = parts[0]
                try:
                    chunk_id = int(parts[1])
                    return (True, batch_id, chunk_id)
                except ValueError:
                    pass
        return (False, job_id, -1)

    async def process_file_stream(self, job_id: str):
        """
        Process file stream with high concurrency and streaming writes

        Automatically detects if this is a chunk job or whole file job.
        """
        is_chunk, batch_id, chunk_id = self._is_chunk_job(job_id)

        if is_chunk:
            logger.info(f"Processing chunk {chunk_id} of batch {batch_id}")
            await self._process_chunk(batch_id, chunk_id)
        else:
            logger.info(f"Processing whole file for batch {batch_id}")
            await self._process_whole_file(batch_id)

    async def _process_chunk(self, batch_id: str, chunk_id: int):
        """Process a specific chunk of a batch file"""
        start_time = datetime.now()
        logger.info(f"Starting to process chunk {chunk_id} of batch: '{batch_id}'")

        # Get batch data
        try:
            batch = await self.get_batch(batch_id)
            if not batch:
                logger.error(f"Batch '{batch_id}' not found in database")
                return

            # Get chunk metadata
            chunk = await get_batch_chunk(batch_id, chunk_id)
            if not chunk:
                logger.error(
                    f"Chunk {chunk_id} of batch '{batch_id}' not found in database"
                )
                return

            logger.info(
                f"Found chunk: Batch={batch_id}, Chunk={chunk_id}, Lines={chunk['line_start']}-{chunk['line_end']}"
            )
        except Exception as db_error:
            import traceback

            traceback.print_exc()
            logger.error(
                f"Database error while querying chunk {chunk_id} of batch '{batch_id}': {db_error}"
            )
            return

        try:
            # Update chunk status to processing
            await update_chunk_status(batch_id, chunk_id, "processing")

            # Get input file ID
            input_file_id = batch["input_file_id"]

            # Check if file exists in storage
            if not await self.storage.exists(input_file_id):
                raise StorageNotFoundError(f"Input file not found: {input_file_id}")

            # Bounded task pool and streaming writes
            tasks = set()
            max_in_flight = self.max_concurrency * 2

            successful_count = 0
            error_count = 0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_total_tokens = 0

            # Chunk-specific output file
            output_file_id = f"r_{batch_id}_chunk_{chunk_id}"

            def _accumulate_usage(usage_obj: Any):
                nonlocal total_prompt_tokens, total_completion_tokens, total_total_tokens
                if not usage_obj:
                    return
                if isinstance(usage_obj, dict):
                    total_prompt_tokens += usage_obj.get("prompt_tokens", 0) or 0
                    total_completion_tokens = usage_obj.get("completion_tokens", 0) or 0
                    total_total_tokens += usage_obj.get("total_tokens", 0) or 0
                else:
                    total_prompt_tokens += getattr(usage_obj, "prompt_tokens", 0) or 0
                    total_completion_tokens += (
                        getattr(usage_obj, "completion_tokens", 0) or 0
                    )
                    total_total_tokens += getattr(usage_obj, "total_tokens", 0) or 0

            # Stream results to storage
            result_queue = asyncio.Queue()

            async def write_results():
                """Background task to write results to storage"""

                async def result_lines():
                    while True:
                        result = await result_queue.get()
                        if result is None:  # Sentinel value
                            break
                        yield json.dumps(result, default=lambda o: o.__dict__)

                try:
                    await self.storage.write_lines(output_file_id, result_lines())
                except Exception as e:
                    logger.error(f"Failed to write results: {e}")
                    raise

            # Start writer task
            writer_task = asyncio.create_task(write_results())

            try:
                # Read specific line range from storage
                line_start = chunk["line_start"]
                line_end = chunk["line_end"]

                async for line_number, line in self.storage.read_lines_range(
                    input_file_id, line_start, line_end
                ):
                    if not line.strip():
                        continue

                    task = asyncio.create_task(
                        self.process_line_with_semaphore(line, line_number, batch_id)
                    )
                    tasks.add(task)

                    # Keep the number of in-flight tasks bounded
                    if len(tasks) >= max_in_flight:
                        done, pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED
                        )
                        for completed in done:
                            try:
                                result = completed.result()
                                _accumulate_usage(result.get("usage"))
                                successful_count += 1
                            except Exception as e:
                                result = {
                                    "id": f"batch_req_{uuid.uuid4().hex}",
                                    "custom_id": "unknown",
                                    "response": None,
                                    "error": {
                                        "code": "executor_error",
                                        "message": str(e),
                                    },
                                }
                                error_count += 1

                            await result_queue.put(result)
                        tasks = pending

                # Drain remaining tasks
                while tasks:
                    done, tasks = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for completed in done:
                        try:
                            result = completed.result()
                            _accumulate_usage(result.get("usage"))
                            successful_count += 1
                        except Exception as e:
                            result = {
                                "id": f"batch_req_{uuid.uuid4().hex}",
                                "custom_id": "unknown",
                                "response": None,
                                "error": {"code": "executor_error", "message": str(e)},
                            }
                            error_count += 1

                        await result_queue.put(result)

                # Signal writer to finish
                await result_queue.put(None)
                await writer_task

            except Exception as e:
                # Cancel writer if processing fails
                writer_task.cancel()
                raise

            # Update chunk completion status
            await update_chunk_completion(
                batch_id,
                chunk_id,
                successful_count,
                error_count,
                output_file_id,
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Chunk {chunk_id} of batch {batch_id} completed: "
                f"{successful_count} successful, {error_count} errors in {duration:.2f}s"
            )

            # Check if all chunks are completed and trigger merge
            if await all_chunks_completed(batch_id):
                logger.info(
                    f"All chunks completed for batch {batch_id}, triggering merge"
                )
                # Queue merge job
                merge_queue_key = "merge_queue"
                await self.redis_client.rpush(merge_queue_key, batch_id)

        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id} of batch {batch_id}: {e}")
            await update_chunk_status(batch_id, chunk_id, "failed")

    async def _process_whole_file(self, batch_id: str):
        """Process entire file for batch (backward compatible, non-chunked)"""
        start_time = datetime.now()
        logger.info(f"Starting to process batch: '{batch_id}'")

        # Get batch data
        try:
            batch = await self.get_batch(batch_id)
            if not batch:
                logger.error(f"Batch '{batch_id}' not found in database")
                return

            logger.info(
                f"Found batch: ID={batch['id']}, Status={batch['status']}, File={batch['input_file_id']}"
            )
        except Exception as db_error:
            import traceback

            traceback.print_exc()
            logger.error(
                f"Database error while querying batch '{batch_id}': {db_error}"
            )
            return

        try:
            # Update job status to processing
            await self.update_job_status(batch_id, "processing")

            # Get input file ID
            input_file_id = batch["input_file_id"]

            # Check if file exists in storage
            if not await self.storage.exists(input_file_id):
                raise StorageNotFoundError(f"Input file not found: {input_file_id}")

            # Bounded task pool and streaming writes
            tasks = set()
            line_number = 0
            max_in_flight = self.max_concurrency * 2

            successful_count = 0
            error_count = 0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_total_tokens = 0

            output_file_id = f"r_{batch_id}"

            def _accumulate_usage(usage_obj: Any):
                nonlocal total_prompt_tokens, total_completion_tokens, total_total_tokens
                if not usage_obj:
                    return
                if isinstance(usage_obj, dict):
                    total_prompt_tokens += usage_obj.get("prompt_tokens", 0) or 0
                    total_completion_tokens += (
                        usage_obj.get("completion_tokens", 0) or 0
                    )
                    total_total_tokens += usage_obj.get("total_tokens", 0) or 0
                else:
                    total_prompt_tokens += getattr(usage_obj, "prompt_tokens", 0) or 0
                    total_completion_tokens += (
                        getattr(usage_obj, "completion_tokens", 0) or 0
                    )
                    total_total_tokens += getattr(usage_obj, "total_tokens", 0) or 0

            # Stream results to storage
            result_queue = asyncio.Queue()

            async def write_results():
                """Background task to write results to storage"""

                async def result_lines():
                    while True:
                        result = await result_queue.get()
                        if result is None:  # Sentinel value
                            break
                        yield json.dumps(result, default=lambda o: o.__dict__)

                try:
                    await self.storage.write_lines(output_file_id, result_lines())
                except Exception as e:
                    logger.error(f"Failed to write results: {e}")
                    raise

            # Start writer task
            writer_task = asyncio.create_task(write_results())

            try:
                # Read and process input file line by line from storage
                async for line in self.storage.read_lines(input_file_id):
                    if not line.strip():
                        continue

                    task = asyncio.create_task(
                        self.process_line_with_semaphore(line, line_number, batch_id)
                    )
                    tasks.add(task)
                    line_number += 1

                    # Keep the number of in-flight tasks bounded
                    if len(tasks) >= max_in_flight:
                        done, pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED
                        )
                        for completed in done:
                            try:
                                result = completed.result()
                                _accumulate_usage(result.get("usage"))
                                successful_count += 1
                            except Exception as e:
                                result = {
                                    "id": f"batch_req_{uuid.uuid4().hex}",
                                    "custom_id": "unknown",
                                    "response": None,
                                    "error": {
                                        "code": "executor_error",
                                        "message": str(e),
                                    },
                                }
                                error_count += 1

                            await result_queue.put(result)
                        tasks = pending

                # Drain remaining tasks
                while tasks:
                    done, tasks = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for completed in done:
                        try:
                            result = completed.result()
                            _accumulate_usage(result.get("usage"))
                            successful_count += 1
                        except Exception as e:
                            result = {
                                "id": f"batch_req_{uuid.uuid4().hex}",
                                "custom_id": "unknown",
                                "response": None,
                                "error": {"code": "executor_error", "message": str(e)},
                            }
                            error_count += 1

                        await result_queue.put(result)

                # Signal writer to finish
                await result_queue.put(None)
                await writer_task

            except Exception as e:
                # Cancel writer if processing fails
                writer_task.cancel()
                raise

            if (successful_count + error_count) == 0:
                raise Exception("No valid request lines found in input file")

            # Update batch completion status
            await self.update_batch_completion(
                batch_id,
                output_file_id,
                successful_count,
                error_count,
                total_prompt_tokens,
                total_completion_tokens,
                total_total_tokens,
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Job {batch_id} completed: {successful_count} successful, {error_count} errors in {duration:.2f}s"
            )

        except Exception as e:
            logger.error(f"Error processing file {batch_id}: {e}")
            await self.update_job_status(batch_id, "failed")

    async def process_line_with_semaphore(
        self, line: str, line_number: int, job_id: str
    ):
        """Process single line with concurrency control"""
        async with self.semaphore:
            return await self.process_line(line, line_number, job_id)

    async def process_line(self, line: str, line_number: int, job_id: str):
        """Process individual line"""
        try:
            # Parse the request line (follows OpenAI batch format)
            request_data = json.loads(line)

            # Make the litellm call
            response = await self.make_http_call(request_data)

            # Format result to match OpenAI batch format
            result = {
                "id": f"batch_req_{uuid.uuid4().hex}",
                "custom_id": request_data.get("custom_id", f"req_{line_number}"),
                "response": response,
                "error": None,
                "usage": response.get("usage"),  # Extract usage for aggregation
            }

            return result

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON at line {line_number}: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)

        except Exception as e:
            error_msg = f"Error processing line {line_number}: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def make_http_call(
        self, request_data: dict, retries: int = 3
    ) -> Dict[str, Any]:
        """Make async litellm completion call with retry logic"""
        for attempt in range(retries):
            try:
                # Extract data from request_data.body (matches OpenAI batch format)
                body = request_data["body"]
                model = body.get("model")
                messages = body.get("messages")

                # Override model name if set
                if self.model_name:
                    model = self.model_name

                # Log the API call details (only on first attempt)
                if attempt == 0:
                    logger.debug(
                        f"Making litellm call: model={model}, "
                        f"api_base={self.config.api_base}, "
                        f"messages_count={len(messages) if messages else 0}"
                    )

                # Use async litellm for completion
                # Note: We rely on OPENAI_API_BASE and OPENAI_API_KEY environment variables
                # (set in __init__) rather than passing them explicitly to avoid litellm routing issues
                if len(body) == 2:
                    response = await litellm.acompletion(
                        model=model,
                        messages=messages,
                        base_url=self.config.api_base,
                        api_key=self.config.api_key,
                    )
                else:
                    # Pass extra kwargs from the request body
                    extra_kwargs = {
                        k: v for k, v in body.items() if k not in ("model", "messages")
                    }
                    response = await litellm.acompletion(
                        model=model, messages=messages, **extra_kwargs
                    )

                # Convert response to dict format
                result = {
                    "status_code": 200,
                    "request_id": f"req_{uuid.uuid4().hex}",
                    "body": (
                        response.model_dump()
                        if hasattr(response, "model_dump")
                        else dict(response)
                    ),
                    "usage": getattr(response, "usage", None),
                }

                return result

            except Exception as e:
                # Log detailed error information
                logger.warning(
                    f"Attempt {attempt + 1}/{retries} failed: {type(e).__name__}: {str(e)}"
                )

                if attempt == retries - 1:
                    # Final attempt failed, log full details
                    logger.error(
                        f"All {retries} attempts failed. "
                        f"API Base: {self.config.api_base}, "
                        f"Model: {model}, "
                        f"Error: {type(e).__name__}: {str(e)}"
                    )
                    raise

                # Exponential backoff
                wait_time = 2**attempt
                await asyncio.sleep(wait_time)

        raise Exception("Max retries exceeded")


class WorkerNode:
    """
    Worker node that processes jobs from Redis queue

    Can be scaled horizontally by running multiple instances.
    """

    def __init__(self, worker_id: int, config: BESHConfig):
        """
        Initialize worker node

        Args:
            worker_id: Unique worker identifier
            config: BESH configuration
        """
        self.worker_id = worker_id
        self.config = config
        self.processor = FileProcessor(config)
        self.should_exit = False

    def _handle_shutdown_signal(self, signum, frame):
        """Handle shutdown signals gracefully"""
        sig_name = signal.Signals(signum).name
        logger.info(
            f"Worker {self.worker_id} received signal {sig_name}, shutting down..."
        )
        self.should_exit = True

    async def start(self):
        """Start worker node (blocking)"""
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

        # Initialize processor
        await self.processor.initialize()

        logger.info(f"Worker {self.worker_id} started and waiting for jobs...")
        await asyncio.sleep(self.worker_id * 1.0)  # Stagger startup

        while not self.should_exit:
            try:
                # Atomically move from queue to processing list to avoid job loss
                job_id = await self.processor.redis_client.brpoplpush(
                    "batch_queue", "batch_processing", timeout=1
                )

                if job_id:
                    logger.info(f"Worker {self.worker_id} received job: {job_id}")
                    try:
                        await self.processor.process_file_stream(job_id)
                        # Ack on success: remove one occurrence from processing list
                        await self.processor.redis_client.lrem(
                            "batch_processing", 1, job_id
                        )
                    except Exception as e:
                        # Likely transient (e.g., API overload). Sleep briefly and requeue
                        logger.error(
                            f"Worker {self.worker_id} failed processing job {job_id}: {e}"
                        )
                        await asyncio.sleep(1.0)
                        try:
                            # Remove from processing and push back to main queue
                            await self.processor.redis_client.lrem(
                                "batch_processing", 1, job_id
                            )
                            await self.processor.redis_client.rpush(
                                "batch_queue", job_id
                            )
                            logger.info(
                                f"Worker {self.worker_id} requeued job: {job_id}"
                            )
                        except Exception as requeue_error:
                            logger.error(
                                f"Worker {self.worker_id} failed to requeue job {job_id}: {requeue_error}"
                            )
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.1)


async def main():
    """Initialize processor and start workers concurrently"""
    # Load config from environment
    from besh.config import BESHConfig

    config = BESHConfig.from_env()
    worker_count = int(os.getenv("WORKER_COUNT", "2"))

    # Start multiple worker nodes
    await asyncio.gather(*[WorkerNode(i, config).start() for i in range(worker_count)])


if __name__ == "__main__":
    asyncio.run(main())
