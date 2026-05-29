# M2 Phased Execution Plan to 95%+ (Feature Building Focus)

**Created**: 2026-05-28  
**Purpose**: Define a clear, disciplined, phased path from current M2 state to honest 95%+ "set & forget" capability using groups of 8 agents per major phase.  
**Core Constraints (Non-Negotiable)**:
- **M1 is complete**.
- **M2–M4 = Explicit Feature Addition Phases only**. These phases are strictly for feature creation, addition, refinement, and hardening. 
- **No dogfooding of any kind on the Wikifier project itself until M5**. This includes running `--m2-health --deep`, sustained autonomous sessions, heavy self-validation, or treating the Wikifier source tree as a primary dogfood target in any form. All real usage, stress, and validation during M2–M4 must be restricted to the harness, RecipeLab, and user-designated external projects only.
- M5 is the dedicated full dogfooding and testing phase on the multiple real-world projects the user has prepared. The strict final 7-criteria scoring, literal multi-day high-trust autonomous operation on true 5k+ external monorepos, and complete 0/7 85% evaluation are reserved exclusively for M5.
- During M2–M4, "actual 95%" refers to the quality, completeness, and refinement of features under the long-term principles (zero new dependencies, full scalability spectrum, event-sourced durability, full observability, etc.). It does **not** refer to the final M5 dogfood success criteria.
- Long-term viability (5–10+ years), **explicit zero new dependencies**, and **full scalability spectrum** (Tiny <100 files → Medium → Large → Massive 15k–50k+ → Creative Monorepos with barrels, dynamic/conditional imports, JS+Python mixes, workspaces, symlinks) are the primary design drivers.
- "3" (original partials deep proof track + `test_partial_continuation_workflow_25k`) remains **absolute last and untouched**.
- All work follows the 9-step hygiene-first discipline (local-only worktrees until properly gated + reviewed, small batches, full `--m2-health --deep` gates before main consideration, dual independent reviewers).

---

## Guiding Principles (Reinforced for All Phases)

1. **Scalability Spectrum First** — Every deliverable must have explicit, tested answers for the full range from tiny scripts to massive creative monorepos.
2. **Zero-Dependency + Portable** — Pure stdlib + existing patterns only. No new packages.
3. **Dual-Path Architecture** — Python-primary engine + thin, high-fidelity shell.
4. **Event-Sourced + Compaction** — Journal, pending, and major caches must be append-oriented with smart, safe compaction.
5. **Frozen + Versioned Contracts** — All major shapes versioned with migration paths.
6. **Full Observability by Default** — ACS/CIABRE-aware diagnostics on every hot path.
7. **Multi-Agent Safe by Design** — Concurrent agents, daemons, and human edits must not corrupt state.
8. **Harness + Designated External Driven** — Heavy use of harness + RecipeLab + user-designated other external projects. **Wikifier source itself is reserved for M5**.
9. **Explicit Exit Criteria** — Measurable per phase and per workstream.

---

## Phase Structure

### Phase 80-85: M2 Core Feature Completion (Feature Building)

**Agent Allocation**: 8 agents (following the successful pattern of subagents 80–85).

**Goal**: Bring the core M2 feature set (Workstreams A–E) to a solid, implemented, and exercised state. The system must be observably useful and reliable for agent workflows on creative monorepos using the new paths as the normal/default experience.

**Primary Focus Areas** (drawn from long-term scalable plan A-E exits):
- **A (Streaming/Resumable/Partials + Reverse)**: Full end-to-end streaming with safe partials, continuation, reverse as first-class, and basic shell parity.
- **B (Health Durability)**: Reliable stale detection, heal policy, sharded views, and zero flakiness under concurrent load.
- **C (Journal/Compaction/Intent)**: Event-sourced journal with smart compaction, bounded pending, and useful historical intent queries.
- **D (Transparency/ACS+CIABRE)**: First-class low-confidence/unresolved/failure data with rich provenance and explainability.
- **E (v0.4 Thin Library + Protocol + Ergonomics)**: Clean public API, thin MCP/CLI wiring, and usable protocol conformance.

**Allowed Validation Targets**:
- Harness (10k–50k creative generators + deep mode)
- RecipeLab (1637/269)
- User-designated external projects (other than Wikifier itself)

**Forbidden**:
- Sustained autonomous sessions, dogfooding, or primary validation on the Wikifier source tree.

