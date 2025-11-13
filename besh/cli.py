"""
Click-based CLI interface for BESH

Provides commands for running API server, workers, or both together.
"""

import click
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env file before anything else
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="1.0.0", prog_name="BESH")
def cli():
    """
    BESH - Batch Endpoint Service Handler

    Production-ready batch processing for LLMs with local or S3 storage.

    \b
    Examples:
        # Run API and workers together
        besh serve --database-url postgresql://localhost/besh

        # Run workers only
        besh worker --workers 4 --database-url postgresql://localhost/besh

        # Run API only
        besh api --database-url postgresql://localhost/besh

        # Use config file
        besh serve --config production.yaml

        # Test S3 connectivity
        besh test-storage --storage s3 --s3-bucket my-bucket
    """
    pass


@cli.command()
@click.option("--host", default="0.0.0.0", help="API server host")
@click.option("--port", default=8080, type=int, help="API server port")
@click.option(
    "--api-workers", default=2, type=int, help="Number of API worker processes"
)
@click.option(
    "--batch-workers", default=4, type=int, help="Number of batch worker processes"
)
@click.option(
    "--storage",
    "storage_backend",
    type=click.Choice(["local", "s3"]),
    default=None,
    help="Storage backend (default: from .env or 'local')",
)
@click.option(
    "--upload-folder",
    default=None,
    help="Local storage folder (default: from .env or /tmp/batch_files)",
)
@click.option("--s3-bucket", help="S3 bucket name (required if storage=s3)")
@click.option("--s3-region", default="us-east-1", help="AWS region")
@click.option("--s3-profile", help="AWS profile name for authentication")
@click.option(
    "--s3-endpoint", "s3_endpoint_url", help="Custom S3 endpoint (MinIO, LocalStack)"
)
@click.option(
    "--database-url",
    default=None,
    help="PostgreSQL connection URL (or set BESH_DATABASE_URL in .env)",
)
@click.option(
    "--redis-url", default="redis://localhost:6379", help="Redis connection URL"
)
@click.option(
    "--openai-api-base",
    default="http://localhost:8000/v1",
    help="OpenAI-compatible API endpoint",
)
@click.option("--openai-api-key", default="dummy-key", help="API key for LLM endpoint")
@click.option(
    "--max-workers", default=64, type=int, help="Concurrent tasks per batch worker"
)
@click.option(
    "--reload", is_flag=True, help="Auto-reload on code changes (development)"
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True),
    help="Load configuration from YAML file",
)
def serve(config_file, **kwargs):
    """
    Run API server and batch workers together

    This command starts both the FastAPI server and batch processing workers
    in a single process with multiprocessing for scalability.
    """
    from besh.config import BESHConfig
    from besh.supervisor import ProcessSupervisor

    try:
        # Load config
        if config_file:
            click.echo(f"Loading configuration from {config_file}")
            config = BESHConfig.from_yaml(config_file)

            # Apply CLI overrides
            for key, value in kwargs.items():
                if value is not None and hasattr(config, key):
                    setattr(config, key, value)
        else:
            # Remove None values
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            config = BESHConfig(**kwargs)

        # Set log level
        logging.getLogger().setLevel(config.log_level)

        click.echo(f"Starting BESH server:")
        click.echo(f"  API: {config.host}:{config.port} ({config.api_workers} workers)")
        click.echo(f"  Batch workers: {config.batch_workers}")
        click.echo(f"  Storage: {config.storage_backend}")
        if config.storage_backend == "s3":
            click.echo(f"  S3 bucket: {config.s3_bucket}")

        # Start supervisor
        supervisor = ProcessSupervisor(config)
        supervisor.start()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--workers", default=4, type=int, help="Number of worker processes")
