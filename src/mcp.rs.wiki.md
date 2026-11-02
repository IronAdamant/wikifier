# src/mcp.rs

**Role:** Stdio JSON-RPC MCP adapter over `src/api.rs`.

`tools/call` sets `isError` when the payload has `success: false`. `resources/read` serves the library, health, pending, and journal resources. `prompts/get` returns a short user message. Each call runs on a thread and stops waiting after `WIKIFIER_MCP_DEADLINE_S` seconds (default 60). A timeout payload has `timed_out` and `may_still_complete`.
