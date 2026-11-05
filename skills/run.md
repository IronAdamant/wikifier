# Wikifier Agent Protocol v0.7

**Package 5.0.0** (live version: `wikifier --version`, from `Cargo.toml`) · **Status:** active, supersedes v0.6 · **Scope:** agent-to-agent codebase wiki for token-efficient lookup. Not a human docs product, not an issue tracker.

This file is the contract for any agent operating Wikifier. Part 1 is all you need day to day; Part 2 is reference. In the Wikifier repository, `AGENTS.md` is the entry point and points here.

---

## Part 1 — The core loop (read this)

**SELECTIVE WORK (mandatory):** only touch 🔴 Red and *actionable* 🟡 Yellow files. Never re-summarize 🟢 Green files. Never bulk-wiki 🟡 *Initial* stubs — a stub means "on the map", not "needs prose"; write a wiki for a file only when you edit it.

### Every session

| Step | MCP tool | CLI (`wikifier …`) |
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
- File arguments may be project-relative, `./`-prefixed, `\`-separated (Windows) or absolute (inside the project). Results return the canonical project-relative `file`. A lookup (`prepare_edit`, `get_dependencies`, `get_dependents`, `get_file_wiki`) on a path that is neither on disk nor in the map returns `error_type: "FileNotFound"`; `list_paths` shows the mapped files.
- `record_change` and `mark_green` require the file to exist; for removed files use `record_deletion`.
- `check_changes` watches every mapped file, every file ever marked Green, and `monitored_paths.txt` entries — the list only adds files (docs, scripts), it never hides mapped ones. A mapped file whose size and mtime still match its cache row is compared by the hash stored there (the rule `update_maps` skips by); any other file is read and hashed.
- Green means the wiki was checked against the code (see *Wiki verification*). A failed check lists the symbols to document; update the wiki and retry. `force=True` with a reason overrides and is recorded as `forced`.
- Orient with the bootstrap **root folder card** → `list_paths(prefix)` for one folder → `prepare_edit(file)` for file-to-file links. Do not read `library.md` mermaid to orient.
- Wiki convention: `<file>.wiki.md` next to the source (e.g. `src/api.rs.wiki.md`).

### Readiness

`session_bootstrap.readiness` must be **`ready_for_daemon`** before unattended work — not Map Ready alone. If it is `blocked`, do the priority-1/2 `actions[]` first (they are not install failures):

1. Write lean `monitored_paths.txt` (extra watch list — the docs and scripts you maintain; mapped sources are watched anyway; never bare `.` on real trees).
2. Write `map_paths.txt` (import-map package roots; independent of monitored paths).
3. `update_maps(full=True)`, then re-run `session_bootstrap`.

### Paste into new sessions

```
You are operating inside a Wikifier-managed codebase (Agent Protocol v0.7, package 5.0.0).
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

`mark_green` compares the file's public symbols (Python: `__all__` or top-level public functions/classes; JS/TS: exports; Rust: unrestricted `pub` items, impl methods, and trait-impl items) with those recorded at the previous mark-green, and refuses (`error_type: "WikiVerificationError"`, `issues[]`) when:

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

- `get_dependencies(file)` (default `detail="compact"`): `internal` edges (`path`, `line`, `names`, `conditional`, `dynamic`, `via_barrel`, `confidence`), `external` module names, and `needs_review` objects (`raw`, `line`, `reason`). `detail="full"` (CLI `--full`) also returns `imports[]` with `resolved_path`, `confidence_score`, `confidence_reasons`, `acs`, `is_dynamic`, `is_conditional`, and `in_cycle`.
- `get_dependents(file)`: who imports it (indexed lookup).
- ACS triage: work from `actionable_low_conf_edges` + `reason_code_counts`. `external_or_bare` and `dynamic_literal` edges are noise, not work items.
- `get_cycles`: strongly connected components of size greater than 1. Each component includes `external_edges` and `break_hint` (the lowest-confidence edge inside the component, with `src`, `dst`, `confidence`, and `reason`).
- Parsers: comment-masked regex for Python, JS/TS, Rust, Go, C/C++, C#, and Java. Named JS/TS re-exports are followed to depth 8 and stored as `via_barrel`. A Python import indented under a block is `conditional`. `import()` is `dynamic`. See *Implementation* for what this scan does and does not resolve.

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

Mutations take an advisory project lock (`.wikifier_staging/.lock`, a create-new pid file), re-entrant within a thread and exclusive across processes. Never hand-edit `file_health.json`, `pending_updates.md`, `library.md` or the cache — use the tools.

### Commands (CLI)

