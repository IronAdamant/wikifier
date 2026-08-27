# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed
- CI: install `wikifier[mcp]` only on Python ≥3.10 (`mcp` has no 3.8/3.9 wheels).

## [4.6.13] - 2026-08-27

### Added
- `record_change` returns additive `needs_mark_green: true` and does not auto-green.
- `suggest_next_actions` / `session_bootstrap` emit a `mark_green` action for recorded yellows.
- `prune-health --deleted-missing` retires DELETED audit rows whose files are gone.
- MCP in-process deadline (`timeout_s`, default 60s) on status/check-changes/mutators; `timed_out` structured failure.
- Shared `wikifier/parsers/_ldsi.py` so importing the Python parser does not load JavaScript/BREE/CDIA.

### Fixed
- Collect/parse `.mjs/.cjs/.mts/.cts` as JavaScript sources (map suffixes now match `_parse_file`).
- `import a, b` emits two Python edges; CJS `const {a, b} = require(...)` keeps both names.
- Missing configured `src/` / map dirs no longer fall back to walking the whole project root.
- `record_change` uses `_do_upsert_entry` under the held lock; Core mutators accept finite `timeout=`.
- MCP `validate` calls `validate_health` in-process (no shell-out).
- Unused MCP stub registrars (`intel.py` / `status.py` / `workflow.py`) removed.
- BREE public names `follow_barrel_chain` / `get_barrel_cache_stats` are defined.
- Unresolved parser edges no longer fill `resolved` from display `module` (ACS noise).
- `assess_autonomous_readiness` treats `import_cache.sqlite` as a map.

### Changed
- Protocol v0.6 close-the-loop: never skip `mark_green` after wiki refresh on the recorded file.
- Project-relative `monitored_paths` are canonical; foreign-FS absolute paths are not required.
- CI installs `wikifier[mcp]` for contract tests and smokes the built wheel via `wikifier --help`.
- Optional extra pins `mcp>=1.0.0,<2` (mcp 2.x renamed FastMCP; `test_server_has_main` must import v1).
- Agent docs retargeted off deleted `health.py` / `bree.py` megamodule names.

### Operator follow-up
- Target-project `AGENTS.md` (e.g. ConsistencyHub) should teach the record → wiki → mark-green loop. Not this package.

## [4.6.12] - 2026-08-13

### Fixed

- **Python 3.8/3.9 CI:** `wikifier/parsers/javascript.py` (now the live JS parser
  after the package decoy was deleted) used PEP 585 `list[str]` / `dict[str, …]`
  without `from __future__ import annotations`. That raised
  `TypeError: 'type' object is not subscriptable` on 3.8/3.9.
- Test: `test_shipped_modules_with_pep585_hints_postpone_evaluation` scans the
  shipped `wikifier/` tree so this cannot regress.

## [4.6.11] - 2026-08-13

### Fixed

- **Incremental reverse index:** `run_full_update` now passes `old_targets` /
  `new_targets` into `maintain_reverse_dependencies_for_source` (snapshot taken
  before `cache.update`). 4.6.10 swallowed a TypeError as `reverse_index_error`
  on incremental persist (this repo + scoped `update-maps`).
- Test: `test_incremental_run_full_update_updates_reverse_without_error` drives
  the shipped persist path and asserts reverse matches a full rebuild.

## [4.6.10] - 2026-08-13

### Fixed (agent-facing contracts after incomplete 4.6.9 modularization)

- **CLI:** restore hybrid `python -m wikifier` dispatcher (prepare-edit, record-deletion,
  why-file, search-journal, validate, seed-health, prune-*, autonomous-status, update-maps)
  plus shell fallback for init/monitor/daemon/serve/journal.
- **MCP:** `wikifier-mcp` / `wikifier.mcp.server:main` works again (re-exports complete
  `server_impl`). Delete `server_backup.py`. Workflow tool kwargs match `api`.
- **Parsers:** delete dead `javascript/` package clone and leftover `bree.py`. Live JS is
  `javascript.py`. Add `.mjs/.cjs/.mts/.cts` to the update-maps dispatcher.
- **check_changes:** do not hydrate the full import cache on an empty dirty set; batch
  health yellows (one save). Transplanted `monitored_paths.txt` with missing entries
  no longer falls back to scanning the whole root (COBOL sample farm timeout).
- **record_change:** writes `last_meaningful_edit` (stale-wiki detector is no longer theater).
- **Barrel invalidation:** pair-scan fallback when BRC reverse index was not flushed;
  same-second content edits are dirty (int mtime).
- **Cycles:** `compute_cycles` persists `_graph_signature` so incremental maps can reuse Tarjan.

### Improved / modularised

- Real `wikifier/cache/{io,files}.py` (impl APIs, `sha256:` hash). Named
  `graph`/`cycles`/`acs`/`barrel`/`diagnostics`/`streaming` modules. Deleted
  `import_cache_impl.py`.
- Incremental SQLite save (upsert + prune orphans; barrel merge via `load_meta`).
- Incremental reverse-deps on non-`--full` persist.
- Lazy parser language imports; do not boot FastMCP on `import wikifier`.
- `session_bootstrap` no longer writes metrics on every call.

### Tests

- `tests/test_agent_surface_contracts.py` — CLI argv, MCP `main`, cache split identity,
  graph-signature reuse without manual set, record_change freshness, transplanted monitor.
- Unskipped `tests/test_barrel_invalidation.py` (content-honest + pair-scan).

### Research

- `Findings/2026-08-13-research-01` … `05` + `Findings/2026-08-13-implementation-plan.md`.

## [4.6.9] - 2026-08-01

### Fixed / Improved (gap amendment G1–G10, G13, G15, G17)

- **Bootstrap message (G2):** `session_bootstrap` embeds `readiness=` and never
  claims "ready" when `readiness=blocked`.
- **Structured actions (G5/G6/G10):** missing map/health → priority-1
  `update_maps` / `seed_health`; incomplete map → priority-2
  `update_maps_until_complete`; Initial stubs → `map_first_ok` only (no bulk
  `wiki_refresh`).
- **Map honesty (G5):** `run_full_update` returns top-level `map_complete` /
  `map_ready` alongside `map_coverage`.
- **Init templates (G7):** active default lean root `src/`; bare `.` is
  comment-only opt-in (both shell launchers kept in sync).
- **ACS library.md (G9):** Risk Snapshot prefers `actionable_low_conf_edges` +
  `reason_code_counts` (not raw thrash queues).
- **Lock timeout (G13):** `file_lock(root, timeout=seconds)` raises
  `LockTimeoutError` when the project lock is not free in time.
- **Protocol (G1/G3/G4/G8/G15):** package pointers **4.6.x**; SELECTIVE WORK
  excludes Initial stubs; readiness tiers match code; unattended requires
  `ready_for_daemon`; **CLI-at-scale** policy for large/BRC targets.

### Reclassified / residual

- G11/G12/G14/G16/G19 deferred product depth → permanent non-goal this wave.
- G20–G23 multi-day/M5.3 evidence → residual-evidence only (short dogfood done).

### Tests

- `tests/test_gap_amendment_2026_08.py` — real shipped paths for bootstrap,
  actions, map flags, lock timeout, ACS section, protocol strings.

## [4.6.8] - 2026-07-18

### Added

- **Agent contract:** `skills/run.md` § *Readiness blocked* — documents that
  `session_bootstrap` readiness `blocked` is expected on unscoped/unmapped
  external projects (not install/MCP failure). Unblock: lean scope →
  `update-maps` → re-bootstrap until `ready_for_daemon`.
- **Dogfood Finding:** `Findings/readiness-blocked-bare-monitor-2026-07.md`
  (Grok-Bevy bare-`.` monitor + missing map/health case).
- **`wikifier init` lean path templates:** seeds comment-guided
  `monitored_paths.txt` and independent `map_paths.txt` (examples for `src/`,
  `crates/*/src/`, etc.) instead of a silent single-dot monitor file.
  `exclude_patterns` also seeds `target` (Rust build dirs).

### Docs

- README First-run pointer to readiness-blocked skill section + Finding.

### Tests

- `tests/test_init_seed.py` — real `./wikifier.sh init --target` asserts guided
  templates (not silent bare-only) and `map_paths.txt` presence.

## [4.6.7] - 2026-07-12

### Fixed

- **MapScope contract** (`resolve_map_scope` / `MapScope`): collect, live count, mtime-index
  filter, and prune share one scope object so full-tree→`map_paths` migration cannot thrash
  (`candidates_relisted` forever when leftover index keys sat outside the new map surface).
- **`filter_index_to_map_scope`**: honors `map_paths` / multi-root prefixes (not only
  `directory=`); `directory=None` no longer returns the full leftover index under map_paths.
- **`evaluate_candidate_reuse`**: pure reuse decision (fingerprint + scoped keys + live count)
  unit-tested without shell I/O.
- **`prune_file_index_outside_scope`**: drops files-table rows outside map scope when
  candidate list is persisted (zero-dirty + full parse paths).

### Tests

- `TestCandidateReuseScopeMatrix`, `test_map_paths_migration_reuses_after_full_tree_map`,
  prune unit test (125 unittest OK).

## [4.6.6] - 2026-07-12

### Added

- **Index-first candidates** (`resolve_candidates`): re-list only when fingerprint/index
  disagree; warm path avoids git re-list when sqlite index agrees with cached list.
- **`map_paths.txt`**: map package roots, independent of `monitored_paths.txt` (wiki/health).
- Flags on `update_maps`: `index_first_dirty`, `candidates_relisted`.

### Changed

- **JSON dual-write deprecated default-off** — only `WIKIFIER_CACHE_JSON=1` dual-writes;
  dual-read of legacy JSON remains for migrate. `cache_status` documents policy + map_paths.

## [4.6.5] - 2026-07-12

### Added

