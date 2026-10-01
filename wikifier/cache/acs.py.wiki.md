# wikifier/cache/acs.py

**Purpose:** agent confidence summary (ACS v1.3) and map coverage.

- `classify_edge_agent_signal` / `_edge_is_*_noise` — external/bare and literal-dynamic edges are `skip`; internal low-confidence edges are `investigate`.
- `compute_acs_summary` — totals, averages, `actionable_low_conf_edges`, `reason_code_counts`, samples. Recomputed by every update-maps; `ensure_acs_summary_persisted` only fills a missing/outdated summary on read paths.
- `build_map_coverage` — `complete` / `files_remaining_dirty` for budgeted runs.
