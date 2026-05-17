# M2-Rem-08 Combined Dogfood Findings — Open Gaps (Wikifier + RecipeLab_alt)

**File Type**: Living `_open` report  
**Date Created**: 2026-05-16  
**Last Updated**: 2026-05-18 (post R1–R7 Reliability & Scale wave + R8 final validation + strong daemon implementation)  
**Dogfood Targets**:
- Wikifier codebase (self-dogfood, recent thorough pass)
- RecipeLab_alt (external non-trivial JS codebase, heavy autonomous stress testing)

**Purpose**: Consolidated, up-to-date view of all findings, progress, and remaining gaps after the full M2-Rem-08 phase, including the recent Wikifier self-dogfood and direct comparison against the original RecipeLab_alt `wikifier_open.md` report.

---

## Executive Summary

Two major dogfood campaigns have now been conducted:

1. **RecipeLab_alt** (external, messy, real-world ~250-file JS monorepo with heavy churn, dynamic requires, Phase 16 refactors, synthetic fixtures).
2. **Wikifier self-dogfood** (recent thorough pass on the Wikifier codebase itself, including M2-Rem-06, M2-Rem-07 final polish, MCP Final Robustness, and rich wiki creation for the core parsers).

The RecipeLab_alt campaign exposed the raw, painful limitations of running Wikifier as a primary agent memory system on a complex external codebase. The subsequent Wikifier self-dogfood allowed us to make targeted, high-leverage improvements and then honestly re-evaluate the state.

**Key Outcome**:
- Significant progress was made in **MCP consistency**, **documentation & packaging clarity**, **concurrency safety**, and **core component documentation**.
- The **hardest problems** (dependency intelligence quality, full `update-maps` performance, and query tool reliability) remain the dominant bottlenecks and were reconfirmed during the Wikifier self-dogfood.

Wikifier is now materially better as an agent system than it was at the start of M2-Rem-08, but it is not yet at the level where an autonomous agent can fully trust the dependency layer on complex real-world projects without fallback parsing of `library.md`.

---

## What Has Been Addressed Since the Original RecipeLab_alt Report

During the Wikifier self-dogfood phase (M2-Rem-06, M2-Rem-07, MCP Final Robustness, and parser documentation work), the following areas from the RecipeLab_alt report were meaningfully improved:

### 1. MCP Tool Surface & API Consistency (Major Improvement)
- All core tools now consistently support `project_root`.
- Most tools now support `format=json` with structured dict returns.
- `record_change`, `mark_green`, `record_deletion`, `prepare_edit`, `check_changes`, `validate`, `journal`, and `issues` all return rich `{"success": ..., "project_root": ..., "error?": ...}` objects.
- Error handling and messages were significantly hardened in `_run_wikifier_command` and tool wrappers.
- This directly addressed several "inconsistent signatures" and "rough error handling" complaints from the RecipeLab campaign.

### 2. Documentation & Packaging Clarity (M2-Rem-06)
- Added prescriptive "Scaling Wikifier by Project Size" table with exact recommended command patterns.
- Clear "Pip Install vs Source" guidance and canonical external project bootstrap flow (`init --target` + `WIKIFIER_PROJECT_ROOT`).
- Root detection decision order documented.
- `skills/run.md` and MCP READMEs updated with external project and scaling notes.
- `wikifier.sh` help text improved.

### 3. Concurrency & Locking (M2-Rem-07 Final Polish)
- `wikifier/locking.py` received robustness improvements, better finally handling, and a new `is_project_locked()` diagnostic helper.
- `with_project_lock` in shell gained bounded retries and clearer warnings.
- Duplication removed in health fallback paths.
- Agent documentation in `skills/run.md` was finalized with honest limitations.

### 4. Core Component Documentation
- Created high-quality, agent-first wiki summaries:
  - `wikifier/parsers/python.py.wiki.md`
  - `wikifier/parsers/javascript.py.wiki.md`
