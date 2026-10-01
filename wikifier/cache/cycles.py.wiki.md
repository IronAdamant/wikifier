# wikifier/cache/cycles.py

**Purpose:** cycle detection and impact analysis.

- `compute_cycles` — Tarjan SCCs with per-cluster dynamic/conditional/barrel/low-confidence edge signals; reuses the previous result when `graph_signature` is unchanged.
- `compute_cycle_analyses` — severity score, external blast radius, weakest links, ranked breaking recommendations (rule registry `BREAKING_RECOMMENDATION_RULES`).
- `compute_graph_integrity` is derived from `_cycles` on read; `set_graph_integrity` only drops stale persisted copies.
