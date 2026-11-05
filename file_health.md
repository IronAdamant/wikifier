# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| .github/workflows/publish.yml | 🟢 Green | 2026-11-03 09:27:04 | Multi-target release archives and SHA256SUMS (subid=release-5.0.0) |
| AGENTS.md | 🟢 Green | 2026-11-03 09:27:04 | Package line is 5.0.0; pip remains Python 4.7 (subid=release-5.0.0) |
| CHANGELOG.md | 🟢 Green | 2026-11-05 05:15:34 | wiki updated (claude/windows-verify speed) |
| CLAUDE.md | 🟢 Green | 2026-11-03 09:27:04 | Package line is 5.0.0 (subid=release-5.0.0) |
| CONTRIBUTING.md | 🟢 Green | 2026-11-03 05:34:35 | Address the 3 Nov review findings (subid=review-2026-11-03) |
| Cargo.lock | 🟢 Green | 2026-11-03 09:27:04 | Lockfile version 5.0.0 (subid=release-5.0.0) |
| Cargo.toml | 🟢 Green | 2026-11-03 09:27:04 | Version 5.0.0 (subid=release-5.0.0) |
| Findings/M5-Dogfood-Assessment-Report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/M5-Dogfood-Progress.md | 🟢 Green | 2026-11-03 08:06:46 | Wiki marks this file as the historical M5 log (subid=protocol-v07) |
| Findings/M5.1-cross-hardening-analysis.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/Milestones-Overview.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/p6_real_world_validation_report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| README.md | 🟢 Green | 2026-11-05 04:16:31 | wiki updated (claude/windows-verify) |
| docs/spec.md | 🟢 Green | 2026-11-03 08:00:11 | Name the Rust binary and protocol v0.7 in the living principles (subid=protocol-v07) |
| scripts/benchmark_parity.sh | 🟡 Yellow | 2026-11-03 08:56:15 | Benchmark script and measured results. |
| scripts/benchmark_results.md | 🟡 Yellow | 2026-11-03 08:56:15 | Benchmark script and measured results. |
| skills/run.md | 🟢 Green | 2026-11-05 05:15:34 | wiki updated (claude/windows-verify speed) |
| src/api.rs | 🟢 Green | 2026-11-05 05:19:31 | wiki current (claude/windows-verify pending) |
| src/artifacts.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/cache.rs | 🟢 Green | 2026-11-05 05:15:33 | wiki updated (claude/windows-verify speed) |
| src/cache_commit.rs | 🟢 Green | 2026-11-05 05:15:33 | wiki updated (claude/windows-verify speed) |
| src/cycle_report.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/daemon_svc.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/jsonutil.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/legacy_cache.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/lib.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/low_conf.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/main.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/maps_out.rs | 🟢 Green | 2026-11-05 05:15:33 | wiki updated (claude/windows-verify speed) |
| src/mcp.rs | 🟢 Green | 2026-11-05 05:15:47 | wiki updated (claude/windows-verify speed) |
| src/parse.rs | 🟢 Green | 2026-11-05 05:15:33 | wiki updated (claude/windows-verify speed) |
| src/pending_line.rs | 🟢 Green | 2026-11-05 05:19:31 | wiki (claude/windows-verify pending) |
| src/proc.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/project_lock.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/scope.rs | 🟢 Green | 2026-11-05 05:15:34 | wiki updated (claude/windows-verify speed) |
| src/sha256.rs | 🟢 Green | 2026-11-05 04:14:08 | wiki updated (claude/windows-verify) |
| src/symbols.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/text_out.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/timeutil.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/wiki_files.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| tests/agent_args.rs | 🟡 Yellow | 2026-11-05 04:14:08 | new: agent-style file args, missing args, lean MCP outputs, init roots, CRLF (claude/windows-verify) |
| tests/behaviour_gaps.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Tests for those parity fixes. |
| tests/cache_and_artifacts.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Tests for those parity fixes. |
| tests/cli_surface.rs | 🟡 Yellow | 2026-11-05 04:14:08 | launcher exit-code test for wikifier.bat / wikifier.sh (claude/windows-verify) |
| tests/contract_gaps.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Tests for those parity fixes. |
| tests/dogfood.rs | 🟢 Green | 2026-11-05 05:15:34 | wiki updated (claude/windows-verify speed) |
| tests/parity.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/parity_fixes.rs | 🟡 Yellow | 2026-11-05 05:15:33 | pending item wording and empty-queue note (claude/windows-verify speed) |
| tests/protocol_v07.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/robustness.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/skip_maps.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/speed_paths.rs | 🟡 Yellow | 2026-11-05 05:15:33 | new: fast paths give the slow paths' answers (claude/windows-verify speed) |
| wikifier.sh | 🟢 Green | 2026-11-03 08:06:46 | Wiki describes the Rust binary launcher (subid=protocol-v07) |
