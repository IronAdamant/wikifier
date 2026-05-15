# Wikifier v0.3

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**Agent-first • Zero-dependency • LLM-operated codebase wiki**

Wikifier turns any codebase (tiny scripts → large monorepos) into a living, token-efficient map that LLMs/agents operate autonomously.

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

---

## What Wikifier Gives You

- **Per-file Documentation Health Matrix** — 🟢 Green / 🟡 Yellow / 🔴 Red status with reasons
- **Semantic Change Logging** — `record-change "file" "I did X because Y"` (the "why", not just the "what")
- **Background Heartbeat Monitor** — Passive `monitor &` loop keeps everything fresh while you sleep
- **Automated Journal + Categorized Issues** — Dated entries + `Logged_issues/{simple,moderate,high,critical}/...`
- **Beautiful Static Dashboard** — `index.html` with live health lights, Mermaid graphs, and one-click command reference
- **MCP / Agent Ready** — Full `skills/run.md` contract so Grok, Claude, Cline, etc. can drive it natively
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
