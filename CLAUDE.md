# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Wikifier is a **zero-dependency, agent-to-agent codebase wiki**: it gives AI agents a token-efficient, queryable map of a codebase (health matrix, dependency graph, per-file wiki summaries) so they can look things up instead of re-reading full sources. The human layer (`index.html` dashboard) is strictly secondary — a read-only viewer of the same artifacts. It is deliberately NOT a general human documentation tool.

**This repo dogfoods itself.** Wikifier runs on its own source, and you are expected to follow its agent protocol when working here (see below). The authoritative agent contract is `skills/run.md` (Agent Protocol v0.7 — package 4.7.x) — read it before substantive work.

**USE WIKIFIER FIRST (non-negotiable in this repo, preferred on any managed target):** At session start call `session_bootstrap` (MCP or `python -m wikifier session-bootstrap`). Prefer Core daily tools (`list_core_tools`): bootstrap, `check_changes`, `prepare_edit`, `suggest_next_actions` (json `actions[]`), `record_change`, `mark_green`. Look up via map/wiki/deps before re-reading full sources. Selective work only (🔴 / actionable 🟡). Never skip `record_change` after edits.

## Hard Constraints

- **NON-NEGOTIABLE: effectively zero-dependency.** The core must run on pure Python stdlib (>=3.8) + POSIX shell alone — `pyproject.toml` declares `dependencies = []` and that stays. The reason is architectural, not stylistic: anyone forking this project must be free to bring their own third-party libraries on top of a dependency-free base. Therefore: never add a runtime dependency, never couple core logic to an optional extra (the `mcp` extra must remain strictly optional and isolated to `wikifier/mcp/`), and never make core behavior degrade when nothing beyond the stdlib is installed.
- **`library.md`, `file_health.md`, `pending_updates.md` are generated/managed artifacts.** Never hand-edit `library.md` (overwritten by `update-maps`); mutate health/pending only through the official commands (they hold locks).
- **Human-layer separation:** only `index.html` is deployed to target projects on `init`. `diagnostics.html` is maintainer-only and stays in this repo. `index.v2.html` / `diagnostics.v2.html` are proposed redesigns kept in this repo for comparison (not deployed).
- Agent-to-agent scope only — do not grow features toward general human docs or IDE use.

## Mandatory Workflow (the project's own protocol)

After any source edit in this repo:

```bash
wikifier check-changes                                   # what's dirty; read file_health.md + pending_updates.md
# ... edit source (prioritize 🔴 Red, then 🟡 Yellow) ...
wikifier record-change "path/to/file" "why (semantic reason, include subid for agent work)"   # REQUIRED — never skip
# ... update the file's wiki entry (*.wiki.md or library summary) ...
wikifier mark-green "path/to/file" "reason"              # checks the wiki against the code's public symbols
# many files: wikifier record-changes -r "path/or/glob=why" --only <your files> --green
wikifier update-maps                                     # only when imports/structure changed
wikifier health --summary                                # re-validate at end of session
```

`record-change` is the semantic audit trail (journal + health + pending) — skipping it breaks the system's core value. For edits to agent-maintained docs (skills/run.md, README, Findings/M5-*.md), precede with "FRESH 3" hygiene: grep the target for 0 stale/deferred matches first.

The Wikifier MCP server may be connected (tools like `get_project_status`, `get_dependencies`, `get_file_wiki`, `record_change`, `mark_green`). Prefer MCP tools when available; the CLI/library is the battle-tested fallback (MCP can time out on very large barrel-heavy targets). For any external project, always pass explicit `project_root=` or `WIKIFIER_PROJECT_ROOT=`.

## Commands

```bash
pip install -e .                       # dev install (entry points: wikifier, wikifier-mcp)
python -m wikifier <command>           # equivalent to the wikifier entry point
./wikifier.sh <command>                # thin launcher: execs python -m wikifier (root copy == wikifier/scripts/ copy)
wikifier init [--target DIR]           # bootstrap a target project (copies only index.html)
wikifier update-maps [--full] [--directory src/] [--max-files N] [--stream]   # rebuild dependency graph + library.md
wikifier health [--summary|--json]     # health matrix (use --summary/--json for machine consumption)
wikifier dependencies|dependents <file>   # what a file imports (compact; --full for per-edge records) / who imports it
wikifier record-changes [-r PATH=WHY] [--only P] [--green] [--dry-run]   # batch record from git
wikifier verify-wikis                  # re-check Green wikis against their code
python scripts/benchmark_lookup.py REPO   # tokens + correctness of lookups vs grep (see Findings/2026-10-01-lookup-benchmark.md)
wikifier monitor                       # foreground check-changes loop
wikifier daemon {start|stop|status}    # managed background maintenance
WIKIFIER_PROJECT_ROOT=/abs/path wikifier-mcp   # MCP server (requires pip install wikifier[mcp])
./scripts/publish.sh [test|prod]       # PyPI release (build + twine)
```

**Tests:** `python -m unittest discover tests` (pure stdlib unittest — no pytest, per the zero-dependency rule; 260+ tests incl. `test_regressions_4_7.py`, `test_verification_and_batch.py`, the parser accuracy fixtures and the benchmark harness). Run it after any core change, plus `python scripts/parser_accuracy.py` after parser changes (must stay 1.00/1.00). Additionally verify by dogfooding: `wikifier check-changes`, `wikifier update-maps` (catches parse/pipeline errors), `wikifier health --summary`, and MCP smoke calls (`get_project_status`, `suggest_next_actions`), then confirm the artifacts (file_health.md, library.md) look right.

## Architecture

