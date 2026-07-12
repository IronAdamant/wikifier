# Wikifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**A zero-dependency codebase wiki for AI agents** — token-efficient maps so LLMs look things up instead of re-reading full sources.

Wikifier is an **agent-to-agent** tool: it builds a living map of a project (health matrix, dependency graph, short file summaries) and agents keep that map current as they work. Humans can peek via a small dashboard; the product is the agent loop, not a general docs site or IDE.

Works from small scripts to large monorepos. **Deep import/include maps** (zero-dep regex parsers):

| Language | Extensions | Notes |
|----------|------------|--------|
| Python | `.py` | full ACS/CDIA path |
| JavaScript / TypeScript | `.js` `.ts` `.jsx` `.tsx` | barrels (BREE), dynamic/CDIA |
| Rust | `.rs` | `use` / `mod` / `extern crate` |
| Go | `.go` | `import` / import blocks |
| C / C++ | `.c` `.h` `.cpp` `.cc` `.cxx` `.hpp` `.hh` | `#include` (local + system) |
| C# | `.cs` | `using` namespaces |
| Java | `.java` | `import` / `import static` |

Health/journal still work for any monitored path. Parsers are **pragmatic regex** (not full cargo/`go.mod`/classpath/`-I` resolution). Prefer **lean `monitored_paths.txt`** on huge monorepos; raise dirty cap with `WIKIFIER_CHECK_CHANGES_MAX` (default 2000) only when needed.

## Why

Context windows are finite. Re-reading a large file to answer “what is this and who depends on it?” wastes tokens.

| Artifact | Role |
|----------|------|
| `file_health.md` | 🟢 / 🟡 / 🔴 matrix — what to trust, what to fix first |
| `library.md` | File tree, Mermaid dependency map, import tables, cycles + confidence |
| `*.wiki.md` | Short per-file “what this is for” notes (**agent-maintained** prose) |
| `journal/` + `pending_updates.md` | Semantic *why* trail + work queue (audit, **not** a full issue tracker) |

**Map first, wiki depth second:** `update-maps` builds the structural map automatically. Rich per-file wiki text is filled by agents as they work — not a free full-repo “understand everything” pass on init.

## First run (bootstrap the map)

```bash
pip install wikifier            # pure Python stdlib core — no runtime deps
pip install wikifier[mcp]       # optional Model Context Protocol (MCP) server

cd /path/to/your/project
wikifier init                   # seeds + human index.html
wikifier update-maps            # full structural map → library.md + import cache
wikifier health --summary       # matrix counts
wikifier suggest-next           # or MCP suggest_next_actions — 🔴/🟡 only
```

Always set an explicit root for external trees: `WIKIFIER_PROJECT_ROOT=/abs/path wikifier …`

## Steady state (only touch what needs it)

Full protocol: [`skills/run.md`](skills/run.md) (Agent Protocol v0.6 — package **4.6.x**).

```bash
wikifier session-bootstrap      # one-shot: root, health, attention, actions[]
wikifier check-changes          # content-honest dirty; red ghosts (missing paths)
# prioritize 🔴 then *actionable* 🟡 — do NOT re-wiki 🟢 Green files
wikifier prepare-edit path/file.py   # wiki + status + deps/dependents preflight
# ... edit only those sources ...
wikifier record-change "path/file.py" "why this changed"   # required
# ... refresh that file’s wiki summary only ...
wikifier mark-green "path/file.py"
wikifier update-maps            # only if imports/structure changed (warm 0-dirty is cheap)
# removals:
wikifier record-deletion "path/gone.py" "why removed"
```

**Core 6** (prefer every session — MCP or library/CLI):  
`session_bootstrap` → `check_changes` → `prepare_edit` → `suggest_next_actions` (json `actions[]`) → `record_change` → `mark_green`.

Advanced intel as needed: `get_dependencies`, `get_dependents`, `get_cycles`, barrels/diagnostics. Always pass `project_root=` / `WIKIFIER_PROJECT_ROOT` for external trees. **Never** point `project_root` at a multi-repo parent folder (e.g. a directory of clones).

## What you get

