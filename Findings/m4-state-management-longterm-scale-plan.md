# M4 – State Management & Long-Term Scale Plan

**Created**: 2026-06-02 (immediately after M3 80-95% completion, central handoff push, and README/Milestones update)
**Status**: Draft for review and execution
**Owner**: M4 Program
**Related Documents**:
- `Findings/M3-80-95-Completion-Package-Handoff.md` (explicit prioritized recommendations for M4)
- `Findings/Milestones-Overview.md`
- `Findings/m3-agent-interface-ergonomics-plan.md` and `m3-agent-interface-ergonomics-checklist.md`
- `Findings/m3-03/M3-03-LONG-TERM-LENS-DIARY.md` (8-step Decision Framework + full 9 Guiding Principles)
- `Findings/m2-full-closure-longterm-scalable-plan.md` (M2 Core Promise and long-term exits)
- The 9 Guiding Principles (verbatim in m3-03 and M3 handoff)

---

## 1. M4 Definition

**M4 – State Management & Long-Term Scale**

**Primary Focus**:
- Advanced, durable state management (journal, compaction, pending, health, caches) engineered for years-scale autonomous operation.
- Full resilience and bounded behavior on massive creative monorepos (50k+ files with heavy barrels, dynamic/conditional imports, workspaces, symlinks, high churn, and sustained concurrent agent + daemon + human load).
- Richer, long-horizon observability and diagnostics that remain useful over months and years.
- Long-term evolution policies (versioning, migration, compatibility) that keep the system pleasant and stable for 5–10+ years of agent and LLM progress.

This phase completes the durability foundations from M2 and the ergonomic surfaces from M3 into a system that can genuinely run "set & forget" for years on the hardest real-world targets.

---

## 2. Vision – How M4 Contributes to "Actual Usefulness Close to 95%"

The Core Promise from M2 (refined through M3):

> An agent (or swarm) can maintain a high-fidelity, low-ambiguity, incrementally-updatable map of any codebase over months/years — with bounded state, actionable diagnostics, first-class semantic intent logging, and query surfaces that remain fast and useful at scale.

M3 made the interface delightful and first-class for agents. **M4 makes the underlying state durable and trustworthy for the long haul.**

Without excellent long-term state management, even the best library and protocol will eventually suffer from unbounded growth, mysterious drift, unrecoverable compaction failures, or observability that goes dark after weeks of autonomous operation.

M4 must deliver explicit, production-grade answers for the full scalability spectrum, with the hardest cases (50k+ creative monorepos under sustained high-churn concurrent load) as the primary design driver. Tiny and medium cases must remain zero-ceremony and fast.

Long-term focus is non-negotiable: every design decision must be evaluated for 5–10+ year viability under realistic agent evolution.

---

## 3. Alignment to the 9 Guiding Principles (Zero-Dep Lens Highlighted)

M4 must visibly advance all nine principles, with **especially strong emphasis** on:

1. **Scalability Spectrum First** — Explicit, tested answers for Tiny (<100 files) through Massive 50k+ creative (barrels + dyn/cond imports + workspaces + symlinks + high churn + partials/"3" under years-scale concurrent load). The 50k+ creative case drives the design.
2. **Zero-Dependency + Portable** (PRIMARY LENS FOR M4) — All new state, compaction, health, and observability logic must be pure stdlib or existing patterns. No new runtime dependencies. Any necessary algorithms (e.g., advanced compaction strategies) may be implemented directly if it preserves the zero-dep contract. Thin, portable packaging remains sacred.
3. **Dual-Path Architecture** — State and compaction engines remain Python-primary and authoritative; thin shells (CLI/MCP) continue as high-fidelity delegates.
4. **Event-Sourced + Compaction Where Appropriate** — This is M4's core. Journal, pending state, health records, and major caches must use append-oriented designs with safe, reversible, bounded compaction that works for years of continuous autonomous operation.
5. **Frozen + Versioned Contracts** — Extend M3 versioning to all long-term state shapes (journal events, compaction manifests, health histories, session traces). Clear migration paths and detection for long-lived installations.
6. **Full Observability by Default** — Every hot path in state management, compaction, healing, and long-running sessions must produce rich, queryable, ACS/CIABRE-aware diagnostics that remain useful after months/years of data.
7. **Multi-Agent Safe by Design** — Years-scale concurrent operation (multiple autonomous agents + background daemons + occasional humans) must never corrupt state or lose intent. Locking, sharding, and conflict resolution must be production-hardened at 50k+ creative scale.
8. **Harness + Designated External Driven** — All serious validation and evidence during M4 uses only the harness (extended M3/M4 suites), RecipeLab, and user-designated external creative monorepos. No sustained dogfood on the Wikifier project itself until M5.
9. **Explicit Exit Criteria** — Measurable "good enough for production long-term" criteria with honest calibration.

