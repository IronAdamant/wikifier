# wikifier/mcp/deadline.py

Stdlib in-process wall-clock cap for MCP tools (`call_with_deadline`, `MCP_INPROCESS_DEADLINE_S` default 60s).

Lives outside `server_impl.py` so tests can force `timeout_s<=0` without importing the optional `mcp` extra. Returns `{success: False, timed_out: True}`.
