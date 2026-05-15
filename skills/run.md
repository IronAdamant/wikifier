# Wikifier Skills & Commands (LLM / Grok Build / MCP Agent Interface)

**This file is the primary contract for any LLM or agent operating Wikifier.**

## Mandatory New-Session Rule

**Copy this exact block into the system prompt or the very first instruction of every new LLM session that uses Wikifier:**

```
You are now operating inside a Wikifier v0.3 managed codebase.

FIRST ACTIONS (mandatory):
1. Run: wikifier check-changes
2. Immediately read: file_health.md and pending_updates.md
3. Prioritise ALL 🔴 Red files, then 🟡 Yellow files.
4. For ANY edit you perform on the monitored codebase:
     - After the code change: wikifier record-change "<relative/path>" "I did X because Y. This affects Z."
5. After you have updated the corresponding wiki summary MD file:
     - wikifier mark-green "<relative/path>"
6. If imports changed significantly: wikifier update-maps
7. Re-validate with wikifier health before finishing.

Never skip the record-change step — it creates the semantic audit trail the project depends on.
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

## MCP / Tool Exposure Recommendations

When exposing Wikifier to an MCP client (Claude Desktop, Cline, Grok Build, etc.):

- Map each `wikifier <command>` to a distinct tool.
- For `record-change`, require two parameters: `file` (string) and `reason` (string).
- Return value should be the structured journal snippet + new health status.
- Also expose read-only tools:
  - `read_library` → returns `library.md`
  - `read_health_matrix` → returns `file_health.md`
  - `read_pending` → returns `pending_updates.md`

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
