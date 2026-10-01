# wikifier/api.py

**Purpose:** the library surface every agent, CLI command and MCP tool goes through.

- Workflow: `check_changes`, `record_change`, `mark_green`, `record_deletion` — lock the project, normalize paths with `paths.to_rel`, write journal → health → pending. Files must exist (except deletions).
- `check_changes` watches mapped files, files with a Green baseline and `monitored_paths.txt` entries (`_watch_candidates`); files with a baseline are compared against the mtime stored with it, so `update_maps` running first cannot hide an edit.
- `mark_green(file, reason, force=False)` verifies the wiki against the code (`health_pkg.verify`); on failure returns `error_type: "WikiVerificationError"` + `issues`/`hint`; `force` needs a reason. Result has `verification`, `warnings`, `symbol_coverage`.
- `record_changes(reasons, default_reason, since, green, dry_run, only)` — one call over git's change set (`gitchanges.changed_files`): reasons by exact path > longest glob/`dir/`; any file without a reason ⇒ nothing written + `template`; deletions/renames via `record_deletion`; `green=True` marks Green through verification and retires deleted rows whose wiki is gone. `verify_wikis` — read-only audit of Green wikis.
- Maps: `run_full_update` (collect → nanosecond-mtime dirty → parse via `_parser_for` → `_dedupe_pairs` → persist + reverse index, cycles, cycle analyses, ACS and resolution diagnostics recomputed → health stubs → `library.md` + folder maps). Supports `max_files`, `time_budget_s`, `progress` callback; reports `map_complete`. `update_maps` is the root-checked facade.
- Lookup: `prepare_edit`, `session_bootstrap`, `suggest_next_actions` (+ `agent_loop`), `get_dependencies(file, detail="compact"|"full")` (compact: `internal`, `external`, `needs_review` via `_compact_imports`) / `get_dependents` (indexed SQLite edges), `cycles_report` + `format_cycles_report`, `why_file`, `search_journal`, `list_paths`.
- Setup: `init_project` (lean templates, `.wikifier/config`, dashboard copy), `copy_human_dashboards`, `heal_stubs`, `journal`, `issues`, `health`, `cache_status`, `seed_source_content_hashes`, `list_core_tools`.

**Contract:** every function returns a dict with `success`; failures carry `error` + `error_type` (`ProjectRootError`, `ProjectPathError`, `FileNotFoundError`, `LockTimeoutError` → `timed_out`). Never falls back to another directory.