**Zero-Dependency Mandate (repeated for emphasis)**: M4 will not introduce any new Python packages for its core contributions. All compaction algorithms, state sharding, long-term health policies, and observability enhancements must be implementable with the Python standard library + the existing Wikifier patterns established in M2/M3. This is a hard constraint and primary evaluation lens for every Work Area.

---

## 4. Current State (as of M3 80-95% Completion)

**Strengths (Foundations from M2 + M3)**:
- Event-sourced journal with smart compaction hooks (M2 Workstream C).
- Bounded pending state and sharded health views (M2 Workstream B).
- Proven real usage data from 80-85/86-90 swarms on 5k+ creative targets under long-load chaos (including partials/"3" at scale).
- M3 surfaces (library + protocol) now make long-running autonomous loops ergonomic and conformance-testable.
- Versioned contracts (M3) provide a path for long-term evolution.
- Rich ACS/CIABRE observability patterns already proven.

**Gaps / Opportunities for M4**:
- Compaction policies are still relatively simple; not yet proven for years of continuous high-churn 50k+ creative operation.
- State growth, recovery after extended autonomous runs, and "what happens after 6–18 months of uninterrupted agent activity" are under-explored.
- Observability is excellent for days/weeks but needs hardening for months/years of historical querying and trend analysis.
- Concurrent MA + daemon + human safety at extreme scale and duration needs deeper stress and formalization.
- Long-term migration/compatibility story for state formats is incomplete.
- Evidence for "years-scale" claims is still proxy-based (long sims + multi-week real runs); literal multi-month autonomous validation on 50k+ creative targets is M5 territory but M4 must prepare the ground.

---

## 5. Major Work Areas for M4

### 5.1 Advanced Journal, Compaction & Intent for Years-Scale

- Production-grade, reversible compaction policies that remain bounded and correct after years of continuous append-only operation on 50k+ creative monorepos.
- Intent/query surfaces that stay fast and useful over very long time horizons.
- Safe, observable compaction under concurrent load.

### 5.2 Extreme-Scale State Management & Boundedness (50k+ Creative)

- All internal state (caches, health, pending, session traces, reverse dependencies) must remain O(changed) or better even on the hardest 50k+ creative workloads with high churn and heavy use of partials/"3".
- Explicit handling of barrels + dynamic/conditional imports + workspaces + symlinks at long-term scale.
- Memory, disk, and token bounds that agents can rely on for months/years.

### 5.3 Long-Term Health, Healing & Resilience

- Health and healing policies proven under sustained autonomous + concurrent MA/daemon/human load for extended periods.
- Recovery stories after extended runs, partial failures, or external chaos.
- "Good citizen" guarantees for the Wikifier-managed codebase over years.

### 5.4 Richer Observability, Diagnostics & Query Surfaces for Long Runs

- Long-horizon diagnostics, trend analysis, and "what happened over the last 3 months" query capabilities.
- ACS/CIABRE and session aggregates hardened for years-scale data volumes.
- Actionable signals that remain useful when an agent has been running autonomously for months.

### 5.5 Long-Term Versioning, Migration & Compatibility Policy

- Comprehensive policy and implementation for evolving all long-lived state shapes (journal, compaction manifests, health histories, etc.).
- Easy detection and graceful migration for installations that have been running for years.
- Backwards compatibility guarantees that support the 5–10+ year vision.

### 5.6 M4 Validation Harness, Evidence Strategy & Clean M5 Handoff

- Extended harness suites that can stress years-scale scenarios (accelerated time, chaos, sustained concurrent load on 25k–50k+ creative generators).
- Rich evidence requirements on allowed targets only (harness + RecipeLab + designated externals).
- Clean handoff artifacts (documentation of known long-term limitations, migration guides, what M5 must still dogfood at literal multi-month scale).

