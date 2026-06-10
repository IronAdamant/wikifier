# Dogfood Findings — 2026-06-10 (post-refactor validation, real-world sweep)

Dogfood order (as requested): **Wikifier itself → RecipeLab_alt → each project under
cloned_sample_projects**. All runs used the installed dev package (`pip install -e .`,
v4.1.4 + the 2026-06-10 refactoring pass). Every project was driven with explicit
`WIKIFIER_PROJECT_ROOT`. Existing (pre-dogfood) issues are listed at the end.

Companion fix plan: `Findings/2026-06-10-Fix-Plan.md`.

---

## 1. Wikifier on itself

Curated repo (docs-scoped monitored_paths) **plus** a full-pipeline run on a scratch
copy of the source tree (`/tmp/wf_dogfood_self`, 17 .py files) to exercise the parsers.

| # | Finding | Severity |
|---|---------|----------|
| W1 | `wikifier health --summary` / `--json` CLI flags are **silently ignored** — full matrix printed either way. README, skills/run.md and CLAUDE.md all document them. Only the Python library (`health(format="summary")`) honors formats. | Medium |
| W2 | `init` is missing from `wikifier help`; `issues` output points to `Logged_issues/map.md`, which was pruned in the simplification phase. | Low |
| W3 | **`wikifier.sh` line 718 crashes the map build**: `${node_dependents[$tgt_node]:-0}` references an array that is *never declared or populated* (only occurrence in the script; `mermaid_nodes` gets `declare -gA` at line 551, `node_dependents` gets nothing). Under `set -u`, bash arithmetic-evaluates the subscript of an undeclared array, so the first bare-module target node (e.g. `os`) aborts the script: `line 718: os: unbound variable`. Pre-existing at HEAD in both root and packaged copies. Consequences: library.md left as an 11-line template stub, `_cycles` never persisted, so `wikifier cycles` permanently reports "run update-maps first". | **Critical** |
| W4 | `wikifier.sh` ~line 1197: the embedded `python3 -c` block for reverse-dependency preload calls `os.environ.get(...)` **without `import os`** → guaranteed `NameError` on every invocation, hidden by `2>/dev/null`. Reverse-dependency data has silently never loaded on the shell path. | High |
| W5 | `update-maps` (sh) **truncates library.md to the template header before building**, so any crash (W3) destroys the previous artifact. Observed destruction in the wild: RecipeLab_alt's M5-era library.md was already reduced to an 11-line stub by earlier runs of this bug. | **Critical** |
| W6 | Shell update-maps performance: **3m19s for 17 files (~12s/file)** on the scratch copy. Root cause shared with S5 below. Extrapolates to ~27h for airflow — unusable. | High |
| W7 | `update-maps --python-primary` is **not a real full update**: `run_full_update` deep-parses only `min(20, dirty)` files (cli.py:338,419) while reporting `success: true` and the *full* `files_to_reparse` count; persists a schema-divergent blob (top-level `resolved_pairs` list with **absolute** src paths and stringified `"false"` booleans, vs the canonical per-file dict with relative paths); and never generates library.md. Combined with W3/W6: **there is currently no working end-to-end update-maps for a fresh real project.** | **Critical** |
| W8 | `check-changes` does **not honor `exclude_patterns.txt`**: flagged `wikifier/__pycache__/__main__.cpython-314.pyc` Yellow on the scratch project even though the default excludes list `__pycache__` and `*.pyc`. | Medium |
| W9 | `init` writes a template health entry — `wikifier.sh 🟢 Green "Core CLI implemented and documented"` — into **every target project's** file_health.md. It describes Wikifier itself, not the target. Confirmed in all 8 sample projects (every fresh health matrix = this entry + 1 auto-yellow). | Medium |
| W10 | Edge-data inconsistency in resolved pairs across paths: `resolved` is sometimes `''`, sometimes the bare module name; `src` sometimes `None`, sometimes absolute. One canonical representation is needed. | Medium |

Positives: check-changes incremental detection sub-second; daemon status / journal /
issues / validate / record-change / mark-green / heal-stubs all work; locking held under
concurrent invocations.

## 2. RecipeLab_alt (206 src files, JS/TS, pre-wikified M5 target)

