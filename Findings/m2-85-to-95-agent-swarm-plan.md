# M2 85% → 95%+ Agent Swarm Plans (Post 2026-05-27 Baseline)

**Created**: 2026-05-27  
**Status**: Honest baseline from completed 8+2 wave (33-42), hygiene on main (0 markers in critical runtime, import GREEN), rich wave evidence preserved in Findings/wave-evidence/, gate functional (YELLOW only on CIABRE perf tuning ~149ms on 50-node synth; strong M2 deep scale inc_ratio 0.94, high concurrency, dogfood, external patterns).  
**Current Honest %**: 82–87% toward full 95%+ "set & forget" (per long-term scalable plan snapshot; 0/7 of the strict 85% criteria met on clean usable tree per v2 definition and honest assessments).  
**Focus (non-negotiable)**: Long-term (5–10+ year viability), zero new dependencies (pure stdlib + existing patterns), scalable from tiny (<100 files) to massive creative monorepos (50k+ files with barrels, dynamic/conditional imports, JS+Python mixes, workspaces, symlinks). Difficult paths first. Honest no-overclaim. Harness/RecipeLab + true external high-trust dogfood. "3" (original partials deep proof track) absolute last and untouched.

---

## 85% Success Factors (Measurable, Testable on Clean Tree + Dogfood)

Broader M2 reaches honest 85% when **all** of the following are demonstrably true on a clean, runnable main tree (import GREEN, 0 markers in runtime sources + plans, full `--m2-health --deep` GREEN) with real RecipeLab 1637/269 dogfood + at least one true external 5k+ creative monorepo under realistic multi-agent/chaos load:

1. **Zero committed markers + clean import/hygiene** (v2 crit 1): Package imports cleanly on main; zero committed conflict markers (<<<<<<< / >>>>>>> / =======) in all runtime sources (health.py, contracts.py, parsers/python.py, both .sh) and key plans. Self-hosting hygiene matrix only flags genuinely problematic files. Gate 0 passed.

2. **Streaming/resumable/partials + rich summaries as routine/default path** (v2 crit 2): For normal agent usage on 20k+ creative monorepos, the default path is `generate_update_events` / `run_update_stream` (with PartialResult_v1, continuation, budgets, ACS/CIABRE hooks, reverse maintenance) + rich bounded summaries (executive/impact via compute_*_summary or MCP get_*_summary format=summary). Not opt-in or fallback. Thin shells (wikifier.sh + scripts/wikifier.sh) detect A2 flags and delegate cleanly with event/Partial consumption.

3. **Both thin shells provide full parity under real 25k–50k+ creative chaos** (v2 crit 3): `update-maps --stream/--partial/--resume` etc. produce identical observables + fidelity to pure Python primary on RecipeLab + true external creative under concurrent edits/renames. Memory-safe O(1) UX. No duplicate logic. Gate 2 passed.

4. **True external 5k+ creative multi-day high-trust autonomous dogfood** (v2 crit 4 + Gate 3, the hardest per reviewer 31): At least one true external (not saturated internal RecipeLab) 5k+ creative monorepo exercised for multi-day (3–7+) autonomous agent sessions with streaming/partials/summaries as the normal/default workflow (record_change, check, update, suggest, health, journal, get_*_summary). Reproducible artifacts, logs, metrics (partials usage %, agent task success without full fallback, ACS/CIABRE explain-all, no trust failures). Full `--m2-health --deep` + external logs committed. Honest assessment vs exact "external preferred + extended periods with high trust" wording. Gate 3 passed.

5. **All Workstream A M2 exit criteria met with verification** (v2 crit 5): 20k+ creative scoped queries in seconds + safe partials + reverse as trustworthy as forward + structured/summary modes recommended. Proven on clean main + RecipeLab + external under scale/chaos. (Builds on existing A0/A1/A2 foundations now on main.)

