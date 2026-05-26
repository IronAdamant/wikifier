# Gap #1: Dependency Intelligence Quality — 4-Phase Long-Term Closure Roadmap

**File Type**: Living `_open` architectural synthesis and implementation roadmap  
**Created**: 2026-05-17  
**Last Updated**: 2026-05-17 (immediately after completion of all four dedicated long-term planning sub-agents)  
**Status**: Open — Ready for review and phased execution  
**Owner**: Gap #1 Closure Program (M2-Rem-08 continuation)

---

## Executive Summary

After extensive parser improvements, the rich data pipeline fix, and multiple rounds of dogfooding, **Gap #1 (Dependency Intelligence Quality & Query Reliability)** remains the single largest blocker preventing Wikifier from being trusted for fully autonomous long-term operation on real-world (especially JavaScript/TypeScript-heavy) codebases.

In this session, four specialized long-term planning sub-agents were commissioned to produce rigorous, owner-grade architectural designs focused on **reliability and scaling** rather than quick fixes. All four have now delivered high-quality plans.

This document synthesizes those four independent designs into one coherent, sequenced, long-term program to finally close Gap #1 properly.

**Key Conclusion**:
- The four plans form a surprisingly coherent layered architecture.
- Phase 4 (Modern Resolution) is the true foundation.
- A disciplined 4-wave execution plan can deliver early agent-visible value while building durable infrastructure.
- The highest cross-cutting risk is the `wikifier.sh` pipe serialization + first-pass integration layer.

If executed well, this roadmap can take dependency intelligence from “mostly useful with known blind spots” to “production-grade, explainable, and trustworthy at monorepo scale.”

---

## Current State (Post Recent Work)

### What Has Been Hardened
- Rich parser metadata in `javascript.py` (Phases 1–4 of earlier work): `is_dynamic`, `dynamic_type`, `is_conditional`, `via_barrel`, `barrel_depth`, `barrel_chain`, confidence downgrades.
- End-to-end data pipeline (Fix 8 + data survival pass): Rich fields now reach `import_cache.py` and are partially visible in MCP tools.
- Reverse dependencies + basic consumers (Mermaid impact edges, `get_dependents` fast path).
- Health matrix auto-healing and debuggability (`WIKIFIER_DEBUG=1`).

### What Remains Weak (The 4 Hard Problems)
1. **Modern & Reliable Resolution** — Incomplete `package.json` `"exports"`, no `"imports"`, weak workspace/TS paths, symlink/monorepo fragility, duplicated logic across `javascript.py`, `bree.py`, and the shell.
2. **Deep Barrel Intelligence** — Barrel following is still mostly parse-time and importer-centric. Changes to barrels cause widespread staleness. Normal imports into barrels are only partially expanded.
3. **Conditional & Complex Dynamic Classification** — Still relies on crude 800-character lookback heuristics. Real-world patterns (feature flags, lazy wrappers, computed paths, aliases) produce too many opaque or wrong classifications.
4. **Graph Integrity (Cycle Detection)** — Almost non-existent beyond a tiny visited guard inside barrel following. No SCC analysis, no persistence, no exposure in tools or visualizations.

These four problems map directly to the four phases below.

---

## The Four Long-Term Architectural Plans

### Phase 1: Cycle Detection & Graph Integrity Layer
**Focus**: Production-grade, incremental, trustworthy cycle detection and graph integrity.

**Core Design**:
- Build in-memory dependency graph from rich `resolved_pairs` + `_reverse_dependencies`.
- Use **Tarjan’s SCC algorithm** (O(V+E)) as primary.
- Persist results under `_cycles` and `_graph_integrity` top-level cache keys.
- Normalize cycles to avoid duplicate reporting.
- Compute immediately after reverse-dependency persistence in the first-pass.
- Exposure: `get_cycles()` MCP tool, `wikifier cycles` CLI, dedicated section in `library.md`, red `cycleNode` styling in Mermaid.

**Long-term Priorities**: Incremental safety, canonical node identity, rich per-cycle metadata (dynamic/conditional participation), testing with synthetic + real graphs.

**Critical Files**: `import_cache.py`, `wikifier.sh`, `mcp/server.py`.

### Phase 2: Deep Barrel & Re-export Expansion System (BREE v2)
**Focus**: Turn barrel handling from a clever parse-time probe into reliable, cache-aware infrastructure.