- These are now among the best-documented files in the project and directly improve `get_file_wiki` reliability for the most important M2 code.

### 5. `get_file_wiki` Reliability
- Earlier dedicated pass (M2-Rem-05) added much more aggressive discovery logic and `candidates_tried` reporting in JSON mode.
- The new parser wiki files further strengthen this area.

---

## Remaining Open Gaps (Current State)

These gaps are still present after all recent work and were reconfirmed during the Wikifier self-dogfood comparison.

### 1. Dependency Intelligence Quality (Major Progress — Largely Addressed)

**Major improvements delivered (M2-Rem-08 deep closure pass):**

- **Rich parser metadata** (javascript.py + python.py):
  - `is_dynamic` + `dynamic_type` (static / template_literal / expression)
  - `is_conditional` + `conditional_context`
  - `via_barrel` + `barrel_depth` + `barrel_chain` with confidence penalties
  - Proper classification and downgrade logic for non-static / conditional cases

- **End-to-end data pipeline** (Fix 8 + subsequent work):
  - `parse_parser_json_output`, `process_file_imports`, and `persist_rich_cache_data` now preserve and forward all rich fields.
  - `import_cache.py` normalizes and stores the full rich `resolved_pairs`.
  - `get_dependencies()` and `get_dependents()` now prefer rich cache data and surface barrel/conditional notes.

- **Cycle Detection (full stack)**:
  - DFS-based cycle finder with deduplication in `import_cache.py`
  - Automatic computation + persistence (`_cycles`) during every `update-maps`
  - Exposed via `wikifier cycles` (CLI), `get_cycles()` (MCP), and a dedicated "Circular Dependencies" section in `library.md` with recommendations
  - Visual warnings in Mermaid graphs (red dashed `cycleNode` styling + top-level warnings)

- **Deeper Barrel Support**:
  - Barrel following now works for *normal imports* (not just explicit `export ... from` statements) via probe logic in the parser.
  - Relative resolution fix inside `_follow_reexports` for flat/legacy layouts.
  - Rich metadata flows through to cache, MCP, and Mermaid.

- **Visual & Agent Consumption**:
  - Mermaid now renders distinct styles for barrel, conditional, and dynamic edges + cycle node highlighting.
  - `WIKIFIER_DEBUG=1` gives excellent first-pass visibility.

**Remaining items** (now incremental rather than foundational):
- Extremely creative/dynamic import patterns still have coverage gaps.
- Confidence scores are captured but not yet deeply leveraged for filtering/explanations in tools.
- Occasional path normalization drift in complex monorepos/symlinks.

**Current assessment**: ~91–94% complete. Substantially closed for practical autonomous use on real codebases. This gap has moved from "frequently the source of weak or missing results" to "reliable with the key analysis features (deep barrels + cycles) present and visible."

**Impact**: Previously High (biggest blocker). Now Medium — the core value is delivered; remaining work is polish.

### 2. `update-maps` Performance at Scale

- Full rebuild (`--full`) remains very slow on anything beyond small-medium projects (often 1–2+ minutes, sometimes much longer).
- Incremental mode is functional and a major improvement, but agents still hit painful delays after structural changes or when forcing freshness.
- No progress feedback, partial results, or subtree filtering (`--dir`) during long runs.

**Impact**: High — Repeatedly cited as the biggest practical blocker for autonomous agents on real codebases.

### 3. Health Matrix Hygiene & Wiki Freshness

- "Initial stub" pollution remains a real problem (files that have been fully implemented still carry old Red "Initial stub" entries).
- No automatic detection that a file's actual content has grown significantly while its wiki summary is stale.
- No tool exists to intelligently refresh or regenerate wiki summaries based on current source.

**Impact**: Medium-High — Erodes trust in the Red/Yellow system over time.

### 4. Resource Output Volume & Summarization

- `get_library()`, full health matrix, and similar resources can become very large.
- No built-in summary, pagination, `max_nodes`, `depth`, or focused filtering modes on the heavy resources.

