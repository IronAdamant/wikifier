# Wikifier MCP Server (Rich Edition)

Wikifier now provides a powerful, first-class **MCP server** using the Model Context Protocol.

This allows AI coding agents to treat Wikifier as a native, transparent, and conservative codebase memory system.

## Installation

```bash
pip install wikifier[mcp]
# Development:
pip install -e ".[mcp]"
```

## Running

```bash
wikifier-mcp
# or
python -m wikifier.mcp.server
```

### Targeting a Specific Project (External Dogfooding) — Packaging Notes (M2-Rem-06)

After `pip install wikifier[mcp]`, `wikifier-mcp` is a global console script. It works on **any** external codebase.

**Options for pointing the MCP server at the right project (priority order):**

1. **Environment variable** (most reliable across sessions):
   ```bash
   WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/project wikifier-mcp
   ```

2. **CLI flag**:
   ```bash
   wikifier-mcp --project-root /path/to/your/project
   ```

3. **Auto-discovery**:
   Walks upward from CWD for `monitored_paths.txt` or `.wikifier/`.

4. **Per-tool `project_root` parameter**:
   You can override on individual calls even if the server was started against a different root:
   ```json
   { "get_dependents": { "file": "src/foo.js", "project_root": "/path/to/project" } }
   ```

**First-time external / monorepo project bootstrap after pip install** (R6 hardened):
```bash
# 1. Bootstrap directly (auto-creates markers, .wikifier/, optionally copies launcher)
wikifier init --target /absolute/path/to/your/monorepo

# 2. (Optional) set for session or rely on auto-discovery + per-call project_root
export WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/monorepo

# 3. Run commands (CLI now propagates --target/--project-root automatically)
wikifier check-changes

# 4. Start MCP (now reliably uses installed launcher + PROJECT_ROOT; no more sh-not-found)
wikifier-mcp --project-root /absolute/path/to/your/monorepo
# or simply: WIKIFIER_PROJECT_ROOT=... wikifier-mcp
```

Per-tool overrides still work for multi-project agents. The CLI, MCP runner, and shell now consistently separate script location from project state (WIKIFIER_PROJECT_ROOT), making large external pnpm/yarn/TS monorepos far smoother with fewer manual steps (no manual sh copy or repeated exports needed for basic flow).

This closes the external bootstrap gaps from P6/R3 dogfooding (RecipeLab_alt etc.). See also root README "Using Wikifier on External Projects".


## High-Value Tools

### Core
- `check_changes`, `record_change`, `mark_green`, `update_maps`, `health`, `validate`, etc.

### Dependency Intelligence (Very Powerful)
- `get_dependencies(file)`
- `get_dependents(file)` — Reverse dependencies ("who imports me?")
- `get_file_wiki(file)` — Smart lookup of per-file documentation

### Agent Productivity Tools
- `get_project_status()` — Excellent first tool call
- `suggest_next_actions()` — Extremely useful for autonomous agents
- `get_files_needing_attention()`
- `search_files(pattern, health_status)`

### Resources
- `wikifier://library`
- `wikifier://health`
- `wikifier://pending`
- `wikifier://journal/{date}`

### Prompts (Built-in Workflows)
- `review_pending_changes`
- `audit_project_health`
- `plan_refactoring(target)`
- `find_architectural_smells`
- `understand_codebase_structure`

## Philosophy

- **Conservative by default** — prioritizes accuracy and trustworthiness over completeness.
- **Highly transparent** — agents can see resolution stats, health, and limitations.
- **Agent-native** — high-level tools (`get_project_status`, `suggest_next_actions`, `get_dependents`) are first-class citizens.
- **Concurrency safe** (M2-Rem-07) — critical state files are protected by file locking so multiple agents + background monitors can safely operate in parallel.
- **Scales to large repositories** — incremental `update-maps`, directory-filtered health queries, and caching make it practical on monorepos with thousands of files.

This is currently the recommended way to integrate Wikifier with modern AI coding agents.

## Client Configuration Examples

Example configuration files for popular MCP clients (Claude Desktop, Cline, Cursor, etc.) are available in the `client-configs/` folder.

### Quick Claude Desktop Setup

1. Copy the example from `client-configs/claude-desktop.json`.
2. Merge it into your Claude Desktop configuration file.
3. Restart Claude Desktop.

See `client-configs/README.md` for detailed instructions and examples for other clients.