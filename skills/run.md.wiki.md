# skills/run.md

**Role:** Agent Protocol v0.7. This is the contract for the daily loop. `AGENTS.md` is the repository entry point and points here.

Part 1 is the session loop: bootstrap, check-changes, suggest-next, prepare-edit, record-change, mark-green, update-maps. Part 2 is the reference for health, wiki verification, batch recording, dependencies, and commands. Wiki verification covers Python, JS/TS, and Rust `pub` items including impl methods and trait-impl items. Rust import names include `[workspace] members`.

The implementation note records how the std-only Rust binary fills that contract: `wk_cache`, regex-plus-reexport parsing, Rust paths from `crate::` / `self::` / `super::` / the root Cargo.toml crate name, map artifacts, deletion, MCP errors, the project lock, and a standing `serve` that feeds the dashboard. Daemon actions are `start`, `stop`, `status`, and `run`. `init DIR`, `verify-wikis DIR`, and `search-journal --file` apply. The protocol version stays v0.7. The live version command is `wikifier --version`.
