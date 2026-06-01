# Wikifier Project Milestones Overview

**Date**: 2026-05-28 (Rebuilt per user direction after full project review)
**Current Status**: M1 Complete. M2 considered sufficiently advanced (post 86-90 deeper wave + user decision). Moving into M3 – Agent Interface & Ergonomics (Feature Building Phase).

---

## Milestone Philosophy (User Clarified)

- **M1–M4**: Feature building and technical gap closure phases.
  - Goal: Implement the core capabilities, make them solid, observable, scalable, and usable in real workflows.
  - Real usage on the developer's own projects during these phases is treated as **valuable design/implementation feedback and feature exercising**, not final validation.
- **M5**: Broad dogfooding and production hardening.
  - Goal: Stress-test the completed feature set across multiple real-world projects the user has prepared, achieve "set & forget" confidence, and reach full production release quality.

This structure prevents the feature-building work from being incorrectly measured against final-dogfood success criteria.

---

## Current Milestone Status

### M1 – Core Reliability (Complete)

**Focus**: Foundational stability, basic health, locking, change recording, consistency, and self-hosting hygiene.

**Delivered**:
- Health matrix, locking, record_change / mark_green lifecycle
- Basic journaling and pending state
- MCP consistency and daemon foundations
- Self-hosting hygiene discipline established
- `--gap1-health` (and later `--m2-health`) gates functional

**Status**: [x] Complete.

---

### M2 – Dependency Intelligence (In Progress – Feature Building Phase)

**Focus**: Make `update-maps` and the surrounding stateful system genuinely useful, reliable, observable, and scalable as the "living memory" layer for agents. Zero new dependencies. Works from tiny to 50k+ creative monorepos.

**Core Vision for Completed M2**:
An agent (or swarm) can maintain a high-fidelity, low-ambiguity, incrementally-updatable map of any codebase over months/years — with bounded state, actionable diagnostics, first-class semantic intent logging, and query surfaces that remain fast and useful at scale.

#### Major M2 Workstreams & Current Status (Post 80/82/83/84/85 Swarm)

**A – Streaming / Resumable / Partials + Reverse (Strong Progress)**
- Core `generate_update_events` + `run_update_stream` + `PartialResult_v1` + continuation + budgets + ACS/CIABRE hooks now on main and exercised.
- Reverse dependency maintenance (A1) present and surviving real edits/renames in real usage.
- Real usage on 5k+ main Wikifier creative self-host (80 Phase 1 + supporting slices) proved O(changed) behavior, high partials usage, no full O(n) fallback on normal workflows.
- **Remaining for M2 feature complete**: Full thin-shell parity for new streaming paths (no fallback temptation), richer structured summaries as the unquestioned default in library.md / CLI / MCP.

**B – Health Durability (Good Real-Usage Evidence)**
- Health durability, stale detection, heal policy, sharded views, provenance, and multi-agent safety exercised under authentic concurrent load from 80 on the real 5k+ target (82).
- Zero flakiness, reliable Yellow/Red from real churn, 100% heal success in real cycles.
- **Remaining**: Further years-scale compaction + query usefulness under sustained real multi-agent load (some work can carry into M3/M4).

**C – Journal / Compaction / Intent (Strong Real-Usage Evidence)**
- Event-sourced journal + smart compaction hooks + bounded pending + useful historical intent queries demonstrated on the real 5k+ Wikifier creative target under Phase 1 load (83 + integration with 80/82/84).
- Journal now functions as source of truth for intent, health transitions, and transparency.
- **Remaining**: Production-grade compaction policies + richer historical query surfaces (partially M2, some can extend).

**D – Transparency / ACS + CIABRE (Strong Real-Usage Evidence)**
- Full first-class low-conf / unresolved / failure transparency "as easy as success", parser parity on all paths, ACS/CIABRE explain-all everywhere, exercised on real creative paths (84 + prior 74).
- **Remaining**: Complete coverage on every failure mode + even richer suggestion_for_agent surfaces.

**E – v0.4 Thin Library + Protocol + Ergonomics (Good Foundations + Real Usage)**
- Pure Python-primary surfaces, thin MCP/CLI wiring, contracts v1, flat ergonomics, protocol alignment demonstrated on real 5k+ usage (85 + prior 75).
- Library usable for core agent loops.
- **Remaining**: Complete thin-shell parity + final v0.4 conformance polish + richer executive summary consumption.

