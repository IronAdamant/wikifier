# BRC pathologies on barrel-heavy targets: scoped re-run churn + sh incremental hang

**Date logged:** 2026-06-10
**Severity:** Medium (does not affect the primary full/incremental pipeline; hits scoped re-runs and the sh fallback on barrel-heavy repos)
**Status:** Open
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
