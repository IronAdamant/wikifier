# Wikifier v0.3

**Agent-first, zero-dependency, self-maintaining codebase documentation & change tracking system.**

Wikifier turns any codebase (tiny scripts → large monorepos) into a living, token-efficient map that LLMs/agents operate autonomously.

**Purpose**
- Provide an always-current map of files, imports, purpose summaries, and dependency graph (Mermaid).
- Maintain **Documentation Health Matrix** (🟢 Green / 🟡 Yellow / 🔴 Red per file) with `pending_updates.md` task queue.
- Passive mtime polling (background heartbeat) + active LLM `record-change` semantic intent logging ("I added X because Y").
- Automated dated journal + categorised `Logged_issues`.
- Static HTML dashboard for humans (health lights, recent reasons, command launcher).
- Strict MD contract + `library.md` + skills for LLMs.
- Zero external dependencies – pure native OS tools (`.sh` + `.bat`). Runs on any hardware.

**This is agent-first and MCP/skills compatible.** LLMs/Grok Build drive it via shell commands. Humans observe via `index.html`.

## New Session Rule (add to every LLM/Grok Build prompt)

```
First run: wikifier check-changes
Read file_health.md and pending_updates.md
Prioritise 🔴 Red then 🟡 Yellow
For your own edits: use record-change <file> "reason" or record-deletion
After wiki MD updates: mark-green <file>
Then re-validate.
```

## Quick Start

1. `./wikifier.sh check-changes` (or `monitor` for background heartbeat).
2. Edit `monitored_paths.txt` / `exclude_patterns.txt` to point at your target codebase.
3. Open `index.html` for the live dashboard.
4. Agents: use commands from `skills/run.md` (MCP tool-ready).

See `spec.md` (immutable user requirements) and `Basis-v0.3.md` for full details. `TRADEOFFS.md` for design choices.

**Differentiation**: Unlike Karpathy LLM Wiki forks (agent-heavy and PKB-focused), Wikifier is the ultra-light shell-native implementation with per-file health matrix, semantic `record-change` for self-review, heartbeat loop, and native cross-platform support.

**License**: MIT – fork freely.
