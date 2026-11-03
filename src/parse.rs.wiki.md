# src/parse.rs

**Role:** Comment-masked import scans for Python, JS/TS, Rust, Go, C/C++, C#, and Java.

Unknown suffixes emit no edges. Named JS/TS re-exports are followed to depth 8 and flagged `via_barrel`. A Python import with indent greater than zero is `conditional`. `import()` is `dynamic`. Direct edges clear `via_barrel` when the same destination is also reached that way.

Rust `mod` names a file beside the declaring module (`lib.rs`, `main.rs`, and `mod.rs` use the parent directory; other files use a directory with the file's stem). Inline `mod name { ... }` is not a file. `crate::` stays in the file's crate, so `tests/*.rs` and `src/bin/*.rs` do not point `crate::` at the library. `self::` and `super::` walk from that file; a `super::` inside an inline module pops the inline frame before it leaves the file. The root `Cargo.toml` `[package].name` and `[lib].name` (hyphens become underscores) both point at the library root (`src/lib.rs` when it exists). That is how `use wikifier::...` from `src/main.rs` and `tests/*.rs` becomes an edge. A path expression with the same shape counts as an edge too. `use` of any other crate is external. The scan does not read workspace members.

The scan does not use CPython `ast` and does not read tsconfig paths, package exports, or workspaces. The frozen fixtures, including the Cargo crate layout, are the accuracy gate.

Public scan entry points: `language`, `read_utf8`, `scan_file_warned`, `scan_file`, `resolve_project`, `resolve_python_spec`, `analyze_files`, `analyze_changed`, `edges_for_files`. Public types: `RawImport`, `Kind`, `Scan`, `FactEdge`, `FileFacts`, `Analysis`.
