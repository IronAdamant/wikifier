# V1 Visual Layer Production Hardening Wave — Architecture Document (P1 Deliverable)

**Role**: V1-P1 Visual Layer Architect  
**Wave**: V1 Visual Layer + Scale Hardening (8-agent parallel model mirroring Gap #1 P1–P7 waves)  
**Date**: 2026-05-18  
**Status**: FROZEN REFERENCE — Binding for P2–P5 (Visual Production) and P7 (Data Wiring). P6 (Performance Guardian) to validate/measure.  
**Dual Audience**: Primary — LLM agents / autonomous Grok Build sessions (exact copy-paste commands, parseable data, no ambiguity). Secondary — human developers performing refactoring, porting, or maintenance (clear sections, comments, rationale).  
**Binding Constraints (Non-Negotiable)**:  
- Zero external dependencies beyond existing Tailwind CDN + Mermaid CDN. Pure static HTML5 + vanilla JS + inline CSS/JS only.  
- Total delivered weight (index.html + diagnostics.html + any minimal supporting static assets) < 85 KB uncompressed.  
- Large monorepo resilience mandatory (5k–20k+ file projects; library.md summarized per R1, file_health.md very large tables).  
- No build step, no new runtime deps, no frameworks.  
- All changes to visual layer assets recorded via project Wikifier process (record-change → wiki update → mark-green).  
- Agent-first UX with full human-dev parity.

**References (read before any implementation)**:  
- Findings/m2_rem_08_combined_dogfood_findings_open.md (scale pain points, resource volume, update-maps perf)  
- Findings/gap1_polish_hardening_wave_closure_report.md + r3_large_scale_dogfooding_report.md (real 577-file ConsistencyHub, 66-file cycles, R1 context)  
- wikifier/scripts/wikifier.sh (R1 LARGE_SCALE_MODE, MAX_SHELL_RESOLVED_PAIRS=8000 default, streaming persist via FRESH_PAIRS_TMP, degradation in generate_* )  
- skills/run.md (mandatory agent protocol, full CLI + MCP command surface)  
- Current index.html (28 KB baseline single-page dashboard)  
- README.md (Scaling table by project size) + Findings/gap1_prewave0_shared_contracts_open.md (contracts for rich data)  
- Wave charter (memory): concrete index upgrades + separate heavy diagnostics page; 8-agent model; agent-primary.

---

## 1. Page Model & High-Level Information Architecture

**Two-Page Split (Fast Main vs Heavy Diagnostics)**:  
- **index.html** (primary, fast-load "Dashboard"): Lightweight overview, health summary, exhaustive command surface (CLI + MCP), compact visuals, R1-aware summaries. Target: <30 KB. Entry point for agents (run wikifier check-changes then open).  
- **diagnostics.html** (secondary, "Deep Diagnostics"): Full interactive matrices, exhaustive library.md sections, detailed intel, scale panels, command reference with schemas. Target: <50 KB. Linked from index; not loaded by default.

**Rationale**: Current single index.html already mixes overview + detailed parsing. Splitting satisfies user request ("move detailed diagnostics to separate page"), keeps main fast for 5k+ projects (avoids DOM bloat from 1000s-row tables or huge parsed mermaid), respects 85 KB envelope, enables graceful degradation without compromising either audience.

**Navigation (Simple, Zero-JS-Router)**:  
- Persistent top header (shared style): Logo + "Wikifier v0.3 — Visual Layer" + badges (AGENT-FIRST, GAP#1 RICH, ZERO DEP, SCALE-AWARE) + **Dashboard** (self) | **Diagnostics** (link to diagnostics.html) | **skills/run.md** | **MCP** | Refresh.  
- Cross-links in footers and scale banners.  
- No tabs/modals for core nav (perf + simplicity); deep content uses in-page anchors + vanilla filter/search.  
- Breadcrumbs / "Back to fast dashboard" on diagnostics.  
- Keyboard: 'R' refresh (current), '/' focus command filter (new).

**Data Flow (Pure Static, Client-Only)**:  
1. Both pages fetch project-root-relative static artifacts via `fetch()`: `file_health.md`, `pending_updates.md`, `journal/YYYY/MM/DD.md`, `library.md`. (Optional: `file_health.json` for future structured if small.)  
2. Vanilla JS parsers (simple line-based for tables, regex for ## sections + mermaid blocks, tolerant of R1 notes). No server, no eval.  
3. R1 Scale Detection (central): Scan library.md for "R1 Scale Degradation" / "LARGE_SCALE_MODE" / "ScaleNote" on load. If present (or rowCount > threshold), activate `isLargeScale=true` flag.  
4. Render: summaries + filtered views first; full expansion only under cap or explicit user action (with perf warning).  
5. Commands: Buttons do **not** execute (static); they display/copy exact invocation strings for both `./wikifier.sh <cmd>` (or `wikifier`) **and** MCP `tool call <name>` (with example args). Dual forms satisfy agent (MCP primary per skills) and human/shell.  
6. Updates: After agent runs CLI/MCP, user refreshes page (or monitor heartbeat auto-refreshes health/pending).  
7. No mutation of project data from UI (read-only visual layer).

**Large-Scale Degradation Strategy (Mandatory, R1-Aligned)**:  
- **Detection**: `library.md` contains R1 strings (from sh generate_* when `LARGE_SCALE_MODE` or `resolved_pairs` cap hit at 8000); or `file_health.md` row count >800 (heuristic); or explicit `?scale=large`.  
- **Behavior (both pages)**:  
  - Health: Load full MD for counts + Red/Yellow priority list (top 50 critical). Full table/filter available but virtualized or paged (simple JS slice + search on in-mem array; never dump 5k+ rows to DOM on load).  
  - Library/Mermaid/Intel: Show R1 notice banner + summarized sections (use existing python-generated summaries for cycles/barrels/cdia). Skip expensive edge loops; provide "Query via MCP: get_dependencies(file, depth=2, format=json)" examples.  
  - Mermaid: If degraded, render only the scaleNote node + legend (no full graph build).  
  - Commands/Intel: Emphasize MCP `get_project_status`, `get_files_needing_attention`, `get_cycles(analysis=true)`, `suggest_next_actions` over full `update-maps --full`.  
- **Guarantees**: Rich data (cdia_v1, barrel_v2, res_meta_v1, cycles) always lives in import_cache (via sh streaming FRESH_PAIRS_TMP + contracts) even when library.md table/graph omitted. Visual layer never re-implements or re-parses raw edges at scale.  
- **5k–20k+ Resilience**: JS parsers are linear + early-exit on caps; no O(n^2) or heavy string ops on full data. Memory bounded. Tested conceptually against ConsistencyHub 577-file + extrapolated dogfood.  
- **Graceful Fallbacks**: "Matrix unavailable (run check-changes)" already present; extend to scale banners with exact recovery commands.

**Component Ownership (Clear Boundaries for P2–P5 Implementers)**:  
- **Shared (duplicate minimal CSS/JS constants across files to avoid extra assets)**: Header, badges, status pills, command-btn styles, R1 banner, health count pills, basic MD row parser, runCommand toast helper (educational copy).  
- **index.html owns (light)**: HealthSummary (counts + priority reds), QuickCommandPalette (exhaustive grid + daemon/monitor), CompactMermaid/IntelCards (R1 truncated), Pending + Journal previews, Agent Rules footer.  
- **diagnostics.html owns (heavy but budgeted)**: FilterableFullHealthTable (search/status/sort/paginate), FullLibrarySections (cycles with CIABRE, barrels, cdia rendered as cards/lists), ScaleDiagnosticsPanel (R1 details + recommended patterns), ExhaustiveCommandReference (all CLI + MCP with signatures/examples), DevRefactorNotes (porting comments).  
- **No shared .js file** (would add weight + complexity); inline duplicated helpers with /* SHARED: ... */ comments for easy sync/port.  
- **New in this wave**: Scale-aware logic, full command surface buttons, cross-page nav, R1 banners, diagnostics page.

---

## 2. Recommended Section Maps (Concrete for Implementation)

### index.html (Fast Main — ~25-30 KB target)
Keep structure close to current for minimal diff, harden + expand per charter.

1. **Header** (existing wikifier-header + new nav links to diagnostics.html + MCP README)  
2. **Status Bar / Hero** — Title + live health-summary pills (Green/Yellow/Red counts; add "Scale: Large (R1 active)" badge if detected)  
3. **Quick Commands — Agent & Human Surface** (new, prominent, 2-3 row grid):  
   - All non-daemon: check-changes, health, update-maps [--full], validate, record-change, record-deletion, prepare-edit, mark-green, journal, issues, cycles, init, help  
   - Daemon/background: monitor &  
   - Key MCP (primary for agents): get_project_status, suggest_next_actions, get_files_needing_attention, get_dependencies, get_dependents, get_cycles(analysis=true), update_maps, health (MCP), record_change etc.  
   - Each button: onclick shows fixed toast with **exact copyable lines** (shell + MCP XML example + note "Run in terminal or via connected MCP server"). Include project_root variants.  
   - Filter/search input over commands (vanilla).  
4. **Overview Grid** (existing 12-col):  
   - Health highlights (compact table or cards: only Red + top Yellow; "Full matrix → diagnostics.html")  
   - Pending Actions (mini)  
   - Recent Journal (mini preview)  
   - Compact Dependency Graph (mermaid or placeholder + R1 note)  
5. **Dependency Intelligence Summary** (existing 4 intel-cards, truncated + R1-aware)  
6. **Agent Protocol Reminder** + footer links (skills, spec, diagnostics) + "Recorded via Wikifier" note.

**JS Additions**: R1 detection on library load, scale badge, command filter, full button set (no behavior change to existing loads).

### diagnostics.html (Heavy but Lightweight Implementation — ~45-50 KB target)
New file. Mirror header style + "← Fast Dashboard (index.html)".

1. **Header** (same + "Deep Diagnostics" badge + scale indicator)  
2. **Scale & Project Status Banner** (R1 detection, size heuristics, recovery commands, link to README scaling table)  
3. **Full Documentation Health Matrix** (interactive):  
   - Controls: status filters (All/Red/Yellow/Green), file search input (live filter on parsed rows), sort by file/status/date, "Show only critical" default.  
   - Table (scrollable or paged 100-row batches via vanilla JS; in-mem rows from full parse).  
   - Stats footer + "Export note: use CLI health --json or MCP".  
4. **Full Dependency Intelligence Sections** (from library.md):  
   - Circular Dependencies + CIABRE (full top clusters, severity, recs)  
   - Barrel Expansions (BREE)  
   - Conditional & Dynamic (CDIA)  
   - Resolved pairs summary or note (R1 degraded if present)  
   - Rendered Mermaid (with warning if large)  
5. **Detailed Diagnostics Panel**:  
   - Incremental status, graph integrity, cycle stats, pending + journal full recent.  
   - Raw-ish previews (capped) of key MDs.  
6. **Exhaustive Command & MCP Reference** (for agents + porting humans):  
   - Table or sections: Command | CLI form | MCP tool | Args | When to use | Scale notes | Dual-audience tips.  
   - Covers everything from skills/run.md + sh help + new visual commands.  
7. **Large Monorepo Resilience & R1 Rules** (self-documenting for future agents/devs): explicit copy of scale handling + performance envelope.  
8. **Developer / Refactoring Notes**: "For porting this visual layer: see component comments, parser helpers are pure functions, duplicate minimal shared code with /* PORT NOTE */ markers. No build required."  
9. **Footer** with back link + protocol reminder.

**JS**: Re-use/adapt parsers from index (documented), add filter/sort/paginate (event delegation), R1 logic, no heavy libs.

---

## 3. Explicit Performance Budget & Scale Handling Rules (Binding for All Subsequent Agents P2–P8)

**Delivered Weight (Hard Cap)**:  
- index.html: ≤ 30 KB (target 25 KB)  
- diagnostics.html: ≤ 55 KB (target 45 KB)  
- Combined + any 1-2 tiny support (e.g. no extra): < 85 KB total.  
- Per-file: HTML skeleton + Tailwind script + Mermaid script + custom <style> + <script> (vanilla) must be lean. Minify not required (readability for humans) but no bloat. Measure at creation (P6 will enforce).

**Runtime / Render Budgets**:  
- Initial load (no data): <1.5s on modern browser.  
- After fetch + parse (typical health 100-500 rows + library): <800ms render.  
- Large scale (5k+ rows or R1): summary path <400ms; full interactive filter only on explicit "load full" (warns "may be slow in browser").  
- Mermaid: cap nodes/edges or skip; never block on huge graphs.  
- Memory: parsers keep bounded arrays (slice on render); no full-DOM for everything.  
- Network: only project .md files (local/fast); CDNs cached.

**Scale Handling Rules (Frozen — Violate = Wave Failure)**:  
1. Every JS data loader (health, library, intel) **must** check for R1 degradation markers first. Activate `degradedMode` and short-circuit heavy paths.  
2. Health table render: **never** unconditionally append > 300 rows on load. Default to priority (Red/Yellow + first N Green) + live client-side filter/search that operates on parsed JS array.  
3. Library parsing: use existing lightweight regex + `.slice(0, N)` for cards/sections; honor R1 notices verbatim in banners.  
4. No new CDNs, no dynamic imports, no workers unless vanilla.  
5. Command buttons: 100% static strings (no runtime generation that scales with project size).  
6. All new code **must** include dual-audience comments: `// AGENT: exact command string below for copy-paste` and `/* HUMAN PORT: ... */`.  
7. Coordinate with V1-P6: expose hooks or console metrics for timing (e.g. `performance.mark('health-parse')`); P6 owns final measurement + any trimming.  
8. With V1-P7: data wiring must remain fetch + parse; any new fields in library.md or health must be tolerated by parsers (additive, never break).  
9. Total visual layer assets must survive `du -h` + manual review; no creep above 85 KB across wave.  
10. Large monorepo test: architecture guarantees useful view even when library.md omits full table (per current sh R1 logic at 8000 pairs) and file_health has 10k+ entries.

**Component / Code Hygiene**:  
- Prefer functions over monolithic scripts.  
- All fetch errors already graceful (keep).  
- Accessibility: existing good contrast; keep.  
- Mobile: current responsive grid; maintain.

---

## 4. Implementation & Handoff Notes

**Process Compliance**: This architecture doc itself created + recorded via Wikifier tools (prepare/record + mark-green). All visual changes will follow same.  

**Coordination**:  
- **V1-P6 (Performance Guardian)**: Review budget, add measurement in diagnostics, validate R1 paths do not regress perf, sign off on final sizes.  
- **V1-P7 (Data Wiring)**: Ensure new intel or health fields parse cleanly; extend parsers only additively.  
- P2–P5: Implement per section maps + rules above. Use this doc as single source of truth.  
- P8 Closer: Produce wave closure report referencing this + metrics.

**Risks Mitigated**: Single-page bloat on large health (split), command discoverability (full palette), scale blindness (R1 first-class), dual-audience mismatch (explicit everywhere), weight overrun (hard caps + ownership).

**Success Criteria (for wave)**:  
- index.html remains fast, delightful for agents (one-glance + copy commands).  
- diagnostics.html provides depth without punishing main flow.  
- 5k–20k projects render usefully (summaries + targeted queries).  
- <85 KB total.  
- Zero new deps/build.  
- Fully documented for porting.

This document is the frozen architectural contract.

**Maintained by**: V1-P1 (Grok Build) — decisive, agent-first, scale-hardened.

---

*End of V1 Visual Layer Architecture (P1). Next agents: read this first.*