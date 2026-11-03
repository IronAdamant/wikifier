# AGENTS.md

**Role:** Entry point for any coding agent in this repository.

It points at `skills/run.md` (protocol v0.7) and names the live Rust binary, the daily loop, and the files that are historical Python-era records. Map roots stay `src/` and `tests/`. The import scan stays comment-masked regex plus named re-exports. Rust also resolves `crate::`, `self::`, `super::`, and the root Cargo.toml package or lib name, so `src/main.rs` and `tests/*.rs` are dependents of the library modules they import.
