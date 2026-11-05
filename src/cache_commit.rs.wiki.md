# src/cache_commit.rs

**Role:** One commit for a map run.

The `Session` edits the index in memory and writes `by_src` before `by_dst`, with the generation file last. A crash leaves `commit.pending`. Unresolved notes are stored as `U`, the raw specifier, the line, and a reason. Removing a file also drops its barrel record on commit. The cache lock is `wk.lock`. `check_consistency` compares the forward and reverse indexes. `rebuild` rewrites them. `Consistency` is that comparison's result.

Forward files are written as one parallel batch before the `by_dst` batch (`cache::atomic_write_all`). `index_targets` lists each index row's targets for `cache::edges`. Every commit records each checked file's length in `sizes.tsv`; `Session::open` compares those lengths with one directory listing per kind (`by_src`, `payload`, `notes`, `by_dst`) and reads a file only when no length is recorded. A bad forward file marks its source for re-parsing (`needs_parse`); a bad `by_dst` file is rewritten from the index. `rebuild` deletes `sizes.tsv`.

`Session` methods: `open`, `known`, `dsts_of`, `note_stat`, `rels`, `upsert`, `remove`, `stage_barrel`, `has_changes`, `needs_parse`, `commit`. `has_changes` is true when `commit` would write.