**Cross-Cutting (Hygiene, Harness, Observability)**
- Main hygiene strong (0 critical markers, import GREEN).
- Harness `--m2-health --deep` mature (54/46/0 baseline, 10k–50k creative generators, journal/compaction hooks, real external 5k+ patterns).
- The 80/82/83/84/85 swarm on the actual 5k+ main Wikifier creative self-host provided the best real-usage feature exercising the project has seen (journal as intent source, health matrices under real churn, transparency on creative paths, v0.4 surfaces in practice, high partials with no fallback on normal work).

**Overall M2 Assessment (Feature-Building Lens)**:
M2 is considered sufficiently advanced after the 86-90 deeper durability/scale hardening wave (strong evidence across years-load compaction, session observability, 50k+ creative stress, sustained concurrency, and cross-integration, with clean independent review). 

Per user direction (2026-05-29), we are treating current M2 state as adequate to move forward. Remaining M2 polish items can be addressed opportunistically or in M3/M4 as needed. The previous strict 82–87% / 0/7 framing remains inappropriate during feature-building phases.

**M2 Status**: Sufficient for transition to M3.

---

### M3 – Agent Interface & Ergonomics

**Focus**: Clean, versioned public Python library + rigorous testable Agent Protocol (v0.4+). Thin consumers (CLI/MCP) are excellent but secondary.

**Status**: Active (as of 2026-05-29). Foundations in place from M2. Detailed execution plan created in `Findings/m3-agent-interface-ergonomics-plan.md`.

**Guiding Constraints** (per user direction):
- Long-term focus and full scalability spectrum (tiny → massive creative monorepos)
- Actual usefulness as close to 95% on the feature-building lens
- Feature creation, addition, and refinement only
- **No dogfooding** on the Wikifier project itself (harness + RecipeLab + user-designated external projects only)
- Same discipline as M2-M4 (zero new dependencies, rich evidence, honest tracking)

See `Findings/m3-agent-interface-ergonomics-plan.md` for the full plan.

