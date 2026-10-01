# Wikifier Agent Protocol v0.7

**Package 4.7.x** (live version: `wikifier.__version__`) · **Status:** active, supersedes v0.6 · **Scope:** agent-to-agent codebase wiki for token-efficient lookup. Not a human docs product, not an issue tracker.

This file is the contract for any agent operating Wikifier. Part 1 is all you need day to day; Part 2 is reference.

---

## Part 1 — The core loop (read this)

**SELECTIVE WORK (mandatory):** only touch 🔴 Red and *actionable* 🟡 Yellow files. Never re-summarize 🟢 Green files. Never bulk-wiki 🟡 *Initial* stubs — a stub means "on the map", not "needs prose"; write a wiki for a file only when you edit it.

### Every session

| Step | MCP tool | CLI (`python -m wikifier …` / `wikifier …`) |
|---|---|---|
| 1. Orient | `session_bootstrap` | `session-bootstrap` |
| 2. What changed | `check_changes` | `check-changes` |
| 3. What to do | `suggest_next_actions` (use `actions[]`) | `suggest-next --json` |
| 4. Before editing a file | `prepare_edit(file)` (status, wiki, deps, dependents) | `prepare-edit <file>` |
| 5. After editing it | `record_change(file, why)` — **never skip** | `record-change <file> "<why>"` |
| 6. After refreshing its wiki | `mark_green(file)` — closes the loop; **refused** if the wiki misses public symbols you added/removed | `mark-green <file>` |
| 7. Imports/structure changed | `update_maps` | `update-maps` |
| 5+6 for many files | `record_changes(reasons, green=True)` — reasons per path/glob/`dir/`, from git | `record-changes -r "src/=why" --green` |

- Always pass `project_root=` (MCP/library) or `--target DIR` / `WIKIFIER_PROJECT_ROOT` (CLI) for any project other than the current directory. **A root that does not exist is an error** — nothing is ever written elsewhere.
- File arguments may be project-relative, `./`-prefixed or absolute (inside the project). Results return the canonical project-relative `file`.
- `record_change` and `mark_green` require the file to exist; for removed files use `record_deletion`.
- `check_changes` watches every mapped file, every file ever marked Green, and `monitored_paths.txt` entries — the list only adds files (docs, scripts), it never hides mapped ones.
- Green means the wiki was checked against the code (see *Wiki verification*). A failed check lists the symbols to document; update the wiki and retry. `force=True` with a reason overrides and is recorded as `forced`.
- Orient with the bootstrap **root folder card** → `list_paths(prefix)` for one folder → `prepare_edit(file)` for file-to-file links. Do not read `library.md` mermaid to orient.
- Wiki convention: `<file>.wiki.md` next to the source (e.g. `src/api.py.wiki.md`).

### Readiness

`session_bootstrap.readiness` must be **`ready_for_daemon`** before unattended work — not Map Ready alone. If it is `blocked`, do the priority-1/2 `actions[]` first (they are not install failures):

1. Write lean `monitored_paths.txt` (extra watch list — the docs and scripts you maintain; mapped sources are watched anyway; never bare `.` on real trees).
2. Write `map_paths.txt` (import-map package roots; independent of monitored paths).
3. `update_maps(full=True)`, then re-run `session_bootstrap`.

### Paste into new sessions

```
You are operating inside a Wikifier-managed codebase (Agent Protocol v0.7, package 4.7.x).
It is an agent-to-agent wiki: look things up (health, file wikis, deps) instead of re-reading sources.

SELECTIVE WORK: only update 🔴 Red and actionable 🟡 Yellow files; never re-wiki 🟢 Green files;
never bulk-wiki 🟡 Initial stubs (wiki a file only when you edit it).

Loop: session_bootstrap → check_changes → suggest_next_actions (json actions[]) →
prepare_edit(file) → edit → record_change(file, why) → refresh <file>.wiki.md → mark_green(file).
Many files: record_changes({"path or glob or dir/": "why"}, green=True, only=[files you touched]).
mark_green checks the wiki against the code: if it lists undocumented symbols, document them and retry.
Run update_maps only when imports or structure changed. Pass project_root= for external projects.
Never skip record_change after an edit; never skip mark_green after refreshing that file's wiki.
```

---

## Part 2 — Reference

### Health statuses

| Status | Meaning | Agent action |
|---|---|---|
| 🟢 Green | wiki checked against the code at mark-green; source/wiki hashes and public symbols captured | look up only |
| 🟡 Yellow *actionable* | recorded change, content changed since mark-green, or importer of a changed barrel | refresh wiki → mark-green |
| 🟡 Yellow *Initial stub* | on the dependency map, no wiki yet | nothing until you edit it |
| 🔴 Red | file missing on disk or recorded deletion | restore, or `record_deletion` / `prune-health --deleted-missing` |

`check_changes` is content-honest: an mtime-only touch with unchanged bytes does not re-Yellow a Green file, and already-flagged files are not re-journaled. It watches explicit files listed in `monitored_paths.txt` (any type, e.g. `README.md`) and parseable sources under listed directories.