@click.option(
    "--concurrency",
    "concurrent_requests_per_worker",
    default=64,
    type=int,
    help="Concurrent tasks per worker",
)
@click.option(
    "--storage",
    "storage_backend",
    type=click.Choice(["local", "s3"]),
    default=None,
    help="Storage backend (default: from .env or 'local')",
)
@click.option(
    "--upload-folder",
    default=None,
    help="Local storage folder (default: from .env or /tmp/batch_files)",
)
@click.option("--s3-bucket", help="S3 bucket name")
@click.option("--s3-region", default="us-east-1", help="AWS region")
@click.option("--s3-profile", help="AWS profile name")
@click.option("--s3-endpoint", "s3_endpoint_url", help="Custom S3 endpoint")
@click.option(
    "--database-url",
    default=None,
    help="PostgreSQL connection URL (or set BESH_DATABASE_URL in .env)",
)
@click.option(
    "--redis-url", default="redis://localhost:6379", help="Redis connection URL"
)
@click.option(
    "--openai-api-base", default="http://localhost:8000/v1", help="LLM API endpoint"
)
@click.option("--openai-api-key", default="dummy-key", help="LLM API key")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
)
@click.option("--config", "config_file", type=click.Path(exists=True))
def worker(config_file, workers, **kwargs):
    """
    Run batch workers only (no API server)

    This is useful for scaling workers separately in a distributed setup
    or when using a hybrid deployment with Docker GPUs + CLI workers.
    """
    from besh.config import BESHConfig
    from besh.supervisor import ProcessSupervisor

    try:
        # Load config
        if config_file:
            click.echo(f"Loading configuration from {config_file}")
            config = BESHConfig.from_yaml(config_file)
        else:
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            config = BESHConfig(**kwargs)

        # Override to run workers only
        config.batch_workers = workers
        config.api_workers = 0  # No API workers

        logging.getLogger().setLevel(config.log_level)

        click.echo(f"Starting BESH batch workers:")
        click.echo(f"  Workers: {config.batch_workers}")
        click.echo(
            f"  Concurrent requests per worker: {config.concurrent_requests_per_worker}"
        )
        click.echo(f"  Storage: {config.storage_backend}")

        supervisor = ProcessSupervisor(config, workers_only=True)
        supervisor.start()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--host", default="0.0.0.0", help="API server host")
@click.option("--port", default=8080, type=int, help="API server port")
@click.option("--workers", default=2, type=int, help="Number of API worker processes")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes")
@click.option(
    "--database-url",
    default=None,
    help="PostgreSQL connection URL (or set BESH_DATABASE_URL in .env)",
)
@click.option(
    "--redis-url", default="redis://localhost:6379", help="Redis connection URL"
)
@click.option(
    "--storage",
    "storage_backend",
    type=click.Choice(["local", "s3"]),
    default=None,
    help="Storage backend (default: from .env or 'local')",
)
@click.option(
    "--upload-folder",
    default=None,
    help="Local storage folder (default: from .env or /tmp/batch_files)",
)
@click.option("--s3-bucket", help="S3 bucket name")
@click.option("--s3-region", default="us-east-1")
@click.option("--s3-profile", help="AWS profile name")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
)
@click.option("--config", "config_file", type=click.Path(exists=True))
def api(config_file, workers, **kwargs):
    """
    Run API server only (no batch workers)

    This is useful for scaling the API separately or in deployments where
    workers are managed by a separate system.
    """
    from besh.config import BESHConfig
    from besh.supervisor import ProcessSupervisor

    try:
        # Load config
        if config_file:
            config = BESHConfig.from_yaml(config_file)
        else:
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            config = BESHConfig(**kwargs)

        # Override to run API only
        config.api_workers = workers
        config.batch_workers = 0  # No batch workers

        logging.getLogger().setLevel(config.log_level)

        click.echo(f"Starting BESH API server:")
        click.echo(f"  Address: {config.host}:{config.port}")
        click.echo(f"  Workers: {config.api_workers}")
        click.echo(f"  Reload: {config.reload}")

        supervisor = ProcessSupervisor(config, api_only=True)
        supervisor.start()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("test-storage")