| Command | Purpose |
|---|---|
| `init [DIR]` | keeps an existing path list, seeds the map roots when that list is empty (`src/` if present, else each top-level directory that holds source), copies `index.html` only when it is missing, writes `.wikifier/marker`. `[DIR]` is the project root unless `--target` is set |
| `session-bootstrap`, `check-changes`, `suggest-next [--json]` | core loop |
| `prepare-edit F`, `record-change F WHY`, `mark-green F [WHY] [--force]`, `record-deletion F [WHY]` | per-file loop |
| `record-changes [-r PATH=WHY]… [--reasons FILE] [--default WHY] [--only P]… [--since REF] [--green] [--dry-run]` | batch loop (git) |
| `verify-wikis [DIR]` | re-check Green wikis against the code (exit 1 if any fail). `[DIR]` limits the check to that file or directory |
| `dependencies F [--full]`, `dependents F`, `cycles [--json]`, `why-file F`, `search-journal [TEXT] [--file F]` | lookup. `--file` limits the journal search to that path |
| `update-maps [--full] [--directory D] [--max-files N] [--stream]` | dependency map |
| `health [--summary\|--json]`, `validate`, `cache-status`, `autonomous-status` | status |
| `seed-health`, `seed-source-hashes`, `prune-pending`, `prune-health [--deleted-missing]`, `prune-barrels` | hygiene |
| `heal-stubs [--dry-run]`, `healable-stubs`, `healing-stats`, `stale-wikis` | stub healing |
| `journal [YYYY-MM-DD]`, `issues`, `list-paths [PREFIX]`, `list-core-tools` | misc. `issues` is the same `actions[]` list as `suggest-next` |
| `monitor`, `daemon start\|stop\|status\|run`, `serve [PORT]` | background / human view. `daemon logs` and `install-service` are not commands |

The implementation is a std-only Rust binary. `wikifier.sh` / `.ps1` / `.bat` launch it. MCP is `wikifier mcp`.

### Library

There is no Python library. Agents call the CLI or `wikifier mcp`. The same functions live in the Rust crate (`src/api.rs`) and both fronts call them.

### Implementation (package 5.0.0, protocol stays v0.7)

The program is a std-only Rust binary under `src/`. `Cargo.toml` has an empty `[dependencies]` list. Launchers exec that binary. MCP is `wikifier mcp`.

