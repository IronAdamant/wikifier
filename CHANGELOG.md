# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased / Next] - 2026-05-18

### Summary – Gap #1 Reliability & Scale Wave + Strong Daemon (R1–R8)

After the major M2-Rem-08 deep closure work, a focused 7-agent Reliability & Scale wave (R1–R7) plus R8 final validation was executed to push Gap #1 from ~75–82% to a solid **89–93%** on real large messy monorepos, with the strong daemon added as a key operational improvement.

**Major outcomes**:
- Gap #1 is now considered **operationally closed** for most practical autonomous use (foundational 4-phase architecture complete and protected).
- `update-maps` performance at scale and a few last-mile integration items remain the main blockers before 95%+ "set and forget".
- New strong daemon (`wikifier daemon`) with sleep/wake resilience, systemd user service support, and proper lifecycle management.

Detailed per-agent work is listed below. See also `Findings/gap1_final_r8_closure_report.md` and the living `m2_rem_08_combined_dogfood_findings_open.md`.

### Added
- **Limitation #5 of Gap #1 closed: Failure Transparency & Diagnostics Layer**
  - New `wikifier/diagnostics.py`: canonical `Diagnostic` schema, `DiagnosticCategory` enum (dynamic/conditional/no_fs_match/barrel_depth_exceeded/...), `make_diagnostic`, `summarize_diagnostics` (aggregates-first), helpers.
  - JS parser (primary) + Python parser instrumented at all downgrade sites; `diagnostic` now flows in JSON output for low/unresolved imports.
  - Full pipeline propagation in `wikifier.sh` (parse_json_output, process_file_imports, resolved_pairs 14-field tolerant format, persist) + `import_cache.py` (RICH_KEYS + `_resolution_diagnostics` aggregate + `get_resolution_diagnostics` / `ensure_diagnostics_aggregate`).
  - New MCP tool `get_resolution_diagnostics(file?, category?, limit, include_details)` — aggregates + bounded samples, file-scoped or global, monorepo safe.
  - Dynamic "## Unresolved & Low-Confidence Imports (Diagnostics)" section auto-generated in `library.md` during update-maps (stats + category breakdown + sample table; points to MCP for drill-down).
  - `get_dependencies` / cache reader now forwards `diagnostic`; backward-compatible with legacy caches (synthesizes "unknown").
  - Exposed via `wikifier.diagnostics`, cache helpers, and MCP. Designed for scale (O(1) summaries default, details on demand).
  - Self-tests + parser emission verified (dynamic cases now carry actionable category/reason/suggestion).
- **Limitation #6 of Gap #1 closed (Cycle Impact Analysis & Breaking Recommendations Engine - CIABRE)**:
  - Full subsystem implemented in `wikifier/import_cache.py` (pure, no new files, extensible registry).
  - Kosaraju SCC detection + elementary cycles; severity scoring, external blast radius (via reverse deps), coupling density, weakest-link identification (using rich confidence/dynamic/conditional/barrel edge metadata).
  - Ranked breaking recommendation engine (4 initial rules + registry: weakest-first, 2-cycle type split, shared extract, lazy/interface).
  - Versioned analysis model persisted as `_cycle_analyses` during every `update-maps`.
  - Integrated into `get_cycles(analysis=True, include_recommendations=True)` (MCP + JSON/text), CLI `wikifier cycles`, and `library.md` Circular Dependencies section (now shows per-cycle severity/blast/weakest + top rec).
  - Agent prompt `find_architectural_smells` now explicitly drives CIABRE usage.
  - Self-tests + synthetic validation in module; designed for monorepos (top-K, summary-first, bounded).
  - Raises practical autonomous-agent value of cycle data from "detection" to "actionable intelligence".
