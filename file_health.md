# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| .github/workflows/publish.yml | 🟢 Green | 2026-05-15 21:39:44 AEST | Wiki summary verified accurate after change. |
| Findings/m2_rem_08_combined_dogfood_findings_open.md | 🟢 Green | 2026-05-17 00:29:11 | Investigation officially initiated. Dedicated log created and first analysis steps begun. |
| Findings/m2_rem_08_dogfood_gaps_closed.md | 🟢 Green | 2026-05-16 23:23:42 | M2-Rem-08 dogfood gaps report closed and renamed from _open. Content updated to reflect completion of M2-Rem-06, M2-Rem-07 final polish, and MCP Final Robustness on the Wikifier project. |
| Findings/m2_rem_08_dogfood_gaps_open.md | 🟢 Green | 2026-05-16 23:13:12 | MCP Final Robustness section updated in the gap report after completing the consistency and structured return improvements. |
| Logged_issues/high/import/m2-dependency-intelligence-tasks.md | 🟡 Yellow | 2026-05-16 12:10:34 AEST | Continued progress on A12, B12, C12. |
| Logged_issues/high/import/m2-gap-closure-dependency-intelligence.md | 🟢 Green | 2026-05-17 08:36:54 | Profiling harness work started. |
| Logged_issues/high/import/update-maps-v0.4-planning.md | 🟢 Green | 2026-05-15 22:27:36 AEST | Planning document completed and approved. |
| Logged_issues/map.md | 🟢 Green | 2026-05-15 22:05:18 AEST | Wiki summary verified accurate after change. |
| Logged_issues/moderate/backend/health-matrix-flakiness.md | 🟡 Yellow | 2026-05-15 22:05:18 AEST | Initial issue created for Milestone 1 - Core Reliability. |
| Logged_issues/moderate/backend/m1-core-reliability-tasks.md | 🟡 Yellow | 2026-05-15 22:25:06 AEST | Completed M1-A3 and M1-A4: Exit codes standardized + better error messages for health operations. |
| Logged_issues/moderate/other/python-library-design.md | 🟡 Yellow | 2026-05-15 22:08:04 AEST | Created focused design issue for the Python library API (split from previous broad issue). |
| Logged_issues/moderate/other/python-library-initial-implementation.md | 🟡 Yellow | 2026-05-15 22:08:04 AEST | Created implementation issue for initial Python library (split from previous broad issue). |
| Logged_issues/v0.4-roadmap.md | 🟡 Yellow | 2026-05-16 11:37:03 AEST | Linked to the new detailed v0.4-execution-plan.md. |
| MANIFEST.in | 🟢 Green | 2026-05-15 21:42:40 AEST | Wiki summary verified accurate after change. |
| README.md | 🟢 Green | 2026-05-16 23:05:45 | M2-Rem-06 Documentation & Packaging Clarity pass complete. Added prescriptive scaling table by project size, clear pip install + external bootstrap workflow, and improved root detection decision order. Directly addresses remaining gaps in m2_rem_08_dogfood_gaps_open.md. |
| library.md | 🟢 Green | 2026-05-16 18:58:53 AEST | Regenerated after including wikifier/mcp/ in monitored paths. MCP server files now appear in dependency graph and reverse dependencies. |
| pyproject.toml | 🟢 Green | 2026-05-15 21:42:44 AEST | Finalized for v0.3.0 PyPI release. Ready for automated publishing. |
| recipe-lab-dogfood/MCP_Findings/wikifier_open.md | 🟢 Green | 2026-05-16 23:29:54 | Comprehensive dogfood report verified: 6 challenge features, exhaustive MCP surface (20+ tools/resources/prompts), all limitations and recommendations documented. Zero other MCPs used. |
| recipe-lab-dogfood/public/app.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — client-side UI logic. |
| recipe-lab-dogfood/src/api/app.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — Express app entry, route wiring. |
| recipe-lab-dogfood/src/api/routeLoader.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — Phase 16 split core, facade for routes. |
| recipe-lab-dogfood/src/cli/index.js | 🟢 Green | 2026-05-16 21:49:50 | Lazy loading complete. CLI is now safe for wikifier-stress execution. All Wikifier workflow steps followed. |
| recipe-lab-dogfood/src/internal/mcp-stress/legacy/routeLoader.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — legacy code for MCP stress history. |
| recipe-lab-dogfood/src/internal/wikifier-stress/README.md | 🟢 Green | 2026-05-16 21:48:43 | Documentation complete and accurate. Harness is now a first-class, self-describing, usable addition to the RecipeLab project for ongoing Wikifier dogfooding. |
| recipe-lab-dogfood/src/internal/wikifier-stress/wikifierStressHarness.js | 🟢 Green | 2026-05-16 23:03:12 | autonomy cycle 1 complete |
| recipe-lab-dogfood/src/models/Ingredient.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — used by Recipe, importers, nutrition pipelines. |
| recipe-lab-dogfood/src/models/Recipe.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub for Wikifier dogfood — core domain model, many dependents in services/routes. |
| recipe-lab-dogfood/src/plugins/PluginSystemFacade.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — Phase 16 facade, complex plugin hooks. |
| recipe-lab-dogfood/src/services/mealPlannerService.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — central service with many cross-deps (search, shopping, nutrition). |
| recipe-lab-dogfood/src/services/searchService.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — heavily used, complex query logic. |
| recipe-lab-dogfood/src/services/similarityService.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — Phase 7 service, used by recommendations. |
| recipe-lab-dogfood/src/services/versionControlService.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — recipe versioning, complex. |
| recipe-lab-dogfood/src/utils/validation.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — shared validation, depended by many. |
| recipe-lab-dogfood/tests/testRunner.js | 🔴 Red | 2026-05-16 20:10:00 AEST | Initial stub — custom test runner, 564+ tests. |
| skills/run.md | 🟢 Green | 2026-05-16 23:35:55 | Verified during M2-Rem-08 dogfood. Content remains accurate after recent concurrency and packaging updates. |
| src/internal/wikifier-stress/synthetic-dep-graph/churnA.js | 🟡 Yellow | 2026-05-16 22:52:23 | Heavy churn test file 0 |
| src/internal/wikifier-stress/synthetic-dep-graph/churnB.js | 🟡 Yellow | 2026-05-16 22:52:23 | Heavy churn test file 1 |
| src/internal/wikifier-stress/synthetic-dep-graph/churnC.js | 🟡 Yellow | 2026-05-16 22:52:24 | Heavy churn test file 2 |
| test/atomic-test.md | 🟢 Green | 2026-05-15 22:20:52 AEST | Testing improved mark-green logging |
| test/journal-format.md | 🟡 Yellow | 2026-05-15 22:23:20 AEST | Testing standardized journal format with separator (M1-B4) |
| test/json-test.md | 🔴 Red | 2026-05-15 22:22:20 AEST | DELETED — Testing deletion with JSON |
| v0.4-Execution-Plan.md | 🟡 Yellow | 2026-05-16 12:42:09 AEST | User confirmed: Continue parallel A/B/C grinding on M2 before evaluating against Success Markers. |
| v0.4-execution-plan.md | 🟡 Yellow | 2026-05-16 11:37:03 AEST | Created comprehensive v0.4 Execution Plan with checkbox tracking for all milestones and tasks. |
| wikifier.sh | 🟢 Green | 2026-05-17 16:21:10 AEST | Core CLI implemented and documented. |
| wikifier/__init__.py | 🟢 Green | 2026-05-15 21:42:40 AEST | Wiki summary verified accurate after change. |
| wikifier/cli.py | 🟢 Green | 2026-05-15 21:39:47 AEST | Wiki summary verified accurate after change. |
| wikifier/health.py | 🟢 Green | 2026-05-16 21:03:53 | File locking integrated for concurrent safety (M2-Rem-07). |
| wikifier/import_cache.py | 🟢 Green | 2026-05-16 21:04:02 | File locking integrated (M2-Rem-07). |
| wikifier/locking.py | 🟢 Green | 2026-05-16 23:10:19 | Final polish on M2-Rem-07 complete: Robustness improvements, new diagnostic helper (is_project_locked), better documentation, and agent clarity. |
| wikifier/mcp/README.md | 🟢 Green | 2026-05-16 23:05:53 | M2-Rem-06: Strengthened external project targeting and pip install bootstrap instructions in the MCP context. |
| wikifier/mcp/__init__.py | 🟢 Green | 2026-05-16 18:55:36 AEST | Package initializer for the MCP module. |
| wikifier/mcp/client-configs/README.md | 🟢 Green | 2026-05-16 23:05:56 | M2-Rem-06: Added packaging and external project bootstrap tips for MCP client users. |
| wikifier/mcp/server.py | 🟢 Green | 2026-05-17 01:08:29 | Fix 9 polished: Richer data (raw, resolved, confidence) exposed in get_dependencies. |
| wikifier/mcp/server.py.wiki.md | 🟢 Green | 2026-05-16 23:13:00 | Wiki summary refreshed after MCP final robustness improvements. |
| wikifier/parsers/javascript.py | 🟢 Green | 2026-05-17 08:33:49 | Quick win prototype: Directory marker memoization added to JS bare resolver. |
| wikifier/parsers/javascript.py.wiki.md | 🟢 Green | 2026-05-16 23:35:44 | Wiki summary is complete and accurate. Part of thorough M2-Rem-08 dogfood. |
| wikifier/parsers/python.py | 🟢 Green | 2026-05-17 01:02:26 | Fix 3 complete: Python parser now emits resolution_confidence. |
| wikifier/parsers/python.py.wiki.md | 🟢 Green | 2026-05-16 23:35:41 | Wiki summary is complete and accurate. Part of thorough M2-Rem-08 dogfood. |
| Findings/v1_visual_layer_architecture.md | 🟢 Green | 2026-05-18 16:29:49 AEST | V1-P1 Architecture Document complete and self-documenting as frozen reference for the wave. No separate wiki.md needed for Findings report; content serves as authoritative summary. Health promoted to Green per agent protocol. |
| index.html | 🟢 Green | 2026-05-18 16:48:11 AEST | V1-P2 Command Surface role completed and verified by main agent. Post-trim lightweight implementation is stable, error-free, and compliant with P6 performance rules and frozen architecture. |
| diagnostics.html | 🟢 Green | 2026-05-18 16:39:44 AEST | V1-P4 created full human refactor/porter hub (~39KB). All sections delivered: Arch Glance, Porting Checklist, Command Impl Map with .wiki.md links, Key Files consuming existing wiki.md, monorepo realities, visual port notes. Process followed (prepare+record+mark-green). Size impact to P6: combined visual ~85.7KB close to cap, P6 to validate/trim if needed. |
| Findings/p6_real_world_validation_report.md | 🟢 Green | 2026-05-18 16:39:52 AEST | P6 notified of V1-P4 visual size impact (46.6KB index + 39KB diagnostics). Awaiting P6 sign-off/validation per wave charter. |
| Findings/v1_visual_layer_wave_closure_report.md | 🟢 Green | 2026-05-18 16:48:53 AEST | V1-P8 Closer report finalized and wave officially closed. All P1–P7 deliverables accounted for and integrated. |
