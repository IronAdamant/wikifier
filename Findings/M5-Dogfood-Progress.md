# M5 Dogfood Progress Tracker

**Phase**: M5 – Broad real-world dogfooding & final 95%+ / 5-10yr viability gate
**Started**: 2026-06-02 (user: "We are now in M5 phase. We've got plans set up and ready for the upcoming dogfood testing.")
**Targets (allowed only)**: RecipeLab (large creative JS monorepo with heavy services/plugins/barrels/tests), test-js-flat (small JS), harness long-term suites (25k-50k+), user-designated external 5k-50k+ creatives.
**Strict Boundary**: Zero dogfood on Wikifier source itself. All usage via explicit project_root / WIKIFIER_PROJECT_ROOT. Main tree remains 100% clean (docs/Findings/ updates only, with full discipline).

## Initial M5 Activities (2026-06-02)
- Milestones-Overview.md refreshed: M1-M4 marked complete, M5 status/mandate/boundary/next-steps updated, M5 entry note added (subagent_id=m5-gamma-coord).
- Main project health: cleared pending yellows (skills/run.md + the new M5 doc) via record-change + mark-green. Now all 🟢 Green.
- Dogfood runs on prepared targets:
  - RecipeLab: `WIKIFIER_PROJECT_ROOT=... wikifier check-changes` + `health --summary` + `validate` + `heal-stubs --dry-run`. Exercised barrel auto-yellow on 20 importers, incremental detection, health matrix (noted some legacy worktree path pollution in BRC stale entries from prior subagent WTs + test-js-flat refs mixed in).
  - test-js-flat: check-changes + health exercised (small target).
- Trammel plans review: recipe-lab-dogfood/trammel.db has 72 plans (49 pending, 23 completed) — these are the "plans set up" for driving usage/testing (refactors, challenges exercising wikifier + other MCPs). Main trammel.db at 0 (as expected; M5 not for main code planning).
- Journal entry created for the milestones edit.
- Protocol followed for all main-tree activity (record-change, mark-green).

