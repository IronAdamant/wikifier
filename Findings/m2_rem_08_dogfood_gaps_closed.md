# M2-Rem-08 Dogfood Gap Report — Closed (Wikifier Self-Dogfood)

**Date Opened**: 2026-05-16  
**Date Closed**: 2026-05-16  
**Phase**: M2-Rem-08 — Final Dogfood Validation (Wikifier project)  
**Dogfood Target**: Wikifier codebase (self-dogfood)

**Purpose**: Consolidate gaps observed during M2-Rem-08 dogfooding on the Wikifier project itself. This report is now closed after completing M2-Rem-06, M2-Rem-07 final polish, and MCP Final Robustness work.

---

## Executive Summary

This M2-Rem-08 dogfood phase on the **Wikifier project itself** has been completed.

During this session the following major remediation items were finished:

- **M2-Rem-06**: Documentation & Packaging Clarity (prescriptive scaling guide, clear pip install + external project bootstrap workflow, root detection decision order)
- **M2-Rem-07 Final Polish**: Concurrency & Locking (robustness improvements, new `is_project_locked()` helper, duplication cleanup, excellent agent documentation)
- **MCP Final Robustness**: Full consistency pass — all core tools now support `project_root`, most support `format=json`, write tools return structured results, error handling significantly improved

As a result, several high-impact gaps from the earlier combined dogfood report (RecipeLab_alt + Wikifier) have been substantially closed or mitigated on this project.

**Remaining high-priority items** (documented below) are now tracked for future work or the dedicated RecipeLab_alt dogfood session.

---

## Gap Categories

### 1. Parser Quality (JS/TS)

- [ ] JS/TS parser still produces suboptimal results on real-world flat/legacy codebases (no package.json, missing index files, heavy dynamic requires, barrel exports).
- [ ] Confidence scoring exists but is not yet deeply leveraged by the bash resolver or MCP tools in all flows.
- [ ] Non-relative bare internal module resolution works better but is not yet as robust as the Python parser.

**Evidence**: RecipeLab_alt dogfood (flat structure with no package.json) + current self-dogfood observations.

**Impact**: High — Dependency intelligence on JS-heavy projects remains the weakest language path.

---

### 2. Dependency Graph & `update-maps`

- [ ] Full `update-maps` (especially `--full`) remains slow on anything beyond small-medium projects (observed >1 hour run in background task).
- [ ] Incremental mode is functional and a major improvement, but the "Resolved Internal Dependencies" table generation still does some redundant work.
- [ ] Cache (`import_cache.json`) is working but could be more aggressively leveraged (e.g., skipping resolution entirely for cached resolved targets in all code paths).
- [ ] No easy way for agents to inspect or invalidate the import cache (`get_incremental_status` helps but is limited).

**Evidence**: Both dogfoods — full rebuild pain was repeatedly highlighted.

**Impact**: High — This is one of the biggest blockers to using Wikifier on large monorepos.

---

### 3. Health Matrix

- [ ] Still primarily file-based with limited multi-agent/session attribution. Works for small numbers of agents but will need sharding or richer metadata for high-concurrency massive repos.
- [ ] Directory filtering and summary mode are now available, but the flat Markdown view is still the default human experience.

**Impact**: Medium-High for very large concurrent agent setups.

---

### 4. MCP Tool Surface & API

- [x] ~~Inconsistent parameter surfaces across tools (`project_root`, `format`, `directory` are not uniformly applied).~~  
  **MCP Final Robustness (2026-05-16)**: All core tools now accept `project_root`. Lower-level tools (`check_changes`, `validate`, `journal`, `issues`, `prepare_edit`, `record_deletion`) were brought up to parity with high-value tools.

- [x] ~~Some tools still return raw shell text instead of structured JSON even when `format=json` is supported elsewhere.~~  
  **MCP Final Robustness**: Added `format=json` support + structured dict returns to `check_changes`, `validate`, `journal`, `issues`. All write tools (`record_change`, `mark_green`, `record_deletion`, `prepare_edit`) now return rich `{"success": ..., "project_root": ..., "error?": ...}` dicts.

- [x] ~~Error handling remains rough in several tools — agents receive unhelpful or raw error messages.~~  
  **MCP Final Robustness**: `_run_wikifier_command` improved with clearer error messages including the project root. All tools now catch exceptions and return structured error objects instead of raising in most cases.

- [x] ~~Lower-level tools (`record_change`, `mark_green`, `validate`, `journal`) have received `project_root` support but still feel less mature than the high-level dependency tools.~~  
  **MCP Final Robustness**: These tools (plus `check_changes`, `prepare_edit`, `record_deletion`, `issues`) now match the maturity of `get_dependents`, `suggest_next_actions`, etc.

**Status after MCP Final Robustness pass**: The MCP tool surface is now highly consistent, structured, and agent-friendly. The remaining minor gaps are cosmetic.