Pipeline: **scan → parse → resolve → cache → health → artifacts**, all under `wikifier/` (~21k LOC pure stdlib; package version in `wikifier/__init__.py`, currently **4.7.x**).

- `api.py` — the library surface (`check_changes`, `record_change`, `record_changes`, `mark_green`, `verify_wikis`, `record_deletion`, `update_maps`/`run_full_update`, `prepare_edit`, `get_dependencies`/`get_dependents`, `cycles_report`, `init_project`, …). `check_changes` watches mapped + Green + monitored files. `gitchanges.py` supplies the change set for `record_changes` (git optional). Every function returns `{"success": …}`; errors are reported, never fallen back from. `cli.py` is an argparse front end over it (every command is Python; the shell/PowerShell/batch launchers only exec `python -m wikifier`).
- `paths.py` — `resolve_root` (explicit root → env → discovery; a missing explicit root raises `ProjectRootError`) and `to_rel` (canonical project-relative POSIX keys). All file arguments go through `to_rel`. `project_root.py` holds marker discovery.
- `parsers/python.py` — stdlib `ast` (regex fallback); resolves relative, absolute (package root / project root / `src/`) and `from pkg import submodule` imports; marks imports under `if`/`try` conditional. `parsers/javascript.py` — regex over comment-masked source (`_lex_mask`), one edge per specifier, delegates resolution to `resolution.py`. Other languages: `rust.py`, `go_lang.py`, `c_cpp.py`, `csharp.py`, `java.py`. Shared edge contract in `parsers/_edge.py`.
- `parsers/cdia.py` — conditional/dynamic import analysis; `ScopeBuilder` finds only *enclosing* guards (braces for JS/TS, indentation for Python). `parsers/bree/` — barrel/re-export chain expansion with a persistent barrel cache (`_barrel_resolutions` / `_barrel_file_index`) used for exact stale-importer invalidation.
- `resolution.py` — single source of truth for JS/TS path canonicalization (symlinks, TS paths, package.json exports, workspaces). Identity goes through `to_canonical_rel`.
- `cache_store.py` — SQLite store: `files`, `edges(src,dst)` (indexed both ways), `meta`. `cache/` package (also importable as `import_cache`): `io`, `files` (nanosecond-mtime dirty detection), `graph` (reverse index, Tarjan, signatures), `cycles` (SCCs + breaking recommendations), `acs` (confidence summary, map coverage), `barrel`, `diagnostics`. Reserved keys start with `_`; derived summaries are recomputed every update-maps.
- `health_pkg/` (importable as `wikifier.health`) — `store` (file_health.json SSOT + .md view), `pending`, `freshness` (content hashes, stale wikis, mark-green), `verify` (wiki vs code: public symbols diffed against the last Green baseline; `mark_green` refuses undocumented changes unless forced), `scope` (monitored_paths, ghosts, seeding, pruning, validate), `summary`, `readiness`, `healing`. `_do_*` functions assume the caller holds the lock.
- `journal.py` — journal append (raises on failure; de-duplicates identical retries within 120 s), day reads, Logged_issues listing.
- `contracts.py` — frozen shared shapes (CDIA v1, barrel v2, ResolutionMetadata, `compute_acs_confidence`). New fields are additive only.
- `locking.py` — advisory project lock on `.wikifier_staging/.lock` (`fcntl`/`msvcrt`), re-entrant per thread. High-level tools lock automatically.
- `streaming.py` — `update-maps --stream` events from the real pipeline. `daemon.py` — background loop. `serve.py` — localhost dashboard server + read-only JSON API (`/__wikifier/api/*`). `map_index.py` — sharded folder cards. `library.py` — `library.md`.
- `mcp/server_impl.py` — optional MCP server: a thin adapter over `api.py` (no subprocess); `mcp/status_ops.py` + `mcp/deadline.py` for bounded status calls.

Generated artifacts (in the target project root): `file_health.md/.json`, `library.md` (Mermaid + dependency tables + ACS/cycle reports), `pending_updates.md`, `journal/YYYY/MM/DD.md` (audit trail), per-file `*.wiki.md`, `.wikifier_staging/` (SQLite cache, folder maps, locks, daemon state). Scoping for large repos: `monitored_paths.txt` (watch list, files or dirs), `map_paths.txt` (import-map roots), `exclude_patterns.txt`.

Adding a language = new `wikifier/parsers/{lang}.py` exposing `parse_{lang}_imports(filepath) -> List[Dict]` with the same edge contract, wired in `api._parser_for`, plus a fixture in `tests/accuracy_fixtures.py` (and, for wiki verification, a symbol extractor in `health_pkg/verify.public_symbols`).

## Versioning & Releases

- Version lives in `wikifier/__init__.py` (`__version__`); pyproject reads it dynamically. SemVer + Keep a Changelog format in `CHANGELOG.md`.
- Protocol versions (`skills/run.md`) are independent of package version; mandatory I/O changes require a protocol version bump with migration notes there.
- Agents must tolerate additive fields in dict returns; library returns always include `"success": bool`. Operational failures return `{"success": False, "error": ...}`; contract misuse raises.

## Repo Map (beyond the package)

- `skills/run.md` — the agent protocol (primary contract for any LLM operating Wikifier)
- `docs/spec.md` — spec and guiding principles
- `Findings/` — decisions and dogfood evidence (`README.md` index; superseded plans in `Findings/archive/`)
- `SIMPLIFICATION_PLAN_AND_LOG.md` — log of the simplification phases
- `file_health.md`, `pending_updates.md`, `journal/`, `library.md` — this repo's own live wiki state (dogfood)
