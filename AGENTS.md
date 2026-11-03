# AGENTS.md

Entry point for any coding agent working in this repository, or using Wikifier on another tree. The day-to-day contract is `skills/run.md` (Agent Protocol v0.7, package 4.7.x). Read that file before substantive work. This file says what is live, what is history, and which rules are easy to miss.

## What this program is

Wikifier is a zero-dependency, agent-to-agent codebase wiki. Agents look up a health matrix, a dependency map, and short per-file wikis instead of re-reading full sources. The human dashboard (`index.html`) is a read-only view of the same artifacts.

The program is the std-only Rust binary under `src/`. Version is `Cargo.toml` (`wikifier --version`). `wikifier.sh`, `wikifier.ps1`, and `wikifier.bat` only exec that binary. MCP is `wikifier mcp` in the same binary. `.mcp.json` launches `wikifier` with args `["mcp"]`. There is no Python package. `pip install wikifier` and `python -m wikifier` are the archived product.

`src/main.rs` and `src/mcp.rs` both call `src/api.rs`. Every call returns JSON with `success`. An operational failure is `{"success": false, "error", "error_type"}`.

## Daily loop

On this repo, or on any Wikifier-managed tree:

1. `wikifier session-bootstrap` (MCP: `session_bootstrap`). For another project, pass `--target DIR` or `WIKIFIER_PROJECT_ROOT`. A missing root is an error.
2. Act on `actions[]`. Touch 🔴 Red, then actionable 🟡 Yellow. Leave 🟢 Green alone. Leave 🟡 Initial stubs alone until you edit that file.
3. `wikifier prepare-edit <file>` before a substantial edit.
4. After the edit: `wikifier record-change "<file>" "<why>"`. Include a short subid in the reason.
5. Refresh that file's `<file>.wiki.md` only.
6. `wikifier mark-green "<file>" "<why>"`.
7. `wikifier update-maps` only when imports or structure changed.

Many files: `wikifier record-changes -r "path/or/glob=why" --only <your files> --green`.

Prefer the CLI when the connected MCP server is still `python3 -m wikifier.mcp.server` or `wikifier-mcp`. Those entry points belong to the archived package and the handshake fails. Pass `project_root=` on every MCP call for a tree that is not the server's cwd.

## Hard rules

- `Cargo.toml` keeps an empty `[dependencies]` list. Do not add a crates.io crate, a Python package, or a Node module.
- Do not hand-edit `library.md`, `file_health.md`, `file_health.json`, or `pending_updates.md`. `update-maps` rewrites `library.md`. Health and pending change only through the commands. They take `.wikifier_staging/.lock`.
- `init` copies `index.html` only when it is missing, and it does not clobber an existing path list. `diagnostics.html` stays in this repo. `index.v2.html` and `diagnostics.v2.html` are comparison pages and are not deployed.
- This repo's map roots are `src/` and `tests/` (`map_paths.txt`). `monitored_paths.txt` is the extra watch list for docs and `wikifier.sh`.
- The import scan is comment-masked regex, plus named JS/TS re-exports to depth 8 (`parser: "regex+reexport"`). An indented Python import is conditional. `import()` is dynamic. Rust resolves `mod`, `crate::`, `self::`, `super::`, and package or lib names from the root `Cargo.toml` and from `[workspace] members` (globs included, `-` to `_`). `crate::` stays in that file's crate (`tests/*.rs`, `src/bin/*.rs`, and each workspace member). A package or lib name points at that member's library, which is how `src/main.rs` and `tests/*.rs` show up as dependents. The accuracy gate is `accuracy_fixtures_match_frozen_edges` (the frozen layouts, including a Cargo crate). Do not describe the scan as a CPython `ast` walk, and do not claim it has been run on Babylon.js. It does not read tsconfig paths, package exports, or npm workspaces.
- `mark_green` checks Python, JS/TS, and Rust public names against the wiki. Rust names are unrestricted `pub` items, `pub` methods and associated items on a public type, and trait-impl items for a public type. `pub(crate)`, `pub(super)`, `pub(self)`, and `pub(in ...)` stay out. Go, C/C++, C#, Java, and Markdown come back `unchecked`. That is expected.
- `wikifier serve` binds `127.0.0.1:8787`. Do not bind port 8080.
- Do not set the project root to a parent that contains several repos.
- Git: honor hooks. Do not use `--no-verify`. Do not commit `.cursor/`, `target/`, or gitignored leftovers (`wikifier/*.pyc`, `build/`, `dist/`, `.venv-build/`).
- Do not add a new license badge or new copy that announces a public release. Leave the existing README badge as it is. The opening paragraphs of `docs/spec.md` are the original requirements note. The living rules are the Core Principles section.

## Where to look

| Need | Path |
|---|---|
| Protocol, commands, JSON shapes | `skills/run.md` |
| Module map | `CLAUDE.md` architecture section |
| Build and language table | `README.md` |
| How to add a command | `CONTRIBUTING.md`: implement in `src/api.rs`, dispatch from `src/main.rs` |
| This repo's map | `library.md` (generated), `.wikifier_staging/maps/` |
| One file | `<file>.wiki.md`, then `prepare-edit` |

`update-maps` writes `library.md` as a file tree, a Mermaid block capped at 80 edges, and the dependency table. Folder cards are `.wikifier_staging/maps/_root.json` and `maps/{prefix}/_index.json`. The cache is the text index `.wikifier_staging/wk_cache`. An empty cache can be filled from `import_cache.sqlite` via the `sqlite3` CLI, or from `import_cache.json`.

## History, leave it

These files still describe the deleted Python package. They are records. Do not implement them, and do not rewrite them to sound current.

- `Findings/archive/MODULARIZATION_PLAN.md`
- `Findings/archive/SIMPLIFICATION_PLAN_AND_LOG.md`
- `Findings/` and `Findings/archive/`
- `journal/` entries from before the Rust cutover
- Released sections of `CHANGELOG.md` (Unreleased is the live note)
- The original requirements narrative at the top of `docs/spec.md`

A checkout can still contain a gitignored `wikifier/` tree, `build/`, `dist/`, and bytecode. Those files are not the program. Do not delete them unless asked.

## Tests

`cargo test`. Parser changes keep `accuracy_fixtures_match_frozen_edges` green. After source edits here, also run `wikifier check-changes` and `wikifier health --summary`.

This repo currently has Initial-stub Yellow rows for mapped files that have no wiki yet (`src/jsonutil.rs`, `src/proc.rs`, `src/scope.rs`, `src/sha256.rs`, `src/timeutil.rs`, and several `tests/*.rs`). Wiki one of those only when you edit it.