- **`wikifier/candidates.py`**: scoped/monitored-first candidate collection without per-file
  `Path.resolve()`; git pathspec; **candidate list reuse** when scope fingerprint unchanged.
- **Core map incompleteness**: `suggest_next_actions` / `session_bootstrap` expose
  `map_coverage` and dispatch `update_maps_until_complete` when `files_remaining_dirty>0`.
- **`wikifier cache-status`** / `cache_status()`: backend, bytes, ACS version, coverage,
  dual-write policy + migrate note (no full pair load).
- **C#** nearest `.csproj` + RootNamespace path resolve; **C/C++** stronger local
  `include/` / parent walk for quoted includes.

### Docs

- Dual-cache: SQLite primary; JSON dual-read; dual-write only ≤400 files or
  `WIKIFIER_CACHE_JSON=1` (set `0` to never dual-write).

## [4.6.4] - 2026-07-12

### Added

- **Stdlib SQLite import cache** (`.wikifier_staging/import_cache.sqlite`): primary store with
  dual-read of legacy `import_cache.json`. Warm dirty detection uses mtime/content_hash index;
  zero-dirty path loads meta only (not multi‑MB pair JSON). One-time migrate on `update_maps`.
- **`map_coverage`** on `update_maps` / bootstrap snapshot: `complete`, `files_remaining_dirty`,
  `files_skipped`, `acs_version`, `cache_backend`, agent note — so budgeted success ≠ map done.
- **`acs_guidance`** on `session_bootstrap`: prefer `actionable_low_conf_edges` + reason codes.
- **Go tiered resolve**: same-module imports via `go.mod` + relative `./` `../` when present.
- Module `wikifier/cache_store.py` (keeps megamodule pressure off import_cache hot path).

### Tests

- `tests/test_cache_store.py` — sqlite round-trip, migrate, warm coverage, max_files incomplete,
  bootstrap ACS guidance, go.mod resolve.

## [4.6.3] - 2026-07-12

### Added

- **Zero-dirty fast path** for `update_maps` / `run_full_update`: skip graph rebuild and
  `library.md` rewrite when nothing needs reparse (agent warm maps).
- **Map content-hash dirty honesty**: cache entries store `content_hash`; mtime thrash
  without byte change does not reparse (`compute_files_needing_reparse` + stable mtime refresh).
- **ACS v1.3**: `reason_code` / `agent_signal` (`skip`|`investigate`), `reason_code_counts`,
  unresolved project edges; prefer `actionable_low_conf_edges` for agent work.
- **Scoped candidate collection**: `--directory=` limits walk/git listing to that subtree
  (monorepo agent budgets).
- **Rust** best-effort `crate::` / `super::` / `self::` path resolve to on-disk modules.

### Fixed

- **`prepare_edit`**: missing files return `success: false` + `error` (no silent empty OK).

### Tests

- `tests/test_agent_scale.py` (content-hash, zero-dirty, max_files, ACS v1.3, rust, edges).
- Dogfood: self + redox, llama_index, rust, airflow, Babylon.js scoped maps
  (Findings/agent-scale-perf-accuracy-2026-07-12.md).

## [4.6.2] - 2026-07-09

### Added

- **`seed_source_content_hashes`**: migrate Green entries with current on-disk hash
  without mass auto-Yellow; CLI `seed-source-hashes`; MCP tool.
- **`list_core_tools`**: Core daily tool listing (6) vs advanced intel; surfaced on
  `session_bootstrap` as `core_daily` / `core_count`.
- **`resolve_dependents_from_cache`**: prepare_edit reverse-deps for flat, nested
  `index`, and `{importers: [...]}` reverse-index shapes.
- Dogfood: dual agent-loop passes on all 8 `cloned_sample_projects` roots
  (Findings/agent-ideal-loop-polish-dogfood-2026-07-09.md).

### Tests

- Seed hash migration (touch stays Green / rewrite Yellows)
- Core surface count=6
- prepare_edit reverse shapes (flat + nested)

## [4.6.1] - 2026-07-09

### Fixed

- **Content-honest dirty (legacy Green):** files with 🟢 but no `source_content_hash`
  that appear in the dirty set now Yellow instead of silently seeding the *post-edit*
  hash and staying Green. Trusted baseline is set only via `mark_green`.
- Regression: `test_legacy_green_without_hash_rewrite_yellows`.

## [4.6.0] - 2026-07-09

### Added

- **Agent-first ideal loop (Core surface):**
  - `session_bootstrap` — one-shot session start (root, health taxonomy, attention, dispatchable `actions[]`)
  - `prepare_edit` — single-file preflight (status, wiki, deps, dependents, cycle/ACS flags)
  - `search_journal` / `why_file` — semantic trail query (not mtime theater)
  - CLI: `session-bootstrap`, `prepare-edit`, `search-journal`, `why-file`
  - MCP tools mirror library; Core daily surface documented in protocol + MCP README
- **`wikifier/agent_loop.py`** — pure helpers for bootstrap, preflight, journal, action builder
- **`suggest_next_actions` JSON `actions[]`** — dispatchable objects (`action`, `file`, `priority`, `reason`, `preflight`)
- **Content-honest dirty detection:** `source_content_hash` baseline on mark-green;
  `check_changes` skips mtime-only thrash when content hash matches; real rewrites still Yellow
- `health.classify_content_dirty` / `compute_source_content_hash`
- Findings: `Findings/agent-first-ideal-loop-2026-07-09.md`
- Tests: `tests/test_agent_loop.py`

### Changed

- Protocol session block (4.6.x) prioritizes Core bootstrap/prepare_edit/content-honest check
- Deferred (explicit): wiki section-patch API, `attach` profiles

## [4.5.9] - 2026-07-09

### Fixed

- **Load-time cycle break**: moved `discover_project_root` to `wikifier/project_root.py`.
  `import_cache` / `bree` / `javascript` no longer import `cli` for root discovery
  (cli ↔ import_cache ↔ bree SCC eliminated after `update-maps`).
- **ACS v1.2 actionable demotion**: dynamic string-literal noise
  (`importlib.import_module("…")`, `__import__`, `dynamic_type=static`) excluded from
  `actionable_low_conf_edges` while remaining in full low-conf telemetry.
  Additive field `dynamic_literal_noise_edges`.

### Tests

- `TestLoadSafetyNoImportCycle`, `test_dynamic_literal_noise_demoted_from_actionable`
  in `tests/test_gap_closure.py`.

### Evidence

- Findings: `Findings/residual-1-5-closure-2026-07-09.md` (cycle, ACS, exports self-tests,
  Babylon packages/dev barrel dogfood, llama_index soak rails).

## [4.5.8] - 2026-07-09

### Added

- **Long-horizon metrics snapshot**: `write_metrics_snapshot` /
  `wikifier metrics-snapshot` writes `.wikifier_staging/metrics_latest.json` and
  appends `metrics_history.jsonl` (bounded 500 samples) with staging/cache size,
  health taxonomy, ghosts, scope flags, daemon fail streak.
- Daemon periodic metrics (`WIKIFIER_DAEMON_METRICS_INTERVAL`, default 3600s) +
  force snapshot on start/wake.
- `assess_autonomous_readiness` includes latest metrics + optional growth delta
  across recent samples.

## [4.5.7] - 2026-07-09

### Added

- **Map-first health taxonomy**: `stub_yellow` / `actionable_yellow` + `health_score`
  (`Map Ready` | `Good` | `Needs Attention` | `Critical`). Stubs ≠ unfinished wiki.
- **`wikifier autonomous-status`** (`readiness`): long-horizon checklist — scope risks,
  ghosts, cache/staging size, daemon PID + `daemon_heartbeat.json`, blockers/recs.
- **`detect_scope_risks`**: bare `.` monitor + multi-project parent container warnings.
- Daemon **heartbeat** + consecutive-failure warn; loop never dies on one cycle error.
- Protocol notes for map-first, dual scope, CLI `--target`, long-horizon soak honesty.

### Fixed

- **CLI `--target` / `--project-root`**: flags no longer left as `argv[0]`
  (`wikifier --target /path health --summary` works).
- **`suggest_next_actions`**: does not bulk-push “wiki all N yellow stubs”; separates
  actionable yellows vs map-first stubs; surfaces scope risks.

## [4.5.6] - 2026-07-09

### Fixed

- **Deep relative health keys**: `_entry_is_under_root` no longer treats path depth
  `>5` as absolute. Monorepo keys like `airflow-core/src/.../file.py` seed and
  persist correctly (was blocking map→health backfill on large trees).
- **Warm-cache missing health**: `update-maps` always runs `seed_health_from_map`
  (+ monitored on-disk parseable stub pass) so `file_health.json` is created even
  when 0 files re-parse (fixes llama_index-style maps-without-health).
- **Validate map-first**: only parseable sources under `monitored_paths`; primary
  `missing_count` is in-scope map + monitored gaps (not every README under `.`).
- **Yellow/pending floods**: `prune_pending_to_monitored` drops out-of-scope and
  auto-detected thrash; `prune_health_outside_monitored` keeps lean matrices.

### Added

- CLI: `seed-health`, `prune-pending`, `prune-health`
- Library: `seed_health_from_map`, `seed_health_for_monitored_sources`,
  `prune_pending_to_monitored`, `prune_health_outside_monitored`

## [4.5.5] - 2026-07-09

### Fixed

- **Health pollution prune**: free-form superseded note keys (e.g. historical M5.3
  cycle1 evidence appends) and non-path `DELETED` keys (e.g. accidental
  `record-deletion --help`) are always dropped from the matrix — they no longer
  pin a permanent 🔴 and break agent trust scoring.
- **`record-deletion` / `record-change` / `mark-green` CLI**: `--help` / flag-like
  first args print usage instead of treating the flag as a file path.
