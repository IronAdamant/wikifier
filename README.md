# Wikifier v0.3

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**Agent-first • Zero-dependency • LLM-operated codebase wiki**

Wikifier turns any codebase (tiny scripts → large monorepos) into a living, token-efficient map that LLMs/agents operate autonomously.

### What's New in v0.3.1

- **Major improvements to Dependency Intelligence** (M2-Rem-08):
  - Complete refactor of the first-pass analysis engine (`perform_first_pass_graph_and_cache_update`)
  - Rich `resolved_pairs` now stored with `confidence` (`high` / `medium` / `low`)
  - Full reverse dependency recording and persistence (`_reverse_dependencies`)
  - `get_dependencies()` and `get_dependents()` now prefer the rich cache and are significantly more reliable
  - New `heal_stubs` and `list_healable_stubs` MCP tools + CLI commands

- **Health Matrix Auto-Healing**:
  - New `heal_outdated_stubs` system that detects "Initial stub" entries with real wiki summaries
  - Smarter quality heuristics (headings, purpose sections, structure, word count)
  - High-quality wikis can now be auto-promoted directly to 🟢 Green
  - `wikifier heal-stubs`, `wikifier healable-stubs`, and `wikifier healing-stats` commands
  - Full MCP tool support (`heal_stubs`, `list_healable_stubs`, `health(format="healing-stats")`)

- **Developer Experience**:
  - `WIKIFIER_DEBUG=1` mode for the first-pass (shows exactly what would be re-parsed without side effects)
  - Much cleaner and more maintainable first-pass code with extracted helpers

- **Cache & Data Model**:
  - `import_cache.json` now stores confidence in `resolved_pairs` and a top-level `_reverse_dependencies` map
  - Per-file `dependents` lists are now stored for impact analysis

This is a substantial patch release focused on making dependency intelligence and the Health Matrix trustworthy for autonomous agents.

> **GitHub**: https://github.com/IronAdamant/wikifier  
> **PyPI**: https://pypi.org/project/wikifier/

---

## 🚀 Installation

**Recommended — via pip:**

```bash
pip install wikifier
```

Then run:

```bash
wikifier init
wikifier check-changes
```

Then open `index.html` in your browser for the live dashboard.

---

**Alternative — from source:**

```bash
git clone https://github.com/IronAdamant/wikifier.git
cd wikifier
chmod +x wikifier.sh
./wikifier.sh init
./wikifier.sh check-changes
```

### Mandatory Rule for Every LLM / Grok Build Session

Copy this into the **start of every new prompt** when working in a Wikifier-managed project:

```text
You are operating inside a Wikifier v0.3 project.

MANDATORY FIRST STEPS:
1. Run: wikifier check-changes
2. Read file_health.md + pending_updates.md
3. Prioritise 🔴 Red → 🟡 Yellow items
4. For every code edit: wikifier record-change "path/to/file" "I did X because Y"
5. After updating the wiki summary: wikifier mark-green "path/to/file"
6. Re-validate before finishing
```

> **Note**: This rule applies per-project. When using Wikifier on an external codebase (not the Wikifier repo itself), the agent should be told which project root to operate on (via `WIKIFIER_PROJECT_ROOT`, `--project-root`, or the `project_root` parameter on MCP tools).

---

### Using Wikifier on External Projects (Packaging & Setup Clarity — M2-Rem-06)

Wikifier is a **general-purpose** agent memory system. After `pip install wikifier` (or `pip install wikifier[mcp]`), the `wikifier` and `wikifier-mcp` console scripts become available globally. You can (and should) use them on **any** codebase — not just the Wikifier source tree.

#### Pip Install vs Running from Source

- **After `pip install wikifier`** (recommended for normal use):
  - `wikifier` and `wikifier-mcp` commands are in your PATH.
  - The underlying implementation is the installed package (Python + shell scripts bundled).
  - You still need to tell Wikifier **which project** you want to document (see Root Targeting below).
  - `wikifier init --target /path/to/project` is the correct way to bootstrap state in an external folder.

- **Running from source** (development / contributing):
  - Clone the repo, `chmod +x wikifier.sh`, and invoke `./wikifier.sh ...` or the scripts directly.
  - Useful when you are actively modifying Wikifier itself.

**First-time setup on a new external codebase after pip install** (canonical flow):
```bash
# 1. Point at the target project
export WIKIFIER_PROJECT_ROOT=/path/to/your/actual/codebase

# 2. Bootstrap (creates monitored_paths.txt, file_health.md, etc.)
wikifier init --target "$WIKIFIER_PROJECT_ROOT"

# 3. Optional but recommended: edit monitored_paths.txt to focus on src/, app/, packages/ etc.
# 4. Run the mandatory workflow
wikifier check-changes

# 5. For agent work, start the MCP server with the same root
WIKIFIER_PROJECT_ROOT="$WIKIFIER_PROJECT_ROOT" wikifier-mcp
```

#### How Root Targeting Works (Decision Order for Agents)

Wikifier resolves the project root using this strict priority. Agents should follow it to avoid confusion:

1. `WIKIFIER_PROJECT_ROOT` environment variable (strongest — works for shell + all MCP tools)
2. Explicit `--project-root` (CLI) or `project_root` parameter on MCP tool calls
3. Upward directory walk looking for `monitored_paths.txt` or a `.wikifier/` directory
4. `.mcp.json` present in the workspace root (common in Grok Build, Cursor, etc.)

When the MCP server is started via `wikifier-mcp` (or through `.mcp.json`), it will usually auto-detect correctly if you `cd` into the project first. For maximum reliability on external dogfooding, always pass `project_root` or set the env var.

