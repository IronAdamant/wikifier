# src/mcp.rs

**Role:** Stdio JSON-RPC MCP adapter over `src/api.rs`.

`tool_schema` describes one tool. `handle_message` answers one JSON-RPC request. `serve_stdio` reads messages from stdin. `tools/call` sets `isError` when the payload has `success: false`. `resources/read` serves the library, health, pending, and journal resources. `prompts/get` returns a short user message. Each call runs on a thread and stops waiting after `WIKIFIER_MCP_DEADLINE_S` seconds (default 60). A timeout payload has `timed_out` and `may_still_complete`.

A `tools/call` that leaves out a required argument other than `project_root` (or sends it empty) gets `InvalidArguments` naming the missing field, the accepted fields, and the fields received. `project_root` falls back to `WIKIFIER_PROJECT_ROOT`, then the cwd. `update_maps` omits the edge list unless `edges: true`; `edges_persisted` still gives the count. `health` takes `limit` (adds `entries_total` when it cuts) and `summary`.
