# Wikifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**A zero-dependency codebase wiki for AI agents** — token-efficient maps so LLMs look things up instead of re-reading full sources.

Wikifier is an **agent-to-agent** tool: it builds a living map of a project (health matrix, dependency graph, short file summaries) and agents keep that map current as they work. Humans can peek via a small dashboard; the product is the agent loop, not a general docs site or IDE.

Works from small scripts to large monorepos. **Deep import/include maps** (zero-dependency parsers):

| Language | Extensions | Notes |
|----------|------------|--------|
| Python | `.py` | stdlib `ast`; absolute, relative and `from pkg import submodule` imports; guarded imports flagged |
| JavaScript / TypeScript | `.js` `.ts` `.jsx` `.tsx` `.mjs` `.cjs` `.mts` `.cts` | tsconfig paths, package `exports`, workspaces, barrel chains; comments/strings ignored |
| Rust | `.rs` | `use` / `mod` / `extern crate` |
| Go | `.go` | `import` / import blocks |
| C / C++ | `.c` `.h` `.cpp` `.cc` `.cxx` `.hpp` `.hh` | `#include` (local + system) |
| C# | `.cs` | `using` namespaces |
| Java | `.java` | `import` / `import static` |

Health/journal still work for any monitored path. The non-Python parsers are pragmatic regex (not full cargo/`go.mod`/classpath/`-I` resolution). On huge monorepos, split scope deliberately:

| File | Surface |
|------|---------|
| **`map_paths.txt`** | Package roots for **import maps** (`update-maps` walk). Prefer package dirs (`src/`, `packages/foo/`) — not a wiki-only file list. |
| **`monitored_paths.txt`** | **Wiki / health** watch list (can be individual `.md` files). Does **not** define the map. |

