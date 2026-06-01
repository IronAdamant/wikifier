# M3 – Agent Interface & Ergonomics Checklist & Progressive Milestones

**Created**: 2026-05-29  
**Status**: Draft – ready for review and execution  
**Purpose**: Actionable breakdown of the M3 plan with clear definitions of done at progressive levels of completeness (20% → 95% on the feature-building / long-term usefulness lens). Designed for agent swarm execution with the same discipline used in M2.

---

## Core Constraints (Non-Negotiable for All M3 Work)

- **Feature creation, addition, and refinement only** (M2–M4 style). This is not M5.
- **No dogfooding on the Wikifier project itself**. All serious validation, stress testing, and real-usage work must use:
  - Harness (extended M2/M3 suites)
  - RecipeLab
  - User-designated external creative monorepos
- Long-term focus + full scalability spectrum first (tiny scripts → 50k+ creative monorepos with barrels, dynamic imports, workspaces, symlinks).
- Actual usefulness close to 95% on the feature-building lens (quality, completeness, and long-term viability under the 9 Guiding Principles).
- Zero new dependencies (pure stdlib + existing patterns).
- Rich, harvestable evidence (diaries, conformance artifacts, metrics) against explicit criteria.
- Honest calibration toward 95% usefulness. No overclaim.

---

## Major Work Areas for M3

1. **Polished Public Library Surface** (Primary agent experience)
2. **Rigorous, Testable Agent Protocol (v0.4+ and successors)**
3. **Long-Running Autonomous Agent Ergonomics**
4. **Thin Consumers as First-Class Delegates**
5. **Agent-Builder Documentation & Patterns**

---

## Recommended Execution Model

Continue the proven high-discipline approach:
- Use **6–8 agent swarms** for larger sub-phases (similar to 80-85 / 86-90).
- Smaller focused teams or single agents + review for targeted micro-batches.
- Isolated persistent original-path worktrees.
- `subagent_id=86-XXX` (or new M3 numbering) in 100% of commits, diaries, and artifacts.
- FRESH LAST "3" hygiene before any harness/source changes.
- Rich local diaries with verbatim mappings to this checklist, the 9 Guiding Principles, and long-term exits.
- External long-pole priority on allowed targets (RecipeLab + designated externals).
- Dual review on significant batches.

---

## Progressive Definitions of Done

These percentages are on the **M3 feature-building / long-term usefulness lens** (quality and completeness under the 9 Guiding Principles + contribution to overall 95% agent usefulness). They are **not** final M5 dogfood scoring.

### 20% – Foundations & Direction Locked
- M3 plan and this checklist reviewed and approved.
- Core vision, constraints, and 5 work areas clearly documented and socialized.
- Initial public API surface audit completed (what exists today in `from wikifier import ...`).
- v0.4 protocol (skills/run.md) reviewed for gaps against long-running autonomous agent needs.
- First agent swarm (or small team) launched on the highest-leverage early work (likely library surface + protocol baseline).
- All work following no-dogfood / allowed-targets rule.

**Agent Swarm Role**: 1 small team (3–4 agents) for discovery + initial direction setting. Heavy documentation and planning output.

### 40% – Core Surfaces & Protocol Baseline Working
- Stable initial public library surface defined (`__all__`, primary happy-path functions clearly documented).
- Most common autonomous agent loop (check → edit → record_change → mark_green) made significantly more ergonomic in the library.
- v0.4 protocol updated with clearer mandatory behaviors for long-running agents.
- Basic versioning story started for library objects and protocol messages.
- First conformance ideas / test hooks prototyped.
- Early evidence on harness + RecipeLab that the new surfaces work for simple autonomous loops.
- Thin consumers (CLI/MCP) updated to stay in parity with library changes.

**Agent Swarm Role**: Full 6–8 agent swarm on "Library Surface Foundation" + "Protocol Baseline" sub-phase.

**Definition of Done at 40%**: An agent can start using the library for basic autonomous work with noticeably better ergonomics than today, and the protocol has clear "this is the expected loop" guidance.

### 60% – Solid Ergonomics + Versioning + Initial Conformance
- Public library surface feels polished and opinionated for agent use (excellent defaults, strong typing/docstrings, clear error modes).
- Core autonomous loop is low-friction and high-signal for days/weeks of operation.
- Protocol (v0.4 or v0.5) has initial machine-checkable conformance tests or strong harness validation.
- Versioning model for library + protocol is defined and partially implemented.
- Thin consumers are demonstrably excellent thin delegates (strong parity tests passing).
- Agent-builder documentation and examples exist for the happy path across scale tiers (small → massive).
- Evidence on allowed targets (including at least one external creative monorepo) showing the interface is usable for multi-day autonomous runs.

**Agent Swarm Role**: 6–8 agent swarm(s) on "Ergonomics & Versioning" + "Protocol Conformance v1" + "Documentation & Examples".

**Definition of Done at 60%**: An agent (or small swarm) can comfortably run for multiple days on medium-to-large projects using the new interface with minimal friction. The protocol feels like a real contract rather than guidance.

### 80% – Production-Ready for Long-Running Agents at Scale
- Library + protocol support excellent long-running autonomous operation (weeks/months) with strong observability and recovery stories.
- Full support for the multi-agent + daemon + occasional human concurrent model.
- Conformance testing is robust and part of the harness.
- Versioning and migration paths are complete and tested.
- Thin consumers remain first-class and are the recommended thin entry points.
- Comprehensive agent-builder documentation + patterns exist for tiny → massive creative monorepos.
- Strong evidence on harness (including heavy 25k–50k+ creative stress) + RecipeLab + at least one additional user-designated external creative monorepo that the M3 interface is production-useful for autonomous agents.
- All 9 Guiding Principles visibly upheld in the delivered interface (especially scalability, zero new deps, dual-path, observability, multi-agent safety, and versioning).

