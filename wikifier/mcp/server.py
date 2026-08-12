"""
Wikifier MCP server — agent-to-agent wiki (optional `pip install wikifier[mcp]`).

This is the main server module that imports and registers all tools.
Tool implementations are organized in mcp/tools/ by domain.
"""

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as _e:
    raise ImportError(
        "The Wikifier MCP server requires the optional 'mcp' dependency. "
        "Install it with: pip install wikifier[mcp]. "
        "The core wikifier CLI and library work without it."
    ) from _e

# Import all tool implementations
from .tools import *

# Create MCP server instance
mcp = FastMCP("Wikifier")

# Tools are automatically registered by FastMCP via decorators in tool modules
