# src/api.rs

**Role:** Agent-facing operations. The CLI and MCP server both call this module.

`update_maps_run` walks the map roots, skips unchanged files by size and mtime, commits the text cache, then writes `library.md` and the folder cards. `--directory`, `--max-files`, and `--stream` are arguments of that run. A file budget leaves the map incomplete and the next run resumes.

`record_deletion` journals the removal, marks the health row Red, and drops the file from the graph. `record_changes_opts` takes the git change list and matches reasons by exact path, directory prefix, then glob. `mark_green` checks Python and JS/TS public names against the wiki and removes that file's pending line.

`serve_loop` answers the JSON API, `/__wikifier/status`, dashboard `run` and `shutdown`, and project files such as `file_health.json` and `library.md`. `monitor_loop` and `daemon_ctl` (`start`, `stop`, `status`, `run`) are the other standing processes. `heal_stubs` with `dry_run` counts long Initial stubs and does not write. `seed-health` returns `HealthError` when the write fails. `verify_wikis_under` can limit the check to one file or directory. `search-journal --file` keeps one path. Mutating commands take `.wikifier_staging/.lock` before the cache lock. `prune_health` and `prune_pending` keep files named in `monitored_paths.txt`. `prune-health --deleted-missing` also drops rows whose path is no longer a file.
