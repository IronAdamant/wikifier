# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| .github/workflows/publish.yml | 🟢 Green | 2026-06-10 14:50:34 AEST | Verified: bash -n, dynamic banner shows v4.2.0 from package, YAML parses, 28/28 tests, packaged copies identical |
| CHANGELOG.md | 🟢 Green | 2026-07-09 08:07:42 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| CLAUDE.md | 🟢 Green | 2026-07-09 06:14:09 | test count synced to 49 |
| Findings/2026-06-10-Dogfood-Refactor-Validation.md | 🟢 Green | 2026-06-10 09:54:26 AEST | Self-describing findings doc |
| Findings/2026-06-10-Fix-Plan.md | 🟢 Green | 2026-06-10 14:20:33 AEST | Results appended, all phases verified |
| Findings/M5-Dogfood-Assessment-Report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/M5-Dogfood-Progress.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/M5.1-cross-hardening-analysis.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/Milestones-Overview.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/dogfood-goal-pass1-2026-07-09.json | 🟢 Green | 2026-07-09 07:07:11 | goal verification complete |
| Findings/dogfood-goal-pass2-2026-07-09.json | 🟢 Green | 2026-07-09 07:07:11 | goal verification complete |
| Findings/dogfood-hygiene-fix-2026-07-09.json | 🟢 Green | 2026-07-09 06:34:48 | verified 53 tests; dogfood validate 0/8 |
| Findings/dogfood-hygiene-fix-2026-07-09.md | 🟢 Green | 2026-07-09 06:34:48 | verified 53 tests; dogfood validate 0/8 |
| Findings/gap-closure-report.md | 🟢 Green | 2026-07-09 05:40:10 | G12 closed; 39/39 tests |
| Findings/long-horizon-autonomous-ops.md | 🟢 Green | 2026-07-09 07:07:11 | goal verification complete |
| Findings/p6_real_world_validation_report.md | 🟢 Green | 2026-07-09 05:02:27 | kept; stale yellow cleared |
| Findings/residual-1-5-closure-2026-07-09.md | 🟢 Green | 2026-07-09 08:07:43 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| Logged_issues/2026-06-10-brc-scoped-rerun-pathology.md | 🟢 Green | 2026-06-10 19:09:35 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; sh update-maps 3m39s->2.0s + hung incremental now 1.5s; Babylon scoped re-run 75min->80.6s, cache 274MB->101MB; all 12 sh commands smoke-tested |
| Logged_issues/2026-06-10-js-barrel-churn-selftest-failure.md | 🟢 Green | 2026-06-10 14:19:50 AEST | v4.2.0 fix pass verified: 28/28 unittest, parser self-tests (churn 4/4), llama_index 3837/3837 files 8.5s, Babylon 3905/3905, RecipeLab library.md recovered, redox honest reporting, health CLI flags, MCP smoke. |
| README.md | 🟢 Green | 2026-07-09 05:52:23 | lang table |
| diagnostics.html | 🟢 Green | 2026-06-05 08:33:20 AEST | Wiki summary verified accurate after change. |
| file_health.md | 🟢 Green | 2026-06-07 12:47:31 AEST | Phase 1 cruft pruning complete (bulk historical M2-M4/Logged/etc removed per audit). Survivors re-marked Green. subid=simplification-cruft-phase-1. |
| index.html | 🟢 Green | 2026-06-11 00:20:17 AEST | Verified: 30/30 tests; tree generated on all 9 projects (llvm 2,940 files renders as clean indented tree); headless 9/9 tree-ok + lazy graph + forced-open render + pan-zoom canvas + file:// banner; parser comment-leak repro now 0 garbage edges |
| library.md | 🟢 Green | 2026-06-10 20:20:38 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| pyproject.toml | 🟢 Green | 2026-06-10 14:41:19 AEST | Build + twine check pass; clean-room wheel install verified |
| screenshot/front_page_review.png | 🟢 Green | 2026-06-11 00:37:47 AEST | Asset referenced by README |
| skills/run.md | 🟢 Green | 2026-07-09 06:55:03 | 4.5.7 verified tests |
| tests/ | 🟢 Green | 2026-06-10 16:59:05 AEST | Verified: 30/30 unittest, exports 8/8, churn 4/4; Babylon full run 25m52s->5m52s and 417k->44k edges; worst file 990->55; RecipeLab identical 671 edges; e2e cache carries imported_names + barrel_leaf_selection |
| tests/__init__.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/_base.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/run_all.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/selftest/__init__.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/selftest/run_cdia_selftest.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/selftest/run_contracts_selftest.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/selftest/run_javascript_selftest.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/selftest/run_python_parser_selftest.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/selftest/run_resolution_selftest.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/test_barrel_invalidation.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/test_gap_closure.py | 🟢 Green | 2026-07-09 08:07:42 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| tests/test_health.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/test_import_cache.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/test_multi_lang_parsers.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/test_parsers.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| tests/test_selftest_wrappers.py | 🟢 Green | 2026-07-09 05:40:10 | G12 closed; 39/39 tests |
| wikifier.bat | 🟢 Green | 2026-06-10 14:50:33 AEST | Verified: bash -n, dynamic banner shows v4.2.0 from package, YAML parses, 28/28 tests, packaged copies identical |
| wikifier.ps1 | 🟢 Green | 2026-06-10 20:20:31 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier.sh | 🟢 Green | 2026-07-09 05:32:45 | gap-closure swarm verified 34/34 tests |
| wikifier/__init__.py | 🟢 Green | 2026-07-09 08:07:41 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| wikifier/__main__.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| wikifier/cli.py | 🟢 Green | 2026-07-09 08:07:38 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| wikifier/contracts.py | 🟢 Green | 2026-07-09 06:13:34 | mtime-only / post-4.5.x auto-yellow cleared; git content clean at mark-green (hygiene session subid=hygiene-cleanup); no wiki-prose change required (map-first) |
| wikifier/daemon.py | 🟢 Green | 2026-07-09 07:58:09 | mtime-only auto-yellow cleared (session tour check-changes); no content edit this session; map-first no wiki rewrite (subid=fix-yellows) |
| wikifier/diagnostics.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| wikifier/health.py | 🟢 Green | 2026-07-09 07:58:09 | mtime-only auto-yellow cleared (session tour check-changes); no content edit this session; map-first no wiki rewrite (subid=fix-yellows) |
| wikifier/import_cache.py | 🟢 Green | 2026-07-09 08:07:44 | post residual-1-5 hygiene mtime clear (subid=residual-1-5-closure) |
| wikifier/index.html | 🟢 Green | 2026-06-11 00:20:18 AEST | Verified: 30/30 tests; tree generated on all 9 projects (llvm 2,940 files renders as clean indented tree); headless 9/9 tree-ok + lazy graph + forced-open render + pan-zoom canvas + file:// banner; parser comment-leak repro now 0 garbage edges |
| wikifier/library.py | 🟢 Green | 2026-06-11 00:20:14 AEST | Verified: 30/30 tests; tree generated on all 9 projects (llvm 2,940 files renders as clean indented tree); headless 9/9 tree-ok + lazy graph + forced-open render + pan-zoom canvas + file:// banner; parser comment-leak repro now 0 garbage edges |
| wikifier/locking.py | 🟢 Green | 2026-06-10 14:19:39 AEST | v4.2.0 fix pass verified: 28/28 unittest, parser self-tests (churn 4/4), llama_index 3837/3837 files 8.5s, Babylon 3905/3905, RecipeLab library.md recovered, redox honest reporting, health CLI flags, MCP smoke. |
| wikifier/mcp/README.md | 🟢 Green | 2026-07-09 05:02:27 | stale yellow cleared |
| wikifier/mcp/__init__.py | 🟢 Green | 2026-06-10 09:27:38 AEST | Refactor verified: py_compile + no-mcp/no-fcntl import sims + parser self-tests + check-changes/update-maps/health smoke all pass. Interface unchanged. |
| wikifier/mcp/server.py | 🟢 Green | 2026-07-09 07:58:09 | mtime-only auto-yellow cleared (session tour check-changes); no content edit this session; map-first no wiki rewrite (subid=fix-yellows) |
| wikifier/parsers/__init__.py | 🟢 Green | 2026-07-09 06:13:34 | mtime-only / post-4.5.x auto-yellow cleared; git content clean at mark-green (hygiene session subid=hygiene-cleanup); no wiki-prose change required (map-first) |
| wikifier/parsers/_edge.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| wikifier/parsers/bree.py | 🟢 Green | 2026-07-09 08:07:40 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| wikifier/parsers/c_cpp.py | 🟢 Green | 2026-07-09 05:52:22 | dogfood llvm/linux |
| wikifier/parsers/cdia.py | 🟢 Green | 2026-07-09 06:13:34 | mtime-only / post-4.5.x auto-yellow cleared; git content clean at mark-green (hygiene session subid=hygiene-cleanup); no wiki-prose change required (map-first) |
| wikifier/parsers/csharp.py | 🟢 Green | 2026-07-09 05:52:22 | dogfood dotnet |
| wikifier/parsers/go_lang.py | 🟢 Green | 2026-07-09 05:52:22 | dogfood |
| wikifier/parsers/java.py | 🟢 Green | 2026-07-09 06:34:55 | hygiene session complete 4.5.6; 53 tests OK |
| wikifier/parsers/javascript.py | 🟢 Green | 2026-07-09 08:07:40 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| wikifier/parsers/python.py | 🟢 Green | 2026-07-09 06:13:34 | mtime-only / post-4.5.x auto-yellow cleared; git content clean at mark-green (hygiene session subid=hygiene-cleanup); no wiki-prose change required (map-first) |
| wikifier/parsers/rust.py | 🟢 Green | 2026-07-09 05:52:21 | dogfood rust/redox |
| wikifier/project_root.py | 🟢 Green | 2026-07-09 08:07:38 | residual-1-5-closure verified; tests OK (subid=residual-1-5-closure) |
| wikifier/resolution.py | 🟢 Green | 2026-07-09 06:13:34 | mtime-only / post-4.5.x auto-yellow cleared; git content clean at mark-green (hygiene session subid=hygiene-cleanup); no wiki-prose change required (map-first) |
| wikifier/scripts/wikifier.ps1 | 🟢 Green | 2026-06-10 20:20:33 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
| wikifier/scripts/wikifier.sh | 🟢 Green | 2026-07-09 05:02:49 | synced with root; portable rel paths (subid=post-assess-hygiene) |
| wikifier/serve.py | 🟢 Green | 2026-06-10 20:20:23 AEST | Verified: endpoint whitelist + Origin/Host 403s + clean shutdown via curl; headless DOM on all 9 projects x 3 modes (exec/static/file): map renders, exec chip + Stop button, no Tailwind, no active errors; 30/30 tests |
