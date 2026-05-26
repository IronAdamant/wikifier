# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
| monitored_paths.txt | 🟡 Yellow | 2026-05-16 20:04:18 AEST | Added recipe-lab-dogfood/* paths (symlinked RecipeLab_alt) for large-scale dogfooding of Wikifier MCP on 250+ JS file non-trivial codebase. This enables dependency intelligence and health matrix stress testing on real production-like project. |
| ../../skills/run.md | 🟡 Yellow | 2026-05-17 00:23:50 AEST | mtime changed since last check-changes (auto-detected) |
| file_health.md | 🟡 Yellow | 2026-05-16 20:05:44 AEST | Bootstrapped 15 key RecipeLab_alt files as 🔴 Red stubs to enable health matrix stress testing and agent workflow on external dogfood project. Bypassed find/symlink limitation in current validate/check-changes. |
| recipe-lab-dogfood/src/wikifier-challenge/dependencyIntelligenceProbe.js | 🟢 Green | 2026-05-16 22:48:27 AEST | Challenge Feature 1 implemented + expanded with analyzeDepIntelligence() + standalone runner. Accurate. |
| recipe-lab-dogfood/src/wikifier-challenge/healthWorkflowProbe.js | 🟢 Green | 2026-05-16 22:48:28 AEST | Challenge Feature 2 implemented + real workflow stress runner. Accurate. |
| recipe-lab-dogfood/src/wikifier-challenge/mcpToolSurfaceHarness.js | 🟢 Green | 2026-05-16 22:48:28 AEST | Challenge Feature 3 implemented + surface stress. Accurate. |
| recipe-lab-dogfood/src/wikifier-challenge/longRunningStatefulStress.js | 🟢 Green | 2026-05-16 22:48:32 AEST | Challenge Feature 4 long-running implemented + runnable. Accurate. |
| recipe-lab-dogfood/src/wikifier-challenge/crossCutCombinedStress.js | 🟢 Green | 2026-05-16 22:48:32 AEST | Cross-cutting 1 implemented. Accurate. |
| recipe-lab-dogfood/src/wikifier-challenge/promptAndMCPHarness.js | 🟢 Green | 2026-05-16 22:48:33 AEST | Cross-cutting 2 prompt harness implemented. Accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/synthetic-dep-graph/core.js | 🟢 Green | 2026-05-16 22:48:38 AEST | Synthetic fixture for dep stress - accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/synthetic-dep-graph/aggregator.js | 🟢 Green | 2026-05-16 22:48:39 AEST | Fan-in fixture - accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/synthetic-dep-graph/cycleA.js | 🟢 Green | 2026-05-16 22:48:39 AEST | Cycle fixture for parser stress - accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/README.md | 🟢 Green | 2026-05-16 22:48:34 AEST | Documentation for all 6 challenges + synthetic fixtures complete and accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/wikifierStressHarness.js | 🟢 Green | 2026-05-16 22:48:35 AEST | Main harness fixed for full MCP surface + all 6 tests production ready. Accurate. |
| recipe-lab-dogfood/MCP_Findings/wikifier_open.md | 🟢 Green | 2026-05-16 22:54:30 AEST | Master dogfood report complete, accurate, and comprehensive. All requirements satisfied. Wikifier workflow followed end-to-end for the report file itself. |
| recipe-lab-dogfood/src/internal/wikifier-stress/synthetic-dep-graph/churnA.js | 🟢 Green | 2026-05-16 22:54:44 AEST | Churn fixture from cross-cut test - accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/synthetic-dep-graph/churnB.js | 🟢 Green | 2026-05-16 22:54:45 AEST | Churn fixture - accurate. |
| recipe-lab-dogfood/src/internal/wikifier-stress/synthetic-dep-graph/churnC.js | 🟢 Green | 2026-05-16 22:54:46 AEST | Churn fixture - accurate. |
| wikifier.sh | 🟢 Green | 2026-05-17 16:21:03 AEST | Core CLI implemented and documented. |
