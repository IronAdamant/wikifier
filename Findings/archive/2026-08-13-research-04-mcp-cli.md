# Research 04 — MCP / CLI / API surface (agent-first)

**Date:** 2026-08-13  
**Agent:** /deep-research + local explore (MCP/CLI/api slice)  
**Scope:** `cli.py`, `api.py`, `mcp/server*.py`, `mcp/tools/*`, `pyproject.toml` entry points, public `from wikifier import …`

**Verdict:** half-finished extract. Library imports still work. **`wikifier-mcp` is broken.** `python -m wikifier` dropped protocol CLI commands. Intel MCP tools are stubs. This is a **public-contract regression**.

## Findings

| ID | Pri | Axis | Finding |
|----|-----|------|---------|
| C1 | P0 | Modularised badly | `wikifier-mcp = wikifier.mcp.server:main` but live `server.py` (28 lines) has **no `main()`**. |
| C2 | P0 | Modularised badly | `intel.py` all 6 tools return `"Not yet implemented"`. |
| C3 | P0 | Modularised badly | Status stubs: `get_project_status`, `get_files_needing_attention`, `get_incremental_status`. |
| C4 | P0 | Simplified too far | Workflow wrappers pass kwargs `api` does not accept (`format=`; `search_journal(query)` as first positional = `project_root`). |
| C5 | P0 | Simplified too far | CLI lost `prepare-edit`, `record-deletion`, `validate`, `why-file`, `search-journal`, `seed-source-hashes`, and shell-forward for `init`/`monitor`/`daemon`/`serve`/`journal`. |
| C6 | P1 | Modularised sloppy | `server_impl.py` ≡ `server_backup.py` (2241 lines each, unimported). `_common.py` instantiates a **second unused** FastMCP. |
| C7 | P1 | Tests | Zero tests for `cli.main` argv or `server.main` existence. Suite stays green while contracts are dead. |

Library `from wikifier import check_changes, health, update_maps` **still works** via `cli` re-export of `api`. Zero-dep core intact.

## Must-do

1. Restore `main()` on live `server.py` (re-export complete `server_impl.mcp` + `main` until tools are fully ported — **do not ship stubs**).
2. Delete `server_backup.py` (identical corpse).
3. Fix workflow kwargs to match `api`.
4. Restore hybrid CLI `main()` from 4.6.9 (Python-primary commands + `wikifier.sh` fallback).
5. Tests: `hasattr(server, "main")`; `cli.main` argv for `prepare-edit` / `record-deletion` / `session-bootstrap`; intel tools not stubs.

## Perf

- Stop eager `from . import mcp` in `wikifier/__init__.py` (library users should not boot FastMCP).
- CLI `--help` should not import parsers/cache (lazy api imports where cheap).
- Re-port `get_barrel_reports` 10s TTL if intel stays on impl (already there).
