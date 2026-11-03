# src/cache_commit.rs

**Role:** One commit for a map run.

The `Session` edits the index in memory and writes `by_src` before `by_dst`, with the generation file last. A crash leaves `commit.pending`. Unresolved notes are stored as `U`, the raw specifier, the line, and a reason. Removing a file also drops its barrel record on commit. The cache lock is `wk.lock`. `check_consistency` compares the forward and reverse indexes. `rebuild` rewrites them. `Consistency` is that comparison's result.

`Session` methods: `open`, `known`, `dsts_of`, `note_stat`, `rels`, `upsert`, `remove`, `stage_barrel`, `commit`.
