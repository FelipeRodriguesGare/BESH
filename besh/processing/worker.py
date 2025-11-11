"""
Batch processing worker for BESH

Processes batch jobs from Redis queue using storage abstraction.
"""

import asyncio
import json
import uuid
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

        # Configure litellm
        os.environ["OPENAI_API_BASE"] = config.api_base
        os.environ["OPENAI_API_KEY"] = config.api_key

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

    async def process_file_stream(self, batch_id: str):
        """Process file stream with high concurrency and streaming writes"""
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

                # Use async litellm for completion
                if len(body) == 2:
                    response = await litellm.acompletion(model=model, messages=messages)
                else:
                    # Pass extra kwargs
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
                if attempt == retries - 1:
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

    async def start(self):
        """Start worker node (blocking)"""
        # Initialize processor
        await self.processor.initialize()

        logger.info(f"Worker {self.worker_id} started and waiting for jobs...")
        await asyncio.sleep(self.worker_id * 1.0)  # Stagger startup

        while True:
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