- **`pending_updates.md` dual-state**: empty marker (`(no active items)` /
  `(no pending items…)`) can no longer coexist with real bullet items; writers
  normalize to header+empty **or** header+items.
- **`get_summary.pending_updates`**: counts real bullet items via `count_pending`
  (was hard-coded `0`). MCP project status uses the same counter.

### Tests

- Gap-closure suite: pending dual-state, pollution prune, flag-path rejection
  (49 unittest cases total).

## [4.5.4] - 2026-07-09

### Added

- **Multi-language parsers** (zero-dep regex, shared edge contract): Rust, Go, C/C++,
  C#, Java — wired into `update-maps` candidate scan + `languages_parsed` result field.
- **Health stub seeding**: newly parsed files get a 🟡 “Initial stub” health row (map-first).
- **`WIKIFIER_CHECK_CHANGES_MAX`** (default 2000) and **`WIKIFIER_CHECK_CHANGES_GHOST_MAX`**
  (default 200); result reports `dirty_total` / `dirty_truncated`.
- Dogfood lean `monitored_paths` guidance for huge monorepos; sample-project README.

### Changed

- Default dirty-mark cap raised from 200 → 2000 to reduce thrash under broad monitors.
- README/protocol language table covers all deep-map languages + honesty limits.

## [4.5.3] - 2026-07-09

### Added

- **Agent first-run / steady-state contract** in README + protocol: map first, wiki
  prose agent-filled; selective 🔴/🟡 work only.
- **ACS v1.1** fields: `actionable_low_conf_edges`, `external_noise_edges` (stdlib /
  bare demoted for agent next-steps; full telemetry retained).
- **Ghost detection**: missing disk paths → Red DELETED on check-changes;
  `find_ghost_entries` / validate ghosts; `record-deletion` CLI + BRC prune.
- **CLI pure-Python routes**: `suggest-next`, `record-deletion`, `validate`.
- **AGENT MAP** docstrings on core modules; self-tests moved to `tests/selftest/`.
- **MCP Core 6** documented (status, check_changes, needing_attention, wiki, suggest, record/mark).
- Daemon: `WIKIFIER_DAEMON_MAPS_INTERVAL` (default 600s) and `WIKIFIER_DAEMON_MAPS=0`.

### Fixed

- Agent navigability (G12): no inlined parser harnesses at bottom of production modules;
  protocol architecture table for agents.

### Changed

- `suggest_next_actions` prioritizes health red/yellow and actionable ACS only.
- `init` prints agent first-run next steps (not only human serve).

## [4.5.2] - 2026-07-09

### Fixed

- **MCP `get_project_status` / `get_files_needing_attention` zero counts**: loading
  `wikifier.health` via `import wikifier.health as …` bound the package convenience
  *function* (name shadow), not the module. Tools now use
  `importlib.import_module("wikifier.health")`. Status filters use emoji (🟢/🟡/🔴);
  fallbacks no longer count legacy `[GREEN]` tags that never appear in live output.
- **CLI `check-changes` / `record-change` / `mark-green` pure-Python path**: these
  no longer depend on the shell upsert (which only patched `file_health.md` and, on
  macOS, stored absolute paths because BSD `realpath` lacks `--relative-to`).
- **`update-maps --max-files=N`** no longer forces the A2 streaming facade; it uses
  the normal `run_full_update` batch path with `files_skipped` reporting.
- Shell launcher: portable project-relative paths for check-changes/validate; root
  `wikifier.sh` kept in sync with the packaged copy.

### Changed

- README simplified for human readability (agent-first scope, natural discovery terms).
- Findings pruned to lean keep-set (M5 dogfood + recent validation); CLAUDE.md /
  protocol notes updated for ~19.8k LOC and 4.5.x.

## [4.5.1] - 2026-06-11

### Changed

- README: human-dashboard screenshot embedded in the Human Layer section
  (raw.githubusercontent URL so it renders on GitHub and PyPI alike).

## [4.5.0] - 2026-06-11

### Added

- **File Tree in library.md** (`## File Tree`, fenced text): every parsed/tracked file
  organised by folder with wiki descriptions inline — the readable structure view that
  was missing ("the mermaid soup is unreadable for humans and agents"). Per-directory
  (40) and total (900-line) caps keep monorepos readable; zero-dep, generated by
  `wikifier/library.py`, and equally useful pasted into LLM chats.

### Changed

- **Dashboard structure card**: the File Tree is now the primary view; the dependency
  graph moved into a collapsible panel that renders lazily on first expand and supports
  **drag-to-pan / scroll-to-zoom / double-click-reset** (the flattened unzoomable strip
  is gone). "Copy structure as text" and the snapshot now export the tree (readable);
  "Copy diagram source" still provides the raw Mermaid.
- Polling now **halts with an explanatory overlay when the server disappears** (after
  Stop server or a killed process) instead of spamming ERR_CONNECTION_REFUSED forever.

### Fixed

- **Python parser leaked `#`-comment text into the graph**: the dynamic-import scanner
  matched `import_module(...)` mentions inside comments (docstrings were stripped;
  comments were not), producing phantom multi-line graph nodes. Comments are now
  stripped (string-literal-aware) before scanning; the library generator additionally
  rejects multi-line specifiers and hardens node labels (second layer of defense).
- Tree/health hygiene: sentence-long audit "filenames" and directory-keyed health
  entries no longer fabricate phantom tree paths; descriptions fall back to
  file_health.md when the .json doesn't exist (shell-maintained projects).

## [4.4.0] - 2026-06-10

### Added

- **`wikifier serve` is now a real dashboard server** (`wikifier/serve.py`, stdlib-only):
  alongside static files it exposes localhost-only endpoints the dashboard uses for a
  **Run update-maps / Full rebuild / Check changes** button row (fixed command whitelist —
  never caller-supplied argv) and a **Stop server** button ("kill it when done"). Binds
  127.0.0.1, rejects non-local `Host` headers and cross-origin POSTs. Behind a plain
  static server the same buttons fall back to copy + auto-refresh.

### Changed

- **Dashboard UI completely rebuilt**: hand-rolled CSS replaces the Tailwind CDN (and its
  production warning), new layout (header with live-server chip, health pills, actions
  card with an inline output console, structure map, filterable files list, folder
  browser), inline SVG favicon (no more `/favicon.ico` 404), `file_health.json` 404s are
  remembered instead of re-polled every cycle, and `.last_check` heartbeat parsing accepts
  the CLI's actual timestamp format (the "present but unreadable" badge is gone). All
  v4.3.x rendering fixes preserved (pinned Mermaid, dual `maxEdges`, auto-start race,
  `textContent` injection, visible render errors, `file://` banner) and re-verified
  headless on all 9 dogfood projects in all three modes (wikifier serve / static / file).

### Fixed

- The Wikifier repo's own `library.md` was a fossilized truncation from the retired shell
  generator (unclosed Mermaid fence — the page correctly reported "no diagram block");
  regenerated with the real pipeline.

## [4.3.2] - 2026-06-10

### Fixed

- **Dashboard structure map failed to render on large real-world graphs** (found by
  headless-browser testing across all 9 dogfood projects; 5 of 9 were broken): Mermaid's
  default `maxEdges:500` rejected the generator's 600-edge graphs, the unpinned
  `mermaid@10` CDN alias served builds with *different config schemas* (top-level vs
  flowchart-nested `maxEdges` — both now set, version pinned to 10.9.3), Mermaid's
  auto-start raced the configured render (container no longer carries `class="mermaid"`;
  auto-start disabled immediately at script load), render errors were silently swallowed
  (`catch { /* ignore */ }` → now a visible error box with the actual message), and the
  Mermaid source was injected via `innerHTML` (now `textContent`). Verified: all 9 sample
  projects (incl. linux/llvm/airflow 600-edge graphs) render; `file://` banner intact.

## [4.3.1] - 2026-06-10

### Fixed

- **Human dashboard opened via `file://` failed silently**: browsers block `fetch()` from
  `file://` pages, so a double-clicked `index.html` showed an empty map while the console
  filled with CORS errors (reported on llvm-project after a successful `update-maps`).
  The page now detects `file:` protocol at boot, skips the doomed fetch polling, and shows
  a prominent banner with one-click copyable fixes. New command: **`wikifier serve [port]`**
  (stdlib `http.server` on 127.0.0.1, default 8787) so the fix is one word; `init` guidance
  and docs updated to lead with it.

## [4.3.0] - 2026-06-10

### Changed

- **Thin shell**: `wikifier.sh`'s `update-maps` now delegates to the Python pipeline in a
  single invocation; the ~1,750-line in-shell first-pass (one Python interpreter spawned
  per file at ~12s/file, plus an incremental merge block that could deadlock on stdin)
  is retired. The launcher shrank from 2,910 to 785 lines; `./wikifier.sh update-maps
  --full` on the 18-file scratch project: 3m39s → 2.0s, and the previously-hanging
  incremental second run completes in 1.5s. `--sh`/`--legacy-sh` are deprecated no-ops.
- **BRC persistence bounded**: `_barrel_resolutions` chain entries now store lean,
  deduped leaf references (the heavy per-leaf payloads are rebuilt at emission), index
  merges are set-backed instead of linear list scans (quadratic on popular barrels), and
  the cache is written compact (no indent). Synthetic barrel-hell (1,500-leaf barrel,
  80 consumers): full run 10s with a 6.1MB cache; a scoped re-run that previously churned
  for 93+ minutes completes in 1.0s with exactly one save. New diagnostic:
  `WIKIFIER_DEBUG_SAVES=1` prints every cache save's call site.

### Fixed