@click.option(
    "--storage",
    "storage_backend",
    type=click.Choice(["local", "s3"]),
    required=True,
    help="Storage backend to test",
)
@click.option(
    "--upload-folder",
    default=None,
    help="Local storage folder (default: from .env or /tmp/batch_files)",
)
@click.option("--s3-bucket", help="S3 bucket name (required for S3)")
@click.option("--s3-region", default="us-east-1", help="AWS region")
@click.option("--s3-profile", help="AWS profile name")
@click.option("--s3-endpoint", "s3_endpoint_url", help="Custom S3 endpoint")
def test_storage(storage_backend, **kwargs):
    """
    Test storage backend connectivity

    This command verifies that the storage backend is properly configured
    and accessible.
    """
    import asyncio
    from besh.config import BESHConfig
    from besh.storage import get_storage
    from besh.exceptions import StorageException

    try:
        click.echo(f"Testing {storage_backend} storage backend...")

        # Create minimal config
        config_dict = {
            "storage_backend": storage_backend,
            "database_url": "postgresql://dummy",  # Required but not used
            **{k: v for k, v in kwargs.items() if v is not None},
        }

        config = BESHConfig(**config_dict)

        async def test():
            storage = get_storage(config)

            # Test 1: List files
            click.echo("  Testing list files...")
            files = await storage.list_files()
            click.echo(f"    ✓ Found {len(files)} files")

            # Test 2: Write test file
            click.echo("  Testing write...")
            test_file_id = "test_besh_connectivity"

            async def test_lines():
                yield "test line 1"
                yield "test line 2"

            await storage.write_lines(test_file_id, test_lines())
            click.echo(f"    ✓ Wrote test file")

            # Test 3: Read test file
            click.echo("  Testing read...")
            lines = []
            async for line in storage.read_lines(test_file_id):
                lines.append(line)
            click.echo(f"    ✓ Read {len(lines)} lines")

            # Test 4: Get metadata
            click.echo("  Testing metadata...")
            metadata = await storage.get_metadata(test_file_id)
            click.echo(f"    ✓ File size: {metadata['size']} bytes")

            # Test 5: Delete test file
            click.echo("  Testing delete...")
            deleted = await storage.delete(test_file_id)
            if deleted:
                click.echo("    ✓ Deleted test file")

            click.echo()
            click.secho("✓ All storage tests passed!", fg="green", bold=True)

        asyncio.run(test())

    except StorageException as e:
        click.secho(f"✗ Storage test failed: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="besh-config.yaml",
    help="Output configuration file",
)
def init_config(output):
    """
    Generate a sample configuration file

    Creates a YAML configuration file with all available options and their
    default values. You can edit this file and use it with --config.
    """
    from besh.config import BESHConfig

    try:
        # Create default config
        config = BESHConfig(
            database_url="postgresql://user:password@localhost:5432/besh"
        )

        # Export to YAML
        config.to_yaml(output)

        click.secho(f"✓ Created configuration file: {output}", fg="green")
        click.echo()
        click.echo("Edit the file and run:")
        click.echo(f"  besh serve --config {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def version():
    """Show BESH version and system information"""
    import platform
    from besh import __version__

    click.echo(f"BESH version: {__version__}")
    click.echo(f"Python version: {platform.python_version()}")
    click.echo(f"Platform: {platform.platform()}")

    # Check optional dependencies
    click.echo()
    click.echo("Optional dependencies:")

    try:
        import aioboto3

        click.echo("  ✓ aioboto3 (S3 support)")
    except ImportError:
        click.echo("  ✗ aioboto3 (install with: pip install besh[s3])")


@cli.command()
@click.option(
    "--database-url",
    default=None,
    help="Database connection URL (e.g., postgresql://user:pass@host/db)",
)
def migrate(database_url: str):
    """
    Run database migrations manually

    This is useful when you want to run migrations separately from the application,
    for example in a dedicated migration job or during deployment.

    Example:
        besh migrate
        besh migrate --database-url postgresql://user:pass@localhost/besh
    """
    import asyncio
    from besh.api.models.batch import run_migrations, init_db_pool

    async def run_migrations_standalone():
        """Run migrations as standalone command"""
        click.echo("🔄 Running database migrations...")

        try:
            # Initialize database pool (without auto-migrate to avoid recursion)
            await init_db_pool(
                database_url=database_url,
                auto_migrate=False,  # Explicitly disable auto-migrate
            )

            # Run migrations
            await run_migrations()

            click.echo("✅ Database migrations completed successfully!")

        except Exception as e:
            click.echo(f"❌ Migration failed: {e}", err=True)
            import traceback

            traceback.print_exc()
            raise click.Abort()

    asyncio.run(run_migrations_standalone())


if __name__ == "__main__":
    cli()
