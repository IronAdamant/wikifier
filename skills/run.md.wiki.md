# skills/run.md

**Role:** Agent Protocol v0.7. This is the contract for the daily loop.

Part 1 is the session loop: bootstrap, check-changes, suggest-next, prepare-edit, record-change, mark-green, update-maps. Part 2 is the reference for health, wiki verification, batch recording, dependencies, and commands.

The implementation note records how the std-only Rust binary fills that contract: `wk_cache`, regex-plus-reexport parsing, map artifacts, deletion, MCP errors, the project lock, and a standing `serve` that feeds the dashboard. The protocol version stays v0.7. The live version command is `wikifier --version`.
