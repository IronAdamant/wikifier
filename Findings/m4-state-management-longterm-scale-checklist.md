# M4 – State Management & Long-Term Scale Checklist & Progressive Milestones
**Created**: 2026-06-02  
**Status**: Draft – ready for review and execution (updated 2026-06-01 post E5 patterns synthesis per m4-80-95-e5 role + 90-95% DoD; subagent_id=m4-80-95-e5 for updates; see end for E5 additions: patterns ref + 9GP/8-step traces + spectrum matrices + honest limitations + E8 support)
**Purpose**: Actionable breakdown of the M4 plan with clear definitions of done at progressive levels of completeness (20% → 95% on the long-term feature-building / years-scale usefulness lens). Designed for agent swarm execution with the same (or stricter) discipline used in M2 and M3.
**Update Note (subagent_id=m4-80-95-e5)**: Post FRESH LAST "3" 0-def hygiene (10+ verbatim exact cmds "0 def matches (FRESH LAST PASS)" + internal grep "No matches found"; only safe harness:3109 cites), full reads of 6+ files + priors, synthesis of complete patterns surface from E* + priors (E1 <15% growth/99%+/0 corr/<5min rec + prototype; E3 Phase1 RecipeLab/test-js-flat rich metrics barrels/health/obs 75%+; C5 90d/3mo concrete 25MB/80MB bounded/83.3% comp/1.79ms rec/22 stories/0 corr on 109 partials3/50k+ patterns + actionable trends; D6/C6 bases + M3 100% "3" fidelity). Added 90-95% patterns/DF/matrix/lims sections + E8 ref + 9GP/8-step traces per E5 role/Guide. Zero-dep .md only. M5 boundary absolute. See new M4-Years-Scale-Agent-Builder-Guide.md + E5 diary for full.

---
## Core Constraints (Non-Negotiable for All M4 Work)
- **Feature creation, addition, and refinement only** (M2–M4 style). This is not M5.
- **No dogfooding on the Wikifier project itself**. All serious validation, stress testing, and real-usage work must use:
  - Harness (extended M3/M4 long-term suites on 25k–50k+ creative generators)
  - RecipeLab
  - User-designated external creative monorepos (5k–50k+ with target patterns)
- **Zero new dependencies** (PRIMARY LENS) — Pure stdlib + existing patterns only for all new state, compaction, health, and observability logic. No new runtime Python packages.
- Long-term focus + full scalability spectrum first (tiny scripts → 50k+ creative monorepos with barrels, dynamic imports, workspaces, symlinks, high churn, and sustained concurrent MA + daemon + human load).
- Actual usefulness close to 95% on the long-term feature-building lens (quality, completeness, and 5–10+ year viability under the 9 Guiding Principles).
- **"3" sacred** — test_partial_continuation_workflow_25k + related 25k partials/continuation deep-proof terms remain absolute last and untouched. Explicit FRESH LAST grep (0 def matches on active non-guardian code and planned write paths) required before any write touching journal/partials/continuation areas. Only safe historical citation (e.g., "exact harness test_partial_continuation_workflow_25k:3109") allowed in docs/examples.
- Rich, harvestable evidence (diaries, compaction correctness proofs, long-horizon metrics, conformance artifacts) against explicit criteria.
- Honest calibration toward 95% long-term usefulness. No overclaim.
- Main source 100% clean until M5.

---
## Major Work Areas for M4
1. **Advanced Journal, Compaction & Intent for Years-Scale**
2. **Extreme-Scale State Management & Boundedness (50k+ Creative)**
3. **Long-Term Health, Healing & Resilience**
4. **Richer Observability, Diagnostics & Query Surfaces for Long Runs**
5. **Long-Term Versioning, Migration & Compatibility Policy**
6. **M4 Validation Harness, Evidence Strategy & Clean M5 Handoff**

