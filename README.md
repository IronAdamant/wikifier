# Wikifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**Agent-to-Agent Codebase Wiki — Token-Efficient • Autonomous • Zero-Dependency**

Wikifier gives AI agents and LLMs a living, queryable map of any codebase — from tiny scripts to 50k+ file monorepos — so they can look up files, imports, health status, and summaries without dumping full source into context.

The goal is token efficiency. It works as a token-saving agent-operated wiki layer that agents maintain themselves through a strict but lightweight workflow. Primary purpose: help LLMs and agents work on real codebases without wasting context on raw files they don't need right now.

Key capabilities flow naturally from this:
- Fast, targeted lookup through small `file_health.md`, `library.md` (with Mermaid dependency graphs and summaries), per-file `*.wiki.md` notes, health matrix, barrel reports, and incremental status.
- Autonomous maintenance: after editing source, agents use `record-change "the why"` (this is mandatory) to log intent, then `mark-green` once the wiki entry is updated.
- Support for creating new wiki entries or docs on the fly during agent work.
- Works great with or without MCP. There's an optional `wikifier-mcp` server that provides rich tools such as `get_project_status`, `get_dependencies`, `get_file_wiki`, `suggest_next_actions`, and `check_changes`.
- Handles large projects well thanks to incremental updates, directory scoping, and streaming modes. Everything is zero-dependency (pure Python + Bash).

**Mandatory agent protocol** (the exact loop agents should follow): `check-changes` → read the compact `file_health.md` + `pending_updates.md` → prioritize → edit → `record-change` → `mark-green` → `update-maps` when imports or structure change. The full LLM-ready details and examples live in `skills/run.md` (v0.5).

This entire project (including all the M5 dogfood evidence) was built and operated by agents using exactly this mode. It is deliberately **not** a general-purpose human documentation tool or IDE replacement — agent-to-agent first, always.

See `--help`, `skills/run.md`, and the MCP README for concrete usage.

### Intended Use: Strictly Agent-to-Agent (Token-Saving)

This is meant **strictly** as an agent-to-agent wiki layer for token saving:

- Primary purpose: save tokens for agents/LLMs by letting them consult the health matrix, file wikis, barrels, and incremental status instead of re-reading full sources.
- Agents autonomously keep everything current: edit source → `record-change "the why"` → update the corresponding wiki entry → `mark-green`.
- You can create new wiki-maintained files or docs as part of your agent sessions.
- Typical workflow: run `wikifier check-changes`, read the small `file_health.md` + `pending_updates.md`, prioritize (🔴 then 🟡), do the work, record the change with intent, mark it green, and run `update-maps` when the dependency picture shifts.
- **It shouldn't be used for anything more than that.** Not general human docs, not an IDE, not for broad non-agent use.

The exact loop and LLM workflow are documented in `--help` and `skills/run.md`. All the real-world M5+ evidence in `Findings/` was produced by agents following this protocol precisely.

### Status & Recent Changes

M5 broad real-world dogfood (85-90%+) on multiple external 5k–50k+ creative projects is complete. See `Findings/M5-Dogfood-Progress.md`, `M5-Dogfood-Assessment-Report.md`, and `p6_real_world_validation_report.md` for full agent diaries, metrics, 9 Guiding Principles traces, and the M5.3 plan.

Recent focus (v4.1.x):
- Human investigation layer separation (only the clean `index.html` viewer is deployed to targets; `diagnostics.html` is maintainer-only).
- Mapping & update speed hygiene (faster candidate collection with scandir + git fast-path, consistent excludes, parser micro-opts).
- Human dashboard UX: prominent Quick actions toolbar with copy-to-clipboard buttons for main commands (check-changes, update-maps, monitor &); big primary buttons in empty states for first-time setup; auto-copy of `wikifier update-maps` command on first render of "no structure map yet" (session-guarded) so it feels automatic on first run of a fresh project. See v4.1.3 notes.

Full history moved to `docs/` and `Findings/`. The project stays deliberately lean and agent-first.

**v4.1.3 (2026-06)**: Human dashboard command buttons + first-run update-maps UX (very minor polish to the secondary human investigation layer).
- Added visible "Quick actions" bar with easy one-click copy buttons for the primary commands available to humans using the dashboard (check-changes, update-maps, start monitor). Feedback includes exact pasteable command + "run in this project folder then Refresh" guidance + manual refresh link.
- Enhanced empty states ("No structure map yet", "No files yet") with prominent primary buttons for the relevant commands (update-maps prioritized, combined first-time setup for files).
- "Automatically on first run": when the no-map empty state first appears in a browser session, the `wikifier update-maps` command is auto-copied (guarded by sessionStorage) with a note, making the recommended first action feel automatic. Buttons + instructions guide the user to run in terminal and refresh/poll.
- Existing "Rebuild tree" / "Update data" buttons now use the improved copy+feedback UX. Keeps the clean human view (no dense agent internals).
- All under protocol (FRESH, record+mark-green with subid=human-dashboard-commands). No new features or scope change. Complements the existing copy snapshot buttons and guidance.

**v4.1.2 (2026-06)**: Speed improvements for updates on large projects (scandir/git fast-path in collectors, richer early pruning via `exclude_patterns.txt`, regex hoisting in parsers). Complements scoping, streaming budgets, and incremental dirty + barrel reverse index. No behaviour change.

**v4.1.1**: Human layer separation enforcement (only `index.html` copied on init).

**v4.1.0**: Structure cleanup (historical docs to `docs/`).

**v4.0 + 4.0.1 + M5**: Broad dogfood, MCP hardening, zero-dep enforcement, sustained monitor/subagent foundations. See `Findings/` for details.

---

## 🚀 Installation

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
