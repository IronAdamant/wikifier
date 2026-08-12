"""
Wikifier MCP server — agent-to-agent wiki (optional `pip install wikifier[mcp]`).

Modularized MCP server with tools organized by domain.
"""

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as _e:
    raise ImportError(
        "The Wikifier MCP server requires the optional 'mcp' dependency. "
        "Install it with: pip install wikifier[mcp]. "
        "The core wikifier CLI and library work without it."
    ) from _e

# Create MCP server instance
mcp = FastMCP("Wikifier")

# Import tool registration functions (they will register with the mcp instance above)
from .tools import workflow, intel, status

# Register all tools
workflow.register_tools(mcp)
intel.register_tools(mcp)
status.register_tools(mcp)

# Export mcp for backward compatibility
__all__ = ['mcp']
