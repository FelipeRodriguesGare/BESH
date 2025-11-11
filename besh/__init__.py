"""
BESH - Batch Endpoint Service Handler

A production-ready batch processing system for large language models
with support for local and S3 storage backends.
"""

__version__ = "1.0.0"
__author__ = "Floris Fok"
__email__ = "floris.fok@prosus.com"

# Public API exports
from besh.config import BESHConfig

__all__ = ["BESHConfig", "__version__"]
