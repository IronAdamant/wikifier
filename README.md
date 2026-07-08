# Wikifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**A zero-dependency codebase wiki for AI agents** — token-efficient maps so LLMs look things up instead of re-reading full sources.

Wikifier is an **agent-to-agent** tool: it builds a living map of a project (health matrix, dependency graph, short file summaries) and agents keep that map current as they work. Humans can peek via a small dashboard; the product is the agent loop, not a general docs site or IDE.

Works from small scripts to large monorepos (Python + JavaScript/TypeScript imports, barrels, cycles, incremental updates).

## Why

Context windows are finite. Re-reading a large file to answer “what is this and who depends on it?” wastes tokens.

Wikifier keeps a small set of artifacts agents can query:

| Artifact | Role |
|----------|------|
| `file_health.md` | 🟢 / 🟡 / 🔴 matrix — what to trust, what to fix first |
| `library.md` | File tree, Mermaid dependency map, import tables, cycles + confidence |
| `*.wiki.md` | Short per-file “what this is for” notes (agent-maintained) |
| `journal/` | Semantic *why* trail from `record-change` |

Lookup beats re-ingest. That’s the whole idea.

## Quick start

```bash
pip install wikifier            # pure Python stdlib core — no runtime deps
pip install wikifier[mcp]       # optional Model Context Protocol (MCP) server

cd /path/to/your/project
wikifier init
wikifier update-maps            # dependency graph + library.md
wikifier check-changes
wikifier health --summary
```

Always set an explicit root for external trees:

```bash
WIKIFIER_PROJECT_ROOT=/abs/path/to/project wikifier check-changes
```

## Agent loop

Full protocol: [`skills/run.md`](skills/run.md).

```bash
wikifier check-changes
# prioritize 🔴 then 🟡 in file_health.md / pending_updates.md
# ... edit source ...
wikifier record-change "path/file.py" "why this changed"   # required
# ... refresh that file’s wiki summary ...
wikifier mark-green "path/file.py"
wikifier update-maps            # if imports/structure changed
```

`record-change` logs intent a git diff can’t reconstruct for the next agent (or human).

## What you get

- **Import analysis** — Python + JS/TS (ESM, CommonJS, dynamic imports, path aliases, package exports); per-edge confidence; name-routed barrel expansion (precise leaves, not edge explosion)
- **Incremental pipeline** — pure-Python `update-maps`: dirty parse → import cache → reverse deps → cycles → `library.md`
- **Scale** — reverse index + barrel invalidation so one edit doesn’t re-scan the monorepo
- **MCP tools** — optional server for Claude, Cursor, Cline, and other MCP clients (`get_project_status`, `get_dependencies`, `get_file_wiki`, `record_change`, …)
- **Zero core dependencies** — stdlib only; forks can add their own stack on top

## Performance (measured)

| Project | Scale | Full `update-maps` |
|---------|-------|--------------------|
| llama_index | ~3.8k Python files | ~8.5s |
| Babylon.js | ~3.9k TS files, barrel-heavy | ~4.5 min (scoped re-runs ~80s) |
| Large trees (e.g. LLVM-scale) | tens of thousands of files | candidate scan in seconds |

Tests: `python -m unittest discover tests` (stdlib only).

## Commands

| Command | Purpose |
|---------|---------|
| `wikifier init [--target DIR]` | Bootstrap project + human `index.html` |
| `wikifier check-changes` | Incremental scan → health / pending |
| `wikifier record-change <file> "reason"` | Log *why* (required after edits) |
| `wikifier mark-green <file>` | Mark wiki current |
| `wikifier update-maps [--directory=src/] [--max-files=N]` | Rebuild graph + `library.md` |
| `wikifier health [--summary\|--json]` | Health matrix (machine-friendly flags) |
| `wikifier cycles` | Circular deps + break hints |
| `wikifier monitor` / `daemon` | Background maintenance |
| `wikifier serve` | Localhost dashboard with Run/Stop |

Library: `from wikifier import check_changes, record_change, mark_green, health, update_maps`.

## MCP

```bash
WIKIFIER_PROJECT_ROOT=/abs/path/to/project wikifier-mcp
# or: python3 -m wikifier.mcp.server
```

Setup and tool list: [`wikifier/mcp/README.md`](wikifier/mcp/README.md).

## Human dashboard (secondary)

![Wikifier dashboard — file tree, health pills, local Run/Stop](https://raw.githubusercontent.com/IronAdamant/wikifier/main/screenshot/front_page_review.png)

`wikifier init` drops a single `index.html`. Prefer **`wikifier serve`** (e.g. http://localhost:8787/index.html) — `file://` can’t load project files. The markdown artifacts and CLI/MCP tools stay the source of truth; the UI is a read-only window.

## Scope

**In:** agent-maintained codebase wiki, dependency intelligence, token-saving lookup for LLMs and coding agents.  
**Out:** general human documentation systems, IDE plugins, “docs for everyone” product growth.

## Links

- [PyPI](https://pypi.org/project/wikifier/) · [GitHub](https://github.com/IronAdamant/wikifier)
- Agent protocol: [`skills/run.md`](skills/run.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Dogfood notes: `Findings/`