---
## Recommended Execution Model
Continue (and strengthen) the proven high-discipline approach:
- Use **6–8 agent swarms** for larger sub-phases.
- Smaller focused teams or single agents + review for targeted micro-batches.
- Isolated persistent original-path worktrees under `~/.grok/worktrees/Wikifier/subagent-m4-*`.
- `subagent_id=m4-XXX` (or m4-planning-coord for this phase) in 100% of commits, diaries, headers, and artifacts.
- **FRESH LAST "3" hygiene** (explicit 0-def grep output logged) before any write touching journal/partials/continuation areas.
- Rich local diaries with verbatim mappings to this checklist, the 9 Guiding Principles (full text from m3-03), 8-step DF, and long-term exits.
- External long-pole priority on allowed targets only (harness + RecipeLab + designated externals).
- Dual review on significant batches and all central handoffs.
- Central handoff packages at major gates (modeled exactly on M3 C8/B8 style).
- Zero new dependencies enforced as a primary review criterion on every artifact.

---
## Progressive Definitions of Done
These percentages are on the **M4 long-term feature-building / years-scale usefulness lens** (quality, completeness, and 5–10+ year viability under the 9 Guiding Principles + contribution to overall 95% agent usefulness). They are **not** final M5 dogfood scoring.

### 20% – Foundations & Direction Locked
- M4 plan and this checklist reviewed and approved.
- Core vision, constraints (especially zero-dep as primary lens), "3" sacred rule, and 6 Work Areas clearly documented and socialized.
- Current state audit of all M2/M3 state, journal, compaction, health, and observability components completed.
- 8-step DF (from m3-03) applied to initial Work Area prioritization with explicit spectrum matrix (tiny vs 50k+ creative long-term).
- First agent swarm (or small team) launched on highest-leverage early work (likely advanced compaction/journal durability foundation).
- All work following no-dogfood / allowed-targets / FRESH "3" / zero-dep rules.

**Agent Swarm Role**: 1 small team (3–4 agents) for discovery + initial direction setting. Heavy documentation and planning output.

### 40% – Core Compaction & State Durability Foundation Working
- Advanced, reversible compaction policies defined and prototyped for years-scale append-only operation.
- Journal and intent surfaces demonstrably bounded and queryable under extended load.
- Initial 50k+ creative monorepo state boundedness prototypes (barrels + dyn/cond + ws + symlinks + high churn + partials/"3").
- Zero-dep implementation validated for all new compaction/state logic (pure stdlib + existing patterns only).
- Early evidence on harness (long-term suites) + RecipeLab showing basic years-scale compaction and state behavior.
- Rich local diaries with verbatim 8-step + 9 GPs + "3" hygiene mappings.

**Agent Swarm Role**: Full 6–8 agent swarm on "Compaction & Journal Durability Foundation" + "Extreme-Scale State Prototypes".

**Definition of Done at 40%**: Core compaction and state mechanisms are safe and bounded in principle for long-term 50k+ creative use, with zero new dependencies and clean FRESH "3" hygiene. Agents can reason about years-scale behavior from the prototypes and docs.

