# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Wikifier is a **zero-dependency, agent-to-agent codebase wiki**: it gives AI agents a token-efficient, queryable map of a codebase (health matrix, dependency graph, per-file wiki summaries) so they can look things up instead of re-reading full sources. The human layer (`index.html` dashboard) is strictly secondary — a read-only viewer of the same artifacts. It is deliberately NOT a general human documentation tool.

**This repo dogfoods itself.** Wikifier runs on its own source, and you are expected to follow its agent protocol when working here (see below). `AGENTS.md` is the entry point for any coding agent. The authoritative contract is `skills/run.md` (Agent Protocol v0.7, package 4.7.x). Read it before substantive work.

**USE WIKIFIER FIRST (non-negotiable in this repo, preferred on any managed target):** At session start call `session_bootstrap` (MCP or `wikifier session-bootstrap`). Prefer Core daily tools (`list_core_tools`): bootstrap, `check_changes`, `prepare_edit`, `suggest_next_actions` (json `actions[]`), `record_change`, `mark_green`. Look up via map/wiki/deps before re-reading full sources. Selective work only (🔴 / actionable 🟡). Never skip `record_change` after edits.

## Hard Constraints

- **NON-NEGOTIABLE: zero third-party dependencies.** The program is a Rust binary with an empty `[dependencies]` list in `Cargo.toml`. Do not add crates.io crates. POSIX shell launchers only exec that binary. MCP is `wikifier mcp` in the same binary, not a Python extra.
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
cargo build --release                  # std-only binary: target/release/wikifier
./wikifier.sh <command>                # launches that binary (or cargo run)
wikifier init [--target DIR]           # bootstrap a target project
wikifier update-maps [--full] [--directory src/] [--max-files N] [--stream]
wikifier health [--summary|--json]
wikifier dependencies|dependents <file>
wikifier record-changes [-r PATH=WHY] [--only P] [--green] [--dry-run]
wikifier verify-wikis
wikifier monitor
wikifier daemon {start|stop|status}
wikifier mcp                           # MCP server on stdio
```

**Tests:** `cargo test`. Parser changes must keep `accuracy_fixtures_match_frozen_edges` green. Also dogfood: `wikifier check-changes`, `wikifier update-maps`, `wikifier health --summary`.

## Architecture

Pipeline: **scan → parse → resolve → cache → health → artifacts**, implemented in Rust under `src/` (version in `Cargo.toml`, currently **4.7.x**). The former Python package has been removed. CLI (`src/main.rs`) and MCP (`src/mcp.rs`) both call `src/api.rs`. Every function returns a JSON object with `success`. Operational failures return `{"success": false, "error", "error_type"}`.

- `src/api.rs` — the library surface: `session_bootstrap`, `check_changes`, `prepare_edit`, `suggest_next_actions`, `record_change`, `record_changes`, `record_deletion`, `mark_green`, `verify_wikis`, `update_maps` / `update_maps_run`, `dependency_report`, `load_dependents`, `cycles`, `init_project`, `serve_loop`, `monitor_loop`, `daemon_ctl`. `check_changes` watches mapped files, Green files, and `monitored_paths.txt`. `record_changes` reads `git status` (git is optional).
- `src/scope.rs` — project root, `map_paths.txt`, `monitored_paths.txt`, excludes, and the file walk. A missing configured map directory is a scope error. Three or more child projects make the root a container and the walk stops.
- `src/parse.rs` — comment-masked regex scans for Python, JS/TS, Rust, Go, C/C++, C#, and Java. Named JS/TS re-exports are followed to depth 8 (`via_barrel`). An indented Python import is `conditional`. `import()` is `dynamic`. JS/TS resolution reads `tsconfig.json` `paths`, `package.json` `exports`, and npm `workspaces`. Rust resolves `mod`, `crate::`, `self::`, `super::`, and package or lib names from the root `Cargo.toml` and `[workspace] members` (`-` to `_`, globs included). `crate::` stays in the file's crate; a member name points at that member's library. This is not a CPython `ast` parser. The accuracy gate is `accuracy_fixtures_match_frozen_edges`.
- `src/cache.rs` + `src/cache_commit.rs` — text index at `.wikifier_staging/wk_cache` (per-file payload, `by_src`, `by_dst`, notes, barrels). One commit per `update-maps`. Size and mtime skip unchanged files. `--full` rehashes. `src/legacy_cache.rs` imports an empty cache from `import_cache.sqlite` (the `sqlite3` CLI) or `import_cache.json`.
- `src/artifacts.rs` — `file_health.json` (schema version 2) plus the `file_health.md` view, pending lines, and the journal. Identical journal retries within 120 seconds are skipped. `mark_green` stores `public_symbols`, `wiki_hash`, and `source_mtime_ns`, and refuses a Python or JS/TS wiki that misses the current public names, still mentions a removed name in backticks, or is unchanged after the public surface changed.
- `src/maps_out.rs` — `library.md` (a file tree, a Mermaid block capped at 80 edges, and the dependency table) and sharded folder cards at `.wikifier_staging/maps/_root.json` and `maps/{prefix}/_index.json`.
- `src/project_lock.rs` — advisory lock `.wikifier_staging/.lock`, taken before the cache lock, re-entrant per thread, 30 second wait, stolen when the recorded pid is dead.
- `src/mcp.rs` — stdio JSON-RPC. `isError` follows `success: false`. `resources/read` and `prompts/get` are implemented. Deadline `WIKIFIER_MCP_DEADLINE_S` (default 60).

Generated artifacts (in the target project root): `file_health.md/.json`, `library.md`, `pending_updates.md`, `journal/YYYY/MM/DD.md`, per-file `*.wiki.md`, `.wikifier_staging/` (`wk_cache`, folder maps, `incremental_status.json`, locks, daemon state). Scoping: `monitored_paths.txt` (extra watch list), `map_paths.txt` (import-map roots), `exclude_patterns.txt`. This repo's map roots are `src/` and `tests/`.

Adding a language means a scan in `src/parse.rs` with the same edge shape, a frozen fixture kept green by `accuracy_fixtures_match_frozen_edges`, and, when wiki verification should refuse that language, a symbol extractor beside `python_public_symbols` / `js_public_symbols` / `rust_public_symbols`. Languages without an extractor are marked `unchecked`. Rust's extractor is `rust_public_symbols` in `src/parse.rs`.

## Versioning & Releases

- Version lives in `Cargo.toml` (`version`). SemVer + Keep a Changelog format in `CHANGELOG.md`.
- Protocol versions (`skills/run.md`) are independent of package version; mandatory I/O changes require a protocol version bump with migration notes there.
- Agents must tolerate additive fields in JSON returns. Every return includes `"success"`. Operational failures return `{"success": false, "error", "error_type"}`.

## Repo Map (beyond the package)

- `AGENTS.md` — entry point for any coding agent in this repo
- `skills/run.md` — the agent protocol (primary contract for any LLM operating Wikifier)
- `docs/spec.md` — original requirements, then the living Core Principles
- `Findings/` — dogfood evidence (`README.md` index; superseded plans in `Findings/archive/`). Historical. Do not treat it as the current design.
- `Findings/archive/SIMPLIFICATION_PLAN_AND_LOG.md`, `Findings/archive/MODULARIZATION_PLAN.md` — Python-era logs. Do not implement them.
- `file_health.md`, `pending_updates.md`, `journal/`, `library.md` — this repo's own live wiki state (dogfood)