6. **Workstreams B–E have closed their highest-leverage phases sufficient for 85% usability** (v2 crit 6): 
   - B: Zero flakiness under rapid multi-agent + reliable stale wiki detection + stub pollution non-issue on real projects (health durability surfaces exercised heavily).
   - C: Journal/pending bounded + useful historical intent queries after simulated heavy activity.
   - D: Full first-class low-confidence/unresolved/failure transparency as easy to consume as success edges (parser parity, diagnostics).
   - E: Protocol conformance + thin library/MCP wiring sufficient for 85% usability (v0.4 surfaces exercised).
   Gate 4 prep complete; high-leverage phases closed on clean tree + dogfood.

7. **Main tracker reflects Broader M2 at honest ~85% (not [x]) + v0.4 plans updated + clean self-hosting hygiene** (v2 crit 7): Tracker shows honest ~85% with evidence catalog (not aspirational claims). v0.4-Execution-Plan.md and related updated with lessons from the 85% push. Clean self-hosting hygiene (no stray markers, session data, untracked wave junk on main). All prior Gates 0-4 passing on clean tree + RecipeLab 1637/269 + true external 5k+ creative multi-day high-trust with the new paths.

**Verification (Mandatory, from v2 plan)**:
- Gate 0 (Hygiene): Clean import + basic surfaces + `--gap1-health` lite + `--m2-health --deep` (import/health section) GREEN on clean main. Self-hosting hygiene passes.
- Gate 1–3: Full `--m2-health --deep` (50k creative generators + 8-agent concurrency + real RecipeLab 1637 + compaction/journal hooks + WS A-E integration) + external creative 5k+ runs.
- Gate 2 specific: Shell vs pure-Python identical observables + fidelity under concurrent edits on RecipeLab + external creative.
- Gate 3 specific: True external 5k+ creative (not just RecipeLab) + multi-day (3–7+) autonomous sessions with partials/summaries dominant + reproducible artifacts + metrics + high trust + honest assessment vs exact wording.
- Gate 4 (85% Declaration): All prior gates + all 7 exact criteria + WS A-E high-leverage phases closed + tracker honest ~85% (not [x]) + v0.4 plans updated + clean self-hosting hygiene + no Gap #1 regression.
- Cross-cutting (after every micro): Harness + RecipeLab + concrete metrics (partials %, fidelity, bounded resources, no trust failures). Self-hosting hygiene validated.
- No Shortcuts: Any claim without passing the relevant gate on a clean tree is invalid. "3" (original partials deep proof track + test_partial_continuation_workflow_25k) absolute untouched.

**How far we can push with current foundations** (honest assessment):
- **To 85%**: Highly achievable with focused 8+2 swarms (see below). Current foundations (hygiene on main, real streaming generator + facade + CLI/MCP on main, evidence of honest state preserved, gate functional, CIABRE measurement improved) give us the engine. The remaining work is making the 7 criteria "demonstrably true" on clean main + real dogfood (especially 2, 3, 4, 6 — the "routine/default", "full parity", "true external multi-day", and "WS B-E high-leverage closure" items). Difficult paths: true external high-trust multi-day (long pole), making streaming the unquestioned default in shells/CLI/MCP/daemon, full WS B-E stress under 25k–50k+ creative chaos. Realistic timeline with disciplined swarms: weeks to low months, depending on external dogfood availability.
- **To 95%+**: Achievable but requires the full detailed per-WS A-E exits from the long-term scalable plan (see below). Current 82–87% baseline (per long-term plan snapshot) already incorporates the streaming foundation + hygiene + evidence. The remaining ~8–13% is durability under years of autonomous load, richer executive/impact summaries as first-class, full 50k+ creative real monorepo dogfood exercising everything (not just harness generators), complete thin-shell parity with no fallback temptation, and the last-mile observability/durability polish. This is the "set & forget for autonomous agents on massive creative monorepos" vision. More work, but the architecture (event-sourcing, contracts v1, O(changed), zero-dep, streaming resumable) is already the correct long-term foundation.