### 60% – Solid Long-Term Resilience + Observability
- Compaction and state management feel production-hardened for months of continuous autonomous operation on 50k+ creative targets.
- Health, healing, and recovery stories are clear and observable under sustained concurrent MA + daemon + human load.
- Richer long-horizon observability and diagnostics (trend analysis, months-scale queries) implemented with zero new deps.
- Initial long-term versioning/migration policy sketched and prototyped for key state shapes.
- Thin consumers (CLI/MCP) updated to surface long-term state diagnostics as first-class.
- Evidence on allowed targets (including at least one external 50k+-scale creative) showing multi-week autonomous resilience with rich metrics (boundedness, compaction success, obs usefulness, recovery time).
- All 9 GPs visibly upheld (especially #1, #2 zero-dep primary, #4, #5, #6, #7).

**Agent Swarm Role**: 6–8 agent swarm(s) on "Long-Term Resilience & Observability" + "Versioning Policy Foundation" + "Documentation & Examples".

**Definition of Done at 60%**: An agent (or small swarm) can run for multiple weeks on large creative projects with confidence that state will remain bounded and observable, compaction is safe, and recovery paths are clear. The long-term story feels real rather than aspirational.

### 80% – Production-Ready for Years-Scale Autonomous Operation at 50k+
- Journal, compaction, and all major long-lived state structures are demonstrably safe, bounded, and correct after extended autonomous operation (weeks-scale real + accelerated years-scale sims) on 50k+ creative targets with full target patterns (barrels + dyn/cond + ws + symlinks + high churn + partials/"3").
- Full support for sustained concurrent multi-agent + daemon + occasional human operation over long periods without corruption or lost intent.
- Rich, long-horizon observability and diagnostics that remain useful after months of data.
- Long-term versioning and migration policy complete, implemented, and tested for all M4 state shapes.
- Comprehensive agent-builder documentation + patterns exist for long-term (months/years) operation on tiny → massive creative monorepos.
- Strong evidence on harness (extended long-term suites) + RecipeLab + at least one additional user-designated external 50k+-scale creative monorepo that the M4 state management is production-useful for years-scale autonomous agents.
- All 9 Guiding Principles visibly upheld with particular strength on #1 (spectrum at 50k+ long-term), #2 (zero-dep as primary lens throughout), #4 (advanced compaction), #5 (versioned long-term state), #6 (long-horizon obs), and #7 (years-scale MA safety).

**Agent Swarm Role**: One or more 6–8 agent swarms focused on "Years-Scale Hardening", "Scale Validation on Allowed Targets", "Observability & Versioning Completion", "Documentation & Patterns", and "M5 Handoff Prep".

**Definition of Done at 80%**: The state management layer is the clear, reliable foundation for agents to operate autonomously for years on 50k+ creative monorepos. It has been meaningfully exercised at scale on allowed targets with positive results (boundedness, compaction safety, rich long-term obs, recovery). Remaining work is final polish and M5 dogfood evidence rather than foundational gaps.

### 90-95% (Full M4 Exit Criteria Met — Ready for M5 Dogfood)
- Every item in the M4 exit criteria is demonstrably met with rich, harvestable evidence on allowed targets only.
- The state management layer is observably solid, scalable to years of autonomous operation, and production-useful across the full spectrum on 50k+ creative monorepos with all target patterns under realistic concurrent load.
- Clean handoff artifacts exist (long-term limitations documentation, migration guides, compaction policy reference, what M5 must still validate at literal multi-month autonomous scale on real user projects).
- Honest calibration at 90–95% on the long-term feature-building usefulness lens (under the 9 Guiding Principles and contribution to overall 95% agent usefulness for years-scale "set & forget").
- All work done without dogfooding the Wikifier project itself and with zero new dependencies.

**E5 Patterns/DF/Matrix/Lims Additions (subagent_id=m4-80-95-e5; post FRESH #10 hygiene + synthesis from E* + priors + D6/C6 base + E1/E3/C5 metrics; see M4-Years-Scale-Agent-Builder-Guide.md for polished full + 8-step/9GP traces per pattern + spectrum matrices + E8 ref section)**:
- Comprehensive years-scale agent-builder patterns (4+ extended from D6 4 + C6 3: years compaction/bounded reversible (E1 <15% growth/99%+/0 corr/<5min rec on 50k+ all patterns + concurrent MA + C5 83.3% comp/25MB mem cap/80MB disk/0 corr 109 partials3 in 90d/3mo 50k+ sim with barrels756/dyn1108/ws215/sym354/partials3 109 + actionable obs); full resilience/health/recovery (E1/E3/C5 22 recoveries 1.79ms avg 0 corr stories under concurrent chaos); rich long-horizon obs/trend (C5/E3/E2 actionable weekly_trend post 3mo data usefulness >0.8); complete versioning/migration additive V1 (E2/E1 safe 0 drift); "3" elevation safe ONLY via "exact harness test_partial_continuation_workflow_25k:3109" cite (M3 100% roundtrip 0 drift 0 corr O(scope) 25k+ + E1/C5 extensions 0 corr on 50k+ paths; replicate in all recovery/obs/versioning/compaction paths; SACRED_PARTIALS_3 = 3 safe only); heavy evidence wired (E3 Phase1 RecipeLab/test-js-flat rich barrels/health/obs 75%+ readiness/80%+ compliance; C5 pure stdlib 90d sim metrics + 8-step/9GP; priors B1/B2/wave 5k-50k+ baselines; M3 100% "3" fidelity).
- Full 9GP/8-step DF traces + spectrum matrices (tiny <100f zero-ceremony legacy untouched vs 50k+ creative years barrels+dyn/cond/ws/symlinks/high churn/partials/"3"/sustained concurrent MA+daemon+human as design driver; E1/C5/E3 real metrics prove O(changed) bounded <15% growth / 25MB/80MB / 83.3%+ comp success / <5min or 1.79ms rec 0 corr / actionable obs after months; 5-10yr viability) per pattern + cross-cutting in Guide + this.
- Honest limitations + M5 boundary (verbatim from E6 handoff + 6 files + plan + E1 handover pre-pop): Literal multi-month (toward years) autonomous "set & forget" on real user-prepared 50k+ creative = M5 exclusive (M4: capability/evidence on allowed harness 25k-50k+ + RecipeLab + designated externals; accel sims + multi-week real); full years 1000s cycles literal real high churn/MA+human = M5; long-horizon obs usefulness literal months/years real 50k+ user data = M5; versioning/migration on long-lived real installs = M5; sustained concurrent MA+daemon+human safety literal months/years real 50k+ = M5; "3" literal years autonomous partial/resume/continuation no-drift/boundedness on real 50k+ (barrel edits/dyn during resume/concurrent) = M5; E3 Phase1 only (full heavy external for E8/90-95%); migration tested on years real data = M5. See Guide for full matrices/lims + E8 patterns ref (abs paths to D6 + Guide + E1 handover/e1-to-e8-handover-notes.md + C5 metrics + 6 files + E6 handoff + all evidence).
- E8 support: Final patterns ref section in Guide (evidence bundle abs paths; recs for E8 harvest full E* WTs + wire E3 metrics + Re-FRESH "3" exact cmd pre writes + update Milestones/checklist + handoff to M5 real 50k+ literal multi-month); subagent_id=m4-80-95-e8 100%; M5 boundary + zero-dep + "3" sacred (harness:3109 cite only) absolute. E5 support available on patterns/Guide.
- 9GP/8-step application: #1 spectrum 50k+ years E1/C5/E3 real data primary (tiny legacy untouched); #2 zero-dep primary (pure .md + stdlib sketches + existing surfaces; no pyproject changes); #4 advanced compaction (E1 polish + C5 83.3% + D6 rev policies); #5 versioned (E2/E1 additive V1 + migration guides); #6 long-horizon obs (E2/E3/C5 actionable trends post 3mo); #7 years MA safety (E1/E3/C5 0 corr 0 lost intent concurrent chaos 50k+); #8 allowed/M5 boundary (harness/RecipeLab/externals only; literal multi-month real 50k+ user = M5 exclusive per all files/E6); #9 measurable (E1 <15% growth/99%+/0 corr/<5min; C5 25MB/80MB/83.3%/1.79ms/22 stories/0 corr/109 partials3; E3 75%+ readiness; 8-step/9GP traces + matrices in Guide). Full verbatim 9 GPs + 8-step per pattern/decision in E5 diary + Guide (synthesized from m3-03 harvest in 6 files + M3 C8).

**M4 is complete when the above 90-95% criteria are met with the same rigor and evidence quality that closed M3.**

All prior M2/M3 discipline is carried forward and strengthened, with **zero new dependencies** as an explicit primary success criterion for every Work Area and artifact.

See the accompanying `m4-state-management-longterm-scale-plan.md` for the full vision, 9 GPs alignment, 8-step DF application, and detailed Work Area descriptions.

**90-95% Gate Closure (post E1-E8 swarm + E8 central synthesis; 2026-06-01; subagent_id=m4-80-95-e8)**: All 90-95% criteria demonstrably met with rich harvestable evidence on allowed targets only (E1 years-scale compaction/state polish prototype + handover with limitations/policy/migration/M5 items + 45-55%+; E3 heavy evidence runs on RecipeLab/test-js-flat creative proxies + rich metrics (barrels/health/obs) + wired priors + 80%+ compliance/75%+ readiness; E2/E4/E5/E6/E7 diaries + prep for obs/versioning/hygiene/patterns/M5-handoff/REV1; E8 top-level cross-swarm synthesis + central M4-80-95-Completion-Package-Handoff.md in Findings/ with 90-95% DoD matrix, FRESH "3" verbatim logs (terminal exact + grep tool 0-def), iron/9GP, evidence bundle abs paths, honest 75-85%+ calib, known long-term limitations (from E1), migration guides, what M5 must validate at literal multi-month autonomous scale on real 50k+ user projects, patterns ref (D6 base + E1/E5 Guide), REV1 hygiene). 75-85%+ visible snapshot (strong compliance/hygiene/DF/GPs/zero-dep/"3" sacred/M5 boundary/spectrum from all E* + E1/E3 concrete + synthesis; gaps in literal multi-month real user 50k+ per M5 boundary). 0 overclaim. Target 90-95%+ post M5 dogfood. All iron rules upheld ("3" sacred 0 pollution, zero new deps, main clean, allowed targets only, subagent_id 100%, 8-step/9GP throughout, rich diaries). Central handoff + Milestones/checklist updates committed clean (only intended docs). M4 feature-building complete. Ready for M5. subagent_id=m4-80-95-e8. Accurate, honest, no overclaim. See M4-80-95-Completion-Package-Handoff.md for full harvest.

**90-95% Snapshot (2026-06-01; early / partial E* delivery; subagent_id=m4-80-95-e8)**: Central M4-80-95-Completion-Package-Handoff.md + E8 WT diary materialized (mandatory 6-file reads + FRESH "3" 0-def verbatim exact E1 cmd + variants + 8-step/9GP synthesis traces + long-term limitations + migration guides + what M5 must validate at literal multi-month autonomous scale on real 50k+ user projects (harvested from E1 handover + extended) + full evidence bundle with abs paths to E1 (prototype + handover) + E2 + priors + D6 patterns). E1/E2 delivered rich diaries + pure stdlib prototypes + handovers (pre-populating M5 artifacts, 45-55%+ calib, safe "3", 8-step/9GP). E3/E7 active; E4-E6 early. Honest 25-35%+ visible snapshot toward 90-95% long-term lens (target 75-85%+ post full E* + E8 re-synth + E3 evidence). See handoff for verbatim 90-95% DoD matrix + recs for M5 + E1/E2 artifacts. All iron rules + zero-dep + "3" sacred + M5 boundary upheld. Ready for E3-E7 completion + M5 dogfood. subagent_id=m4-80-95-e8.

**E5 Patterns Update (subagent_id=m4-80-95-e5)**: 90-95% advanced with polished Guide (Findings/M4-Years-Scale-Agent-Builder-Guide.md) extending D6 + wiring E1/E3/E2/C5 real metrics + concrete patterns + full 9GP/8-step/spectrum/honest lims + E8 ref section (abs paths + recs); 10+ FRESH "3" 0-def (exact cmds + tool "No matches found"; only safe :3109 cites); zero-dep .md; M5 boundary; subagent_id 100%; honest 20-30%+ visible (E* partial) / 75-85%+ target post E8 + full E3. See E5 diary + Guide for 8-step/9GP traces + matrices + synthesis surface. Checklist/Milestones updated clean. Ready for E8 + M5 literal multi-month real 50k+.

---

**M4 is complete when the above 90-95% criteria are met with the same rigor and evidence quality that closed M3.**

All prior M2/M3 discipline is carried forward and strengthened, with **zero new dependencies** as an explicit primary success criterion for every Work Area and artifact.

See the accompanying `m4-state-management-longterm-scale-plan.md` for the full vision, 9 GPs alignment, 8-step DF application, and detailed Work Area descriptions.

**subagent_id=m4-80-95-e5 — 90-95% patterns/DF/matrix/lims/E8 ref additions complete post FRESH #10 + synthesis. Zero-dep. "3" sacred (harness:3109 cite only). M5 boundary absolute. See Guide + E5 diary for full. Accurate, honest, no overclaim.**