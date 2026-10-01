# wikifier/mcp/status_ops.py

**Purpose:** `get_project_status` / `get_files_needing_attention` work under the in-process deadline. Dependency intel comes from persisted meta keys (ACS, cycle analyses, barrel cache, resolution diagnostics) — the full cache is never loaded on the status path.
