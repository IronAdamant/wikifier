# Wikifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**Agent-to-Agent Codebase Wiki — Token-Efficient • Autonomous • Zero-Dependency**

Wikifier gives **AI agents and LLMs** a living, queryable map of any codebase (tiny scripts to 50k+ monorepos) so they can look up files, imports, health, and summaries **without loading full source into context**.

It is a **token-saving agent-operated wiki layer**. Agents autonomously maintain it using a strict workflow (see below). Primary purpose: save tokens for LLMs/agents doing real work on codebases.

### For AI Agents and LLMs: Token-Saving Codebase Wiki

- Fast lookup via small `file_health.md`, `library.md` (Mermaid dep graph + summaries), per-file `*.wiki.md`, health matrix, barrels, and incremental status — instead of dumping entire files.
- Autonomous updates: edit source → `record-change "the why"` (mandatory) → update the wiki entry → `mark-green`.
- Create new wiki entries/docs as you work.
- Works with or without MCP. Optional `wikifier-mcp` server exposes rich tools (`get_project_status`, `get_dependencies`, `get_file_wiki`, `suggest_next_actions`, `check_changes`, etc.).
- Incremental + scoped + streaming for large projects. Zero dependencies (pure Python + Bash).

**Mandatory agent protocol** (exact loop): `check-changes` → read health + pending → prioritize → edit → `record-change` → `mark-green` → `update-maps` when structure changes. Full details and LLM-ready workflow in `skills/run.md` (v0.5).

This project was built and dogfooded by agents operating exactly in this mode. It is **not** a general human docs system or IDE tool. Agent-to-agent first.

See `--help`, `skills/run.md`, and the MCP README for usage.

### Intended Use: Agent-to-Agent Wiki (Token-Saving Only)

This is meant **strictly** as an agent-to-agent wiki layer.

- Primary purpose: save tokens for agents/LLMs.
- You (the agent) can look up files quickly via the health matrix / file wikis / barrels / incremental status instead of reading full sources.
- Autonomously update wiki summaries and create new ones as you work (edit source → `record-change` → update the wiki entry → `mark-green`).
- Create new wiki-maintained files/docs as needed during agent sessions.
- Workflow for agents: `wikifier check-changes`, read the small `file_health.md` + `pending_updates.md`, prioritise, edit, `record-change`, `mark-green`, `update-maps` when relevant.
- **It shouldn't be used for anything more than that.** Not a general human documentation system, not an IDE replacement, not for broad non-agent use.

See the LLM workflow in `--help` and `skills/run.md` for the exact loop. All M5+ evidence was produced by agents operating in exactly this mode.

### Status & Recent Changes

M5 broad real-world dogfood (85-90%+) on multiple external 5k–50k+ creative projects is complete. See `Findings/M5-Dogfood-Progress.md`, `M5-Dogfood-Assessment-Report.md`, and `p6_real_world_validation_report.md` for full agent diaries, metrics, 9 Guiding Principles traces, and the M5.3 plan.

Recent focus (v4.1.x):
- Human investigation layer separation (only the clean `index.html` viewer is deployed to targets; `diagnostics.html` is maintainer-only).
- Mapping & update speed hygiene (faster candidate collection with scandir + git fast-path, consistent excludes, parser micro-opts). See v4.1.2 notes below.

Full history moved to `docs/` and `Findings/`. The project stays deliberately lean and agent-first.

**v4.1.2 (2026-06)**: Speed improvements for updates on large projects (scandir/git fast-path in collectors, richer early pruning via `exclude_patterns.txt`, regex hoisting in parsers). Complements scoping, streaming budgets, and incremental dirty + barrel reverse index. No behaviour change.

**v4.1.1**: Human layer separation enforcement (only `index.html` copied on init).

**v4.1.0**: Structure cleanup (historical docs to `docs/`).

**v4.0 + 4.0.1 + M5**: Broad dogfood, MCP hardening, zero-dep enforcement, sustained monitor/subagent foundations. See `Findings/` for details.

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

Then (after init) open `index.html` in your browser for the live (human) dashboard — health matrix, Mermaid tree, and export/copy text for LLM use. It lives inside your project folder alongside the MCP setup.

---

**Alternative — from source:**

```bash
git clone https://github.com/IronAdamant/wikifier.git
cd wikifier
chmod +x wikifier.sh
./wikifier.sh init
./wikifier.sh check-changes
```

### Mandatory Rule for Every LLM / Grok Build Session (Protocol v0.4)

