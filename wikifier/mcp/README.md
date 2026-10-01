# Wikifier MCP server

An optional [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the Wikifier library to MCP clients (Claude, Cursor, Cline, …). It is a thin adapter over `wikifier.api`: every tool calls the same Python function the CLI uses — there is no shell fallback and no second code path. Agent contract: [`skills/run.md`](../../skills/run.md) (protocol v0.7).

## Install and run

```bash
pip install 'wikifier[mcp]'          # core stays zero-dependency; the extra adds mcp>=1,<2
WIKIFIER_PROJECT_ROOT=/abs/path/to/project wikifier-mcp
# or: wikifier-mcp --project-root /abs/path/to/project
# or: python -m wikifier.mcp.server
```

Client configuration:

```json
{
  "mcpServers": {
    "wikifier": {
      "command": "wikifier-mcp",
      "env": { "WIKIFIER_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```

The server root is resolved at startup (env / `--project-root` / marker discovery). Every tool also takes `project_root=` to target another project per call. **A `project_root` that does not exist is an error** (`error_type: "ProjectRootError"`), never a silent fallback.

## Core daily tools

| Tool | Role |
|---|---|
| `session_bootstrap` | root, readiness, health taxonomy, attention lists, dispatchable `actions[]`, root folder card |
| `check_changes` | flag content changes under monitored paths Yellow (content-honest) |
| `prepare_edit(file)` | status, wiki, dependencies (with `resolved_path`), dependents, cycle flag |
| `suggest_next_actions` | 🔴 then actionable 🟡 only; JSON `actions[]` |
| `record_change(file, reason)` | journal + Yellow + pending — required after every edit |
| `mark_green(file, force=False)` | checks the wiki against the code's public symbols, then trusts it; refusal returns `issues[]` |

`list_core_tools` lists them; everything below is advanced.

## Other tools

| Group | Tools |
|---|---|
| Batch | `record_changes(reasons, default_reason, only, since, green, dry_run)` — every file git reports as changed, reasons per path/glob/`dir/`; `verify_wikis` |
| Lookup | `get_file_wiki`, `why_file`, `search_journal`, `list_paths`, `get_dependencies` (`detail="compact"` default, `full`, `low_confidence_only`, `unresolved_only`), `get_dependents`, `get_cycles(analysis=True)`, `get_resolution_diagnostics`, `get_barrel_reports` |
| Status | `get_project_status`, `get_files_needing_attention`, `health(format=text\|json\|summary\|healing-stats)`, `validate`, `get_incremental_status`, `get_current_project_root`, `journal`, `issues` |
| Maintenance | `update_maps(full, directory, max_files)`, `record_deletion`, `seed_source_content_hashes`, `list_healable_stubs`, `heal_stubs` |
| Resources | `wikifier://library`, `wikifier://health`, `wikifier://pending`, `wikifier://journal/{YYYY-MM-DD}` |
| Prompts | `review_pending_changes`, `audit_project_health`, `plan_refactoring`, `find_architectural_smells`, `understand_codebase_structure`, `review_recent_changes`, `generate_project_health_report`, `onboard_to_module` |

## Behaviour notes

- Results are dicts with `success`; failures carry `error` and `error_type`. Read tools never write state.
- `check_changes`, `record_change` and `mark_green` run under an in-process deadline (`timeout_s`, default `WIKIFIER_MCP_DEADLINE_S=60`). On `timed_out: true` the call may still finish in the background (`may_still_complete: true`); check `why_file` before retrying. Identical `record_change` retries within 120 s are de-duplicated in the journal.
- `update_maps` returns `map_complete`; with a `max_files` budget, re-run with the same scope until it is true.
- Status tools read persisted summaries (ACS, cycle analyses, barrel cache, resolution diagnostics) and never deserialize the whole cache.
- On very large monorepos prefer the CLI/library for long `update_maps` runs (no MCP deadline), scoped with `directory`.

## Human layer

`wikifier init` copies only `index.html` into the project. Humans run `wikifier serve` and open `http://localhost:8787/index.html`; it is a read-only view of the same artifacts. `wikifier serve` also answers `/__wikifier/api/*` (read-only JSON over the same library calls).
