# wikifier/cache/files.py

**Purpose:** per-file cache entries and dirty detection.

- `get_mtime_ns` is what the cache stores; rows written before 4.7 hold whole seconds and are detected (`< 1e12`).
- `compute_files_needing_reparse(root, candidates)`: unchanged nanosecond mtime ⇒ clean without reading the file; changed mtime with the same content hash ⇒ recorded in `content_stable_mtime_updates` (index refresh, no re-parse); also checks indexed files outside the candidate list.
- `compute_file_content_hash` → `sha256:<hex>`.
