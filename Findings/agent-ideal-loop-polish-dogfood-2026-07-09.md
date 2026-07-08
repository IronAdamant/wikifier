# Agent ideal-loop polish + 8-project dogfood (2026-07-09)

**Package:** 4.6.2  
**subid:** agent-ideal-loop-polish  

## Shipped (items 1–4)

| # | Item | Status |
|---|------|--------|
| 1 | `seed_source_content_hashes` — seed Green baselines without mass Yellow | ✅ |
| 2 | `list_core_tools` + bootstrap `core_surface` / `core_daily` (Core 6) | ✅ |
| 3 | `resolve_dependents_from_cache` multi-shape reverse index in `prepare_edit` | ✅ |
| 4 | Dual dogfood on all 8 cloned_sample_projects | ✅ 8/8 × 2 |

## Dogfood roots (never parent multi-repo)

`cloned_sample_projects/{airflow,Babylon.js,dotnet-dotnet,linux,llama_index,llvm-project,redox,rust}`

### Loop per project

`session_bootstrap` → `seed_source_content_hashes` → `check_changes` → `suggest_next_actions(json)` → `prepare_edit(<file>)`

### Results

| Pass | Success | Notes |
|------|---------|-------|
| 1 | **8/8** | content_honest=true all; prepare_edit deps/dependents exercised (e.g. Babylon dependents=10) |
| 2 | **8/8** | Second session validation; stable |

JSON: implementer scratch `dogfood_pass1.json` / `dogfood_pass2.json`.

## Tests

`tests/test_agent_loop.py` — seed, core listing, reverse shapes; full suite 74+.

## CLI

- `wikifier seed-source-hashes`
- `wikifier list-core-tools`
