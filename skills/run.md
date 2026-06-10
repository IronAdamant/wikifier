# Wikifier Agent Protocol v0.6

**Formerly "Wikifier Skills & Commands". This is the authoritative, versioned specification for agent behavior when using Wikifier.**

**Version**: v0.6 (v4.2.0 real-pipeline + reliability update)  
**Date**: 2026-06-10  
**Status**: Active. Supersedes v0.5.  
**See also**: `README.md` (Intended Use section: strictly agent-to-agent wiki for token saving), M5-Dogfood-Assessment-Report.md, Findings/2026-06-10-Dogfood-Refactor-Validation.md, and the library in wikifier/.

**v0.6 migration notes (package v4.2.0)** — changes are additive or strictly-better defaults; v0.5 agent behavior keeps working:
- `update-maps` (CLI) now runs the **pure-Python full pipeline by default**: every dirty file is parsed in-process, the canonical per-file cache is persisted, reverse deps + cycles + ACS are computed, and `library.md` is regenerated atomically. `--python-primary` is accepted but redundant; `--sh`/`--legacy-sh` selects the legacy shell path (slow fallback). Scoping is explicit via `--directory=`/`--max-files=` and reported in the result (`files_skipped`) — there are no silent caps.
- `run_full_update`/`update_maps` returns gained additive fields: `files_parsed` (actual), `parseable_files`, `edges_persisted`, `files_skipped`, `cycles`, `library`. Tolerate additive fields as always.
- `wikifier health --summary|--json|--format=...` now work from the CLI (previously library-only).
- A POSIX lock self-deadlock in library `record_change`/`mark_green`/`check_changes` was fixed (locking is now re-entrant per process). MCP timeouts on those tools should no longer occur; the CLI fallback guidance below remains valid as defense in depth.
- A stdlib-only test suite exists: `python -m unittest discover tests` (run it when working on Wikifier itself).

**Core design**: Token-efficient agent-to-agent wiki. Agents use it to look up files (health matrix + file wikis + BRC + stele chunks instead of full sources), autonomously update wiki summaries, and create new ones as work progresses. **It should not be used for anything more than that.** 

This protocol + the Python package + MCP server form the bridge for consistent, low-ambiguity agent operation on real external projects.

**This file + the `wikifier` Python package (`from wikifier import ...`) together form the M2/M3 bridge for consistent, low-ambiguity agent operation.**

**This file is the primary contract for any LLM or agent operating Wikifier.**

## Mandatory New-Session Rule

**Copy this exact block into the system prompt or the very first instruction of every new LLM session that uses Wikifier:**

