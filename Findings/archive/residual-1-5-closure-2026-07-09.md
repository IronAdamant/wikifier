# Residual investigation items 1–5 closure (2026-07-09)

**Package:** 4.5.9  
**subid:** residual-1-5-closure  

## 1. Cyclic SCC (cli ↔ import_cache ↔ bree)

**Fix:** Extracted `discover_project_root` to `wikifier/project_root.py`.  
`import_cache`, `bree`, and `javascript` load-time helpers import `project_root` (not `cli`).  
CLI re-exports for public API stability.

**Evidence:** `update-maps` on Wikifier → `cycles.count: 0`; trio absent from `all_cycle_files`.  
Unit: `TestLoadSafetyNoImportCycle` in `tests/test_gap_closure.py`.

## 2. ACS actionable demotion (v1.2)

**Fix:** `_edge_is_dynamic_literal_noise` + `_edge_is_non_actionable_noise` in `import_cache.py`.  
Demotes `importlib.import_module("…")` / `__import__` / `dynamic_type=static` string literals from `actionable_low_conf_edges` (telemetry `low_conf_edges` unchanged).  
`acs_version` → **1.2**; on-demand recompute when older.

**Evidence:** `test_dynamic_literal_noise_demoted_from_actionable` keeps project-local unresolved actionable; demotes dynamic literal fixture.

## 3. package.json exports self-tests

All 8 synthetic exports cases **PASS** via `tests/selftest/run_javascript_selftest.py` (string shorthand, conditional import, relative local-pkg, subpath, missing-target no-crash, legacy main, top-level conditions).  
Also barrel churn 4/4. Captured under implementer scratch `exports_selftest.txt`.

## 4. Barrel-heavy dogfood (Babylon.js)

| Run | Scope | Result |
|-----|--------|--------|
| force_full | `packages/dev` | success, **78.7s**, 3632 files parsed, **43758** edges persisted |
| incremental re-run | same | success, **11.4s**, 0 dirty, **no hang** |
| cache | — | ~100.6 → **101.1 MB** (not unbounded growth) |
| BRC | — | 7617 chains, 4393 index keys, 44345 resolved_pairs |

**Bound:** `WIKIFIER_BARREL_LEAF_CAP` default **24** (`javascript._barrel_leaf_cap`) already caps barrel leaf emission; no additional cap required after this dogfood (pathology not observed).

JSON: implementer scratch `barrel_dogfood.json`.

## 5. Long-horizon soak rails (not 72h wall-clock)

**Target:** `cloned_sample_projects/llama_index` (lean monitor: `llama-index-core`).

| Check | Result |
|-------|--------|
| `assess_autonomous_readiness` | `ready_for_daemon`, blockers `[]` |
| metrics snapshots | ≥2 samples (`goal-soak-1/2` + history) |
| daemon start/status | PID started; `daemon_heartbeat.json` `ok: true`, `consecutive_failures: 0` |
| daemon stop | clean stop after evidence capture |

**Honest residual gap:** multi-day (≥72h) continuous soak with growth/corruption watch is **not** claimed. Use `Findings/long-horizon-autonomous-ops.md` + metrics_history for that evidence later.

## Optional 6. Multi-lang

Smoke `update-maps` (capped max_files) on rust / redox / dotnet-dotnet / linux include: **4/4 success**.
Parsers emit edges; **path resolution remains shallow** (unresolved_ratio ~1.0 for these trees — expected regex maps, not cargo/go.mod/classpath/`-I`). Quality bar for deeper resolution is still future work; smoke proves parsers do not crash and persist edges.

Scratch: `multi_lang.json`.

## Tests

```bash
python3 -m unittest discover tests   # 62+ OK after this work
```