---

## 95%+ Full M2 Exits (from Long-Term Scalable Plan)

The long-term plan vision (solid, production-useful, trustworthy for autonomous long-term agent operation on 10 files to 50k+ creative monorepos) is achieved when the 8 guiding principles + detailed per-WS A-E exit criteria are met (see the full long-term plan for the exhaustive checklists). High-level:

- **WS A (Core Update/Streaming/Reverse)**: Full O(changed) streaming/resumable pipeline with first-class reverse as trustworthy as forward, rich Partial + Summary protocol, proven on 50k+ creative under years of multi-agent load. No fallback to full rebuild in normal operation.
- **WS B (Health Durability)**: Zero flakiness under rapid multi-agent + reliable stale wiki detection + stub pollution non-issue on real 50k+ projects over years. Health matrix + heal policy durable and observable.
- **WS C (Journal/Pending)**: Event-sourced journal primary with smart compaction; pending bounded and useful for historical intent queries after heavy autonomous activity over years.
- **WS D (Transparency/Parser Parity)**: Full first-class low-confidence/unresolved/failure transparency as easy to consume as success edges; parser parity (confidence, raw_module, resolved_path, rich diagnostics) on all paths; ACS/CIABRE explain-all everywhere.
- **WS E (Library/Protocol v0.4+)**: Full protocol conformance + thin library/MCP/CLI wiring; zero-dep ergonomics for agents; versioned contracts with migration paths; proven on massive creative monorepos.

All with the 8 principles (scalability spectrum first, zero-dep + portable, dual-path, event-sourced + compaction, frozen + versioned contracts, full observability by default, multi-agent safe by design, dogfood + harness driven, explicit exit criteria).

**Gaps from current 82–87% baseline** (high-level from long-term plan + recent honest assessments):
- Streaming not yet the unquestioned routine/default in shells/CLI/MCP/daemon under real 25k–50k+ creative chaos (criteria 2/3).
- True external 5k+ creative multi-day high-trust autonomous with the new paths (criteria 4).
- Full WS B-E high-leverage closure under scale/chaos on real projects (criteria 6).
- CIABRE perf tuning to meet the tightened R5 target on scale (remaining gate YELLOW).
- Durability under years of autonomous load, richer summaries as first-class, full 50k+ creative real dogfood (the last miles to 95%+).

---

## Agent Swarm Structure for 85% Push + 95% Full Exits

**Same discipline as prior successful waves (non-negotiable)**:
- 8+ phase agents + 2 dedicated reviewers (41/42 style) in isolated persistent git worktrees on original paths (`/home/aron/.grok/worktrees/Wikifier/subagent-43` etc.).
- Use `todo_write` (one in_progress at a time, merge:false for full list).
- Read plans first (this document + long-term scalable plan + current tracker + wave-evidence diaries).
- Update **only local** copies of plans with checkboxes + rich diaries (subagent_id=XX in every commit and diary entry).
- Small safe read-first steps only (read_file before any search_replace on plans or code).
- "3" (original partials/continuation deep proof track + test_partial_continuation_workflow_25k) absolute untouched.
- Zero new dependencies.
- Harness-driven + RecipeLab 1637/269 dogfood + true external 5k+ creative (multi-day high-trust where possible).
- Honest checkboxes only ([x] only when production-grade, verified on real workloads, tree actually runnable).
- Many small commits with subagent_id in message.
- Full gates after significant phases (harness --m2-health --deep + RecipeLab + external where relevant).
- Reviewers (two new) inspect all phase trees, verify vs this plan + 85%/95% factors + gates, recommend safe hygiene-first merges (small batches, full gate on source before any main change).