This packaging + targeting story was a major focus of M2-Rem-06 to eliminate the friction reported during RecipeLab_alt and self-dogfood.

---

### Scaling Wikifier — Recommended Patterns by Project Size (M2-Rem-06)

Wikifier is explicitly designed to scale from tiny scripts to massive monorepos. The guidance below is **prescriptive** — follow the patterns for your project size to stay fast and reliable.

#### Recommended Command Patterns

| Size                  | Preferred Interface       | Health Query                              | `update-maps` Strategy                          | Key Additional Practices |
|-----------------------|---------------------------|-------------------------------------------|-------------------------------------------------|--------------------------|
| **Tiny / Small**<br>(< 300 files) | Shell or MCP             | `wikifier health` (full table is fine)   | `wikifier update-maps` (default incremental)   | Use `.wiki.md` files next to sources for best `get_file_wiki`. Full rebuilds are cheap. |
| **Medium**<br>(300–2,000 files) | MCP preferred            | `health --summary` or `health --dir src/` | `update_maps()` (incremental). Use `--full` only after large refactors or suspected cache corruption. | Prefer MCP tools (`get_project_status`, `suggest_next_actions`). Use directory filtering heavily. |
| **Large**<br>(2,000–8,000 files) | **MCP strongly recommended** | `health(format="json", directory="src/services/")` + `--summary` | Always incremental. Inspect with `get_incremental_status()`. `--full` only on major structural changes. | Enable locking (automatic via Python backend). Run background `monitor &` safely. Use `get_files_needing_attention`. |
| **Massive**<br>(8,000–30,000+ files) | **MCP only**             | `health --summary --dir <package>/` (never full table) | Incremental + `get_incremental_status()` before/after. Never run `--full` unless cache is known stale. | Use `get_dependents` / `get_dependencies` per-file. Leverage `import_cache.json` visibility. Multiple agents + monitor is safe thanks to M2-Rem-07 locking. |

**When to use `--full` (rare):**
- After moving/renaming many packages or changing import styles across the codebase.
- If you manually deleted `import_cache.json`.
- When the dogfood report or `get_incremental_status` shows very low resolution health.

**Root Detection Rules (to avoid confusion)**
Wikifier finds the project root using this priority (agents should understand this):
1. `WIKIFIER_PROJECT_ROOT` environment variable (highest priority, works for both shell + MCP).
2. Explicit `--project-root` flag (CLI) or `project_root` parameter (MCP tools).
3. Walk upward from CWD looking for `monitored_paths.txt` or `.wikifier/` directory.
4. `.mcp.json` in the current workspace (common in Grok Build / Cursor sessions).

When operating on an external project after `pip install wikifier`, the most reliable pattern is:
```bash
WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/repo wikifier check-changes
WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/repo wikifier-mcp
```
Or pass `project_root` on every MCP tool call.

This section was significantly strengthened during M2-Rem-06 based on dogfood feedback.

---

## What Wikifier Gives You

- **Per-file Documentation Health Matrix** — 🟢 Green / 🟡 Yellow / 🔴 Red status with reasons
- **Semantic Change Logging** — `record-change "file" "I did X because Y"` (the "why", not just the "what")
- **Background Heartbeat Monitor** — Passive `monitor &` loop keeps everything fresh while you sleep
- **Automated Journal + Categorized Issues** — Dated entries + `Logged_issues/{simple,moderate,high,critical}/...`
- **Beautiful Static Dashboard** — `index.html` with live health lights, Mermaid graphs, and one-click command reference
- **First-Class MCP Server** — Run `wikifier-mcp` to expose Wikifier as a proper MCP server with rich tools (`get_dependents`, `get_project_status`, `suggest_next_actions`, etc.), resources, and prompts. Works great with Claude Desktop, Cline, Cursor, and other MCP clients.
- **Legacy Skills Interface** — `skills/run.md` still available for simpler shell-based agent setups.
- **True Zero Dependencies** — Pure Bash + PowerShell. Works on any machine, no Docker, no Node, no Python packages.

**This is agent-first.** LLMs operate the system via shell commands. Humans just watch the dashboard.

## Core Commands

| Command                    | Purpose                                      |
|---------------------------|----------------------------------------------|
| `wikifier check-changes`  | Incremental mtime scan + health update       |
| `wikifier record-change <file> "reason"` | Log *why* you made an edit (required) |
| `wikifier mark-green <file>` | Mark wiki summary as accurate after editing |
| `wikifier monitor &`      | Background heartbeat (30s polling)           |
| `wikifier update-maps`    | Rebuild `library.md` + Mermaid dependency graph |
| `wikifier health`         | Show current Documentation Health Matrix     |

Full reference → [`skills/run.md`](skills/run.md)

## Quick Links

- [spec.md](spec.md) — Immutable user requirements
- [Basis-v0.3.md](Basis-v0.3.md) — Implementation reference & data formats
- [TRADEOFFS.md](TRADEOFFS.md) — Why we made the design choices we did
- [index.html](index.html) — Open this in a browser for the live dashboard

## Differentiation

Unlike heavy "LLM Wiki" approaches (e.g. Karpathy-style personal knowledge bases), Wikifier is the **ultra-light, shell-native** implementation:

- Per-file health matrix with clear Red/Yellow/Green workflow
- Semantic `record-change` intent logging for future self-review
- True background monitor + zero external dependencies
- Native cross-platform (Linux/macOS/Windows via PowerShell)
- Designed from day one to be driven by LLMs via MCP/tools

**License**: MIT — fork freely and use in any project.

---

*Built for agents, by agents, with just `bash` and stubbornness.*
