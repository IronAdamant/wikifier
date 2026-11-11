# src/git_index.rs

**Role:** read a git checkout's index (`.git/index`, or the linked worktree's `gitdir`/index; versions 2 and 3, SHA-1 or SHA-256 ids) without running git.

`GitIndex::read` parses the stage-0 entries: path, size, mtime, blob id. `blob_if_fresh` returns an entry's blob id only while the file still has that size and mtime and the entry is not racily clean (stamped at or after the index file itself); nanoseconds count only when git stored them. Index v4, split indexes, and anything malformed give `None`, and the caller hashes files instead. Used by `src/worktree.rs` to prove a fresh worktree's files unchanged without reading them.