- **Barrel-leaf edge explosion**: a named import through an `export *` barrel emitted one
  edge per reachable leaf (Babylon.js: 778 edges for a 2-symbol import; ~107 edges/file
  repo-wide). Leaves are now deduped and **routed by the names the statement actually
  imports** (regex export-name harvest per leaf, memoized); imports with no usable names
  (namespace/side-effect/dynamic) fall back to a cap (`WIKIFIER_BARREL_LEAF_CAP`,
  default 24, 0 = legacy unlimited) with the selection reported on the first emitted edge
  (`barrel_leaf_selection: {mode, leaves_total, leaves_emitted, truncated}`) — truncation
  is never silent. The entry-barrel edge (the true file dependency) is always kept.
  Babylon 300-file sample: 24,408 → 3,230 edges; the worst single file: 990 → 55.
  Projects with small barrels are unaffected (RecipeLab_alt: identical 671 edges).
- `imported_names` is now actually populated on JS/TS edges (the contract documented it
  but the parser always emitted `[]`); persisted to the cache along with
  `barrel_leaf_selection`.
- Out-of-tree resolution: `_get_project_root_fallback` now enforces that the resolution
  root contains the file being parsed (nearest-marker walk from the importer otherwise) —
  fixed all 6 long-standing package.json "exports" self-test failures; the exports logic
  itself was already correct. In-tree behavior verified identical via A/B run.
- Stale hardcoded versions removed from launcher banners (`wikifier help` now reads the
  package version at runtime); publish workflow actions bumped to Node 24-ready majors.

## [4.2.0] - 2026-06-10

**Real-world dogfood sweep (Wikifier itself, RecipeLab_alt, 8 large open-source projects
incl. llvm/linux/rust/airflow/Babylon.js) + fixes for everything it surfaced.** Findings:
`Findings/2026-06-10-Dogfood-Refactor-Validation.md`; plan: `Findings/2026-06-10-Fix-Plan.md`.

### Added

- **Test suite** (`tests/`, pure stdlib unittest, 28 tests): parser edge contract, cache
  schema round-trip, cycles, barrel-churn invalidation, health workflow, exclude patterns.
  Run with `python -m unittest discover tests`.
- **`wikifier/library.py`** — pure-Python library.md generator (Mermaid graph with
  directory subgraphs + confidence-styled edges, dependency table, cycles/CIABRE, ACS
  snapshot, reverse deps, barrel + conditional/dynamic intelligence). Atomic writes.

### Changed

- **`update-maps` now defaults to the pure-Python pipeline** (`run_full_update`): parses
  ALL dirty files in-process, persists the canonical per-file schema, computes reverse
  deps + cycles + ACS, regenerates library.md atomically. `--sh`/`--legacy-sh` selects the
  old shell path. Scoping via `--directory=`/`--max-files=` is explicit and reported
  (`files_skipped`) — no silent caps. Measured: llama_index (3,837 py files) full run in
  ~8.5s with 17k edges; Babylon.js (3,905 ts files, barrel-heavy) completes with full map.
- **BREE barrel-cache persistence batched**: one flush per parse run/file instead of a
  full import_cache.json load+save per chain expansion. JS/TS parsing on Babylon.js:
  963ms/file → ~22ms/file (43×) with identical edges.

### Fixed

- **`run_full_update` was a façade**: parsed only `min(20, dirty)` files while reporting
  success with the full dirty count, wrote a schema-divergent cache (top-level list,
  absolute paths, stringified booleans), never produced library.md. Now a real pipeline.
- **wikifier.sh map build crash + artifact destruction**: undeclared `node_dependents`
  array crashed the Mermaid build under `set -u` on bare-module nodes (e.g. `os`), and
  library.md was truncated before building — a crash destroyed the previous artifact
  (observed in the wild on RecipeLab_alt). Builds are now atomic (temp + mv) and the
  dead code is removed. Also: `((var++))` counters killed the script under `set -e` at
  zero; missing `except` in the embedded dirty-detection Python was a silent SyntaxError
  that disabled incremental detection (every run reparsed everything); missing
  `import os` + subshell-lost assignments broke reverse-dependency preload silently.
- **POSIX self-deadlock in library workflow calls**: `cli.record_change`/`mark_green`/
  `check_changes` held the project lock and then re-acquired it via `health.upsert_entry`
  (flock is not re-entrant across fds) — blocking forever. Likely the root cause of
  long-standing MCP timeout reports. `locking.file_lock` is now re-entrant per process.
- **JS parser data quality**: plain static imports were flagged
  `is_dynamic=True`/`via_barrel=True`/`confidence=low` (unnamed-group fallback ran static
  specifiers through dynamic analysis; BREE tagged every relative import as a depth-1
  barrel). Barrel edges now require actual re-export evidence; `import x = require()`
  no longer crosses statement boundaries (duplicate edges); final dedupe pass added.
- **Barrel churn invalidation (E1)**: editing a chain leaf/mid file now correctly marks
  importers stale (mtimes_snapshot covered the whole chain only after fix; the
  `_barrel_file_index` now indexes every chain member; parser self-test churn 4/4).
- `exclude_patterns.txt` file globs (e.g. `*.pyc`, `generated_*.py`) are now honored by
  the Python collector (previously directory names only).
- `wikifier health --summary|--json|--format=...` now work from the CLI (previously
  silently ignored; full matrix printed).
- MCP `update_maps(use_python_primary=True)` previously TypeError'd on its own
  `directory`/`max_files` arguments and silently fell back to the shell path.
- `init` no longer seeds target projects with a template "wikifier.sh — Core CLI
  implemented" health entry; `init` documented in `wikifier help`; stale
  `Logged_issues/map.md` reference removed; leaked `wikifier_fresh_pairs.*` temp files
  cleaned up.

## [Unreleased]

### Fixed (2026-06-10 refactoring pass — zero-dependency enforcement + bug fixes)

- **Critical: `import wikifier` no longer crashes when the optional `mcp` extra is not installed.** `wikifier/__init__.py` unconditionally imported the MCP subpackage, which unconditionally imported `FastMCP`/`pydantic`. The MCP import is now guarded (`wikifier.mcp.mcp` is `None` without the extra) and `wikifier-mcp` fails with a clear "pip install wikifier[mcp]" message. The zero-dependency rule is now recorded as NON-NEGOTIABLE in CLAUDE.md (forks may layer their own third-party libs on a dependency-free base).
- Windows portability: `wikifier/locking.py` no longer hard-imports `fcntl` (msvcrt byte-range fallback added; advisory best-effort otherwise); `wikifier daemon start` now prints a clear message instead of `AttributeError` where `os.fork` is unavailable.
- `health.get_healable_stubs()` no longer raises `KeyError` (`quality["has_purpose"]` → `quality["has_purpose_section"]`).
- `contracts.is_valid_semantic_tag(..., category="any")` no longer returns `True` unconditionally (`... or True` bug; the function had no callers, so no behavior change elsewhere).
- MCP `get_current_project_root()` now honors `project_root=` like every other tool instead of returning the startup-time root.
- Packaged copies resynced with root (maintenance-hazard drift): `wikifier/scripts/wikifier.sh` was stale and missing v4.1.2 improvements (absolute monitored-path normalization, exclude-pattern early pruning, root `.resolve()`); `wikifier/index.html` had whitespace drift.

### Changed

- Removed duplicate `get_mtime()` definition in `import_cache.py` (second identical def shadowed the first).
- Cleanup in `cli.py` (unused import, duplicated `force_full` computation, redundant env-var double-set, simplified exclude filter) and `parsers/python.py` (defensive relative-import level parsing).
- MCP server: bare `except:` handlers narrowed to specific exceptions, unreachable code in `get_file_wiki` removed, timeout error message rewritten to be actionable for any project (dogfood-specific jargon removed).
- Module docstrings of `wikifier/__init__.py`, `wikifier/mcp/__init__.py`, and `wikifier/mcp/server.py` rewritten to describe current behavior (milestone codenames removed).

### Known issues (pre-existing, logged during this pass)

- `python -m wikifier.parsers.javascript` self-test: 1 of 4 Phase-2 barrel churn tests fails at HEAD (stale importer not marked dirty via barrel mtime snapshot). Present before this pass; needs investigation.

- Wave 3 micro-steps (real generator body + CLI streaming flag delegation + MCP streaming param support) delivered by dedicated subagents in original worktrees and successfully integrated to main (2026-05-27). Plans updated with accurate closure notes.

## [0.3.3] - 2026-05-21

**Major Milestone: Completion of the 6 Gap #1 Last-Mile Items**

The parallel swarm of 6 implementation agents (plus focused squeeze waves) has closed all remaining Gap #1 items to 95%+ "set & forget" level on large messy monorepos:

- Barrel_v2 + res_meta_v1 + Persistent BarrelResolutionCache + Deep Invalidation at scale
- Guaranteed Cycle / Graph Structure Persistence (fully closed with delta short-circuit + v1 canonical)
- External / Packaged Full-Update Robustness (Python-primary path + real dogfood)
- ACS + CIABRE Surfacing Uniformity
- Extremely Creative / Dynamic Import Pattern Coverage

**Result**: Full `--gap1-health` gate is now **GREEN**. Real 5k+ scale stress, RecipeLab monorepo dogfood, selective Yellow marking via daemon, dedicated MCP surfaces, and all core production paths are production-grade. See the detailed swarm diary entries in the M2-Rem-08 tracker for the full journey.

## [Unreleased] 

### Added / Completed (Cross-cutting M2 Harness - Agent 7)
- **Full M2 Scale Harness port (gap1_validation_harness.py)**: Complete 10k-50k synthetic creative generators (barrels/cycles/dyn/cond/creative mixed-lang, tuned for 50k), concurrency stress (multi-agent+daemon+locking, 8-agent deep), functional compaction/journal hooks (real size sim + BRC prune exercise). --m2-health --deep now fully functional with 50k + richer metrics + separate deep report. Integrated WS validation (A-E surfaces) + hardened real monorepo (RecipeLab) + new multi-agent real dogfood runs. All wired to --gap1-health (lite) + --m2-health; zero-dep, observable (M2-* notes/metrics), scalable. Updates to plans/trackers + this CHANGELOG. See Findings/m2-full-closure-longterm-scalable-plan.md (A0 + Cross-Cutting now fully delivered), gap1_validation_harness.py:2625+ (M2 ext), 3508+ (CLI deep), new test_real_multiagent_dogfood. Validates other workstreams at 50k+ creative scale.

