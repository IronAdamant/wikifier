# src/maps_out.rs

**Role:** Human `library.md` and the sharded agent folder cards.

`write` rebuilds `.wikifier_staging/maps/_root.json` and one `_index.json` per directory prefix. `library.md` has a file tree, then a Mermaid block capped at 80 edges, then the dependency table. `write_status` stores `incremental_status.json` for `map_complete` and `files_remaining_dirty`. `read_status` reads that file back.
