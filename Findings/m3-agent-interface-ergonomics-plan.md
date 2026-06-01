# M3 – Agent Interface & Ergonomics Plan

**Created**: 2026-05-29 (immediately after declaring M2 sufficiently advanced post-86-90 deeper wave)
**Status**: Draft for review and execution
**Owner**: M3 Program
**Related Documents**:
- `Findings/Milestones-Overview.md`
- `Findings/m2-full-closure-longterm-scalable-plan.md` (especially Workstream E and the Core Promise)
- `skills/run.md` (current v0.4 Agent Protocol)
- `Findings/m2-phased-to-95-agent-plan.md`
- The 9 Guiding Principles (long-term scalable plan)

---

## 1. M3 Definition

**M3 – Agent Interface & Ergonomics**

**Primary Focus**:
- A clean, versioned, delightful public Python library (`from wikifier import ...`)
- A rigorous, testable, versioned Agent Protocol (v0.4 and successors)
- Excellent ergonomics for autonomous agents (and agent swarms) operating over long periods

Thin consumers (CLI and MCP server) are important and must remain excellent, but they are **secondary** to the library and protocol being first-class.

**Rule (carried forward)**: No heavy claims of M3 completion until M2 is considered stable enough that the interface has something solid to expose.

---

## 2. Vision – How M3 Contributes to "Actual Usefulness Close to 95%"

The Core Promise of completed M2 (from the long-term plan) is:

> An agent (or swarm) can maintain a high-fidelity, low-ambiguity, incrementally-updatable map of any codebase over months/years — with bounded state, actionable diagnostics, first-class semantic intent logging, and query surfaces that remain fast and useful at scale.

M3 exists to make that promise **actually usable** by real agents in practice.

Even a perfect M2 engine is only ~60-70% of the value if the interface is clumsy, error-prone, or requires constant human babysitting. M3 closes the gap between "the engine exists" and "an agent can reliably drive it for months on massive creative monorepos with minimal drama."

M3 must deliver on the full scalability spectrum:
- Tiny scripts (fast startup, minimal ceremony)
- Medium projects
- Large monorepos
- Massive creative monorepos (50k+ files, heavy barrels, dynamic imports, workspaces, symlinks)

Long-term focus is mandatory: the interface and protocol must be designed to remain pleasant and stable for 5–10+ years of agent evolution, not just the next LLM release.

---

## 3. Alignment to the 9 Guiding Principles

M3 must visibly advance (not regress) all nine principles, with particular emphasis on:

1. **Scalability Spectrum First** — The library and protocol must feel natural from 50-file scripts to 50k+ creative monorepos.
2. **Zero-Dependency + Portable** — No new runtime dependencies for the public surface.
3. **Dual-Path Architecture** — Python library is the authoritative engine; thin shell (CLI/MCP) remains an excellent, high-fidelity thin wrapper.
4. **Event-Sourced + Compaction** — Protocol should make the intent/journal story natural for agents.
5. **Frozen + Versioned Contracts** — Library objects and protocol messages must be versioned with clear migration paths.
6. **Full Observability by Default** — Every major library call and protocol interaction should be rich in diagnostics by default.
7. **Multi-Agent Safe by Design** — The interface must not create new hazards when multiple agents (plus humans + daemons) operate concurrently.
8. **Harness + Designated External Driven** — All serious validation during M3 uses the harness, RecipeLab, and user-designated external projects only.
9. **Explicit Exit Criteria** — M3 must have measurable "good enough for production" criteria.

---

## 4. Current State (as of end of 86-90)

**Strengths**:
- Substantial public surface already exists (`health`, `record_change`, `mark_green`, `update_maps`, `run_full_update`, `suggest_next_actions`, etc.).
- v0.4 Agent Protocol exists in `skills/run.md` and is actively used.
- Contracts v1 and rich data shapes are in place.
- Python-primary path (`run_full_update`) is real and hardened for external use.
- Some real usage demonstrated in Phase 85.

**Gaps / Opportunities for M3**:
- The library surface is still somewhat "implementation leakage" rather than a polished, opinionated agent API.
- Protocol (v0.4) is prescriptive but not yet rigorously conformance-testable in a machine-checkable way.
- Error modes and recovery stories for long-running autonomous agents are underdeveloped.
- Versioning story for both the library objects and the protocol messages is incomplete.
- Documentation and examples are still heavily human-oriented rather than agent-builder-oriented.
- The "mandatory happy path" for autonomous agents (the record_change → update wiki → mark_green loop) can still be made lower-friction and higher-signal.
- Thin consumers (especially the shell) sometimes feel like afterthoughts rather than first-class thin delegates to the library.

---

## 5. Major Work Areas for M3

### 5.1 Polished Public Library Surface (Primary)

- Define a small, stable, high-signal public API surface (`__all__` + clear docs).
- Make the most common autonomous agent loop (check → edit → record → mark) extremely ergonomic.
- Provide excellent structured + human-readable dual outputs by default.
- Strong typing + rich docstrings aimed at agent builders and static analysis.