**Core Design**:
- Promote `bree.py` (`BarrelReexportAnalysisEngine`) as the single source of truth.
- Introduce persistent `BarrelResolutionCache` with `mtimes_snapshot` per chain (decouples importer mtime from barrel freshness).
- First-class `ExpansionPolicy` (configurable depth, fanout, cost, smart stopping rules).
- Full propagation of `barrel_chain`, `barrel_detector`, per-hop traces.
- Invalidation protocol that detects changed barrels and triggers selective refresh or lazy re-expansion.
- Graceful partial results on broken chains.

**Critical Innovation**: Barrel expansion freshness is no longer tied to the importer’s file mtime.

**Critical Files**: `bree.py`, `javascript.py`, `wikifier.sh`, `import_cache.py`, `mcp/server.py`.

**Detailed Execution Plan**: See `Findings/gap1_deep_barrel_invalidation_longterm_strategy.md` for the zero-dependency 4-wave roadmap (delta invalidation, structured observability, daemon integration, pruning/GC + v1 canonical) that turns the BRC foundation into production-scale selective barrel invalidation. Wave 1 (O(changed) + deletion correctness) has begun.

### Phase 3: Robust Conditional & Complex Dynamic Import Intelligence (CDIA)
**Focus**: Replace brittle heuristics with a scalable, explainable, pluggable analysis subsystem.

**Core Design**:
- Registry-driven pluggable detectors (inspired by BREE).
- Lightweight multi-pass context builder (brace-aware scope nesting, predicate harvest, semantic tagging, limited dataflow).
- Rich structured output: `conditional_analysis` and `dynamic_analysis` containing `semantic_tags`, `analysis_trace`, `predicate_snippet`, `detectors_fired`, etc.
- Strong explainability and actionability (MCP filters, “why” explanations, integration with ACS and CIABRE).
- Never assign high/medium confidence to conditional or non-static dynamic edges.

**Key Advance**: Moves from “this import looks suspicious” to “this import is conditional because of feature flag X with 0.85 detector agreement — here is the exact predicate and evidence.”

**Critical Files**: `javascript.py`, `wikifier.sh`, `import_cache.py`, `mcp/server.py`, `diagnostics.py`.

### Phase 4: Modern Resolution Engine & Path Normalization Hardening
**Focus**: Make resolution the single source of truth and future-proof it for real monorepos.

**Core Design**:
- Centralize all resolution in `resolution.py` using the existing `ResolutionStrategy` + `ProjectContext` architecture.
- Full pragmatic support for `package.json` `"exports"` and `"imports"` fields, workspace resolution, `tsconfig.json` paths, and pnpm/Yarn monorepo layouts.
- Strong canonical form contract (physical by default for graph nodes + rich logical metadata).
- Rich `Resolution` objects carrying strategy, matched conditions, symlink info, etc.
- Parsers, BREE, and the shell delegate to the central engine.

**Strategic Stance**: Stay pure Python for the next 5–10 years; use pluggable strategies to avoid special-case accretion.

**Critical Files**: `resolution.py`, `javascript.py`, `bree.py`, `wikifier.sh`, `import_cache.py`.

---

## Integrated Dependency & Sequencing Analysis

**Strong Dependencies**:
- Phase 2 (Barrels) has a **strong** dependency on Phase 4 (authoritative resolution for hops and exports handling).
- Phase 1 (Cycles) has a **strong** dependency on stable canonical node identities from Phase 4.
- Phases 2 and 3 both need excellent pipeline propagation and cache patterns.

**Softer Dependencies**:
- Phase 3 benefits from `ProjectContext` symbols (Phase 4) for better dataflow analysis.
- All phases benefit from rich, stable edges produced by the others.

**Recommended Execution Order** (4-Wave Program):

**Wave 1 – Foundation (Resolution First)**
- Phase 4.1 (Centralization) + early wiring
- Goal: Every resolution call goes through a trustworthy engine with canonical output.

**Wave 2 – Data Richness (Propagation Wins)**
- Phase 2.1 (full `barrel_chain` survival)
- Phase 3.1–3.2 (CDIA core + pipeline propagation)
- Goal: Agents can immediately see richer barrel, conditional, and dynamic signals.

**Wave 3 – Intelligence & Caching Layers**
- Phase 2.2–2.3 (BREE policy + persistent barrel cache + invalidation)
- Phase 3.3 (CDIA integrations with ACS/CIABRE)
- Phase 4.2–4.3 (modern features + monorepo hardening)
- Early Phase 1 (graph building + Tarjan SCC)

