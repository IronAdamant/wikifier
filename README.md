# Wikifier v4.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/wikifier.svg)](https://pypi.org/project/wikifier/)
[![GitHub Stars](https://img.shields.io/github/stars/IronAdamant/wikifier?style=social)](https://github.com/IronAdamant/wikifier/stargazers)

**Agent-first • Zero-dependency • LLM-operated codebase wiki**

Wikifier turns any codebase (tiny scripts → large monorepos) into a living, token-efficient map that LLMs/agents operate autonomously.

### Intended Use: Agent-to-Agent Wiki (Token-Saving Only)

This is meant **strictly** as an agent-to-agent wiki layer.

- Primary purpose: save tokens for agents/LLMs.
- You (the agent) can look up files quickly via the health matrix / file wikis / barrels / incremental status instead of reading full sources.
- Autonomously update wiki summaries and create new ones as you work (edit source → `record-change` → update the wiki entry → `mark-green`).
- Create new wiki-maintained files/docs as needed during agent sessions.
- Workflow for agents: `wikifier check-changes`, read the small `file_health.md` + `pending_updates.md`, prioritise, edit, `record-change`, `mark-green`, `update-maps` when relevant.
- **It shouldn't be used for anything more than that.** Not a general human documentation system, not an IDE replacement, not for broad non-agent use.

See the LLM workflow in `--help` and `skills/run.md` for the exact loop. All M5+ evidence was produced by agents operating in exactly this mode.

### M5 Broad Real-World Dogfood Complete — 85-90%+ (June 2026)

The M5 phase (broad real-world dogfood on the user's prepared external 5k–50k+ creative projects) has been fully executed.

**Execution ("same as before")**:
- 4 parallel background subagents covering all targets: RecipeLab/alt (BRC ~20+ named services/chains exact reproduction), ConsistencyHub + CoordinationHub + core MCPs (Chisel/Trammel/stele-context cross), ~18+ other customs + scoped OSS (Babylon.js etc.), LargeScale (llvm-project heavily scoped subs ~79k files in llvm/ + clang/lib, ~540k total monitored when expanded, plus worktree consistency copy).
- Full workflows on externals only (WIKIFIER_PROJECT_ROOT / project_root= always, absolute monitored_paths, scoped --directory where needed, python-primary for large streaming, cross chisel/stele/trammel where applicable).
- Strict protocols: FRESH 3 hygiene before every Findings edit, `record-change` + `mark-green`, subagent_id tagging, 9 Guiding Principles (esp. #1 spectrum, #7 multi-agent, #8 M5 boundary, #9 measurable), 8-step DF traces, honest calibration, zero self-dogfood on Wikifier source, main tree 100% clean.

**Key Evidence & Outcomes** (see `Findings/` for full):
- `M5-Dogfood-Progress.md` (1192 lines): full diaries from all 4 agents + launch/status/synth notes. Subid counts: 5/6/10/15.
- `M5-Dogfood-Assessment-Report.md`, `p6_real_world_validation_report.md`, `M5.1-cross-hardening-analysis.md`.
- Main health: 4+ 🟢 on M5 keys (Progress, Milestones, Assessment, p6, M5.1-cross, wikifier.sh). Targets: lean "Pruned 0", expected BRC/MISSING as designed stress (alt BRC signals exact match prior snapshot), no cross-pollution after M5.1 fixes.
- Highlights: alt BRC ~20+ from named (AdversarialScaffoldGenerator etc.), llama core 5673u/8e (new py edges), Consistency 82162 edges + stele self 108 docs/30k sym/6 mismatches + target trammel plans, Other breadth with 185u/22g Rust etc. + Babylon 0-miss + graceful large-batch timeout handling, Large 79k+ C++ (python-primary streaming success on 5k dir, 0 sub-entries in health, chisel C++ 0% observed vs prior 168k u/4min, stele path-prefix exercised, barrel 0 on pure C++).
- Honest calibration (per Assessment-Report): **85-90%+** toward actual 95%+ / 5-10yr viability ("as close as possible without [literal more] dogfooding"). 7-criteria and 9 GPs upheld with rich measurable evidence. Remaining gaps require M5.3: literal multi-month (≥72h concurrent MA+daemon on 3+ targets: alt/Consistency/llvm-llama priority) for full "3" 0-corr under churn, obs after months, full OSS depth, central 95% scoring (see 10 DoD + M5.3 plan in Assessment).

**M5.1/M5.2 Hardening** (using existing snapshot data only, no new dogfood during phases): MCP reliability (timeouts/caching), health.py auto-prune + under-root scoping for external, cli resilience, cross-MCP analysis + safe fixes (chisel/stele/trammel), agent doom-loop handling patterns. Artifacts produced.

See the final synth in `Findings/M5-Dogfood-Progress.md` and full Assessment-Report for metrics, 9GP/DF traces, gaps/DoD, M5.3 plan.

**v4.0 Release**: M5 (broad real-world dogfood 85-90%+) is complete, including M5.1/M5.2 hardening for MCP reliability and external use, M5.3 sustained foundations (monitors, subagents, agent-to-agent wiki scope), and recent MCP/skills updates. With zero-dependency explicitly enforced, the agent-to-agent wiki model (token-efficient lookup + autonomous updates) mature, and full protocol in skills/run.md v0.5, this is the 4.0 release.

**v4.0.1 (2026-06)**: Post-4.0 cleanup + small robustness (patch level; no major addition or scope change — remains 4.x per direction). 
- `health.py`: `_coerce_root` (accepts str | Path for `load_health`/`save_health`/`upsert_entry` etc.; direct Python lib use with WIKIFIER_PROJECT_ROOT or "." now robust, no TypeError). Added `SUPERSEDED_PATTERNS` + prune logic (load/migrate/save/upsert) to aggressively drop superseded historical wiki-notes (e.g. early M5.3 "Cycle1 evidence" from before full gate) while preserving explicit 🔴 Red "DELETED" audit records as intentional, observable markers for agents.
- `pending_updates.md`: cleaned (removed full `grep --help` preamble corruption from prior diagnostics; only real audit + mtime notes remain).
- Repo: removed tracked + fs junk (old `test-js-flat/`, `Findings/wave-evidence/*` subagent/phase diaries) via rm + `git rm --cached`; lingering monitors killed (safe pids); launcher banners/headers (`wikifier.sh`, `scripts/wikifier.sh`) now consistently v4.0.
- Monitored paths + health matrix kept lean/specific (no broad `.` or external pollution). Main health: 4+ 🟢 on core (README, mcp/*, wikifier.sh, --help, M5 Findings) + 1 intentional 🔴 Red audit + unrelated mtime Yellow.
- Version to 4.0.1. All under M5 protocols (FRESH before this README edit, record+mark, subid, zero-dep, main clean, external-only for any dogfood). See cleanup commit 4c37dd5 + `health --summary`.

**v4.1.0 (2026-06)**: Minor bump for project structure cleanup and reorganisation (no behaviour changes).

- Organised documentation: moved historical and non-core `.md` files (Basis-v0.3.md, spec.md, TRADEOFFS.md, RELEASE_NOTES.md, the v0.4 execution plans) into a new `docs/` folder. Root directory is now much cleaner, containing only the essential files: README.md, CHANGELOG.md, CONTRIBUTING.md, the core wiki state files (file_health.md, library.md, pending_updates.md), and .mcp.json.wiki.md.
- Updated all references/links in README.md, index.html (the dashboard), MANIFEST.in, and pyproject.toml.
- This is a pure organisational improvement to make the project easier to navigate (especially for the human investigation layer via the dashboards, while keeping agent-to-agent primary via the text files and tools). No changes to monitored_paths.txt (still only tracks the key agent-wiki files), no impact on functionality or the health matrix.

**v4.1.1 (2026-06)**: Very minor patch for human investigation layer separation (enforcement + hygiene; no new behaviour or scope).

- Enforced correct deployment: `wikifier init` (cli.py + wikifier.sh) now copies *only* `index.html` (the clean, data-driven human wiki viewer for the *target project's* agent-maintained wiki: chart, files+descriptions, copies). `diagnostics.html` (Wikifier's own maintainer/refactor/porter hub with architecture, full maps, porting checklist and *this tool's* source tree) is no longer copied into target roots — it was causing "stale" + "pointing at wrong folder" (Wikifier tree instead of the actual project) when opened after `update-maps` in external projects (e.g. RecipeLab_alt).
- Updated `index.html` template: "For maintainers" link is now a safe informative span (with tooltip) so copied instances in targets don't have broken links.
- Refreshed `diagnostics.html` content: added prominent disclaimer that the file map is for Wikifier *tool* refactors only (not host project); updated tree to current layout (post-structure org, human layer split, health robustness); fixed Two-Page description and section numbering.
- Added guidance in the human dashboard: old `diagnostics.html` in project roots (from prior inits) can be safely deleted.
- Synced descriptions in README.md, `skills/run.md`, `wikifier/mcp/README.md`.
- All under protocol (FRESH, record-change + mark-green with subid, main clean). Version to 4.1.1. See the separation-fix commit.

**v4.1.2 (2026-06)**: Very minor patch for mapping / update speed hygiene (no new behaviour or scope; pure internal improvements for large projects).

- Faster candidate collection everywhere that drives check-changes, monitor, and update-maps (Python-primary paths): switched to `os.scandir`-based recursive scan (std lib, avoids walk overhead) + git `ls-files --cached --others --exclude-standard` fast-path when in a git repo (dramatically faster on real monorepos; falls back cleanly).
- Consistent early pruning: `exclude_patterns.txt` (user-editable, populated by init) now applied more broadly during mapping walks in both sh and Python collectors (venvs, caches, site-packages, etc. stop descent sooner).
- Small parser micro-opt: hoisted common regex compiles (docstring strip, dynamic import detectors) to module level in the Python parser (hot path on dirty files during maps).
- Minor sh-side note + skeleton for git fast collection in traditional update-maps path (real wins already flow through the Python collectors used by check-changes/streaming/lib/MCP).
- All changes FRESH-checked + recorded+marked under subid=mapping-speed-hygiene. Complements existing levers (monitored_paths.txt narrowing, --dir / directory= scoping, --stream / --max-files / --max-time streaming+budgets, python-primary, incremental dirty + BRC reverse index).
- Version to 4.1.2. See the speed-hygiene edits + this commit.

### Historical (pre-v4.0)

#### What's New in v0.3.3 (Gap #1)

**Gap #1 (Dependency Intelligence) is now at 95%+ "set & forget" on large messy monorepos — Swarm Complete**

This release marks the full closure of the 6 remaining Gap #1 last-mile items using a parallel multi-agent swarm (Grok Build 0.1 model):

- Barrel_v2 + res_meta_v1 + Persistent BarrelResolutionCache + Deep Invalidation at real monorepo scale
- Guaranteed Cycle / Graph Structure Persistence (delta short-circuit + v1 canonical default)
- External / Packaged Full-Update Robustness (Python-primary `run_full_update` + complex monorepo discovery)
- ACS + CIABRE Surfacing Uniformity (actionable recommendations everywhere + new low-conf filter)
- Extremely Creative / Dynamic Import Pattern Coverage (new CDIA detectors + Layer 3.5 dataflow + Python parity)

**Key Outcomes**:
- Full `python -m wikifier.gap1_validation_harness --gap1-health` now reports **GREEN**
- Selective barrel invalidation, real 5k+ dogfood, RecipeLab monorepo paths, and daemon integration all production-grade
- All changes strictly zero-dependency, scalable to 50k+ files, and additive

See the detailed agent diary entries in `Findings/m2_rem_08_and_v0.4_progress_tracker.md` for the complete swarm journey.

### Broader M2 Progress — Phase 6-7 95%+ Swarm Wave (2026-05-28)

Significant progress on detailed per-Workstream A–E durability and external long-pole execution toward genuine 95%+ "set & forget":

- Dual independent reviewers (77 + 78) confirmed the full 9-step hygiene-first merge playbook **all PASS**.
- WS A–E durability slices (71–75) completed with concrete metrics on real external 5k+ creative proxies (main Wikifier self-host + RecipeLab 1637/269) + harness 25k–50k generators under long-load chaos.
- Dedicated external long-pole agent (76) executed extended proxy work on the **real 5k+ main Wikifier creative target** with streaming + rich bounded A3 summaries (`format=summary`) as the normal/default path, delivering strong reproducible artifacts (health matrices over "days", high partials usage, 0 trust failures, ACS/CIABRE explain-all, correct reverse survival, etc.).
- Evidence layer (`Findings/wave-evidence/`) updated with rich diaries from the long-horizon agents (notably 72 ~6.8 h, 71, 75, 76).

**Current honest calibration** (per the 7 exact 85% criteria + long-term scalable plan): **82–87% toward 95%+**, **0/7 strict 85%**. The dominant remaining gap is the literal multi-day (3–7 d) high-trust autonomous external long-pole on real 5k+ creative monorepos with the new paths as the unquestioned normal/default (crit4/Gate3), as confirmed by 76/77/78 and prior reviewers. Proxies are strong; literal wallclock multi-day high-trust autonomous execution remains open.

**Re-alignment Note (late 2026-05-28)**: Per explicit user direction, M1–M4 are the feature-building and technical gap-closing phases. M5 is reserved for broad dogfooding across multiple real-world projects the user has already prepared. The 80/82/83/84/85 swarm work on the real 5k+ main Wikifier creative self-host represents meaningful M2 feature completion and real-usage exercising during the building phase, not final M5 validation. The previous strict 0/7 scoring pressure is being de-emphasized while features are still being completed.

See `Findings/m2-85-to-95-agent-swarm-plan.md`, the updated tracker, `wave-evidence/`, and the long-term scalable plan for full details. All work under strict discipline ("3" untouched, main clean, honest no-overclaim).

### M3 – Agent Interface & Ergonomics (Feature-Building Complete)

The M3 phase — polished public Python library surface, rigorous testable Agent Protocol (v0.5 baseline with mandatory long-running/swarm/MA + daemon + human behaviors), complete versioning + additive migrations, thin-consumer parity (≥0.92 fidelity), and comprehensive agent-builder documentation + patterns across the full scalability spectrum (tiny scripts to 50k+ creative monorepos with barrels, dynamic/conditional imports, workspaces, symlinks) — is now complete as a pure feature-building phase under the 9 Guiding Principles.

- Central deliverable: `Findings/M3-80-95-Completion-Package-Handoff.md` (exact C8/B8 model; verbatim 9 Guiding Principles + 80%/90-95% DoD; FRESH LAST "3" hygiene with multiple verbatim 0-def grep logs on active non-guardian code; full evidence index with absolute paths to all E1-E8 / F1-F8 / G1-G4 swarm artifacts + C5 heavy 50k+ creative validation on allowed targets only; honest 48-55%+ calibration).
- Sacred partials/continuation ("3" / test_partial_continuation_workflow_25k deep-proof track at harness:3109) elevated as the natural scalable ergonomics path for 50k+ creative work via safe citation and pattern replication only — the implementation track itself remains untouched.
- Strict execution: zero new dependencies, main source 100% clean, M5 boundary absolute (all serious validation on harness M3 suites + RecipeLab + user-designated external creative monorepos; no sustained dogfood on the Wikifier project itself).

See `Findings/Milestones-Overview.md` (now updated with 80-95% closure + Gamma coordination) and the original plan/checklist in `Findings/m3-*.md`.

### M4 – State Management & Long-Term Scale (80-95% Complete)

M4, the feature-building phase for years-scale autonomous "set & forget" operation on massive creative monorepos, is now at 80-95% completion.

**Delivered durability foundations** (E1–E5 + D6/C6 bases, strong evidence on allowed targets):

- Reversible, bounded compaction and O(changed) state for 50k+ creative monorepos with barrels, dynamic/conditional imports, workspaces, symlinks, high churn, and partials/"3" (E1 prototype + B1/B2/D1/D6 Pattern 1; <15% growth / 99%+ success / 0 corruption on "3" paths in 50k+ sims; 83%+ compaction in 90-sim-day C5 runs).
- Rich long-horizon observability and diagnostics that remain useful after months of data (E2/D3/E3).
- Complete additive versioning and migration policy for all M4 state shapes (E2/D3).
- Comprehensive years-scale agent-builder patterns and documentation (E5 Guide extending D6 4 patterns + C6 base with real E1/E3/C5 metrics from harness 25k-50k+, RecipeLab, and external 50k+ proxies; full 8-step/9GP/spectrum matrices; honest limitations).

**Evidence** (harness extended 25k-50k+ creative generators with full target patterns + partials/"3" + concurrent chaos, RecipeLab, designated external 50k+ proxies):

- 0 "3" corruption on 100+ partials_3 exercised.
- Bounded growth (e.g. ~25 MB mem / 80 MB disk in 50k+ 90-sim-day).
- Sub-2 ms average recoveries, actionable obs trends, high Prin compliance (0.87–1.0 on relevant).

**M5 Preparation** (explicit central handoff):

See `Findings/M4-80-95-Completion-Package-Handoff.md` for the full handoff, including known limitations and the precise mandate for M5: literal multi-month (toward years) uninterrupted autonomous "set & forget" on user-prepared real 5k-50k+ creative projects under the 9 Guiding Principles (full patterns + sustained concurrent MA+daemon+human; specific metrics for boundedness, recovery, obs usefulness, versioning, "3" fidelity, 95%+ usefulness + 5-10yr viability).

M4 = capability + proxy evidence on allowed targets (harness/RecipeLab/externals). Literal broad real-user multi-month dogfood = M5 exclusive.

**Process**: 7–8 agent swarms (E1–E8 + Gamma coordination), visible execution, full discipline (multiple independent FRESH LAST "3" with verbatim 0-def logs, zero new dependencies, M5 boundary, 8-step DF + 9 GPs everywhere, rich diaries with verbatim evidence).

See the central handoff, `Findings/M4-Years-Scale-Agent-Builder-Guide.md`, E7 REV1 report, E1 prototype reference (in e1 worktree), and updated Milestones for details.

**M5 status (June 2026)**: Broad real-world dogfood round complete (see new top-level M5 section above). 85-90%+ achieved "as close as possible without (more) dogfooding". M5.3 (literal multi-month sustained on 3+ targets) remains for the final 95%+/5-10yr gate per the Assessment-Report DoD.

### What's New in v0.3.2

**Gap #1 (Dependency Intelligence Quality) is now substantially closed (~94–96%)**

This release completes the major M2-Rem-08 deep closure work on dependency intelligence:

- **Major Barrel Intelligence Improvements** (6 parallel specialized agents):
  - Barrel following depth increased (2 → 3)
  - Much smarter barrel detection (now catches real-world import-style index barrels)
  - Full `barrel_chain` tracking and visibility across the system
  - Modern `package.json` `"exports"` map support for resolution and barrel following
  - Significant performance improvements for barrel probing
  - Conditional context now properly propagates through barrel chains

- **Cycle Detection (Complete Stack)**
  - Full cycle detection with DFS + deduplication
  - Exposed via `wikifier cycles`, `get_cycles()` MCP tool, "Circular Dependencies" section in `library.md`, and visual warnings in Mermaid graphs

- **Overall**
  - Rich dependency metadata now flows reliably everywhere
  - `get_dependencies()` and `get_dependents()` are dramatically more trustworthy
  - Dependency intelligence is no longer the primary blocker for autonomous agents

This is a significant patch release that brings the dependency layer to a production-useful level for most real-world projects. The main remaining practical challenge is now `update-maps` performance at very large scale.

**Other highlights carried from v0.3.1**:
- Health Matrix Auto-Healing (`heal-stubs`, `healing-stats`, etc.)
- `WIKIFIER_DEBUG=1` for first-pass transparency
- Richer cache and reverse dependency support

> **GitHub**: https://github.com/IronAdamant/wikifier  
> **PyPI**: https://pypi.org/project/wikifier/

---

## 🚀 Installation

**Recommended — via pip:**

```bash
pip install wikifier
```

Then run:

```bash
wikifier init
wikifier check-changes
```

Then (after init) open `index.html` in your browser for the live (human) dashboard — health matrix, Mermaid tree, and export/copy text for LLM use. It lives inside your project folder alongside the MCP setup.

---

**Alternative — from source:**

```bash
git clone https://github.com/IronAdamant/wikifier.git
cd wikifier
chmod +x wikifier.sh
./wikifier.sh init
./wikifier.sh check-changes
```

### Mandatory Rule for Every LLM / Grok Build Session (Protocol v0.4)

**Authoritative spec**: See `skills/run.md` (Wikifier Agent Protocol v0.4) + the full library surface design in `Findings/m2-full-closure-longterm-scalable-plan.md` (Workstream E).

Copy this (or the exact block from skills/run.md) into the **start of every new prompt**:

```text
You are now operating inside a Wikifier v0.4 managed codebase (Agent Protocol v0.4).

FIRST ACTIONS (mandatory):
1. If the Wikifier MCP server is connected, prefer its tools (get_project_status, check_changes, suggest_next_actions).
2. Else if the `wikifier` Python package is importable, prefer the direct library API:
     from wikifier import check_changes, health, record_change, mark_green, suggest_next_actions, update_maps, discover_project_root
     check_changes()
     h = health(format="json")  # or "summary"
     ... perform edit ...
     record_change("path/to/file", "concise semantic reason (why, not what)")
     ... update wiki summary ...
     mark_green("path/to/file")
     if imports_or_structure_changed:
         update_maps(directory="src/", use_python_primary=True)
     suggest_next_actions(format="json")
     health(format="json")
3. Otherwise fall back to shell: wikifier check-changes
... (see full mandatory workflow, I/O contracts, error handling, and scaling in skills/run.md)
```

**Python Library (clean public API, zero-dep)**: The preferred path for agents (when importable). Provides structured dicts, auto-locking, Python-primary paths for the full mandatory loop with no shell. See `__init__.py`, `cli.py` (Workstream E funcs), and the design doc. Submodule power access (e.g. `from wikifier.health import ...`) remains available.

> **Note**: This rule applies per-project. When using Wikifier on an external codebase (not the Wikifier repo itself), the agent should be told which project root to operate on (via `WIKIFIER_PROJECT_ROOT`, `--project-root`, or the `project_root` parameter on MCP tools / library calls). The library + protocol make sessions low-ambiguity across models.

---

### Using Wikifier on External Projects (Packaging & Setup Clarity — M2-Rem-06)

Wikifier is a **general-purpose** agent memory system. After `pip install wikifier` (or `pip install wikifier[mcp]`), the `wikifier` and `wikifier-mcp` console scripts become available globally. You can (and should) use them on **any** codebase — not just the Wikifier source tree.

#### Pip Install vs Running from Source

- **After `pip install wikifier`** (recommended for normal use):
  - `wikifier` and `wikifier-mcp` commands are in your PATH.
  - The underlying implementation is the installed package (Python + shell scripts bundled).
  - You still need to tell Wikifier **which project** you want to document (see Root Targeting below).
  - `wikifier init --target /path/to/project` is the correct way to bootstrap state in an external folder.

- **Running from source** (development / contributing):
  - Clone the repo, `chmod +x wikifier.sh`, and invoke `./wikifier.sh ...` or the scripts directly.
  - Useful when you are actively modifying Wikifier itself.

**First-time setup on a new external codebase after pip install** (canonical flow, R6 improved):
```bash
# 1. Bootstrap directly into the target (auto-creates .wikifier/ marker, state files; CLI copies launcher if possible)
wikifier init --target /absolute/path/to/your/actual/monorepo-or-project

# 2. Optional but recommended: edit monitored_paths.txt to focus on src/, packages/, app/ etc. for large monorepos
# 3. Run the mandatory workflow (CLI auto-propagates project root from --target or env)
wikifier check-changes

# 4. For agent work / MCP (now robust, no sh-not-found even on pure pip installs)
WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/actual/monorepo wikifier-mcp
# or pass project_root on individual tool calls
```

The R6 Monorepo & External UX wave made `init --target` fully functional (state in target, launcher copy, .wikifier marker), made CLI/MCP/sh consistently honor WIKIFIER_PROJECT_ROOT, and hardened pnpm/yarn/symlink/TS-ref edge cases in resolution. Much less manual setup for real-world large external codebases.

#### How Root Targeting Works (Decision Order for Agents)

Wikifier resolves the project root using this strict priority. Agents should follow it to avoid confusion:

1. `WIKIFIER_PROJECT_ROOT` environment variable (strongest — works for shell + all MCP tools)
2. Explicit `--project-root` (CLI) or `project_root` parameter on MCP tool calls
3. Upward directory walk looking for `monitored_paths.txt` or a `.wikifier/` directory
4. `.mcp.json` present in the workspace root (common in Grok Build, Cursor, etc.)

When the MCP server is started via `wikifier-mcp` (or through `.mcp.json`), it will usually auto-detect correctly if you `cd` into the project first. For maximum reliability on external dogfooding, always pass `project_root` or set the env var.

**M5 dogfood note (2026-06)**: Broad real-world dogfood round ("same as before") across all prepared external targets (RecipeLab/alt, ConsistencyHub + meta MCPs, 18+ customs, scoped OSS incl. Babylon, llvm-project 79k+ C++ heavily scoped subs + worktree) completed successfully with 4 parallel subagents.

- All targets used absolute `monitored_paths.txt` + `project_root=` / `WIKIFIER_PROJECT_ROOT=` + launcher.
- Python/MCP backend + M5.1 scoping/prune fixes prevented pollution; lean health + "Pruned 0" held; BRC/MISSING as designed stress signals reproduced exactly.
- Full evidence (diaries, 9GP traces, calibs 35-65%, 85-90%+ overall) in `Findings/M5-Dogfood-Progress.md` (1192 lines) + Assessment-Report.

The external robustness (abs paths, scoping, python-primary for 50k+) is now battle-tested at real 5k-79k+ creative scale.

This packaging + targeting story (plus M5.1 external hardening) was a major focus to eliminate friction for multi-target dogfood. See the M5 section above for summary and Findings for details.

---

### Scaling Wikifier — Recommended Patterns by Project Size (M2-Rem-06)

Wikifier is explicitly designed to scale from tiny scripts to massive monorepos. The guidance below is **prescriptive** — follow the patterns for your project size to stay fast and reliable.

#### Recommended Command Patterns

| Size                  | Preferred Interface       | Health Query                              | `update-maps` Strategy                          | Key Additional Practices |
|-----------------------|---------------------------|-------------------------------------------|-------------------------------------------------|--------------------------|
| **Tiny / Small**<br>(< 300 files) | Shell or MCP             | `wikifier health` (full table is fine)   | `wikifier update-maps` (default incremental)   | Use `.wiki.md` files next to sources for best `get_file_wiki`. Full rebuilds are cheap. |
| **Medium**<br>(300–2,000 files) | MCP preferred            | `health --summary` or `health --dir src/` | `update_maps()` (incremental). Use `--full` only after large refactors or suspected cache corruption. | Prefer MCP tools (`get_project_status`, `suggest_next_actions`). Use directory filtering heavily. |
| **Large**<br>(2,000–8,000 files) | **MCP or Python library strongly recommended** | `health(format="json", directory="src/services/")` (via library or MCP) + `--summary` | Always incremental via `update_maps(..., use_python_primary=True)` (library). | Enable locking (automatic). Use library `check_changes` / `suggest_next_actions` for structured agent loops. |
| **Massive**<br>(8,000–30,000+ files) | **Python library or MCP only** | `health(format="summary", directory=...)` via `from wikifier import health` (or MCP) | `update_maps(directory=..., use_python_primary=True)` (library facade to pure path). | Library or MCP required. Directory scoping + summaries mandatory. Full protocol + locking + import_cache ACS/CIABRE. See Workstream E design. |

**When to use `--full` (rare):**
- After moving/renaming many packages or changing import styles across the codebase.
- If you manually deleted `import_cache.json`.
- When the dogfood report or `get_incremental_status` shows very low resolution health.

**Root Detection Rules (to avoid confusion)**
Wikifier finds the project root using this priority (agents should understand this):
1. `WIKIFIER_PROJECT_ROOT` environment variable (highest priority, works for both shell + MCP).
2. Explicit `--project-root` flag (CLI) or `project_root` parameter (MCP tools).
3. Walk upward from CWD looking for `monitored_paths.txt` or `.wikifier/` directory.
4. `.mcp.json` in the current workspace (common in Grok Build / Cursor sessions).

When operating on an external project after `pip install wikifier`, the most reliable pattern is:
```bash
WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/repo wikifier check-changes
WIKIFIER_PROJECT_ROOT=/absolute/path/to/your/repo wikifier-mcp
```
Or pass `project_root` on every MCP tool call.

This section was significantly strengthened during M2-Rem-06 based on dogfood feedback.

---

## What Wikifier Gives You

- **Per-file Documentation Health Matrix** — 🟢 Green / 🟡 Yellow / 🔴 Red status with reasons
- **Semantic Change Logging** — `record-change "file" "I did X because Y"` (the "why", not just the "what")
- **Background Heartbeat Monitor** — Passive `monitor &` loop keeps everything fresh while you sleep
- **Automated Journal + Categorized Issues** — Dated entries + `Logged_issues/{simple,moderate,high,critical}/...`
- **Human Investigation Dashboard (secondary layer)** — `index.html` (copied by init into your project root). Clean human view: prominent code structure chart (Mermaid dependency tree) as hero, "Files & descriptions" list with short summaries ("what the code is about"), simple folder browser, and easy copy buttons for the tree text + full snapshot (tree + files + descriptions) ready for pasting to LLMs or sharing. Auto-refreshes when monitor runs. `diagnostics.html` for technical details / refactors. The .md files + tools remain primary for agents.
- **First-Class MCP Server** — Run `wikifier-mcp` to expose Wikifier as a proper MCP server with rich tools (`get_dependents`, `get_project_status`, `suggest_next_actions`, etc.), resources, and prompts. Works great with Claude Desktop, Cline, Cursor, and other MCP clients.
- **Legacy Skills Interface** — `skills/run.md` still available for simpler shell-based agent setups.
- **True Zero Dependencies** — Pure Bash + PowerShell. Works on any machine, no Docker, no Node, no Python packages.

**Primary: agent-to-agent wiki (token-saving).** Agents/LLMs use the text files (file_health.md, library.md, *.wiki.md) + MCP/CLI/tools directly for lookup + autonomous updates (see skills/run.md).

**Secondary: human investigation layer.** Run `wikifier init` on any project (new or existing). Only `index.html` (the clean human wiki viewer) is copied into the project root. Open it (via local server recommended) to see the project's own code structure chart (Mermaid), "Files & descriptions" with short summaries from the agent wiki, folder browser, and copy buttons for tree text + snapshot. `diagnostics.html` (Wikifier's maintainer/refactor hub with its own architecture + source tree) is *not* copied — it would point at the wrong folder and be irrelevant/stale for the host project. If you have an old copy, you can delete it. Primary agent-to-agent use is always the text files + MCP/CLI.

This enables humans to investigate projects (existing or new) while agents/MCP keep the wiki current. The .md files remain the SSOT for agents.

## Core Commands

| Command                    | Purpose                                      |
|---------------------------|----------------------------------------------|
| `wikifier check-changes`  | Incremental mtime scan + health update       |
| `wikifier record-change <file> "reason"` | Log *why* you made an edit (required) |
| `wikifier mark-green <file>` | Mark wiki summary as accurate after editing |
| `wikifier monitor &`      | Background heartbeat (30s polling)           |
| `wikifier update-maps`    | Rebuild `library.md` + Mermaid dependency graph |
| `wikifier health`         | Show current Documentation Health Matrix     |

Full reference → [`skills/run.md`](skills/run.md)

## Quick Links

- [docs/spec.md](docs/spec.md) — Immutable user requirements
- [docs/Basis-v0.3.md](docs/Basis-v0.3.md) — Implementation reference & data formats
- [docs/TRADEOFFS.md](docs/TRADEOFFS.md) — Why we made the design choices we did
- [index.html](index.html) — Open this in a browser for the live dashboard

## Differentiation

Unlike heavy "LLM Wiki" approaches (e.g. Karpathy-style personal knowledge bases), Wikifier is the **ultra-light, shell-native** implementation:

- Per-file health matrix with clear Red/Yellow/Green workflow
- Semantic `record-change` intent logging for future self-review
- True background monitor + zero external dependencies
- Native cross-platform (Linux/macOS/Windows via PowerShell)
- Designed from day one to be driven by LLMs via MCP/tools

**License**: MIT — fork freely and use in any project.

---

*Built for agents, by agents, with just `bash` and stubbornness.*
