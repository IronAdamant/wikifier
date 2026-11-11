# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| .github/workflows/publish.yml | 🟢 Green | 2026-11-03 09:27:04 | Multi-target release archives and SHA256SUMS (subid=release-5.0.0) |
| AGENTS.md | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: worktree_root note; version 5.5.0 |
| CHANGELOG.md | 🟢 Green | 2026-11-11 12:53:37 | m5-fixes review: cold-start and --worktree position notes |
| CLAUDE.md | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: worktree module in the architecture list; version 5.5.0 |
| CONTRIBUTING.md | 🟢 Green | 2026-11-03 05:34:35 | Address the 3 Nov review findings (subid=review-2026-11-03) |
| Cargo.lock | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: version 5.5.0 |
| Cargo.toml | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: version 5.5.0 |
| Findings/M5-Dogfood-Assessment-Report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/M5-Dogfood-Progress.md | 🟢 Green | 2026-11-03 08:06:46 | Wiki marks this file as the historical M5 log (subid=protocol-v07) |
| Findings/M5.1-cross-hardening-analysis.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/Milestones-Overview.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/p6_real_world_validation_report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| README.md | 🟢 Green | 2026-11-11 12:53:37 | m5-fixes review: worktree cold start and --worktree position |
| docs/spec.md | 🟢 Green | 2026-11-03 08:00:11 | Name the Rust binary and protocol v0.7 in the living principles (subid=protocol-v07) |
| scripts/benchmark_parity.sh | 🟡 Yellow | 2026-11-03 08:56:15 | Benchmark script and measured results. |
| scripts/benchmark_results.md | 🟡 Yellow | 2026-11-03 08:56:15 | Benchmark script and measured results. |
| skills/run.md | 🟢 Green | 2026-11-11 12:53:37 | m5-fixes review: worktree cold start, branch-only check_changes, --worktree position |
| src/api.rs | 🟢 Green | 2026-11-11 12:53:37 | m5-fixes review: overlay check_changes skips files unchanged from main; overlay map artifacts only on demand |
| src/artifacts.rs | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: state paths via worktree; append_journal_many for one durable journal write per check-changes run |
| src/cache.rs | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: cache under worktree staging; parser stamp constant and marker path |
| src/cache_commit.rs | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: re-parse Rust rows once when the parser stamp is missing or old |
| src/cycle_report.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/daemon_svc.rs | 🟢 Green | 2026-11-11 12:01:53 | m5-fixes: daemon state paths under worktree staging (unchanged for main) |
| src/drift.rs | 🟢 Green | 2026-11-11 12:53:37 | m5-fixes review: worktree line counts of unchanged files come from main's copy and line cache |
| src/git_index.rs | 🟢 Green | 2026-11-11 12:53:38 | m5-fixes review: new std-only git index reader (v2/v3) so a fresh worktree's unchanged files are proven without reading them |
| src/jsonutil.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/legacy_cache.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: legacy cache lookup under worktree staging |
| src/lib.rs | 🟢 Green | 2026-11-11 12:53:38 | m5-fixes review: declare git_index |
| src/low_conf.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: low_conf.tsv under worktree staging |
| src/main.rs | 🟢 Green | 2026-11-11 12:53:38 | m5-fixes review: --worktree accepted before the command, like --target |
| src/maps_out.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: library.md and folder cards routed through worktree state and staging |
| src/mcp.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: worktree_root on read tools, when-to-use tool descriptions and always-on GUIDE instructions, timeout_s capped at 600 |
| src/mcp_compact.rs | 🟢 Green | 2026-11-05 10:00:58 | wiki updated (claude/limit-rule) |
| src/mcp_groups.rs | 🟢 Green | 2026-11-05 06:30:10 | wiki updated (claude/tool-groups listChanged) |
| src/parse.rs | 🟢 Green | 2026-11-11 12:35:06 | internal alias; wiki unchanged |
| src/pending_line.rs | 🟢 Green | 2026-11-05 05:19:31 | wiki (claude/windows-verify pending) |
| src/proc.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/project_config.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: a config line without = no longer ends the scan; read through worktree state |
| src/project_lock.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: lock under worktree staging so a worktree locks its overlay |
| src/scope.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: path lists and excludes read through worktree state (tree, else main) |
| src/sha256.rs | 🟢 Green | 2026-11-05 04:14:08 | wiki updated (claude/windows-verify) |
| src/symbols.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/text_out.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/timeutil.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Parity with the Python package: wiki lookup, symbols, daemon, init, flags, MCP, cycles, and low-confidence actions. |
| src/wiki_files.rs | 🟢 Green | 2026-11-11 12:01:54 | m5-fixes: wiki candidates read through worktree state (tree, else main) |
| src/worktree.rs | 🟢 Green | 2026-11-11 12:53:38 | m5-fixes review: cold first call under 2 s on Specula (git index adoption, hard-linked seed, BaseView for health and line counts) |
| tests/agent_args.rs | 🟡 Yellow | 2026-11-05 04:14:08 | new: agent-style file args, missing args, lean MCP outputs, init roots, CRLF (claude/windows-verify) |
| tests/behaviour_gaps.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Tests for those parity fixes. |
| tests/cache_and_artifacts.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Tests for those parity fixes. |
| tests/cli_surface.rs | 🟡 Yellow | 2026-11-05 08:49:40 | B7 --help prints and runs nothing; compact default MCP replies for big repos (claude/specula-fixes) |
| tests/compact_replies.rs | 🟡 Yellow | 2026-11-05 08:49:40 | B7 --help prints and runs nothing; compact default MCP replies for big repos (claude/specula-fixes) |
| tests/contract_gaps.rs | 🟡 Yellow | 2026-11-03 08:56:14 | Tests for those parity fixes. |
| tests/dogfood.rs | 🟢 Green | 2026-11-11 12:01:55 | m5-fixes: worktree overlay, glob fixture, parser stamp, config, deadline and modularity tests; dogfood dependents updated |
| tests/drift_alerts.rs | 🟢 Green | 2026-11-11 07:24:35 | Wiki matches the modularity slice (subid=modularity-alerts) |
| tests/fixtures/mcp_default.jsonl | 🟢 Green | 2026-11-11 12:01:55 | m5-fixes: worktree overlay, glob fixture, parser stamp, config, deadline and modularity tests; dogfood dependents updated |
| tests/limit_rule.rs | 🟢 Green | 2026-11-11 07:24:35 | Wiki matches the modularity slice (subid=modularity-alerts) |
| tests/m5_fixes.rs | 🟢 Green | 2026-11-11 12:01:55 | m5-fixes: worktree overlay, glob fixture, parser stamp, config, deadline and modularity tests; dogfood dependents updated |
| tests/parity.rs | 🟢 Green | 2026-11-11 12:01:55 | m5-fixes: worktree overlay, glob fixture, parser stamp, config, deadline and modularity tests; dogfood dependents updated |
| tests/parity_fixes.rs | 🟡 Yellow | 2026-11-05 05:15:33 | pending item wording and empty-queue note (claude/windows-verify speed) |
| tests/protocol_v07.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/robustness.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/skip_maps.rs | 🟡 Yellow | 2026-11-03 08:56:15 | Tests for those parity fixes. |
| tests/speed_paths.rs | 🟡 Yellow | 2026-11-05 05:37:11 | self-heal and durable user-state tests (claude/windows-verify release-5.1.0) |
| tests/tool_groups.rs | 🟢 Green | 2026-11-11 12:01:55 | m5-fixes: worktree overlay, glob fixture, parser stamp, config, deadline and modularity tests; dogfood dependents updated |
| tests/worktree_overlay.rs | 🟢 Green | 2026-11-11 12:53:38 | m5-fixes review: git index fast path test and --worktree position test |
| wikifier.sh | 🟢 Green | 2026-11-03 08:06:46 | Wiki describes the Rust binary launcher (subid=protocol-v07) |
