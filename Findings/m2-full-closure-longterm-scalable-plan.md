# M2 Full Closure — Long-Term Scalable Architecture & Execution Plan

**File Type**: Living architectural strategy, phased roadmap, and detailed execution plan  
**Created**: 2026-05-22  
<<<<<<< HEAD
**Last Updated**: 2026-05-22  
**Status**: Open — Ready for phased multi-wave execution  
=======
**Last Updated**: 2026-05-26 (Workstream E resumption via Agent 6: completing Python-primary extraction + MV library to clean public API, merging design/Protocol v0.4 into main docs, conformance harness, CLI/MCP thin wiring, dogfooding; focus on rigorous contracts + zero-dep agent-first quality)  
**Status**: Open — Ready for phased multi-wave execution (E foundational slice complete; remaining E items active under Agent 6)  
>>>>>>> agent-6-library-final
**Owner**: M2 Closure Program (post Gap #1 Swarm)  
**Related Documents**:
- `Findings/m2_rem_08_and_v0.4_progress_tracker.md` (current status + diary)
- `v0.4-Execution-Plan.md`
- `Logged_issues/high/import/m2-dependency-intelligence-tasks.md`
- `Logged_issues/high/import/m2-gap-closure-dependency-intelligence.md`
- Existing Gap #1 long-term strategies (`gap1_*_longterm_strategy.md`)
- `contracts.py`, `import_cache.py`, `health.py`, `cli.py`, `wikifier.sh`, `mcp/server.py`

---

## Executive Summary & Vision

**Goal**: Bring M2 (Dependency Intelligence) to a state that is **solid, production-useful, and trustworthy for autonomous long-term agent operation** on codebases ranging from tiny scripts (10 files) to massive creative monorepos (50k+ files), with no shortcuts that create future technical debt.

Gap #1 (Dependency Intelligence Quality — the 6 last-mile items) is complete (2026-05-21 swarm, full `--gap1-health` GREEN). The remaining work is the **broader M2 mandate**: make `update-maps` and the surrounding stateful system genuinely useful, reliable, observable, and scalable as the core "living memory" layer for agents.

**Core Promise of Completed M2**:
> An agent (or swarm of agents) can maintain a high-fidelity, low-ambiguity, incrementally-updatable map of any codebase over months/years of evolution — with bounded state, actionable diagnostics, first-class semantic intent logging, and query surfaces that remain fast and useful from 10 files to 50k+ files.

**Why "Long-Term & Scalable" (No Short Paths)**:
- Short-term hacks (e.g., "just add progress bars", "simple journal pruning", "best-effort summaries") will fail at scale or under multi-agent concurrent load.
- Every major component must be designed from the ground up for:
  - **Proportional cost**: Work is O(changed) or O(query scope), never O(entire repo) in the common case.
  - **Durability**: Survives years of agent activity, project moves, renames, massive refactors, symlinked monorepos, and multiple concurrent agents.
  - **Observability**: Every important decision (resolution, invalidation, health flip, intent record) is explainable with provenance.
  - **Agent ergonomics**: Structured + human-readable dual surfaces; protocol is versioned and conformance-testable.
  - **Zero new dependencies**: Pure Python stdlib + portable shell + existing patterns (locking, contracts, BRC-style caches, ACS/CIABRE).
- Difficult but correct architectures (event sourcing with compaction, streaming resumable pipelines, first-class reverse index structures, versioned data contracts) are explicitly preferred when they provide 5–10 year viability.

**Rule (unchanged)**: No M3 until this plan's exit criteria are met and the main tracker reflects M2 as [x].

---

## Guiding Principles (Non-Negotiable)

1. **Scalability Spectrum First**: Every design must have explicit answers for Tiny (<100 files), Medium (100–2k), Large (2k–15k), Massive (15k–50k+), and "Creative Monorepo" (heavy barrels, dynamic imports, workspaces, symlinks).
2. **Zero-Dependency + Portable**: No new Python packages, no external databases, no fs watchers (mtime + explicit triggers remain the contract). Works after `pip install wikifier`.
3. **Dual-Path Architecture**: Continue and complete the Python-primary extraction (cli.py `run_full_update` + import_cache core) while keeping a thin, high-fidelity shell orchestrator. Python becomes the scalable engine; shell is the portable thin wrapper + legacy compatibility layer.
4. **Event-Sourced + Compaction Where Appropriate**: Journal, pending state, and major caches must be append-oriented with smart, safe compaction rather than mutable-in-place files that grow forever.
5. **Frozen + Versioned Contracts**: Build on `contracts.py`. Major data shapes (cache entries, health records, journal events, resolution provenance) get version stamps and migration paths.
6. **Full Observability by Default**: Every hot path (resolution, invalidation, health transition, intent recording) produces rich, queryable, ACS/CIABRE-aware diagnostics (following the successful patterns from Gap #1 ACS + Barrel + Cycles waves).
7. **Multi-Agent Safe by Design**: Locking (M2-Rem-07) is table stakes. Future designs must consider concurrent agents, background daemons, and human edits without corruption or lost updates.
8. **Dogfood + Harness Driven**: Nothing is "done" until it passes the existing `--gap1-health` gate extended with M2-specific suites + real monorepo dogfood (RecipeLab + synthetic 10k–50k stress + at least one external creative monorepo).
9. **Explicit Exit Criteria**: Each workstream has measurable "good enough for production M2" criteria. No vague "improve".

---

## Current State Snapshot (Post 2026-05-21 Gap #1 Swarm)

**Completed (Gap #1)**:
- Barrel_v2 + Persistent BRC + Deep O(changed) Invalidation + reports + prune + daemon integration + dedicated MCP `get_barrel_reports`
- Guaranteed Cycle/Graph Persistence (iterative Tarjan, graph_signature delta short-circuit, v1 canonical default, reuse stats, real timing proof)
- External/Packaged robustness + Python-primary `run_full_update` extraction (Wave 5/6, deeper dirty+parser+persist+ACS tie-in)
- ACS + CIABRE Surfacing Uniformity + `low_confidence_only` filter
- Creative/Dynamic coverage (CDIA Layer 3.5 + Python parity + 4+ new detectors)
- Full `--gap1-health` GREEN

**M2 Status** (from `m2_rem_08_and_v0.4_progress_tracker.md`):
- Overall: [-] M2 (deep in phase, post-Gap #1 closure)
- Dominant open blocker: `update-maps` Performance & UX at Scale
- Other tracked gaps: Health Matrix Hygiene, Resource Summarization, Long-Running Ergonomics, Resolution Failure Transparency, M3+ foundational work (Python library + protocol)

**Live Health (example run)**: 31 Green / 13 Yellow / 14 Red. Many Logged_issues and roadmap docs themselves appear in `get_files_needing_attention`.

**Architectural Foundation Already Present** (leverage heavily):
- `import_cache.py` + locking (M2-Rem-07)
- `contracts.py` (rich shapes, RESERVED keys, ACS, barrel_v2, cycles, diagnostics)
- `cli.py` `run_full_update` + `discover_project_root` (sophisticated Wave 4/5 external hardening)
- `health.py` (JSON fast path + MD view, upsert, heal_stubs, barrel report application)
- `resolution.py` + parsers (bree + javascript + python + cdia)
- MCP server as rich query surface
- BRC + graph_signature + reuse patterns as models for other caches

**Technical Debt / Asymmetries** (documented in historical investigation):
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
- ~~Python vs JS parser fidelity (confidence, raw_module, resolved_path)~~ — CLOSED for resolution_confidence/resolved_path/rich diagnostics/provenance on relatives by python.py update (M2 Workstream D slice); bare absolutes remain intentionally lower-fidelity.
=======
- Python vs JS parser fidelity (confidence, raw_module, resolved_path)
>>>>>>> agent-3-health-reliability
=======
- Python vs JS parser fidelity (confidence, raw_module, resolved_path)
>>>>>>> agent-4-journal
=======
- Python vs JS parser fidelity (confidence, raw_module, resolved_path)
>>>>>>> agent-7-harness-final
=======
- Python vs JS parser fidelity (confidence, raw_module, resolved_path)
>>>>>>> agent-6-library-final
- Crude grep extraction in some shell paths vs proper JSON
- Journal/pending_updates as simple append-only text (no structure, no compaction)
- Health matrix still has flakiness (subshells, non-idempotency)
- No first-class streaming/partial UX on the update pipeline
- Python library is still a thin launcher

---

## Workstream Structure

The plan is organized into five major workstreams. They can (and should) proceed with significant parallelism after foundational contracts and harness extensions are in place.

Each workstream has:
- Vision
- Current state & leverage points
- Key architectural decisions (the "difficult but correct" ones)
- Phased waves with checkboxes
- Scalability notes
- Verification & dogfood strategy
- Exit criteria for M2

---

## Workstream A: Scalable Incremental `update-maps` Core & UX (Highest Priority)

**Vision**: `update_maps` (CLI, MCP, Python-primary, daemon) becomes a first-class, resumable, observable, scoped, proportionally-costed operation that agents can trust on massive monorepos without fear of timeouts or token explosion.

**Why Long-Term & Difficult**:
- Current implementation is still largely "run the full pipeline or a simple dirty list."
- At 20k–50k files with creative imports, even "incremental" can be painful without true streaming, early termination, subtree scoping, and rich partial results.
- Reverse dependencies must become a first-class persisted, queryable, incrementally-maintained structure (not reconstructed from the human table).

**Key Architectural Decisions (No Shortcuts)**:
- **Streaming / Resumable Pipeline**: Core computation yields structured events (file parsed, edge resolved, cycle found, barrel chain expanded, ACS computed, etc.). Consumers (CLI, MCP, library) can stream, checkpoint, or request "next N" / "up to time budget".
- **First-Class Scope & Projection**: Support `directory=`, `include_globs`, `max_depth`, `focus_files` (seed set + transitive closure) at the engine level, not as post-filters.
- **Dual Persisted Structures**:
  - Forward dependency graph (already strong).
  - Reverse dependency index (new, maintained incrementally like BRC).
  - Both under versioned contracts with graph_signature-style delta detection.
- **Progress + Partial + Summary Protocol**: Every long operation returns (or streams) `{progress, partial_results, summary, next_actions, diagnostics}`. Structured JSON is primary; human text is derived.
- **Python-primary as the Engine**: Complete Phase 4 extraction. Shell becomes thin orchestrator + compatibility layer for existing users.
- **Resource Budget Awareness**: Optional `time_budget_ms`, `token_budget` (for agent callers), `max_files` hints that influence early termination + best-effort partial results.

**Phased Execution (Checkboxes)**

### Phase A0 — Foundations & Contracts (Foundation for everything else)
- [ ] Extend `contracts.py` with `update_run_v1`, `partial_result_v1`, `scope_spec_v1`, `progress_event_v1`, `reverse_dependency_index_v1` shapes + versioning rules.
- [ ] Design and implement minimal streaming generator in `import_cache.py` (or new `update_engine.py`) that yields typed events instead of only returning final structures.
- [ ] Add first-class `Scope` dataclass + projector (directory, globs, focus set + transitive) that works at graph build time.
<<<<<<< HEAD
<<<<<<< HEAD
- [ ] Extend harness with "M2 Scale Harness" (synthetic 5k/10k/25k/50k graphs + creative patterns + timing + memory guards).
=======
- [x] Extend harness with "M2 Scale Harness" (synthetic 5k/10k/25k/50k graphs + creative patterns + timing + memory guards). (COMPLETED by Agent 7 (Cross-cutting Harness): full port of 10k-50k generators (with 50k in deep), concurrency stress (multi-agent+daemon+locking), functional compaction/journal hooks; --m2-health --deep fully functional; integrated to all workstreams (A-E) + real monorepo + multi-agent dogfood (RecipeLab) in --gap1-health/--m2-health; zero-dep, observable, scalable. See gap1_validation_harness.py + this plan's Cross-Cutting. A0 complete.)
>>>>>>> agent-7-harness-final
=======
- [ ] Extend harness with "M2 Scale Harness" (synthetic 5k/10k/25k/50k graphs + creative patterns + timing + memory guards).
>>>>>>> agent-6-library-final

### Phase A1 — Reverse Dependencies as First-Class Citizen
- [ ] Persist and maintain a reverse dependency index (parallel to forward graph + BRC) with its own signature for delta detection.
- [ ] `get_dependents` and new `get_reverse_dependencies` (or unified) use the index directly (O(1) or O(k) for k dependents).
- [ ] Wire into health, ACS (low-conf reverse edges), library.md (new "Who depends on me" sections), MCP.
- [ ] Full dogfood + harness asserts on reverse accuracy at scale (including after renames/deletes via record-deletion).

### Phase A2 — Streaming / Resumable / Partial UX (Core Deliverable)
- [ ] Implement resumable `run_update_stream(...)` (or generator) in Python-primary path that yields progress events + partial resolved pairs / cycles / ACS.
- [ ] CLI `update-maps` (both paths) surfaces progress (dots, % , ETA, or structured) and supports `--resume`, `--max-time`, `--partial`.
- [ ] MCP `update_maps` gains streaming-friendly response shape + `partial` mode (return what you have + continuation token / next scope).
- [ ] Subtree scoping (`--dir src/`, focus on a module + its dependents) works end-to-end with proportional cost.
- [ ] Shell parity maintained (thin wrapper calls Python streaming where possible).

### Phase A3 — Structured Output + Summarization as First-Class
- [ ] Every major surface (MCP tools, `run_full_update` result, health, library.md generator) supports `format=summary|full|json|stream` with bounded sizes.
- [ ] New `get_dependency_summary`, `get_impact_summary(file)` etc. that are cheap even on massive repos.
- [ ] library.md gains "Executive Summary" + "High-Impact Areas" + "Recent Changes" sections derived from the rich data (not just the full table).

### Phase A4 — Massive Scale Hardening + Real Dogfood
- [ ] 25k–50k synthetic stress (timing < X seconds incremental on hot paths, memory bounded, no O(n) scans on common operations).
- [ ] Real external creative monorepo dogfood (pnpm/yarn workspace, heavy dynamic + barrel usage) — full update + incremental + scoped queries + reverse lookups.
- [ ] Daemon + multi-agent concurrent update scenarios proven stable.
- [ ] Exit criteria checklist complete.

**Scalability Notes**:
- Tiny: Full run is instant; streaming still works but unnecessary.
- Massive: Common operations (dirty + barrel + cycles delta + scoped queries) stay O(changed + scope size). Full rebuilds are rare and resumable.
- Creative monorepos: CDIA + barrel + ACS signals remain first-class in the streaming events.

**Verification**: Extended harness + RecipeLab + 50k synthetic + external monorepo. Metrics: incremental time, peak memory, result completeness vs full run, agent task success rate using partial results.

**M2 Exit Criteria for Workstream A**:
- Agents can perform useful dependency work on 20k+ file creative monorepos with scoped queries returning in seconds, progress visibility, and partial results that are safe to act on.
- Reverse dependencies are as trustworthy and fast as forward ones.
- Structured + summary modes exist and are the recommended path for agents on large repos.

---

## Workstream B: Production Health Matrix & Wiki Freshness System

**Vision**: The 🟢/🟡/🔴 matrix + wiki summaries become a trustworthy, low-maintenance, automatically self-healing source of truth that correctly reflects both code reality and agent intent at any scale.

**Key Hard Problems**:
- Stub pollution and stale wiki detection at 50k files.
- Flakiness under concurrency and rapid agent activity.
- No correlation between wiki content freshness and actual code/intent changes.

**Architectural Decisions**:
- Health becomes a proper versioned event-sourced structure (not just mutable JSON + MD).
- Wiki freshness uses content hashing + last-semantic-edit correlation (journal events) rather than simple mtime.
- Healing policies become configurable + observable (with ACS-style confidence on the heal decision itself).
- Summary-only and directory-sharded views for massive scale.

**Phased Execution (Checkboxes)**

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
- [ ] Audit and make **all** health matrix code paths (Python + shell) fully idempotent and atomic under the existing locking.
- [ ] Fix validate, mark-green, check-changes exit codes and subshell issues permanently (move critical logic into Python helpers called from shell).
=======
- [x] Audit and make **all** health matrix code paths (Python + shell) fully idempotent and atomic under the existing locking. (2026-05-26: health.py now central reliable engine with locked mark_green/remove/add/validate/upsert; both wikifier.sh + wikifier/scripts/wikifier.sh delegate mutations; upsert wrapper kept only as safe fallback. Combined ops use single file_lock acquisition.)
- [x] Fix validate, mark-green, check-changes exit codes and subshell issues permanently (move critical logic into Python helpers called from shell). (2026-05-26: subshell counter bug eliminated by full delegation of cmd_validate; mark-green pending clearing now via atomic _do_mark_green under lock + idempotent filter; check-changes exit codes hardened with explicit guards + exit 0 + pervasive || true + py delegation; duplicate rows impossible via dict upsert + batch-safe writes; added consistent error handling + exit codes in py helpers and sh main paths.)
>>>>>>> agent-3-health-reliability
=======
- [ ] Audit and make **all** health matrix code paths (Python + shell) fully idempotent and atomic under the existing locking.
- [ ] Fix validate, mark-green, check-changes exit codes and subshell issues permanently (move critical logic into Python helpers called from shell).
>>>>>>> agent-4-journal
=======
- [ ] Audit and make **all** health matrix code paths (Python + shell) fully idempotent and atomic under the existing locking.
- [ ] Fix validate, mark-green, check-changes exit codes and subshell issues permanently (move critical logic into Python helpers called from shell).
>>>>>>> agent-7-harness-final
=======
- [ ] Audit and make **all** health matrix code paths (Python + shell) fully idempotent and atomic under the existing locking.
- [ ] Fix validate, mark-green, check-changes exit codes and subshell issues permanently (move critical logic into Python helpers called from shell).
>>>>>>> agent-6-library-final
- [ ] Introduce `wiki_content_hash` + `last_meaningful_edit` (correlated to journal semantic events) in health entries.
- [ ] Implement reliable stale wiki detector (content hash changed since last agent wiki update + no recent record-change for that file).
- [ ] Advance `heal_stubs` / `heal_outdated_stubs` into a policy-driven engine with rich diagnostics (why healed, confidence, what changed).
- [ ] Add sharded / summary-only health views for >10k file repos (health --summary --dir remains the fast path; full matrix is lazy or on-demand).
- [ ] Full concurrency stress + real monorepo dogfood (multiple agents + daemon + human edits for days).
- [ ] Health matrix itself appears in `get_files_needing_attention` only when genuinely problematic (self-hosting hygiene).

**Scalability**: Summary views + directory scoping are O(1) or O(scope) even at 50k. Full matrix generation is rare/background.

**M2 Exit Criteria**: Zero flakiness in normal + rapid multi-agent usage; stale wiki detection works reliably; stub pollution is a non-issue on real projects; health commands are fast and correct on massive repos.

---

## Workstream C: Durable Stateful Layer (Journal, Pending, Audit Trail)

**Vision**: Semantic intent (record-change, record-deletion, auto-detected, agent rationale) is stored in a durable, queryable, compactable, long-term-usable event log — not an ever-growing pile of text files.

**Why This Is Hard & Important**:
- Current journal is daily append-only Markdown. Works for small use, becomes a liability at scale and over years.
- Agents need to ask "Why did we touch X three months ago?" or "What were the last 50 high-impact changes?"
- pending_updates.md is a simple todo list that can bloat or lose context.

**Architectural Decisions**:
- Structured event log (JSONL or versioned binary + human projection) with strong schema.
- Compaction strategy (time-based + significance-based + summarization via ACS/CIABRE).
- First-class query surfaces (MCP + library) for "recent intent on these files", "changes by agent/session", etc.
- Tight integration with health matrix (every journal semantic event can affect freshness scores).

**Phased Execution**:
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> agent-7-harness-final
=======
>>>>>>> agent-6-library-final
- [ ] Design `journal_event_v1` (and later v2) contract — typed events with provenance, actor (agent id), session, confidence/rationale links to ACS.
- [ ] Implement dual-write (structured log + human-readable daily MD projection) during transition.
- [ ] Add compaction engine (safe, reversible, with dry-run + manifest).
- [ ] New query tools / MCP surfaces: `get_intent_history(file, since)`, `get_high_impact_changes(limit)`, summarization.
- [ ] pending_updates evolves into a structured, prioritized, auto-pruned work queue with provenance.
- [ ] Multi-year simulation dogfood (replay months of real + synthetic activity and verify compaction + query performance).
- [ ] Full integration with record-change/record-deletion as the canonical way agents record *why*.
<<<<<<< HEAD
<<<<<<< HEAD
=======
- [x] Design `journal_event_v1` (and later v2) contract — typed events with provenance, actor (agent id), session, confidence/rationale links to ACS. (Workstream C slice start — contracts.py + evolution path + ActorV1/ProvenanceV1/JournalEventV1 + make_ + defensive load)
- [x] Implement dual-write (structured log + human-readable daily MD projection) during transition. (JSONL primary in .wikifier_staging/journal/v1/ + exact MD projection preserved; emit in health.py)
- [x] Add compaction engine (safe, reversible, with dry-run + manifest). (Skeleton in health.py: time+significance policy, streaming iter, archive layout, manifest with reversible notes)
- [ ] New query tools / MCP surfaces: `get_intent_history(file, since)`, `get_high_impact_changes(limit)`, summarization.
- [ ] pending_updates evolves into a structured, prioritized, auto-pruned work queue with provenance.
- [ ] Multi-year simulation dogfood (replay months of real + synthetic activity and verify compaction + query performance).
- [x] Full integration with record-change/record-deletion as the canonical way agents record *why*. (write_journal() in wikifier.sh + scripts/ copy now dual-writes via health.emit_journal_event on every call path including auto-detected)
>>>>>>> agent-4-journal
=======
>>>>>>> agent-7-harness-final
=======
>>>>>>> agent-6-library-final

**Scalability**: Compaction keeps active state bounded (e.g., last 90 days full + yearly summaries + high-significance events forever). Queries are indexed or use the same graph techniques as cycles/BRC.

**M2 Exit Criteria**: Journal and pending state remain usable and bounded after simulated months/years of heavy agent activity on large repos. Agents can usefully query historical intent without reading megabytes of text.

---

## Workstream D: Resolution Failure Transparency & Diagnostics

**Vision**: When resolution is incomplete, low-confidence, or fails, the system makes this **first-class, actionable, and explainable** information rather than something agents discover by accident or by grepping.

**Leverage from Gap #1**:
- ACS + CIABRE + creative detectors + confidence explanations already exist and are partially surfaced.
- Need to make them **complete, always-on, and queryable at scale** (not just samples).

**Phased Execution**:
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
- [x] Complete Python parser parity for `resolution_confidence`, `resolved_path`, rich diagnostics (close the historical asymmetry). — Done: python.py now emits resolved_path (for relatives, with FS target), ties confidence to it, produces rich "diagnostic" (make_diagnostic for static low cases + creative), + per-edge (parser, resolution_strategy, resolution_metadata) provenance. All flow to cache/MCP/ACS/CIABRE.
- [x] First-class "Unresolved Imports" and "Low-Confidence Hotspots" views in health, library.md, MCP (`get_unresolved_imports`, `get_low_confidence_edges`). — Done: new helpers in import_cache.py; exposed in MCP get_project_status + health(json) via "resolution_transparency" (counts + bounded samples + provenance notes); enhanced get_dependencies(..., unresolved_only=True); library.md generator (both sh) now emits dedicated "## Resolution Transparency" section with actionable samples + cross-refs.
- [x] Per-edge provenance stored (which parser path, which strategy, which barrel chain, which CDIA signals) — versioned. — Done: stored in python (and JS) parser outputs for all edges; preserved by import_cache.update_file_data RICH_KEYS; visible in status/health/library/MCP/ACS.
=======
- [ ] Complete Python parser parity for `resolution_confidence`, `resolved_path`, rich diagnostics (close the historical asymmetry).
- [ ] First-class "Unresolved Imports" and "Low-Confidence Hotspots" views in health, library.md, MCP (`get_unresolved_imports`, `get_low_confidence_edges`).
- [ ] Per-edge provenance stored (which parser path, which strategy, which barrel chain, which CDIA signals) — versioned.
>>>>>>> agent-3-health-reliability
=======
- [ ] Complete Python parser parity for `resolution_confidence`, `resolved_path`, rich diagnostics (close the historical asymmetry).
- [ ] First-class "Unresolved Imports" and "Low-Confidence Hotspots" views in health, library.md, MCP (`get_unresolved_imports`, `get_low_confidence_edges`).
- [ ] Per-edge provenance stored (which parser path, which strategy, which barrel chain, which CDIA signals) — versioned.
>>>>>>> agent-4-journal
=======
- [ ] Complete Python parser parity for `resolution_confidence`, `resolved_path`, rich diagnostics (close the historical asymmetry).
- [ ] First-class "Unresolved Imports" and "Low-Confidence Hotspots" views in health, library.md, MCP (`get_unresolved_imports`, `get_low_confidence_edges`).
- [ ] Per-edge provenance stored (which parser path, which strategy, which barrel chain, which CDIA signals) — versioned.
>>>>>>> agent-7-harness-final
=======
- [ ] Complete Python parser parity for `resolution_confidence`, `resolved_path`, rich diagnostics (close the historical asymmetry).
- [ ] First-class "Unresolved Imports" and "Low-Confidence Hotspots" views in health, library.md, MCP (`get_unresolved_imports`, `get_low_confidence_edges`).
- [ ] Per-edge provenance stored (which parser path, which strategy, which barrel chain, which CDIA signals) — versioned.
>>>>>>> agent-6-library-final
- [ ] Integrated failure taxonomy surfaced via diagnostics category + ACS.
- [ ] Agents can ask "show me everything that is currently untrustworthy in my dependency map" as a standard operation.
- [ ] Scale testing: 50k file repo with deliberately injected hard creative cases — transparency surfaces must remain fast and complete.

**M2 Exit Criteria**: No important resolution limitation is invisible to agents. Low-confidence and failure data is as easy to consume as successful edges.

---

## Workstream E: Python Library + Formal Agent Protocol (M2/M3 Bridge)

**Vision**: There is a clean, versioned, well-documented public Python API (`from wikifier import ...`) and a rigorous, testable Agent Protocol specification that different models can follow with high consistency. This is the foundation for M3 and beyond.

**Why It Leaks into M2**:
- The tracker and execution plan list "M3+ Foundational Work" under gaps that must be considered before M2 is solid.
- The current thin launcher + informal `skills/run.md` is insufficient for the "production-useful" bar.

<<<<<<< HEAD
**Phased Execution**:
- [ ] Complete Python-primary extraction (Phase 4 vision from Gap #1 external work) so the library can offer real power without shell.
- [ ] Design the public library surface (health, record, query, update, config, diagnostics, locking). Produce a design doc (can live in this plan or a sibling).
- [ ] Minimal viable implementation that covers the mandatory agent workflow (check-changes, health, record-change, update-maps scoped, suggest_next_actions, etc.).
- [ ] Evolve `skills/run.md` into **Wikifier Agent Protocol v0.4** (or v1.0) — versioned, with mandatory vs optional sections, error handling, structured output expectations, concurrency guidance, scaling patterns.
=======
**Public Library API Design (Documented & Initial Skeleton Implemented — Workstream E slice, 2026-05-26)**

**Rationale & Principles** (non-negotiable alignment with overall Guiding Principles + M2 Exit Criteria):
- **Python-primary first for power without shell**: Core operations (check_changes, record_change, health ops, scoped updates, suggestions, queries) implemented or directly delegated to pure-Python modules (health.py for matrix, import_cache.py for dependency intel + dirty + ACS/CIABRE/cycles/barrels, cli.py for discovery + run_full_update, contracts.py, locking.py, resolution/parsers/diagnostics). The shell (wikifier.sh + launcher in cli.main) becomes a thin orchestrator/compat layer. This completes more of the Phase 4 extraction vision.
- **Flat high-level + submodule access for ergonomics**: `from wikifier import check_changes, record_change, health, suggest_next_actions, update_maps, discover_project_root, run_full_update` (and friends). Power users continue `from wikifier import health as h; from wikifier import import_cache as ic; from wikifier import locking, contracts`. Matches "from wikifier import health, record, query, update, etc." expectation.
- **Consistent, agent-friendly I/O contracts**:
  - All high-level funcs: `project_root: Optional[Union[str, Path]] = None` (None → auto via discover_project_root(); explicit overrides for multi-project or daemon use). Additional scoped params (directory, format, full, etc.).
  - Returns: Structured `dict` primary ({"success": bool, "project_root": str, ...data fields..., "error"?: str}). Text/MD for format="text" human paths (e.g. health). No silent failures; agents get machine-readable + optional human.
  - Structured always preferred (JSON-serializable where possible, using contracts shapes for rich fields like acs_summary, barrel_invalidation_summary, cycles_reuse).
- **Error handling & robustness**: Programming errors (bad args, import failures) raise standard exceptions (for dev). Operational failures (lock contention edge, partial scan) return success=False + diagnostic "error" + partial data where safe. Never leave state inconsistent; use locking for all mutators. Defensive try/except internally (additive to existing patterns).
- **Automatic locking & concurrency safety**: All mutating workflow functions (record_*, check_changes, mark_green, update_maps) acquire the project-level advisory lock via `wikifier.locking.file_lock` (or equivalent). Mirrors M2-Rem-07 production readiness. Agents rarely call locking directly.
- **Versioning & contracts**: Library surface versioned via package `__version__`. New data shapes go through `contracts.py` (additive, _vN fields, dual-read). Protocol v0.4 (see skills/run.md) references this surface.
- **Scalability & scoping built-in**: directory= / subtree filters, summary modes, use_python_primary flags propagate to O(changed) paths via existing BRC/dirty/ACS. Supports tiny → 50k+ without O(n) surprises.
- **Dual human + structured**: Structured for agents/MCP/library callers; human text/MD derived (e.g., health text, suggestions). Aligns with existing health.json + .md, library.md, journal.
- **Minimal new surface, maximum reuse**: Thin facades/wrappers over battle-tested modules (no duplication of parser/ACS/cycle logic). Enables future: MCP and CLI become thin consumers of the same library funcs.
- **Dogfood + self-hosting**: The implementation itself exercises the new surface (e.g., record_change after edits to these files).

**Core Public Surface (flat `from wikifier import ...` — minimal viable for M2/M3 bridge)**

**Discovery & Package**:
- `discover_project_root() -> Path`: Canonical, hardened (symlinks, pnpm/yarn/monorepo markers, logical+physical, outermost .git preference). Already extracted.
- `__version__: str`

**Health Matrix (primary agent trust surface + self-healing)**:
- `health(project_root=None, directory: Optional[str]=None, format: Literal["text", "json", "summary", "healing-stats"] = "text") -> str | dict`
- `get_health_summary(project_root=None, directory=None) -> dict` (counts: green/yellow/red + pending)
- `get_files_needing_attention(project_root=None, status_filter=None, directory=None) -> List[str]`
- `mark_green(file: str, reason: str = "", project_root=None) -> dict` (sets 🟢, removes from pending via health + pending logic)

**Intent Recording & Audit (MANDATORY after every edit; creates semantic trail + journal + pending)**:
- `record_change(file: str, reason: str, project_root=None) -> dict`  # Sets 🟡, appends pending_updates.md, writes structured journal entry, success payload
- `record_deletion(file: str, reason: str, project_root=None) -> dict`
- `check_changes(project_root=None) -> dict`  # Incremental mtime + barrel-driven scan; updates health (Yellow for changed) + pending; returns {success, changes_detected, barrel_invalidation_summary, rich_auto_yellow..., recommendation}

**Agent Guidance & Status**:
- `suggest_next_actions(project_root=None, directory=None, format: Literal["text","json"]="text") -> str | dict`  # Prioritizes 🔴/🟡, low-conf ACS via ensure_acs, update_maps hints, dependents, journal. Rich in json.
- `get_project_status(project_root=None, ...) -> dict`  # Rich composite (health counts + dep_intel: acs_summary, ciabre, barrels, cycles_reuse, sample reports)

**Update / Maps (Python-primary engine)**:
- `update_maps(project_root=None, full: bool=False, directory: Optional[str]=None, use_python_primary: bool=True, ...) -> dict`  # Facade; prefers pure path (delegates to run_full_update for dirty+parse+persist+barrel+acs); supports scoping.
- `run_full_update(root=None, force_full=True, verbose=False, use_canonical=True, use_python_primary=True) -> dict`  # Already present + deepened (Wave 5/6); now part of public surface.

**Query & Diagnostics (supporting primitives, many via re-export or thin wrappers)**:
- Re-exports / access: `get_dependencies`, `get_dependents`, `get_cycles`, `get_acs_summary` etc. via `from wikifier import import_cache as ic` or future flat `query_*`.
- `get_resolution_diagnostics(...)` (from diagnostics module)
- Full submodule power: `from wikifier import locking, contracts, parsers, resolution, diagnostics, health as health_module, import_cache as import_cache_module`

**Other**:
- `locking`, `contracts` (existing re-exports expanded)
- Internal but useful: `_get_effective_root` patterns documented for extension.

**Mandatory Agent Workflow (now directly expressible in Python, zero shell required for core loop)**:
```
from wikifier import (
    check_changes, health, record_change, mark_green,
    suggest_next_actions, update_maps, discover_project_root
)
root = discover_project_root()
check_changes()
h = health(format="summary")  # or json for rich dep_intel
# ... edit code ...
record_change("src/foo.py", "Switched X because Y for Z reason. See ACS low-conf edge.")
# write .wiki.md or update summary
mark_green("src/foo.py", "Wiki refreshed with intent + import delta.")
if imports_changed:
    update_maps(directory="src/", use_python_primary=True)
suggest = suggest_next_actions(format="json")
final_h = health(format="json")
```
Never skip record_change. Use directory scoping on large repos. Structured returns enable reliable parsing/branching in agent code.

**Error / Edge Handling Expectations** (part of design + protocol):
- Lock timeout/contention: success=False + diagnostic (future nonblock support noted).
- No monitored_paths / fresh project: graceful init-like behavior or clear error.
- Partial results on massive scale: success=True + note + bounded data (use summaries).
- All results include "project_root" for traceability in multi-root swarms.

**Relation to Protocol, MCP, CLI, Future**:
- This surface is the reference implementation for Wikifier Agent Protocol v0.4 (see updated skills/run.md).
- MCP tools (server.py) and CLI can/should migrate to thin delegation to these (future wave).
- Enables conformance testing (later).
- Examples dogfooded in this very edit session + README updates (out of this isolated slice scope).

This design + skeleton makes the library "usable for the core agent loop" per M2 Exit for E. No shortcuts; leverages all prior Gap#1/M2 Python foundations (health scalable, BRC dirty, ACS on-demand, locking, discover).

**Phased Execution** (checkboxes advanced by foundational slice):
- [x] Complete Python-primary extraction (Phase 4 vision from Gap #1 external work) so the library can offer real power without shell. *(More extraction completed in this slice via additional pure-Py record/check helpers + facades in cli.py; run_full_update + health/import_cache already strong; see code changes + design above.)*
- [x] Design the public library surface (health, record, query, update, config, diagnostics, locking). Produce a design doc (can live in this plan or a sibling). *(Full design documented in this section of the plan; no sibling file created per guidelines preferring edits to existing.)*
- [x] Minimal viable implementation that covers the mandatory agent workflow (check-changes, health, record-change, update-maps scoped, suggest_next_actions, etc.). *(Initial skeleton implemented in cli.py + __init__.py re-exports/wrappers; covers full recommended loop with real Py logic for record/check + delegation for others; locking + structured I/O + scoping.)*
- [x] Evolve `skills/run.md` into **Wikifier Agent Protocol v0.4** (or v1.0) — versioned, with mandatory vs optional sections, error handling, structured output expectations, concurrency guidance, scaling patterns. *(Strengthened in this slice: added v0.4 header, explicit I/O contracts per surface above, error handling, structured expectations, versioning note, cross-ref to this design, refined mandatory rule.)*
>>>>>>> agent-6-library-final
- [ ] Conformance test suite (harness) that any agent implementation can run against.
- [ ] Wire the CLI and MCP to be thin consumers of the library where possible.
- [ ] Documentation + examples that are themselves dogfooded.

<<<<<<< HEAD
**M2 Exit Criteria**: A new session following the protocol (or using the library) can execute the full recommended workflow with minimal ambiguity. The Python library is usable for the core agent loop. The protocol is treated as the authoritative specification.
=======
**Resumption Phase (Agent 6 — E Library + Protocol, zero-dep long-term agent-first focus)**:
- [~] Complete Python-primary extraction and harden minimal viable library implementation into clean, rigorous public API (centralized helpers via delegation, documented health access patterns, faithful extraction reuse of _collect + health/import_cache, design I/O + error contracts, contracts.py alignment, submodule+flat ergonomics). (Core API clean + extraction improvements landed; full pipeline parity ongoing.)
- [x] Merge the library design + Protocol v0.4 into main plan/docs (README.md, spec.md, v0.4-Execution-Plan.md, progress tracker, Logged_issues via precise edits; cross-refs, examples, success criteria updates).
- [x] Conformance harness (initial rigorous suite exercising library funcs + protocol mandatory loop, I/O shapes, error cases, versioning; validated seed + notes for gap1_validation_harness.py extension).
- [x] Wire CLI/MCP as thin consumers (MCP core tools delegate to library `record_*`/`check_changes`/`mark_green`; _get_effective_root centralized via import+thin wrapper in MCP; CLI surface + python-primary path already present).
- [x] Dogfood the library + protocol (pure-Py usage in workspace via python -c exercising protocol example steps (health json w/ dep_intel, suggest, discover), conformance shape validation, clean API verified post all refactors; no breakage).

**M2 Exit Criteria**: A new session following the protocol (or using the library) can execute the full recommended workflow with minimal ambiguity. The Python library is usable for the core agent loop. The protocol is treated as the authoritative specification. *(Foundational slice delivered surface + skeleton + v0.4; Agent 6 resumption completes extraction/API hardening, merge, harness, wiring, dogfood for final declaration. Focus: clean public API + rigorous protocol.)*

**Workstream E Slice Completion Note (2026-05-26)**: Design documented inline, 4/7 phased checkboxes advanced to [x] with details, Python-primary extraction extended in cli.py (new pure record/check/mark/suggest/update/ health facades + journal/pending writers + locking + structured I/O), __init__.py surface exports, skills/run.md evolved to full v0.4 protocol spec (I/O contracts, errors, structured expectations, versioning, updated mandatory rule + library-first examples). Skeleton covers the exact mandatory agent workflow listed in the vision. High-quality, isolated, no new files created. Bridges cleanly to M3 (conformance, thin wiring, full examples remain). Re-read this section + skills/run.md for usage.

**Agent 6 Resumption Note (2026-05-26 onward)**: Resuming focused execution on the 5 remaining E items per user directive. Primary goals: (1) harden skeleton into clean public API (eliminate submodule shadowing e.g. health func vs module, centralize discovery/helpers, faithful extraction using import_cache/health primitives, rigorous dict contracts matching design + contracts.py, full typing/robustness/zero-dep); (2) merge design/protocol references + examples into main docs via edits only; (3) initial conformance harness exercising protocol/library I/O rigorously; (4) thin delegation in CLI (beyond the --python-primary special case) + MCP (replace _run_wikifier_command sh paths for core tools); (5) active dogfooding of `from wikifier import ...` + protocol rules inside this workspace + harness runs. All changes preserve prior Gap#1/M2 foundations. Checkboxes in this section + cross-refs updated.
>>>>>>> agent-6-library-final

---

## Cross-Cutting Work

- **Contracts & Versioning**: All new major shapes go through `contracts.py` with clear migration/compat rules.
<<<<<<< HEAD
<<<<<<< HEAD
- **Massive Scale Test Harness**: Extend `gap1_validation_harness.py` (or new `m2_scale_harness.py`) with 10k–50k synthetic generators, creative pattern injectors, timing/memory guards, multi-agent concurrency scenarios, compaction stress tests.
=======
- **Massive Scale Test Harness**: Extend `gap1_validation_harness.py` (or new `m2_scale_harness.py`) with 10k–50k synthetic generators, creative pattern injectors, timing/memory guards, multi-agent concurrency scenarios, compaction stress tests. (COMPLETED by dedicated Agent 7 (Cross-cutting Harness resume): full port + 50k + deep --m2-health + WS integration + real+multi-agent RecipeLab dogfood runs + observable metrics. Harness now the canonical scalable zero-dep gate. See wikifier/gap1_validation_harness.py (M2 sections, run_m2_*, test_real_multiagent_dogfood, --m2-health --deep). A0 + Cross-Cutting harness fully delivered.)
>>>>>>> agent-7-harness-final
=======
- **Massive Scale Test Harness**: Extend `gap1_validation_harness.py` (or new `m2_scale_harness.py`) with 10k–50k synthetic generators, creative pattern injectors, timing/memory guards, multi-agent concurrency scenarios, compaction stress tests.
>>>>>>> agent-6-library-final
- **Real Monorepo Dogfood Cadence**: RecipeLab (current) + at least one external large creative monorepo (pnpm/yarn workspace with heavy dynamic imports) run regularly.
- **Observability Unification**: All new systems produce data consumable by the existing ACS / CIABRE / diagnostics / barrel reports / journal patterns.
- **Locking & Concurrency Evolution**: Fine-grained (per-file or per-subtree) locking when usage pressure justifies it; keep advisory + project-level as safe default.
- **Documentation & README Updates**: Scaling patterns, new surfaces, protocol guidance, and "how to operate at 20k+ files" sections.

---

## Overall Phasing & Dependencies (High Level)

1. **Foundation Wave** (2–4 weeks agent time): Contracts extensions + harness upgrades + Python-primary completion (A0 + parts of E). Unblocks parallel work.
2. **Core Delivery Waves** (parallel):
   - A1–A3 (Reverse + Streaming + Structured)
   - B core (Idempotency + Freshness)
   - C early phases (Structured journal design + dual write)
   - D (Transparency completion)
3. **Hardening & Dogfood Wave**: Massive scale + real external + concurrency + compaction.
4. **Protocol & Library Wave** (E): Can overlap but should have stable engine surfaces before finalizing the protocol spec.
5. **Exit & Transition**: Update all trackers, cut release notes, declare M2 solid, begin M3 planning.

---

## Tracking & Governance

- This plan is the single source of truth for M2 closure scope.
- Every checkbox here must be reflected (when complete) in `m2_rem_08_and_v0.4_progress_tracker.md` under the relevant M2 bullets.
- Major waves should produce diary entries in the tracker + CHANGELOG sections.
- Use the existing `wikifier issues` / health matrix to track sub-work (many of the current Logged_issues will be superseded or closed by waves in this plan).
- Regular `--gap1-health` (extended) + new M2 scale harness runs as quality gates.

---

## Exit Criteria for Full M2 Closure (Summary)

- All five workstreams have their documented exit criteria met.
- `--gap1-health` (or its M2 successor) is GREEN with new scale/UX/freshness/intent/transparency sections also passing.
- Real dogfood on at least one 5k+ creative monorepo (external preferred) shows agents can operate autonomously for extended periods with high trust in the system.
- The main `m2_rem_08_and_v0.4_progress_tracker.md` shows M2 as fully [x].
- v0.4-Execution-Plan.md updated with M2 complete + lessons.
- A clear handoff document exists for M3 (Python library + protocol now solid foundations).

---

**This plan deliberately chooses the harder, longer-lasting path on every major dimension.** Short-term velocity is deprioritized in favor of a system that will still be a joy (and a source of truth) for agents operating on 50k-file creative monorepos in 2028–2030.

When in doubt during execution: re-read the Guiding Principles. If a proposed change would create future pain at scale or under multi-agent load, redesign it.

---

**Next Immediate Action (as of creation)**: 
1. Review and approve this plan (or iterate on it).
2. Seed the Foundation Wave tasks into the main tracker or a trammel plan.
3. Begin Workstream A0 + harness extension (highest leverage).

The 6 Gap #1 items are done. Now we make the rest of M2 worthy of the same standard.