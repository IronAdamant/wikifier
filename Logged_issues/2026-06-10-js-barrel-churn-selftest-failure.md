# JS parser self-test: barrel churn fails to mark importer dirty

**Date logged:** 2026-06-10
**Severity:** Medium (incremental-update correctness on barrel edits)
**Status:** RESOLVED 2026-06-10 (v4.2.0 fix pass) — mtimes_snapshot now covers the whole
chain (entry + intermediate hops + leaves) and `_barrel_file_index` indexes every chain
member; per-item error tolerance replaced the silent `except: pass` that emptied the
snapshot. Verified: parser self-test churn 4/4, tests/test_barrel_invalidation 4/4.
**Found during:** 2026-06-10 refactoring pass (subid=refactor-zero-dep-cleanup-1)

## Symptom

`python -m wikifier.parsers.javascript` (built-in self-test) reports:

```
Stale importers from invalidate: []
FAIL: churn did not mark the importer dirty via barrel snapshot
Affected importers via index for b.js: []
Phase2 churn tests: 3 passed, 1 failed.
WARNING: Phase 2 barrel cache tests had failures — inspect mtimes/partial/index logic.
```

## Verified pre-existing

Reproduced identically on a clean `git worktree` of HEAD (commit 0c276f0) before
any 2026-06-10 changes were applied. Not a regression from the refactoring pass.

## Suspected area

Barrel resolution cache churn path: either the `mtimes_snapshot` comparison in
the persisted barrel chains or the reverse `_barrel_file_index` lookup
(`get_affected_importers`) does not surface the importer when a mid-chain
barrel file (`b.js` in the self-test) changes. See
`wikifier/parsers/bree.py` (BarrelResolutionCache / chain mtime validation) and
`wikifier/import_cache.py` (`invalidate_stale_barrel_entries`).

## Impact

If real (not just a self-test setup artifact), an edit to a barrel file may not
trigger re-parse of files importing through it, leaving stale resolved edges
until the next full `update-maps --full`.

## Next step

Reproduce outside the self-test with a minimal three-file chain
(consumer → barrel → leaf), touch the barrel, and trace
`invalidate_stale_barrel_entries` to see which lookup returns empty.