### Wiki verification (mark_green)

`mark_green` compares the file's public symbols (Python: `__all__` or top-level public functions/classes; JS/TS: exports) with those recorded at the previous mark-green, and refuses (`error_type: "WikiVerificationError"`, `issues[]`) when:

| Issue code | Meaning |
|---|---|
| `undocumented_new_symbols` | a public symbol was added and the wiki does not mention it |
| `wiki_mentions_removed_symbols` | a removed symbol is still referenced in backticks in the wiki |
| `wiki_not_updated_for_api_change` | the public surface changed but the wiki file is byte-identical to the last mark-green |

A change that leaves the public surface alone (a bug fix inside a function) passes without touching the wiki. The first mark-green after upgrading only warns (no baseline yet). Each Green row records `verification`: `verified`, `no_wiki` (allowed — map-first), `unchecked` (no symbol extractor for the language), `forced` (overridden with a reason), or `legacy` (marked before verification). `health --summary` shows the split as `green_breakdown`; `verify_wikis` / `verify-wikis` re-checks every Green wiki without writing.

### Batch recording (record_changes)

`record_changes(reasons, default_reason=None, since=None, green=False, dry_run=False, only=None)` reads git (`git diff --name-status <since or HEAD>` plus untracked files, limited to the project root). `reasons` keys are exact paths, globs or `dir/` prefixes (exact wins, then the longest pattern); `default_reason` fills the rest. If any file is left without a reason, **nothing is written** and the result has `missing_reasons` + a fill-in `template`. Deletions and the old side of renames go through `record_deletion`. `green=True` marks each changed file Green through verification (`verification_failed` lists the rest, which stay Yellow) and retires deleted files whose wiki is gone. Wikifier artifacts and `*.wiki.md` files are skipped. `unused_reasons` flags patterns that matched nothing. Without git: `error_type: "GitUnavailableError"` — use `record_change` per file.

### Readiness tiers (`assess_autonomous_readiness`)

| Tier | When |
|---|---|
| `blocked` | no import map and/or no health matrix (or a ghost flood) |
| `map_ok_scope_risk` | map + health present but scope warnings (bare `.` monitor, multi-repo parent) |
| `ready_for_daemon` | Map Ready/Good and a lean monitor — the only safe unattended tier |
| `ready_with_agent_wiki_work` | needs attention, no reds |
| `not_ready` | anything else (e.g. reds) |

### Dependency intelligence

- `get_dependencies(file)` (default `detail="compact"`): `internal` edges (`path`, `line`, `names`, plus `conditional` / `dynamic` / `via_barrel` / `in_cycle` / `confidence` only when they apply), `external` module names, `needs_review` (unresolved imports that look internal). About 1/10 the size of `detail="full"`, which returns `imports[]` with every per-edge record — `confidence_score` 0.05–0.95, `confidence_reasons`, `confidence_explanation` (ends with a **Recommendation:** sentence), `is_dynamic`/`dynamic_type`, `is_conditional`/`conditional_context`, `via_barrel`/`barrel_depth`, `strategy`, `diagnostic`. `low_confidence_only` / `unresolved_only` (MCP) imply full.
- `get_dependents(file)`: who imports it (indexed lookup).
- ACS triage: work from `actionable_low_conf_edges` + `reason_code_counts`. `external_or_bare` and `dynamic_literal` edges are noise, not work items.
- `get_cycles(analysis=True)`: SCC clusters with severity, external blast radius, weakest links and ranked breaking recommendations.
- Parsers: Python (stdlib `ast`; absolute, relative and `from pkg import submodule` imports resolve; imports under `if`/`try` are conditional), JS/TS (comments and string literals ignored; tsconfig paths, package `exports`, workspaces, barrel re-export chains; `import()` is a dynamic literal), plus Rust, Go, C/C++, C#, Java.

### Update maps

`update_maps(directory=None, max_files=None, full=False)` runs the whole pipeline in-process and persists it. With a budget, `map_complete=false` / `files_remaining_dirty>0` means re-run with the same scope — already-parsed files are not dirty, so re-running resumes. `success=true` alone is not "map complete". `update-maps --stream` emits JSON progress events while persisting normally.

### Results and errors

- Every library/MCP call returns a dict with `success`. Operational failures (missing root, missing file, path outside the project, lock timeout, I/O) return `{"success": false, "error", "error_type"}`; lock timeouts add `timed_out: true`.
- MCP mutators run under a deadline (`WIKIFIER_MCP_DEADLINE_S`, default 60s). On `timed_out` the call may still complete in the background (`may_still_complete: true`) — check `why_file` before retrying. Identical `record_change` retries within 120s are de-duplicated in the journal (`duplicate_skipped: true`).
- Request `format="json"` for decisions; text output is for humans.
- Tolerate additive fields; never assume an exact key set.

### Scale (CLI-at-scale policy)

On large or barrel-heavy monorepos, prefer the CLI/library for `update_maps` and long health loops; scope with `--directory` / `max_files` and keep `monitored_paths.txt` lean. `WIKIFIER_CHECK_CHANGES_MAX` (default 2000) bounds one check-changes pass.

