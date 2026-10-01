# wikifier/mcp/server.py

**Purpose:** installed MCP entry point (`wikifier-mcp`, `python -m wikifier.mcp.server`); re-exports `mcp` and `main` from `server_impl.py`. `import wikifier` never imports it (`wikifier.mcp` is lazy).
