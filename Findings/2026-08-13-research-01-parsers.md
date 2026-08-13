# Research 01 — Parsers (agent-first)

**Date:** 2026-08-13  
**Agent:** /deep-research + local explore (parsers slice)  
**Scope:** `wikifier/parsers/**`, parse dispatch in `api.py` / `import_cache_impl.py`, parser tests  
**Axes:** improved · simplified · modernised · modularised further

Runtime identity (confirmed): CPython package directory wins over a same-named `.py`.

```
wikifier.parsers.javascript → parsers/javascript/__init__.py  (live)
wikifier.parsers.bree       → parsers/bree/__init__.py        (live)
```

## Coverage

`__init__.py`, `_edge.py`, `python.py` (779), `javascript.py` (2681, decoy), `javascript/_parser.py` (2684, live), `bree.py` (1-line leftover), `bree/_bree.py` (2013), `cdia.py` (908), rust/go/c_cpp/csharp/java, `api._parse_file`, streaming parse in `import_cache_impl`, `tests/test_parsers.py`, `test_multi_lang_parsers.py`, `test_barrel_invalidation.py` (all 4 skipped), selftests.

## Findings

| Axis | Pri | Path | Finding | Change |
|------|-----|------|---------|--------|
| Simplified | P0 | `javascript.py` xor `javascript/` | Two ~2.68k near-clones. Package is live; `.py` is a decoy. Live `_parser.py` does `from . import bree` (wrong inside package) so standalone BRC flush is swallowed. | **Delete `javascript/` package.** Keep `javascript.py` (sibling imports `.bree` / `.cdia` are correct). No extra shim. |
| Simplified | P0 | `bree.py` | 1-line leftover next to `bree/`. Health/wiki still name this file. | **Delete `bree.py`.** Keep `bree/_bree.py`. |
| Improved | P0 | `tests/test_barrel_invalidation.py` | All four E1 tests `@skip` while BREE claims E1 is fixed. | Unskip; fix if red. |
| Improved | P1 | `api._parse_file` | Dispatcher omits `.mjs/.cjs/.mts/.cts` even though JS resolver knows them. | Add those suffixes to the same JS parser. |
| Improved | P1 | `python.py` | `import a, b` only captures the first name. | Split commas on the `import` form. |
| Modernised | P1 | `parsers/__init__.py` + `wikifier/__init__.py` | `import wikifier` eagerly loads JS+BREE+CDIA+all langs. | Lazy `parsers` language imports (`__getattr__`). |
| Modularised | P0 | JS layout | `MODULARIZATION_PLAN.md` 6-file JS split never happened — dump + 29-line `__init__`. | Delete the clone **first**. Do not split `_parser.py` in the same change. |
| Modularised | later | `_ldsi.py` | Python imports private JS LDSI helpers. | Shared module after decoy is gone. |

## Must-do

1. Confirm `__file__` (done) → delete dead JS package + leftover `bree.py`.
2. Unskip barrel invalidation tests.
3. Add `.mjs/.cjs/.mts/.cts` to `_parse_file`.
4. Lazy parser package import.

## Do not

- Add COBOL or any new language parser (unknown suffix already no-ops).
- Implement the 6-file JS package on top of the clone.
- Change `parse_*_imports(filepath) -> List[Dict]` contract.
