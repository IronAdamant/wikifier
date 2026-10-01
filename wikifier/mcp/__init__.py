"""
Wikifier MCP server package (optional extra: ``pip install wikifier[mcp]``).

Importing this package is cheap and never requires the extra; the FastMCP
server is only constructed when ``wikifier.mcp.server`` (or the ``mcp``
attribute below) is first accessed.
"""

from typing import Any

__all__ = ["mcp"]


def __getattr__(name: str) -> Any:
    if name == "mcp":
        try:
            from .server import mcp as server
        except ImportError:
            return None
        return server
    raise AttributeError(name)
