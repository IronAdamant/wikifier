# Wikifier Agent Protocol v0.6

**Formerly "Wikifier Skills & Commands". This is the authoritative, versioned specification for agent behavior when using Wikifier.**

**Version**: v0.6 (v4.2.0 real-pipeline + reliability update; package current **4.6.x**, live `__version__` in `wikifier/__init__.py`)  
**Date**: 2026-06-10 (package notes refreshed 2026-08-01; gap-closure contract 2026-07-09)  
**Status**: Active. Supersedes v0.5.  
**See also**: `README.md`, `Findings/gap-closure-report.md`, `Findings/gap-amendment-plan-2026-08-01.md`, and the library in wikifier/.

**Package 4.6.x + gap-closure notes (additive; protocol still v0.6):**
- File Tree + `wikifier serve`; MCP status/attention use library + emoji (not `[GREEN]` tags).
- **First-run:** `init` → lean `monitored_paths.txt` + `map_paths.txt` (default active root `src/`, not bare `.`) → `update-maps` → `health --summary` → `suggest_next_actions`. Map is automatic; wiki *prose* is agent-filled over time.
- **`session_bootstrap` readiness:** message embeds the readiness tier. `blocked` is not a crash — see **§ Readiness blocked**. Hard blockers = missing map/health (or severe ghosts). Bare `.` monitor alone → `map_ok_scope_risk` when map+health exist (scope warnings / fix_scope), not the same tier as missing map. Unattended ops require **`readiness=ready_for_daemon`**, not `health_score=Map Ready` alone.
- **Map-first ≠ wiki-done:** `health_score` **Map Ready** + many 🟡 *Initial stubs* means structural coverage only. Do **not** bulk-wiki stubs. Wiki a file when you edit it, then `mark-green`. Prefer `actionable_yellow` / 🔴 over raw yellow counts.
- **Steady-state selective work:** only 🔴 and *actionable* 🟡 (never re-wiki 🟢; never bulk-wiki Initial/map stubs). **ACS v1.3:** use `actionable_low_conf_edges` + `reason_code_counts` / `agent_signal` (`skip`|`investigate`). Do **not** thrash on raw `low_conf_edges` (includes external/bare scores ~0.48). Prefer `map_coverage.complete` / `map_ready` / `files_remaining_dirty` after budgeted `update-maps` — `success: true` ≠ map complete.
- **Warm maps:** SQLite primary; zero-dirty uses mtime index + meta. **Index-first:** re-list candidates only when fingerprint / map-scoped index / live count disagree (`index_first_dirty` / `candidates_reused` on `update_maps`). Prefer `--directory=` or `map_paths.txt` package roots (not bare `.`). Collect, live count, index filter, and prune share **MapScope** so full-tree→`map_paths` narrow does not thrash.
- **map_paths vs monitored_paths:** `map_paths.txt` = import-map package roots; `monitored_paths.txt` = wiki/health thrash bound. Independent. Wiki-only monitored lists do **not** define the map.
- **Cache ops:** `wikifier cache-status`. Dual-write JSON **deprecated default-off** (`WIKIFIER_CACHE_JSON=1` to opt in). Dual-read legacy JSON for migrate remains.
- **ACS:** prefer `actionable_low_conf_edges` + `reason_code_counts` / `agent_signal`; never thrash on raw `low_conf_edges` alone.
- **Dual scope:** `monitored_paths` = check-changes/health scope (keep lean). `update-maps --directory=` / `--max-files=` = map walk. Never set `project_root` to a multi-repo parent (e.g. `cloned_sample_projects`).
- **CLI target:** `wikifier --target /abs/project health --summary` (flags stripped before the command). Or `WIKIFIER_PROJECT_ROOT=…`.
- **Long-horizon:** `wikifier autonomous-status` (or `readiness`) before unattended runs; daemon writes `.wikifier_staging/daemon_heartbeat.json`. Soak ≥72h is still evidence work, not automatic.
- **Deletions:** `record-deletion` + ghost detection. **Languages:** py/js/ts/rust/go/c/c#/java (regex). journal/pending = audit queue, not Jira.
- **Huge monorepos:** lean `monitored_paths.txt` (not bare `.`). `WIKIFIER_CHECK_CHANGES_MAX` default 2000. Hygiene: `seed-health`, `prune-pending`, `prune-health`.
- **Monitor/daemon:** mtime heartbeat; agents still own wiki/mark-green. `WIKIFIER_DAEMON_MAPS_INTERVAL` default 600s; `WIKIFIER_DAEMON_MAPS=0` for check-only.
- Health module: `importlib.import_module("wikifier.health")` or `wikifier.health_module` — `from wikifier import health` is the *function*.