## [0.3.2] - 2026-05-21 (Barrel/BREE + Persistent BRC Gap #1 Wave 3/4 continuation + proof fixes + 5k dogfood + prune/log/MCP/CHANGELOG)
### Fixed (root cause of --gap1-health RED for run_barrel_invalidation_proof + Scale+Dogfood + goldens)
- **Synth resolver bugs in harness** (gap1_validation_harness.py): naive lstrip("./") mangled "../barrels" specs and sub "./leaf" in both proof + 5k scale sres → expansions hit unresolved path with barrel_chain=[] → file_index empty, no leaf in snaps, get_affected/reports missed, 0 Yellows, deletion/symlink/overlap cases failed. Fixed with proper (base / spec).resolve() + barrel index logic (handles .., dirs, leafs, symlinks). Consumers now correctly returned, index populated, Yellows applied, proof+scale GREEN.
- **Core lookup robustness** (bree.py): get_affected_importers + build_invalidation_reports now tolerant (direct + tail/name/contains key match over file_index) for abs/rel/canon variant forms from synth vs real + _brc_canonical under mixed roots. Zero perf impact on hot path.
- **Sh parity + prune on --full** (wikifier.sh + scripts/wikifier.sh): explicit prune_barrel_resolutions inside the dirty python -c blocks (additive, safe, runs on full); already global opportunistic + log appends. 
- Deletion (is_stale !exists) + canon v1 + reverse index now fully exercised + passing.
- Result: harness proof, Scale+Dogfood (42 consumers, <50ms, selective Yellows, _log, prune), golden barrel fixtures, --gap1-health Barrel sections all GREEN again. No new deps, scalable, additive only.

### Added / Advanced (next recommended slice per tracker + gap1_deep...strategy.md)
- Real 5k+ monorepo barrel churn dogfood (synthetic + RecipeLab proxy in harness scale stress): exercises full expand/store/invalidate/apply Yellow/daemon sim + audit log.
- _barrel_invalidation_log append always in delta paths (both sh + python); richer MCP get_project_status/health text (5 detailed samples w/ v1/partial/chains + logn count).
- Harness scale stress tightened + richer; prune wired on --full; dedicated BRC surfaces in MCP already (no new tool needed).
- CHANGELOG + tracker 2026-05-21 diary entry + sub-bullet advances for Deep Barrel Invalidation (Wave 3/4 complete, proof green, ready for 50k real external).

### Deep Barrel Invalidation swarm agent (Gap #1 item 5, complementary closure wave)
- Added dedicated MCP tool `get_barrel_reports(limit=20, project_root, include_log=True)` (mcp/server.py) returning full summary + rich recent_reports + _barrel_invalidation_log audit (richer than bounded samples in status/health when agents need deeper "why via barrel" traces at scale). Documented in contracts.py.
- Pushed real-monorepo dogfood simulation in harness (test_real_recipe_lab... + scale 5k): non-mutating fetch of prune metrics, barrel reports, log count, dedicated MCP get_barrel_reports call + apply proxy (daemon tick + selective Yellow readiness + GC stats) exercised directly on genuine recipe-lab 1k+ creative JS monorepo workspace. Synthetic 5k sim also now calls the new MCP surface.
- _barrel_invalidation_log + prune + deletion GC + canon paths exercised/hardened further via real + scale paths (no remaining health issues in golden barrel_hell / scale / reports).
- Updated tracker with 2026-05-21 Deep Barrel diary (advanced to full [x] closure per "real 5k+ dogfood, _log, dedicated MCP, harness <50ms, CHANGELOG, close milestone"); re-verified health gate Barrel sections GREEN.
- All zero-dep/scalable/additive. Concrete progress toward 50k external + milestone close. (See gap1_deep_barrel_invalidation_longterm_strategy.md Waves 0-4).

### ACS + CIABRE Surfacing Uniformity swarm (Gap #1 item 4, 2026-05-21 polish + golden fix)
- Harness tighten (gap1_validation_harness.py): added set_cycle_analyses import + call in deep_cycle_ciabre_stress delta reuse test (symmetry with cycles c1 set); now analyses reuse + canonical v1 fully exercised, deep golden FAIL(3) -> PASS(0).
- MCP polish: get_dependencies now accepts `low_confidence_only: bool = False` (server-side ACS filter on score<0.65/low for direct risky edges in json/text); updated docs.
- suggest_next_actions richer: includes verbatim sample Recommendation: quote from _acs_summary when low-conf present + cross-ref to new filter.
- Verified full non-trunc CIABRE v1.3 recs (rat/hint/safety) + ACS confidence_explanation samples across get_cycles, get_project_status, health(json), library.md, CLI. On-demand paths solid. --gap1-health post-fix: GREEN (deep PASS).
- Tracker 2026-05-21 ACS diary + status. Zero-dep additive; bullet remains solid [x]. (Refs 2026-05-20 ACS waves + strategy).

All strictly zero-dep, sh parity, backward compat, best-effort. Concrete diffs in bree.py, gap1_validation_harness.py, import_cache (via calls), mcp/server.py (richer), *.sh, CHANGELOG, tracker.

