# Wikifier MCP Server (Rich Edition)

Wikifier provides a powerful, first-class **MCP server** using the Model Context Protocol.

**This is explicitly part of the agent-to-agent wiki system** (see root README "Intended Use" and skills/run.md v0.6): for token-efficient file lookup (via health matrix, get_file_wiki, BRC reports, etc.), autonomous updates to wiki summaries, and creation of new wiki entries as agents work. Core Wikifier is **zero-dependency** (see pyproject.toml: dependencies = [] ; only optional `mcp` extra for the server). MCP support is opt-in and does not affect the zero-dep guarantee for agents using the library or CLI.

This allows AI coding agents to treat Wikifier as a native, transparent, and conservative codebase memory system for the strict agent-to-agent wiki use case.

## Installation (Zero-Dependency Core + Optional MCP)

The entire project is **explicitly zero-dependency** by design:

```toml
# pyproject.toml
dependencies = []  # Zero-dependency by default. MCP support is optional.
[project.optional-dependencies]
mcp = ["mcp>=1.0.0"]
```

```bash
# Core (zero-dep, always):
pip install wikifier

# With MCP server (optional extra):
pip install wikifier[mcp]
# Development:
pip install -e ".[mcp]"
```

Core library + CLI work with zero deps for health matrix, record-change, etc. MCP is only for the server/tools exposure.

## Running

```bash
wikifier-mcp
# or
python -m wikifier.mcp.server
```

### Targeting a Specific Project (External / Agent-to-Agent Use) — M5+ Notes

After `pip install wikifier` (zero-dep core) or `wikifier[mcp]`, `wikifier-mcp` is a global console script. It works on **any** external codebase.

**M5 dogfood validated (alt BRC stress, ConsistencyHub, llvm 79k+ C++ subs, many customs):** always use explicit root targeting for user/external projects. Core remains zero-dep; MCP optional.

**Options for pointing the MCP server at the right project (priority order):**

1. **Environment variable** (most reliable across sessions, especially daemons/monitors):
   ```bash
   WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/project wikifier-mcp
   ```

2. **CLI flag**:
   ```bash
   wikifier-mcp --project-root /path/to/your/project
   ```

3. **Auto-discovery**:
   Walks upward from CWD for `monitored_paths.txt` or `.wikifier/`.

4. **Per-tool `project_root` parameter** (MCP agents):
   You can override on individual calls even if the server was started against a different root:
   ```json
   { "get_dependents": { "file": "src/foo.js", "project_root": "/path/to/project" } }
   ```

**First-time external / monorepo project bootstrap** (M5-hardened, zero-dep):
```bash
# 1. Bootstrap directly (auto-creates markers, .wikifier/, optionally copies launcher)
wikifier init --target /absolute/path/to/your/monorepo

# 2. (Optional) set for session or rely on auto-discovery + per-call project_root
export WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/monorepo

# 3. Run commands (CLI now propagates --target/--project-root automatically; zero-dep core)
wikifier check-changes

# 4. Start MCP (reliably uses installed launcher + PROJECT_ROOT)
wikifier-mcp --project-root /absolute/path/to/your/monorepo
# or simply: WIKIFIER_PROJECT_ROOT=... wikifier-mcp
```

Per-tool overrides still work for multi-project agents. The CLI, MCP runner, and shell now consistently separate script location from project state (WIKIFIER_PROJECT_ROOT), making large external monorepos far smoother.

See also root README "Using Wikifier on External Projects" and "Intended Use" (primary: strictly agent-to-agent wiki for token saving via tools/text files; secondary: human investigation).

M5.1 fixed pollution, absolute paths, root discovery. M5.3 added monitor/daemon support for sustained agent use. Post-4.0.1 hygiene: `health.py` now supports direct `str | Path` roots via `_coerce_root` (robust for library + per-tool MCP consumers) and auto-prunes superseded historical wiki-note entries (e.g. early M5.3 launch notes) while preserving intentional 🔴 Red audit records for lean, trustworthy agent lookup (see main health matrix and the superseded prune logic).

