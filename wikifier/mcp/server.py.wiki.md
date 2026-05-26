# wikifier/mcp/server.py

The core Model Context Protocol (MCP) server implementation for Wikifier.

## Purpose
Provides a rich, structured interface for AI agents (especially in Grok Build) to interact with Wikifier’s capabilities programmatically.

## Key Features Exposed via MCP
- Project status and health overview (`get_project_status`)
- Smart next-action suggestions (`suggest_next_actions`)
- Forward and reverse dependency queries (`get_dependencies`, `get_dependents`)
- Per-file wiki lookup (`get_file_wiki`)
- Full access to core commands: `check_changes`, `record_change`, `mark_green`, `update_maps`, etc.
- Built-in prompts for common agent workflows (refactoring planning, health audits, architectural analysis)

## Architecture
- Built using `FastMCP` from the official MCP Python SDK.
- All tools are defined with clear Pydantic models for structured output where possible.
- Designed to be conservative and transparent (agents can see resolution quality and limitations).

## Location
`wikifier/mcp/server.py`

## Related Files
- `wikifier/mcp/README.md` — High-level usage and tool list
- `.mcp.json` — Project-level registration for Grok Build
- `skills/run.md` — Legacy shell-based agent contract

## Status (M2 Final Robustness)
All core tools now have consistent `project_root` support and many support `format=json` for structured agent consumption.

Lower-level tools (`record_change`, `mark_green`, `record_deletion`, `prepare_edit`, `check_changes`, `validate`, `journal`, `issues`) return structured dicts with `success`, `project_root`, and error information.

High-value agent tools (`get_project_status`, `suggest_next_actions`, `get_files_needing_attention`, `get_incremental_status`, dependency tools) are mature and reliable.

Error handling is now graceful (structured errors instead of raw exceptions where possible).

This pass completed the final robustness items before deep M2-Rem-08 dogfooding.
