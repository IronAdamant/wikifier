# tests/protocol_v07.rs

**Role:** Integration tests for the agent-facing contract that the early Rust port left thin.

Covers `library.md` and folder cards, `--directory` / `--max-files` resume, `record_deletion` plus journal de-duplication, `record_changes` globs and `--green`, dependency confidence and cycle `break_hint`, JS wiki refusal, legacy JSON import, `init` keeping path lists, MCP `isError` plus resource and prompt reads, prune keeping a monitored file that sits outside the map roots, and `serve` reading `file_health.json` and `library.md` before shutdown.
