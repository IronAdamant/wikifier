# Research 05 — Packaging / tests / dogfood leftovers (agent-first)

**Date:** 2026-08-13  
**Agent:** /deep-research + local explore (packaging/tests/dogfood)  
**Scope:** `pyproject.toml`, CI, publish, tests, launchers, Findings dogfood notes, leftovers

## Findings

| ID | Pri | Finding |
|----|-----|---------|
| P1 | P0 | `wikifier-mcp` entry points at `server:main` which does not exist. |
| P2 | P0 | MCP intel/status stubs — Core/intel regression. |
| P3 | P0 | Thin CLI dropped documented commands; tests import **functions** so suite stays green. |
| P4 | P0 | Version still **4.6.9** (already published gap-amendment). Must bump (4.6.10). Do not re-tag 4.6.9. Sitting `dist/wikifier-4.6.9-*` is **pre-split**. |
| P5 | P1 | New packages (`cache/`, `health_pkg/`, `parsers.javascript`, `mcp.tools`) will ship on next build; stub `cache/files.py` would ImportError if imported. |
| P6 | P1 | Duplicate megamodules (JS ×2, server ×2, bree leftover). |
| P7 | P1 | CI: no wheel-install smoke, no `[mcp]` import, no `wikifier --help` command table. |
| P8 | P1 | 140 real library tests; **zero** shim/CLI/MCP entry tests. README still says 125. |
| P9 | P2 | `file_health.md` has `wikifier/health.py` 🔴 ghost; new modules unmonitored. |
| P10 | P2 | No post-split dogfood. July cloned scopes remain the representative set (do **not** unbounded-scan linux/llvm/rust). |

Zero-dep (`dependencies = []`) is intact. COBOL parser is **not** required; unknown langs already skip.

## Must-do

1. Fix MCP/CLI entry points (P1–P3).
2. Bump to **4.6.10** + CHANGELOG (modularization + contract restore + perf). `test_version_is_4_6` only checks `startswith("4.6.")`.
3. CI smoke: `hasattr(server, "main")` + `python -m wikifier --help` lists restored commands.
4. Delete duplicate megamodules.
5. Dogfood after the fix using the July scoped command set + COBOL root + two subprojects.

## Do not

- Republish 4.6.9.
- Touch `index.html` / `diagnostics.html` / `serve.py` UX.
- Add core runtime deps.
- Invent a COBOL parser.