Or pass `--directory=pkg/` / `--max-files=N` per run. Raise dirty cap with `WIKIFIER_CHECK_CHANGES_MAX` (default 2000) only when needed. Never set `project_root` to a multi-repo parent of clones.

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
wikifier init                   # seeds index.html + lean path-list templates
# Edit monitored_paths.txt + map_paths.txt to package roots (not bare ".") on real trees
wikifier update-maps            # full structural map → library.md + import cache
wikifier health --summary       # matrix counts
wikifier suggest-next           # or MCP suggest_next_actions — 🔴/🟡 only
```

Always set an explicit root for external trees: `WIKIFIER_PROJECT_ROOT=/abs/path wikifier …`

**MCP `session_bootstrap` → `readiness: blocked`?** That means lean scope and/or the map are missing (often bare `.` monitor + never ran `update-maps`) — not a broken install. Fix: write lean `monitored_paths.txt` / `map_paths.txt`, then `update-maps`. Agent contract: **`skills/run.md`** § *Readiness*.

## Steady state (only touch what needs it)

Full protocol: [`skills/run.md`](skills/run.md) (Agent Protocol v0.7 — package **4.7.x**).

```bash
wikifier session-bootstrap      # one-shot: root, health, attention, actions[], names-only map_index
wikifier check-changes          # content-honest dirty; red ghosts (missing paths)
# prioritize 🔴 then *actionable* 🟡 — do NOT re-wiki 🟢 Green files
wikifier prepare-edit path/file.py   # wiki + status + deps/dependents preflight
# ... edit only those sources ...
wikifier record-change "path/file.py" "why this changed"   # required
# ... refresh that file’s wiki summary only ...
wikifier mark-green "path/file.py"   # refused if the wiki misses public symbols you added/removed
# many files at once (reasons per path, glob or dir/; git supplies the file list):
wikifier record-changes -r "src/api/=retry on 429" -r "tests/=cover retries" --only src/ --only tests/ --green
wikifier update-maps            # only if imports/structure changed (warm 0-dirty is cheap)
# removals:
wikifier record-deletion "path/gone.py" "why removed"
```

**Core 6** (prefer every session — MCP or library/CLI):  
`session_bootstrap` → `check_changes` → `prepare_edit` → `suggest_next_actions` (json `actions[]`) → `record_change` → `mark_green`.

Advanced intel as needed: `list_paths` (names-only folder expand), `get_dependencies`, `get_dependents`, `get_cycles`, barrels/diagnostics. Always pass `project_root=` / `WIKIFIER_PROJECT_ROOT` for external trees. **Never** point `project_root` at a multi-repo parent folder (e.g. a directory of clones).

**Map split:** `update-maps` writes two views from the same import cache — human `library.md` (File Tree + mermaid, dashboard only) and sharded agent folder cards (`.wikifier_staging/maps/`, depth-1). Bootstrap returns the root card; `list_paths` expands one folder; `prepare_edit` follows file-to-file links. Do **not** read `library.md` mermaid for orientation.

## What you get

- **Import analysis** — Python (`ast`), JS/TS (ESM/CJS, barrels), Rust (`use`/`mod` + best-effort `crate::` paths), Go, C/C++ includes, C# usings, Java; per-edge confidence; barrel expansion for TS/JS
- **Incremental pipeline** — pure-Python `update-maps`: dirty parse → import cache → reverse deps → cycles → `library.md`
- **Warm agent maps (4.6.3–4.6.7)** — zero-dirty + **index-first** candidates (re-list only when fingerprint / map-scoped index / live count disagree); **MapScope** keeps collect, live count, index filter, and prune aligned; **stdlib SQLite**; content-hash dirty
- **Two path lists** — `map_paths.txt` = map package roots; `monitored_paths.txt` = extra watch list (docs, scripts). `check-changes` always watches mapped files and anything ever marked Green, so a narrow list never hides edits
- **Green you can trust** — `mark-green` checks the wiki against the code's public symbols (Python, JS/TS) and refuses when added symbols are undocumented or removed ones are still referenced; `verify-wikis` audits every Green wiki; `health --summary` splits Green into verified / no-wiki / forced
- **Partial-map honesty** — `map_coverage` on `update_maps` / bootstrap / **`suggest_next`**; `update_maps_until_complete` when incomplete
- **Cache ops** — `wikifier cache-status`; JSON dual-write **deprecated default-off** (`WIKIFIER_CACHE_JSON=1` opt-in); dual-read for migrate
- **Selective agent work** — health + suggest bias to 🔴/actionable 🟡 only; **ACS v1.3** `reason_code` / `agent_signal`; prefer `actionable_low_conf_edges` + reason codes — **never** raw `low_conf_edges` averages alone
- **Scale** — indexed edge table (dependents/dependencies without loading the cache), exact barrel invalidation, nanosecond-mtime dirty checks (unchanged files are never re-read)
- **MCP tools** — optional server for Claude, Cursor, Cline, and other MCP clients
- **Zero core dependencies** — stdlib only; forks can add their own stack on top
- **Honest failures** — a missing `project_root`, missing file or lock timeout is an error result, never a silent fallback; every command is plain Python (the shell launchers just exec `python -m wikifier`)

## Does it pay off? (measured)

`scripts/benchmark_lookup.py` asks the questions an agent asks before an edit, on real repositories, answered by Wikifier and by grep, scored against Python's own bytecode import scanner ([details](Findings/2026-10-01-lookup-benchmark.md)). 40 targets per repo:

| Question | Repo | Wikifier: exactly right / median tokens | grep: exactly right / median tokens |
|---|---|---|---|
| Which files import M? | llama-index-core (724 files) | **40/40** · 72 | 27/40 · 84 |
| | airflow-core (1,143 files) | **39/40** · 111 | 23/40 · 266 |
| What could break if I change M? (depth 3) | llama-index-core | **40/40** · 487 | 11/40 · 209 (15 over a 200k-token budget) |
| | airflow-core | **36/40** · 584 | 12/40 · 21,676 (8 over budget) |
| What does M import? | both | **40/40** · ~270 | reading the file: ~1,100 |

Typical lookups cost about the same; grep goes wrong on common module names (`base`, `utils`) and its cost explodes on them (up to 100k tokens for one question). Mapping from scratch: 2.3 s for 724 files, 21 s for 7,174.

## Performance (measured)

Full / heavy runs (historical order-of-magnitude):

| Project | Scale | Full / heavy `update-maps` |
|---------|-------|----------------------------|
| llama_index | ~3.8k Python files | ~8.5s class full |
| Babylon.js | ~3.9k TS files, barrel-heavy | minutes full; scoped re-runs tens of seconds |
| Large trees (e.g. LLVM-scale) | tens of thousands of files | `map_paths` / `--directory` / `--max-files` — never unscoped one-shot |

Warm **0-dirty** re-runs after **4.6.7** (same machine class; scoped; candidates **reused** — agent session path):

| Project | Scope | Warm `update-maps` | n |
|---------|-------|--------------------|---|
| Wikifier (self) | `map_paths`: `wikifier/` + `tests/` | **~30 ms** | 50 |
| llama_index | `llama-index-core` | **~76 ms** | 724 |
| rust | `library/std` | **~79 ms** | 719 |
| airflow | `airflow-core` | **~180 ms** | 1920 |
| Babylon.js | `packages` | **~400 ms** | 3895 |

Residual floor on large scopes is mtime/stat + live count under MapScope (not full JSON re-walk). Sub-100ms is not a hard SLA on every 1k+ tree.

### Parser accuracy

`python scripts/parser_accuracy.py` measures precision/recall of internal edges on small realistic layouts (`tests/accuracy_fixtures.py`):

| Fixture | 4.6.13 precision / recall | 4.7.0 precision / recall |
|---------|---------------------------|--------------------------|
| Django app (absolute app imports) | 1.00 / 0.29 | 1.00 / 1.00 |
| `src/`-layout package | 1.00 / 0.14 | 1.00 / 1.00 |
| TS monorepo (workspaces, paths, barrels) | 1.00 / 1.00 | 1.00 / 1.00 |
| Comment / string / regex traps | 0.29 / 0.67 | 1.00 / 1.00 |

Tests: `python -m unittest discover tests` (stdlib only; 260+ tests including one regression test per 4.7.0 fix, the accuracy fixtures and the benchmark harness).

## Commands

| Command | Purpose |
|---------|---------|
| `wikifier init [--target DIR]` | Bootstrap project + human `index.html` |
| `wikifier session-bootstrap` | Session start: health, attention, `actions[]`, names-only `map_index` |
| `wikifier check-changes` | Content-honest scan → health / pending |
| `wikifier prepare-edit <file>` | Preflight: status, wiki snippet, deps, dependents |
| `wikifier list-paths [prefix]` | Depth-1 folder card (names only). `--recursive` / `--depth=0` for a subtree. Then `prepare-edit` for file links. |
| `wikifier record-change <file> "reason"` | Log *why* (required after edits) |
| `wikifier mark-green <file> [--force]` | Check the wiki against the code, then mark it current (`--force` + reason overrides) |
| `wikifier record-changes [-r PATH=WHY]… [--only P]… [--green] [--dry-run]` | Record every file git reports as changed, reasons per path/glob/`dir/`; nothing written if any reason is missing |
| `wikifier verify-wikis [dir]` | Re-check every Green wiki against its code (exit 1 on failures) |
| `wikifier record-deletion <file> "reason"` | Mark removed paths 🔴, drop them from the graph, prune barrel refs |
| `wikifier dependencies <file> [--full]` / `dependents <file>` | What a file imports (compact; `--full` for per-edge confidence records) / who imports it (JSON) |
| `wikifier suggest-next` | Next actions (🔴/actionable 🟡 only; `--json` for `actions[]`) |
| `wikifier update-maps [--directory=src/] [--max-files=N]` | Rebuild graph + human `library.md` + agent folder maps (warm 0-dirty is fast; honors `map_paths.txt`) |
| `wikifier cache-status` | SQLite/JSON backend, dual-write policy, coverage snapshot (no full pair load) |
| `wikifier health [--summary\|--json]` | Health matrix (machine-friendly flags) |
| `wikifier validate` | Missing wiki rows + ghost paths |
| `wikifier cycles [--json]` | Circular deps + break hints |
| `wikifier heal-stubs [--dry-run]` | Promote Initial stubs that now have a real wiki |
| `wikifier monitor` / `daemon` | Background maintenance (`WIKIFIER_DAEMON_MAPS=0` for check-only) |
| `wikifier serve` | Localhost dashboard with Run/Stop |

Library: `from wikifier import session_bootstrap, prepare_edit, list_paths, check_changes, record_change, record_changes, mark_green, verify_wikis, suggest_next_actions, update_maps, get_dependencies, get_dependents, cycles_report, health, init_project`.

`wikifier.sh` / `wikifier.ps1` / `wikifier.bat` are thin launchers for `python -m wikifier` (set `WIKIFIER_PYTHON` to pick the interpreter).

## MCP

```bash
WIKIFIER_PROJECT_ROOT=/abs/path/to/project wikifier-mcp
# or: python3 -m wikifier.mcp.server
```

Setup and tool list: [`wikifier/mcp/README.md`](wikifier/mcp/README.md).

## Human dashboard (secondary)

![Wikifier dashboard — file tree, health pills, local Run/Stop](https://raw.githubusercontent.com/IronAdamant/wikifier/main/screenshot/front_page_review.png)

`wikifier init` drops a single `index.html`. Prefer **`wikifier serve`** (e.g. http://localhost:8787/index.html) — `file://` can’t load project files. The markdown artifacts and CLI/MCP tools stay the source of truth; the UI is a read-only window.

`wikifier serve` also exposes a read-only JSON API (`/__wikifier/api/file?path=…`, `dependencies`, `dependents`, `cycles`, `journal`, `bootstrap`, `diagnostics`) that the dashboard uses for per-file dependencies and history. This repo also contains a proposed redesign, `index.v2.html` and `diagnostics.v2.html`, to compare side by side with the current pages (`http://localhost:8787/index.v2.html`); they are not deployed by `init`.

## Scope

**In:** agent-maintained codebase wiki, dependency intelligence, token-saving lookup for LLMs and coding agents.  
**Out:** general human documentation systems, IDE plugins, “docs for everyone” product growth.

**Agent navigability:** Prefer the protocol ([`skills/run.md`](skills/run.md)) + MCP Core 6 over reading the parsers/cache. Self-tests live under `tests/` and `tests/selftest/`.

## Links

- [PyPI](https://pypi.org/project/wikifier/) · [GitHub](https://github.com/IronAdamant/wikifier)
- Agent protocol: [`skills/run.md`](skills/run.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Dogfood notes: `Findings/` (historical plans and research in `Findings/archive/`)
