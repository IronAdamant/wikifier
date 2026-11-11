# tests/m5_fixes.rs

**Role:** the smaller 5.5.0 fixes.

Covers: a cache without the parser stamp re-parses its Rust files once (and a `--max-files` run leaves the stamp until all are parsed); a config line without `=` no longer hides later keys; the MCP deadline cap of 600 seconds; no fan-in alert for a crate root; modularity alerts ranked by severity with changed files first, listed 10 at a time unless `full`.
