# CLAUDE.md

**Role:** Repo guidance for an agent working in this tree.

Hard constraints: empty Cargo dependencies, no hand-edits of `library.md` or the health and pending files, and the human dashboard stays secondary. The Python-era plan logs live under `Findings/archive/`. It points agents at `AGENTS.md` and `skills/run.md` (protocol v0.7, package 5.2.0). The architecture section names the Rust modules under `src/`, the library file tree, and this repo's map roots `src/` and `tests/`. The parse note includes Rust `crate::`, `self::`, `super::`, Cargo.toml crate names, `[workspace] members`, and `rust_public_symbols` for wiki checks. JSON failures use `success: false`.
