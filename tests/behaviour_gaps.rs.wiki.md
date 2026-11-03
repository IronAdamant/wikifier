# tests/behaviour_gaps.rs

**Role:** Behaviour tests for four paths that had no coverage.

`mcp_deadline_stops_a_blocking_call_and_lets_a_fast_call_finish` runs `wikifier mcp` with `WIKIFIER_MCP_DEADLINE_S`. A `health` call finishes. A `monitor` call returns `DeadlineExceeded`, `timed_out`, and `may_still_complete`. A value of `0` still waits at least one second.

`check_changes_cap_stops_the_pass_and_names_the_env_var` sets `WIKIFIER_CHECK_CHANGES_MAX` to 1 and expects `truncated` plus the env var in the warning. A numeric cap above the file count, and a non-numeric value, leave the pass uncapped.

`sqlite_import_fills_an_empty_cache_and_reports_an_unreadable_file` always checks that a corrupt sqlite file warns `sqlite_present_unread`. When the `sqlite3` CLI is on PATH it also builds a database, checks the imported edge and the `sha256:legacy` hash, and checks that a later sqlite write does not replace a filled cache.

`actionable_low_conf_edges_keep_conditional_and_drop_dynamic` maps a conditional import and a dynamic `import_module`. Only the conditional edge is actionable, at confidence 0.55 with reason `conditional_guard`.