- `update-maps` writes `library.md` (a file tree, a Mermaid block capped at 80 edges, and the dependency table) and `.wikifier_staging/maps/` (`_root.json` plus one `_index.json` per directory). `--directory`, `--max-files`, and `--stream` apply. A file budget returns `map_complete=false` and `files_remaining_dirty`. The next run stat-skips files already parsed, so the same command resumes. `--stream` prints JSON events on stderr and still persists the map. The result field `parser` is `regex+reexport`. A run that changes nothing in the cache keeps `library.md` and the folder cards as they are.
- The cache is `.wikifier_staging/wk_cache`, a text index (payload, `by_src`, `by_dst`, notes, barrels). When that index is empty, an existing `import_cache.sqlite` is imported with the `sqlite3` CLI, and `import_cache.json` is the other fallback. Rows imported this way use hash `sha256:legacy` and mtime 0, so the next `update-maps` re-parses them. If the sqlite file is present and cannot be read, the result includes the warning `sqlite_present_unread`.
- A resolved edge line is `dst`, `line`, `names`, then optional flag letters `c` (conditional), `d` (dynamic), and `b` (via barrel). Confidence is assigned when the edge is read: dynamic 0.4, conditional 0.55, via barrel 0.7, static 0.9. ACS reason codes are `dynamic_literal`, `conditional_guard`, `via_barrel`, and `resolved_static`. Unresolved notes use `unresolved_relative` (the specifier starts with `.`), `dynamic_literal`, or `unresolved`.
- `dependencies --full` returns `imports[]` with `confidence_score`, `confidence_reasons`, `acs`, `is_dynamic`, `is_conditional`, and `in_cycle`. Compact rows always include `conditional`, `dynamic`, `via_barrel`, and `confidence`.
- `record_deletion` appends the journal line, marks the health row Red, drops the file from the graph, and removes its pending line. The file does not have to exist.
- `record_changes` matches reasons by exact path, then the longest `dir/` prefix, then the longest glob (`*` and `?`). `--reasons` accepts a JSON object (`{"path": "why"}`) or `PATH=REASON` lines (`-` reads stdin). `--only`, `--green`, `--dry-run`, and deletions are applied. `--green` lists verification failures and leaves those files Yellow. MCP `reasons` may be that object.
- `mark_green` extracts Python public names with a tokenizer (multi-line `__all__` lists, tuples, and `+=`; comments and strings ignored; top-level `def`, `async def`, and `class`, including decorated ones; `.py` and `.pyi`), JS/TS `export` names after comments and strings are masked, and Rust unrestricted `pub` items (`fn`, `struct`, `enum`, `trait`, `mod`, `type`, `const`, `static`, and `pub use` names), plus `pub` methods and associated items on a public type and the items written in a trait impl for that type. Each current name must appear in the wiki. `pub(crate)`, `pub(super)`, `pub(self)`, and `pub(in ...)` are not Rust public names. With a previous baseline, a removed name still wrapped in backticks is `wiki_mentions_removed_symbols`, and a changed public surface with an unchanged wiki hash is `wiki_not_updated_for_api_change`. Go, C/C++, C#, and Java have no symbol extractor, so their rows are `unchecked`. The wiki is `<file>.wiki.md`, then `<file>.md`, the stem beside the source, then the same names under `docs/wiki`, `docs`, `wiki`, `documentation`, and `.wiki`. `health --summary` returns `health_summary` (including `green_breakdown`) without the entry list. `health --format healing-stats` is the stub counts. `--directory` limits health, bootstrap, and suggest-next. A successful mark removes that file's pending line. Pending bullets are `- path: message` (`<reason> — refresh the wiki, then mark-green` after `record-change`). The `(no pending items …)` line shows only while the queue is empty. `session_bootstrap --limit N` caps `files` and adds `files_total`; over MCP the default cap is 100 (`limit: 0` lists every file).
- `suggest-next` adds `review_low_confidence_edges` when a mapped file has a resolved, non-dynamic edge below confidence 0.65. The count is stored while parsing (`low_conf.tsv`) so a warm `update-maps` does not rescan it.
- `list-paths --depth 0` or `--recursive` lists every file under the prefix. `--max-files` caps that list. `verify-wikis --limit` and `stale-wikis --limit` cap the rows returned. `cycles` adds `severity`, `score`, `external_blast_radius`, `recommendation`, and `reverse_dependencies` (top 20 by inbound edges). `--no-analysis` omits those. `--max-items` caps the cycle list.
- `seed-source-hashes` writes the current hash onto Green rows and does not change status. `--force` replaces a hash that is already stored. `seed-health` still adds Initial-stub rows. `heal-stubs` promotes a stub whose wiki is at least 350 characters (`--min-wiki-length` overrides).
- Health stubs from `update-maps` follow `monitored_paths.txt` when that file lists real paths. If the file is absent, empty, or only a bare `.`, every mapped file is seeded.
- The scan ignores comments and strings. It does not use CPython `ast`. It does read `tsconfig.json` `paths`, `package.json` `exports`, and npm `workspaces` (`*` directory globs). Named re-exports are the barrel follow. Rust reads the root `Cargo.toml` `[package].name`, `[lib].name`, and `[workspace] members` (globs included; hyphens become underscores). It resolves `crate::`, `self::`, `super::`, those crate names, and `mod` to files. `crate::` stays in the file's crate (`tests/*.rs` and `src/bin/*.rs` are their own crates, and a workspace member does not share `crate::` with another member). A package or lib name points at that member's library. Accuracy is `accuracy_fixtures_match_frozen_edges`, including the Rust crate layout. This parser has not been run on Babylon.js.
- MCP `tools/call` sets `isError` when the payload has `success: false`. `resources/read` and `prompts/get` answer. Prompts name the tools to call. Optional arguments include `format` (`text` or `json`), `timeout_s`, `directory`, `detail`, `low_confidence_only`, `unresolved_only`, `depth`, `recursive`, `max_files`, `limit`, `max_items`, and a `reasons` object. A call waits at most `timeout_s` or `WIKIFIER_MCP_DEADLINE_S` seconds (default 60) and then returns `timed_out` and `may_still_complete`. An identical journal action, file, and reason inside 120 seconds sets `duplicate_skipped` and does not append another line. A call that leaves out a required argument other than `project_root` returns `error_type: "InvalidArguments"` with the accepted and received argument names. Over MCP, `update_maps` omits the edge list unless `edges: true` (`edges_persisted` is the count), and `health` takes `limit` (with `entries_total`) and `summary`. The CLI default is JSON. `--text` prints prose. `health --format text` does the same for health.
- Commands that write health, pending, the map, or the cache take `.wikifier_staging/.lock` before the cache lock. The lock is re-entrant on the same thread, waits 30 seconds, and is stolen when the recorded pid is dead. A timeout returns `error_type: "LockTimeoutError"` and `timed_out: true`.
- `init` keeps a path list that already has a non-comment entry. When a list is missing it writes the map roots: `src/` when it exists, otherwise every top-level directory that holds a source file (for example `crates/` and `tests/` in a Cargo workspace), otherwise `src/`. It also writes `exclude_patterns.txt`, empty `file_health.md`, `pending_updates.md`, `library.md`, `.wikifier/config`, `.wikifier/marker`, and the `journal/` and `Logged_issues/` directories when those paths are absent. `--no-copy` skips `index.html`. Otherwise `index.html` is copied only when it is missing.
- `serve` listens on `127.0.0.1:8787` until stopped. It answers `/`, `/__wikifier/api/{bootstrap,file,dependencies,dependents,cycles,journal,diagnostics}`, `/__wikifier/status`, and the project files the dashboard reads (`file_health.json`, `library.md`). `POST /__wikifier/run` accepts `update-maps`, `update-maps --full`, and `check-changes`. `POST /__wikifier/shutdown` stops the process. `monitor` repeats `check-changes` (default every 30 seconds). `daemon run` checks every `WIKIFIER_POLL_INTERVAL` seconds (default 30) and runs `update-maps` at start and then at most every `WIKIFIER_DAEMON_MAPS_INTERVAL` seconds (default 600). `WIKIFIER_DAEMON_MAPS=0` skips the map. State is `.wikifier_staging/wikifier.pid`, `daemon.log`, and `daemon_heartbeat.json`. `daemon logs`, `restart`, `install-service`, and `uninstall-service` are supported (systemd user unit on Linux, launchd plist on macOS, Task Scheduler on Windows). `daemon start` refuses readiness `blocked` unless `--force`. `not_ready` may start. `issues` is the same `actions[]` list as `suggest-next`. `library.md` stays the short tree, Mermaid block, and dependency table; cycle severity is on `cycles`, not in that file.

