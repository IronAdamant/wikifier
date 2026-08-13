# Research 03 — Health / workflow / protocol (agent-first)

**Date:** 2026-08-13  
**Agent:** /deep-research + local explore (health/protocol slice)  
**Scope:** `health_impl.py`, `health_pkg/`, `agent_loop.py`, `locking.py`, `daemon.py`, `api` Core-6, `skills/run.md` honesty only

There is **no** `wikifier/health.py` source. Module is `health_pkg` stuffed into `sys.modules["wikifier.health"]`. `from wikifier import health` remains the **function**.

## Findings

| Axis | Pri | ID | Finding | Change |
|------|-----|----|---------|--------|
| Modularised | P1 | H1 | `health_pkg` is `from ..health_impl import *`. Planned io/pending/status/analysis/healing split not done (2504-line megamodule). | Split into `health_pkg/{io,pending,status,hashing,mapfirst,analysis,healing}.py`; keep `sys.modules` hack + `health_module`. Delete leftover `__main__` CLI or leave unused. |
| Improved | P0 | H3 | `record_change` never calls `record_meaningful_edit`. Stale-wiki (`last_meaningful_edit > last_wiki_refresh`) is theater. | Call `_do_record_meaningful_edit` under the existing lock. |
| Improved | P0 | H4 | Heal predicate tests `"Initial stub" in status`. Real stubs are Yellow + reason `"Initial stub —"`. | Use `_is_map_first_stub_entry`. |
| Improved | P0 | H5 | Thin CLI dropped protocol commands (`prepare-edit`, `record-deletion`, `validate`, `why-file`, …). | Restore hybrid CLI (see research 04). |
| Improved | P0 | H6 | MCP `workflow.py` passes `format=` / wrong positional args to `api` → TypeError. | Match `api` signatures. |
| Improved | P0 | H7 | `check_changes` does per-file `upsert` → full JSON+MD rewrite (cap 2000; daemon 30s). | One load, in-memory upserts, one save. |
| Improved | P1 | H8 | `_do_mark_green` saves the matrix three times. | Single save. |
| Modernised | P1 | H11 | Every `session_bootstrap` writes metrics (`staging.rglob` byte walk). | `write_metrics=False` on bootstrap; metrics on daemon interval. |
| Simplified | P2 | H2 | Health function vs module shadowing still hurts agents. | Keep hack; prefer `health_module`. Do not rename `health()` this wave (breaking). |

## Must-do

1. Restore CLI protocol verbs (H5).
2. Fix MCP workflow kwargs (H6).
3. `record_change` → `last_meaningful_edit` (H3).
4. Heal predicate (H4).
5. Batch `check_changes` health writes (H7).
6. Real `health_pkg` split if time; otherwise do not add more wrappers.

## Protocol honesty

Do **not** rewrite `skills/run.md` except a short additive note after CLI restore. Available Commands still say “mtime scan” / “stage mtime”; code entry still says `health.py`. v0.6.1 additive note only if I/O names change.