**Authoritative spec**: See `skills/run.md` (Wikifier Agent Protocol v0.4) + the full library surface design in `Findings/m2-full-closure-longterm-scalable-plan.md` (Workstream E).

Copy this (or the exact block from skills/run.md) into the **start of every new prompt**:

```text
You are now operating inside a Wikifier v0.4 managed codebase (Agent Protocol v0.4).

FIRST ACTIONS (mandatory):
1. If the Wikifier MCP server is connected, prefer its tools (get_project_status, check_changes, suggest_next_actions).
2. Else if the `wikifier` Python package is importable, prefer the direct library API:
     from wikifier import check_changes, health, record_change, mark_green, suggest_next_actions, update_maps, discover_project_root
     check_changes()
     h = health(format="json")  # or "summary"
     ... perform edit ...
     record_change("path/to/file", "concise semantic reason (why, not what)")
     ... update wiki summary ...
     mark_green("path/to/file")
     if imports_or_structure_changed:
         update_maps(directory="src/", use_python_primary=True)
     suggest_next_actions(format="json")
     health(format="json")
3. Otherwise fall back to shell: wikifier check-changes
... (see full mandatory workflow, I/O contracts, error handling, and scaling in skills/run.md)
```

**Python Library (clean public API, zero-dep)**: The preferred path for agents (when importable). Provides structured dicts, auto-locking, Python-primary paths for the full mandatory loop with no shell. See `__init__.py`, `cli.py` (Workstream E funcs), and the design doc. Submodule power access (e.g. `from wikifier.health import ...`) remains available.

> **Note**: This rule applies per-project. When using Wikifier on an external codebase (not the Wikifier repo itself), the agent should be told which project root to operate on (via `WIKIFIER_PROJECT_ROOT`, `--project-root`, or the `project_root` parameter on MCP tools / library calls). The library + protocol make sessions low-ambiguity across models.

---

## Installation & Quick Start (for Agents & Humans)

```bash
pip install wikifier
```

For a project (recommended for agents):

```bash
# 1. In the target project (or use WIKIFIER_PROJECT_ROOT)
wikifier init

# 2. Focus monitored_paths.txt for large repos (highly recommended)
# 3. Run the agent loop
wikifier check-changes
wikifier health --summary
# ... edit ... 
wikifier record-change "path/to/file.py" "added feature X because Y (agent task Z)"
wikifier mark-green "path/to/file.py"
wikifier update-maps   # when imports/structure changed
```

**For MCP / AI agents** (Claude Desktop, Cursor, Cline, etc.):

```bash
WIKIFIER_PROJECT_ROOT=/abs/path/to/your/project wikifier-mcp
```

Or pass `project_root=` on every tool call. Root detection priority: env var > explicit param > upward walk for markers > .mcp.json.

Full protocol, examples, and LLM workflow: `skills/run.md` (read this first as an agent).

## What You Get

- Token-efficient lookup for agents (health matrix, library.md with Mermaid, file wikis, BRC, incremental status).
- Autonomous maintenance: `record-change` (the "why") + `mark-green`.
- Incremental + scoped + resumable for large codebases.
- Optional MCP server with 23+ tools for agents.
- Secondary clean `index.html` dashboard (after init) for humans browsing the agent's wiki (chart + file descriptions + copyable snapshots).
- True zero dependencies.

See `skills/run.md` for the exact agent contract and `wikifier/mcp/README.md` for MCP setup.

## Core Commands

| Command | Purpose |
|---------|---------|
| `wikifier check-changes` | Incremental scan + health/pending update |
| `wikifier record-change <file> "reason"` | Log why (required after edits) |
| `wikifier mark-green <file>` | Mark the wiki entry current |
| `wikifier update-maps` | Rebuild dependency graph + library.md |
| `wikifier health --summary` | Quick view (use for agents) |
| `wikifier monitor &` | Background incremental heartbeat |

For full power use the Python library (`from wikifier import ...`) or MCP tools directly.

## Links

- GitHub: https://github.com/IronAdamant/wikifier
- PyPI: https://pypi.org/project/wikifier/
- Agent Protocol: `skills/run.md`
- MCP: `wikifier/mcp/README.md`
- Evidence: `Findings/` (M5 dogfood etc.)

**For AI search / agents**: Wikifier is a zero-dependency, agent-maintained, token-saving codebase wiki with autonomous `record-change` / `mark-green` updates, MCP tools, and strong support for large monorepos via scoping and streaming.