**Wave 4 – Integrity, Consumers & Hardening**
- Full Phase 1 (persistence, MCP, Mermaid, library section)
- Consumer surfaces and explanations for Phases 2 & 3
- Phase 4.4–4.6 (perf, deprecation, testing)
- Full dogfood and metrics

This order balances early value with proper architectural sequencing.

---

## Shared Infrastructure & Cross-Cutting Contracts (Critical)

The four plans repeatedly touch the same sensitive areas. These must be designed **once**:

1. **Rich Metadata & Analysis Contract**
   - Consistent shapes for `*_analysis`, `analysis_trace`, `diagnostic`, resolution `metadata`.
   - Semantic tag vocabulary and detector naming conventions.

2. **Shell Pipeline Serialization Strategy**
   - How to carry complex nested structures through the `|` pipe in `wikifier.sh` without breaking old cache lines.
   - Recommended approach: versioned b64/JSON fields with extremely defensive parsing.

3. **Cache Extension & Invalidation Patterns**
   - How `RICH_KEYS`, top-level keys (`_cycles`, `_barrel_resolutions`, etc.), and mtime logic evolve together.
   - Coherent invalidation protocol across resolution contexts, barrels, and importers.

4. **Diagnostics & Explainability Layer**
   - Unified way to attach traces and suggestions that flow to agents via MCP and `library.md`.

5. **Lightweight Configuration Mechanism**
   - Single place for barrel policies and CDIA predicate registries.

**Strong Recommendation**: Before any Wave 1 code is written, run a short “Metadata & Pipeline Contract v2” design session.

---

## Risk Register

| Risk | Impact | Likelihood | Primary Mitigation |
|------|--------|------------|--------------------|
| Pipe serialization fragility during propagation | High | High | Define defensive serialization strategy in Wave 0 / pre-Wave 1 |
| Cache invalidation complexity (especially barrels) | High | Medium | Treat invalidation as a single coherent design, not per-phase |
| Over-pluggability before proving value | Medium | Medium | Start with small registries; add extension points only on demonstrated need |
| Silent regressions on legacy/flat projects | Medium | Medium | Golden fixtures + property tests from the beginning |
| Agent confusion during multi-wave transition | Medium | High | Keep all legacy fields; make new structured fields additive |
| Scope creep on Phase 4 (full Node resolver) | Medium | Low | Explicitly bound to “pragmatic production subset” |

---

## Definition of “Gap #1 Closed”

Gap #1 is considered closed when:

- On real 5k–20k+ file mixed-language monorepos, `get_dependencies()` and `get_dependents()` return results that experienced agents (and humans) judge to be **reliable enough to act on without constant cross-checking** of the underlying source.
- Barrel changes no longer cause widespread silent staleness.
- Conditional and dynamic imports are classified with useful semantic tags and explanations at least 80–85% of the time.
- Cycle detection surfaces the important tangles with actionable context.
- Resolution is stable across pnpm/Yarn workspaces and modern `exports` usage.
- All of the above is achieved with clean, maintainable, debuggable code that has clear ownership and evolution paths.

---

## References

- Four original sub-agent design documents (available via their task outputs):
  - Phase 1: Cycle Detection
  - Phase 2: Barrel Expansion (BREE v2)
  - Phase 3: Conditional & Dynamic (CDIA)
  - Phase 4: Modern Resolution Engine
- Prior work: `m2-gap-closure-dependency-intelligence.md` (original investigation)
- `m2_rem_08_combined_dogfood_findings_open.md`
- `wikifier/parsers/javascript.py`, `bree.py`, `resolution.py`, `import_cache.py`, `wikifier.sh`, `mcp/server.py`

---

## Next Immediate Actions

1. **Review & Align** — Team reviews this synthesis + the four individual plans. Adjust scope or sequencing if needed.
2. **Contract Definition** — Define the shared Metadata + Pipeline + Cache extension rules (highest priority pre-coding task).
3. **Wave 0 / Pre-work** — Create golden test fixtures and a basic “barrel hell + hard conditional” synthetic test harness.
4. **Wave 1 Kickoff** — Begin Phase 4.1 (central resolution engine) with supporting shell/cache wiring.

---

**This document is now the single source of truth for the Gap #1 long-term closure program.**

It will be updated as waves are executed, risks are retired, and new learnings emerge from dogfooding.

**Status**: Open for execution planning.