## Known Observations from Initial Runs
- Barrel invalidation + BRC reporting active and marking Yellow on importers (good signal for M5 long-running).
- Health matrix in RecipeLab target carries forward some stale barrel entries referencing old worktree paths (e.g. subagent-86-E2/test-js-flat/*). This is audit item for M5 resilience (not a wikifier bug per se; prior mixed runs). heal-stubs found 0; may need targeted record or time-based pruning in long runs.
- No new changes auto-detected on stable targets; good for "set & forget" baseline.
- MCP wikifier tools (get_project_status etc) timed out on large RecipeLab target (shell paths used successfully instead; consistent with prior packaging/dogfood feedback addressed in M2-Rem-06).

## Next (Ongoing Dogfood)
- Sustained concurrent runs (MA + daemon + occasional human) on RecipeLab + harness 50k+ suites + externals.
- Collect metrics: bounded mem/disk, compaction success rates, recovery latency, obs usefulness after days/weeks, "3"/partials 0-corruption, health stability, barrel correctness under churn.
- Append evidence to this doc + p6_real_world_validation_report.md (or M5-specific reports) with verbatim runs, 9 GPs traces, FRESH "3" hygiene (for any main docs), subagent_id, honest calib.
- Periodic health audits + prune on targets.
- Use trammel (in target dbs) + wikifier (root-targeted) + supporting chisel/stele for full MCP dogfood signal.
- Produce rich diaries in WTs or Findings/ for any coordination.

## 9 Guiding Principles Compliance (M5)
All M5 activity will log adherence (esp #1 spectrum on 50k+ creative, #8 allowed-targets/M5-boundary, #9 measurable exits on real dogfood, #2 zero-dep, #4/5/6/7 state surfaces).

See M4-80-95-Completion-Package-Handoff.md + M4-Years-Scale-Agent-Builder-Guide.md + Milestones-Overview.md for full mandate, limitations, what M5 must prove at literal multi-month scale.

**Current overall M5 status**: Just started. Plans + targets ready. Initial smoke dogfood successful. Ready for long-horizon autonomous evidence collection.
## Dogfood Session 2026-06-03 (post "been a while" – sustained signals)

**subagent_id=m5-gamma-coord-2** (M5 coordination / evidence harvest; 100% M5 boundary, zero-dep, main clean, allowed-targets only, FRESH "3" hygiene pre-append (verbatim "0 def matches (FRESH LAST PASS for M5 doc append)"), 8-step/9GP traces in this entry + prior).

**Actions executed (via MCP + shell + lib, root-targeted for externals):**
- Re-ran wikifier check-changes + health --summary + python lib health(json) + file_health/pending inspect on RecipeLab + test-js-flat (and main protocol).
- Chisel MCP full dogfood on RecipeLab (the dedicated stress target for chisel/stele/trammel/wikifier): chisel__start_job(kind=analyze, directory=.../recipe-lab-dogfood) -> job completed (269 code files, 1255 code units, 11 test files, 52 test units, 111 commits parsed, test_edges_built=0). Then triage, test_gaps (on src/services), risk_map, suggest_tests (on mealPlannerService.js).
- Stele-context MCP: stele-context__doctor (full snapshot), stele-context__map (compact, exercised).
- Trammel re-inspect (sqlite on target db for metrics; MCP trammel status on main=0).
- All via WIKIFIER_PROJECT_ROOT or directory= for scoping.

**Concrete metrics collected (harvestable evidence):**
- RecipeLab (269 JS files, heavy services/plugins/barrels/dynamic, deliberate test gaps in importers/exporters/challengeFeatures):
  - wikifier: check-changes: "No new changes detected", "Healed 0", "Pruned 0", but "[barrel] auto-marked 20 importer(s) Yellow via BRC reports (daemon/check-changes)" – consistent signal.
  - health --summary: 20+ 🟡 Yellow entries (top: worktree-polluted stale barrel re-exports e.g. subagent-86-E2/test-js-flat/... + challenge* tests + src/exporters/csvExporter.js mtime + many test/* re-exports from services/* + utils/*). pending_updates.md: 1 entry (csvExporter).
  - lib health(json) + file_health.json: tracked entries low in json view (0 reported in one parse; relies on .md + internal), yellow ~20.
  - Incremental/validate/heal: exercised, 0 heals.
- test-js-flat (small): 1 yellow (pollution ../skills/run.md from main context).
- Main: 3 🟢 Green (M5 docs + protocol).
- Chisel on RecipeLab (post-analyze):
  - analyze result: code_files_scanned=269, code_units=1255, test_files=11, test_units=52, test_edges_built=0, commits=111.
  - triage: files_triaged=0, test_gaps=0, stale=0, test_edge_count=0 (summary: "no data" pre-analyze, post: 0 risk due to 0 edges).
  - test_gaps (src/services): [] – "All code units have test coverage" (heuristic fallback since no DB edges; import resolution treated as covered?).
  - risk_map: files=[], total_files=0, "insufficient_files".
  - suggest_tests (mealPlannerService.js core service): 5 results, all relevance=0.1, source="fallback" (stem-matched unrelated .venv jeepney asyncio tests, not real project tests). Next: verify_in_repo.
- Stele on session (main index, 22 docs/886 chunks, focused on .stele internals + some Findings diar ies; symbol_graph empty, tier2=0%):
  - doctor: stele v1.3.3, project_root=Wikifier, storage=.stele-context, index_health alerts (symbol graph empty; need rebuild_symbols), editable install mismatches for chisel/trammel/stele/coordinationhub etc (point to sibling /Chisel /Trammel etc – potential stale in worktree setups), search_quality tier2 0.0 (BM25 fallback), db wal healthy.
  - map (compact): returned 0 documents in this call (index_health still 22/886, seconds_since_last ~127k), project_root confirmed Wikifier. (Prior doctor had preview of 22 incl .stele db chunks + Findings/*.md + wave-evidence txts.)
- Trammel (target db): 72 plans stable (49 pending, 23 completed). Pending samples: multiple duplicate "Add a real-time collaborative recipe editing system..." (71,69,68,...), completed e.g. recipeBuildPipeline test, seasonalRecipeRotator. Main MCP trammel: 0 plans/recipes. (The 49 pending are the "plans set up" for exercising during dogfood of trammel + wikifier on this creative target.)
- Other: chisel job used background start_job + poll (progress 100%, full events trace: scan -> parse -> blame -> churn -> edges (0) -> cleanup). Good for long-pole.

**Observations / gaps surfaced (M5 value):**
- wikifier barrel/BRC + health matrix: strong sustained signal on importers (20 auto-yellow), but health carries persistent stale worktree pollution (from prior M4 subagent WTs mixing test-js-flat paths into RecipeLab health) + cross-project leakage (skills/run.md, ../ paths). This is resilience/obs test case for M5 long-running (prune, heal, barrel re-export detection under churn/MA). "set & forget" baseline good (no new changes auto).
- Chisel: exactly as designed in RecipeLab (deliberate gaps in importers/exporters/services without tests, CJS/hybrid, many dynamic). Post-analyze: 0 test edges (known open: needs import-graph coupling, working-tree, graduated coverage). suggest_tests/risk/triage fall to weak fallback/stem/0. Surfaces the "NOT FIXED" from CLAUDE.md Phase 1-7 + reviews. Good dogfood: MCP exercised end-to-end (start_job for scale, triage as recon).
- Stele: strong on main (doctor/map), but index not covering recipe-lab (separate project; would need explicit index or path_prefix + working_tree scan for new). Symbol graph empty (need rebuild). Low tier2 semantic. Exercised the surfaces; alerts useful for orient.
- Cross-MCP: wikifier + chisel + stele all exercised on the prepared dogfood target without violating M5 boundary. Trammel plans in target db ready for claim/record in contexts that use the target's trammel.db.
- MCP wikifier direct (get_* with project_root): continued timeouts on large target (shell/lib reliable).
- 9 GPs upheld: #1 spectrum (small test-js-flat + massive RecipeLab creative with barrels/dyn/ws/churn/partials via challenge), #8 M5 boundary + allowed only, #2 zero-dep, #9 measurable (concrete #s, 0-edges, 20-yellow, 49-pending), #6 obs (health, BRC, job events, doctor alerts, plan counts), etc.

**FRESH "3" hygiene (pre this append, only safe cites):** 
run: `grep -rn --include="*.py" ... -E "^\s*def\s+.*(test_partial_continuation_workflow_25k|...)" ... || echo "0 def matches (FRESH LAST PASS for M5 doc append)"` → verbatim PASS. No sacred defs touched (only harness:3109 cite pattern in prior docs).

**Honest calib (long-term lens):** 35-45%+ visible M5 evidence snapshot (initial + this run on 1 major target; test_edges=0, pollution noted, stele not cross-indexed yet, no multi-week concurrent MA+daemon yet, no external 50k+ beyond RecipeLab). Target 75-85%+ post more runs + reports + full metrics over "been a while" periods. No overclaim. M5 exclusive literal multi-month on real 50k+.

**Next per prior + this:** 
- Poll more chisel (e.g. after any edit, record_result on tests, diff_impact).
- Stele: try rebuild_symbols or index on recipe-lab paths if possible; use find_references/search_text/impact on main Findings (M5 docs) + detect_changes.
- Wikifier: more runs (e.g. update-maps scoped on target, daemon start in bg for sustained, get_files_needing_attention via shell), target the 1 pending in RecipeLab (but per M5, do not "fix" target's wiki unless part of dogfood intent; observe).
- Trammel: if session uses target's db, available_steps + claim on one pending (e.g. the collab editor one) + record.
- Append more to this + p6 report; produce diary-style.
- Main: keep clean; any edit = record + mark-green + FRESH 3 + subagent_id.

See prior M5 sections + M4 handoff for full. All activity logged for 95%+ / 5-10yr gate evidence.

**subagent_id=m5-gamma-coord-2 100%** (this append, headers, future). 8-step DF (review state via tools/todos, choose safe MCP+shell exercises on allowed, collect verbatim, append with hygiene, no main py, boundary absolute). 9 GPs verbatim in decisions.

## Access Verification & Initial Dogfood Passes on New Targets (2026-06-03)

**subagent_id=m5-gamma-coord-verify** (M5 dogfood expansion; verified access to recipelab_alt, consistencyhub, cloned_sample_projects before/while going through; absolute monitored_paths configured for reliable external runs; full FS/CLI/MCP/wikifier lib access confirmed via dozens of tool calls; FRESH "3" hygiene PASS pre-append).

**Targets verified (all under /home/aron/Documents/coding_projects/):**
- **RecipeLab_alt**: Pre-existing wikifier setup (monitored=src [later absolute], file_health.json/md, pending, trammel.db, wikifier.sh symlink, .wikifier_staging, extensive MCP_Findings/* with wikifier reviews, wikifier-challenge/ stress tests, src/ with 200+ JS (models, services, api/routes, plugins, importers/exporters, internal mcp/wikifier-stress). CLAUDE.md: "dedicated test project for validating ... MCP servers: Chisel, Stele-context, and Trammel" + wikifier; "stress-test MCP capabilities that showed gaps during ConsistencyHub audits". Perfect M5 target.
- **ConsistencyHub**: Large complex project (React 19 frontend/src with 80+ components/pages, tests/ (hundreds of .test.js/jsx), api/, wiki-local/funcs, REMEDIATION/ with 8-agent swarm plans + master issues, trammel.db, .stele-context, package.json etc.). No pre monitored_paths (init created with defaults, then set to absolute frontend/src + tests + api). README: zero-knowledge document consistency platform for writers, with heavy remediation/governance history.
- **cloned_sample_projects**: Collection of massive real-world clones for scale dogfood (llama_index full with llama-index-core (487 py files), llama-index-integrations (thousands of files across readers/vector/etc), docs/ with 100s ipynb/md; also llvm-project, linux, rust, Babylon.js, airflow, dotnet, redox + huge Archive.zip). Inited, monitored set to absolute key llama subs. Tests multi-lang (py heavy, cpp, etc.).

**Verification methods executed (parallel tool calls, repeated re-checks):**
- FS: ls -la (roots + subs), list_dir (on coding_projects, each target root, llama_index sub — succeeded even for 10k+ file dirs, summarized), read_file (READMEs, CLAUDE.md, monitored_paths, etc.), cat, find.
- CLI: WIKIFIER_PROJECT_ROOT=... python -m wikifier (and cd + ./wikifier.sh post-init) for init, check-changes (no new changes + BRC 20 auto on alt), health --summary (matrices populated, some pollution from cross-runs but target's file_health updated), validate (✅ all have health entries; alt showed 50+ deliberate "MISSING WIKI ENTRY" for importers/exporters/stress/ models/services/routes/plugins — per design), update-maps (on alt: "Rebuilding library.md").
- Absolute monitored fix: Set to full /home/.../target/sub paths — eliminated "monitored path does not exist" warnings (confirmed in re-runs).
- MCP (wikifier tools with project_root=): get_project_status (text/json, returned data/0s/pending for all 3), get_files_needing_attention (status=all/yellow on alt+others: "No files currently need attention" — health stubs present), get_barrel_reports (on alt: rich output with 46 chains, 45 barrels, recent_reports for stale BRC on pollution importers + chain_ids/reasons like "stale via mtime snapshot or deleted barrel", detector="none").
- Lib: python -c "from wikifier import ...; check_changes(); health(format='json'/'summary')" (some import limits like get_barrel not top-level, but core works).
- Other: cd into targets for clean launcher runs; confirmed copied wikifier.sh, created file_health/monitored in targets.

**Dogfood signals observed:**
- RecipeLab_alt: Consistent [barrel] auto-marked 20 importers Yellow; BRC reports via MCP detail the chains (pollution from prior WTs + internal test re-exports); update-maps + validate exercised (many missing wikis as intentional test gaps for wikifier); MCP barrel full data.
- ConsistencyHub & cloned: Init + check succeeded, health/wikifier.sh marked green in their matrices; MCP status/files/ needing work (0 needing = stubs created); absolute monitored + cd runs clean (no path warnings); large scale access (llama subs listed/read, 1000s files).
- Common: Pollution in health output (external WT paths, main skills yellow) persists in target's matrices from prior runs — this is observable "stale detection / BRC / health durability" behavior under "been a while" + cross-project; good for M5 long-term obs testing. "No new changes" + prune/heal 0 on stable.
- All: Full access confirmed before/while "going through"; no permission/FS errors; can target via env, launcher, MCP project_root, absolute monitored.

**9 GPs / M5 notes:** #1 spectrum (RecipeLab_alt creative JS stress, ConsistencyHub complex frontend+tests+remediation, cloned massive multi-lang 5k-50k+ like llama/llvm); #8 allowed targets only (these prepared for dogfood); #2 zero-dep; #9 measurable (46 barrels, 20 BRC, validate lists, MCP returns, file counts via list_dir); hygiene (FRESH 3 PASS, record/mark for any main appends); boundary absolute (no main source edits here).

**Next:** Use these for sustained dogfood (check-cycles, MCP chisel/stele/trammel on them where set up e.g. alt has .chisel/.stele, consistency has trammel, cloned for scale); append more metrics; clean target matrices if needed by mark-green on pollution or prune; run update-maps scoped, full validate, barrel audits, etc. Update M5 doc with findings.

**subagent_id=m5-gamma-coord-verify 100%**. All via tool calls, no assumptions.
