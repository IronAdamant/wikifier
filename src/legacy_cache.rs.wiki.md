# src/legacy_cache.rs

**Role:** Fill an empty `wk_cache` from an older import cache.

`import_if_empty` runs when the text cache has no paths. If `import_cache.sqlite` exists, the `sqlite3` CLI reads `files` and `edges`. `import_cache.json` is the other fallback. Imported rows use mtime 0 and hash `sha256:legacy`, so the next `update-maps` re-parses them. A sqlite file that cannot be read returns the warning `sqlite_present_unread`.
