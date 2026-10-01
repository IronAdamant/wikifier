# wikifier/gitchanges.py

**Purpose:** what changed according to git — the input for `api.record_changes`.

- `changed_files(root, since=None)` → `{"base": sha, "changes": [{"path", "status", "old_path"?}]}`: `git diff --name-status -z -M --relative <since or HEAD>` (staged + unstaged) plus `git ls-files --others --exclude-standard` (untracked). Paths are project-relative even when the project is a subdirectory of the repository. `status`: added | modified | deleted | renamed | copied | untracked.
- No commits yet ⇒ diff against git's empty tree (`EMPTY_TREE`). Unknown `since` ref ⇒ error.
- `GitUnavailableError`: git missing or not a work tree. git is an external tool, not a Python dependency; callers fall back to per-file `record_change`.