**Human layer in MCP projects**: `wikifier init --target` (or equivalent) copies only `index.html` (the human viewer) into the project root — the same folder the MCP server/CLI operate on. `diagnostics.html` (Wikifier's maintainer/refactor hub with its own architecture and source tree) is no longer copied; it would point at the wrong folder and be stale/irrelevant for the host project (delete any old copy if present). Humans run `wikifier serve` and open http://localhost:8787/index.html (browsers block file:// fetches — a double-clicked index.html shows an empty map; the page itself detects this and shows the fix) for a clean visual of *this project's* wiki: the code structure/dependency chart (Mermaid) is the prominent hero at the top, followed by "Files & descriptions" (paths + short wiki summaries of what each file does) and a simple folder browser. A "Quick actions" toolbar provides one-click copy buttons for the main commands (check-changes, update-maps, monitor &); empty states have prominent buttons for first-time commands (update-maps prioritized). On first open (no map yet), the update-maps command is auto-copied (sessionStorage-guarded) with guidance so initial setup feels automatic — and live-wait mode starts immediately. Buttons use an enhanced copy+live-wait model: copy the exact command, inject a fixed "Waiting for `wikifier update-maps` (or combined) to produce data... (auto-polling every 3s)" banner at top, with an "I ran it — refresh now" link; an aggressive 3s setInterval then reloads the relevant sections (mermaid for update-maps, health for check) and auto-detects when data appears (hasMap / hasFiles from the artifacts written by the terminal execution), stops polling, removes banner, shows success toast "✓ Data updated! View refreshed.", and forces view refresh — so the trees/files appear automatically after the user runs the pasted command. A UI note explains the design: pure static client-side viewer (zero runtime deps, no privileged code); browser sandbox prevents static JS from executing host shell commands; the provided auto is copy + live-wait + fast poll so results show without further UI action post-terminal-run. This was accepted as "Good enough" after full rationale. Two big copy buttons give "Copy structure as text" (just the Mermaid) and "Copy full snapshot (tree + files + descriptions)" — clean Markdown ready to paste into docs, emails, or LLM chats. The main human page deliberately shows *only* what's useful for human investigation (chart + files + what they look like); dense agent details live in `diagnostics.html` in the Wikifier source (for maintainers/porters of the tool). Agent-to-agent work via MCP tools + the text files stays primary and unchanged. This is the secondary human investigation / export layer on top of the zero-dep agent wiki.


## Reliability Notes (v4.2.0)

- `update_maps` now drives the **real pure-Python pipeline** by default: every dirty file is parsed in-process, the canonical cache is persisted, reverse deps + cycles + ACS are computed, and `library.md` is regenerated atomically. `directory=` and `max_files=` are explicit scoping, reported back as `files_skipped` (no silent caps). Measured: 3,837 Python files in ~8.5s.
- A POSIX lock self-deadlock in `record_change`/`mark_green`/`check_changes` (the likely cause of historical MCP timeout reports on these tools) is fixed — locking is now re-entrant per process.
- Barrel-cache persistence is batched per run instead of per chain expansion (~43× faster JS/TS parsing on barrel-heavy projects).
- The optional `mcp` dependency is now import-guarded: the core `wikifier` package imports cleanly without it, and `wikifier-mcp` fails with a clear "pip install wikifier[mcp]" message instead of a traceback.

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

## Philosophy (Agent-to-Agent Wiki, Zero-Dep Core)

- **Strictly agent-to-agent wiki for token saving** (per root README "Intended Use" and skills/run.md v0.6): quick file lookup via the health matrix / get_file_wiki / BRC / stele chunks (instead of dumping full sources into context), autonomous updates to wiki summaries, and creation of new wiki-maintained files/entries as agents work. It should not be used for anything more.

- **Zero-dependency by design** — core (health matrix, record-change, check-changes, library, CLI) has no runtime dependencies (see pyproject.toml). MCP server/tools are optional via the `[mcp]` extra only. This keeps the agent wiki layer lightweight and portable for any environment.

- **Conservative by default** — prioritizes accuracy and trustworthiness over completeness. Agents should prefer `format="summary"` or `"json"` + `directory=` scoping on large projects. Timeouts are rare since v4.2.0 (deadlock fix + batched barrel persistence), but the CLI fallback remains valid defense in depth on extreme targets.
- **Highly transparent** — agents can see resolution stats, health, and limitations.
- **Agent-native** — high-level tools (`get_project_status`, `suggest_next_actions`, `get_dependents`) are first-class citizens.
- **Concurrency safe** (M2-Rem-07) — critical state files are protected by file locking so multiple agents + background monitors can safely operate in parallel.
- **Scales to large repositories** — incremental `update-maps`, directory-filtered health queries, and caching make it practical on monorepos with thousands of files.

This is currently the recommended way to integrate Wikifier with modern AI coding agents.

## Client Configuration Examples

MCP clients (Claude Desktop, Cline, Cursor, etc.) are configured to launch the server with proper project targeting.

**Recommended for external/agent-to-agent use** (M5+ lesson): run via environment or flag so the server knows the target root:

```json
{
  "mcpServers": {
    "wikifier": {
      "command": "wikifier-mcp",
      "args": [],
      "env": {
        "WIKIFIER_PROJECT_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

Per-tool `project_root` overrides also work for multi-project agents. See "Targeting a Specific Project" above and `skills/run.md` for the full agent protocol (always pass explicit root for externals, fall back to CLI on large/BRC targets).

No bundled client-configs/ examples in this release (historical references removed for cleanliness); use the patterns above + the tool list in this doc. For advanced setups, consult the MCP client docs and the Wikifier health matrix for current state.