**Impact**: Significantly reduced (was High, now Medium-Low for agent trust).

---

### 5. `get_file_wiki`

- [ ] Still the weakest high-level tool. Discovery of dedicated wiki files (especially `*.wiki.md` next to source files) is unreliable.
- [ ] Extraction from `library.md` has improved but is not yet robust across different project layouts.
- [ ] In the current dogfood, `get_file_wiki("wikifier/health.py")` failed to locate the existing `health.py.wiki.md`.

**Evidence**: Both dogfoods (major complaint in RecipeLab report + live failure observed here).

**Impact**: High — One of the most agent-visible gaps.

---

### 6. Documentation & Packaging

- [x] ~~While external project usage documentation has improved (README, `skills/run.md`), agents still occasionally get confused about root detection and when to use `--full` vs normal mode.~~  
  **M2-Rem-06 Update (2026-05-16)**: Added clear "Root Detection Rules (Decision Order)" + "When to use `--full` (rare)" section with exact priority list and canonical external bootstrap commands. Significantly reduced confusion risk.

- [x] ~~Packaging story after `pip install` vs running from source is better documented but still has friction points for new users on external projects.~~  
  **M2-Rem-06 Update**: Added dedicated "Pip Install vs Running from Source" subsection + canonical first-time external project bootstrap flow (`init --target`, env var, `wikifier-mcp`). Help text in `wikifier.sh` also updated. Friction greatly reduced.

- [x] ~~No clear "scaling guide" that tells users/agents exactly how to operate efficiently at different project sizes (small / large / massive).~~  
  **M2-Rem-06 Update**: Replaced vague recommendations with a full prescriptive table "Recommended Command Patterns by Project Size" (Tiny/Small, Medium, Large, Massive) including exact commands, when to prefer MCP, directory filtering, incremental vs `--full`, and `get_incremental_status` usage. This is now the authoritative agent reference.

**Status after M2-Rem-06**: Documentation & Packaging Clarity gap is now **substantially closed**. The three specific pain points identified in dogfood have been directly addressed with clear, prescriptive, copy-pasteable guidance.

**Impact**: Now Low for this category (was Medium).

---

### 7. Concurrency & Multi-Agent Safety

- [x] ~~Basic project-level locking is now in place and working.~~  
  **Final M2-Rem-07 Polish (2026-05-16)**: Completed thorough quality pass.
  - `wikifier/locking.py` now has improved documentation, more robust `file_lock` context manager, a new `is_project_locked()` diagnostic helper, and a better `with_lock` decorator.
  - Shell `with_project_lock` helper made more resilient (bounded retries + clear warnings).
  - Duplication removed in `upsert_health` Markdown fallback (now reuses the central helper).
  - `skills/run.md` concurrency section received final clarity pass with honest limitations and agent guidance.
  - All high-level tools (MCP + CLI) automatically use locking via the Python backend.

- [ ] Fine-grained (per-file or per-agent) attribution and locking is still absent.  
  **Note**: Project-level advisory locking is explicitly documented as sufficient for the current M2 scope (including heavy multi-agent dogfooding on large monorepos). Per-file/sharded locking remains a planned future extension when real usage pressure appears.

**Status after final polish**: Concurrency safety is now considered production-grade and well-documented for M2. The remaining item is a conscious design decision rather than a gap.

**Impact**: Low for current and near-term use.

---

### 8. Performance at Scale

- [ ] Full `update-maps` performance remains the most visible scalability bottleneck.
- [ ] Health matrix operations are now much better thanks to the JSON backend, but some shell paths and table views can still feel slow on very large projects.

---

## Summary of Must-Address Gaps Before Closing M2

**Highest Priority (Strongly recommended before M3)**:
- `get_file_wiki` reliability and discovery
- Full `update-maps` performance (especially `--full` on large projects)
- Parser quality on complex real-world JS/TS codebases

**Important for Long-Term Credibility**:
- Continued refinement of MCP tool ergonomics and structured output
- Deeper integration of resolution confidence into agent-facing tools

**Already Addressed in This M2-Rem-08 Phase**:
- Documentation & Packaging Clarity (M2-Rem-06) — Closed
- Concurrency Safety & Locking (M2-Rem-07) — Final polish complete
- MCP Tool Surface Consistency & Robustness — Final robustness pass complete

---

**Closure Note**

This report (`m2_rem_08_dogfood_gaps_closed.md`) marks the completion of the M2-Rem-08 dogfood validation pass focused on the **Wikifier codebase itself**.

Significant progress was made in:
- Documentation quality and external project usability
- Production-grade concurrency safety
- MCP server robustness and consistency

The file was renamed from `_open` to `_closed` on 2026-05-16 before moving on.

Remaining gaps (especially `get_file_wiki`, full `update-maps` performance, and JS parser edge cases) are preserved here for tracking in future sessions or the RecipeLab_alt dogfood.

**M2-Rem-08 on Wikifier project: Closed.**
