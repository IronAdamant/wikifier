"""
Wikifier MCP Server Package

This package exposes Wikifier as a Model Context Protocol (MCP) server.

The MCP server requires the optional 'mcp' extra (pip install wikifier[mcp]).
The core wikifier package is zero-dependency and must stay importable without
it, so the server import is guarded: `wikifier.mcp.mcp` is None when the
extra is not installed.
"""

try:
    from .server import mcp
except ImportError:
    mcp = None

__all__ = ["mcp"]
