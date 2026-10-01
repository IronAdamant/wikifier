# wikifier/cache/io.py

**Purpose:** the historical dict API over `wikifier.cache_store` (SQLite).

`load_cache` (full dict incl. `_*` keys), `load_mtime_index` (light), `save_cache` (locks) / `_do_save_cache` (caller holds the lock). Errors propagate — there is no silent JSON fallback.
