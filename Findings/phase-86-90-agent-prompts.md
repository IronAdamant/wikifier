# Phase 86-90: Durability, Observability & Scale Hardening — Agent Prompts (8 Agents)

**Phase Goal**: Harden the M2 core for long-term (years-scale) autonomous multi-agent operation and prove full scalability across the spectrum to massive 25k–50k+ creative monorepos (JS+Python mixes, barrels, dynamic/conditional, workspaces, symlinks). Deliver bounded state, first-class richer observability (executive/impact summaries + autonomous session traces), production-grade compaction/journal/health/transparency durability, and zero trust failures under sustained heavy load — all while strictly respecting the long-term zero-dep + portability mandate.

**Key Rules (non-negotiable in every prompt and every agent's work)**:

**M2–M4 = Pure Feature Addition Phases Only**
- M1 is complete.
- M2–M4 are strictly for feature creation, addition, refinement, and hardening. There is **no dogfooding of any kind** allowed on the Wikifier project itself until M5.
- This includes (but is not limited to): running `--m2-health --deep`, sustained autonomous sessions, heavy self-validation, or using the Wikifier source tree as a primary target for stress or validation.
- All real usage, stress, and validation during M2–M4 must be restricted exclusively to: the harness (synthetic 25k–50k+ creative generators), RecipeLab, and user-designated external projects only.
- M5 is the dedicated full dogfooding and testing phase on the multiple real-world projects the user has prepared. The strict final 7-criteria scoring, literal multi-day high-trust autonomous operation, and complete 0/7 85% evaluation are reserved exclusively for M5.

**"Actual 95%" Definition During M2–M4**
- References to "actual 95%" or progress toward 95%+ in this phase refer only to the quality, completeness, and long-term viability of the features being built (under the 9 Guiding Principles: zero new dependencies, full scalability spectrum, event-sourced durability, full observability, etc.).
- It does **not** refer to the final M5 dogfood success criteria or literal 7-criteria scoring.

**Other Non-Negotiable Rules**
- "3" (original partials deep proof track exercising PartialResultV1 / continuation_token / 25k–50k creative streaming paths in the harness M2 suites) is **absolute last and untouched** — explicit LAST grep on `wikifier/gap1_validation_harness.py` before every content write that touches source/harness + final verification. Only historical references + designated subagent WT copies allowed (0 runtime pollution on main).
- Zero new dependencies (pure stdlib throughout).
- Follow the full 9-step hygiene-first discipline on every batch: local-only persistent original-path worktrees, small micro-batches, full `--m2-health --deep` gate on source/temp **before any main consideration**, external long-pole #1 on allowed targets only, new reviewer pair per batch, main 100% clean (0 critical markers + import GREEN).
- Focus on long-term viability: explicit zero-dep + portable, dual-path (Python-primary default + thin shell delegation), event-sourced journal + smart compaction, frozen/versioned contracts, full observability (ACS/CIABRE default on every path), multi-agent safety (locking + provenance), harness-driven evidence.
- All work must be harvestable: rich local diary in your WT (vs exact long-term A-E 95%+ exits from `m2-full-closure-longterm-scalable-plan.md`, the 7-criteria, and the 8/9 guiding principles) + final harvest to `wave-evidence/phase6-86-90-*-completion.txt` (or equivalent).
- Honest calibration: 82–87% toward 95%+ / **0/7 strict 85%** preserved throughout (feature-building lens during M2–M4; literal multi-day high-trust autonomous external long-pole per old crit4/Gate3 wording + full 0/7 is M5 scope only).
- Use the detailed working checklist: `Findings/m2-86-90-durability-observability-scale-hardening-checklist.md`.

---

## Agent 86-B2: Health Durability Hardening Lead (Years-Load + Multi-Agent)

**Role**: Lead for advanced years-scale compaction policies on health matrix + stale signals + sustained heavy multi-agent long-run durability + extreme-scale sharded/summary views.

**Mission**:
- Deliver safe, reversible, observable time + significance (ACS/CIABRE + high-impact) compaction for health + PendingItemV1 that keeps active state strictly bounded after 1000+ simulated "day"/"year" churn cycles.
- Prove zero flakiness, 100% heal accuracy, and provenance survival under sustained 8+ concurrent agent chaos (edits/renames/intent via record_change + heal + health queries) for simulated weeks/months.
- Make directory-scoped + summary-only health views the fast/default path at 50k+ creative scale (O(k) memory/time).

**Strict Constraints**:
- **No work or validation on the Wikifier source tree itself**.
- Primary targets: harness 25k–50k+ creative generators (extend run_m2_compaction_longrun_years_sim + durability_longrun) + RecipeLab + any user-designated external creative monorepos.
- "3" untouched — explicit LAST grep before every write touching harness/source.
- All evidence vs long-term WS B 95% exit + 8/9 principles + honest 82-87%/0/7.

**Deliverables**:
- Health matrix + stale detection remain accurate and bounded after extreme simulated years-load + heavy concurrent chaos.
- Sharded/summary views proven fast and default on massive creative workloads (allowed targets).
- Rich WT diary + harvest to wave-evidence/ with metrics (size stability, heal accuracy, query perf, provenance presence, 0 trust failures).
- 5+ commits carrying subagent_id=86-B2.

**Agent Pattern**: Isolated persistent original-path worktree (subagent-86-B2), 9-step hygiene, small batches, full gate before any main consideration, rich local diary vs checklist items + long-term exits + 7-criteria + 8/9 principles, evidence harvest, local-only until post full gated review.

---

## Agent 86-C2: Journal / Compaction / Intent Scale Hardening Lead

**Role**: Lead for years-scale reversible compaction policies (time + significance + ACS/CIABRE-driven) + historical query usefulness + pending as robust auto-pruned work queue under extreme sustained load.

**Mission**:
- Extend compaction (manifest, archive, dry-run, reversible) to true multi-"year" event volumes (thousands of mixed agent sessions, high creative/barrel churn) while keeping active state bounded and queries fast/useful.
- Prove `get_intent_history`, `get_high_impact_changes`, `get_session_summary` (and any new surfaces) return rich provenance-bounded results (ACS/CIABRE/reverse/journal links) after aggressive years-scale pruning — no megabytes, no loss of actionable history.
- Harden pending_updates as high-fidelity queue (provenance, priority, safe auto-prune) that survives continuous record_change + heal + streaming partials chaos without corruption or unbounded growth.

**Strict Constraints**:
- Allowed targets only (harness + RecipeLab + designated externals). No Wikifier source dogfood.
- "3" sacred — LAST grep before every write.
- Evidence must tie to long-term WS C 95% exit + compaction durability + query usefulness under years autonomous load.

**Deliverables**:
- Journal/pending strictly bounded + queries remain useful/fast after extreme simulated years activity on 25k–50k+ creative.
- Full reversible compaction with manifest/dry-run/observability proven at scale.
- Rich diary + harvest (metrics: bytes saved, query hit relevance post-prune, 0 corruption, provenance always present).
- subagent_id=86-C2 in all commits/diaries.

**Agent Pattern**: Worktree subagent-86-C2, 5+ commits, rich diary vs exact long-term C exit + 7-criteria + 8/9 principles, 9-step, LAST "3" grep hygiene, harvest to wave-evidence/.

---

## Agent 86-D2: ACS/CIABRE + Transparency + Session Observability Hardening

**Role**: Harden first-class low-conf/failure transparency, parser parity, ACS/CIABRE explain-all, richer suggestion_for_agent, and autonomous session aggregate observability at massive creative scale (build directly on 81 last-mile prototypes).

**Mission**:
- Deliver first-class autonomous session traces + richer long-run executive/impact summary consumption as the normal experience for long autonomous runs on 25k–50k+ creative (O(k) bounded, cross-linked to ACS/CIABRE/reverse/journal/barrels even after days/weeks of simulated activity).
- Push explain-all + context-aware suggestion quality to 50k+ scale with heavy barrel/dynamic/cond/JS+Py patterns; integrate with A3 summaries and health impact views.
- Guarantee provenance (ACS/CIABRE, reverse fan-in, barrel 300 v1, health freshness, journal intent) is present and consistent on *every* surface under years-load + extreme compaction/partials/heal.

**Strict Constraints**:
- Harness creative generators (25k–50k+ barrels + dynamic + mixed) + RecipeLab + designated massive externals only.
- No Wikifier source.
- "3" untouched; LAST grep before writes.
- Cross-workstream collaboration with B2/C2/A3 on session obs + provenance.

**Deliverables**:
- Session aggregate obs + richer A3 summaries practical and default at massive scale with full provenance.
- Every resolution limitation/cycle/barrel/creative pattern surfaces high-quality suggestions.
- Zero "explainability debt" at 50k+ under sustained load (provenance always present).
- Rich evidence harvest vs long-term WS D/A exits + 7-criteria + 8/9 principles.

**Agent Pattern**: subagent-86-D2 worktree, 5+ commits with id, rich diary, 9-step, LAST grep hygiene, harvest to wave-evidence/phase6-86-90-d2-....

---

## Agent 86-X3: Harness Long-Running Durability Stress (Years-Sim + Full A/B/C/D Integration)

**Role**: Primary harness agent for extended long-running (simulated years) durability stress suites exercising full A/B/C/D orchestration, streaming partials/resume safety, health heal/compaction, journal historical queries, transparency, and reverse survival under continuous multi-agent load.

**Mission**:
- Build/extend harness suites for multi-"year" churn loops (resume tokens, continuation, safe_to_act, partial consumption, heal, compaction, historical queries, ACS/CIABRE provenance) that remain trustworthy across simulated months/years.
- Integrate all workstreams (A streaming/partials/reverse + B health + C journal + D transparency) in realistic long autonomous session simulations on 25k–50k+ creative.
- Prove no drift in bounded state, provenance, or trust after extreme duration.

**Strict Constraints**:
- Harness primary (plus RecipeLab/designated if available). No Wikifier source.
- "3" sacred — explicit LAST grep before any harness edits.
- Evidence vs long-term cross-cutting durability + 8/9 principles + honest calibration.

**Deliverables**:
- New/extended longrun durability suites (years-equivalent) with full A/B/C/D + partial/resume safety passing cleanly on 25k–50k+ creative.
- 0 trust failures, bounded state, provenance everywhere, useful historical queries post-load.
- Rich diary + harvest (metrics, integration proofs, 7-criteria alignment).

**Agent Pattern**: subagent-86-X3, 5+ commits, rich local diary, 9-step + gate, LAST "3" grep, harvest naming phase6-86-90-x3-...

---

## Agent 86-X4: 50k+ Massive Creative Scale + Regression Gates + Sustained Concurrency

**Role**: Harness scale + regression specialist. Push generators to true 50k+ massive creative (deep barrels, heavy dynamic/cond/JS+Py, workspaces), add strict memory/perf regression assertions (O(changed)/O(k) must hold), sustained 8+ agent concurrency chaos, and durability regression suite (replay prior 80-85 sessions + assert 0 drift).

**Mission**:
- 50k+ creative generator coverage + memory caps + timing regression guards in --m2-health --deep and dedicated suites.
- Sustained 8+ concurrent simulated agents + daemon/locking + intent chaos for hours of wallclock on massive creative.
- Durability regression harness: replay 80-85 chaos/intent/compaction/streaming as first-class gate; assert bounded/ACS/provenance/query usefulness/0 trust failures.
- All integrated into the standard deep gate as long-term regression protection.

**Strict Constraints**:
- Harness + allowed targets only. No Wikifier dogfood.
- "3" untouched; LAST grep before harness writes.
- Focus on tooling/evidence/regression (cross-support B2/C2/D2/A3).

**Deliverables**:
- 50k+ scale + sustained concurrency + regression suite passing with strict O(changed)/O(k) + memory assertions.
- --m2-health --deep extended with years/longrun/50k/regression as normal.
- Full evidence harvest with metrics vs scalability principle + 7-criteria.

**Agent Pattern**: subagent-86-X4 worktree, 5+ commits id=86-X4, rich diary vs checklist + long-term exits, 9-step, LAST grep, harvest to wave-evidence/.

---

## Agent 86-A3: Richer Summaries & Autonomous Session Observability Durability at Scale

**Role**: Cross-cutting support for richer executive/impact/dependency summaries + autonomous session aggregate traces as the durable, recommended, O(k) bounded default for long autonomous runs on massive creative (build on 80-A1/A2 + 81 prototypes; cross-link to D2/B2/C2).

**Mission**:
- Ensure compute_executive_summary / compute_impact_summary / compute_dependency_summary (with ACS/reverse/CIABRE cross-links, deque tails) + new session obs views remain the normal path, high-signal, and strictly bounded after years-scale load/compaction/partials on 25k–50k+ creative.
- Memory-safe O(1) UX for very long sessions (many partials, large summary outputs).
- Full integration with health impact, journal historical, transparency provenance.

**Strict Constraints**:
- Allowed targets + harness 25k–50k+ creative only.
- No Wikifier source.
- "3" sacred.
- Collaborate with D2 (session obs) + X agents (harness).

**Deliverables**:
- Richer summaries + session traces proven durable, practical, and default at massive scale under extreme load.
- O(k) + provenance always present post-compaction/years-sim.
- Evidence vs long-term WS A 95% exit + observability principle.

**Agent Pattern**: subagent-86-A3, 5+ commits, rich diary, 9-step + LAST grep hygiene, harvest.

---

## Agent 86-E2: Thin Ergonomics & Protocol Durability at Massive Scale

**Role**: Cross-cutting support for thin-shell + v0.4 library/protocol durability at massive creative scale (memory-safe long sessions, O(1) streaming/partials/summaries/health/journal over very large outputs + many partials; v0.4 record_change/check-first/Red-Yellow ergonomics rock-solid under years load).

**Mission**:
- Both wikifier.sh + scripts/wikifier.sh remain clean thin delegates with full parity for all hardened surfaces (streaming/partials/summaries/health/journal/compaction queries) on long massive-creative sessions.
- Eliminate any remaining duplicate logic or memory-unsafe patterns at 50k+ scale.
- v0.4 protocol (mandatory record_change post-edit, check-first, prioritize Red/Yellow, summary default) production-hardened for autonomous agent loops on massive repos.

**Strict Constraints**:
- Validation on harness 25k–50k+ + RecipeLab + designated externals only.
- "3" untouched.
- No Wikifier source dogfood.
- Support X agents on shell parity in longrun suites.

**Deliverables**:
- Thin dual-path experience remains clean, memory-safe, and fallback-free for long autonomous sessions at massive scale.
- Protocol conformance + ergonomics solid under years-load stress.
- Evidence vs long-term WS E 95% exit + zero-dep/dual-path principle.

**Agent Pattern**: subagent-86-E2, 5+ commits with id, rich diary vs checklist + long-term E + 8/9 principles, 9-step, LAST "3" grep, harvest.

---

## Agent 86-REV1: Independent Reviewer (Hygiene + 9-Step Enforcement)

**Role**: Dedicated independent reviewer for micro-batches across the phase (new pair recommended per batch per 9-step playbook). Enforce "3" LAST grep, M5 boundary, main cleanliness, evidence quality, and full 9-step before any main consideration.

**Mission**:
- Review all 86- agent WT output (diaries, commits, harvests, code/docs) against the 86-90 checklist, phased plan, long-term A-E exits, 7-criteria, 8/9 principles, and iron rules.
- Perform explicit LAST "3" grep + git hygiene checks + gate runs on every batch.
- Ensure no dogfood language violations and honest 82-87%/0/7 calibration in all artifacts.
- Produce reviewer reports (wave-evidence/phase6-86-90-rev1-... style) suitable for 86/87-style dual review.

**Strict Constraints**:
- Full independence from the agents being reviewed.
- All rules (M5 boundary, "3", 9-step, zero-dep, scalability) enforced literally.
- No direct feature work; pure review + hygiene gate.

**Deliverables**:
- 86/87-style reviewer reports with pass/fail on 9-step, "3" hygiene, M5 compliance, evidence quality, calibration honesty.
- Citations and integration notes for tracker/plan updates.
- Confirmation that main stays 100% clean and "3" untouched.

**Agent Pattern**: subagent-86-REV1 worktree (or dedicated reviewer WT), rich review diary, multiple LAST greps documented, 9-step enforcement, harvest of reviewer artifacts.

---

## Launch Instructions for Phase 86-90

- Each agent gets its own isolated persistent original-path worktree (`subagent-86-B2`, `subagent-86-C2`, etc.).
- Every prompt includes the full iron rules + explicit reference to `Findings/m2-86-90-durability-observability-scale-hardening-checklist.md` as the working checklist.
- All agents must produce rich local diaries in their WTs (vs exact long-term A-E exits + 7-criteria + 8/9 principles + honest calibration) + final harvest to `wave-evidence/phase6-86-90-*-completion.txt`.
- Use the standard 9-step hygiene-first playbook + dual independent reviewers (86-REV1 or new pair per batch).
- External long-pole style real usage (high-value feedback) is allowed **only** on user-designated projects other than the Wikifier source itself (M5 boundary).
- subagent_id=86-B2 (etc.) must appear in 100% commits, diaries, headers, and harvests.
- Explicit LAST grep for "3" (partials continuation 25k track) before every write touching harness/source — document the grep in your diary.
- After all 8 complete: central harvest + citations into phased plan / tracker / Milestones-Overview / README, then full `--m2-health --deep` gate + hygiene verify before any main merge consideration.

This set of 8 prompts (plus the detailed checklist) is ready for immediate execution under the `m2-phased-to-95-agent-plan.md`.

**Sacred "3" Hygiene (PREP-86)**: Multiple explicit LAST greps performed during 86-01 review + immediately before creation of this prompts file and the companion checklist (2026-05-28). Historical name "test_partial_continuation_workflow_25k" has no matches in current harness; the exercised M2 equivalents (25k–50k creative streaming/partials/continuation via run_m2_scale_harness + PartialResultV1/partial_ready/continuation_token fidelity paths) are confirmed untouched in main (only prior-agent additive comments + "'3' untouched" markers present). This satisfies the pre-write hygiene requirement. All 86-90 agents must repeat + document the grep in their WT diaries before any harness/source writes.

**M5 Boundary Reminder (repeated for emphasis)**: Do not dogfood the Wikifier project itself in any 86-90 work. Validation and real-usage stress restricted to harness + RecipeLab + user-designated other external projects. This project moves to M5 dogfooding only after honest 95%+ per the long-term plan.

**subagent_id=PREP-86-05** (prompts creation) + per-agent 86- ids for execution. "3" untouched. Long-term zero-dep + full scalability spectrum first. Honest 82–87%/0/7 preserved.

Ready for user direction: "Execute 8 sub agents for 86-90" (or adjustments).