**Phase Structure for 85% Push (building directly on current foundations)**:
- **Phase 5a: Default Streaming + Rich Summaries Routine (complete v2 crit 2)**: Make the streaming/resumable/partial + rich summaries (A3 executive/impact) the unquestioned routine/default path in shells, CLI, MCP, daemon, library. Thin delegation complete. Bounded summaries O(k) and first-class.
- **Phase 5b: Full Thin-Shell Parity Under Real Scale + Chaos (complete v2 crit 3)**: Both shells deliver full parity (identical observables/fidelity/memory-safe O(1)) under 25k–50k+ creative concurrent edits/renames on RecipeLab + true external. No duplicate logic.
- **Phase 5c: True External Multi-Day High-Trust Extension (complete v2 crit 4 + Gate 3)**: Extend 38's proxy work to at least one true external 5k+ creative monorepo for multi-day (3–7+) autonomous sessions with the new paths as normal/default + high trust. Reproducible artifacts/metrics. Honest assessment vs exact wording. Gate 3 passed.
- **Phase 5d: WS B-E High-Leverage Closure (complete v2 crit 6)**: Heavy stress on B (health durability under rapid multi-agent + heal policy), C (journal queries after heavy activity), D (transparency on partials/failures/low-conf), E (library/MCP conformance + thin wiring) on clean main + RecipeLab + external under scale/chaos.
- **Phase 5e: 85% Declaration + Tracker Update (complete v2 crit 7 + Gate 4)**: All 7 criteria demonstrably true on clean main + dogfood. All Gates 0-4 passed. Tracker at honest ~85% with evidence catalog. v0.4 plans updated. Clean self-hosting hygiene. Gate 4 passed. Honest % bump to 85%.

**Subsequent Phases for 95%+ Full Exits** (detailed per long-term scalable plan):
- Phase 6: Full per-WS A-E exit criteria (durability under years of autonomous load, richer first-class summaries, complete 50k+ creative real monorepo dogfood exercising everything, last-mile observability/durability polish).
- Phase 7: Final 95%+ declaration on main tracker + long-term plan. M2 [x].

**Verification & Governance (same as v2 plan, extended)**:
- Mandatory gates after each phase (harness --m2-health --deep on clean main + RecipeLab 1637/269 + true external 5k+ creative where relevant for the phase).
- "3" absolute last.
- Honest local-only updates until gates pass on clean main.
- Reviewers inspect all phase trees before any main merge; hygiene-first, small batches, full gate on source.
- No overclaim. Difficult paths first (true external extension, making streaming the unquestioned default, full WS B-E high-leverage under real chaos).

**Risks & Mitigations**:
- CIABRE perf remaining YELLOW: Continue the R5 tuning (graph reuse, Tarjan, caching) in parallel with the swarms; the measurement improvement already helps.
- External long-pole difficulty (per reviewer 31): Prioritize finding/setting up a real 5k+ creative target early; use harness 25k+ as high-fidelity proxy while pursuing the real one.
- Overclaim temptation on "routine/default": Strict "demonstrably true on clean tree + real dogfood" rule + reviewer cross-check.
- "3" pollution: Explicit rule + grep enforcement in every agent prompt.

**How Far We Can Push** (honest):
- **85%**: Highly achievable (weeks to a few months with disciplined 8+2 swarms). The 7 criteria are the measurable target; current foundations give us the engine.
- **95%+**: Achievable (longer, more work on the detailed per-WS exits + years-of-load durability + full 50k+ creative real dogfood). The architecture is already the correct long-term one.

This plan deliberately chooses the harder, longer-lasting path. When in doubt, re-read the long-term scalable plan's Guiding Principles and "no shortcuts" rule. The evidence from the prior 8+2 wave (now in wave-evidence/) plus the hygiene on main gives us a strong, honest starting point.

**Next Immediate Action**: Launch the first 8+2 swarm (subagent-43+) for Phase 5a (default streaming + rich summaries routine) using the exact discipline above. Use this document + the long-term scalable plan + current tracker + wave-evidence/ as the required reading.