**Agent Swarm Role**: One or more 6–8 agent swarms focused on "Long-Running Excellence", "Scale Validation", "Conformance Hardening", and "Final Polish".

**Definition of Done at 80%**: The M3 interface is the clear, recommended way for agents to interact with Wikifier. It has been meaningfully exercised at scale on allowed targets with positive results. Remaining work is polish and final exit evidence rather than foundational gaps.

### 90–95% – Full M3 Exit Criteria Met (Ready for M4/M5 Handoff)

- Every item in the M3 exit criteria (see below) is demonstrably met with rich evidence.
- The public library + protocol are observably solid, scalable, and production-useful across the full spectrum on allowed targets.
- Clean handoff artifacts exist (documentation, migration guides, known limitations, what M5 must still validate).
- Honest calibration at 90–95% on the feature-building usefulness lens (under the 9 Guiding Principles and contribution to overall long-term 95% agent usefulness).
- All work done without dogfooding the Wikifier project itself.

**Agent Swarm Role**: Final integration + evidence + documentation swarm (6–8 agents) + dedicated review.

---

## Detailed Checklist (Mapped to Milestones)

### Work Area 1: Polished Public Library Surface

- [ ] Initial public API audit and proposed stable surface (20%)
- [ ] Core autonomous loop (check → record → mark) made ergonomic in library (40%)
- [ ] Stable `__all__` + excellent docstrings + typing for primary surfaces (60%)
- [ ] Strong defaults + clear error modes + recovery helpers for long-running use (80%)
- [ ] Full support for scale tiers (tiny → massive creative) with good ergonomics (80–90%)
- [ ] Rich structured + human-readable dual outputs by default (80%)
- [ ] Complete and stable public surface with migration guarantees (90–95%)

### Work Area 2: Rigorous, Testable Agent Protocol

- [ ] v0.4 protocol reviewed and gaps documented against long-running needs (20%)
- [ ] Updated protocol with clearer mandatory behaviors (40%)
- [ ] Initial conformance test hooks / harness validation (40–60%)
- [ ] Robust, machine-checkable conformance suite integrated with harness (80%)
- [ ] Versioning model for protocol messages with migration support (60–80%)
- [ ] Protocol feels like a real, enforceable contract for autonomous agents (80–90%)
- [ ] Full protocol + conformance story complete and evidenced (90–95%)

### Work Area 3: Long-Running Autonomous Agent Ergonomics

- [ ] Happy-path loop validated for multi-day runs on allowed targets (40–60%)
- [ ] Excellent observability and diagnostics surfaced for agents (60%)
- [ ] Recovery stories and error modes designed for long-running autonomous use (60–80%)
- [ ] Strong support for concurrent agents + daemon + human model (80%)
- [ ] Ergonomics proven comfortable for weeks/months of operation at scale (80–90%)
- [ ] All long-running patterns documented and evidenced on allowed targets (90–95%)

### Work Area 4: Thin Consumers as First-Class Delegates

- [ ] CLI and MCP updated to stay in parity during library/protocol changes (ongoing)
- [ ] Strong automated parity tests between library and thin consumers (60%)
- [ ] Thin consumers feel like excellent, high-fidelity thin shims (80%)
- [ ] Documentation clearly positions when to use library vs thin consumers (80–90%)
- [ ] Thin consumers fully aligned and evidenced as first-class (90–95%)

### Work Area 5: Agent-Builder Documentation & Patterns

- [ ] Agent-first documentation strategy defined (20–40%)
- [ ] Happy-path examples for small/medium/large/massive projects (60%)
- [ ] Long-running autonomous patterns + "how to be a good citizen" guidance (80%)
- [ ] Comprehensive, high-quality agent-builder docs + examples across scale tiers (90–95%)

---

## M3 Exit Criteria (90–95% Definition of Done)

M3 is complete when **all** of the following are demonstrably true on allowed targets (harness + RecipeLab + user-designated external creative monorepos):

1. There is a small, stable, well-documented public Python library that is the primary recommended interface for agents.
2. There is a rigorous, versioned, conformance-testable Agent Protocol that clearly defines expected behavior for autonomous agents.
3. The most common long-running autonomous agent loop is low-friction, high-signal, and observably reliable for weeks/months of operation.
4. The library + protocol work excellently across the full scalability spectrum (tiny scripts to 50k+ creative monorepos).
5. Thin consumers (CLI/MCP) are excellent, high-fidelity thin delegates with strong parity.
6. Rich evidence exists (including heavy scale stress on allowed targets) that the M3 interface is production-useful for autonomous agents and swarms.
7. All work was executed under the 9 Guiding Principles with zero new dependencies and no dogfooding on the Wikifier project itself.
8. Clean handoff artifacts exist for M4/M5 (including what still needs broad dogfooding in M5).

---

## Recommended First Execution Steps

1. Review and approve this checklist + the parent M3 plan.
2. Launch first agent swarm (6–8 agents) focused on 20% → 40% milestones (primarily Work Areas 1 + 2 baseline).
3. Produce rich local diaries + evidence against the 20%/40% definitions of done.
4. Dual review + harvest before moving to the 40% → 60% swarm(s).

All the usual high-discipline practices apply (isolated worktrees, subagent_ids, FRESH "3" hygiene where relevant, rich evidence, honest tracking, external long-pole priority on allowed targets).

---

**This checklist turns the M3 plan into an executable, measurable program while preserving the long-term, scalability-first, no-shortcuts philosophy that has served the project well.** 

Ready for review and first swarm launch.