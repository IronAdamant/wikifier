# M2 Phase 86-90: Durability, Observability & Scale Hardening Checklist

**Phase**: 86-90 (Durability, Observability & Scale Hardening – Feature Building Phase)  
**Agent Allocation**: 8 agents  
**Primary Goal**: Harden the M2 core (Workstreams A–E) for long-term (years-scale) autonomous multi-agent operation and prove the full scalability spectrum — from tiny monorepos to massive 25k–50k+ creative monorepos (JS+Python mixes, barrels, dynamic/conditional imports, workspaces, symlinks) — with strictly bounded state, practical first-class observability, zero trust failures, and production-grade durability under sustained heavy load.

**Key Constraints** (non-negotiable):
- **No dogfooding of the Wikifier project itself** until M5. Use harness, RecipeLab, and user-designated *other* external projects only for all real-usage validation and stress. This is still M2–M4 feature building.
- "3" (original partials deep proof track exercising PartialResultV1 / continuation_token / 25k–50k creative streaming paths in the harness M2 suites) is **absolute last and untouched** — explicit LAST grep on `wikifier/gap1_validation_harness.py` before every content write that touches source/harness + final verification. Only historical references + designated subagent WT copies allowed (0 runtime pollution on main).
- Zero new dependencies (pure stdlib: jsonl journal, deque summaries, fnmatch, file_lock, etc.).
- Follow the full 9-step hygiene-first playbook on every batch (source gate first via --m2-health --deep, small micro-batches, external long-pole #1 on allowed targets, new reviewer each batch, main 100% clean with 0 critical markers + import GREEN, local-only worktrees until post full gate).
- Focus on long-term viability: explicit zero-dep + portable, dual-path (Py-primary default + thin shell), event-sourced journal + compaction, frozen/versioned contracts, full observability (ACS/CIABRE default), multi-agent safety, harness+dogfood-driven (M5 boundary respected).
- All work must be harvestable to `wave-evidence/` with rich local diaries in WTs vs exact long-term A-E 95%+ exits + 7-criteria + 8/9 guiding principles.
- Honest calibration preserved: 82–87% toward 95%+ / **0/7 strict 85%** (feature-building lens; full literal crit4/Gate3 multi-day high-trust autonomous on true 5k+ real usage + complete 0/7 is M5 scope).

---

## Phase Exit Criteria (86-90)

By the end of this phase, the following must be demonstrably true on allowed targets (harness + RecipeLab + user-designated external creative monorepos only):

- Strong durability characteristics under simulated years of autonomous multi-agent load: compaction (journal/pending/health caches) safe, reversible, observable; active state strictly bounded; historical queries remain useful and fast without megabytes of I/O.
- Richer first-class observability surfaces (executive/impact summaries, autonomous session aggregate traces, ACS/CIABRE provenance everywhere) are practical, default, and performant at massive creative scale (O(k) bounded, cross-linked to reverse/health/journal/barrels).
- Scalability proven across the full spectrum: O(changed) streaming/partials, O(k) summaries/health, memory-safe long sessions, query perf stable on 25k–50k+ creative generators + designated massive externals; no O(n) fallbacks in normal paths.
- Multi-agent safety under heavy sustained concurrent load (8+ agents, chaos edits/renames/intent via record_change + heal cycles, locking, provenance always correct, 0 corruption or trust failures).
- All 8/9 guiding principles visibly upheld in code, tests, and evidence artifacts.
- Main remains 100% clean, "3" untouched, and all validation during the phase stayed strictly on allowed targets only (harness + RecipeLab + designated external projects). No `--m2-health --deep` or equivalent heavy self-validation was performed on the Wikifier source tree itself.
- Rich, reproducible evidence catalog in `wave-evidence/` (completion harvests with metrics vs exact long-term exits, 7-criteria, 8/9 principles, honest calibration, subagent_id in 100% commits/diaries/headers).

---

## Workstream B2 – Health Durability Hardening

**Current State (Post 80-85)**:  
Zero flakiness, reliable stale detection (content-hash + last-semantic-edit), 100% heal success, sharded + summary views, full provenance (freshness + ACS/CIABRE/barrel/reverse), and multi-agent safety demonstrated under concurrent load on 25k–50k creative gens + RecipeLab 269 proxy + designated 5k+ external creative targets (80-B1, 82, 72, 65, harness run_m2_durability_longrun_stress + compaction hooks). Health matrix stable "over time"; get_stale_wikis + heal_with_policy + PendingItemV1 hardened; timestamp parsing dual-signal robust. See wave-evidence/phase6-80-85-*-completion.txt and phase6-82-*. Strong bounded + observable behavior.

**Remaining Items for Phase 86-90**:

1. **Advanced years-load compaction policies for health matrix + stale wiki signals**  
   - Time-based + significance (ACS/CIABRE blast radius + high-impact) + reversible compaction that keeps active state bounded while preserving detection accuracy.  
   - Simulate 1000+ "day"/"year" churn cycles with heavy multi-agent edits/intent on 25k–50k creative + designated massive externals.  
   - Metrics: matrix size stability (no unbounded growth), stale flip accuracy 100% (0 false pos/neg post-compaction), query perf on sharded views.  
   - Validation: Long-running harness simulations (extend run_m2_compaction_longrun_years_sim) + RecipeLab + designated external creative monorepos.

2. **Sustained heavy multi-agent safety + long-run durability (beyond initial 80-85)**  
   - 8+ concurrent agents under continuous chaos (edits/renames/deletes + record_change + heal + health queries) for simulated weeks/months of wallclock-equivalent load.  
   - Prove locking, PendingItemV1 atomicity, provenance survival, zero drift in health state or false heals.  
   - Validation: Extended harness durability_longrun + crossws suites on allowed targets.

3. **Extreme-scale sharded + summary-only health views (50k+ creative)**  
   - Directory-scoped + summary-only must be the fast/default path for massive repos; full matrix generation rare/background only.  
   - O(k) memory/time even on 50k+ files with deep barrels/dynamic patterns.  
   - Validation: 25k–50k+ synthetic creative generators + any user-designated massive external monorepos.

**Suggested Agent Split**: 2 agents (B2 lead for years compaction + one for sustained multi-agent longrun + scale views).

---

## Workstream C2 – Journal / Compaction / Intent Scale Hardening

**Current State (Post 80-85)**:  
Event-sourced journal (jsonl primary + MD dual) + smart compaction (time/significance/ACS-driven, manifest, archive, dry-run default) + bounded pending + first-class historical intent query surfaces (`get_intent_history`, `get_high_impact_changes`, `get_session_summary`) proven production-grade on 5k+ creative proxy under Phase 1 load + harness 1200-event heavy sim (80-C1, 83, 73, 65). Journal functions as source of truth for intent, health transitions, transparency. Queries return useful provenance-bounded results post heavy activity without megabytes. Reversible, observable, safe. See wave-evidence/phase6-80-85-c1-... and phase6-83-*. Bounded + query_useful=yes.

**Remaining Items for Phase 86-90**:

1. **Years-scale reversible compaction policies at extreme event volume**  
   - Full multi-"year" simulation (thousands of events, mixed agent sessions, high barrel/creative churn) exercising time + significance + ACS/CIABRE blast-radius policies.  
   - Active state (recent full chains + summarized older periods) must stay strictly bounded; prune must be safe/reversible with manifest + dry-run always available.  
   - Validation: Extended harness run_m2_compaction_longrun_years_sim + real usage on designated 5k+–massive creative targets (allowed only).

2. **Historical query usefulness + provenance preservation after extreme compaction**  
   - `get_intent_history(file, since=...)`, high-impact, session summaries must remain fast, relevant, and rich (full ACS/CIABRE/reverse/provenance links) even after aggressive years-scale pruning.  
   - No loss of actionable history for autonomous agents.  
   - Validation: Post-compaction query benchmarks on harness + RecipeLab + designated externals.

3. **pending_updates as robust, auto-pruned, high-fidelity work queue under sustained chaos**  
   - Provenance, priority, automatic safe pruning while preserving historical value for queries.  
   - Survives heavy concurrent record_change + heal + streaming partials without corruption or unbounded growth.  
   - Validation: Sustained concurrent load + years sim on allowed targets.

**Suggested Agent Split**: 2 agents (C2 lead for years compaction policies + one for query durability + pending robustness).

---

## Workstream D2 – ACS/CIABRE + Transparency Hardening at Scale

**Current State (Post 80-85)**:  
Full first-class low-conf/unresolved/failure transparency ("as easy as success"), parser parity on *all* paths (success/low-conf/fail/barrels/cycles/JS+Py/creative), and ACS/CIABRE explain-all everywhere (with diagnostic + suggestion_for_agent + provenance) exercised on real creative paths and 25k–50k gens (80-D1, 84, 74, 49/57/64). Reverse, health, journal, summaries, barrel reports all cross-link rich context. Low-conf/failure paths now trustworthy. See wave-evidence/phase6-80-85-d1-... and phase6-84-*. 

**Remaining Items for Phase 86-90**:

1. **Autonomous session aggregate observability + richer long-run A3 consumption**  
   - Build directly on 81 last-mile prototypes: first-class session traces, aggregate high-impact views, richer executive/impact summary consumption as normal for long autonomous runs.  
   - O(k) bounded, cross-linked to ACS/CIABRE/reverse/journal even after days/weeks of simulated activity on massive creative.  
   - Validation: Long-running harness + designated 5k+–50k+ creative targets.

2. **Explain-all + suggestion quality at 50k+ creative + heavy barrel/dynamic load**  
   - Every resolution limitation, cycle, barrel, creative import pattern must surface high-quality, context-aware suggestions_for_agent.  
   - Integration with richer A3 summaries (A3) and health impact views.  
   - Validation: Heavy 25k–50k creative generators (barrels + dynamic/cond + mixed JS+Py) + designated massive externals.

3. **Provenance always present + cross-surface consistency under years-load**  
   - ACS/CIABRE, reverse fan-in, barrel 300 v1 chains, health freshness, journal intent must be present and consistent on *every* surface (even post-compaction, partials, heal, extreme scale).  
   - Zero "explainability debt" at massive scale.  
   - Validation: Full A/B/C/D integration stress on allowed targets.

**Suggested Agent Split**: 1–2 agents (D2 lead with cross-workstream collaboration on session obs + scale transparency).

---

## Workstream X3/X4 – Harness Durability & Scale Stress (Cross-Cutting)

**Current State (Post 80-85)**:  
Four new M2 stress suites added and exercised (run_m2_streaming_partials_creative_stress on 25k–50k+ creative with format=summary/partials/budgets/resume sim; run_m2_durability_longrun_stress; run_m2_compaction_longrun_years_sim with 1200-event heavy append + policies; run_m2_crossws_integration_suite with A→C→B→D orchestration). --m2-health --deep gate (lite + deep) fully integrated, 0 flakiness on 4800+ files / 2400+ events, R5 CIABRE reuse 0.037–0.7ms, 100% barrel, O(k) bounded, ACS/CIABRE provenance, full A/B/C/D cross-integration, main 54/RecipeLab 1637/269 targets. See 80-X1/X2 harvests + wave-evidence/phase6-80-85-x*-completion.txt and phase6-65/71-76 prior. Live deep gate running at end of 80-85.

**Remaining Items for Phase 86-90**:

1. **Extended long-running (simulated years) durability stress with full A/B/C/D + resume/partial safety**  
   - Multi-"year" churn loops exercising streaming partials/resume, health heal/compaction, journal historical queries, transparency, reverse survival, thin-shell parity under continuous load.  
   - Resume tokens, continuation, safe_to_act, and partial consumption must remain trustworthy across simulated months/years.  
   - Validation: New/extended harness longrun suites + allowed massive creative targets.

2. **50k+ massive creative generator + memory/perf regression gates + sustained 8+ agent concurrency**  
   - Push generators to true 50k+ scale (deep barrels, heavy dynamic/cond/JS+Py mixes, workspaces). Add strict memory caps + timing regression assertions (O(changed)/O(k) must hold).  
   - Sustained 8+ concurrent simulated agents + daemon/locking chaos for hours of wallclock.  
   - Validation: Harness only (plus RecipeLab/designated if available).

3. **Durability regression harness (replay + assert 0 drift)**  
   - Replay prior 80-85 chaos/intent/compaction/streaming sessions as regression suite; assert bounded state, ACS/CIABRE presence, query usefulness, zero trust failures, provenance consistency.  
   - Integrated into --m2-health --deep as first-class long-term gate.  
   - Validation: Harness self-test on 25k–50k creative.

**Suggested Agent Split**: 2 agents (X3 harness longrun durability + X4 50k+ scale + regression gates).

---

## Workstream A3 / E2 – Richer Summaries & Thin Ergonomics Durability at Massive Scale (Support)

**Current State (Post 80-85)**:  
Richer executive/impact/dependency summaries (compute_*_summary with ACS/reverse/CIABRE cross-links, deque tails, format="summary" default) + full thin-shell parity (both wikifier.sh + scripts/wikifier.sh delegate cleanly for --stream/--partial/--summary etc.) + v0.4 protocol alignment + library ergonomics proven on 5k+ creative proxy + 25k–50k gens (80-A1/A2, 80-E1, 85, 75, 58). Reverse auto-maintained in streaming/partials. O(k) practical. See A1/A2/E1 harvests.

**Remaining Items for Phase 86-90** (supporting B2/C2/D2/X):

1. **Richer summaries + autonomous session obs durability at 25k–50k+ scale**  
   - Executive/impact views + session aggregate traces must remain the recommended path, O(k) bounded, and high-signal after years-scale load/compaction on massive creative.  
   - Cross-link to all D2 provenance surfaces.  
   - Validation: Longrun harness + designated massive creative targets.

2. **Thin ergonomics + protocol polish for long autonomous sessions**  
   - Memory-safe O(1) UX for streaming/partials/summaries/health/journal over very long sessions (large outputs, many partials).  
   - v0.4 surfaces (record_change mandatory post-edit workflow, check-first, Red/Yellow priority) rock-solid at scale.  
   - Validation: Harness 25k–50k + RecipeLab/designated.

**Suggested Agent Split**: 1 agent (A3/E2 cross-cutting support for summaries + thin durability at scale).

---

## Cross-Cutting Items (Required for Phase Exit)

- **Harness & Tooling**: Extend the M2 stress suites (and any future allowed-target gate mechanisms) with years-scale longrun, 50k+ massive creative, sustained concurrency, durability regression, and full A/B/C/D orchestration. All such extensions and testing remain strictly on allowed targets (harness + RecipeLab + designated externals). No heavy self-validation or --m2-health --deep is performed on the Wikifier source tree itself during M2–M4.
- **Documentation & Ergonomics**: Update `library.md`, `skills/run.md`, contracts, README, and any protocol examples to reflect hardened durability/obs defaults and "summary as normal for massive creative" guidance (M5 boundary explicit).
- **Evidence & Calibration**: All 8 agents produce rich, harvestable artifacts (local WT diaries + wave-evidence/phase6-86-90-*-completion.txt) with metrics vs long-term A-E exits, 7-criteria, 8/9 principles, honest 82–87%/0/7, subagent_id everywhere, "'3' LAST grep" hygiene notes.
- **Hygiene**: Main 100% clean (0 critical markers, import GREEN). "3" untouched (LAST grep documented before every write). Full 9-step on every batch. Local-only WTs until post-gate. Dual independent reviewers recommended for 86/87-style.
- **M5 Boundary**: Every artifact, prompt, diary, and commit must explicitly state: validation restricted to harness + RecipeLab + user-designated other externals; Wikifier source dogfood deferred to M5.

---

## Suggested 8-Agent Allocation for Phase 86-90

- **86-B2** (lead) + support: Health years-load compaction + sustained multi-agent longrun durability.
- **86-C2** (lead) + support: Journal/compaction scale policies + historical query + pending robustness under extreme load.
- **86-D2** (lead) + support: Autonomous session obs + ACS/CIABRE/transparency hardening at 50k+ scale.
- **86-X3**: Harness long-running (years) durability stress + full A/B/C/D integration + resume/partial safety.
- **86-X4**: 50k+ massive creative scale gates + memory/perf regression + sustained concurrency + durability regression suite.
- **86-A3/E2**: Richer summaries + thin ergonomics durability at massive creative scale (cross-cutting support).
- **86-REV1** (or distributed): Independent reviewer batch (new pair per micro-batch, 9-step gate enforcement).

All agents must:
- Use subagent_id=86-B2 etc. in 100% commits, diaries, headers, harvests.
- Produce rich local WT diary + exact evidence vs long-term exits + 7-criteria + 8/9 principles.
- Perform explicit LAST grep for "3" (partials continuation 25k track) before every write touching harness/source.
- Harvest to `wave-evidence/phase6-86-90-*-completion.txt` (or equivalent naming).
- Keep main clean; only low-risk docs citations on main until full gated review.

**This checklist is the detailed execution guide for Phase 86-90 of the `m2-phased-to-95-agent-plan.md`.**

**Honest Calibration (as of start of prep)**: 82–87% toward 95%+ / 0/7 strict 85% preserved. Phase 80-85 delivered strong core feature completion + 25k–50k+ evidence (4800 files/2400 events, 0 flakiness, full cross-integration). 86-90 focuses the durability/obs/scale hardening needed for the remaining foundation before 91-95 exit closure. External long-pole (allowed designated targets) remains highest priority per plan. "3" untouched. M5 dogfood boundary explicit and respected.

Ready for `Findings/phase-86-90-agent-prompts.md` (8 self-contained briefs) + plan/tracker updates + execution.

---

**Sacred "3" Hygiene Note (PREP-86-01)**: Explicit LAST grep performed on `wikifier/gap1_validation_harness.py` (2026-05-28 context, multiple invocations during 86-01 review + immediately pre-checklist creation): historical name "test_partial_continuation_workflow_25k" has no matches; current equivalents (M2 streaming/partials/continuation exercised via run_m2_scale_harness + 25k–50k creative gens, PartialResultV1/partial_ready/continuation_token paths, fidelity notes) confirmed untouched in main (only additive comments referencing prior agents + "'3' untouched" markers). This grep serves as the pre-write hygiene step. Will be repeated in 86-07 final verify + documented in all 86-90 artifacts and agent WT diaries. Only historical + designated subagent-3 WT copies permitted.

**Note on Gates During Prep**: Any prior `--m2-health --deep` observations from the 80-85 period are historical only. Going forward in 86-90 and the remainder of M2–M4, no heavy self-validation or --m2-health --deep is performed on the Wikifier source tree. All gate activity stays strictly on allowed targets (harness + RecipeLab + designated externals).

**References**:
- `Findings/m2-phased-to-95-agent-plan.md` (authoritative 80-85 → 86-90 → 91-95 structure + M5 boundary)
- `Findings/m2-80-85-feature-completion-checklist.md` (exact mirror template + post-execution current state)
- `Findings/phase-80-85-agent-prompts.md` (prompt structure to mirror)
- `Findings/m2-full-closure-longterm-scalable-plan.md` (8/9 principles + detailed per-WS A-E 95%+ exits)
- `Findings/wave-evidence/` (80-85 completion harvests + prior durability/obs prototypes from 81/71-76)
- `Findings/Milestones-Overview.md` + `m2_rem_08_and_v0.4_progress_tracker.md` (current M2-in-progress status)
- Harness: `wikifier/gap1_validation_harness.py` (M2 stress suites + --m2-health --deep)

**subagent_id=PREP-86-01** (prep phase; all artifacts carry this or per-agent 86- ids). "3" untouched. Main clean. M5 boundary respected. Long-term zero-dep + scalability first.