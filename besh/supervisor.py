"""
Process supervisor for BESH

Manages multiple API, worker, and merger processes with monitoring and graceful shutdown.
Similar to uvicorn's multiprocessing approach.
"""

import multiprocessing
import signal
import time
import sys
import os
from typing import List, Optional
import logging

from besh.config import BESHConfig
from besh.constants import SHUTDOWN_TIMEOUT

logger = logging.getLogger(__name__)


def _run_batch_worker(worker_id: int, config_dict: dict):
    """
    Run batch worker in a subprocess (standalone function for pickling)

    Args:
        worker_id: Worker process ID for logging
        config_dict: Configuration dictionary
    """
    try:
        import asyncio
        from besh.processing.worker import WorkerNode
        from besh.config import BESHConfig
        from dotenv import load_dotenv

        # Load .env in child process
        load_dotenv(override=False)

        # Reconstruct config from dict
        config = BESHConfig(**config_dict)

        logger.info(f"Batch worker {worker_id} starting")

        # Create and run worker
        worker = WorkerNode(worker_id=worker_id, config=config)

        asyncio.run(worker.start())

    except Exception as e:
        logger.error(f"Batch worker {worker_id} failed: {e}")
        sys.exit(1)


def _run_merger_worker(config_dict: dict):
    """
    Run merger worker in a subprocess (standalone function for pickling)

    Args:
        config_dict: Configuration dictionary
    """
    try:
        import asyncio
        from besh.processing.merger import MergerWorker
        from besh.config import BESHConfig
        from dotenv import load_dotenv

        # Load .env in child process
        load_dotenv(override=False)

        # Reconstruct config from dict
        config = BESHConfig(**config_dict)

        logger.info("Merger worker starting")

        # Create and run merger worker
        merger = MergerWorker(config)

        asyncio.run(merger.start())

    except Exception as e:
        logger.error(f"Merger worker failed: {e}")
        sys.exit(1)


