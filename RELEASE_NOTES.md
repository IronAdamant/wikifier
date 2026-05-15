# Wikifier v0.3 — Initial Public Release

**Agent-first, zero-dependency, self-maintaining codebase documentation & change tracking system.**

Wikifier is now open source.

## Highlights

- **Full cross-platform CLI**
  - `wikifier.sh` — Complete Linux/macOS implementation (all commands)
  - `wikifier.ps1` + `wikifier.bat` — Real Windows PowerShell support
- **Semantic Intent Logging** — `record-change <file> "I did X because Y"` captures the *why*, not just the diff
- **Documentation Health Matrix** — Per-file 🟢 Green / 🟡 Yellow / 🔴 Red with automatic updates
- **Background Heartbeat** — `wikifier monitor &` keeps the wiki fresh without constant LLM attention
- **Rich Static Dashboard** — Beautiful `index.html` with live health matrix, Mermaid dependency graphs, pending queue, and command launcher
- **MCP / Agent Native** — `skills/run.md` contains the exact contract and mandatory new-session rule every LLM must follow
- **Automated Journaling + Logged Issues** — Dated daily journals + categorized issues (`simple` → `critical`, `frontend`/`backend`/`security`/...)
- **True Zero Dependencies** — Only native OS tools. No Docker, no Node, no Python packages. Runs anywhere.

## New Session Rule (for LLMs)

Every time you start working in a Wikifier project, the first thing you must do is:

```bash
wikifier check-changes
# then read file_health.md + pending_updates.md
# then prioritise Red → Yellow
# use record-change for every edit
# mark-green after updating wiki summaries
```

## Quick Start

```bash
git clone https://github.com/IronAdamant/wikifier.git
cd wikifier
chmod +x wikifier.sh
./wikifier.sh init
./wikifier.sh check-changes
# open index.html
```

## What's Next (v0.4 ideas)

- Language-aware import parsing (better Mermaid graphs)
- Optional git hook integration
- TUI dashboard option
- Obsidian export mode

This is the real initial release of the project described in the original spec.

**Built for agents. Operated by agents. With just bash and determination.**
