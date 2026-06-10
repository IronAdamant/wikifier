# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| skills/run.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| Findings/Milestones-Overview.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| Findings/M5-Dogfood-Progress.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| wikifier.sh | 🟢 Green | 2026-06-10 20:20:28 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| Findings/M5-Dogfood-Assessment-Report.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| Findings/p6_real_world_validation_report.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| Findings/M5.1-cross-hardening-analysis.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| --help | 🟢 Green | 2026-06-04 06:50:01 AEST | Wiki summary verified accurate after change. |
| M5.3 Cycle1 evidence append: 3 subs spawned+running (alt BRC20 named, trammel48, consist/llvm metrics, 72h gate start, FRESH3, 9GPs/DoD maps, subid=m5.3-coord-agents) | 🔴 Red | 2026-06-04 15:44:23 AEST | DELETED — Historical early M5.3 launch note from coord sub (pre full alt gate pass + sustained monitors). Superseded by complete agent records in M5-Dogfood-Progress.md (alt sub 1356s exit0 gate claim, 2 other subs rich, monitors running). Cleaned as part of post-M5 skills/MCP refresh. |
| README.md | 🟢 Green | 2026-06-10 20:20:34 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier/mcp/server.py | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| wikifier/mcp/README.md | 🟡 Yellow | 2026-06-10 20:15:48 AEST | mtime changed since last check-changes (auto-detected) |
| wikifier/cli.py | 🟢 Green | 2026-06-10 19:09:27 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| diagnostics.html | 🟢 Green | 2026-06-05 08:33:20 AEST | Wiki summary verified accurate after change. |
| index.html | 🟢 Green | 2026-06-10 20:20:25 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier/import_cache.py | 🟢 Green | 2026-06-10 19:09:24 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| wikifier/parsers/python.py | 🟢 Green | 2026-06-10 09:27:51 AEST | Refactor verified: py_compile + no-mcp/no-fcntl import sims + parser self-tests + check-changes/update-maps/health smoke all pass. Interface unchanged. |
| file_health.md | 🟢 Green | 2026-06-07 12:47:31 AEST | Phase 1 cruft pruning complete (bulk historical M2-M4/Logged/etc removed per audit). Survivors re-marked Green. subid=simplification-cruft-phase-1. |
| CHANGELOG.md | 🟢 Green | 2026-06-10 20:22:28 AEST | v4.4.0 release prep; 30/30 tests |
| CLAUDE.md | 🟢 Green | 2026-06-10 19:09:30 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| wikifier/__init__.py | 🟢 Green | 2026-06-10 20:22:27 AEST | v4.4.0 release prep; 30/30 tests |
| wikifier/mcp/__init__.py | 🟢 Green | 2026-06-10 09:27:38 AEST | Refactor verified: py_compile + no-mcp/no-fcntl import sims + parser self-tests + check-changes/update-maps/health smoke all pass. Interface unchanged. |
| wikifier/health.py | 🟢 Green | 2026-06-10 09:27:42 AEST | Refactor verified: py_compile + no-mcp/no-fcntl import sims + parser self-tests + check-changes/update-maps/health smoke all pass. Interface unchanged. |
| wikifier/contracts.py | 🟢 Green | 2026-06-10 09:27:43 AEST | Refactor verified: py_compile + no-mcp/no-fcntl import sims + parser self-tests + check-changes/update-maps/health smoke all pass. Interface unchanged. |
| wikifier/locking.py | 🟢 Green | 2026-06-10 14:19:39 AEST | v4.2.0 fix pass verified: 28/28 unittest, parser self-tests (churn 4/4), llama_index 3837/3837 files 8.5s, Babylon 3905/3905, RecipeLab library.md recovered, redox honest reporting, health CLI flags, MCP smoke. |
| wikifier/daemon.py | 🟢 Green | 2026-06-10 09:27:49 AEST | Refactor verified: py_compile + no-mcp/no-fcntl import sims + parser self-tests + check-changes/update-maps/health smoke all pass. Interface unchanged. |
| wikifier/scripts/wikifier.sh | 🟢 Green | 2026-06-10 20:20:30 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier/index.html | 🟢 Green | 2026-06-10 20:20:26 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| Logged_issues/2026-06-10-js-barrel-churn-selftest-failure.md | 🟢 Green | 2026-06-10 14:19:50 AEST | v4.2.0 fix pass verified: 28/28 unittest, parser self-tests (churn 4/4), llama_index 3837/3837 files 8.5s, Babylon 3905/3905, RecipeLab library.md recovered, redox honest reporting, health CLI flags, MCP smoke. |
| Findings/2026-06-10-Dogfood-Refactor-Validation.md | 🟢 Green | 2026-06-10 09:54:26 AEST | Self-describing findings doc |
| Findings/2026-06-10-Fix-Plan.md | 🟢 Green | 2026-06-10 14:20:33 AEST | Results appended, all phases verified |
| wikifier/library.py | 🟢 Green | 2026-06-10 14:19:34 AEST | v4.2.0 fix pass verified: 28/28 unittest, parser self-tests (churn 4/4), llama_index 3837/3837 files 8.5s, Babylon 3905/3905, RecipeLab library.md recovered, redox honest reporting, health CLI flags, MCP smoke. |
| wikifier/parsers/bree.py | 🟢 Green | 2026-06-10 19:09:22 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| wikifier/parsers/javascript.py | 🟢 Green | 2026-06-10 19:09:25 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| tests/ | 🟢 Green | 2026-06-10 16:59:05 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; Babylon full run 25m52s->5m52s and 417k->44k edges; worst file 990->55; RecipeLab identical 671 edges; e2e cache carries imported_names + barrel_leaf_selection |
| pyproject.toml | 🟢 Green | 2026-06-10 14:41:19 AEST | Build + twine check pass; clean-room wheel install verified |
| wikifier.ps1 | 🟢 Green | 2026-06-10 20:20:31 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier.bat | 🟢 Green | 2026-06-10 14:50:33 AEST | Verified: bash -n, dynamic banner shows v4.2.0 from package, YAML parses, 28/28 tests, packaged copies identical |
| .github/workflows/publish.yml | 🟢 Green | 2026-06-10 14:50:34 AEST | Verified: bash -n, dynamic banner shows v4.2.0 from package, YAML parses, 28/28 tests, packaged copies identical |
| Logged_issues/2026-06-10-brc-scoped-rerun-pathology.md | 🟢 Green | 2026-06-10 19:09:35 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| wikifier/scripts/wikifier.ps1 | 🟢 Green | 2026-06-10 20:20:33 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier/serve.py | 🟢 Green | 2026-06-10 20:20:23 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| library.md | 🟢 Green | 2026-06-10 20:20:38 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
