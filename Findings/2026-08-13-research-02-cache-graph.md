# Research 02 — Cache / graph / resolution (agent-first)

**Date:** 2026-08-13  
**Agent:** /deep-research + local explore (cache/graph slice)  
**Scope:** `import_cache.py`, `import_cache_impl.py`, `cache/`, `cache_store.py`, `candidates.py`, `resolution.py`, `contracts.py`, `library.py`, related tests

## Coverage

HEAD is **wrapper → impl megamodule → unused stubs**, not a finished `wikifier/cache/` package. Live path: `import_cache.py` → `cache/__init__.py` → `from ..import_cache_impl import *`. Nothing imports `cache/io.py` or `cache/files.py`. Planned `graph.py` / `cycles.py` / `acs.py` / `barrel.py` / `diagnostics.py` / `streaming.py` are absent.

Stub `files.py` **diverges** (raw hex hash vs impl `sha256:` prefix; missing `imports`/`resolved`; imports missing `cache.barrel`).

## Findings

| Axis | Pri | Path | Finding | Change |
|------|-----|------|---------|--------|
| Modularised | P0 | `import_cache_impl.py` 2589 + `cache/` | Package is a star-reexport of the megamodule. | Split impl into `cache/{io,files,graph,cycles,acs,barrel,diagnostics}.py` using **impl** APIs. Delete `import_cache_impl.py`. Overwrite stub `io.py`/`files.py`. |
| Simplified | P0 | Triple stack | wrapper + impl + unused stubs. | One shim (`import_cache`) + one package (`cache/`) + `cache_store`. |
| Improved | P1 | `compute_cycles` + `api.run_full_update` | `_graph_signature` is never set on the update path → Tarjan+CIABRE every dirty run. | Persist `set_graph_signature` in compute / persist. Test reuse **without** manual set. |
| Improved | P1 | `cache_store.save_cache_dict` | Full DELETE+INSERT of all file+meta rows every save. Barrel merge does `load_cache_dict` (full hydrate) if keys missing. | Incremental upsert of changed rows; barrel merge via `load_meta`. |
| Improved | P1 | `api.py` persist | Always `rebuild_reverse_dependencies` (O(E)); incremental `maintain_reverse_dependencies_for_source` exists and is unused. | Delta reverse on incremental persist; full rebuild on `--full`. |
| Improved | P0 | `api.check_changes` | Always `load_cache()` for barrel even when dirty is empty (full pair hydrate). | Skip barrel merge / use `load_meta` when dirty empty. |
| Modernised | P1 | `cache_store._connect` | New connection + WAL pragma every call. | Reuse connection per operation batch. |
| Simplified | P1 | `generate_update_events` ~470 lines | Second unused update engine (JS+Py only). | Do not treat as the split. Keep importable; do not load on hot path. |

## Must-do

1. Real `cache/` split from impl; delete `import_cache_impl.py`.
2. Keep `from wikifier.import_cache import …` working.
3. Register `_candidate_list`, `_map_coverage`, `_reverse_signature` in `RESERVED_TOP_LEVEL_KEYS`.
4. Persist graph signature; incremental SQLite upsert; skip full cache load on warm check-changes.

## Do not

- Wire current stub `files.py` as-is (would break hash tests).
- Dual-write JSON (already default-off).
- Split `contracts.py` / `resolution.py` in this wave.