class ProcessSupervisor:
    """
    Supervisor for managing multiple API and worker processes

    Features:
    - Spawns configurable number of API and worker processes
    - Monitors process health and auto-restarts failed processes
    - Graceful shutdown with configurable timeout
    - Signal handling (SIGTERM, SIGINT)
    """

    def __init__(
        self, config: BESHConfig, api_only: bool = False, workers_only: bool = False
    ):
        """
        Initialize process supervisor

        Args:
            config: BESH configuration
            api_only: Only run API processes (no batch workers)
            workers_only: Only run worker processes (no API)
        """
        # Keep config for easy access (not passed to subprocesses)
        self.config = config
        # Store config as dict to avoid pickling issues with Pydantic models
        self.config_dict = config.model_dump()
        self.api_only = api_only
        self.workers_only = workers_only
        self.processes: List[multiprocessing.Process] = []
        self.should_exit = False

        # Determine what to run
        self.num_api_workers = 0 if workers_only else config.api_workers
        self.num_batch_workers = 0 if api_only else config.batch_workers
        # Always run 1 merger worker when batch workers are enabled
        self.num_merger_workers = 1 if (self.num_batch_workers > 0) else 0

        logger.info(
            f"Initializing ProcessSupervisor: "
            f"api_workers={self.num_api_workers}, "
            f"batch_workers={self.num_batch_workers}, "
            f"merger_workers={self.num_merger_workers}"
        )

    def spawn_processes(self):
        """Spawn all configured API and worker processes"""
        # Set environment variables for child processes
        # This ensures workers can access config even if .env isn't loaded in child
        if self.config_dict.get("database_url"):
            os.environ["BESH_DATABASE_URL"] = self.config_dict["database_url"]
        if self.config_dict.get("redis_url"):
            os.environ["BESH_REDIS_URL"] = self.config_dict["redis_url"]
        if self.config_dict.get("api_base"):
            os.environ["BESH_API_BASE"] = self.config_dict["api_base"]
        if self.config_dict.get("api_key"):
            os.environ["BESH_API_KEY"] = self.config_dict["api_key"]
        if self.config_dict.get("upload_folder"):
            os.environ["BESH_UPLOAD_FOLDER"] = self.config_dict["upload_folder"]
        if self.config_dict.get("storage_backend"):
            os.environ["BESH_STORAGE_BACKEND"] = self.config_dict["storage_backend"]

        # Note: API workers are NOT spawned here
        # They run in the main process using Uvicorn's built-in multiprocessing

        # Spawn batch workers (separate processes)
        for i in range(self.num_batch_workers):
            process = multiprocessing.Process(
                target=_run_batch_worker,
                args=(i, self.config_dict),
                name=f"besh-worker-{i}",
                daemon=False,
            )
            process.start()
            self.processes.append(process)
            logger.info(f"Started batch worker {i} (PID: {process.pid})")

        # Spawn merger workers (separate processes)
        for i in range(self.num_merger_workers):
            process = multiprocessing.Process(
                target=_run_merger_worker,
                args=(self.config_dict,),
                name=f"besh-merger-{i}",
                daemon=False,
            )
            process.start()
            self.processes.append(process)
            logger.info(f"Started merger worker {i} (PID: {process.pid})")

        logger.info(f"Spawned {len(self.processes)} total processes")

    def handle_signals(self):
        """Set up signal handlers for graceful shutdown"""

        def signal_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"Received signal {sig_name}, initiating graceful shutdown...")
            self.should_exit = True

        # Handle SIGTERM and SIGINT
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Ignore SIGCHLD (child process exit) - we monitor processes manually
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def monitor_processes(self):
        """
        Monitor process health and restart failed processes

        Runs in a loop checking if processes are alive and restarts them if needed.
        """
        logger.info("Starting process monitoring...")

        while not self.should_exit:
            for i, process in enumerate(self.processes):
                if not process.is_alive():
                    exit_code = process.exitcode

                    if self.should_exit:
                        # Expected shutdown
                        logger.debug(
                            f"Process {process.name} exited with code {exit_code}"
                        )
                    else:
                        # Unexpected exit - restart
                        logger.warning(
                            f"Process {process.name} (PID: {process.pid}) died "
                            f"with exit code {exit_code}. Restarting..."
                        )

                        # Determine process type and restart
                        if process.name.startswith("besh-merger-"):
                            new_process = multiprocessing.Process(
                                target=_run_merger_worker,
                                args=(self.config_dict,),
                                name=process.name,
                                daemon=False,
                            )
                        elif process.name.startswith("besh-worker-"):
                            worker_id = int(process.name.split("-")[-1])
                            new_process = multiprocessing.Process(
                                target=_run_batch_worker,
                                args=(worker_id, self.config_dict),
                                name=f"besh-worker-{worker_id}",
                                daemon=False,
                            )
                        else:
                            logger.error(f"Unknown process type: {process.name}")
                            continue

                        new_process.start()
                        self.processes[i] = new_process
                        logger.info(
                            f"Restarted {new_process.name} (new PID: {new_process.pid})"
                        )

            # Check every second
            time.sleep(1)

    def shutdown(self):
        """
        Gracefully shutdown all processes

        Sends SIGTERM to all processes and waits for them to exit.
        If they don't exit within SHUTDOWN_TIMEOUT, sends SIGKILL.
        """
        if not self.processes:
            return

        logger.info(f"Shutting down {len(self.processes)} processes...")

        # Send SIGTERM to all processes
        for process in self.processes:
            if process.is_alive():
                logger.debug(f"Sending SIGTERM to {process.name} (PID: {process.pid})")
                try:
                    process.terminate()
                except Exception as e:
                    logger.warning(f"Failed to terminate {process.name}: {e}")

        # Wait for processes to exit
        shutdown_start = time.time()
        for process in self.processes:
            remaining_time = SHUTDOWN_TIMEOUT - (time.time() - shutdown_start)

            if remaining_time <= 0:
                break

            try:
                process.join(timeout=remaining_time)
            except Exception as e:
                logger.warning(f"Error waiting for {process.name}: {e}")

        # Force kill any remaining processes
        for process in self.processes:
            if process.is_alive():
                logger.warning(
                    f"Process {process.name} (PID: {process.pid}) didn't exit gracefully, "
                    "sending SIGKILL"
                )
                try:
                    process.kill()
                    process.join(timeout=1)
                except Exception as e:
                    logger.error(f"Failed to kill {process.name}: {e}")

        logger.info("All processes shut down")

    def start(self):
        """
        Main entry point - start supervisor and monitor processes

        This method blocks until shutdown is requested.
        """
        if self.num_api_workers == 0 and self.num_batch_workers == 0:
            logger.error(
                "No workers configured! Set --api-workers or --batch-workers > 0"
            )
            sys.exit(1)

        try:
            # Set up signal handlers
            self.handle_signals()

            # Spawn batch/merger workers as subprocesses
            self.spawn_processes()

            logger.info("BESH supervisor started successfully")
            logger.info(f"Running with PID: {os.getpid()}")

            # If API workers requested, run Uvicorn in main process (blocks)
            # Uvicorn handles its own multiprocessing for API workers
            if self.num_api_workers > 0:
                import uvicorn

                logger.info(
                    f"Starting API server on {self.config.host}:{self.config.port} "
                    f"with {self.num_api_workers} Uvicorn workers"
                )

                # Run Uvicorn with its internal worker management
                # This blocks until shutdown
                uvicorn.run(
                    "besh.api.app:create_app",
                    host=self.config.host,
                    port=self.config.port,
                    workers=self.num_api_workers,
                    reload=self.config.reload,
                    log_level=self.config.log_level.lower(),
                    factory=True,
                )
            else:
                # No API workers, just monitor batch/merger workers
                self.monitor_processes()

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.should_exit = True
        except Exception as e:
            logger.error(f"Supervisor error: {e}", exc_info=True)
            self.should_exit = True
        finally:
            # Clean up
            self.shutdown()
            logger.info("BESH supervisor stopped")


def run_api_directly(config: BESHConfig):
    """
    Run API server directly without multiprocessing

    Useful for development and debugging.

    Args:
        config: BESH configuration
    """
    import uvicorn
    from besh.api.app import create_app

    app = create_app(config)

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        reload=config.reload,
        log_level=config.log_level.lower(),
    )


def run_worker_directly(config: BESHConfig, worker_id: int = 0):
    """
    Run batch worker directly without multiprocessing

    Useful for development and debugging.

    Args:
        config: BESH configuration
        worker_id: Worker ID
    """
    import asyncio
    from besh.processing.worker import WorkerNode

    worker = WorkerNode(worker_id=worker_id, config=config)
    asyncio.run(worker.start())
