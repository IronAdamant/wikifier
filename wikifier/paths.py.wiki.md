# wikifier/paths.py

**Purpose:** single source of truth for *which project* and *which file*.

- `resolve_root(project_root)`: explicit argument → `WIKIFIER_PROJECT_ROOT` → marker discovery. An explicit value that is not a directory raises `ProjectRootError` (never a silent cwd fallback).
- `to_rel(root, file)`: canonical project-relative POSIX key from absolute (inside root, symlinked roots like /tmp vs /private/tmp handled), `./`-prefixed or backslash paths; climbing out raises `ProjectPathError`.
- `is_under(root, key)`: containment check used to prune health keys.
