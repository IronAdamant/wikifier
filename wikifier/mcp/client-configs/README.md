# Client Configuration Examples

This folder contains example configuration snippets for connecting the Wikifier MCP server to various AI coding tools.

## Claude Desktop

Add the contents of `claude-desktop.json` (or the snippet below) to your Claude Desktop configuration file.

**Location (typical):**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Example:**

```json
{
  "mcpServers": {
    "wikifier": {
      "command": "wikifier-mcp",
      "args": []
    }
  }
}
```

After adding the config, restart Claude Desktop. Wikifier tools and resources should then appear in the MCP tools list.

## Other Clients

Most modern MCP-compatible clients (Cline, Cursor, Roo Code, Windsurf, etc.) support the stdio transport.

General pattern:

- **Command**: `wikifier-mcp`
- **Arguments**: (none)

If `wikifier-mcp` is not in your PATH, use the full path or run it via Python:

```json
{
  "mcpServers": {
    "wikifier": {
      "command": "python",
      "args": ["-m", "wikifier.mcp.server"]
    }
  }
}
```

## Tips (M2-Rem-06 Packaging Clarity)

- After `pip install wikifier[mcp]`, the `wikifier-mcp` command is globally available. Use `WIKIFIER_PROJECT_ROOT` or the `project_root` parameter when the target is an external codebase.
- Always run `check_changes` (or the MCP equivalent) early in a new agent session.
- The MCP server works alongside the legacy `skills/run.md` contract.
- For best results on external projects of any size, combine the MCP server with the prescriptive scaling patterns and root-targeting rules in the main README.md.
- Use `wikifier init --target /path/to/repo` to bootstrap any new project after installation.