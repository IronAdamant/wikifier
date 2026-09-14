# wikifier/map_index.py

Sharded names-only **agent folder maps**. Same import cache as `library.md`, not one dump.

## Purpose

After `update-maps` persist, write `.wikifier_staging/maps/`:

- `_root.json` — top-level folders + top-level files (session_bootstrap)
- `<dir>/_index.json` — immediate children of that folder

A card rewrites only when that folder's child set (file names + child counts) changes. Content edits do not. No wiki blurbs. No mermaid. No second crawl.

## Hops

- Folder → `list_paths(prefix)` (next card)
- File → `prepare_edit` (deps/dependents already in the cache)

## Surfaces

- `ensure_map_index` — persist hook (reuse root card on zero-dirty)
- `bootstrap_map_index` — root card only
- `list_paths(..., depth=1)` — one folder; `depth=0` recursive
