# AGENTS.md

**Role:** Entry point for any coding agent in this repository.

It points at `skills/run.md` (protocol v0.7, package 5.3.1) and names the live Rust binary, the daily loop, and the Python-era records kept under `Findings/archive/`. `pip install wikifier` is the archived Python 4.7 package. Map roots stay `src/` and `tests/`. The import scan stays comment-masked regex plus named re-exports. Rust also resolves `crate::`, `self::`, `super::`, root crate names, and `[workspace] members`, so `src/main.rs` and `tests/*.rs` are dependents of the library modules they import. `mark-green` checks Rust `pub` names, impl methods, and trait-impl items. A "Choosing groups" section tells an agent what each MCP tool group is for, when to turn it off, and the `wikifier:` line for the `agent-tools` block; this file itself has no such block, so dogfooding keeps every tool.
