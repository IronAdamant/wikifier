# Agent-scale perf + accuracy (4.6.3) — 2026-07-12

**subid:** agent-scale-perf-accuracy  
**Package:** 4.6.3  
**Focus:** agents (map lookup + selective touch), not human dashboard.

## What changed (zero-dep)

1. **Zero-dirty fast path** in `run_full_update`: when nothing needs reparse, skip graph rebuild + library.md rewrite; reuse cache + existing `library.md`.
2. **Content-hash map dirty**: cache entries store `content_hash`; mtime thrash with unchanged bytes does not reparse.
3. **Scoped candidate collect**: `--directory=` walks only that subtree (git pathspec or scandir) — monorepo agents no longer pay full-tree walk for a package scope.
4. **ACS v1.3**: stable `reason_code` + `agent_signal` (`skip`|`investigate`); scores unresolved edges; demotes external/dynamic noise; `reason_code_counts` for work selection.
5. **Rust `crate::` / `super::` resolve** to on-disk modules (best-effort).
6. **`prepare_edit` missing file** → `success: false` + `error` (no silent empty OK).

## Perf (same machine; warm2 / 0-dirty where applicable)

| Target | Scope | Baseline warm2 ms | After warm2 ms | Δ |
|--------|--------|-------------------:|---------------:|---|
| Wikifier (self) | full incremental | 94.7 | **42.9** | −55% |
| redox | `src` max 100 | 172.7 | **17.0** | −90% |
| llama_index | `llama-index-core` max 150 | 2170.6 | **564.4** | −74% |
| rust | `library/std/src` max 40 | 3734.4 | **720.0** | −81% |

Strict wins on all measured warm2 paths. Scratch: implementer `perf_baseline.json` / `perf_after.json`.

## Accuracy / agent signal

- ACS `acs_version` **1.3** with `reason_code_counts` (e.g. self: external_or_bare / high_confidence_ok / low_confidence_internal / dynamic_literal).
- Agents should act on `actionable_low_conf_edges` + `reason_code=unresolved_project|low_confidence_internal`, not raw low_conf.
- `prepare_edit` on hubs (cli.py, llama_index core `__init__`, airflow configuration, rust random.rs) returns deps/dependents for “touch only what you need.”

## Dogfood (≥4 single-project roots under cloned_sample_projects)

Never used multi-repo parent as `project_root` (bootstrap on parent → `scope.ok=false` + warnings).

| Project | Ops | Result |
|---------|-----|--------|
| Wikifier | bootstrap, check_changes, prepare_edit, warm maps | success; fast path on warm2 |
| redox | scoped maps + prepare_edit | success; fast path |
| llama_index | scoped maps + prepare_edit | success; fast path |
| rust | scoped maps + prepare_edit | success; max_files budget still reparses remaining dirty |
| airflow | scoped maps + prepare_edit | success; fast path |
| Babylon.js | scoped maps + prepare_edit | success; fast path |

## Tests

- `tests/test_agent_scale.py` — content-hash dirty, zero-dirty fast path, max_files honesty, ACS v1.3, rust resolve, prepare_edit missing.
- Full suite: **85** tests OK (`python3 -m unittest discover tests`).
- Edge battery: tiny tree, multi-repo parent warn, mtime thrash, scoped collect — PASS.

## Residuals (honest)

- Large `import_cache.json` load (e.g. llama_index ~21MB) still dominates warm fast path; future: sharded/SQLite cache (out of this change).
- `max_files` budgets leave residual dirty on huge scopes (rust std) until budget drains — by design.
- Multi-lang resolve still shallow outside Rust crate paths / existing Py+JS resolution.
- Human dashboard untouched (secondary).
