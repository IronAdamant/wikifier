# src/worktree.rs

**Role:** `worktree_root` / `--worktree`. Read tools answer for a git worktree from main's map plus an overlay of the files that differ in the tree.

`target` picks the run: the `worktree` / `worktree_root` flag (validated: absolute, existing, same git common dir as main, read from the `.git` file and `commondir`, no `git` call), or a root that is a linked worktree with no Wikifier state whose main checkout has one, or main. `run` refuses writers with `WorktreeReadOnly`, prepares the overlay, runs `dispatch_main` with the tree as root, and adds `worktree`, `overlay_files`, and `modularity.new_in_worktree`.

The overlay is main's `.wikifier_staging/overlays/<fnv of the tree path>/`: seeded once from main's `wk_cache` under main's lock, then refreshed per call by the incremental map run (size and mtime skip; equal hashes are not re-parsed). Calls that read health also run `check_changes` against main's health rows. While a call runs the tree is registered, and `staging`, `state`, `state_write`, and `baselines` route that root's paths; `is_overlay` tells writers to skip the journal and snapshots. Overlays whose worktree is gone are pruned.

Cold start: `seed` hard-links main's cache files into the overlay (copies when links fail) on several threads. `adopt_unchanged` gives overlay rows the tree's size and mtime when `crate::git_index` proves a file holds the bytes main's map hashed (main's file matches its map row and main's index entry, the tree's file matches the tree's index entry, same blob), so the map run skips it by stat. `base_view` / `BaseView::unchanged` let `check_changes` and the modularity line count treat such files as main's without reading them.
