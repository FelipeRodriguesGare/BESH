# Installing BESH with UV

BESH uses [UV](https://github.com/astral-sh/uv), a fast Python package and project manager from Astral (creators of Ruff).

## Why UV?

- **10-100x faster** than pip for package installation
- **Better dependency resolution** - more reliable environment setup
- **Built-in virtual environment management**
- **Lockfile support** for reproducible builds
- **Drop-in replacement** for pip, pip-tools, and virtualenv

## Installing UV

### Quick Install (Recommended)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.sh | iex"

# Via pip (if you already have Python)
pip install uv
```

### Verify Installation

```bash
uv --version
```

## Installing BESH

### Option 1: Development Installation (Editable)

```bash
# Clone the repository
cd /path/to/BESH

# Create virtual environment and install (UV handles everything)
uv sync

# Or install in editable mode with S3 support
uv pip install -e ".[s3]"
```

### Option 2: Direct Installation from Source

```bash
cd /path/to/BESH
uv pip install .

# With S3 support
uv pip install ".[s3]"

# With all optional dependencies
uv pip install ".[all]"
```

### Option 3: Using UV's Project Management

```bash
cd /path/to/BESH

# Create/sync virtual environment with all dependencies
uv sync

# Install with S3 support
uv sync --extra s3

# Run without activating virtualenv
uv run besh serve --database-url postgresql://localhost/besh
```

## Using BESH with UV

### Running Commands

```bash
# Activate the virtual environment (traditional way)
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows
besh serve

# Or run directly with UV (no activation needed)
uv run besh serve --database-url postgresql://localhost/besh

# Run with S3 storage
uv run besh serve \
  --storage s3 \
  --s3-bucket my-bucket \
  --database-url postgresql://localhost/besh
```

### Development Workflow

```bash
# Install development dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type check
uv run mypy besh/
```

## UV Project Commands

### Creating Virtual Environment

```bash
# UV automatically creates .venv/ on first sync
uv sync

# Use specific Python version
uv sync --python 3.11
```

### Managing Dependencies

```bash
# Add a new dependency
uv add fastapi

# Add development dependency
uv add --dev pytest

# Update all dependencies
uv sync --upgrade

# Show installed packages
uv pip list
```

### Lockfiles

```bash
# Generate lockfile (happens automatically with uv sync)
uv lock

# Install from lockfile (reproducible)
uv sync --locked
```

## Docker with UV

The new `Dockerfile.besh` uses UV for faster Docker builds:

```dockerfile
# Install UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install package (much faster than pip)
RUN uv pip install --system --no-cache .
```

### Building Docker Image

```bash
# Build with UV
docker build -f Dockerfile.besh -t besh:latest .

# Run
docker run -p 8080:8080 besh:latest
```

## Performance Comparison

### Installation Speed

```bash
# Traditional pip (slow)
time pip install -e ".[s3]"
# Real: ~45 seconds

# UV (fast)
time uv pip install -e ".[s3]"
# Real: ~5 seconds
```

### Docker Build Speed

```bash
# With pip
time docker build -f Dockerfile -t besh:pip .
# Real: ~3 minutes

# With UV
time docker build -f Dockerfile.besh -t besh:uv .
# Real: ~45 seconds
```

## Common UV Commands

### Package Management

```bash
# Install package
uv pip install besh

# Install with extras
uv pip install "besh[s3]"

# Install from git
uv pip install git+https://github.com/user/besh.git

# Uninstall
uv pip uninstall besh
```

### Virtual Environments

```bash
# Create venv
uv venv

# Create with specific Python
uv venv --python 3.11

# Activate (same as regular venv)
source .venv/bin/activate
```

### Running Scripts

```bash
# Run without activation
uv run python script.py

# Run with specific Python
uv run --python 3.11 python script.py

# Run entry point
uv run besh serve
```

## Migrating from Pip

UV is a drop-in replacement for most pip commands:

```bash
# Pip → UV
pip install package        → uv pip install package
pip install -e .          → uv pip install -e .
pip install -r req.txt    → uv pip install -r req.txt
pip list                  → uv pip list
pip freeze                → uv pip freeze
pip uninstall package     → uv pip uninstall package

# New UV-specific
uv sync                   # Install from pyproject.toml
uv lock                   # Generate lockfile
uv add package            # Add to pyproject.toml
```

## CI/CD with UV

### GitHub Actions

```yaml
name: Test with UV

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install UV
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install dependencies
        run: uv sync --all-extras
      
      - name: Run tests
        run: uv run pytest
```

### GitLab CI

```yaml
test:
  image: python:3.11-slim
  before_script:
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="/root/.cargo/bin:$PATH"
  script:
    - uv sync --all-extras
    - uv run pytest
```

## Troubleshooting

### UV Not Found After Installation

```bash
# Add to PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Or restart your shell
exec $SHELL
```

### Python Version Issues

```bash
# Use specific Python version
uv venv --python 3.11
uv sync --python 3.11
```

### System Python vs Virtual Environment

```bash
# Install to system Python (not recommended)
uv pip install --system besh

# Install to virtual environment (recommended)
uv venv
uv pip install besh
```

### Docker Build Issues

```bash
# Ensure UV is in PATH
ENV PATH="/root/.cargo/bin:$PATH"

# Use system Python flag
ENV UV_SYSTEM_PYTHON=1
```

## Benefits for BESH Users

1. **Faster Installation**: 10x faster than pip
2. **Reliable Environments**: Better dependency resolution
3. **Reproducible Builds**: Lockfile support
4. **Easier Development**: Single tool for all Python package needs
5. **Better Docker Builds**: Significantly faster image creation

## Learn More

- [UV Documentation](https://github.com/astral-sh/uv)
- [UV Installation Guide](https://github.com/astral-sh/uv#installation)
- [Astral Blog](https://astral.sh/blog)

## Quick Reference

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install BESH
cd /path/to/BESH
uv sync --extra s3

# Run BESH
uv run besh serve --database-url postgresql://localhost/besh

# Development
uv run pytest              # Run tests
uv run ruff format .       # Format code
uv run ruff check .        # Lint code
```

