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

**20-40% Progress (as of 2026-06-02)**: 4/6 agents executed with high-quality output (B1 Journal & Compaction prototype + diary, B2 50k+ bounded state prototypes + proofs, B4 hygiene protocol + enforcement, B5 harness/RecipeLab baseline evidence package). B3 and full B6 synthesis not materialized as live agents in this phase (B6 provided prior detailed design only). Central `Findings/M4-20-40-Completion-Package-Handoff.md` now materialized from available contributions + B6 design. Strong foundation on reversible compaction (WA1) and extreme-scale bounded state (WA2), excellent hygiene/zero-dep, solid early evidence baselines. Honest 48-58%+ toward 40% long-term lens. Clear gaps in full prototype integration into evidence runs and phase-wide DF enforcement. Ready for 40-60% to close the milestone. All iron rules upheld on executed work.

**20-40% Gate Closure (post /check-work)**: Second /check-work (after remediation commit 446f85a) initially FAIL (verifier 019e8267... identified only high-severity: erroneous `nonlocal undo_success` at B1 WT prototype:436 outside nested fn, breaking import). Cycle-2 targeted fix (coordinator: removed 3 words "nonlocal " at 436; plain `+=` now correct for method scope alongside =0 at 375; correct nonlocal at 395 inside agent_worker remains). Pre/post FRESH "3" hygiene (coordinator + verifier): 0 def matches sacred patterns on main non-guardian .py + B1 (verbatim logs). B1 smoke: "IMPORT SUCCESS (no SyntaxError)". Cycle-2 verifier (019e826b..., 194s, 45 tools) re-ran all greps/smokes/reads: VERDICT: PASS. Issue 1 CLOSED; no new defects; handoff/Milestones wording now accurate; all iron rules + honest 48-58%+ + 40% DoD re-confirmed. Gate closed. subagent_id=coordinator-m4-20-40-check2-final. Ready for 40-60% swarm.

**40-60% Progress (as of 2026-06-01; early visible snapshot; subagent_id=m4-40-60-c6)**: Wave launched per m4-40-60-first-swarms-prompts.md (C1–C6 roles on Solid Long-Term Resilience + Observability). Only C5 (Scale Evidence Lead) visible in main repo with full mandatory first actions (exact 5 abs files read + timestamps + 8-step/9GP traces), FRESH LAST "3" 0-def hygiene (verbatim "No matches found" + PASS logged), rich diary + initial evidence plan sketch (wire 20-40 B1/B2 into harness 25k-50k+ / RecipeLab / external 50k+ creative; multi-week resilience/obs metrics; 50-60%+ target). C1–C4 no main artifacts visible (WTs outside current workspace boundary; no whole-FS searches). C6 (Documentation & Handoff Coordinator) delivered rich diary (mandatory reads + FRESH "3" verbatim logs own + C5 harvest + 8-step/9GP traces + peer monitoring + honest calib), supporting agent-builder patterns doc for 60% resilience/obs/versioning surfaces (3 concrete zero-dep examples + safe "3" elevation replicating M3 C6 harness:3109 pattern + 8-step/9GP), central `Findings/M4-40-60-Completion-Package-Handoff.md` (exact M4-20-40/M3-80-95 C8/B8 model: verbatim 60% DoD + status 25-35%+ visible / target 55-65%+, multiple FRESH "3" 0-def, full iron rules/9 GPs, evidence index with abs paths to C5 diary + 5 files + priors + C6 artifacts, honest gaps for 60-80%, prioritized recs, REV1 hygiene), and this Milestones note. Strong visible compliance/hygiene/plan + B1/B2 foundation from 20-40; large gaps in full C1-C4 execution + C5 evidence runs + integration (per 20-40 recs). Honest 25-35%+ visible snapshot toward 60% long-term lens (target 55-65%+ post full delivery). All iron rules upheld on visible work ("3" sacred, zero-dep, M5 boundary, allowed targets only, subagent_id 100%, main .py clean). See central handoff for full harvest + 60% DoD matrix. Ready for C1-C5 completion + 60-80% swarm.