**Exit Criteria for Phase 80-85**:
- All major M2 capabilities have core implementation complete.
- New streaming/partials/reverse paths are the normal/default in library + basic shell usage.
- Health, journal, and transparency surfaces are durable and observable under realistic concurrent load on allowed targets.
- v0.4 thin library surfaces are usable for core agent loops.
- Main remains clean, "3" untouched, and all validation during the phase has stayed strictly on allowed targets (harness + RecipeLab + designated external projects). No `--m2-health --deep` or equivalent heavy self-validation has been run on the Wikifier source tree itself.
- Rich evidence (diaries + artifacts) harvested to `wave-evidence/`.

**Agent Pattern**: One lead per major workstream (A/B/C/D/E) + supporting agents for integration, harness extensions, and real-usage exercising on designated external targets. Follow the 9-step playbook with dual reviewers (new pair recommended).

---

### Phase 86-90: Durability, Observability & Scale Hardening

**Agent Allocation**: 8 agents.

**Goal**: Harden the system for long-term (years-scale) autonomous operation and prove scalability across the full spectrum up to massive creative monorepos.

**Primary Focus Areas**:
- Advanced compaction policies and years-load simulation (journal, pending, caches).
- Richer first-class executive/impact summaries and autonomous session observability (building on 81 prototypes).
- Full scalability testing and optimization on 25k–50k+ synthetic + designated external creative monorepos.
- Multi-agent safety under heavy sustained concurrent load.
- Final durability polish on health, journal, and transparency under extreme conditions.

**Allowed Validation Targets**: Same as previous phase (harness + RecipeLab + user-designated external projects). Still **no Wikifier source dogfood**.

**Exit Criteria for Phase 86-90**:
- System demonstrates strong durability characteristics under simulated years of autonomous multi-agent load.
- Richer observability surfaces are practical and first-class.
- Scalability proven on massive creative workloads (O(changed) behavior holds, bounded state, useful queries).
- All 8/9 guiding principles are visibly upheld in implementation and evidence.
- Main hygiene remains strong, and all validation during the phase stayed strictly on allowed targets (harness + RecipeLab + designated external projects). No heavy self-validation or --m2-health --deep was run on the Wikifier source tree itself.

**Agent Pattern**: Mix of durability/scale specialists + integration agents. Heavy emphasis on long-running simulations and massive monorepo stress. Dual independent reviewers required.

**Prep Status (2026-05-28, subagent_id=PREP-86-05)**: Detailed working checklist (`Findings/m2-86-90-durability-observability-scale-hardening-checklist.md`, 205 lines) and 8 self-contained agent prompts (`Findings/phase-86-90-agent-prompts.md`, 229 lines) created, exactly mirroring the 80-85 structure and iron rules. 
- Explicit M5 dogfood boundary repeated in every section: validation restricted to harness + RecipeLab + user-designated other external projects only. **No Wikifier source dogfood until M5**.
- "3" (original partials continuation 25k creative track) sacred LAST grep hygiene documented in both new artifacts + all 86-01/02/03/05 prep steps (multiple greps performed; current M2 25k–50k streaming/partials/continuation equivalents confirmed untouched in main).
- Focus areas map directly to B2 (health years-load + sustained multi-agent), C2 (journal/compaction scale + historical query durability), D2 (ACS/CIABRE + autonomous session obs at 50k+), X3/X4 (harness longrun years-sim + 50k+ massive creative regression + sustained concurrency), A3/E2 (richer summaries + thin ergonomics durability at massive scale).
- Honest 82–87% toward 95%+ / 0/7 strict 85% preserved. Long-term zero-dep + full scalability spectrum (small to 25k–50k+ creative) first. 9-step + local WTs + rich diaries vs long-term A-E exits + 7-criteria + 8/9 principles required for execution.
- Both new docs reference the long-term scalable plan, 80-85 harvests (as current-state baseline), and explicitly reinforce that no `--m2-health --deep` or equivalent heavy self-validation was performed on the Wikifier source tree during the phase. All gates and validation stayed on allowed targets only.
Ready for user: "Execute 8 sub agents for 86-90" (or adjustments). All rules from the top of this plan upheld.

---

### Phase 91-95: Final Polish & Long-term Exit Closure

**Agent Allocation**: 8 agents.

**Goal**: Close the detailed long-term per-WS A-E 95%+ exit criteria and achieve honest 95%+ "set & forget" readiness per the long-term scalable plan definition.

