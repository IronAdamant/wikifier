# tests/worktree_overlay.rs

**Role:** `worktree_root` against a temp main checkout and a linked worktree laid out the way git does (`.git` file, `commondir`), with one file edited, one added, one deleted, and one grown past the line limit.

Covers: dependents and dependencies follow the tree while the plain call and every byte of main's state stay the same; health, changed lines, check-changes, and `modularity.new_in_worktree` describe the branch; writers refuse; bad paths fail with one line; a root that is a bare worktree is answered as one; a main without git takes a copy; overlays of removed worktrees are pruned; the CLI `--worktree` and the MCP `worktree_root` schema and call.

Also: a fresh worktree trusts both git indexes (a file git vouches for keeps main's edges, proving it was not read; without the tree's index it is hashed), and `--worktree` before, between, or after the other arguments.