```
You are now operating inside a Wikifier-managed codebase (Agent Protocol v0.6 — v4.2.0).

This is strictly an agent-to-agent wiki for token saving: quick file lookup (health matrix + file wikis + BRC + stele instead of full sources), autonomous wiki summary updates, and creation of new wiki entries as you work. It should not be used for anything more.

FIRST ACTIONS (mandatory, post-M5 hardened):
1. If the Wikifier MCP server is connected, prefer its tools (get_project_status, get_file_wiki, check_changes, get_barrel_reports, suggest_next_actions, etc.). Always pass project_root= for external/user projects (e.g. RecipeLab_alt, ConsistencyHub, llvm subs).
2. If MCP times out or is unavailable (rare since v4.2.0 fixed the workflow-call deadlock and batched barrel persistence; historically seen on BRC-heavy or 50k+ scale targets), fall back immediately to reliable CLI/library:
     WIKIFIER_PROJECT_ROOT=/path/to/target python -m wikifier check-changes
     python -m wikifier health --summary   # or format=json/summary for machine use (token-efficient lookup)
     ... perform edit on source ...
     python -m wikifier record-change "path/to/file" "concise semantic reason (why, not what). Include subid if agent work."
     ... write/update the wiki summary for the file ...
     python -m wikifier mark-green "path/to/file" "Reason for Green (e.g. after autonomous agent update)."
     if imports changed: python -m wikifier update-maps [--directory=src/]  # pure-Python full pipeline by default (v4.2.0)
     python -m wikifier health --summary
3. For sustained agent work: launch `python -m wikifier monitor` (or wikifier.sh monitor) in bg / daemon for 30s "Pruned 0 / No new" heartbeat + auto BRC healing. Use .last_check + health for observability.
4. Immediately consult the small health matrix (file_health.md or health --summary) + pending_updates.md. Prioritise 🔴 then 🟡. Use this for quick reference instead of full file reads to save tokens.
5. For edits to agent-maintained docs (e.g. this protocol, README, Findings/M5-*.md): precede with FRESH 3 hygiene (grep for 0 def matches on the target .md), use record-change + mark-green.
6. Always pass explicit project_root / WIKIFIER_PROJECT_ROOT for any external or multi-project work (M5 lesson: absolute monitored_paths.txt, no pollution).
7. Re-validate with health + suggest_next_actions (or equivalent) at end of turn/session. Use monitor for long-running.

Never skip record-change — it is the semantic audit trail (journal + health + pending + BRC).

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
- Non-blocking / timeout queries and per-file locking are not implemented yet (advanced agents can use `wikifier.locking.is_project_locked()` for diagnostics).
- Best-effort portability on non-Unix systems.

The locking system (Python `file_lock` + shell `with_project_lock`) has received final polish. It is now considered production-ready for the M2 scope. Future extensions (fine-grained locking) can be added when real usage pressure appears on extremely large concurrent setups.

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
- **Locking**: Mutators block on project lock (production default). Future non-blocking/timeout will be additive.
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
| `wikifier update-maps` | `[--full] [--directory=...] [--max-files=N] [--sh]` | Rebuild `library.md` + import cache (pure-Python full pipeline by default; `--sh` = legacy shell fallback). |
| `wikifier validate` | — | Ensure every file in monitored_paths has at least a health row. |
| `wikifier journal` | `[YYYY-MM-DD]` | Read the journal for a day (default = today). |
| `wikifier issues` | `[simple|moderate|high|critical]` | List logged issues by severity. |
| `wikifier init` | — | Bootstrap config files if they are missing. |
| `wikifier help` | — | Full command reference. |

## MCP Server (Primary Interface — M5 Hardened)

This project exposes a first-class MCP server (wikifier-mcp or python -m wikifier.mcp.server).

**M5.1+ reality (from dogfood on external 5k-79k+ projects)**: MCP tools are preferred when available (get_project_status, get_file_wiki, get_barrel_reports for deep BRC, check_changes, record_change, mark_green, suggest_next_actions, health equivalents, etc.). **Always pass project_root= (or use WIKIFIER_PROJECT_ROOT env)** for external/user projects (RecipeLab_alt BRC stress, ConsistencyHub, llvm subs, etc.). 

MCP timeouts are rare since v4.2.0 (the library workflow-call deadlock is fixed and barrel persistence is batched), but on very large/BRC-heavy targets they can still happen. In that case, **immediately fall back to CLI/library** (python -m wikifier health --summary or the library health(..., format="summary")) — these are reliable and were the workhorse in M5 sustained/monitor work.

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

**Human investigation layer (secondary, opt-in)**: `wikifier init` copies only `index.html` (the clean human wiki viewer) into the target project (the folder where MCP/CLI run). `diagnostics.html` (Wikifier maintainer hub) is no longer copied — it would show the wrong tree (Wikifier's internals) and be stale for the host project. Humans open the local `index.html` (via `python -m http.server` recommended) to see a clean visual of *that project's* agent-maintained wiki: prominent code structure / dependency chart (Mermaid) as the hero, followed by a simple "Files & descriptions" list (paths + short "what this file is about" summaries pulled from the wiki notes), and a lightweight "Browse by folder" tree derived from the health data. A "Quick actions" toolbar provides one-click copy buttons for the main commands (check-changes, update-maps, monitor &); empty states ("No structure map yet", "No files in the wiki yet") have prominent primary buttons for first-time commands (update-maps prioritized, combined check-changes+update-maps for files). On first open with no map, the `wikifier update-maps` command is auto-copied (sessionStorage-guarded one-time per browser session) and live-wait mode is immediately activated. Buttons use copy + live-wait: they copy the exact command and inject a fixed top "Waiting for `wikifier ...` to produce data... (auto-polling)" banner with aggressive 3s polling that auto-detects when library.md / file_health.* update (from the terminal run) and refreshes the chart/files automatically; includes an "I ran it — refresh now" link in the banner and a success toast on detection. A short explanatory note in the UI clarifies the model: this is a pure static zero-dep viewer (browser JS cannot execute host shell commands due to security sandbox); the auto we provide is copy + immediate live-wait + fast poll so results (trees, files, descriptions) appear automatically after the user pastes/runs in their terminal. "Good enough" acceptance recorded for this copy+live-wait UX. Prominent copy buttons also export "structure as text" (Mermaid source) and a clean full snapshot (tree + file list + descriptions) — exactly the compact, token-saving view agents use. The default human page is intentionally free of dense agent internals (those live in `diagnostics.html` in the Wikifier source for technical users). If an old diagnostics.html is present, it can be safely deleted. The .md files + MCP/CLI/tools remain the primary SSOT and update mechanism for agents. This layer lets humans (or teams) visually investigate and copy-paste wiki summaries for their own work / LLM chats without touching agent behavior or adding deps.