---

## 6. Execution Philosophy & Constraints (Non-Negotiable)

**Same (or stricter) discipline as M2–M4**:

- **Focus**: Feature creation, addition, and refinement only. This is not M5.
- **No dogfooding on the Wikifier project itself** until M5. All serious validation, stress, and real-usage work during M4 must use:
  - The harness (extended M3/M4 suites exercising long-term state/compaction/observability on 25k–50k+ creative generators)
  - RecipeLab
  - User-designated external creative monorepos (5k–50k+ with target patterns)
- **Zero new dependencies** (pure stdlib + existing patterns is the hard primary constraint for all new code in this phase).
- **"3" sacred** (original partials continuation track + test_partial_continuation_workflow_25k at harness ~3109) remains absolute last and untouched. Explicit FRESH LAST grep (0 def matches on active non-guardian code and planned write paths) required before any write that touches journal/partials/continuation-related areas. Only safe historical citation allowed in docs and examples.
- **8-step Decision Framework** (from m3-03) + anti-patterns applied to every significant decision.
- **Long-term + full scalability spectrum first** in every design (tiny scripts must stay delightful; 50k+ creative with all patterns is the forcing function).
- **Rich, harvestable evidence** (diaries, conformance artifacts, long-term metrics, compaction correctness proofs) against explicit exit criteria.
- Honest calibration toward 95% usefulness on the long-term feature-building lens.
- Subagent swarms (6–8 agents per major segment) with isolated worktrees, subagent_id in 100% of output, rich local diaries with verbatim mappings to this plan, the 9 GPs, and long-term exits.
- Central handoff packages at phase gates (modeled on M3 C8/B8 style).
- Main source 100% clean until M5.

---

## 7. Proposed Phased Approach (High Level)

**Phase M4-A: Compaction & Journal Durability Foundation**
- Advanced, reversible compaction policies for years-scale.
- Hardened intent and historical query surfaces.

**Phase M4-B: Extreme-Scale State & Boundedness**
- 50k+ creative monorepo resilience (all target patterns + high churn + partials/"3" + concurrent load).
- Proven memory/disk/token bounds under sustained autonomous operation.

**Phase M4-C: Long-Term Observability & Resilience**
- Rich diagnostics and trend analysis for months/years.
- Health/healing/recovery stories hardened for long autonomous + concurrent scenarios.

**Phase M4-D: Versioning Policy, Harness Extensions & M5 Handoff Prep**
- Complete long-term versioning/migration story.
- Extended validation harness + rich evidence on allowed targets.
- Clean handoff artifacts for M5.

Each sub-phase can (and should) use the proven 6–8 agent swarm pattern with identical strict hygiene, zero-dep, and allowed-targets rules.

---

## 8. Exit Criteria for M4 (Draft)

M4 can be considered feature-complete when:

- Journal, compaction, and all major long-lived state structures are demonstrably safe, bounded, and correct after years-scale simulated + multi-week real autonomous operation on 50k+ creative targets with target patterns.
- The system provides rich, useful observability and recovery stories for months/years of continuous autonomous + concurrent MA/daemon/human operation.
- Long-term versioning and migration policy is complete, implemented, and tested.
- Strong evidence exists on the harness (extended long-term suites) + RecipeLab + at least one additional designated external 50k+-scale creative monorepo.
- All 9 Guiding Principles are visibly upheld, with particular strength on #1 (spectrum), #2 (zero-dep as primary lens), #4 (advanced compaction), #5 (versioned long-term state), #6 (long-horizon obs), and #7 (years-scale MA safety).
- Clean, harvestable handoff artifacts exist that clearly delineate what M5 must still validate at literal multi-month autonomous scale on real user projects.

**M5 Boundary Reminder**: M4 delivers the technical capability and evidence on allowed targets. Literal broad, long-duration dogfooding on the user's prepared real-world projects is reserved exclusively for M5.

---

**subagent_id placeholder for planning coordination**: m4-planning-coord (will be used in all artifacts, commits, and diaries for this phase).

All content respects the iron rules, the M5 boundary, zero new dependencies as a primary constraint, and the requirement for honest, long-term-focused planning before any execution swarms begin.