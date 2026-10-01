# Implementation plan — agent-first restore + real modularization (4.6.10)

**Date:** 2026-08-13  
**Inputs:** `Findings/2026-08-13-research-0{1-5}-*.md`  
**Constraint:** `dependencies = []`; public library + CLI + optional MCP contracts must succeed; no human-layer work.

HEAD (`1bd404c`) is an incomplete modularization: megamodules were copied, not deleted; CLI/MCP contracts regressed; version still 4.6.9.

## Goals

1. **Restore** agent-facing CLI and MCP (P0 contracts).
2. **Simplify** by deleting duplicate megamodules / backups / unused stubs.
3. **Modularise further** by finishing the real `wikifier/cache/` and `wikifier/health_pkg/` splits (impl APIs, then delete `*_impl` leftovers).
4. **Improve performance** on representative warm paths: skip full cache hydrate on empty dirty; incremental SQLite upsert; persist graph signature; batch health writes in `check_changes`.
5. **Modernise** lazy parser/MCP imports; `.mjs/.cjs` dispatch; tests that would have caught the regression.

## Work packages (do in order)

### WP0 — Tests that lock the contract (write first)

- `tests/test_agent_surface_contracts.py` (new):
  - `wikifier.mcp.server` has `main` and `mcp` (skip if extra missing).
  - Intel tools are not `"Not yet implemented"` when registered (or server_impl is the live `mcp`).
  - `cli.main` argv: `prepare-edit`, `record-deletion`, `session-bootstrap`, `health --summary` (tmpdir).
  - `from wikifier import check_changes, health` returns `success` / structured.
  - `import_cache.compute_file_content_hash` still `sha256:` prefix.
- Unskip `tests/test_barrel_invalidation.py` if green; otherwise fix BREE then unskip.
- Graph-signature reuse test: `save_cache` / `load_cache` / `compute_cycles` twice **without** manual `set_graph_signature`.

### WP1 — Restore CLI

Rewrite `wikifier/cli.py` as:

- Re-export public API from `wikifier.api` (keep `from wikifier.cli import check_changes`).
- Restore hybrid `main()` from 4.6.9 (`87c638e`): Python-primary for Core + `validate` / `seed-health` / `prune-*` / `autonomous-status` / `update-maps`; shell-forward via `get_script_path()` for `init` / `monitor` / `daemon` / `serve` / `journal` / `issues`.

Do **not** keep the argparse-only subset.

### WP2 — Restore MCP

- Live `server.py`: re-export `mcp` + `main` from `server_impl.py` (complete tool set + `--project-root` + `mcp.run()`).
- Delete `server_backup.py`.
- Fix `mcp/tools/workflow.py` kwargs to match `api` (no invented `format=`; `search_journal(project_root=, query=)`).
- Slim `_common.py` so it does **not** construct a second FastMCP (or stop importing it from unused stubs).
- Tools package may remain unused this wave; **do not register stubs**.

### WP3 — Delete parser decoys

- Delete `wikifier/parsers/javascript/` (`__init__.py`, `_parser.py`).
- Delete leftover `wikifier/parsers/bree.py`.
- Keep `javascript.py` + `bree/_bree.py`.
- Add `.mjs/.cjs/.mts/.cts` to `api._parse_file`.
- Lazy language imports in `parsers/__init__.py`.

### WP4 — Finish `wikifier/cache/`

Move **impl** bodies (not stubs) into:

| Module | From `import_cache_impl.py` |
|--------|-----------------------------|
| `cache/io.py` | load/save/mtime index |
| `cache/files.py` | file data, hash (`sha256:`), dirty |
| `cache/graph.py` | reverse + `build_dependency_graph` + signatures |
| `cache/cycles.py` | Tarjan, `compute_cycles`, CIABRE |
| `cache/acs.py` | noise classifiers, ACS, map coverage |
| `cache/barrel.py` | BRC index/invalidate/reports |
| `cache/diagnostics.py` | unresolved / low-conf / diagnostics |
| `cache/streaming.py` | keep `generate_update_events` importable (not hot path) |

Then: `cache/__init__.py` exports from those modules; `import_cache.py` stays `from .cache import *`; **delete `import_cache_impl.py`**.

Also:

- `compute_cycles` / persist: `set_graph_signature`.
- `save_cache_dict`: upsert changed file rows + meta; barrel merge via `load_meta`.
- Incremental reverse on `run_full_update` when not `--full`.
- `check_changes`: do not `load_cache()` when dirty is empty.

### WP5 — Health correctness + batch writes

- `record_change` → `_do_record_meaningful_edit` (same lock).
- Heal predicate → `_is_map_first_stub_entry`.
- `check_changes`: one `load_health`, in-memory yellows, one `_do_save_health`.
- `_do_mark_green`: single save if cheap.
- `session_bootstrap`: `assess_autonomous_readiness(..., write_metrics=False)`.
- Split `health_pkg` along planned seams **if** the file cut is mechanical and tests stay green; keep `sys.modules["wikifier.health"]`.

### WP6 — Version, maps, dogfood

- `__version__ = "4.6.10"` + CHANGELOG.
- `update-maps` on this repo after structural deletes (do not hand-edit `library.md`).
- Re-run scoped dogfood (cloned 8 + COBOL root + 2 subs) twice; fix crashes; confirm timings ≤ baseline, at least one primary command strictly faster.

## Non-goals

Human dashboard; COBOL parser; protocol rewrite; unbounded linux/llvm/rust/COBOL scans; adding runtime deps; republishing 4.6.9.

## Success

- 5 research `.md` + this plan on disk.
- `python -m unittest discover tests` ×2 green (includes new contract tests).
- `python -m wikifier health --summary` / `check-changes` / `prepare-edit` work.
- `wikifier.mcp.server.main` exists.
- Dogfood three roots OK; perf bar met.
- Commit + push + PyPI 4.6.10.