### Concurrency

Mutations take an advisory project lock (`.wikifier_staging/.lock`; `fcntl` on POSIX, `msvcrt` on Windows), re-entrant within a thread, exclusive across threads and processes. Never hand-edit `file_health.json`, `pending_updates.md`, `library.md` or the cache — use the tools.

### Commands (CLI)

| Command | Purpose |
|---|---|
| `init [DIR] [--no-copy]` | lean templates (`src/` default), `.wikifier/` marker, read-only dashboard |
| `session-bootstrap`, `check-changes`, `suggest-next [--json]` | core loop |
| `prepare-edit F`, `record-change F WHY`, `mark-green F [WHY] [--force]`, `record-deletion F [WHY]` | per-file loop |
| `record-changes [-r PATH=WHY]… [--reasons FILE] [--default WHY] [--only P]… [--since REF] [--green] [--dry-run]` | batch loop (git) |
| `verify-wikis [DIR]` | re-check Green wikis against the code (exit 1 if any fail) |
| `dependencies F [--full]`, `dependents F`, `cycles [--json]`, `why-file F`, `search-journal [TEXT] [--file F]` | lookup |
| `update-maps [--full] [--directory D] [--max-files N] [--stream]` | dependency map |
| `health [--summary\|--json]`, `validate`, `cache-status`, `autonomous-status` | status |
| `seed-health`, `seed-source-hashes`, `prune-pending`, `prune-health [--deleted-missing]`, `prune-barrels` | hygiene |
| `heal-stubs [--dry-run]`, `healable-stubs`, `healing-stats`, `stale-wikis` | stub healing |
| `journal [YYYY-MM-DD]`, `issues [SEVERITY]`, `list-paths [PREFIX]`, `list-core-tools` | misc |
| `monitor`, `daemon start\|stop\|status\|logs\|run\|install-service`, `serve [PORT]` | background / human view |

All commands are Python; `wikifier.sh` / `.ps1` / `.bat` only run `python -m wikifier`.

### Library

```python
from wikifier import (session_bootstrap, check_changes, prepare_edit, suggest_next_actions,
                      record_change, mark_green, record_deletion, update_maps,
                      get_dependencies, get_dependents, cycles_report, health, init_project)

session_bootstrap(project_root="/abs/project")
record_change("src/api/client.py", "Switched to httpx.AsyncClient: sync requests blocked the event loop.")
# … refresh src/api/client.py.wiki.md …
mark_green("src/api/client.py", "Wiki reflects httpx usage and retry policy.")
```

The health *module* is `importlib.import_module("wikifier.health")` (or `wikifier.health_module`); `from wikifier import health` is the convenience *function*.

### Migration v0.6 → v0.7 (package 4.7.0)

- Missing explicit project roots are errors (previously: silent fallback to the current directory).
- `record_change` / `mark_green` normalize paths, require existing files, and return the canonical `file`; `record_change` adds `journaled` / `duplicate_skipped`.
- `prepare_edit.dependencies[].resolved_path` is populated; `dependents` come from the indexed edge table.
- Python absolute imports now resolve (Django/`src/`-layout graphs were mostly missing before); JS comment/string imports are no longer edges; duplicate edges from overlapping patterns are gone; unresolved relative imports no longer appear as phantom files. Expect more edges and different ACS numbers after the first full `update_maps`.
- Conditional detection only counts *enclosing* guards (most top-level imports were previously flagged conditional).
- New CLI commands: `dependencies`, `dependents`, `heal-stubs`, `healable-stubs`, `healing-stats`, `stale-wikis`, `prune-barrels`, `cycles --json`, `journal --json`, `issues --json`. Every former shell command is now Python.
- Streaming moved: `wikifier.streaming.run_update_stream` (was `wikifier.import_cache.run_update_stream`); it now persists the map.
- MCP no longer shells out; failures are reported, never retried through a second code path.
- `mark_green` verifies the wiki against the code and can now fail (`WikiVerificationError`); pass `force=True` with a reason to override. New entry fields: `public_symbols`, `verification`, `source_mtime_ns`; `health --summary` adds `green_breakdown`.
- `get_dependencies` returns the compact shape by default (`internal`, `external`, `needs_review`); pass `detail="full"` (CLI `--full`) for the previous `imports[]` records.
- `check_changes` watches mapped and Green files regardless of `monitored_paths.txt`; files that were invisible before may turn Yellow on the first run.
- New: `record_changes` / `record-changes`, `verify_wikis` / `verify-wikis`.
- `python -m wikifier` now exits non-zero on failure (it always exited 0).

### Human layer (secondary)

`init` copies only `index.html`. Run `wikifier serve` and open `http://localhost:8787/index.html` (browsers block `file://` fetches). It is a read-only view of the same artifacts; `diagnostics.html` is maintainer-only and stays in the Wikifier repo. `wikifier serve` also answers read-only JSON at `/__wikifier/api/*` (`file`, `dependencies`, `dependents`, `cycles`, `journal`, `bootstrap`, `diagnostics`).