**v0.6 migration notes (packages v4.2.0–v4.3.0)** — changes are additive or strictly-better defaults; v0.5 agent behavior keeps working:
- `update-maps` (CLI) now runs the **pure-Python full pipeline**: every dirty file is parsed in-process, the canonical per-file cache is persisted, reverse deps + cycles + ACS are computed, and `library.md` is regenerated atomically. `--python-primary` is accepted but redundant; the in-shell first-pass was retired entirely (wikifier.sh's update-maps delegates to this pipeline; `--sh`/`--legacy-sh` are deprecated no-ops). Scoping is explicit via `--directory=`/`--max-files=` and reported in the result (`files_skipped`) — there are no silent caps.
- `run_full_update`/`update_maps` returns gained additive fields: `files_parsed` (actual), `parseable_files`, `edges_persisted`, `files_skipped`, `cycles`, `library`. Tolerate additive fields as always.
- `wikifier health --summary|--json|--format=...` now work from the CLI (previously library-only).
- A POSIX lock self-deadlock in library `record_change`/`mark_green`/`check_changes` was fixed (locking is now re-entrant per process). MCP timeouts on those tools should no longer occur; the CLI fallback guidance below remains valid as defense in depth.
- A stdlib-only test suite exists: `python -m unittest discover tests` (run it when working on Wikifier itself).

**Core design**: Token-efficient agent-to-agent wiki. Agents use it to look up files (health matrix + file wikis + BRC + stele chunks instead of full sources), autonomously update wiki summaries, and create new ones as work progresses. **It should not be used for anything more than that.** 

This protocol + the Python package + MCP server form the bridge for consistent, low-ambiguity agent operation on real external projects.

**This file + the `wikifier` Python package (`from wikifier import ...`) together form the M2/M3 bridge for consistent, low-ambiguity agent operation.**

**This file is the primary contract for any LLM or agent operating Wikifier.**

## Agent architecture (navigability — G12)

Do **not** open megamodules (`javascript.py`, `import_cache.py`, `bree.py`) to decide workflow. Use this map:

| Need | Use |
|------|-----|
| First-run map | `init` → lean paths (not bare `.`) → `update-maps` → `health --summary` → `suggest-next` |
| **Session start (4.6+)** | `session_bootstrap` (or CLI `session-bootstrap`) — one shot: root, health, attention, `actions[]`. If `readiness` is `blocked`, fix `actions[]` / `blockers[]` first (usually scope + maps). |
| **Unblock readiness** | Write lean `monitored_paths.txt` + `map_paths.txt` → `update_maps` (full once) → re-`session_bootstrap` until **`readiness=ready_for_daemon`** (not Map Ready alone) |
| **Core tool list** | `list_core_tools` / bootstrap `core_surface` — prefer Core 6; advanced is non-core |
| Steady-state | `check-changes` (content-honest) → edit 🔴/actionable 🟡 only → `record-change` → wiki → `mark-green` |
| **Hash migration** | `seed_source_content_hashes` / CLI `seed-source-hashes` — baseline Greens without mass Yellow |
| **Preflight edit** | `prepare_edit` / CLI `prepare-edit <file>` — wiki + status + deps + dependents (multi-shape reverse index) |
| **Why / journal** | `why_file` / `search_journal` — semantic trail, not mtime theater |
| Lookup Core | `session_bootstrap`, `check_changes`, `prepare_edit`, `suggest_next_actions` (json `actions[]`), `record_change`, `mark_green` |
| Advanced intel | `get_dependencies`, `get_dependents`, `get_cycles`, barrel/diagnostics — not daily Core |
| Deletion | `record-deletion` |
| Long-horizon prep | `autonomous-status` / `readiness`; then `daemon start` with lean monitor |
| Hygiene | `seed-health`, `prune-pending`, `prune-health`, `validate` |
| Code entry | `cli.py` + `agent_loop.py` + `health.py` + parsers — tests in `tests/` |

**Do not open megamodules** (`javascript.py` ~2.6k, `import_cache.py` ~2.3k, `bree.py` ~2k) for workflow decisions — use tools + this table.

**CLI pure-Python vs shell:** mutators and maps prefer `python -m wikifier …`. Shell still owns `init`, `monitor`, `daemon`, `serve`, `journal`.  
**Scope:** `monitored_paths` = change detection; `exclude_patterns` + optional `--directory` = map walk.  
**Human HTML** is secondary observation only.

## Readiness blocked (`session_bootstrap` / external projects)

When MCP `session_bootstrap` (or CLI `session-bootstrap`) returns:

```text
readiness: "blocked"
scope.ok: false
blockers: [ ... ]
actions: [ { "action": "fix_scope", ... }, ... ]
```

**this is expected on a project that has never been scoped/mapped**, not a Wikifier install failure.

### Readiness tiers (code truth — `assess_autonomous_readiness`)

| Tier | When |
|------|------|
| `blocked` | Hard **blockers[]**: no import map and/or no file_health (or severe ghost flood). |
| `map_ok_scope_risk` | Map+health present but **scope warnings** (often bare `.` monitor or multi-repo parent) and clean red/actionable yellow. |
| `ready_for_daemon` | Map Ready/Good **and** not bare_dot_monitor — only safe unattended tier. |
| `ready_with_agent_wiki_work` | Needs Attention, red=0 — daemon OK but agents still have wiki work. |
| `not_ready` | Other (e.g. reds). |

Bare `.` is a **scope warning** (`scope.warnings` / `fix_scope`), not always a hard blocker. Missing map/health **are** hard blockers and emit priority-1 `update_maps` / `seed_health` in `actions[]`.

### Why it happens (Grok-Bevy 2026-07 dogfood)

On **Grok-Bevy** (Rust workspace), first bootstrap reported:

| Signal | Field / tier | Meaning |
|--------|--------------|---------|
| `No import map (run update-maps first)` | `blockers[]` → `blocked` | No dependency/import map yet. Action: **`update_maps`**. |
| `No file_health` | `blockers[]` → `blocked` | Health matrix not seeded. Action: **`seed_health` / update-maps**. |
| `monitored_paths is bare '.'` | `scope.warnings` (often `map_ok_scope_risk` once map exists) | check-changes thrash risk. Action: **`fix_scope`**. |

Also: `bare_dot_monitor: true` and `scope.ok: false` until `monitored_paths.txt` lists **lean package roots**, not bare `.`.

### Fix once per project (agents must do this, not ignore blockers)

1. **Scope (wiki/health thrash bound)** — create/edit **`monitored_paths.txt`** at project root with *specific* dirs/files, e.g.:
   ```text
   crates/foo/src/
   crates/bar/src/
   README.md
   docs/
   ```
   Never leave only `.` on non-tiny trees.
2. **Map roots** — create/edit **`map_paths.txt`** (import-map package roots; independent of monitored):
   ```text
   crates/foo/src/
   crates/bar/src/
   ```
3. **Build map + health** — from the target project (or with `project_root=` / `WIKIFIER_PROJECT_ROOT=`):
   ```bash
   wikifier update-maps --full    # or MCP update_maps full=true
   # re-run session_bootstrap until readiness == ready_for_daemon
   ```
4. **Do not** bulk-re-wiki 🟡 *Initial stubs* after maps land — stubs = map coverage only.

After a successful fix, bootstrap looks like: `scope.ok: true`, `blockers: []`, `health_score: Map Ready` (stubs OK), **`readiness: ready_for_daemon`**. Map Ready without `ready_for_daemon` is **not** unattended-ready.

### Product note for Wikifier maintainers

- Default bare `.` is a footgun for real repos; agents must treat **`fix_scope` as P0** when scope warns bare-dot, and **update_maps/seed_health as P0** when readiness is `blocked`.
- **`wikifier init` (4.6.8+ / 4.6.9 templates)** seeds comment-guided lean templates with active default **`src/`** (bare `.` is commented opt-in for tiny toys only). Multi-crate / monorepo agents must replace with package roots before map-ready work.

See also: Findings note `Findings/readiness-blocked-bare-monitor-2026-07.md`.

## Mandatory New-Session Rule

**Copy this exact block into the system prompt or the very first instruction of every new LLM session that uses Wikifier:**

```
You are now operating inside a Wikifier-managed codebase (Agent Protocol v0.6 — package 4.6.x).

This is strictly an agent-to-agent wiki for token saving: map lookup (health + file wikis + deps) instead of full sources; selective wiki updates; not a human docs product or Jira.

SELECTIVE WORK (mandatory): Only update/remove/re-wiki 🔴 Red and *actionable* 🟡 Yellow files. Do **not** re-summarize 🟢 Green files, and do **not** bulk-wiki 🟡 Initial/map stubs (map coverage only — wiki a stub only when you edit that file). First-run builds the structural map; wiki depth is filled as you touch files. check-changes is content-honest (mtime-only thrash does not re-Yellow when source hash matches mark-green baseline).

FIRST ACTIONS:
1. Prefer MCP Core: session_bootstrap, check_changes, prepare_edit, suggest_next_actions (use actions[]), record_change, mark_green. Always pass project_root= for external projects.
2. CLI/library fallback:
     WIKIFIER_PROJECT_ROOT=/path/to/target python -m wikifier session-bootstrap
     python -m wikifier check-changes
     python -m wikifier suggest-next --json   # actions[] dispatchable
     python -m wikifier prepare-edit path/to/file
     ... edit only red/actionable yellow sources ...
     python -m wikifier record-change "path/to/file" "why (semantic). Include subid if agent work."
     ... update that file's wiki only ...
     python -m wikifier mark-green "path/to/file" "reason"
     if imports changed: python -m wikifier update-maps [--directory=src/]
     if file removed: python -m wikifier record-deletion "path" "why"
     python -m wikifier health --summary
3. Optional background: `python -m wikifier monitor` or daemon — you still own wiki + mark-green.
4. Prioritize 🔴 then actionable 🟡. Lookup greens via prepare_edit / get_file_wiki; do not rewrite them.
5. why_file / search_journal for semantic trail.
6. Always explicit project_root / WIKIFIER_PROJECT_ROOT for external/multi-project work.
7. End turn: health + suggest_next_actions (json).

Never skip record-change — semantic audit trail (journal + health + pending).

**M5+ notes (2026-06)**: 
- External projects: always explicit root. CLI is battle-tested fallback (M5.1 MCP reliability: 60s timeout + better errors; M5 dogfood on alt BRC exact named services, 79k llvm, etc.).
- Scope: token-efficient agent-to-agent wiki only (see README "Intended Use").
- Sustained: monitors + subagents for 72h+ gate (M5.3).
- See health matrix for current Green/Yellow state of M5 agent records (Progress, Assessment, etc.).
- Post-4.0.1 health hygiene (in wikifier/health.py): `_coerce_root` makes direct library calls robust with plain str roots (e.g. `health(".")` or `load_health(".")` now work without TypeError; used by agents/MCP consumers). `SUPERSEDED_PATTERNS` + prune keeps the matrix lean by dropping old superseded historical notes (e.g. early M5.3 "Cycle1" entries) while preserving explicit 🔴 Red "DELETED" audit records (intentional, observable for agents). Main health example: one such Red + unrelated mtime Yellows are normal.
```

**Packaging / External (M5 strengthened)**: After pip install, use global `wikifier` / `wikifier-mcp` or `from wikifier import ...`. For user projects: `WIKIFIER_PROJECT_ROOT=/abs/path/to/target wikifier ...` or pass project_root to every call/MCP tool. Bootstrap with `wikifier init`. Absolute paths in monitored_paths.txt required for externals. Python library + CLI preferred for reliability on large/BRC scale.

## Concurrency & Locking (M2-Rem-07)

Wikifier is designed to be used safely by multiple agents and humans at the same time (e.g. one background `monitor` + several LLM agents + occasional human edits).

### What is Protected
- `file_health.json` (and the generated `file_health.md`)
- `import_cache.json` (used by incremental `update-maps`)
- `pending_updates.md` (in most code paths)
- Journal entries (protected via a compatible mkdir-based lock in `write_journal`)

### How It Works
- Python-side operations (MCP tools, `wikifier.health`, `wikifier.import_cache`) use `fcntl.flock` via `wikifier/locking.py`.
- Shell fallback paths use a portable `mkdir`-based lock (the same technique already used by `write_journal`).
- A reusable helper `with_project_lock` exists in `wikifier.sh` for future critical sections.

### What Agents Need to Know
In most cases, **you do not need to think about locking**. The high-level tools (`record_change`, `mark_green`, `upsert_health`, `update_maps`, etc.) acquire the necessary locks automatically.

However, if you are doing low-level direct writes to Wikifier state files (e.g. manually editing `file_health.md`, `pending_updates.md`, or `import_cache.json`), you should be aware that concurrent access is possible and should prefer going through the official tools.

### Limitations (Final M2-Rem-07 Assessment)
- Locks are **advisory** — a broken or malicious process can ignore them.
- Currently **project-level** (one lock for the entire project). This is the right tradeoff for current needs (including heavy multi-agent + monitor dogfooding) and keeps the implementation simple and fast.
- **Finite timeout** is supported: `file_lock(root, timeout=seconds)` raises `LockTimeoutError` if the lock is not free in time (`timeout=None` still blocks). `is_project_locked()` remains a diagnostic non-blocking probe.
- Per-file / sharded locking is a permanent non-goal unless extreme concurrency pressure appears.
- Best-effort portability on non-Unix systems.

The locking system (Python `file_lock` + shell `with_project_lock`) is production-ready for the M2 scope.

## Protocol v0.4 Additions: I/O Contracts, Error Handling, Structured Output, Versioning

**All agents following this protocol MUST treat the Python library surface (see m2-full-closure-longterm-scalable-plan.md Workstream E) as the source of truth for I/O shapes when the package is importable.**

### Versioning & Compatibility
- Protocol versions are independent of package `__version__` but coordinated (v0.4 aligns with M2 closure library skeleton).
- Changes to mandatory I/O or error behavior require a new minor protocol version + migration notes here.
- Agents should tolerate additive fields in dict returns. Never hardcode exact key sets without "or newer" logic.
- Shell/MCP outputs remain supported as fallbacks but are secondary to library structured returns.

### Core I/O Contracts (Library Preferred)
All high-level functions accept:
- `project_root: Optional[str | Path] = None` (auto-discovers via hardened discover_project_root(); explicit for multi-project or daemon swarms)
- Scoping: `directory: Optional[str] = None` (prefix filter, e.g. "src/")
- `format: Literal["text", "json", "summary"] = "text"` where applicable

Key returns (structured dict primary; "success": bool always present on library paths):
- `check_changes(project_root=None) -> dict`: { "success", "project_root", "changes_detected": int, "message", "recommendation", "barrel_invalidation_summary", "rich_auto_yellow_via", "error"? }
- `record_change(file: str, reason: str, project_root=None) -> dict`: { "success", "file", "project_root", "reason", "message", "error"? }
- `health(project_root=None, directory=None, format="text"|"json"|"summary") -> str | dict`: json includes full entries + "dependency_intel" (acs_summary, etc.) for agent reasoning.
- `mark_green(file, reason="", project_root=None) -> dict`
- `suggest_next_actions(..., format="json") -> dict`: { "success", "red", "yellow", "suggestions": list[str], "health_summary", "acs_note" }
- `update_maps(..., directory=..., max_files=...) -> dict`: delegates to run_full_update — the real full pipeline (all dirty files parsed in-process, canonical persist, cycles/ACS/reverse deps, atomic library.md) + facade metadata.
- `run_full_update(...) -> dict`: { "success", "root", "mode", "parseable_files", "files_to_reparse", "files_parsed", "files_skipped", "edges_persisted", "cycles", "library", "dirty_sample", "persist_pipeline_exercised" (compat), ... }

Text formats are for human review only. Agents MUST request json/summary for machine use in loops.

Pending/journal/health side effects are observable via the returned messages + direct file reads (or health()).

### Error Handling Expectations
- **Operational failures** (e.g., partial scan on huge tree, lock edge): return `{"success": False, "error": "...", "project_root": "...", ...partial_data }`. Agent must handle gracefully and log; continue where safe.
- **Programming / contract errors** (bad types, missing required): raise (standard Python exceptions) — these indicate agent bug.
- **Locking**: Mutators block on project lock by default; optional finite `timeout=` raises on contention.
- Never assume text output parsability. Always use structured returns + explicit format="json".
- On external/packaged installs: discovery is robust; pass explicit project_root if cwd is ambiguous.

**Error Taxonomy (for conformance harness + agent robustness)**:
- Operational (partial, lock contention, scale bounds): success=False + "error" + partial + "project_root". Recoverable.
- Programming (type, missing arg, import of lib): raise Exception (agent code bug; do not catch silently in loops).
- State inconsistency (rare): success=False + diagnostic; run check_changes + health to heal.
- Conformance failures (I/O shape mismatch vs this spec + library design): treat as protocol violation; log + fallback.

Conformance harness (see gap1_validation_harness.py and m2 plan) exercises the above + mandatory workflow shapes.

### Structured Output Expectations (Mandatory for Agents)
- Prefer `format="json"` (or equivalent MCP structured) for all decision-making steps.
- Expect rich "dependency_intel", ACS explanations, barrel reports, cycles_reuse in health/json and suggest paths (on-demand persisted via import_cache).
- Bounded results on scale: use directory + summary; do not request full on 10k+ without resource budget.
- All protocol surfaces (library, MCP, shell) aim for parity on structured shapes.

### Concurrency, Scaling & Best Practices (v0.4)
- Use directory scoping + summaries on Medium+ repos.
- Python library or MCP for all long-running or high-volume work.
- Record intent with record_change on every semantic edit (this is non-negotiable for the living memory guarantee).
- After sleep/wake (daemon) or concurrent human activity: always lead with check_changes + health.
- Multi-agent: locking protects; agents cooperate via advisory protocol.

See the full design, mandatory workflow example, and M2 exit criteria in the plan. This protocol makes sessions predictable across models.

## Available Commands (treat as atomic MCP tools — legacy/compat surface)

| Command | Arguments | Description |
|---------|-----------|-------------|
| `wikifier check-changes` | — | Incremental mtime scan. Updates health matrix + pending queue. |
| `wikifier health` | — | Show current Documentation Health Matrix (🟢🟡🔴). |
| `wikifier record-change` | `<file> "<reason>"` | Semantic log of *why* you changed something. Required after edits. |
| `wikifier record-deletion` | `<file> "<reason>"` | Log a deletion with reasoning. |
| `wikifier prepare-edit` | `<file>` | Stage current mtime before you start editing (for future diffing). |
| `wikifier mark-green` | `<file> [reason]` | Flip file status to Green after you have written/updated its wiki summary. |
| `wikifier monitor` | — | Start background 30s heartbeat (run with `&` or in separate terminal). |
| `wikifier update-maps` | `[--full] [--directory=...] [--max-files=N]` | Rebuild `library.md` + import cache (single pure-Python pipeline; the shell launcher delegates here). |
| `wikifier validate` | — | Ensure every file in monitored_paths has at least a health row. |
| `wikifier journal` | `[YYYY-MM-DD]` | Read the journal for a day (default = today). |
| `wikifier issues` | `[simple|moderate|high|critical]` | List logged issues by severity. |
| `wikifier init` | — | Bootstrap config files if they are missing. |
| `wikifier help` | — | Full command reference. |

## MCP Server (Primary Interface — M5 Hardened)

This project exposes a first-class MCP server (wikifier-mcp or python -m wikifier.mcp.server).

**M5.1+ reality (from dogfood on external 5k-79k+ projects)**: MCP tools are preferred when available (get_project_status, get_file_wiki, get_barrel_reports for deep BRC, check_changes, record_change, mark_green, suggest_next_actions, health equivalents, etc.). **Always pass project_root= (or use WIKIFIER_PROJECT_ROOT env)** for external/user projects (RecipeLab_alt BRC stress, ConsistencyHub, llvm subs, etc.). 

**CLI-at-scale policy (G15):** On barrel-heavy or large monorepos (BRC stress, multi-k source trees), treat **CLI/library as the primary reliability path** for `update_maps`, barrel reports, and long health/suggest loops. MCP subprocess tools use a ~60s cap and may still time out; that is **not** a product failure — **immediately fall back** to `python -m wikifier …` / library calls. Do not claim DoD2 (&lt;30s MCP on alt/Consistency/llama) closed without a fresh measured pack; default operator policy is CLI for scale.

The server implements hardened external discovery (delegates to cli.py discover_project_root / _get_effective_root), 60s timeouts, actionable errors, and parity with library.

Legacy shell (`wikifier check-changes` etc.) and direct `wikifier-mcp` remain full fallbacks.

See `wikifier/mcp/server.py` (updated M5.1 for reliability + external) and `wikifier/mcp/README.md`.

High-value for agents (token-saving lookup + autonomous update):
- get_project_status / health equivalents
- get_file_wiki(file) — the direct "look up this file's wiki summary"
- get_barrel_reports (deep BRC for importers on re-export stress)
- record_change + mark_green (the autonomous update cycle)
- check_changes + suggest_next_actions

## MCP / Tool Exposure Recommendations

For reference, run:
```bash
wikifier-mcp
# or
python -m wikifier.mcp.server
```

The MCP tools are the primary structured interface for agents. Use them with explicit project_root for all non-self work.

## Best Practices for Agents

1. **Always** use `record-change` for your own work. This is what makes the system self-reviewable later.
2. Keep reasons concise (1–2 sentences) but specific.
3. After large refactors, run `update-maps` and then `validate`.
4. When you see many 🔴 Red items, tackle them before writing new features.
5. The background `monitor` process lets you "sleep" — the health matrix will be waiting for you on next wakeup.

## Example Agent Turn (v0.4 — Python library preferred when available)

```python
# Preferred (direct, structured, no shell, Python-primary paths)
from wikifier import check_changes, health, record_change, mark_green, suggest_next_actions, update_maps

check_changes()
print(health(format="summary"))

record_change("src/api/client.py", "Switched to httpx.AsyncClient because the sync requests library was causing blocking in the FastAPI event loop under high concurrency.")

# ... perform the actual edit ...

# Later, after writing the wiki summary for that file:
mark_green("src/api/client.py", "Purpose + import summary updated to reflect httpx usage and retry logic.")

print(suggest_next_actions(format="json"))
update_maps(directory="src/")  # if imports changed — full pure-Python pipeline (v4.2.0)
```

Fallback (shell or MCP) when library not directly importable in the agent env:
```bash
wikifier check-changes
# (reads output or file_health.md)

wikifier record-change "src/api/client.py" "Switched to httpx.AsyncClient because the sync requests library was causing blocking in the FastAPI event loop under high concurrency."

# ... perform the actual edit ...

# Later, after writing the wiki summary for that file:
wikifier mark-green "src/api/client.py" "Purpose + import summary updated to reflect httpx usage and retry logic."
```

This protocol (v0.6) + the zero-dependency Python library (core has no deps; MCP is optional via `pip install wikifier[mcp]`) make Wikifier a first-class, low-ambiguity citizen in any LLM-driven development workflow across models and environments. The design ensures the mandatory loop is executable with minimal deviation.

**Explicitly zero-dependency by design** (see pyproject.toml: dependencies = [] ; MCP via optional extra only). All core agent operations (health matrix for token-saving lookup, record-change/mark-green for autonomous wiki updates, check-changes, etc.) work with plain Python + the installed package or source — no external services or heavy deps required.

## Quick Reference — Library Surface (v0.6)
Core imports (all zero-dep for main paths; support project_root= for external/agent-to-agent use):
`from wikifier import check_changes, record_change, health, mark_green, suggest_next_actions, update_maps, discover_project_root, run_full_update`

All support `project_root=...` and return structured data (plus side-effecting state files for human review).

See README.md "Intended Use" for the strict agent-to-agent wiki scope (token saving for lookup + autonomous update/create of wiki entries only). M5 dogfood validated this on real external projects with the exact patterns above. Recent 4.0.1 hygiene (health coerce + superseded prune) further improves reliability of the matrix for agents doing direct lookups/updates.

**Human investigation layer (secondary, opt-in)**: `wikifier init` copies only `index.html` (the clean human wiki viewer) into the target project (the folder where MCP/CLI run). `diagnostics.html` (Wikifier maintainer hub) is no longer copied — it would show the wrong tree (Wikifier's internals) and be stale for the host project. Humans run `wikifier serve` and open http://localhost:8787/index.html (browsers block file:// fetches, so a double-clicked index.html shows an empty map — the page itself now detects this and shows the fix) to see a clean visual of *that project's* agent-maintained wiki: prominent code structure / dependency chart (Mermaid) as the hero, followed by a simple "Files & descriptions" list (paths + short "what this file is about" summaries pulled from the wiki notes), and a lightweight "Browse by folder" tree derived from the health data. A "Quick actions" toolbar provides one-click copy buttons for the main commands (check-changes, update-maps, monitor &); empty states ("No structure map yet", "No files in the wiki yet") have prominent primary buttons for first-time commands (update-maps prioritized, combined check-changes+update-maps for files). On first open with no map, the `wikifier update-maps` command is auto-copied (sessionStorage-guarded one-time per browser session) and live-wait mode is immediately activated. Buttons use copy + live-wait: they copy the exact command and inject a fixed top "Waiting for `wikifier ...` to produce data... (auto-polling)" banner with aggressive 3s polling that auto-detects when library.md / file_health.* update (from the terminal run) and refreshes the chart/files automatically; includes an "I ran it — refresh now" link in the banner and a success toast on detection. A short explanatory note in the UI clarifies the model: this is a pure static zero-dep viewer (browser JS cannot execute host shell commands due to security sandbox); the auto we provide is copy + immediate live-wait + fast poll so results (trees, files, descriptions) appear automatically after the user pastes/runs in their terminal. "Good enough" acceptance recorded for this copy+live-wait UX. Prominent copy buttons also export "structure as text" (Mermaid source) and a clean full snapshot (tree + file list + descriptions) — exactly the compact, token-saving view agents use. The default human page is intentionally free of dense agent internals (those live in `diagnostics.html` in the Wikifier source for technical users). If an old diagnostics.html is present, it can be safely deleted. The .md files + MCP/CLI/tools remain the primary SSOT and update mechanism for agents. This layer lets humans (or teams) visually investigate and copy-paste wiki summaries for their own work / LLM chats without touching agent behavior or adding deps.
