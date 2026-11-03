# Wikifier

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

## Install

Download a binary from the [GitHub releases](https://github.com/IronAdamant/wikifier/releases). A `v*.*.*` tag publishes these archives and a `SHA256SUMS` file:

| Platform | Archive |
|---|---|
| Linux x86_64 | `wikifier-<version>-x86_64-unknown-linux-gnu.tar.gz` |
| macOS Apple silicon | `wikifier-<version>-aarch64-apple-darwin.tar.gz` |
| macOS Intel | `wikifier-<version>-x86_64-apple-darwin.tar.gz` |
| Windows x86_64 | `wikifier-<version>-x86_64-pc-windows-msvc.zip` |

Check `SHA256SUMS`, unpack, and put `wikifier` (`wikifier.exe` on Windows) on your `PATH`.

```bash
# Linux x86_64, 5.0.0
curl -fsSL -O https://github.com/IronAdamant/wikifier/releases/download/v5.0.0/SHA256SUMS
curl -fsSL -O https://github.com/IronAdamant/wikifier/releases/download/v5.0.0/wikifier-5.0.0-x86_64-unknown-linux-gnu.tar.gz
sha256sum --check --ignore-missing SHA256SUMS
tar -xzf wikifier-5.0.0-x86_64-unknown-linux-gnu.tar.gz
./wikifier --version
```

Or build from source. `[dependencies]` is empty:

```bash
git clone https://github.com/IronAdamant/wikifier
cd wikifier
cargo build --release
./target/release/wikifier --version
```

`pip install wikifier` still installs the archived Python 4.7 package.

**A zero-dependency codebase wiki for AI agents.** Token-efficient maps so LLMs look things up instead of re-reading full sources.

Wikifier is an **agent-to-agent** tool: it builds a living map of a project (health matrix, dependency graph, short file summaries) and agents keep that map current as they work. Humans can peek via a small dashboard; the product is the agent loop, not a general docs site or IDE.

Agents working in this repository start at [`AGENTS.md`](AGENTS.md). The day-to-day contract is [`skills/run.md`](skills/run.md).

Works from small scripts to large monorepos. **Deep import/include maps** (zero-dependency parsers):

| Language | Extensions | Notes |
|----------|------------|--------|
| Python | `.py` | comment-masked regex; relative imports and same-tree module paths; an indented import is flagged conditional |
| JavaScript / TypeScript | `.js` `.ts` `.jsx` `.tsx` `.mjs` `.cjs` `.mts` `.cts` | comment-masked regex; named re-exports followed to depth 8; `import()` flagged dynamic |
| Rust | `.rs` | `mod`, `use`, `crate::`, `self::`, `super::`, and package or lib names from the root `Cargo.toml` and from `[workspace] members` (globs included). `-` becomes `_`. A member name points at that member's library. `crate::` stays inside the crate that owns the file, including `tests/` and `src/bin/` |
| Go | `.go` | `import` / import blocks |
| C / C++ | `.c` `.h` `.cpp` `.cc` `.cxx` `.hpp` `.hh` | `#include` (local + system) |
| C# | `.cs` | `using` namespaces |
| Java | `.java` | `import` / `import static` |

JavaScript and TypeScript resolution also reads `tsconfig.json` `paths`, `package.json` `exports`, and npm `workspaces`. Health/journal still work for any monitored path. The non-Python parsers are pragmatic regex (not full cargo/`go.mod`/classpath/`-I` resolution). On huge monorepos, split scope deliberately:

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
cargo build --release           # std-only Rust binary — no crates.io dependencies
./target/release/wikifier --version

cd /path/to/your/project
./path/to/wikifier init         # seeds lean path-list templates
# Edit monitored_paths.txt + map_paths.txt to package roots (not bare ".") on real trees
wikifier update-maps            # full structural map → library.md + import cache
wikifier health --summary       # matrix counts
wikifier suggest-next           # or MCP suggest_next_actions — 🔴/🟡 only
```

Always set an explicit root for external trees: `WIKIFIER_PROJECT_ROOT=/abs/path wikifier …`

**MCP `session_bootstrap` → `readiness: blocked`?** That means lean scope and/or the map are missing (often bare `.` monitor + never ran `update-maps`) — not a broken install. Fix: write lean `monitored_paths.txt` / `map_paths.txt`, then `update-maps`. Agent contract: **`skills/run.md`** § *Readiness*.

## Steady state (only touch what needs it)

Full protocol: [`skills/run.md`](skills/run.md) (Agent Protocol v0.7 — package **5.0.0**).

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

- **Import analysis** — comment-masked regex for Python, JS/TS, Rust, Go, C/C++, C#, and Java. Named JS/TS re-exports are followed to depth 8. Edges carry conditional, dynamic, and via-barrel flags, and a confidence read from those flags.
- **Incremental pipeline** — `update-maps` parses files whose size or mtime changed, then writes the `wk_cache` text index, reverse edges, `library.md`, and sharded folder cards.
- **Two path lists** — `map_paths.txt` = map package roots; `monitored_paths.txt` = extra watch list (docs, scripts). `check-changes` always watches mapped files and anything ever marked Green, so a narrow list never hides edits.
- **Green you can trust** — `mark-green` checks the wiki against Python, JS/TS, and Rust public symbols and refuses when a public name is missing, a removed name is still in backticks, or the public surface changed while the wiki file did not. Rust names are unrestricted `pub` items, including methods and associated items on a public type and the items written in a trait impl for that type. `pub(crate)`, `pub(super)`, `pub(self)`, and `pub(in ...)` stay out of that set. Go, C/C++, C#, and Java are recorded as unchecked. `verify-wikis` re-checks every Green wiki. `health --summary` includes `green_breakdown`.
- **Partial-map honesty** — `--max-files` returns `map_complete=false` and `files_remaining_dirty`. Run the same command again to resume. Already-parsed files are stat-skipped.
- **Cache** — `.wikifier_staging/wk_cache`. `wikifier cache-status` reports the backend and the file count. An empty cache imports `import_cache.sqlite` through the `sqlite3` CLI, or `import_cache.json`.
- **Selective agent work** — health and `suggest-next` stay on 🔴 and actionable 🟡. Diagnostics list ACS reason codes and `actionable_low_conf_edges`.
- **Scale** — dependents and dependencies read one edge index. Unchanged files are skipped by size and mtime. `--full` rehashes.
- **MCP** — `wikifier mcp` in the same binary. A failed tool call sets `isError`. Calls stop at `WIKIFIER_MCP_DEADLINE_S` (default 60 seconds).
- **Zero core dependencies** — empty `[dependencies]` in `Cargo.toml`.
- **Honest failures** — a missing `project_root`, missing file, or lock timeout is an error result, never a silent fallback. `wikifier.sh` launches the Rust binary.

## Performance (measured)

Full / heavy runs (historical order-of-magnitude):

| Project | Scale | Full / heavy `update-maps` |
|---------|-------|----------------------------|
| llama_index | ~3.8k Python files | ~8.5s class full |
| Babylon.js | ~3.9k TS files, barrel-heavy | minutes full; scoped re-runs tens of seconds |
| Large trees (e.g. LLVM-scale) | tens of thousands of files | `map_paths` / `--directory` / `--max-files` — never unscoped one-shot |

Warm **0-dirty** re-runs after **4.6.7** (same machine class; scoped; candidates **reused** — agent session path). These numbers are from the Python package. This repo's map roots are now `src/` and `tests/`.

| Project | Scope | Warm `update-maps` | n |
|---------|-------|--------------------|---|
| Wikifier (self, Python era) | `map_paths`: `wikifier/` + `tests/` | **~30 ms** | 50 |
| llama_index | `llama-index-core` | **~76 ms** | 724 |
| rust | `library/std` | **~79 ms** | 719 |
| airflow | `airflow-core` | **~180 ms** | 1920 |
| Babylon.js | `packages` | **~400 ms** | 3895 |

Residual floor on large scopes is mtime/stat + live count under MapScope (not full JSON re-walk). Sub-100ms is not a hard SLA on every 1k+ tree.

## Benchmarks

Python 4.7 at `24812ef` versus the Rust binary recorded in [`scripts/benchmark_results.md`](scripts/benchmark_results.md) (that binary reported 4.7.0). 5.0.0 is that program. 5 runs, median milliseconds (min–max). Machine: Intel Xeon, 4 cores, 15.6 GiB RAM, Linux 6.12.94+, Python 3.12.3, rustc 1.83.0. Cold deletes `.wikifier_staging` first. Warm is the next `update-maps`. Full notes, peak RSS, and commands are in that file. Reproduce with `scripts/benchmark_parity.sh`.

| Command | small Python | small Rust | medium Python | medium Rust | large Python | large Rust |
|---|---:|---:|---:|---:|---:|---:|
| startup (`--version`) | 63 (61–66) | 2 (1–2) | same pair | same pair | same pair | same pair |
| cold update-maps | 123 (121–126) | 8 (7–13) | 167 (163–168) | 62 (59–73) | 12675 (12540–13094) | 3142 (3114–3305) |
| warm update-maps | 69 (67–72) | 4 (3–5) | 73 (72–74) | 4 (4–5) | 422 (417–433) | 246 (243–253) |
| session-bootstrap | 66 (64–67) | 2 (1–2) | 65 (64–67) | 2 (1–2) | 270 (269–278) | 21 (21–21) |
| check-changes | 64 (62–65) | 3 (2–3) | 70 (69–75) | 5 (5–6) | 1232 (1217–1266) | 74 (73–76) |
| health --summary | 60 (60–62) | 2 (1–2) | 60 (59–63) | 1 (1–2) | 109 (108–114) | 8 (8–9) |
| verify-wikis | 60 (60–61) | 2 (1–2) | 62 (60–67) | 1 (1–2) | 106 (103–108) | 8 (7–8) |
| cycles | 60 (60–61) | 2 (1–2) | 61 (60–63) | 2 (2–2) | 63 (61–64) | 54 (53–55) |

Resolved file edges after a warm map: small 2 and 2, medium (this repo) 44 Python and 98 Rust, large (Django `django/` + `tests/`, 2939 Python files) 9074 and 9074. Rust cold `update-maps` peak RSS was 3384 / 4424 / 40012 kbytes; Python was 27544 / 28392 / 97564 kbytes. The release binary is 2197456 bytes.

Small is three modules under `src/pkg`. Medium is `src/` and `tests/`. Large is a shallow clone of Django.

### Parser accuracy

`cargo test` checks internal edges on the frozen accuracy layouts:

| Fixture | 4.6.13 precision / recall | 4.7.0 precision / recall |
|---------|---------------------------|--------------------------|
| Django app (absolute app imports) | 1.00 / 0.29 | 1.00 / 1.00 |
| `src/`-layout package | 1.00 / 0.14 | 1.00 / 1.00 |
| TS monorepo (workspaces, paths, barrels) | 1.00 / 1.00 | 1.00 / 1.00 |
| Comment / string / regex traps | 0.29 / 0.67 | 1.00 / 1.00 |

Tests: `cargo test` (std-only Rust; accuracy fixtures, cache lookups, and the agent-loop commands).

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
| `wikifier suggest-next` | Next actions (JSON `actions[]`; `--text` for prose). Includes low-confidence edges when any exist |
| `wikifier update-maps [--directory=src/] [--max-files=N]` | Rebuild graph + human `library.md` + agent folder maps (warm 0-dirty is fast; honors `map_paths.txt`) |
| `wikifier cache-status` | `wk_cache` backend and mapped file count |
| `wikifier health [--summary\|--format text]` | Health matrix. Default is JSON. `--summary` is counts only. `--text` or `--format text` is prose |
| `wikifier validate` | Missing wiki rows + ghost paths |
| `wikifier cycles [--no-analysis] [--max-items N]` | Circular deps, break hints, severity, and who is most depended on |
| `wikifier heal-stubs [--dry-run]` | Promote Initial stubs whose wiki is at least 350 characters |
| `wikifier monitor` / `daemon` | Background maintenance (`WIKIFIER_DAEMON_MAPS=0` for check-only) |
| `wikifier serve` | Localhost dashboard with Run/Stop |

The same operations live in `src/api.rs`. Agents call the CLI or `wikifier mcp`. `wikifier.sh` / `wikifier.ps1` / `wikifier.bat` launch the Rust binary (`WIKIFIER_BIN` overrides the path). `pip install wikifier` still installs the archived Python 4.7 package.

## MCP

```bash
WIKIFIER_PROJECT_ROOT=/abs/path/to/project wikifier mcp
```

This repo's `.mcp.json` launches `wikifier` with argument `mcp`. Tool names and the daily loop are in [`skills/run.md`](skills/run.md).

## Human dashboard (secondary)

![Wikifier dashboard — file tree, health pills, local Run/Stop](https://raw.githubusercontent.com/IronAdamant/wikifier/main/screenshot/front_page_review.png)

`wikifier init` drops a single `index.html`. Prefer **`wikifier serve`** (e.g. http://localhost:8787/index.html) — `file://` can’t load project files. The markdown artifacts and CLI/MCP tools stay the source of truth; the UI is a read-only window.

`wikifier serve` also exposes a read-only JSON API (`/__wikifier/api/file?path=…`, `dependencies`, `dependents`, `cycles`, `journal`, `bootstrap`, `diagnostics`) that the dashboard uses for per-file dependencies and history. This repo also contains a proposed redesign, `index.v2.html` and `diagnostics.v2.html`, to compare side by side with the current pages (`http://localhost:8787/index.v2.html`); they are not deployed by `init`.

## Scope

**In:** agent-maintained codebase wiki, dependency intelligence, token-saving lookup for LLMs and coding agents.  
**Out:** general human documentation systems, IDE plugins, “docs for everyone” product growth.

**Agent navigability:** Prefer the protocol ([`skills/run.md`](skills/run.md)) and the MCP Core 6 over reading the parsers or the cache. Tests live in `tests/*.rs`.

## Links

- [Releases](https://github.com/IronAdamant/wikifier/releases) · [PyPI](https://pypi.org/project/wikifier/) · [GitHub](https://github.com/IronAdamant/wikifier)
- Agent protocol: [`skills/run.md`](skills/run.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Dogfood notes: `Findings/` (historical plans and research in `Findings/archive/`)