**Primary Focus Areas**:
- Final closure of all remaining long-term A-E exit criteria (scalability spectrum proof, full observability, complete thin ergonomics, production-grade durability).
- Comprehensive documentation, contracts finalization, and harness completeness.
- End-to-end proof that the architecture supports 5–10+ year autonomous operation on massive creative monorepos.
- Preparation of clean handoff artifacts for M5 (including notes on what M5 dogfooding must still validate).

**Allowed Validation Targets**: Harness + RecipeLab + user-designated external projects. **Still no dogfooding of the Wikifier project itself**.

**Exit Criteria for Phase 91-95**:
- All detailed long-term A-E 95%+ exit criteria are demonstrably met on allowed targets.
- The system is observably solid, scalable, and production-useful across the full spectrum (tiny to massive creative monorepos).
- Honest 95%+ calibration (per long-term plan) with rich evidence catalog.
- Main is clean, all gates passing strongly, "3" untouched.
- Clear M5 readiness package (what has been proven vs. what still requires broad dogfooding in M5).

**Agent Pattern**: Final integration + polish specialists + dedicated evidence/harvest agents. Dual reviewers mandatory. External long-pole artifacts (from designated projects) highest priority in micro order.

---

## Cross-Phase Rules (Mandatory for All M2–M4 Work)

- **No Dogfooding of This Project Until M5**: The Wikifier source tree must not be used as a primary dogfood target, sustained autonomous session target, or final validation target during any M2–M4 phase. Violation of this rule will be treated as a serious process breach.
- **"3" Untouched**: Explicit `grep` for the protected test **as the absolute last step** before every content write + final verification. Only historical references + the isolated subagent-3 worktree copy are allowed.
- **Zero New Dependencies**: Pure stdlib + existing patterns only.
- **9-Step Hygiene-First**: Local-only worktrees, small safe micro-batches, full `--m2-health --deep` gate on source before any main consideration, dual independent reviewers, evidence to `wave-evidence/`, honest diaries.
- **Real Usage on Designated Targets Only**: Harness + RecipeLab + user-provided other external projects are the allowed vehicles for real-usage feedback and exercising.
- **Scalability & Long-Term First**: Every deliverable must address the full spectrum and long-term viability principles.
- **Evidence & Transparency**: All work produces rich, harvestable artifacts and honest calibration against the long-term exits (not the old strict 85% 7-criteria during building phases).

---

## Sequencing & Agent Deployment

1. **Complete current 80-85 phase work** (if any remaining items) following the rules above.
2. **Phase 86-90**: Launch next group of 8 agents with the durability/scale charter.
3. **Phase 91-95**: Launch final group of 8 agents with the exit-closure charter.
4. Only after honest 95%+ per this plan and the long-term scalable plan do we enter M5 (broad dogfooding, including this project).

---

## References

- `Findings/m2-full-closure-longterm-scalable-plan.md` (source of 8/9 principles + detailed A-E 95%+ exits)
- `Findings/Milestones-Overview.md` (high-level milestone framing)
- `Findings/m2_rem_08_and_v0.4_progress_tracker.md` (current status)
- All prior wave evidence in `Findings/wave-evidence/`

This plan replaces the previous literal 3-7d external long-pole as the sole highest-priority item during M2–M4 feature building. The focus is now disciplined, long-term, zero-dep, scalable feature completion without using the Wikifier project itself as dogfood until M5.

**Detailed Execution Guide for Phase 80-85**:
Use `Findings/m2-80-85-feature-completion-checklist.md` as the working checklist. It breaks down remaining work per A–E workstream, with current state (post recent real-usage swarm), specific tasks, validation targets (harness + RecipeLab + user-designated external projects only), and suggested 8-agent allocation.

**Phase 80-85 Live Status (as of 2026-05-28)**: 7/8 agents complete (E1: thin-shell + v0.4; X2: harness cross-cutting; D1: transparency/ACS+CIABRE; B1: health durability; X1: harness cross-cutting; A2: richer summaries + reverse; A1: streaming shell parity + richer summary default + reverse first-class in both shells; see harvests `wave-evidence/phase6-80-85-*-completion.txt`). Only C1 (journal/compaction) still running. All rules (no dogfooding Wikifier until M5, "3" sacred, 9-step) upheld.

**Subagent ID discipline, "3" sacred, and full 9-step hygiene apply to every phase.**