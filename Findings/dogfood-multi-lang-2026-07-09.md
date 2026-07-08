# Multi-language dogfood — cloned_sample_projects

**Date:** 2026-07-09  
**Parsers added:** Rust, Go, C/C++, C# (plus existing Python, JS/TS)  
**Machine JSON:** `Findings/dogfood-multi-lang-2026-07-09.json`

## Results (scoped / budgeted update-maps)

| Project | Primary langs in tree | Scope | Parsed | Edges | Languages_parsed | Time |
|---------|----------------------|-------|--------|-------|------------------|------|
| llama_index | Python | full tree (warm cache) | 0 dirty | — | (cache hold) | 3.4s |
| airflow | Python + some TS/Go | airflow-core/src max 80 | 0 dirty | — | warm | 9.3s |
| Babylon.js | TypeScript | packages/dev/core/src max 80 | 0 dirty | — | warm | 13.9s |
| **redox** | **Rust** (+ misc) | full force | **30** | **175** | **.rs 21, .c 5, .go 1, …** | 0.4s |
| **rust** | **Rust** | library/std/src max 150 | **150** | **805** | **.rs 150** | 14s |
| **llvm-project** | **C++** | llvm/lib/Support max 100 | **100** | **541** | **.cpp 89, .c 8, .h 3** | 32s |
| **linux** | **C** | init max 50 | **13** | **239** | **.c 11, .h 2** | 21s |
| **dotnet-dotnet** | **C#** | src max 100 | **100** | **359** | **.cs 99, .py 1** | 129s |

All runs: `success: true`. No crashes. Portable `monitored_paths.txt` = `.` on all targets.

## Notes

- Warm-cache targets (llama/airflow/Babylon) prove **incremental** path; multi-lang force runs prove **new parsers**.
- Dotnet `parseable_files` ~104k under `src/` — max_files budget required for agent-scale sessions.
- C/C++ local includes resolve when headers sit next to sources; system `<>` includes are tagged external_or_bare (ACS noise filter).
- Rust `mod` resolves sibling `foo.rs` / `foo/mod.rs`; `use std::…` external.

## Tests

`tests/test_multi_lang_parsers.py` — unit coverage for each new parser + pipeline languages_parsed field.
