# wikifier/cache_store.py

**Purpose:** SQLite import cache: `files(rel_path, mtime, content_hash, payload)`, `edges(src, dst, raw, confidence, score)` indexed on both ends, `meta(key, value)` for reserved `_*` keys.

- Indexed lookups: `load_file_entry`, `load_dependents`, `load_dependencies` (edges backfilled once for older databases).
- `save_cache_dict` rewrites files+edges and meta in one transaction; a dict without file entries never wipes the files table (meta-only saves are safe).
- `load_meta(keys)`, `save_meta_key`, `update_file_index_rows`, `prune_file_index_outside_scope`, `cache_status` (incl. `edge_count`).
- Legacy `import_cache.json` is read only when no database exists; `WIKIFIER_CACHE_JSON=1` adds a JSON copy on save. Database errors propagate.
