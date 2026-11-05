# src/scope.rs

**Role:** Which files a run may touch, and how a caller's path becomes a map key.

`detect` reads `map_paths.txt` and `monitored_paths.txt` into a `Scope`. A missing configured directory is a scope error, and three or more child projects make the root a container; `Scope::allows_walk` is false in both cases. `collect` walks the allowed prefixes with `excludes` (defaults plus `exclude_patterns.txt`) and keeps files that pass `is_source` (extensions in `SOURCE_EXTS`). `read_path_list` reads one path list.

`rel_of` turns a path under the root into the `/`-separated key the cache and health use. `rel_arg` does the same for a caller's argument: `src\a.rs`, `./src/a.rs`, and an absolute path under the root all give `src/a.rs`. `default_map_roots` picks the map roots for `init`: `src/` when it exists, else each top-level directory holding a source file, else `src/`.