**Execution Progress (80-95% multiple concurrent swarms active; prior phases complete)**:
- 0-20% foundations swarm (m3-01/02/03/04 + M3-04 handoff) complete with audits, v0.4 gap analysis, long-term lens (8-step DF), 0-20 handoff package.
- 20-40% core surfaces swarm (m3-a1 to m3-a8) complete: stable 20% library surface (partials/continuation first-class), v0.5 protocol baseline + conformance prototype, versioning contracts sketch, automated thin parity skeleton, early evidence on allowed targets, tiered agent-builder docs/examples (elevating sacred partials/continuation), A7 quality/zero-dep gate, A8 20-40 handoff + REV1 hygiene PASS. /check-work clean. Concrete artifacts in subagent-m3-a* WTs.
- 40-60% swarm (m3-60-b1..b8) complete: polished ergonomic core + long-running examples (B1), extended conformance validation hooks (B2), versioning hardening + migration helpers (B3), expanded thin parity tests ≥0.90 fidelity (B4), heavy evidence on RecipeLab + 5k+ creative + harness patterns (B5), docs + 5 examples incl. weeks/months autonomous + multi-agent concurrent + "3" elevation (B6), cross-cutting quality/DF reviews + 8-step + Prin + "3" hygiene on all peers (B7), B8 central M3-40-60-Completion-Package-Handoff.md + REV1 PASS (9 GPs verbatim, 60% DoD mapping, evidence index abs paths, honest ~5-15% calib at snapshot, recs for C execution). All per iron rules (FRESH "3" 0-def, read A8 first, zero-dep, WT only, allowed targets). See B8 handoff.
- 60-80% swarm (m3-60-80-c1..c8) complete: production library ergonomics + weeks/months examples (C1), full protocol conformance long-running contract suite (C2, 10 vectors MA/daemon/human/"3"/50k+), versioning migration completion + 50k+ creative scale sims O(changed) bounded 0-drift (C3), full 80% thin consumers parity/excellence tests fidelity ≥0.92 (C4), heavy evidence diary + probes on harness 25k-50k+ gens + RecipeLab + externals (C5, 17+ FRESH "3"), comprehensive production agent-builder guide + 5 new 80% examples incl. sacred-3-partials-continuation-elevation.py (harness:3109 hero path) + good-citizen-months-years + full-concurrent (C6), cross-cutting quality long-term viability diary + peer reviews on B1/C1 base (C7, 8-step + Prin + "3" + 95%+ on #1/2/5/7), C8 central M3-60-80-Completion-Package-Handoff.md (modeled on B8: 9 GPs + 80% DoD verbatim, 5+ FRESH "3" 0-matches, REV1 PASS on available, evidence index, recs for E/F evidence + synthesis; honest ~5-15% at C8 snapshot now advanced by full C* delivery). All WTs subagent-m3-60-80-c* + b* populated with diaries/artifacts; main clean; "3" sacred (FRESH greps every write); C8 read mandate for 80-95.
- **80-95% multiple concurrent swarms launched** (2026-06-01, post "Snill no spawns" correction): 19 agents across 3 parallel swarms in isolated persistent WTs (confirmed list_dir + polls). 
  - **Alpha E1-E8** (Final Surfaces & Conformance; e1..e8 WTs): E1 COMPLETE (393s, exit 0): read prompts + C8 handoff IN FULL (abs) + all key B*/C* artifacts first; 4+ ULTIMATE FRESH "3" greps (0 def matches ^test_partial_continuation_workflow_25k on non-guardian harness copies + planned paths pre ANY writes; only subagent-3:3109 historical guardian + safe cites; verbatim logs in diary; PASS verdict); 9 GPs quoted + 8-step DF to every decision; produced M3-E1-Final-Production-Surfaces-Conformance-Versioning-Polish-50k-Readiness.py (~450 LOC pure stdlib, GoodCitizenManager months/years, ConcurrentModelSupport daemon/human/MA, MigrationGuarantees + C3 policy, DualOutputEnhancer, final_update_maps unified, 50k+ creative demo barrels/dyn/cond/ws/symlinks/JS+Py O(scope) bounded partials/"3" elevated ergonomically, metrics Prin #1/2/5/6/7 + harness/RecipeLab integration notes post FRESH); rich local diary (all mandatory sections + FRESH logs + 40-55%+ calib + evidence index + COMPLETION + handoff to Gamma/central); git commit ac458af with subagent_id. E2-E8 running (350-410s elapsed, 40-62 tool calls, read/grep/list/todo/write phase, 0-1 errors). 
  - **Beta F1-F8** (Heavy Evidence & Quality Gate; f1..f8 WTs): F1-F8 running (227-315s, 19-46 tool calls, same mandated early read C8/priors/prompts + FRESH "3" grep + list_dir + todo + write); f2/f5 have early .py + .md per list_dir. Long-pole F5 evidence role active.
  - **Gamma G1-G4** (Documentation & Synthesis / central 90-95% harvest coord; g1..g4 WTs): G1-G4 running (151-197s, 13-42 tool calls, list_dir/read/grep/todo for coordination across Alpha/Beta output + C8/B*); preparing synthesis of E8/F8 harvests into C8-style central 90-95% M3 Exit Handoff package(s).
  - **Common (all 19)**: Prompts `Findings/m3-80-95-first-swarms-prompts.md` (E1-E8 + F1-F8 + G1-G4 roles to finish 80% polish + drive 90-95% full exit; explicit multiple swarms concurrent design). Mandatory: read C8 handoff + prompts + key B*/C* FIRST; multiple FRESH "3" (0 def on sacred terms pre/post writes, only guardian 3109 safe); 8-step DF + anti-patterns + 9 GPs verbatim; 80%/90-95% DoD mapping (polished long-running weeks/months ergonomics, full conformance, versioning/migration complete+tested, thin parity ≥0.92 excellence, ultra-heavy 50k+ creative evidence on allowed only, comprehensive docs with "3" as natural scalable path, quality/long-term gate); honest 40-55%+ calib; subagent_id=m3-80-95-E*/F*/G* in 100% output/headers/commits/diaries; rich local diaries + concrete artifacts (no main .py, WT only); zero new deps (pure stdlib); M5 boundary absolute (harness copies for hygiene + RecipeLab + designated externals 5k+ creative only); main 100% clean. WTs: /home/aron/.grok/worktrees/Wikifier/subagent-m3-80-95-e1..e8, f1..f8, g1..g4 (e1: 1 .py + 1 .md confirmed delivered; others early files per progress; all dirs present). Monitoring via task_ids (E1=019e81f7-a9ba-77a1-b892-b13cb65e3caf COMPLETE; E2=019e81f7-cf50-7120-adeb-707ee96f6ea2 running; ... E8=019e81f9-1cdf-7971-823a-d42ab6dd3e63; F1=019e81f9-74ca-7851-afb0-15ea9323d1b1 ... F8=019e81fa-ec97-7a81-8de3-e92ae56b4df5; G1=019e81fb-94d4-7832-9afb-3448797edf2a ... G4=019e81fc-4521-79f0-a803-604f4de70081). E1 early deliverable feeds E5/F5 evidence + G* synthesis. See C8 for 60-80 harvest + recs; E8/F8/G* for 90-95 central handoff + full M3 exit gate.

**80-95% Multiple Concurrent Swarms COMPLETE + Gamma Final Coordination (M3 Execution Wrapped)**  
- All 19 agents (E1-E8 Alpha surfaces/conformance/versioning/polish + 50k+ creative demos; F1-F8 Beta heavy evidence/quality gate synthesizing C5 multi-week 50k+ metrics on harness 25k "3" 100% roundtrip/0 drift/0 corruption + RecipeLab ~1679 + external 5k+ + Prin +5-6 scores + 0.52s friction; G1-G4 Gamma docs/patterns/synthesis building on C6 production guide + sacred-3-partials-continuation-elevation.py with exact harness:3109 safe replication only) delivered rich local diaries + concrete artifacts (abs paths in central handoff Evidence Bundle).  
- Central M3 80-95% Completion Package Handoff created (2026-06-02) in main repo: `Findings/M3-80-95-Completion-Package-Handoff.md` (22.7KB, modeled exactly on C8/B8: verbatim 9 GPs + 80%/90-95% DoD from prompts/checklist, 3+ FRESH LAST "3" hygiene with verbatim grep outputs showing 0 def on main non-guardian .py + all active 80-95 WT .py (only historical guardian L3109 + safe cites + controlled copies), full evidence index with abs paths to every E*/F*/G* artifact + C5/C7/B8/C8/A8/m3-03/04 + harness/RecipeLab, honest 48-55%+ calib, REV1 PASS on available, recs for M4 state/long-term scale + M5 boundary absolute). Git commit b9a37f6 (subagent_id=m3-80-95-gamma-final-coord).  
- /check-work PASS prior to final coordination. User explicit choice "1" (Gamma handoff now vs straight to M4). M3 feature-building execution fully wrapped. All iron rules 100% (zero new deps, main .py 100% clean, "3" sacred untouched, allowed targets only, subagent_id 100%, 8-step DF + 9 GPs throughout).  
- Ready for M4 planning (State Management & Long-Term Scale) while evidence is fresh. See the central handoff for full harvest, mappings, and prioritized next steps.

---
### M4 – State Management & Long-Term Scale

**Focus**: Years of autonomous multi-agent load, advanced compaction, full 50k+ creative monorepo resilience (barrels + dyn/cond imports + workspaces + symlinks + high churn + partials/"3" under sustained concurrent MA + daemon + human operation), richer long-horizon observability, and long-term versioning/migration policy.

**Status**: Planning complete (2026-06-02). M3 feature-building execution fully wrapped (80-95% multiple concurrent swarms + Gamma central handoff + README + Milestones updates pushed). Significant foundations from M2 (event sourcing, compaction hooks, bounded structures, real usage data from 80-85/86-90 swarms) + M3 ergonomic surfaces now exist. Most heavy lifting for years-scale durability and long-term state management remains here.

**Guiding Constraints** (per user direction and carried from M3):
- Long-term focus (5–10+ year viability for autonomous agents) and full scalability spectrum first (tiny scripts remain delightful; 50k+ creative monorepos with all target patterns are the forcing function).
- Actual usefulness as close to 95% on the long-term feature-building lens.
- Feature creation, addition, and refinement only.
- **Zero new dependencies** as the primary lens for all new state, compaction, health, and observability logic (pure stdlib + existing patterns).
- **No dogfooding** on the Wikifier project itself (harness extended long-term suites + RecipeLab + user-designated external creative monorepos only).
- Same (or stricter) discipline as M2–M4: "3" sacred with explicit FRESH LAST greps (0 def on active non-guardian code), 8-step DF + 9 GPs in every decision, rich evidence on allowed targets only, main .py 100% clean until M5, subagent_id everywhere, central handoff model.
- Honest calibration.

See:
- `Findings/m4-state-management-longterm-scale-plan.md` (full vision, 9 GPs alignment with zero-dep primary emphasis, 6 Work Areas, 8-step DF application, phased approach, exit criteria)
- `Findings/m4-state-management-longterm-scale-checklist.md` (executable progressive 20/40/60/80/90-95% DoD with measurable criteria per Work Area)
- `Findings/M3-80-95-Completion-Package-Handoff.md` (explicit M4 prioritized recommendations from M3 closure)
- `Findings/m4-first-swarms-0-20-prompts.md` + `m4-20-40-first-swarms-prompts.md` + `m4-40-60-first-swarms-prompts.md` + `m4-60-80-first-swarms-prompts.md` + `m4-80-95-first-swarms-prompts.md` (ready-to-launch swarm prompts for all 5 phases)

**Execution Model**: 6–8 agent swarms per major sub-phase in isolated worktrees, rich local diaries, central handoffs (C8/B8 style), REV1 oversight. All serious validation on allowed targets only. Prompts for 0-20% swarm ready to launch.

**0-20% Progress (as of 2026-06-02)**: Swarm launched (M4-01–06). M4-01 (Journal & Compaction Auditor), M4-03 (Long-Term Lens & 8-Step DF), M4-05 (Evidence/Harness Strategy), and M4-06 (Coordinator) completed with rich WT artifacts. Central `Findings/M4-0-20-Completion-Package-Handoff.md` synthesized (20% DoD status 35-45%+, WA1 audit + 20% proposal from M4-01, full 8-step matrices + swarm guidance from M4-03, evidence strategy + harness extensions from M4-05, FRESH "3" hygiene 0-def by all, honest calib). Equips 20-40% swarm for rapid 40% milestone. M4-02/04 still active (expected per discovery design). All iron rules upheld (zero-dep primary, "3" sacred, M5 boundary).

**M3 → M4 Transition Note**: M3 (Agent Interface & Ergonomics) is now feature-building complete. The polished library, v0.5 protocol baseline, long-running ergonomics, thin parity, versioning, and comprehensive agent-builder patterns (including sacred "3" elevation via safe citation only) provide the ergonomic foundation. M4 makes the underlying state durable and trustworthy for years of autonomous operation on the hardest 50k+ creative targets.

---

### M5 – Final Polish, Dogfooding & Release

---

### M5 – Final Polish, Dogfooding & Release

**Focus**: Broad dogfooding on the multiple real-world projects the user has prepared, final "set & forget" confidence, production release quality, full 7-criteria + long-term exit validation.

**Status**: Not started. This is where the strict old 85% / 95%+ scoring and literal multi-day high-trust external long-pole criteria will be applied as final gates.

---

## Key Principle Going Forward (Updated 2026-05-29)

**M1 is complete.**

**M2–M4 are explicit feature addition phases only.** These phases are strictly for feature creation, addition, refinement, and hardening. 

**No dogfooding of any kind on the Wikifier project itself is permitted until M5.** This includes (but is not limited to):
- Running `--m2-health --deep` or equivalent heavy self-validation on the Wikifier source tree
- Sustained autonomous sessions on the Wikifier codebase
- Treating the Wikifier project as a primary dogfood or validation target

All real usage, stress testing, and validation during M2–M4 must be restricted to the harness, RecipeLab, and user-designated external projects only.

**M5 is the dedicated full dogfooding and testing phase.** This is where broad dogfooding on the multiple real-world projects the user has prepared will occur, along with the strict final 7-criteria scoring, literal multi-day high-trust autonomous operation on true 5k+ external monorepos, and complete 0/7 85% evaluation.

During M2–M4, references to "actual 95%" or progress toward 95%+ refer exclusively to the quality, completeness, and long-term viability of features being added (under the 9 Guiding Principles). They do **not** refer to the final M5 dogfood success criteria.

---

## Next Steps (Post 86-90 Wave + M2 Transition)

1. M2 is considered sufficiently advanced (post 86-90 deeper durability/scale wave + user decision on 2026-05-29). Focus now shifts to M3 – Agent Interface & Ergonomics.
2. Execute the M3 plan defined in `Findings/m3-agent-interface-ergonomics-plan.md` using the same high-discipline approach (feature creation/refinement only, long-term + scalability focus, zero new dependencies, no dogfooding on the Wikifier project itself).
3. **Explicit Rule (unchanged)**: No dogfooding of any kind on the Wikifier project itself during M2–M4. Use harness + RecipeLab + user-designated external projects only. All heavy validation and broad dogfooding is reserved for M5.
4. Keep main clean and maintain the established hygiene practices for all M3 work.

All prior discipline remains: "3" untouched, zero new deps, 9-step hygiene where applicable, honest tracking, main clean. Long-term viability, explicit zero-dependency, and full scalability spectrum (small to massive creative monorepos) are the primary drivers.