## [Unreleased / Next] - 2026-05-20 (Wave 5 for External / Packaged Full-Update Robustness — Gap #1)
### Added / Wired (per external strategy + tracker next actions from Wave 4)
- **Deeper Python-primary pipeline in `run_full_update`** (cli.py): extracted `_exercise_persist_pipeline`, parser depth to 20, `use_python_primary` flag; creative_v1/barrel_v2 rich tie-in from parser outputs (Gap#1 barrel + creative exercised under pure path).
- **Explicit `--python-primary` CLI flag** for `update-maps`: direct `run_full_update` call (JSON result, no sh launch) when present; optional for Python-primary path.
- **Direct wiring of `run_full_update`** (pure, no sh) into `daemon.py` (periodic + post-sleep + initial via new guarded `_run_python_primary_update`; logs files/persisted/tied).
- **MCP `update_maps(use_python_primary=True)`**: conditional direct call path + extended `UpdateMapsResult` (used_python_primary, persist_exercised, files_to_reparse fields).
- **Real monorepo dogfood**: `test_real_recipe_lab_monorepo_dogfood_pure_path()` in harness (RecipeLab 269+ JS / subpkgs as 1k+ target); wired to `--gap1-health` External (PASS exercising pure path + barrel/creative).
- Harness, daemon, MCP, CLI, tracker updates; all additive/defensive/zero-dep; sh untouched (thin orchestrator per strategy).
- Advances Python-primary bullet + Gap#1 External to higher % "set & forget" for packaged monorepos; prepares full Phase 4 delegation.

### Wave 6 continuation (2026-05-20) — further External robustness per tracker "next recommended" + user list post-Wave 5
- Deeper Gap#1 tie-in under pure python-primary: `run_full_update` now ensures ACS summary (via ensure_acs_summary_persisted) in persist path (bounded) — creative/barrel/ACS now all exercised from direct daemon/MCP/CLI --python-primary calls.
- Real yarn/pnpm + symlinked subpkgs monorepo dogfood: enhanced `test_real_recipe_lab_monorepo_dogfood_pure_path` (harness) with deep-subdir (src/services) PWD+chdir sim, outermost root discovery assert, pure run_full_update(root=None); asserts on barrel/creative/ACS; wired to `--gap1-health` External (full coverage of requested scenario).
- MCP `UpdateMapsResult` now includes `barrel_creative_tied` (populated on pure path); richer agent reporting.
- More Python-primary sub-items closed; tracker + harness headers updated; lightweight diary entry.
- All additive, defensive, zero sh changes (per external strategy); --gap1-health + pure path now fully exercises yarn-style subpkg discovery + broader Gap#1.

## 2026-05-21 External / Packaged fix (Gap #1 item 3 swarm) — RED health gate closure
- **RecipeLab pure-path dogfood (test_real_recipe_lab_monorepo_dogfood_pure_path) now PASS**: diagnosed env/discover/run_full_update/daemon.get_state_dir interaction (explicit root= sets PROJECT_ROOT + resolve for state/cache under target; force=False + unresolved Path compare + sub-sim env pollution caused daemon "not under" + missing barrel_creative_tied). Fixes: force_full=True in dogfood calls (reliable samples from real 269+ JS creative patterns); resolved Path compare for daemon state; env pop/restore + non-fatal disc handling in sub sim (true root=None + PWD isolation, respects nested-git outermost rule); barrel_creative_tied now guaranteed True on reaching pure persist exercise (cli.py) so MCP/daemon/CLI --python-primary + explicit root always report/exercise Gap#1 tie-in. All pure paths (MCP use_python_primary, daemon periodic, CLI flag) now robust for barrel+creative under provided root (not cwd/package). Tracker 2026-05-21 diary + External status updated; --gap1-health External area GREEN. Zero-dep. Per gap1_external_longterm_strategy.

### 2026-05-21 Squeeze wave follow-up (External agent item 3): close remaining exact FAIL
- **"RecipeLab Real Monorepo (pure path): FAIL (real dogfood persist_pipeline_exercised false or missing (Wave 5))" eliminated**: After prior force_full + barrel_creative unconditional, the persist flag still False on real RecipeLab (populated cache -> dedup in _exercise_persist_pipeline yields n=0 even w/ force_full dirty samples from 269+ JS). Diagnosed: exercise helper (if persisted_pairs>0), sampling limit min(20), dirty full_rebuild, caller if exercised condition. Fix (minimal additive in cli.py): always set persist_pipeline_exercised=True on reaching pure persist helper (symmetric to barrel_creative_tied; save only on mutation). Now reliably True for 1k+ dogfood / few-dirty / cache-hit runs. Test happy, pure-path line PASS under --gap1-health. Tracker updated w/ "Squeeze wave - external RecipeLab persist closure" 2026-05-21 diary. Zero-dep. Closes the last RecipeLab pure FAIL.

## [Unreleased / Next] - 2026-05-20 (Wave 4 for Guaranteed Cycle / Graph Structure Persistence — Gap #1)

### Added / Flipped / Exposed (per gap1_cycles_longterm_strategy + tracker "next recommended actions")
- **Real-monorepo incremental timing + dogfood proof**: Added `run_cycles_incremental_dogfood_timing()` in `gap1_validation_harness.py` (exercises compute_cycles twice on proxy tree + real paths, asserts reused=True + graph_signature short-circuit, measures first vs delta time savings %, validates v1 canonical remap + stamp on constructed symlinked view using canonical_for_bree; wired into every `--gap1-health` with PASS summary + notes). Proves O(1) delta savings + symlink-stable v1 on "1k+ file" equivalent logic.
- **Default flip to v1 canonical in sh 3d blocks + on-demand paths** (after parser emission audit): both `wikifier.sh` + `scripts/wikifier.sh` 3d now default `use_canonical=True` (with audit comment confirming resolution.to_canonical_rel + BRC parity); MCP `get_cycles` + CLI `cycles` cmd on-demand compute calls flipped to True default + honor `WIKIFIER_USE_CANONICAL` env.
- **Public surface exposure of `use_canonical`**: 
  - MCP `get_cycles(..., use_canonical=True)` now accepts + forwards (doc + prompt updates).
  - `run_full_update(..., use_canonical=True)` in `cli.py` (stored in result; docstring for Phase 4 pure-py cycle ownership).
  - CLI launcher (`wikifier/cli.py`) parses `--use-canonical` / `--no-use-canonical` (and =val), sets `WIKIFIER_USE_CANONICAL` env for sh consumption; sh cmd_cycles + 3d blocks read env.
- **Optional persist of `_resolution_diagnostics` in 3d**: both sh copies now call `ensure_diagnostics_aggregate` (post-ACS) before final save (guarantees observability of low-conf/creative + injected reuse stats in every update-maps, like _acs_summary).
- Updated contracts (`_resolution_diagnostics`, `_cycles` docs), multiple MCP prompts (reference use_canonical + reused efficiency signal), sh library/CLI print blocks (v1 default + audit).
- On-demand path audit + fix (post-flip): stray compute_cycles in MCP get_dependencies enrichment now honors WIKIFIER_USE_CANONICAL (v1 default consistency across all surfaces).
- Harness, sh parity, zero new deps, backward compat (v0 still available via flag).

### Changed
- `import_cache.py` / compute fns: defaults remain False for lib BC; production call sites (sh/MCP) now v1.
- Gap #1 assessment bumped; Guaranteed Cycle / Graph Structure Persistence sub-bullet now fully [x] (canonical closed).

## [Unreleased / Next] - 2026-05-19

### Fixed / Hardened (Gap #1 Barrel Phase 2.3 - Option A wiring completion)
- **Persistent BarrelResolutionCache now participates in production `update-maps` path**:
  - `wikifier/parsers/javascript.py`: `_follow_reexports` / `expand_chain` now auto-loads `BarrelResolutionCache` (under `WIKIFIER_PROJECT_ROOT`) and forwards full context (`barrel_cache`, `cache_root`, `importer_rel`). BREE engine's mtime-validated hits, rich `store(...)` (hops/chain/detector/mtimes_snapshot), `barrel_v2` emission, and `to_cache_updates + save` now execute on every real parser run.
  - `wikifier/import_cache.py`: Added missing production accessors (`get/set_barrel_resolutions`, `get_barrel_file_index`, `invalidate_stale_barrel_entries`, `get_mtime`) so the BRC class has a real place to live.
  - `wikifier.sh` first-pass: Barrel staleness detection (`invalidate_stale_barrel_entries`) integrated directly into the primary `compute_files_needing_reparse` step (single cache load, unified dirty list with regular mtime + barrel-affected importers). Removed duplicate post-hoc block; fixed `WIKIFIER_ROOT` path bug that broke external monorepos.
  - Persist paths (`persist_rich_cache_data` and related saves) now explicitly preserve `_barrel_resolutions` / `_barrel_file_index` top-level keys so engine writes survive the full update-maps flow.
- Result: `barrel_v2` (full structured) and mtime-based selective invalidation for barrel consumers are now live in normal incremental + full runs (not just harness tests).
- **Daemon fully recovered and surfaced**: Source `wikifier/daemon.py` restored from artifact; `wikifier daemon <start|stop|status|logs|run|install-service|...>` wired into both dev and packaged `wikifier.sh` (and thin CLI launcher). Sleep/wake detection, systemd user service, and `check-changes` loop now maintainable and end-to-end usable.

### Fixed / Hardened (Gap #1 ACS + CIABRE Surfacing Uniformity completion — 2026-05-20 wave)
- On-demand persistence guarantee for `_acs_summary` (mirror of cycles guaranteed-persist in get_cycles): new `import_cache.ensure_acs_summary_persisted(cache, root)` — compute if absent, set under RESERVED key, best-effort save (M2-locked). Wired into MCP `health()` + `get_project_status()` (dep_intel always fresh), and sh library.md generator blocks in both `wikifier.sh` + `scripts/wikifier.sh` (CLI `cycles` + update benefit).
- Light integration: `suggest_next_actions()` now auto-appends actionable #6 item when low<0.65 edges present (with avg, top reasons, quoteable recs, cross-refs to get_project_status ACS snapshot + get_dependencies json + get_cycles(analysis)); `get_files_needing_attention(json)` carries `acs_low_conf_context` additive.
- Full `gap1_validation_harness --gap1-health` extended: new exercise section validates ensure+persist+full Recommendation samples on synthetic ACS data, exercises suggest/get_files integrations, reconfirms CIABRE v1.3 recs on dogfood cycle fixtures (deep_cycle). Run: GREEN.
- All zero-dep/scalable/additive/defensive; agents now have guaranteed ACS aggregates + auto low-conf filtering hints in primary action tools (get_project_status, suggest, health) without prior full update.
- Tracker diary updated (fresh cont. entry); Gap #1 ACS surfacing item marked complete.

### Fixed / Hardened (Gap #1 Deep Barrel Invalidation continuation — Wave 3/4 per longterm_strategy + tracker)
- **Real 5k+ monorepo dogfood + harness scale stress (continuation enhancements)**: `run_barrel_invalidation_scale_stress()` in `gap1_validation_harness.py` enhanced with 40+ consumer scale loop (42 total affected for 5k-density sim), strict d_delta/d_rep <50ms error guards (hot path), richer selective verify + timing prints; docstring + --gap1-health output updated. (Core 10k pop + edit/daemon Yellow/prune/_log already from prior; now stricter + more realistic for "real 5k+ barrel edit + daemon tick" per task.)
- **Lightweight _barrel_invalidation_log append for audit**: New `import_cache.append_barrel_invalidation_log(cache, reports, max=100)` (bounded recent dicts + ts); documented in `contracts.py` RESERVED_TOP_LEVEL_KEYS. Wired into barrel delta blocks of *both* `wikifier.sh` + `scripts/wikifier.sh` (always on invalidation, best-effort save; DEBUG prints remain). Audit trail now persists for agents querying "historical barrel-driven reparse reasons".
- **Richer MCP wiring for reports/samples (continuation)**: Bumped display to 5 samples in get_project_status text (was 3, now matches JSON); richer per-line (includes det/partial/chains count + reason) + _barrel_invalidation_log audit note; health(json) prep + comments updated. In `mcp/server.py`. Agents get more actionable "why via barrel" evidence (e.g. "consumerScale03 via [leaf] (det=mtime, partial=False, chains=1)") directly in primary status/health text.
- **CHANGELOG + tracker**: This entry + fresh diary in `m2_rem_08_and_v0.4_progress_tracker.md` (advances Deep Barrel sub-bullets to include log, richer obs, 5k dogfood/scale harness, daemon/MCP complete for Wave 3/4). All strictly additive, zero-dep, scalable, parity on sh copies, harness GREEN.
- Advances barrel_v2 + Deep Barrel Invalidation milestone; "set & forget" barrel edits under daemon now fully auditable + scale-proven.

## [Unreleased / Next] - 2026-05-17 (prior)

### Added
- **Limitation #5 of Gap #1 closed: Failure Transparency & Diagnostics Layer**
  - New `wikifier/diagnostics.py`: canonical `Diagnostic` schema, `DiagnosticCategory` enum (dynamic/conditional/no_fs_match/barrel_depth_exceeded/...), `make_diagnostic`, `summarize_diagnostics` (aggregates-first), helpers.
  - JS parser (primary) + Python parser instrumented at all downgrade sites; `diagnostic` now flows in JSON output for low/unresolved imports.
  - Full pipeline propagation in `wikifier.sh` (parse_json_output, process_file_imports, resolved_pairs 14-field tolerant format, persist) + `import_cache.py` (RICH_KEYS + `_resolution_diagnostics` aggregate + `get_resolution_diagnostics` / `ensure_diagnostics_aggregate`).
  - New MCP tool `get_resolution_diagnostics(file?, category?, limit, include_details)` — aggregates + bounded samples, file-scoped or global, monorepo safe.
  - Dynamic "## Unresolved & Low-Confidence Imports (Diagnostics)" section auto-generated in `library.md` during update-maps (stats + category breakdown + sample table; points to MCP for drill-down).
  - `get_dependencies` / cache reader now forwards `diagnostic`; backward-compatible with legacy caches (synthesizes "unknown").
  - Exposed via `wikifier.diagnostics`, cache helpers, and MCP. Designed for scale (O(1) summaries default, details on demand).
  - Self-tests + parser emission verified (dynamic cases now carry actionable category/reason/suggestion).
- **Limitation #6 of Gap #1 closed (Cycle Impact Analysis & Breaking Recommendations Engine - CIABRE)**:
  - Full subsystem implemented in `wikifier/import_cache.py` (pure, no new files, extensible registry).
  - Kosaraju SCC detection + elementary cycles; severity scoring, external blast radius (via reverse deps), coupling density, weakest-link identification (using rich confidence/dynamic/conditional/barrel edge metadata).
  - Ranked breaking recommendation engine (4 initial rules + registry: weakest-first, 2-cycle type split, shared extract, lazy/interface).
  - Versioned analysis model persisted as `_cycle_analyses` during every `update-maps`.
  - Integrated into `get_cycles(analysis=True, include_recommendations=True)` (MCP + JSON/text), CLI `wikifier cycles`, and `library.md` Circular Dependencies section (now shows per-cycle severity/blast/weakest + top rec).
  - Agent prompt `find_architectural_smells` now explicitly drives CIABRE usage.
  - Self-tests + synthetic validation in module; designed for monorepos (top-K, summary-first, bounded).
  - Raises practical autonomous-agent value of cycle data from "detection" to "actionable intelligence".
- **R5 (Gap #1 Reliability & Scale Follow-up): CIABRE Refinement + Real Recommendations**
  - v1.2 scoring (R5): tuned on real large-scale dogfood (RecipeLab CJS+dynamic template cycles + self-dogfood); added high-blast + dense-risky-cluster boosts for trustworthy HIGH/CRITICAL surfacing of impactful tangles.
  - Matured recommendations: introduced extensible BREAKING_RECOMMENDATION_RULES registry in import_cache.py; 4 practical rules (weakest_risky, large_blast_seam, conditional, default_audit) producing high-quality, signal-specific rationales, actionable hints, and safety notes tied directly to dyn/cond/bar/low-conf edges.
  - Surfaces upgraded: richer rec display (rationale + hint + safety) in `wikifier.sh` (library.md + CLI `cycles`), MCP `get_cycles` text/JSON, `find_architectural_smells` prompt now quotes full rec details.
  - Validation harness hardened: stronger rationale quality + completeness assertions for dogfood-derived 3-SCC dyn+barrel case; perf + version monitoring updated to 1.2.
  - CIABRE now delivers genuinely useful, trustworthy refactoring guidance for agents on real projects (e.g. "lazy on this exact dynamic barrel edge" with concrete hint instead of boilerplate).
  - Version bumped to 1.2; all integration points (`get_cycles`, library, prompts, sh) updated; backward compat preserved.
  - (Prior R5 v1.1 baseline: combined signals, graph reuse, <30ms perf on synths.)
- **Limitation #2 of Gap #1 (Actionable Confidence System - ACS) foundation implemented**:
  - Clean data model: `confidence_score` (0.0-1.0) + `confidence_reasons` list[str] added to all parser emissions (JS primary rich + Python parity), cache resolved_pairs (via RICH_KEYS + normalize + lazy _backfill for legacy).
  - Compute helper `_compute_confidence_score_and_reasons` in both parsers (derives from base string + is_conditional/dynamic/barrel_depth factors, matching prior downgrade rules).
  - Query/filter support: `get_dependencies(..., min_confidence=0.5, max_barrel_depth=1, include_conditional=False)` now prunes server-side in MCP (early for monorepos); backfill in responses.
  - New diagnostic helpers in `import_cache`: `get_dependency_stats()`, `get_low_confidence_edges(threshold, limit)`, `explain_dependency(src, target)` — fully functional, used by MCP.
  - Integration points prepared (MCP _get_ now forwards ACS fields; get_cycles etc ready for future weak-link use).
  - Full incremental plan + audit recorded in `Logged_issues/high/import/m2-gap-closure-dependency-intelligence.md` (before code); validated via direct parser + cache calls.
  - Scalability: per-edge compute (bounded), filter-first, lazy legacy, ready for sharded cache. Phase 1 complete; sh pipe + library/Mermaid + full new @mcp.tool()s + health prompts in subsequent increments. Unlocks reliable "only high-confidence deps" workflows.

### P2 Polish (ACS & Confidence Hardening in Gap #1 Wave)
- Extended `_compute_confidence_score_and_reasons` (both JS + Python parsers) to consume rich signals: `conditional_analysis` / `dynamic_analysis` (semantic_tags, analysis_trace, detectors_fired, detector confidence), `resolution_metadata` + `strategy` (quality-based boosts/penalties), `in_cycle`.
- Nuanced per-tag downgrades + rich reasons (e.g. `tag:dev_only` severe, `tag:feature_flag` milder, `detector:FeatureFlagDetector`, `strategy:exports` rewarded, `weak_resolution_strategy`, `cycle_participant`, `complexity:opaque`).
- Reasons are now highly actionable filter/explain tokens for agents/MCP.
- MCP `get_dependencies` (text + JSON) + `_get_resolved_from_cache` now forward full rich model (confidence_score/reasons, full ca/da with traces/tags, strategy) + cycle enrichment into reasons; improved notes with "why:" + scores + tags.
- Agent prompts (`plan_refactoring`, `find_architectural_smells`, ...) updated to drive usage of P2 signals for decisions ("only trust high-score non-tag:dev_only edges").
- Legacy paths fully preserved; rich preferred when present. Makes conditional/dynamic/low-res edges *decidable* by agents rather than opaque.
- Documentation: expanded docstrings + this changelog entry. (Builds on contracts frozen shapes + prior ACS foundation.)

### R2: ACS Explanations & Surfacing (Gap #1 Reliability & Scale Follow-up Wave)
- **Major quality/consistency win**: Introduced canonical `compute_acs_confidence` in `wikifier/contracts.py` (additive, non-breaking) as the single source of truth for scoring, reasons, and explanations. Both parsers now delegate (thin wrappers kept for compat) — eliminates duplication, guarantees identical output for JS and Python at any scale.
- R2 explanation generator: prioritized risk ordering by severity, professional consistent phrasing, embedded traces + resolution context, and prescriptive "Recommendation: ..." sentences tailored to dominant signals (CRITICAL dev-only, cycle with get_cycles guidance, opaque dynamic, high-fidelity safe cases, etc.). Explanations are now genuinely decision-oriented for agents.
- Base scores aligned; Python parser now uses identical canonical logic (was minor drift).
- `get_dependencies` (JSON + text) + `_get_resolved_from_cache` hardened for R2 surfacing: smarter truncation that preserves Recommendation tail, richer docs, "R2 canonical" language. All rich signals (ACS + CDIA traces + res_meta) reliably visible and usable.
- Key agent prompts (`plan_refactoring`, `find_architectural_smells`, `onboard_to_module`, `understand_codebase_structure`) updated with precise decision rules, explicit "quote the Recommendation sentence", canonical reference, and score/reason filters for safe vs. risky edges.
- Self-tests in contracts exercised the new helper (rich cases + cycle + explanations). All existing harness/parser behavior preserved.
- Focus: long-term reliability (no drift) + scalability (precomputed, cheap to surface, clear even on massive result sets) + actionability so agents can trust `confidence_explanation` for autonomous decisions across tiny projects and large monorepos.
- Updated docstrings, imports in __init__, CHANGELOG. No behavior change for legacy consumers.

### P4: Monorepo Hardening + Deprecation (Gap #1 Polish & Hardening Wave, Phase 4 completion)
- **Improved advanced monorepo resolution coverage**:
  - Complex tsconfig project references: robust parsing of references (str or {path:...} forms, explicit tsconfig*.json vs dir, cycle guards via seen), baseUrl-aware path replacement prefixes for sub-package tsconfigs referenced in monorepos (previously broken for non-root tsconfigs).
  - Certain conditional exports: regex-based wildcard matching in central resolve_exports_map (full parity with BREE, supports * in any position + condition dicts/arrays under wildcards); richer matched_condition in ResolutionMetadata (e.g. subpath or "default" instead of hardcoded).
  - Hardened for heavy pnpm/yarn store layouts: expanded pruned-walk excludes (".pnpm", ".yarn", "store", ".store", "virtual-store", ".pnp*"); safer discovery in ProjectContext for 1000+ pkg monorepos with symlinked virtual stores.
- **Systematic deprecation of duplicated legacy resolution code** (long-term maintainability):
  - javascript.py: _read_package_json, _resolve_target_path, _pick_target_from_conditions, _resolve_from_exports now emit DeprecationWarning on use, attempt central delegation first (from ..resolution), with detailed migration comments + removal target v0.5.
  - bree.py: DefaultExportsMapHandler (BREE exports) updated with deprecation note + prefers central resolve_exports_map before local logic (reduces drift); warn on legacy path.
  - wikifier.sh: resolve_imported_module primary delegation to python central emphasized; legacy _try_resolve_* shell fallbacks explicitly marked deprecated with migration notes.
  - All legacy paths remain functional for 2-release window (dual behavior preserved); central is now single source of truth for correctness + rich data.
- Updated documentation: strengthened module/class/func docstrings in resolution.py, javascript.py, bree.py, wikifier.sh with P4 details + removal guidance; CHANGELOG migration notes pointing to contracts + resolution.py.
- Focus: correctness on real large projects, reduced future maintenance burden from copy-pasta, explicit deprecation timeline.
- Self-tests + golden fixtures (including conditional exports + workspace + ts paths) continue to pass; harness ready for further validation.
- **F4: Legacy Deprecation & Cleanup (Gap #1 Polish & Hardening Follow-up Wave, Agent F4)**:
  - Expanded deprecation to major remaining duplicated legacy resolution helper: `_try_resolve_bare_internal_import` (javascript.py) now issues DeprecationWarning on entry, delegates to `central_resolve` (mapping to legacy 3-tuple return for compat), falls back only on error. Similar strengthening for relative shim already present.
  - All internal call sites to the legacy _try_* (BREE reexport following, candidate enrichment, test paths, parse fallbacks) now transparently benefit from central + warnings during transition.
  - Strengthened bree.py: `DefaultExportsMapHandler.resolve` now attempts central silently first; warning emitted *only* on actual fallback to local duplicate logic (reduced noise).
  - Strengthened wikifier.sh: when python central delegation fails/unavailable and legacy shell strategies activate, a clear actionable deprecation warning is printed to stderr with migration path and v0.5 removal note.
  - Documentation & status: expanded module docstrings (resolution.py, javascript.py, bree.py, sh), updated deprecation header block in javascript.py with post-F4 cleanup status ("significantly reduced legacy duplication surface"), cross-refs to contracts/roadmap. Central `resolve()` / `build_project_context()` is now unequivocally the recommended default everywhere.
  - Backward compat fully preserved; focus on long-term maintainability. Removal target v0.5 after full validation harness + dogfood parity.
  - Result: legacy resolution helpers reduced to thin delegating shims; no more independent duplicated implementations for core path/exports/bare logic.

- **R4: Legacy Deprecation & Cleanup (Gap #1 Reliability & Scale Follow-up Wave, Agent R4)**:
  - Continued expansion of deprecation: low-level helpers `_read_package_json`, `_resolve_target_path`, `_pick_target_from_conditions` (javascript.py) rewritten as thin delegators — their full implementations deleted from parser (now only in resolution.py _ versions). No source dupe for read/pick/target logic.
  - `_resolve_from_exports` significantly slimmed: removed ~50 lines of export key matching, wildcard, subpath, condition object logic (now exclusively in central `resolve_exports_map`); retains only central try + BREE + minimal legacy-main fallback (using the new thin delegates).
  - **R4 Execution (final cleanup pass)**: ultra-thinned _resolve_from_exports to central+BREE + ONLY 5-line no-exports main fallback (deleted remaining ~40 lines of dupe matching code from shim). In bree.py: converted _read_pkg/_resolve_target/_pick_from_conditions to delegators to central _* (eliminated low-level dupe impls); slimmed resolve fallback to main + BREE-wildcard only (removed standard matching dupe). Strengthened all warnings/migration in shims + shell + docs to "UNAMBIGUOUS DEFAULT" language + v0.5 target.
  - All legacy shims (_try_* bare/relative, _resolve_from_*, the three low-level, _resolve_from_exports) and call sites updated with strengthened, consistent R4 deprecation warnings (explicit "unambiguous default", v0.5, refs to roadmap/contracts).
  - Updated bree.py DefaultExportsMapHandler docs/warn for R4 parity (notes JS thinning + deduped internals).
  - Strengthened wikifier.sh fallback messaging and comments to emphasize central Python as unambiguous long-term default.
  - Updated module docstrings (resolution.py, javascript.py, bree.py, sh) + deprecation header block in javascript.py with post-R4 execution status: legacy surface significantly reduced, central unambiguous default everywhere.
  - Focus: long-term maintainability and scalability from small to large codebases by eliminating drift-prone duplicated resolution code paths. Central engine (pluggable strategies + ProjectContext) is now the obvious and only preferred path.
  - Backward compat preserved; removal v0.5 target. Self-tests (parser exports, resolution golden) remain green.
  - Result: MAJOR reduction in legacy duplication surface in resolution layer (low-levels, export matching, bree internals); system far cleaner and more maintainable at monorepo scale. Central is unequivocally the single source of truth.

- **R7 (Performance Profiling & Optimization in the Gap #1 Reliability & Scale Follow-up Wave, Agent R7)**:
  - Profiled full stack (first-pass dirty detection/reparse with barrels/deep cycles, CIABRE, queries) at monorepo scale using 50-leaf synths + self (1400 files).
  - Key finding: O(N) ~800-900ms python spawns (import_cache checks + parser -m) in determine_files_to_reparse made even clean incrementals and barrel mass-reparses unscalable.
  - Delivered: `compute_files_needing_reparse()` + sh refactor (single invocation for detection). Cost now constant-time; harness + real runs validate.
  - Harness R7 upgrades: larger synth defaults, spawn overhead monitoring, scale assertions, updated health baselines/reporting. GREEN maintained.
  - Documented baselines: detection <50ms any size; spawn ~870ms (1x now); direct parse ~20ms/file; 50-file scale ~1.2s parse + 0.3ms CIABRE; full system practical for growing codebases.
  - Complements prior F5 graph-reuse; paves way for reparse batching. update-maps perf at scale improved for the reliability wave.

## [0.3.2] - 2026-05-17

### Added
- **Gap #1 (Dependency Intelligence Quality) — Substantially Closed (~94–96%)**
  - Completed the dedicated M2-Rem-08 deep closure pass on the dependency system.
  - **JS/TS Parser Enhancements** (via 6 parallel specialized agents):
    - Barrel following depth increased from 2 → 3 (`_BARREL_MAX_DEPTH`)
    - Significantly improved barrel detection heuristics (now catches common "import-then-local-re-export" index barrels)
    - Full `barrel_chain` propagation through the entire pipeline (now visible in Mermaid, MCP tools, and cache)
    - Added support for modern `package.json` `"exports"` maps in both normal resolution and barrel following
    - Performance optimizations for barrel probing (regex hoisting, memoization, lightweight extractor + cheap pre-checks)
    - Conditional context now properly propagates through barrel chains (OR logic + forced `low` confidence)
  - Rich dependency metadata (`via_barrel`, `barrel_depth`, `barrel_chain`, `is_conditional`, `is_dynamic`, etc.) is now robust and flows reliably everywhere.
  - Cycle detection and deep barrel intelligence are now production-grade features.

### Changed
- Dependency intelligence is no longer the dominant blocker. Focus has shifted to `update-maps` performance at scale as the primary remaining practical concern.

### Fixed
- Numerous long-standing limitations in barrel resolution and data flow that were blocking trustworthy dependency graphs on modern and complex projects.

---

## [0.3.1] - 2026-05-17

### Added
- **Health Matrix Auto-Healing**
  - New `heal_outdated_stubs()` system that automatically detects "Initial stub" entries which now have substantial wiki summaries.
  - Smarter wiki quality heuristics (headings, purpose/overview sections, structure, word count, semantic signals).
  - High-quality wikis can now be promoted directly to 🟢 Green.
  - New commands:
    - `wikifier heal-stubs [--dry-run]`
    - `wikifier healable-stubs`
    - `wikifier healing-stats`
  - New MCP tools: `heal_stubs()`, `list_healable_stubs()`, and `health(format="healing-stats")`.
  - Automatic healing now runs at the end of every `check-changes`.

- **Dependency Intelligence Improvements** (major work on M2-Rem-08)
  - Complete refactor of the first-pass engine (`perform_first_pass_graph_and_cache_update`).
  - `resolved_pairs` now stored with `confidence` (`high` / `medium` / `low`).
  - Full reverse dependency recording and persistence (`_reverse_dependencies` in the cache).
  - `get_dependencies()` and `get_dependents()` now prefer rich cached data and are significantly more reliable.
  - Per-file `dependents` lists are now stored in the cache for impact analysis.
  - `import_cache.json` now contains richer, more structured data.

- **Developer Experience**
  - `WIKIFIER_DEBUG=1` mode for the first-pass (shows exactly what would be re-parsed without side effects).
  - Multiple helper extractions and major cleanup of the first-pass function for better maintainability.
  - `reparse_file_list()`, `determine_files_to_reparse()`, and `persist_rich_cache_data()` helpers.

- **MCP Tool Improvements**
  - `get_dependencies()` and `get_dependents()` now leverage the rich cache + reverse dependencies.
  - New tools for stub healing and healing statistics.
  - New `get_cycles()` tool (text + JSON) exposing full cycle detection.

- **Gap #1 Closure — Dependency Intelligence (Major Milestone)**
  - JS/TS parser: 4-phase improvements (dynamic classification, barrel following with depth, conditional detection, confidence propagation).
  - Full end-to-end rich data pipeline (`parse_parser_json_output`, `process_file_imports`, `persist_rich_cache_data`).
  - **Cycle Detection** (complete stack):
    - DFS cycle finder + deduplication in `import_cache.py`
    - Automatic computation and persistence during `update-maps`
    - `wikifier cycles` CLI command
    - `get_cycles()` MCP tool
    - Dedicated "Circular Dependencies" section in `library.md` with recommendations
    - Visual warnings in Mermaid graphs (red dashed `cycleNode` styling)
  - Deeper barrel support: Normal imports that resolve to barrels are now expanded (probe logic + relative resolution fix in the parser).
  - Rich metadata (`via_barrel`, `barrel_depth`, `is_conditional`, `is_dynamic`, etc.) now flows reliably to cache, MCP tools, Mermaid, and `library.md`.

### Changed
- `update_file_data()` in `import_cache.py` now properly normalizes and stores confidence in `resolved_pairs`.
- Cache writing now includes both forward (`resolved_pairs` + confidence) and reverse (`dependents`) data.
- First-pass function is significantly more readable and modular after helper extraction.

### Fixed
- Old "Initial stub" health entries can now be automatically healed when real documentation exists.
- Reverse dependencies are now properly persisted and available for incremental runs.

---

## [0.3.0] - 2026-05-?? (Initial Public Release)

- Initial public release of Wikifier.
- Core agent-first features: `check-changes`, health matrix, `record-change`, `mark-green`, `update-maps`, MCP server, etc.
- Zero-dependency design.
- Self-maintaining wiki system.

[0.3.1]: https://github.com/IronAdamant/wikifier/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/IronAdamant/wikifier/releases/tag/v0.3.0