| # | Finding | Severity |
|---|---------|----------|
| R1 | check-changes works incl. **barrel auto-yellow** (2 importers correctly flagged via the BRC reverse index) — the core incremental loop is healthy. | Positive |
| R2 | `update-maps` exits 1 (W3/W4 vintage of its local wikifier.sh) and leaves library.md as the 11-line stub. Its canonical import cache (184 files / 686 edges, built June 5 by the slow-but-correct sh parse) is intact; cycles/ACS keys are absent so `cycles` fails. | Critical (same root as W3/W5) |
| R3 | `.wikifier_staging/` accumulates leaked 0-byte temp files `wikifier_fresh_pairs.*.txt` (4 from different dates). Temp cleanup is missing on some path. | Low |

## 3. cloned_sample_projects (8 projects, in tested order)

Per-project: `init` → `update-maps --python-primary --full` (timed) → `check-changes` → health.

| Project | Lang / candidate files | update-maps | check-changes | Notes |
|---------|------------------------|-------------|---------------|-------|
| redox | Rust / 2 | 0.9s, success | 0.7s | **S1**: claims success but `import_cache.json` is never created — nothing persisted, result doesn't say "0 parseable files" |
| llama_index | Python / 3,837 | 2.0s, "success" | 0.7s | **S2**: deep-20 cap quantified — only **8 distinct src files** (15 edges, 5.8KB) persisted of "3837 reparsed" |
| Babylon.js | TS / 3,905 | 11.5s, "success" | 0.7s | cap again; extra time = barrel work on 20 files |
| dotnet-dotnet | C# / 751 js/ts/py | 8.7s, "success" | 0.8s | C# invisible (no parser) — degrades without crash |
| airflow | Python / 8,068 | 3.0s, "success" | 0.8s | cap again |
| linux | C / 374 py | 3.7s, success | 0.8s | **S3**: 37k-file walk scales fine |
| rust | Rust / 220 py/js | 3.0s, success | 0.8s | scales fine |
| llvm-project | C++ / 2,938 py/js | 7.8s, "success" | 0.8s | 54k-file walk fine |

**S4 — In-process parser stress (300 random files each, 0 errors both):**
- Python parser: **~1ms/file** (300 airflow files, 1,807 edges, 0.2s). Full parsing of the
  entire airflow repo would take ~10 seconds — the deep-20 cap is unnecessary for Python.
- JS/TS parser: **~963ms/file** (300 Babylon files, 2,548 edges, 288.8s). Unusable at scale.

**S5 — JS parser bottleneck profiled (cProfile, 8 Babylon files = 34.1s):**
93% of wall time is `bree.expand_chain` → `import_cache.save_cache` → `json.dump` —
BREE serializes the **entire multi-MB import cache to disk on every barrel chain
expansion** (38 full saves for 8 files = 31.7s of 34.1s). This is also the root cause of
W6 (sh path slowness). The parsing logic itself is fast.

**S6** — Non-Python/JS languages (Rust, C, C#, C++) degrade gracefully (no crashes), but
produce near-empty maps with no indication in the update-maps result that the project has
no parseable files (see S1).

## 4. Existing issues (pre-dogfood, carried forward)

| # | Issue | Source |
|---|-------|--------|
| E1 | JS parser self-test: 1 of 4 Phase-2 barrel churn tests fails — touching a mid-chain barrel file does not mark its importer dirty via the BRC mtime snapshot / reverse index. Verified pre-existing at HEAD (clean worktree). | `Logged_issues/2026-06-10-js-barrel-churn-selftest-failure.md` |
| E2 | No test suite — every fix above is currently verified only by dogfooding. | 2026-06-10 refactor pass report |
| E3 | Deferred refactors: monolithic 400–530-line parse functions; `[^)]+?` require/import regex (compensated by balanced-paren fallback); deprecated resolver shims in javascript.py; shell-vs-Python root-discovery duplication; milestone-codename comments in not-yet-touched files. | 2026-06-10 refactor pass report |

## 5. Summary

The incremental loop (check-changes, record-change, mark-green, health, journal, barrel
auto-yellow, locking) is solid across all 10 projects. The **map-building pipeline is
broken end-to-end**: the shell path crashes (W3/W4) and destroys its own artifact (W5),
the python-primary path is a 20-file façade with a divergent schema (W7), and the JS
parser's cache-save storm (S5) makes real-scale parsing impossible regardless of path.
These five findings (W3, W4, W5, W7, S5) share two roots — the shell map builder and
BREE persistence — and one missing pillar (no real python-primary pipeline). The fix
plan addresses them in that order.
