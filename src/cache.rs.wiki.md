# src/cache.rs

**Role:** The `wk_cache` text index under `.wikifier_staging`.

Each mapped file has a payload, a `by_src` edge list, a `by_dst` edge list, notes, and an optional barrel record. An edge line is destination, line, names, then optional flag letters `c`, `d`, and `b`.

`atomic_write` writes a temp file, syncs it, renames it into place, and flushes the directory. `atomic_write_all` does the same for a batch on several threads and flushes each directory once; a commit uses it for the forward files, then for `by_dst`. `edges` reads every file's targets from `index.tsv` (one file), falling back to `by_src` for an index row without targets. `load_internal_edges` reads one `by_src` record without the notes. `index_by_path` and `hash_if_unchanged` give `check-changes` and health seeding the stored content hash when a file's size and mtime still match its index row.

Confidence is computed when an edge is read: dynamic 0.4, conditional 0.55, via barrel 0.7, static 0.9. The ACS reason is `dynamic_literal`, `conditional_guard`, `via_barrel`, or `resolved_static`.

Public names: `check_consistency`, `rebuild`, `Consistency`, `Session`, `payload_path`, `by_src_path`, `commit_pending_path`, `load_dependencies`, `InternalEdge`, `confidence`, `acs_reason`, `confidence_of`, `format_edge_line`, `DependencyView`, `load_dependency_view`, `load_internal_edges`, `load_dependents`, `list_prefix`, `all_paths`, `FileUpdate`, `upsert_file`, `remove_file`, `indexed_rows`, `index_by_path`, `hash_if_unchanged`, `payload_bytes`, `stat_ns`, `edges`, `rel_string`, `write_barrel_record`, `prune_barrel_files`.