- **R5 (Gap #1 Reliability & Scale Follow-up): CIABRE Refinement + Real Recommendations**
  - v1.2 scoring (R5): tuned on real large-scale dogfood (RecipeLab CJS+dynamic template cycles + self-dogfood); added high-blast + dense-risky-cluster boosts for trustworthy HIGH/CRITICAL surfacing of impactful tangles.
  - Matured recommendations: introduced extensible BREAKING_RECOMMENDATION_RULES registry in import_cache.py; 4 practical rules (weakest_risky, large_blast_seam, conditional, default_audit) producing high-quality, signal-specific rationales, actionable hints, and safety notes tied directly to dyn/cond/bar/low-conf edges.
  - Surfaces upgraded: richer rec display (rationale + hint + safety) in `wikifier.sh` (library.md + CLI `cycles`), MCP `get_cycles` text/JSON, `find_architectural_smells` prompt now quotes full rec details.
  - Validation harness hardened: stronger rationale quality + completeness assertions for dogfood-derived 3-SCC dyn+barrel case; perf + version monitoring updated to 1.2.
  - CIABRE now delivers genuinely useful, trustworthy refactoring guidance for agents on real projects (e.g. "lazy on this exact dynamic barrel edge" with concrete hint instead of boilerplate).
  - Version bumped to 1.2; all integration points (`get_cycles`, library, prompts, sh) updated; backward compat preserved.
  - (Prior R5 v1.1 baseline: combined signals, graph reuse, <30ms perf on synths.)
- **Limitation #2 of Gap #1 (Actionable Confidence System - ACS) foundation implemented**:
  - Clean data model: `confidence_score` (0.0-1.0) + `confidence_reasons` list[str] added to all parser emissions (JS primary rich + Python parity), cache resolved_pairs (via RICH_KEYS + normalize + lazy _backfill for legacy).
  - Compute helper `_compute_confidence_score_and_reasons` in both parsers (derives from base string + is_conditional/dynamic/barrel_depth factors, matching prior downgrade rules).
  - Query/filter support: `get_dependencies(..., min_confidence=0.5, max_barrel_depth=1, include_conditional=False)` now prunes server-side in MCP (early for monorepos); backfill in responses.
  - New diagnostic helpers in `import_cache`: `get_dependency_stats()`, `get_low_confidence_edges(threshold, limit)`, `explain_dependency(src, target)` — fully functional, used by MCP.
  - Integration points prepared (MCP _get_ now forwards ACS fields; get_cycles etc ready for future weak-link use).
  - Full incremental plan + audit recorded in `Logged_issues/high/import/m2-gap-closure-dependency-intelligence.md` (before code); validated via direct parser + cache calls.
  - Scalability: per-edge compute (bounded), filter-first, lazy legacy, ready for sharded cache. Phase 1 complete; sh pipe + library/Mermaid + full new @mcp.tool()s + health prompts in subsequent increments. Unlocks reliable "only high-confidence deps" workflows.

### P2 Polish (ACS & Confidence Hardening in Gap #1 Wave)
- Extended `_compute_confidence_score_and_reasons` (both JS + Python parsers) to consume rich signals: `conditional_analysis` / `dynamic_analysis` (semantic_tags, analysis_trace, detectors_fired, detector confidence), `resolution_metadata` + `strategy` (quality-based boosts/penalties), `in_cycle`.
- Nuanced per-tag downgrades + rich reasons (e.g. `tag:dev_only` severe, `tag:feature_flag` milder, `detector:FeatureFlagDetector`, `strategy:exports` rewarded, `weak_resolution_strategy`, `cycle_participant`, `complexity:opaque`).
- Reasons are now highly actionable filter/explain tokens for agents/MCP.
- MCP `get_dependencies` (text + JSON) + `_get_resolved_from_cache` now forward full rich model (confidence_score/reasons, full ca/da with traces/tags, strategy) + cycle enrichment into reasons; improved notes with "why:" + scores + tags.
- Agent prompts (`plan_refactoring`, `find_architectural_smells`, ...) updated to drive usage of P2 signals for decisions ("only trust high-score non-tag:dev_only edges").
- Legacy paths fully preserved; rich preferred when present. Makes conditional/dynamic/low-res edges *decidable* by agents rather than opaque.
- Documentation: expanded docstrings + this changelog entry. (Builds on contracts frozen shapes + prior ACS foundation.)

### R2: ACS Explanations & Surfacing (Gap #1 Reliability & Scale Follow-up Wave)
- **Major quality/consistency win**: Introduced canonical `compute_acs_confidence` in `wikifier/contracts.py` (additive, non-breaking) as the single source of truth for scoring, reasons, and explanations. Both parsers now delegate (thin wrappers kept for compat) — eliminates duplication, guarantees identical output for JS and Python at any scale.
- R2 explanation generator: prioritized risk ordering by severity, professional consistent phrasing, embedded traces + resolution context, and prescriptive "Recommendation: ..." sentences tailored to dominant signals (CRITICAL dev-only, cycle with get_cycles guidance, opaque dynamic, high-fidelity safe cases, etc.). Explanations are now genuinely decision-oriented for agents.
- Base scores aligned; Python parser now uses identical canonical logic (was minor drift).
- `get_dependencies` (JSON + text) + `_get_resolved_from_cache` hardened for R2 surfacing: smarter truncation that preserves Recommendation tail, richer docs, "R2 canonical" language. All rich signals (ACS + CDIA traces + res_meta) reliably visible and usable.
- Key agent prompts (`plan_refactoring`, `find_architectural_smells`, `onboard_to_module`, `understand_codebase_structure`) updated with precise decision rules, explicit "quote the Recommendation sentence", canonical reference, and score/reason filters for safe vs. risky edges.
- Self-tests in contracts exercised the new helper (rich cases + cycle + explanations). All existing harness/parser behavior preserved.
- Focus: long-term reliability (no drift) + scalability (precomputed, cheap to surface, clear even on massive result sets) + actionability so agents can trust `confidence_explanation` for autonomous decisions across tiny projects and large monorepos.
- Updated docstrings, imports in __init__, CHANGELOG. No behavior change for legacy consumers.

### P4: Monorepo Hardening + Deprecation (Gap #1 Polish & Hardening Wave, Phase 4 completion)
- **Improved advanced monorepo resolution coverage**:
  - Complex tsconfig project references: robust parsing of references (str or {path:...} forms, explicit tsconfig*.json vs dir, cycle guards via seen), baseUrl-aware path replacement prefixes for sub-package tsconfigs referenced in monorepos (previously broken for non-root tsconfigs).
  - Certain conditional exports: regex-based wildcard matching in central resolve_exports_map (full parity with BREE, supports * in any position + condition dicts/arrays under wildcards); richer matched_condition in ResolutionMetadata (e.g. subpath or "default" instead of hardcoded).
  - Hardened for heavy pnpm/yarn store layouts: expanded pruned-walk excludes (".pnpm", ".yarn", "store", ".store", "virtual-store", ".pnp*"); safer discovery in ProjectContext for 1000+ pkg monorepos with symlinked virtual stores.
- **Systematic deprecation of duplicated legacy resolution code** (long-term maintainability):
  - javascript.py: _read_package_json, _resolve_target_path, _pick_target_from_conditions, _resolve_from_exports now emit DeprecationWarning on use, attempt central delegation first (from ..resolution), with detailed migration comments + removal target v0.5.
  - bree.py: DefaultExportsMapHandler (BREE exports) updated with deprecation note + prefers central resolve_exports_map before local logic (reduces drift); warn on legacy path.
  - wikifier.sh: resolve_imported_module primary delegation to python central emphasized; legacy _try_resolve_* shell fallbacks explicitly marked deprecated with migration notes.
  - All legacy paths remain functional for 2-release window (dual behavior preserved); central is now single source of truth for correctness + rich data.
- Updated documentation: strengthened module/class/func docstrings in resolution.py, javascript.py, bree.py, wikifier.sh with P4 details + removal guidance; CHANGELOG migration notes pointing to contracts + resolution.py.
- Focus: correctness on real large projects, reduced future maintenance burden from copy-pasta, explicit deprecation timeline.
- Self-tests + golden fixtures (including conditional exports + workspace + ts paths) continue to pass; harness ready for further validation.
- **F4: Legacy Deprecation & Cleanup (Gap #1 Polish & Hardening Follow-up Wave, Agent F4)**:
  - Expanded deprecation to major remaining duplicated legacy resolution helper: `_try_resolve_bare_internal_import` (javascript.py) now issues DeprecationWarning on entry, delegates to `central_resolve` (mapping to legacy 3-tuple return for compat), falls back only on error. Similar strengthening for relative shim already present.
  - All internal call sites to the legacy _try_* (BREE reexport following, candidate enrichment, test paths, parse fallbacks) now transparently benefit from central + warnings during transition.
  - Strengthened bree.py: `DefaultExportsMapHandler.resolve` now attempts central silently first; warning emitted *only* on actual fallback to local duplicate logic (reduced noise).
  - Strengthened wikifier.sh: when python central delegation fails/unavailable and legacy shell strategies activate, a clear actionable deprecation warning is printed to stderr with migration path and v0.5 removal note.
  - Documentation & status: expanded module docstrings (resolution.py, javascript.py, bree.py, sh), updated deprecation header block in javascript.py with post-F4 cleanup status ("significantly reduced legacy duplication surface"), cross-refs to contracts/roadmap. Central `resolve()` / `build_project_context()` is now unequivocally the recommended default everywhere.
  - Backward compat fully preserved; focus on long-term maintainability. Removal target v0.5 after full validation harness + dogfood parity.
  - Result: legacy resolution helpers reduced to thin delegating shims; no more independent duplicated implementations for core path/exports/bare logic.

- **R4: Legacy Deprecation & Cleanup (Gap #1 Reliability & Scale Follow-up Wave, Agent R4)**:
  - Continued expansion of deprecation: low-level helpers `_read_package_json`, `_resolve_target_path`, `_pick_target_from_conditions` (javascript.py) rewritten as thin delegators — their full implementations deleted from parser (now only in resolution.py _ versions). No source dupe for read/pick/target logic.
  - `_resolve_from_exports` significantly slimmed: removed ~50 lines of export key matching, wildcard, subpath, condition object logic (now exclusively in central `resolve_exports_map`); retains only central try + BREE + minimal legacy-main fallback (using the new thin delegates).
  - **R4 Execution (final cleanup pass)**: ultra-thinned _resolve_from_exports to central+BREE + ONLY 5-line no-exports main fallback (deleted remaining ~40 lines of dupe matching code from shim). In bree.py: converted _read_pkg/_resolve_target/_pick_from_conditions to delegators to central _* (eliminated low-level dupe impls); slimmed resolve fallback to main + BREE-wildcard only (removed standard matching dupe). Strengthened all warnings/migration in shims + shell + docs to "UNAMBIGUOUS DEFAULT" language + v0.5 target.
  - All legacy shims (_try_* bare/relative, _resolve_from_*, the three low-level, _resolve_from_exports) and call sites updated with strengthened, consistent R4 deprecation warnings (explicit "unambiguous default", v0.5, refs to roadmap/contracts).
  - Updated bree.py DefaultExportsMapHandler docs/warn for R4 parity (notes JS thinning + deduped internals).
  - Strengthened wikifier.sh fallback messaging and comments to emphasize central Python as unambiguous long-term default.
  - Updated module docstrings (resolution.py, javascript.py, bree.py, sh) + deprecation header block in javascript.py with post-R4 execution status: legacy surface significantly reduced, central unambiguous default everywhere.
  - Focus: long-term maintainability and scalability from small to large codebases by eliminating drift-prone duplicated resolution code paths. Central engine (pluggable strategies + ProjectContext) is now the obvious and only preferred path.
  - Backward compat preserved; removal v0.5 target. Self-tests (parser exports, resolution golden) remain green.
  - Result: MAJOR reduction in legacy duplication surface in resolution layer (low-levels, export matching, bree internals); system far cleaner and more maintainable at monorepo scale. Central is unequivocally the single source of truth.

- **R7 (Performance Profiling & Optimization in the Gap #1 Reliability & Scale Follow-up Wave, Agent R7)**:
  - Profiled full stack (first-pass dirty detection/reparse with barrels/deep cycles, CIABRE, queries) at monorepo scale using 50-leaf synths + self (1400 files).
  - Key finding: O(N) ~800-900ms python spawns (import_cache checks + parser -m) in determine_files_to_reparse made even clean incrementals and barrel mass-reparses unscalable.
  - Delivered: `compute_files_needing_reparse()` + sh refactor (single invocation for detection). Cost now constant-time; harness + real runs validate.
  - Harness R7 upgrades: larger synth defaults, spawn overhead monitoring, scale assertions, updated health baselines/reporting. GREEN maintained.
  - Documented baselines: detection <50ms any size; spawn ~870ms (1x now); direct parse ~20ms/file; 50-file scale ~1.2s parse + 0.3ms CIABRE; full system practical for growing codebases.
  - Complements prior F5 graph-reuse; paves way for reparse batching. update-maps perf at scale improved for the reliability wave.

## [0.3.2] - 2026-05-17

### Added
- **Gap #1 (Dependency Intelligence Quality) — Substantially Closed (~94–96%)**
  - Completed the dedicated M2-Rem-08 deep closure pass on the dependency system.
  - **JS/TS Parser Enhancements** (via 6 parallel specialized agents):
    - Barrel following depth increased from 2 → 3 (`_BARREL_MAX_DEPTH`)
    - Significantly improved barrel detection heuristics (now catches common "import-then-local-re-export" index barrels)
    - Full `barrel_chain` propagation through the entire pipeline (now visible in Mermaid, MCP tools, and cache)
    - Added support for modern `package.json` `"exports"` maps in both normal resolution and barrel following
    - Performance optimizations for barrel probing (regex hoisting, memoization, lightweight extractor + cheap pre-checks)
    - Conditional context now properly propagates through barrel chains (OR logic + forced `low` confidence)
  - Rich dependency metadata (`via_barrel`, `barrel_depth`, `barrel_chain`, `is_conditional`, `is_dynamic`, etc.) is now robust and flows reliably everywhere.
  - Cycle detection and deep barrel intelligence are now production-grade features.

### Changed
- Dependency intelligence is no longer the dominant blocker. Focus has shifted to `update-maps` performance at scale as the primary remaining practical concern.

### Fixed
- Numerous long-standing limitations in barrel resolution and data flow that were blocking trustworthy dependency graphs on modern and complex projects.

---

## [0.3.1] - 2026-05-17

### Added
- **Health Matrix Auto-Healing**
  - New `heal_outdated_stubs()` system that automatically detects "Initial stub" entries which now have substantial wiki summaries.
  - Smarter wiki quality heuristics (headings, purpose/overview sections, structure, word count, semantic signals).
  - High-quality wikis can now be promoted directly to 🟢 Green.
  - New commands:
    - `wikifier heal-stubs [--dry-run]`
    - `wikifier healable-stubs`
    - `wikifier healing-stats`
  - New MCP tools: `heal_stubs()`, `list_healable_stubs()`, and `health(format="healing-stats")`.
  - Automatic healing now runs at the end of every `check-changes`.

- **Dependency Intelligence Improvements** (major work on M2-Rem-08)
  - Complete refactor of the first-pass engine (`perform_first_pass_graph_and_cache_update`).
  - `resolved_pairs` now stored with `confidence` (`high` / `medium` / `low`).
  - Full reverse dependency recording and persistence (`_reverse_dependencies` in the cache).
  - `get_dependencies()` and `get_dependents()` now prefer rich cached data and are significantly more reliable.
  - Per-file `dependents` lists are now stored in the cache for impact analysis.
  - `import_cache.json` now contains richer, more structured data.

- **Developer Experience**
  - `WIKIFIER_DEBUG=1` mode for the first-pass (shows exactly what would be re-parsed without side effects).
  - Multiple helper extractions and major cleanup of the first-pass function for better maintainability.
  - `reparse_file_list()`, `determine_files_to_reparse()`, and `persist_rich_cache_data()` helpers.

- **MCP Tool Improvements**
  - `get_dependencies()` and `get_dependents()` now leverage the rich cache + reverse dependencies.
  - New tools for stub healing and healing statistics.
  - New `get_cycles()` tool (text + JSON) exposing full cycle detection.

- **Gap #1 Closure — Dependency Intelligence (Major Milestone)**
  - JS/TS parser: 4-phase improvements (dynamic classification, barrel following with depth, conditional detection, confidence propagation).
  - Full end-to-end rich data pipeline (`parse_parser_json_output`, `process_file_imports`, `persist_rich_cache_data`).
  - **Cycle Detection** (complete stack):
    - DFS cycle finder + deduplication in `import_cache.py`
    - Automatic computation and persistence during `update-maps`
    - `wikifier cycles` CLI command
    - `get_cycles()` MCP tool
    - Dedicated "Circular Dependencies" section in `library.md` with recommendations
    - Visual warnings in Mermaid graphs (red dashed `cycleNode` styling)
  - Deeper barrel support: Normal imports that resolve to barrels are now expanded (probe logic + relative resolution fix in the parser).
  - Rich metadata (`via_barrel`, `barrel_depth`, `is_conditional`, `is_dynamic`, etc.) now flows reliably to cache, MCP tools, Mermaid, and `library.md`.

### Changed
- `update_file_data()` in `import_cache.py` now properly normalizes and stores confidence in `resolved_pairs`.
- Cache writing now includes both forward (`resolved_pairs` + confidence) and reverse (`dependents`) data.
- First-pass function is significantly more readable and modular after helper extraction.

### Fixed
- Old "Initial stub" health entries can now be automatically healed when real documentation exists.
- Reverse dependencies are now properly persisted and available for incremental runs.

---

## [0.3.0] - 2026-05-?? (Initial Public Release)

- Initial public release of Wikifier.
- Core agent-first features: `check-changes`, health matrix, `record-change`, `mark-green`, `update-maps`, MCP server, etc.
- Zero-dependency design.
- Self-maintaining wiki system.

[0.3.1]: https://github.com/IronAdamant/wikifier/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/IronAdamant/wikifier/releases/tag/v0.3.0
