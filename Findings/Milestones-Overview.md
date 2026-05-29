# Wikifier Project Milestones Overview

**Date**: 2026-05-28 (Rebuilt per user direction after full project review)
**Current Status**: M1 Complete. M2 In Progress (Feature Building Phase).

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
M2 is substantially advanced. The core streaming engine, health/journal/transparency durability, reverse maintenance, and v0.4 thin surfaces have been implemented and meaningfully exercised on a real 5k+ creative monorepo under sustained load.

The previous strict 82–87% / 0/7 framing (driven by the old 7-criteria, especially literal multi-day external long-pole as the blocker for 85%) is no longer the primary measure during the M2 feature-building phase. That level of final validation belongs in M5.

**M2 Feature-Complete Target**:
All A–E workstreams have their core implementation + basic real-usage validation complete, thin shells have parity for the new paths, richer summaries are the normal/default experience, and the system is observably solid on the developer's own 5k+ creative projects.

---

### M3 – Agent Interface & Ergonomics

**Focus**: Clean, versioned public Python library + rigorous testable Agent Protocol (v0.4+). Thin consumers (CLI/MCP) are excellent but secondary.

**Status**: Foundations in place (library surfaces, contracts v1, protocol sketch in skills/run.md). Some real usage in 85. Needs completion after M2 core is solid.

**Rule**: No heavy M3 claims until M2 feature set is stable.

---

### M4 – State Management & Long-Term Scale

**Focus**: Years of autonomous multi-agent load, advanced compaction, full 50k+ creative monorepo resilience, richer observability.

**Status**: Significant foundations from M2 (event sourcing, compaction hooks, bounded structures, real usage data from 80-85 swarm). Most heavy lifting here.

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

## Next Steps (Post This Rebuild)

1. Execute the phased plan defined in `Findings/m2-phased-to-95-agent-plan.md`:
   - Complete current work under Phase 80-85 (M2 core feature completion) using groups of 8 agents. Detailed working checklist: `Findings/m2-80-85-feature-completion-checklist.md`.
   - Then Phase 86-90 (durability & scale hardening).
   - Then Phase 91-95 (final polish & long-term exit closure).
2. **Explicit Rule**: No dogfooding of any kind on the Wikifier project itself during M2–M4. This includes running `--m2-health --deep` or any sustained/heavy validation on the Wikifier source tree. All such activity is deferred to M5. Use harness + RecipeLab + user-designated external projects only during feature-building phases.
3. Keep main clean and follow the 9-step hygiene + "3" untouched rules for all remaining work.

All prior discipline remains: "3" untouched, zero new deps, 9-step hygiene where applicable, honest tracking, main clean. Long-term viability, explicit zero-dependency, and full scalability spectrum (small to massive creative monorepos) are the primary drivers.