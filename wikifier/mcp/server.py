"""
Wikifier MCP server — agent-to-agent wiki (optional `pip install wikifier[mcp]`).

Live implementation is server_impl.py (complete tool set + resources + prompts).
This module is the installed entry point: `wikifier-mcp` / `python -m wikifier.mcp.server`.
"""

from __future__ import annotations

from .server_impl import main, mcp

__all__ = ["mcp", "main"]


if __name__ == "__main__":
    main()
