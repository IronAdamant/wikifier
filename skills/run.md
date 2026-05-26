# Wikifier Skills & Commands (LLM / Grok Build / MCP Agent Interface)

**This file is the primary contract for any LLM or agent operating Wikifier.**

## Mandatory New-Session Rule

**Copy this exact block into the system prompt or the very first instruction of every new LLM session that uses Wikifier:**

```
You are now operating inside a Wikifier v0.3 managed codebase.

FIRST ACTIONS (mandatory):
1. If the Wikifier MCP server is connected in this session, prefer using its tools (especially get_project_status, check_changes, and suggest_next_actions).
2. Otherwise, run: wikifier check-changes
3. Immediately read: file_health.md and pending_updates.md
4. Prioritise ALL 🔴 Red files, then 🟡 Yellow files.
5. For ANY edit you perform on the monitored codebase:
     - After the code change: record the change (via MCP tool or wikifier record-change)
6. After you have updated the corresponding wiki summary MD file:
     - mark it green (via MCP tool or wikifier mark-green)
7. If imports changed significantly: run update-maps
8. Re-validate health before finishing.

Never skip the record-change step — it creates the semantic audit trail the project depends on.

Note: When working on an external project (not the Wikifier source itself), the effective project root may be set via `WIKIFIER_PROJECT_ROOT`, the `--project-root` flag, or the `project_root` parameter on MCP tools.

**Packaging note (M2-Rem-06)**: After `pip install wikifier` or `pip install wikifier[mcp]`, use the global `wikifier` and `wikifier-mcp` commands. Bootstrap external projects with `wikifier init --target /path/to/repo`. The same root-targeting rules apply whether you installed via pip or are running from source.

For large or massive repositories, **strongly prefer the MCP server** (`wikifier-mcp`) over the raw shell. Use `health --summary --dir <path>/` and directory-aware tools heavily. Follow the prescriptive scaling patterns documented in README.md (Small / Medium / Large / Massive tiers). The incremental cache + locking (M2-Rem-07) makes this practical.

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
```

## Available Commands (treat as atomic MCP tools)

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

## Example Agent Turn

```bash
wikifier check-changes
# (reads output or file_health.md)

wikifier record-change "src/api/client.py" "Switched to httpx.AsyncClient because the sync requests library was causing blocking in the FastAPI event loop under high concurrency."

# ... perform the actual edit ...

# Later, after writing the wiki summary for that file:
wikifier mark-green "src/api/client.py" "Purpose + import summary updated to reflect httpx usage and retry logic."
```

This skills file + the shell commands make Wikifier a first-class citizen in any LLM-driven development workflow.
