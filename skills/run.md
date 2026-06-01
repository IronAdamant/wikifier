# Wikifier Agent Protocol v0.4

**Formerly "Wikifier Skills & Commands". This is the authoritative, versioned specification for agent behavior when using Wikifier.**

**Version**: v0.4 (M2 Full Closure — Workstream E slice)  
**Date**: 2026-05-26  
**Status**: Active. Supersedes informal v0.3 skills guidance.  
**See also**: The public Python library surface design + I/O contracts in `Findings/m2-full-closure-longterm-scalable-plan.md` (Workstream E section).

**This file + the `wikifier` Python package (`from wikifier import ...`) together form the M2/M3 bridge for consistent, low-ambiguity agent operation.**

**This file is the primary contract for any LLM or agent operating Wikifier.**

## Mandatory New-Session Rule

**Copy this exact block into the system prompt or the very first instruction of every new LLM session that uses Wikifier:**

```
You are now operating inside a Wikifier v0.4 managed codebase (Agent Protocol v0.4).

FIRST ACTIONS (mandatory):
1. If the Wikifier MCP server is connected in this session, prefer using its tools (especially get_project_status, check_changes, and suggest_next_actions).
2. Else if the `wikifier` Python package is importable in the environment (pip install or source), prefer the direct library API for the core loop:
     from wikifier import check_changes, health, record_change, mark_green, suggest_next_actions, update_maps
     check_changes()
     h = health(format="json")  # or "summary"
     ... perform edit ...
     record_change("path/to/file", "concise semantic reason (why, not what)")
     ... update wiki summary ...
     mark_green("path/to/file")
     if imports_or_structure_changed:
         update_maps(directory="src/", use_python_primary=True)  # scoped, Python primary
     suggest_next_actions(format="json")
     health(format="json")  # re-validate
3. Otherwise fall back to shell: wikifier check-changes
4. Immediately read: file_health.md (or health json) and pending_updates.md
5. Prioritise ALL 🔴 Red files, then 🟡 Yellow files.
6. For ANY edit: record_change (via library, MCP, or wikifier record-change) — never skip.
7. After wiki summary update: mark_green.
8. If imports changed significantly: update_maps (scoped preferred).
9. Re-validate health + consult suggest_next_actions before finishing session.

Never skip the record_change step — it creates the semantic audit trail the project depends on (journal + health + pending).

Note: When working on an external project (not the Wikifier source itself), the effective project root may be set via `WIKIFIER_PROJECT_ROOT`, the `--project-root` flag, the `project_root` parameter on MCP tools, or the `project_root=` kwarg to all library functions (which use the hardened discover_project_root()).

**Packaging note (M2-Rem-06)**: After `pip install wikifier` or `pip install wikifier[mcp]`, use the global `wikifier` and `wikifier-mcp` commands or `from wikifier import ...` directly. Bootstrap external projects with `wikifier init --target /path/to/repo`. The same root-targeting rules apply whether you installed via pip or are running from source. The Python library is the preferred path for production agent use.

For large or massive repositories, **strongly prefer the Python library or MCP server** (`wikifier-mcp`) over raw shell for structured output and Python-primary paths. Use `health(..., directory=..., format="summary"|"json")` and directory-aware tools heavily. Follow the prescriptive scaling patterns in README.md (Small / Medium / Large / Massive tiers) + the library design in the M2 closure plan. The incremental cache + locking (M2-Rem-07) makes this practical at 50k+ files.

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
- `update_maps(..., use_python_primary=True, directory=...) -> dict`: delegates to run_full_update result + facade metadata.
- `run_full_update(...) -> dict`: { "success", "root", "files_to_reparse", "persist_pipeline_exercised", "barrel_creative_tied_in_pure_path", "dirty_sample", ... }

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
| `wikifier update-maps` | — | Rebuild `library.md` with fresh Mermaid dependency graph + import summary. |
| `wikifier validate` | — | Ensure every file in monitored_paths has at least a health row. |
| `wikifier journal` | `[YYYY-MM-DD]` | Read the journal for a day (default = today). |
| `wikifier issues` | `[simple|moderate|high|critical]` | List logged issues by severity. |
| `wikifier init` | — | Bootstrap config files if they are missing. |
| `wikifier help` | — | Full command reference. |

## MCP Server (Primary Interface in Grok Build)

This project has a **first-class MCP server** registered via `.mcp.json`.

When working in Grok Build on this project:

- If the **Wikifier MCP server** is connected (you will see tools like `get_project_status`, `get_dependents`, `suggest_next_actions`, `update_maps`, `record_change`, etc.), **prefer using the MCP tools** over shelling out to `wikifier` commands.
- The MCP server offers richer, structured, and more agent-friendly access (especially dependency intelligence and project status tools).
- The legacy shell commands (`wikifier check-changes`, `wikifier record-change`, etc.) remain fully supported as a fallback.

High-value MCP tools available:
- `get_project_status()` — Best first tool call
- `suggest_next_actions()`
- `get_dependents(file)` / `get_dependencies(file)`
- `get_file_wiki(file)`
- `record_change`, `check_changes`, `update_maps`, `mark_green`, etc.

If the Wikifier MCP tools are **not** visible in the current session, fall back to the shell commands documented below.

## MCP / Tool Exposure Recommendations (Legacy)

For reference, Wikifier can also be run directly:

```bash
wikifier-mcp
```

See `wikifier/mcp/README.md` for details.

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
update_maps(directory="src/", use_python_primary=True)  # if needed
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

This protocol (v0.4) + the Python library make Wikifier a first-class, low-ambiguity citizen in any LLM-driven development workflow across models and environments. The design ensures the mandatory loop is executable with minimal deviation.

## Quick Reference — Library Surface (v0.4)
See the complete design + example in `Findings/m2-full-closure-longterm-scalable-plan.md`.
Core imports: `from wikifier import check_changes, record_change, health, mark_green, suggest_next_actions, update_maps, discover_project_root, run_full_update`
All support `project_root=...` and return structured data (plus side-effecting state files for human review).