- **Import analysis** — Python, JS/TS (ESM/CJS, barrels), Rust (`use`/`mod` + best-effort `crate::` paths), Go, C/C++ includes, C# usings; per-edge confidence; barrel expansion for TS/JS
- **Incremental pipeline** — pure-Python `update-maps`: dirty parse → import cache → reverse deps → cycles → `library.md`
- **Warm agent maps (4.6.3–4.6.5)** — zero-dirty fast path; **stdlib SQLite** cache; **candidate list reuse** + scoped/monitored-first walks (no whole-tree thrash); content-hash dirty
- **Partial-map honesty** — `map_coverage` on `update_maps` / bootstrap / **`suggest_next`**; incomplete maps yield `update_maps_until_complete` actions
- **Cache ops** — `wikifier cache-status` (backend, bytes, ACS, coverage, dual-write policy)
- **Selective agent work** — health + suggest bias to 🔴/actionable 🟡 only; **ACS v1.3** `reason_code` / `agent_signal`; prefer `actionable_low_conf_edges` + reason codes — **never** raw `low_conf_edges` alone
- **Scale** — reverse index + barrel invalidation so one edit doesn’t re-scan the monorepo
- **MCP tools** — optional server for Claude, Cursor, Cline, and other MCP clients
- **Zero core dependencies** — stdlib only; forks can add their own stack on top
- **Agent navigability** — short **AGENT MAP** docstrings on core modules; self-tests under `tests/` (not buried in parsers)

## Performance (measured)

Full / heavy runs (historical order-of-magnitude):

| Project | Scale | Full / heavy `update-maps` |
|---------|-------|----------------------------|
| llama_index | ~3.8k Python files | ~8.5s class full |
| Babylon.js | ~3.9k TS files, barrel-heavy | minutes full; scoped re-runs tens of seconds |
| Large trees (e.g. LLVM-scale) | tens of thousands of files | use lean monitor + `--directory` / `--max-files` |

Warm **0-dirty** re-runs after 4.6.3 (same machine; scoped where noted) — agent session path:

| Project | Scope | Warm2 `update-maps` |
|---------|-------|---------------------|
| Wikifier (self) | incremental full | ~43 ms |
| redox | `src` | ~17 ms |
| llama_index | `llama-index-core` | ~0.6 s |
| rust | `library/std/src` (budgeted) | ~0.7 s (vs multi-second full-tree walk before scoped collect) |

Tests: `python -m unittest discover tests` (stdlib only; 86+ cases including agent-scale edges).

## Commands

| Command | Purpose |
|---------|---------|
| `wikifier init [--target DIR]` | Bootstrap project + human `index.html` |
| `wikifier session-bootstrap` | Session start: health, attention, dispatchable `actions[]` |
| `wikifier check-changes` | Content-honest scan → health / pending |
| `wikifier prepare-edit <file>` | Preflight: status, wiki snippet, deps, dependents |
| `wikifier record-change <file> "reason"` | Log *why* (required after edits) |
| `wikifier mark-green <file>` | Mark wiki current + source content-hash baseline |
| `wikifier record-deletion <file> "reason"` | Mark removed paths 🔴 + prune barrel refs |
| `wikifier suggest-next` | Next actions (🔴/actionable 🟡 only; `--json` for `actions[]`) |
| `wikifier update-maps [--directory=src/] [--max-files=N]` | Rebuild graph + `library.md` (warm 0-dirty is fast) |
| `wikifier health [--summary\|--json]` | Health matrix (machine-friendly flags) |
| `wikifier validate` | Missing wiki rows + ghost paths |
| `wikifier cycles` | Circular deps + break hints |
| `wikifier monitor` / `daemon` | Background maintenance (`WIKIFIER_DAEMON_MAPS=0` for check-only) |
| `wikifier serve` | Localhost dashboard with Run/Stop |

Library: `from wikifier import session_bootstrap, prepare_edit, check_changes, record_change, mark_green, suggest_next_actions, update_maps, health, list_core_tools`.

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

**Agent navigability:** Prefer protocol ([`skills/run.md`](skills/run.md)) + MCP Core 6 over reading 20k LOC of parsers/cache. Production modules carry a short **AGENT MAP** docstring; self-tests live under `tests/` and `tests/selftest/`, not inline at the bottom of parsers.

## Links

- [PyPI](https://pypi.org/project/wikifier/) · [GitHub](https://github.com/IronAdamant/wikifier)
- Agent protocol: [`skills/run.md`](skills/run.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Dogfood notes: `Findings/`
