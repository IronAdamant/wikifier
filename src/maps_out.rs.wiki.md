# src/maps_out.rs

**Role:** Human `library.md` and the sharded agent folder cards.

`write` rebuilds `.wikifier_staging/maps/_root.json` and one `_index.json` per directory prefix. `library.md` has a file tree, then a Mermaid block capped at 80 edges, then the dependency table. `write` reads each file's `by_src` record only. `current` is true when `library.md` (LF or CRLF) and `_root.json` were written by `write`; `update-maps` skips `write` when the cache commit changed nothing and `current` holds. `write_status` stores `incremental_status.json` for `map_complete` and `files_remaining_dirty`. `read_status` reads that file back.

5.5.0: `library.md` is read and written through `crate::worktree::state` / `state_write`, and the folder cards live under the staging dir that `crate::worktree::staging` names.
