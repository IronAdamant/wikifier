"""
Wikifier Python Package

Provides the core Python components for Wikifier, including:
- Import parsers (Python + JavaScript/TypeScript)
- MCP Server
- Health Matrix (scalable implementation)
"""

from . import parsers
from . import mcp
from . import health
from . import locking
from . import import_cache

__version__ = "0.3.2"
