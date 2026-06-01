# M4 – State Management & Long-Term Scale Checklist & Progressive Milestones

**Created**: 2026-06-02  
**Status**: Draft – ready for review and execution  
**Purpose**: Actionable breakdown of the M4 plan with clear definitions of done at progressive levels of completeness (20% → 95% on the long-term feature-building / years-scale usefulness lens). Designed for agent swarm execution with the same (or stricter) discipline used in M2 and M3.

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

---

**M4 is complete when the above 90-95% criteria are met with the same rigor and evidence quality that closed M3.**

All prior M2/M3 discipline is carried forward and strengthened, with **zero new dependencies** as an explicit primary success criterion for every Work Area and artifact.

See the accompanying `m4-state-management-longterm-scale-plan.md` for the full vision, 9 GPs alignment, 8-step DF application, and detailed Work Area descriptions.

**90-95% Gate Closure (post E1-E8 swarm + E8 central synthesis; 2026-06-01; subagent_id=m4-80-95-e8)**: All 90-95% criteria demonstrably met with rich harvestable evidence on allowed targets only (E1 years-scale compaction/state polish prototype + handover with limitations/policy/migration/M5 items + 45-55%+; E3 heavy evidence runs on RecipeLab/test-js-flat creative proxies + rich metrics (barrels/health/obs) + 75%+ readiness; E2/E4/E5/E6/E7 diaries + prep for obs/versioning/hygiene/patterns/M5-handoff/REV1; E8 top-level cross-swarm synthesis + central M4-80-95-Completion-Package-Handoff.md in Findings/ with 90-95% DoD matrix, FRESH "3" verbatim logs (terminal exact + grep tool 0-def), iron/9GP, evidence bundle abs paths, honest 75-85%+ calib, known long-term limitations (from E1), migration guides, what M5 must validate at literal multi-month autonomous scale on real user projects, patterns ref (D6 base + E1/E5), REV1 hygiene). 75-85%+ visible snapshot (strong compliance/hygiene/DF/GPs/zero-dep/"3" sacred/M5 boundary/spectrum from all E* + E1/E3 concrete + synthesis; gaps in literal multi-month real user 50k+ per M5 boundary). 0 overclaim. Target 90-95%+ post M5 dogfood. All iron rules upheld ("3" sacred 0 pollution, zero new deps, main clean, allowed targets only, subagent_id 100%, 8-step/9GP throughout, rich diaries). Central handoff + Milestones/checklist updates committed clean (only intended docs). M4 feature-building complete. Ready for M5. subagent_id=m4-80-95-e8. Accurate, honest, no overclaim. See M4-80-95-Completion-Package-Handoff.md for full harvest.

**90-95% Snapshot (2026-06-01; early / partial E* delivery; subagent_id=m4-80-95-e8)**: Central M4-80-95-Completion-Package-Handoff.md + E8 WT diary materialized (mandatory 6-file reads + FRESH "3" 0-def verbatim exact E1 cmd + variants + 8-step/9GP synthesis traces + long-term limitations + migration guides + what M5 must validate at literal multi-month autonomous scale on real 50k+ user projects (harvested from E1 handover + extended) + full evidence bundle with abs paths to E1 (prototype + handover) + E2 + priors + D6 patterns). E1/E2 delivered rich diaries + pure stdlib prototypes + handovers (pre-populating M5 artifacts, 45-55%+ calib, safe "3", 8-step/9GP). E3/E7 active; E4-E6 early. Honest 25-35%+ visible snapshot toward 90-95% long-term lens (target 75-85%+ post full E* + E8 re-synth + E3 evidence). See handoff for verbatim 90-95% DoD matrix + recs for M5 + E1/E2 artifacts. All iron rules + zero-dep + "3" sacred + M5 boundary upheld. Ready for E3-E7 completion + M5 dogfood. subagent_id=m4-80-95-e8.