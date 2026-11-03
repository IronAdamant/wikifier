# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| AGENTS.md | 🟢 Green | 2026-11-03 11:25:28 | Add the agent entry point: live Rust binary, daily loop, and which logs are historical (subid=agents-md) |
| CHANGELOG.md | 🟢 Green | 2026-11-03 08:04:45 | Note the file tree, dashboard routes, and prune-health --deleted-missing (subid=protocol-v07) |
| CLAUDE.md | 🟢 Green | 2026-11-03 11:25:28 | Point at AGENTS.md, describe the library file tree, and return JSON success false (subid=agents-md) |
| CONTRIBUTING.md | 🟢 Green | 2026-11-03 08:00:11 | Point new commands at src/api.rs and src/main.rs (subid=protocol-v07) |
| Findings/M5-Dogfood-Assessment-Report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/M5-Dogfood-Progress.md | 🟢 Green | 2026-11-03 08:06:46 | Wiki marks this file as the historical M5 log (subid=protocol-v07) |
| Findings/M5.1-cross-hardening-analysis.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/Milestones-Overview.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/p6_real_world_validation_report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| README.md | 🟢 Green | 2026-11-03 11:25:28 | Point agents at AGENTS.md and skills/run.md (subid=agents-md) |
| docs/spec.md | 🟢 Green | 2026-11-03 08:00:11 | Name the Rust binary and protocol v0.7 in the living principles (subid=protocol-v07) |
| monitored_paths.txt | 🟢 Green | 2026-11-03 11:25:28 | Watch AGENTS.md with the other live docs (subid=agents-md) |
| skills/run.md | 🟢 Green | 2026-11-03 11:25:28 | Point the protocol at the repository entry AGENTS.md (subid=agents-md) |
| src/api.rs | 🟢 Green | 2026-11-03 08:04:45 | Serve dashboard files, status, run, and shutdown, and drop missing health rows with prune-health --deleted-missing (subid=protocol-v07) |
| src/artifacts.rs | 🟢 Green | 2026-11-03 08:00:11 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/cache.rs | 🟢 Green | 2026-11-03 08:00:11 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/cache_commit.rs | 🟢 Green | 2026-11-03 08:00:11 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/jsonutil.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| src/legacy_cache.rs | 🟢 Green | 2026-11-03 08:00:12 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/lib.rs | 🟢 Green | 2026-11-03 08:00:12 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/main.rs | 🟢 Green | 2026-11-03 08:00:12 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/maps_out.rs | 🟢 Green | 2026-11-03 08:04:45 | Write a file tree into library.md so the dashboard can show the map (subid=protocol-v07) |
| src/mcp.rs | 🟢 Green | 2026-11-03 08:00:12 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/parse.rs | 🟢 Green | 2026-11-03 08:00:12 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/proc.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| src/project_lock.rs | 🟢 Green | 2026-11-03 08:00:12 | Finish the 4.7 agent contract in the Rust binary: map artifacts, deletion, update-maps flags, record-changes, dependency flags, wiki checks, legacy cache import, serve/monitor/daemon, MCP errors, project lock, and pending cleanup on mark-green (subid=protocol-v07) |
| src/scope.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| src/sha256.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| src/timeutil.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/cache_and_artifacts.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/cli_surface.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/contract_gaps.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/dogfood.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/parity.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/protocol_v07.rs | 🟢 Green | 2026-11-03 08:04:45 | Cover dashboard serving, shutdown, and the library file tree (subid=protocol-v07) |
| tests/robustness.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| tests/skip_maps.rs | 🟡 Yellow | 2026-11-03 07:58:59 | Initial stub |
| wikifier.sh | 🟢 Green | 2026-11-03 08:06:46 | Wiki describes the Rust binary launcher (subid=protocol-v07) |
