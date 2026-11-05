# skills/run.md

**Role:** Agent Protocol v0.7. This is the contract for the daily loop. `AGENTS.md` is the repository entry point and points here.

Part 1 is the session loop: bootstrap, check-changes, suggest-next, prepare-edit, record-change, mark-green, update-maps. Part 2 is the reference for health, wiki verification, batch recording, dependencies, and commands. Wiki verification covers Python, JS/TS, and Rust `pub` items including impl methods and trait-impl items. Rust import names include `[workspace] members`.

The implementation note records how the std-only Rust binary fills that contract: `wk_cache`, regex-plus-reexport parsing, Rust paths from `crate::` / `self::` / `super::` / the root Cargo.toml crate name, map artifacts, deletion, MCP errors, the project lock, and a standing `serve` that feeds the dashboard. Daemon actions are `start`, `stop`, `status`, and `run`. `init DIR`, `verify-wikis DIR`, and `search-journal --file` apply. `init` seeds the map roots it finds. File arguments may use `\` separators. Lookups on an unknown path return `FileNotFound`; an MCP call missing a required argument returns `InvalidArguments`; MCP `update_maps` leaves out the edge list unless `edges: true`. The protocol version stays v0.7. The package line is 5.0.0. The live version command is `wikifier --version` (from `Cargo.toml`).