```bash
wikifier --target /abs/project session-bootstrap
wikifier --target /abs/project record-change src/api/client.py "Switched the client: the old one blocked the loop."
# … refresh src/api/client.py.wiki.md …
wikifier --target /abs/project mark-green src/api/client.py "Wiki reflects the new client and retry policy."
```

### Migration v0.6 → v0.7 (package 4.7.0)

- Missing explicit project roots are errors (previously: silent fallback to the current directory).
- `record_change` / `mark_green` normalize paths, require existing files, and return the canonical `file`; `record_change` adds `journaled` / `duplicate_skipped`.
- `prepare_edit.dependencies[].resolved_path` is populated; `dependents` come from the indexed edge table.
- Python absolute imports now resolve (Django/`src/`-layout graphs were mostly missing before); JS comment/string imports are no longer edges; duplicate edges from overlapping patterns are gone; unresolved relative imports no longer appear as phantom files. Expect more edges and different ACS numbers after the first full `update_maps`.
- Conditional detection only counts *enclosing* guards (most top-level imports were previously flagged conditional).
- New CLI commands: `dependencies`, `dependents`, `heal-stubs`, `healable-stubs`, `healing-stats`, `stale-wikis`, `prune-barrels`, `cycles --json`, `journal --json`, `issues --json`. In the 4.7.0 package those commands lived in Python. They now live in `src/api.rs` and `src/main.rs`.
- `update-maps --stream` persists the map and prints JSON progress on stderr. The 4.7.0 package did this from `wikifier.streaming`.
- MCP no longer shells out; failures are reported, never retried through a second code path.
- `mark_green` verifies the wiki against the code and can now fail (`WikiVerificationError`); pass `force=True` with a reason to override. New entry fields: `public_symbols`, `verification`, `source_mtime_ns`; `health --summary` adds `green_breakdown`.
- `get_dependencies` returns the compact shape by default (`internal`, `external`, `needs_review`); pass `detail="full"` (CLI `--full`) for the previous `imports[]` records.
- `check_changes` watches mapped and Green files regardless of `monitored_paths.txt`; files that were invisible before may turn Yellow on the first run.
- New: `record_changes` / `record-changes`, `verify_wikis` / `verify-wikis`.
- The CLI exits non-zero on failure.

### Human layer (secondary)

`init` copies only `index.html`. Run `wikifier serve` and open `http://localhost:8787/index.html` (browsers block `file://` fetches). It is a read-only view of the same artifacts; `diagnostics.html` is maintainer-only and stays in the Wikifier repo. `wikifier serve` also answers read-only JSON at `/__wikifier/api/*` (`file`, `dependencies`, `dependents`, `cycles`, `journal`, `bootstrap`, `diagnostics`).