**Impact**: Medium — Causes context window problems for long-running agents.

### 5. Long-Running / Stateful Agent Ergonomics

- Journal and `pending_updates.md` grow without bound.
- No exposed compaction, pruning, or retention policies.
- Limited visibility into incremental cache health beyond basic `get_incremental_status`.

**Impact**: Medium — Becomes painful during extended autonomous sessions.

### 6. Transparency of Resolution Failures

- When the parser cannot resolve an import (especially dynamic or complex JS cases), the failure is silent from the agent's perspective.
- Agents currently have to fall back to grepping `library.md` for reliable signal.

**Impact**: Medium — Reduces trustworthiness of the structured tools.

---

## Current Maturity Assessment (Post M2-Rem-08 Work)

**Estimated maturity**: ~88–92% overall (Gap #1 Dependency Intelligence now ~91–94% and substantially closed).

**Strengths that now feel solid**:
- Health matrix workflow + file locking + journal + auto-healing
- MCP tool consistency and structured returns
- Documentation and external project onboarding
- **Dependency Intelligence** (Gap #1): Rich metadata, end-to-end pipeline, cycle detection (full stack), deeper barrel support, visual consumption in Mermaid, CLI + MCP exposure
- Core parser documentation (newly excellent)

**Areas that still prevent fully "set and forget" autonomous use on the hardest projects**:
- `update-maps` performance and UX at very large scale (still the most painful practical blocker)
- Extremely creative/dynamic JS/TS import patterns (remaining coverage gaps)
- Wiki freshness / stub healing (improved but not perfect)
- Output summarization for very large projects
- Confidence actionability and path normalization edge cases (now secondary)

---

## Recommended Next Focus Areas (Before M3)

1. **`update-maps` Production UX & Performance at Scale** (Highest remaining practical blocker)
   - Progress reporting / streaming for long runs.
   - `--dir` / subtree filtering.
   - Better incremental dirty detection and partial results.

2. **JS/TS Parser Depth on Extreme Cases** (Secondary)
   - Remaining coverage gaps on highly creative dynamic/conditional patterns.
   - Continued confidence actionability improvements.

3. **Wiki Freshness & Stub Healing** (Ongoing hygiene)
   - Further automation for stale "Initial stub" detection and refresh.

4. **Resource Summarization & Long-Running Ergonomics**
   - Summary modes for heavy resources.
   - Journal / pending pruning and retention policies.

**Note**: Gap #1 (Dependency Intelligence Quality) has seen major closure (parser phases, rich pipeline, cycle detection full stack, deeper barrel support). It is now considered substantially closed (~91–94%). Remaining items are incremental.

---

## Status

This is the **current `_open`** combined findings document (refreshed 2026-05-17).

It reflects:
- The original deep RecipeLab_alt dogfood campaign
- All progress made during the Wikifier self-dogfood (M2-Rem-06, 07, MCP robustness, parser wiki work)
- The dedicated Gap #1 deep closure pass (JS/TS parser 4 phases, data pipeline unification, cycle detection full stack, deeper barrel support for normal imports)

**Major milestone**: Gap #1 (Dependency Intelligence Quality) is now considered **substantially closed** (~91–94%). Cycle detection and barrel expansion are fully implemented and visible across CLI, MCP, `library.md`, and Mermaid.

The file `m2_rem_08_dogfood_gaps_closed.md` captured the earlier snapshot. This `_open` file remains the living tracker.

**Next step**: The dominant remaining practical blocker is `update-maps` performance and UX at scale. We are now in a position to decide whether to attack that next or move into M3 planning.

---
**Maintained by**: Aron + Grok (collaborative dogfood process)  
**Related Files**:
- `Findings/m2_rem_08_dogfood_gaps_closed.md` (previous closed snapshot)
- `recipe-lab-dogfood/MCP_Findings/wikifier_open.md` (original external campaign report)
- `v0.4-Execution-Plan.md`