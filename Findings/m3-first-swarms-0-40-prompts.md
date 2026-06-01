# M3 First Swarms: 0% → 20% and 20% → 40% Agent Prompts

**Created**: 2026-05-29  
**Purpose**: Ready-to-use prompts for the first two M3 execution segments.  
**Rules (non-negotiable in every prompt and every agent's work)**:

- M2–M4 = Pure Feature Addition Phases Only. No dogfooding of the Wikifier project itself until M5.
- All real usage, stress, and validation during M3 must be restricted exclusively to: the harness, RecipeLab, and user-designated external projects only.
- During M3, "actual 95%" refers only to the quality, completeness, and long-term viability of the features being built (under the 9 Guiding Principles).
- "3" (original partials deep proof track) is absolute last and untouched — explicit LAST grep on the harness before every content write that touches source/harness.
- Zero new dependencies (pure stdlib throughout).
- Follow the full 9-step hygiene-first discipline on every batch.
- subagent_id in 100% of commits, diaries, headers, and harvests.
- Rich local diary in your WT mapping every action directly to this checklist, the 9 Guiding Principles (full text), long-term exits, and honest calibration.
- Long-term focus + full scalability spectrum (tiny scripts → 50k+ creative monorepos) first in every decision.
- Honest calibration toward 95% usefulness on the feature-building lens.

---

## Phase M3-0-20: Foundations & Direction Locked

**Goal**: Lock direction, complete initial audits, and set up the highest-leverage early work so the 20-40% swarm can execute efficiently.

**Recommended Swarm Size**: 4–6 agents (smaller than full phase because this is heavy discovery + planning).

### Agent Roles for 0-20% Swarm

**M3-01 – Library Surface Auditor (Lead for Work Area 1)**
- Perform a complete audit of the current public Python library surface (`from wikifier import ...`).
- Identify what is currently exposed vs what should be in a polished M3 public API.
- Produce a clear proposal for the stable 20% library surface (core functions, objects, and happy-path loop).
- Map every proposal back to the 9 Guiding Principles and scalability spectrum.
- Deliver rich evidence + recommendations in WT diary.

**M3-02 – Protocol Auditor (Lead for Work Area 2)**
- Deep review of current `skills/run.md` (v0.4) against long-running autonomous agent needs.
- Identify gaps in mandatory behaviors, error handling, long-running support, and observability.
- Propose concrete updates needed for the 20-40% protocol baseline.
- Ensure proposals align with versioning and conformance goals.

**M3-03 – Scalability & Long-Term Lens Lead**
- Review all current M3 proposals through the lens of the full scalability spectrum (tiny → massive creative).
- Identify any designs that would create future debt at 50k+ scale.
- Produce explicit guidance for the 20-40% swarm on how to keep long-term viability first.

**M3-04 – Evidence & Planning Coordinator**
- Synthesize outputs from the other agents into a clean 0-20% completion package.
- Update this checklist with actual status vs the 20% definition of done.
- Prepare clear handoff materials and recommended focus areas for the 20-40% swarm.
- Maintain overall M3 tracking and honest calibration.

**M3-05 & M3-06 (optional)**: Additional auditors or writers as needed for depth.

**Success Criteria for 0-20% Swarm**:
- All four 20% definition-of-done items are clearly achieved or explicitly deferred with justification.
- High-quality audit documents + proposals exist in the WTs.
- The 20-40% swarm has a very clear, prioritized starting point.

---

## Phase M3-20-40: Core Surfaces & Protocol Baseline Working

**Goal**: Deliver the 40% milestone — a usable initial public library surface + updated v0.4 protocol baseline with early conformance ideas.

**Recommended Swarm Size**: 7–8 agents (full phase swarm).

### Agent Roles for 20-40% Swarm

**M3-A1 – Library Surface Lead (Work Area 1)**
- Own the definition and implementation of the stable initial public library surface.
- Make the core autonomous loop (check_changes → edit → record_change → mark_green) significantly more ergonomic.
- Ensure the surface works naturally from small scripts to large creative monorepos.
- Deliver with excellent docstrings and clear happy-path examples.

**M3-A2 – Protocol Baseline Lead (Work Area 2)**
- Update and extend the v0.4 Agent Protocol with clearer mandatory behaviors for long-running autonomous agents.
- Introduce initial structure for conformance testing / validation hooks.
- Begin the versioning story for protocol messages.

**M3-A3 – Versioning & Contracts Lead**
- Design and begin implementing the versioning model for library objects and protocol messages.
- Ensure alignment with existing contracts v1 patterns.
- Produce clear migration and stability guarantees.

**M3-A4 – Thin Consumers Parity Lead (Work Area 4)**
- Ensure CLI and MCP stay in excellent parity with the new library + protocol changes.
- Build initial automated parity tests.
- Make sure thin consumers feel like high-fidelity delegates rather than afterthoughts.

**M3-A5 – Early Evidence & Validation Lead**
- Run the new surfaces through the harness on 25k–50k+ creative generators.
- Execute real-usage probes on RecipeLab (and any other designated external targets).
- Produce early evidence that the 40% surfaces are usable for autonomous loops.
- Focus on scalability and long-running ergonomics signals.

**M3-A6 – Documentation & Examples Lead (Work Area 5)**
- Create the first wave of agent-builder-first documentation and examples.
- Cover the new happy-path loop across different scale tiers.
- Work closely with A1 and A2.

**M3-A7 – Cross-Cutting Quality & Zero-Dep Lens**
- Act as the conscience for the swarm on long-term viability, zero new dependencies, and full scalability spectrum.
- Review all designs for future technical debt.
- Ensure every decision is explicitly mapped to the 9 Guiding Principles.

**M3-A8 – Evidence & Harvest Coordinator (like REV1 role)**
- Maintain overall tracking against the 40% definition of done.
- Ensure rich diaries and harvest artifacts are produced.
- Prepare clean handoff package for the 40-60% swarm.
- Perform independent hygiene and evidence quality review.

**Success Criteria for 20-40% Swarm** (40% Definition of Done):

- Stable initial public library surface is defined and usable.
- Core autonomous agent loop is noticeably more ergonomic than today.
- v0.4 protocol has been updated with clearer mandatory behaviors for long-running agents.
- Basic versioning story for library objects and protocol messages has started.
- Initial conformance ideas / test hooks have been prototyped.
- Early evidence exists on harness + RecipeLab that the new surfaces work for simple autonomous loops.
- Thin consumers have been updated to maintain parity.
- All work done with zero new dependencies, rich evidence, and explicit mapping to the 9 Guiding Principles and scalability spectrum.

---

## Shared Rules for Both Swarms

- Every agent must read the full M3 plan and this checklist before starting work.
- All validation must stay on allowed targets only.
- subagent_id must appear in 100% of commits, diaries, and artifacts.
- Perform and document a FRESH LAST "3" grep before any harness or source changes.
- Produce rich local diaries with verbatim mappings to the progressive definitions of done, the 9 Guiding Principles, and long-term usefulness.
- Harvest evidence to `wave-evidence/` (following the established naming pattern).

---

These prompts are ready to be copied into individual agent launch instructions when you decide to start the first M3 swarm(s). 

Let me know when you want the next level of detail (specific micro-batch checklists for the 20-40% swarm, or the actual launch instructions for the first agents).