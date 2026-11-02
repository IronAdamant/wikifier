# src/cache.rs

**Role:** The `wk_cache` text index under `.wikifier_staging`.

Each mapped file has a payload, a `by_src` edge list, a `by_dst` edge list, notes, and an optional barrel record. An edge line is destination, line, names, then optional flag letters `c`, `d`, and `b`.

Confidence is computed when an edge is read: dynamic 0.4, conditional 0.55, via barrel 0.7, static 0.9. The ACS reason is `dynamic_literal`, `conditional_guard`, `via_barrel`, or `resolved_static`.