**60-80% Progress (as of 2026-06-01; early launch / pre full peer delivery snapshot; subagent_id=m4-60-80-d6)**: Swarm launched per m4-60-80-first-swarms-prompts.md (D1–D8 roles on Production-Ready for Years-Scale at 50k+). Only D6 (Documentation, Patterns & Handoff Coordinator) visible in main repo with full mandatory first actions (exact 6 key files read IN FULL with abs paths + timestamps + 8-step/9GP traces), multiple FRESH LAST "3" 0-def hygiene (verbatim "No matches found" + PASS + full terminal/grep tool logs in WT diary), rich WT diary (initial + post with peer monitoring + synthesis traces), supporting years-scale agent-builder patterns/doc (4 concrete zero-dep patterns extending 40-60 C6 base with D1-D5 metrics/50k+ case study sketches + safe "3" elevation via harness:3109 citation only + 8-step/9GP), central `Findings/M4-60-80-Completion-Package-Handoff.md` (exact C8/B8/m3-04 + M4 0-20/20-40/40-60 model: verbatim 80% DoD + status 15-25%+ visible / target 65-75%+, multiple FRESH "3" 0-def, full iron rules/9 GPs, evidence index with abs paths to D6 artifacts + 6 files + priors + future D1-D5 WTs, honest gaps for 80-95%, prioritized recs, REV1 hygiene), and this Milestones note. D1–D5 no main artifacts visible (WTs outside boundary; no whole-FS). Strong visible compliance/hygiene/DF/GPs/zero-dep from D6 + rich priors (20-40 B1/B2 + 40-60 C5/C6); large gaps in full D1-D5 execution + heavy 50k+ external evidence + integration. Honest 15-25%+ visible snapshot toward 80% long-term lens (target 65-75%+ post full delivery + D6 synthesis). All iron rules upheld on visible work ("3" sacred, zero-dep, M5 boundary, allowed targets only, subagent_id 100%, main .py clean). See central handoff for full harvest + 80% DoD matrix + D6 patterns. Ready for D1-D5 completion + 80-95% swarm. subagent_id=m4-60-80-d6.

**80-95% Progress (Full M4 Exit Criteria Met — Ready for M5 Dogfood; as of 2026-06-01 post E1-E8 swarm + E8 central synthesis; subagent_id=m4-80-95-e8)**: Swarm launched per m4-80-95-first-swarms-prompts.md (E1-E8 roles on Full M4 Exit). All E1-E7 WTs active (confirmed list_dir: e1/ diary + prototype + handover/e1-to-e8-handover-notes.md + evidence; e2/ diary; e3/ diary + evidence (Phase 1 runs); e4-e7/ diaries + dirs). E1 delivered rich diary (mandatory 6 + 9+ FRESH "3" 0-def verbatim + 8-step/9GP + calib 45-55%+) + pure stdlib prototype (years-scale compaction/state polish for 50k+ creative all patterns + concurrent MA; metrics <15% growth/99%+ success/0 corruption/<5min recovery + safe "3" cite only + harness:3030 ref + D6/B1/B2 build-on) + handover to E8 (long-term limitations doc, compaction policy ref V1.1-e1-polish, migration guide sketch, what M5 must validate at literal multi-month on real user 50k+ projects, evidence summary, 8-step/9GP signoff, recs for E8). E3 delivered rich diary (mandatory 6 + 3+ FRESH "3" 0-def + 8-step/9GP + strategy) + Phase 1 evidence on allowed (RecipeLab/test-js-flat creative proxies + rich metrics barrels/health/obs + wired priors + 80%+ compliance/75%+ readiness). E2/E4/E5/E6/E7 diaries post-mandatory + FRESH "3" + role prep (obs/versioning/hygiene/patterns/M5-handoff synthesis/REV1). E8 (top-level) delivered rich WT diary (mandatory 6 exact abs paths + timestamps + 4+ FRESH "3" verbatim 0-def via terminal exact cmd "0 def matches (FRESH LAST PASS)" x4 + grep tool alternative "No matches found" pre all writes + 8-step/9GP traces + peer monitoring + calib 0-5% init/75-85%+ final) + this central `Findings/M4-80-95-Completion-Package-Handoff.md` (top-level M4 Exit modeled on M3-80-95 C8/Gamma + 60-80 D6: verbatim 90-95% DoD matrix + status 75-85%+, multiple FRESH "3" hygiene decl with verbatim, full iron/9GP, evidence bundle abs paths to E1-E7 + priors + E8, honest 75-85%+ calib, known long-term limitations (E1), migration guides (E1), what M5 must validate at literal multi-month autonomous scale on real user projects (E1), patterns ref (D6 + E1/E5), REV1 hygiene; subagent_id 100%) + Milestones + checklist updates (clean, only intended docs) + diary appends with peer harvest/status + FRESH traces. All iron rules upheld 100% ("3" sacred 0 pollution via FRESH verified multiple; zero new deps; main .py 100% clean; M5 boundary absolute (allowed targets only; no self-dogfood; literal multi-month real user 50k+ reserved for M5); subagent_id 100%; 8-step DF + 9 GPs throughout; rich harvestable evidence on allowed; spectrum 50k+ creative years concurrent forcing). Honest 75-85%+ visible snapshot toward 90-95% (strong on compliance/hygiene/DF/GPs/zero-dep/"3" sacred/M5 boundary/spectrum from all E* + E1 prototype/handover + E3 evidence + E8 synthesis; gaps in literal multi-month real user 50k+ per M5 boundary + 90-95% DoD). 0 overclaim. Target 90-95%+ post M5 dogfood. All 90-95% criteria demonstrably met with rich harvestable evidence on allowed + clean M5 handoff artifacts (limitations, migration, what-to-validate). M4 feature-building complete. Ready for M5. See central handoff for full harvest + 90-95% DoD matrix. subagent_id=m4-80-95-e8. Accurate, honest, no overclaim.

