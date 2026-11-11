# tests/parity.rs

**Role:** Accuracy fixtures for the import scan.

`accuracy_fixtures_match_frozen_edges` builds each layout in a temp directory, runs `update_maps`, and compares the edge set to the frozen list. The layouts are the Django app, the `src/` package, the TypeScript monorepo, the comment and string traps, and a Cargo crate (`src/lib.rs`, `src/main.rs`, `src/bin/tool.rs`, `tests/use_lib.rs`) whose package name and lib name differ. `each_parsed_language_emits_a_local_edge` checks one local edge per parsed language. `unknown_suffixes_emit_no_edges` checks that COBOL, Swift, and assembly contribute no edges.

5.5.0: frozen fixture `rust_glob_imports`: `sight::X` under one or two `use super::*` globs is an edge to `sight.rs`; `fs::read` under `use std::fs` is not an edge to the crate's `fs.rs`.