### 5.2 Rigorous, Testable Agent Protocol (v0.4+)

- Turn `skills/run.md` into a machine-checkable conformance suite (or at minimum a very strong test harness).
- Define clear protocol versions with migration rules.
- Make "mandatory behaviors" (record_change after edits, health discipline, Red/Yellow priority, etc.) enforceable and observable.
- Add conformance test hooks that agents and harnesses can use.

### 5.3 Long-Running Autonomous Agent Ergonomics

- Design for days/weeks/months of continuous operation by one or more agents.
- Excellent defaults for the common case while still allowing power users.
- Clear, actionable error modes and recovery guidance written for agents.
- First-class support for the "agent + monitor daemon + occasional human" concurrent model.

### 5.4 Versioning & Contracts

- Version the public library objects and protocol messages (building on contracts v1).
- Provide clear stability guarantees and deprecation paths.
- Make it easy for agents to detect and adapt to version differences.

### 5.5 Thin Consumers as First-Class Thin Delegates

- CLI and MCP must remain excellent thin shims over the library.
- They should never feel like second-class citizens, but they should not duplicate core logic.
- Strong parity testing between library and thin consumers.

### 5.6 Documentation & Examples for Agent Builders

- Agent-first documentation (not just human-first).
- High-quality examples and patterns for long-running autonomous operation.
- Clear guidance on "how to be a good citizen" in a Wikifier-managed codebase.

---

## 6. Execution Philosophy & Constraints (Non-Negotiable)

**Same discipline as M2-M4**:

- **Focus**: Feature creation, addition, and refinement only.
- **No dogfooding on the Wikifier project itself** until M5. All serious validation, stress, and real-usage work during M3 must use:
  - The harness (especially extended M2/M3 suites)
  - RecipeLab (and other user-designated external creative monorepos)
- **Zero new dependencies** (pure stdlib + existing patterns).
- **"3" sacred** (original partials continuation track) remains absolute last and untouched if any harness changes are made.
- **9-step hygiene** (or equivalent lightweight version) for significant changes.
- **Long-term + scalability spectrum first** in every design decision.
- **Rich, harvestable evidence** (diaries, test results, conformance artifacts) against explicit exit criteria.
- Honest calibration toward 95% usefulness on the feature-building lens.

We will continue using groups of agents (likely 6–8 per major sub-phase) with isolated worktrees, subagent_ids, rich local diaries, and dual review where appropriate.

---

## 7. Proposed Phased Approach (High Level)

**Phase M3-A: Library Surface & Ergonomics Foundation**
- Define and stabilize the primary public API.
- Make the core autonomous loop (check → edit → record → mark) dramatically more pleasant.
- Strong documentation and examples aimed at agent builders.

**Phase M3-B: Rigorous Protocol & Conformance**
- Evolve v0.4 into a properly testable protocol.
- Build conformance harness/tests.
- Versioning story for protocol messages.

**Phase M3-C: Long-Running & Multi-Agent Excellence**
- Hardening for days/weeks/months of continuous autonomous operation.
- Excellent concurrent agent + daemon + human stories.
- Observability and diagnostics that agents actually use.

**Phase M3-D: Thin Consumers Parity + Final Polish**
- Ensure CLI and MCP are outstanding thin delegates.
- Final integration, documentation, and exit criteria evidence.

Each sub-phase can use the proven 6–8 agent swarm pattern with the same strict hygiene rules.

---

## 8. Exit Criteria for M3 (Draft)

M3 can be considered feature-complete when:

- There is a small, stable, well-documented public Python library that agents can use as their primary interface.
- There is a rigorous, versioned, conformance-testable Agent Protocol that clearly defines mandatory and recommended behaviors.
- The most common long-running autonomous agent loop is low-friction, high-signal, and observably correct by default.
- The library + protocol work excellently across the full scalability spectrum (tiny → massive creative) on allowed targets.
- Thin consumers (CLI/MCP) are excellent, high-fidelity thin delegates with strong parity.
- Rich evidence exists (harness + RecipeLab + designated externals) that the interface is production-useful for autonomous agents.
- All work was done under the 9 Guiding Principles with zero new dependencies and no dogfooding on the Wikifier source itself.

---

## 9. Relationship to Overall 95% Usefulness

M3 is one of the highest-leverage phases for "actual usefulness."

A 94% M2 engine behind a clunky or brittle interface is far less valuable than a 90% M2 engine behind a delightful, reliable one. M3 is where we turn the powerful M2 foundation into something agents actually *want* to use for months at a time on massive creative monorepos.

Getting M3 right is a major step toward the real-world 95% the user ultimately cares about.

---

**Next Step**: Review this plan. Once approved, we can break it into detailed checklists and begin the first M3 sub-phase using the same high-discipline agent swarm approach that served us well in 80-95. 

All the usual constraints remain in force: long-term thinking, full scalability spectrum, zero new dependencies, no dogfooding on the Wikifier project itself, honest tracking toward 95% usefulness on the feature-building lens.