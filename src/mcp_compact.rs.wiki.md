# src/mcp_compact.rs

**Role:** Compact default replies for the MCP tools whose output grows with the repository.

`DEFAULT_LIMITS` names the tools and their default item counts: `health` 10, `get_cycles` 5, `get_dependents` 50, `prepare_edit` 25, `get_resolution_diagnostics` 20. `default_limit` looks one up. `compact` shrinks a successful result: `health` entries are ranked (Red, changed Yellow, Initial stub, Green), cut to the limit, lose `source_content_hash`, and gain `entries_total`; each `get_cycles` cycle keeps `CYCLE_FILES` (10) files with `files_truncated`, and `reverse_dependencies` is cut; `dependents` is cut with `dependents_total` and a top-20 `dependent_dirs` count; diagnostics `notes` and `actionable_low_conf_edges` are cut with `*_total`. `src/mcp.rs` skips it when the call sets `full: true`. The CLI never calls it.
