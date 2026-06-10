# BRC pathologies on barrel-heavy targets: scoped re-run churn + sh incremental hang

**Date logged:** 2026-06-10
**Severity:** Medium (does not affect the primary full/incremental pipeline; hits scoped re-runs and the sh fallback on barrel-heavy repos)
**Status:** RESOLVED 2026-06-10 (thin-shell + BRC rework)

**Actual root causes (found via faulthandler stack dumps + WIKIFIER_DEBUG_SAVES):**
1. The 75-minute scoped burner was NOT cache churn (0 mid-run saves): it was
   `_get_project_root_fallback` re-running marker-walk discovery + Path.resolve()
   **once per barrel leaf per statement** during name routing — ~hundreds of
   thousands of discovery walks on a deep real tree. Fixed by memoizing it and
   `_abs_resolved_target` (keyed by anchor/env/cwd; cleared with parser caches).
   Babylon scoped re-run: 75min → 80.6s (and it parsed 2,070 barrel-affected files).
2. BRC bloat was real and separate: lean deduped leaf references + set-backed index
   merges + compact JSON dump took Babylon's cache 274MB → 101MB and the synthetic
   scoped re-run to 1.0s with exactly one save.
3. The sh incremental hang was retired wholesale: wikifier.sh's update-maps now
   delegates to the Python pipeline (launcher 2,910 → 785 lines); the per-file spawn
   loop and the deadlocking stdin merge block no longer exist.
**Found during:** barrel-leaf explosion fix validation (user noticed stalled background commands)

## Symptom 1 — scoped re-run churn (Python path)

`update-maps --full --directory=packages/tools/playground` on Babylon.js (after a
completed full run had persisted the cache) ran **93+ minutes at 98% CPU, 2.1GB RSS**,
continuously rewriting `import_cache.json`, and was killed. The unscoped full run on the
same repo completes in 5m52s.

Contributing factor: `import_cache.json` on Babylon is **274MB for 44k pairs** —
`_barrel_resolutions` (the persistent BRC) stores the *full results array* per chain
(the @dev/core chain alone carries ~2.5k leaf records), so barrel-heavy repos pay a
massive load/save cost any time the cache is touched. The barrel-leaf emission policy
(v4.2.x) bounds *emitted edges* but not the *stored BRC chains*.

## Symptom 2 — sh incremental hang

A scratch-project `wikifier.sh update-maps` (incremental, second run) hung for ~3 hours
at **0% CPU**: the embedded `python3 -c` merge block (the one that re-emits cached pairs
for unchanged files) sat blocked reading stdin — its producer never completed/closed.
Process tree: `bash wikifier.sh update-maps` → `python3 -c <merge block>` (S state).

## Suspected roots

1. BRC storage shape: chains should store leaf *references* (paths + mtimes), not full
   result records; or cap/compress stored results. This would also shrink the 274MB cache.
2. Scoped runs against a large existing cache: investigate repeated save triggers during
   the parse loop (expected: zero saves until the single end-of-run persist).
3. sh incremental: the stdin pipeline into the merge block can deadlock; needs a timeout
   or restructure (or retirement — see "thin shell" plan below).

## Planned resolution

Fold into the "slow sh fallback path" work item: make the sh first-pass delegate to a
single `run_full_update` invocation (retiring the per-file spawn loop and the hanging
merge block), and rework BRC persistence to store bounded chain records.