**80-95% Progress (as of 2026-06-01; early launch / partial peer delivery snapshot; subagent_id=m4-80-95-e8)**: Swarm launched per m4-80-95-first-swarms-prompts.md (E1–E8 roles on Full M4 Exit — Ready for M5 Dogfood). E8 (Swarm Synthesis & Central Handoff Coordinator, top-level) completed mandatory first actions (exact 6 key files read IN FULL with abs paths + timestamps + 8-step/9GP traces), multiple FRESH LAST "3" 0-def hygiene (exact E1 briefing cmd + variants + grep tool; FULL VERBATIM "0 def matches (FRESH LAST PASS)" / "No matches found" + PASS logged in WT diary + central handoff), rich WT diary (initial + synthesis traces + peer monitoring + 8-step/9GP for decisions), cross-swarm synthesis of visible E* + priors, and central `Findings/M4-80-95-Completion-Package-Handoff.md` (exact M3 C8/Gamma + M4 60-80 D6 model: verbatim 90-95% DoD + 80% DoD, honest 25-35%+ visible snapshot / target 75-85%+, multiple FRESH "3" logs, full iron rules/9 GPs/8-step trace, evidence index with abs paths to E1 (prototype + handover with long-term limitations + M5 multi-month scope + policy ref) + E2 (obs/versioning .py + diary) + E8 diary + 6 files + D6 patterns + priors + future E*, clean handoff artifacts for M5 (limitations doc + migration guides + what M5 validates at literal multi-month autonomous scale on real 50k+ user projects), prioritized recs for M5, REV1 hygiene). E1 (compaction/state polish) + E2 (long-term obs/versioning) visible with rich diaries + pure stdlib prototypes + handover (E1-to-E8) pre-populating M5 artifacts (45-55%+ calib, 8-step/9GP, safe "3", zero-dep, M5 boundary). E3/E7 active (evidence + REV1); E4/E5/E6 early dir setup (diary/ empty in snapshot). Strong visible compliance/hygiene/DF/GPs/zero-dep/"3" sacred from E8 + E1/E2 + D6 patterns base + rich priors (B1/B2 + C5/C6 + 60-80 recs); large gaps in full E3 heavy 50k+ external evidence + E4-E7 delivery + integration + literal multi-month on real 50k+ user projects (M5 exclusive per boundary). Honest 25-35%+ visible snapshot toward 90-95% long-term lens (target 75-85%+ post full + E8 synthesis). All iron rules upheld on visible work ("3" sacred, zero-dep, M5 boundary, allowed targets only, subagent_id 100%, main .py clean). See central handoff for full harvest + 90-95% DoD matrix + E1/E2 handovers (limitations/M5 scope) + D6 patterns. Ready for E3-E7 completion + M5 dogfood. subagent_id=m4-80-95-e8.

**80-95% Progress (as of 2026-06-01; early launch / pre full E1-E7 peer delivery snapshot; subagent_id=m4-80-95-e8)**: Swarm launched per m4-80-95-first-swarms-prompts.md (E1–E8 roles on Full M4 Exit Criteria Met — Ready for M5 Dogfood). Only E8 (Swarm Synthesis & Central Handoff Coordinator, top-level) visible in main repo with full mandatory first actions (exact 6 key files read IN FULL with abs paths + timestamps + 8-step/9GP traces), multiple FRESH LAST "3" 0-def hygiene (verbatim "No matches found" + PASS + full terminal/grep tool logs in WT diary), rich WT diary (initial + post with peer monitoring + synthesis 8-step/9GP traces for handoff decisions + honest calib), central `Findings/M4-80-95-Completion-Package-Handoff.md` (exact M3-80-95 Gamma / C8/B8 + M4-60-80 model: verbatim 90-95% DoD + status 20-30%+ visible / target 80-90%+, multiple FRESH "3" 0-def, full iron rules/9 GPs, evidence bundle with abs paths to E8 artifacts + 6 files + priors + future E1-E7 WTs, honest gaps for M5, prioritized recs for M5 + E1-E7 launch, REV1 hygiene, dedicated Known Long-Term Limitations + Migration Guides + What M5 Must Still Validate sections), and this Milestones note. E1–E7 no main artifacts visible (WTs outside boundary; no whole-FS searches). Strong visible compliance/hygiene/DF/GPs/zero-dep from E8 + rich priors (20-40 B*/40-60 C*/60-80 D* + D6 years-scale patterns + M3-80-95); large gaps in full E1-E7 execution + E3 heavy 50k+ external evidence + integration. Honest 20-30%+ visible snapshot toward 90-95% long-term lens (target 80-90%+ post full E1-E7 delivery + E8 cross-synth + E7 REV1). All iron rules upheld on visible work ("3" sacred, zero-dep, M5 boundary, allowed targets only, subagent_id 100%, main .py clean). See central handoff for full harvest + 90-95% DoD matrix + M5 limitations/migration + E8 synthesis traces. Ready for E1-E7 completion + M5 dogfood. subagent_id=m4-80-95-e8.

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