# wikifier/cache/barrel.py

**Purpose:** barrel (re-export) cache accessors, invalidation and pruning.

- `invalidate_stale_barrel_entries(cache, root, changed_files)` — exact canonical lookups in the reverse index (`_barrel_file_index`); falls back to scanning `via_barrel` pairs only when the index is empty. No basename matching.
- `get_barrel_invalidation_reports` (why an importer was dirtied), `get_barrel_cache_summary`, `append_barrel_invalidation_log`, `prune_barrel_resolutions` (age + deleted files).
