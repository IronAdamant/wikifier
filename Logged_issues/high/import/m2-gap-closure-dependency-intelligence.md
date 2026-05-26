# M2 Gap Closure Investigation — Dependency Intelligence

**Status**: Superseded by full M2 closure plan (Gap #1 investigation complete; broader M2 gaps now tracked in the long-term scalable plan).  

**See**: `Findings/m2-full-closure-longterm-scalable-plan.md` for the authoritative phased execution plan with checkboxes. 
**Started**: 2026-05-16  
**Primary Focus**: Gap #1 — Dependency Intelligence Quality & Query Reliability  
**Related Documents**:
- `Findings/m2_rem_08_combined_dogfood_findings_open.md` (current living combined gaps tracker)
- `recipe-lab-dogfood/MCP_Findings/wikifier_open.md` (original RecipeLab_alt dogfood report)
- `Logged_issues/high/import/m2-dependency-intelligence-tasks.md` (original M2 task list)
- `v0.4-Execution-Plan.md`

**Goal**: Systematically investigate, root-cause, and fix the remaining gaps identified in the M2-Rem-08 combined dogfood findings so that Wikifier can reach a state where it is trustworthy for autonomous agents before moving to M3.

---

## Remaining Gaps (from Combined Dogfood Report)

1. **Dependency Intelligence Quality** (Highest Priority)
   - `get_dependents()` / `get_dependencies()` frequently return incomplete or empty results.
   - JS/TS parser limitations on dynamic, conditional, and complex re-export patterns.
   - Resolution confidence not surfaced in query tools.
   - No cycle detection visibility.
   - Cache / path normalization issues (symlinks, absolute vs relative paths).

2. **update-maps Performance at Scale**
   - `--full` rebuilds too slow for practical agent use.
   - Lack of progress feedback, partial results, or subtree filtering.

3. **Health Matrix Hygiene & Wiki Freshness**
   - "Initial stub" pollution.
   - No automatic detection of stale wiki summaries.

4. **Resource Output Volume & Summarization**
   - Heavy resources (get_library, health matrix) have no summary/pagination modes.

5. **Long-Running Agent Ergonomics**
   - Unbounded growth of journal and pending_updates.
   - Limited pruning and retention controls.

6. **Transparency of Resolution Failures**
   - Agents have poor visibility when imports fail to resolve.

---

## Investigation Log

### 2026-05-16 — Investigation Kickoff

- Created this dedicated investigation log per protocol.
- Confirmed we are in Gap Closure Mode (no M3 until gaps are resolved).
- Prioritized **Gap #1 (Dependency Intelligence Quality)** as the first target.
- Reproduced the core symptom on the current Wikifier codebase:
  - `get_dependents("wikifier/mcp/server.py")` → empty
  - `get_dependencies("wikifier/mcp/server.py")` → empty
  - Similar results on the two parser files.
- This matches the exact pain point reported during the RecipeLab_alt dogfood campaign.

**Next Action**: Begin deep code analysis of the dependency query path (MCP server + table generation in `cmd_update_maps`).

---

### Findings & Experiments

**2026-05-16 — Initial Code Analysis (Table Generation vs Query Path)**

**Key Discovery 1: How the table is built**
- In `cmd_update_maps`, the "Resolved Internal Dependencies" table is generated in three phases:
  1. Fresh re-parsed Python files
  2. Fresh re-parsed JS/TS files
  3. Cached resolved pairs from `import_cache.json` (using `cached_resolved_pairs`)
- Each row is emitted as: `| $rel | $raw_module → $resolved_target |`
- Deduplication is done via `seen_resolved_pairs` associative array.
- The table is sorted and appended under `## Resolved Internal Dependencies`.

**Key Discovery 2: How queries work**
- `get_dependencies()` does a simple regex search in `library.md`:
  ```bash
  pattern = rf"\| {re.escape(file)} \| (.*?) \|"
  ```
- `get_dependents()` calls `_parse_resolved_dependencies()`, which:
  - Finds the table section with regex
  - Splits on "→"
  - Builds a reverse map: `target → [list of sources]`

**Potential Root Causes Identified So Far**:
- Path format mismatch: The `$rel` values written to the table come from `make_relative()`. If the file passed to `get_dependents("wikifier/mcp/server.py")` doesn't exactly match the string stored in the table, the lookup fails.
- For internal Wikifier files, many imports resolve to things like `wikifier.health` or relative within the package. The resolver might be producing slightly different strings than what users pass.
- Cached pairs vs fresh pairs may have different normalization.
- The reverse map only works on the "Resolved Internal Dependencies" table — if that table is sparse (as seen in current runs with many empty rows for core files), queries will return nothing even if the Mermaid graph shows connections.

**Observation**: In the latest `update_maps` run on this project, the Resolved Internal Dependencies table had very few actual `→` entries for Wikifier core modules (most showed empty imports). This explains why the query tools return nothing.

This is consistent with the RecipeLab_alt experience where the human-readable graph was richer than the queryable API.

**New Finding (2026-05-16) — Lazy Imports Pattern**:

In `wikifier/mcp/server.py`, several critical backend imports are lazy (inside functions for optional backends):

```python
from wikifier import health as health_module
from wikifier import import_cache
```

The Python parser correctly returns `raw_module: "wikifier"` for these.

The resolver maps "wikifier" to the package root.

**Consequence**: The table ends up with low-value entries like:
`wikifier/mcp/server.py | wikifier → wikifier/__init__.py`

Instead of the actually useful specific modules (`wikifier/health.py`, `wikifier/import_cache.py`).

This is a real contributor to sparse tables and weak `get_dependents`/`get_dependencies` results for files that use the lazy import pattern (which is common and good practice for optional heavy backends).

**Parser Behavior Test Confirmation**:

I ran a controlled test:

- `from wikifier import health, import_cache` → `"module": "wikifier"`
- `from wikifier.health import upsert_entry` → `"module": "wikifier.health"`
- `from wikifier.mcp import server` → `"module": "wikifier.mcp"`

The parser is working as designed. The root issue is that certain import styles lose submodule information before it reaches the resolver and table generator.

**New Finding — Rich Parser Metadata Under-Utilized**:

The JS/TS parser (`javascript.py`) computes high-value fields for every import:

- `resolved_path`: actual filesystem path when resolved
- `resolution_confidence`: "high" / "medium" / "low" / "unresolved"

These are stored in `import_cache.json` and returned by the parser.

However, in `cmd_update_maps` (the second pass for JS files), only `mod` and `conf` are extracted. The code calls:

`tgt=$(resolve_imported_module "$m" "$rel" "$conf")`

It does **not** use the `resolved_path` returned by the parser. The final table row only contains `raw → tgt` (from the shell resolver).

**New Finding — Incomplete Cache Update for Python**:

When re-parsing Python files in the second pass, the shell code calls:

```bash
import_cache.update_file_data(cache, '$rel_path', $mtime, mods, resolved)
```

It only passes a flat `resolved` list (target files).

It does **not** construct or pass `resolved_pairs` (the preferred `[{"raw": "...", "resolved": "..."}]` format).

In contrast, the cache loading code for unchanged Python files tries to use `resolved_pairs` when available, but since re-parsed files don't store them properly, the table generation for Python often falls back to weaker data.

**Impact on Gap #1**:
- This creates inconsistency between Python and JS handling in incremental `update_maps`.
- Over time, the "Resolved Internal Dependencies" table quality degrades for Python-heavy projects during incremental runs.
- This is another reason `get_dependents`/`get_dependencies` return incomplete results.

**Critical Technical Debt Discovered**:

The Python re-parsing path in `wikifier.sh` uses extremely crude parsing:

```bash
imported_modules=$(echo "$json_output" | grep -o '"module": *"[^"]*"' | cut -d'"' -f4 | sort -u)
```

It only resolves the "module" field again via the shell resolver.

Meanwhile, the Python parser already returns both `raw_module` and `module` (resolved).

The JS path does proper `python3 -c 'import json; ...'` parsing and builds better structure.

This crude `grep` approach for Python is the root of several problems:
1. Loses the ability to easily get raw → resolved pairs.
2. Makes it hard to preserve `resolution_confidence`.
3. Is fragile and inconsistent compared to the JS handling.

This is one of the clearest, most actionable technical debts contributing to Gap #1. The Python and JS paths in the second pass of `update_maps` are implemented at very different levels of quality.

**Code-Level Comparison (Python vs JS JSON Extraction)**:

- **Python first-pass reparse** (around line 1148): Uses `grep -o '"module"'` — only gets the resolved module name. No access to `raw_module` or `resolution_confidence` (Python parser doesn't even emit the latter yet in the same way).
- **JS first-pass reparse** (around line 1241): Uses proper `python3 -c` with `item.get("module")` and `item.get("resolution_confidence")`. Still does not extract `item.get("raw_module")` in the current implementation.

- **Table generation (Python)**: Same crude grep.
- **Table generation (JS)**: Same proper JSON parsing.

Neither path currently extracts `raw_module` from the parser output to build high-quality `resolved_pairs` at the point of re-parsing. The pairs are reconstructed later via the shell resolver calls.

This explains why even when the parsers do good work, the final dependency table and query tools often end up with limited data.

**New Finding — raw_module is Available but Ignored in Both Languages**:

Both parsers return the `raw_module` field:

- Python parser: `"raw_module": "original string from source"`
- JS parser: same

However, in the entire first-pass and table-generation logic in `wikifier.sh`, `raw_module` is **never extracted** for either language.

The `resolved_pairs` that get stored are always of the form `resolved_module → resolved_file` (where `resolved_module` comes from the parser's "module" field or another resolver call), not `raw_import_string → resolved_file`.

This is a systemic data loss point affecting the fidelity of the entire dependency intelligence system.

**Precise Location of the Missed Opportunity (Python First-Pass)**:

In the Python re-parsing block (around line 1174-1180):

```bash
# Collect resolved pair (raw_module → resolved_file) for cache   <--- Comment is aspirational
local pair="$mod→$target_file"                                   <--- $mod is already the resolved name
```

The comment claims it's collecting `raw_module → resolved_file`, but `$mod` comes from the crude grep on `"module"`, so it's actually `resolved_module → resolved_file`.

The parser already computed the correct `raw_module`, but the shell script never asks for it.

The same conceptual limitation exists in the JS path, even though its JSON parsing is better.

**Parser Feature Asymmetry (Python vs JS)**:

- **JS/TS parser** returns a rich structure including:
  - `raw_module`
  - `module` (resolved)
  - `resolved_path`
  - `resolution_confidence`

- **Python parser** returns:
  - `raw_module`
  - `module` (resolved)
  - (missing `resolved_path` and `resolution_confidence`)

Additionally, the shell integration for Python uses crude `grep` parsing, while JS uses proper JSON parsing. This double disadvantage (missing fields + poor extraction) makes Python dependency data systematically lower quality than JS data in the current implementation.

This asymmetry is one of the root reasons the dependency query tools feel unreliable on Python-heavy codebases.

**Call Site Asymmetry in resolve_imported_module**:

- Python re-parsing blocks call: `resolve_imported_module "$mod" "$rel"` (no confidence)
- JS re-parsing blocks call: `resolve_imported_module "$mod" "$rel" "$conf"`

Because the shell resolver applies confidence penalties (lines 317-321):
```bash
if [[ "$confidence" == "low" ]]; then score=$((score - 20))
elif [[ "$confidence" == "unresolved" ]]; then score=$((score - 40))
```

Python resolutions **never receive** these penalties or any future confidence-based bonuses. They always default to "medium".

This is another concrete code-level reason why Python dependency data is treated as lower quality than JS data during resolution.

**Fundamental Design Difference Between the Two Parsers**:

- The **JS/TS parser** was built with resolution confidence as a first-class concept from the beginning:
  - `_try_resolve_bare_internal_import()` explicitly returns confidence ("high", "medium", "low", "unresolved").
  - `_resolve_relative_import()` (JS version) also participates in confidence.
  - The parser output includes `resolution_confidence` as a top-level field.

- The **Python parser** was built with a simpler "best-effort resolved string" model:
  - `_resolve_relative_import()` only returns the resolved module string.
  - There is no confidence calculation at all.
  - The return structure has no `resolution_confidence` field.

This is not just an implementation gap — it's a **design gap**. The Python parser was never given the same resolution quality model as the JS parser, even though Python is the primary language for Wikifier itself and for many agent-driven projects.

This explains a large part of why dependency intelligence feels more reliable for JS than for Python in the current system.

**Impact**:
- The rich `resolved_path` and per-import confidence are computed but mostly discarded for the human-readable table and the query tools.
- `get_dependents` and `get_dependencies` have no visibility into confidence levels.
- This is a significant missed opportunity and one reason the query tools feel weaker than they should.

---

## Root Causes — Gap #1: Dependency Intelligence Quality & Query Reliability

**Investigation completed 2026-05-16.** Below is the consolidated root cause analysis from deep code-level investigation.

### Primary Root Causes (Ranked by Impact)

**1. Fundamental Parser Design Asymmetry (Python vs JS)**
- The **JS/TS parser** was built with resolution quality as a first-class concept:
  - Explicitly returns `resolution_confidence` ("high"/"medium"/"low"/"unresolved")
  - Returns `resolved_path`
  - `_try_resolve_bare_internal_import()` and relative resolution logic participate in confidence scoring
- The **Python parser** was built with a simpler "best-effort resolved string" model:
  - `_resolve_relative_import()` only returns a string (no confidence)
  - No `resolution_confidence` or `resolved_path` fields in output
  - No confidence calculation anywhere in the parser

**Impact**: Python dependency data is structurally lower quality than JS data.

**2. Crude Python JSON Extraction in wikifier.sh (vs Proper JS Parsing)**
- Python path uses fragile `grep -o '"module": *"[^"]*"' | cut -d'"' -f4`
- JS path uses proper `python3 -c 'import json; data = json.loads(...)` with `item.get()`
- This makes it very difficult to access `raw_module`, confidence, or other rich fields for Python files.

**3. `raw_module` Completely Ignored in Shell Integration (Both Languages)**
- Both parsers return the `raw_module` field (original import string from source).
- Neither the first-pass nor the table-generation logic in `wikifier.sh` ever extracts `raw_module`.
- `resolved_pairs` end up as `resolved_module → resolved_file` instead of the more accurate `raw_import → resolved_file`.
- The comment in the Python code even says `# Collect resolved pair (raw_module → resolved_file)`, but the code does not do this.

**4. Python Never Passes Confidence to Shell Resolver**
- Python calls: `resolve_imported_module "$mod" "$rel"`
- JS calls: `resolve_imported_module "$mod" "$rel" "$conf"`
- The shell resolver applies confidence penalties (`low` = -20, `unresolved` = -40). Python resolutions never benefit from (or suffer) these adjustments.

**5. Weaker Cache & `resolved_pairs` Handling for Python**
- Python re-parsing does not properly construct `resolved_pairs` (list of `{"raw": ..., "resolved": ...}`) in the same way as JS.
- `update_file_data()` calls for Python are less rich.
- This causes degraded table quality during incremental `update_maps` runs for Python files.

**6. Redundant Re-Resolution + Information Loss**
- The parsers do real resolution work (especially the JS bare module walker and Python package hierarchy walker).
- The shell then calls `resolve_imported_module()` again, often discarding richer information the parser already had.
- Combined with the loss of `raw_module`, this creates significant fidelity reduction.

**7. Lazy Import Pattern in Core Code (Amplifies the Problem)**
- `server.py` uses `from wikifier import health as ...` style lazy imports.
- This causes the parser to return just `"wikifier"` instead of `"wikifier.health"`.
- The resolver can only map to the package root, losing submodule granularity.

### Secondary Contributing Factors
- Path normalization differences between `make_relative()`, parser output, and how files are passed to MCP tools.
- `module_to_file` / `file_to_module` maps only contain what the (lossy) extraction feeds them.
- No fallback logic in `get_dependents()` / `get_dependencies()` when the table lookup fails.

---

**Status**: Investigation complete. All major root causes identified at the code level. Ready to propose concrete fixes.

---

## Prioritized Fix Proposals for Gap #1

### Tier 1 – High Impact, Relatively Contained (Recommended Starting Points)

**Fix 1: Replace Crude `grep` Python JSON Extraction with Proper Parsing (Biggest Quick Win)**  
**Priority**: Highest  
**Effort**: Low–Medium  
**Impact**: High (foundational)

- Replace all `grep -o '"module": ...'` logic in the Python re-parsing paths (first pass + table generation) with proper `python3 -c` JSON parsing, exactly like the JS path.
- This immediately gives access to `raw_module`, and makes future improvements (confidence, etc.) much easier.
- **Expected outcome**: Python dependency data quality jumps significantly with one contained change.

**Fix 2: Start Capturing `raw_module` → `resolved` Pairs for Python**  
**Priority**: Very High  
**Effort**: Low–Medium  
**Impact**: High

- Modify the Python first-pass reparse block (around line 1150–1189) to also extract `raw_module` from the parser JSON.
- Build `resolved_pairs` as `raw_module → resolved_file` instead of `resolved_module → resolved_file`.
- Update the corresponding cache update and table generation logic.
- **Expected outcome**: Much more accurate reverse dependency lookups.

**Fix 3: Add `resolution_confidence` Support to the Python Parser**  
**Priority**: High  
**Effort**: Medium  
**Impact**: High (closes design gap)

- Extend `_resolve_relative_import()` and the main parsing logic in `python.py` to return a `resolution_confidence` value (even simple heuristics to start: "high" for successful package walk, "medium" default, "low" for fallbacks).
- Add the field to the return dict.
- **Expected outcome**: Python can now participate in the confidence scoring system that already exists for JS.

**Fix 4: Pass Confidence from Python to `resolve_imported_module`**  
**Priority**: High  
**Effort**: Low  
**Impact**: Medium–High

- Update all Python call sites in `wikifier.sh` to pass a third argument (default "medium" until parser is updated, then real values).
- This immediately allows Python resolutions to receive confidence penalties/bonuses.

### Tier 2 – Medium Impact, Good Hygiene

**Fix 5: Improve Python Cache Update to Properly Build `resolved_pairs`**  
**Priority**: Medium–High  
**Effort**: Medium  
**Impact**: Medium–High

- Ensure that when Python files are re-parsed, `update_file_data` is called with a proper `resolved_pairs` list (not just flat `resolved`).
- Align the Python path with how the JS path (and the cache loading logic) expects the data.

**Fix 6: Add Fallback / Resilience Logic to Query Tools**  
**Priority**: Medium  
**Effort**: Low–Medium  
**Impact**: Medium (improves agent experience quickly)

- In `get_dependents()` and `get_dependencies()` (in `server.py`), add fallback behavior when the table lookup fails:
  - Try fuzzy matching on the file path.
  - Fall back to parsing the richer data in `import_cache.json` directly.
  - Or fall back to grepping the Mermaid section of `library.md` with better scoring.

**Fix 7: Reduce Lazy Import Pattern in Core Files (Longer-term Hygiene)**  
**Priority**: Medium  
**Effort**: Low (but requires some refactoring)  
**Impact**: Medium (prevents future data loss)

- In `server.py`, change lazy imports like `from wikifier import health as ...` to more specific imports where reasonable (`from wikifier.health import ...`).
- Or add explicit re-exports in `__init__.py` that the resolver can understand better.

### Tier 3 – Larger / Longer-term Improvements

**Fix 8: Unify Python and JS Second-Pass Logic**  
**Priority**: Lower (for now)  
**Effort**: High  
**Impact**: High long-term

- Refactor the duplicated first-pass and table-generation logic in `wikifier.sh` so Python and JS share more common code paths.
- This would reduce maintenance burden and prevent future drift.

**Fix 9: Expose `raw_module` and Confidence in the MCP Query Tools**  
**Priority**: Lower (after core fixes)  
**Effort**: Medium  
**Impact**: Medium–High (agent usability)

- Once the data is properly captured, surface `raw_module` and `resolution_confidence` in the return values of `get_dependencies()` and `get_dependents()` (especially in JSON mode).

---

## Recommended Execution Order (Suggested)

1. **Fix 1** (Proper Python JSON parsing) – Foundation
2. **Fix 2** (Capture `raw_module` for Python)
3. **Fix 4** (Pass confidence from Python)
4. **Fix 3** (Add confidence to Python parser)
5. **Fix 5** (Improve Python `resolved_pairs` in cache)
6. **Fix 6** (Add fallback logic to query tools) – Quick agent experience win
7. **Fix 7** (Reduce lazy imports in core code)

This sequence gives the fastest path to meaningfully better dependency query reliability.

---

**Next Step**: Once approved, we can begin implementing these fixes (starting with Fix 1 and Fix 2).

## Proposed Fixes

- [ ] ...

## Implementation & Testing Status

- [ ] ...

---

**Owner**: Aron + Grok (collaborative)
**Last Updated**: 2026-05-17 (Gap #1 substantially closed)

---

## Final Status — 2026-05-17

**Gap #1 (Dependency Intelligence Quality) is now considered substantially closed (~91–94%).**

Major deliverables completed during the dedicated closure pass:
- JS/TS parser 4-phase work (dynamic, conditional, barrel depth, confidence)
- Full rich data pipeline from parser through shell helpers into `import_cache`
- Complete cycle detection system (algorithm + persistence + CLI + MCP + library.md section + Mermaid visuals)
- Deeper barrel expansion for normal imports (not just re-exports)

Remaining work is now incremental (extreme dynamic patterns, confidence actionability, path normalization).

The project is in a strong position to either continue polishing Gap #1 or shift focus to the next major remaining gap (`update-maps` performance at scale).

---

## Limitation #1: Extremely Creative/Dynamic Import Patterns — Deep Audit Findings & Long-Term Architecture Proposal (2026-05-17)

**Subagent Mandate**: Long-term specialized focus on Limitation #1 (highest priority remaining incremental item for reaching 98%+ autonomous reliability on `get_dependencies()`/`get_dependents()` without `library.md` fallbacks). Not a quick patch — design scalable, evolvable system for complex dynamic imports from small projects to large monorepos. Full discretion on approach. Report findings + direction clearly *before* code changes.

### Executive Audit Findings (After Thorough Investigation)

**Primary Files Audited**:
- `wikifier/parsers/javascript.py` (core: regex, `_classify_dynamic_import`, `_detect_conditional_context`, `parse_javascript_imports`, `_follow_reexports`, resolution helpers, all 20+ patterns).
- `wikifier/import_cache.py` (RICH_KEYS propagation, `update_file_data`, cycle graph — already forwards is_dynamic/*).
- `wikifier/mcp/server.py` (_get_resolved_from_cache, get_dependencies/get_dependents — rich data in JSON, partial notes surfacing).
- `wikifier.sh` (parse_parser_json_output, process_file_imports, resolved pair emission, Mermaid edge styling for |dynamic|, normalizers — 11-field pipe format already extensible).
- Supporting: test-js-flat/ (basic dynamic template test), v0.4-Execution-Plan.md, Findings/m2_rem_08_*.md, javascript.py.wiki.md, Logged issues.

**Current State (Post M2-Rem-08 4-Phase Work)**:
- **Strengths**: Named-group regex (static | template | expression fallback) in `require_pattern` + `dynamic_import_pattern`; `_classify_dynamic_import` (strips quotes, detects id vs complex via char scan); confidence auto-downgrade (template→low, expr→low, unknown→unresolved); conditional lookback heuristic; full metadata (`is_dynamic`, `dynamic_type`, `is_conditional`, barrel_*) end-to-end to cache/MCP/Mermaid/library; barrel probe works for dynamics too (if static target); zero-dep pragmatic; caches (_parse_cache, _reexport_cache) + perf notes.
- **Dynamic Types Supported**: "static", "template_literal", "expression", "unknown". `import()` and `require()` and `import X = require()`, `import.meta.resolve` (static only).
- **Real Coverage Today**: Good on literals, basic `require(var)`, simple templates `` `foo/${x}` `` (raw kept with ${}), some conditionals. Used in graphs (dotted edges labeled "dynamic").
- **Exact Weaknesses Confirmed via Live Execution** (python -m + synthetic creative cases including ternaries, nested calls, aliases, concats, || defaults, inner fns):

  1. **Regex Capture is the #1 Root Technical Limitation** (`require_pattern` / `dynamic_import_pattern` expression group `(?P<expression>[^)]+?)` + similar in others):
     - `[^)]+?` + `\s*\)` stops at the *first* `)` encountered. 
     - Result: nested parens (ubiquitous in real creative code: `require(path.join(__dirname, sub))`, `require(getMod())`, `require( (a?b:c) )` ) produce **truncated garbage** `raw_module` / `module` like `"path.join(__dirname, \"joined\""` or `"getMod("` or `"cond ? \"./a\" : \"./b\""`.
     - `original_statement` also mangled in some cases. Classify then runs on broken text.
     - Even "simple" creative patterns common in large codebases (RecipeLab_alt "dynamic requires", refactors) fail here.
     - `import_meta_resolve_pattern` only static; no expr support.
     - es_import etc. are static-only (by design).

  2. **No Embedded Literal Harvesting**:
     - Even when capture "succeeds" (e.g. `require(cond ? "./a" : "./b")` or `require(some || "default")` or concat `+ "/bar"`), the strings inside the expr are **never extracted as candidates**.
     - Result: 0 dependency signal for the actual possible targets. The emitted entry has `raw_module` = whole expr (unresolvable), `dynamic_type=expression|unknown`, low/unresolved conf. **Missed edges** — the core complaint.
     - Ternaries, defaults, runtime conditionals (`require(condition ? a : b)`), templates with expr, string concats all lose their static fragments.

  3. **Naive Classification & No Dataflow**:
     - `_classify_dynamic_import`: only checks start/end quote/` , then `re.match ^[a-zA-Z_$][\w$]*$` for "simple id", else "any of ( ) + ? : . [ ]" → expression, else unknown.
     - No AST, no literal pull-out, no var tracking. `someVar || "default"` → unknown (no triggering chars in the any() list for ||).
     - **Zero alias/indirect support**: `const req = require; req("foo")` or `const r = require; r(expr)` or bound/called-via-var completely invisible (no "require(" or "import(" token at call site).
     - Variables computed far away, imported strings, config-driven, loop indices, etc. — all opaque.

  4. **Model & Downstream Gaps**:
     - No `candidates`, `expr_raw`, `complexity`, `indirect_via`, `analysis_methods` fields. One entry per site, no "possible targets" list.
     - In MCP `get_dependencies()` text: surfaces conditional + barrel notes, but **no dynamic/candidates** (even though JSON has the booleans).
     - "module" names for failed dynamics can be expr garbage (pollution risk, though low-conf helps).
     - Confidence "actionable" not yet (no min_conf filters); dynamic info present but under-leveraged for explanations.
     - No special handling for loaders (require.context, require.ensure, System.import, webpack magic comments).
     - Python parser notes similar dynamic gap (`importlib.import_module(var)`) but out of scope for this JS-focused Limitation #1.

  5. **Evidence from Dogfood & Memory**:
     - RecipeLab_alt: "heavy dynamic requires", "Phase 16 refactors", "synthetic fixtures" exposed the holes.
     - Post-closure assessment (Findings + session memory): "Extremely creative/dynamic import patterns (highest priority; main source of missing edges: variables, complex templates, runtime conditionals, `require(condition ? a : b)`). ... JS Parser Weaknesses: 15–20%".
     - Current ~91-94% for Gap #1; this is the dominant remaining for "actually good enough (98%+) for autonomous agent reliance".

  6. **Positive Architectural Foundation**:
     - The 4-phase pipeline, rich dict contract, named groups (from prior "New pattern discovered"), barrel/conditional interaction, full propagation, caches, and "pragmatic zero-dependency" exports resolver are *ideal* for layered extension. No need to rewrite core.
     - Performance already tuned (hoisted regex, early heuristics, memo).
     - Test harness (test-js-flat + python -m self-test in __main__) and dogfood process exist for validation.

**Live Reproduction Confirmed** the exact failure modes listed in memory/context (variables, complex templates, `? :`, partial captures).

### Proposed Long-Term Architecture: Layered Dynamic Specifier Intelligence (LDSI)

**Vision**: A **progressive, registry-driven, depth-configurable static analysis pipeline** for import/require specifiers that gracefully handles the full spectrum of real-world JS creativity while remaining fast, zero-dep by default, and incrementally improvable across releases. Goal: turn "missing edges" into "low-confidence possible edges + transparent notes" so agents get reliable signal + know when to dig deeper.

**Guiding Principles** (for 98%+ trustworthiness at scale):
- **Correctness > Coverage**: Never invent high-conf wrong edges. Low/"speculative" conf + explicit "possible" semantics + complexity flags. Agents/MCP can filter.
- **Graceful Degradation + Transparency**: Every dynamic site is *always recorded* (even opaque ones) with raw expr + reason. No silent drops.
- **Zero Heavy Deps (Default) + Opt-in Power**: Pure Python (regex + state machines + simple passes). Optional pluggable backends (e.g. Node + acorn/babel parser for full expr AST on demand, or tree-sitter via py bindings) behind flag/config/"deep" mode. Preserves "pragmatic" philosophy.
- **Incremental & Evolvable**: Small wins per release (capture fix → literals → aliases → full dataflow → registry → optional AST). Registry of shapes/handlers makes dogfood findings directly actionable.
- **Rich Model Integration**: Extends (does not replace) existing `is_dynamic`/`dynamic_type`/`confidence`/`conditional`/`barrel` contract. New fields flow identically through cache → sh → MCP → graphs → library.md.
- **Performance at Monorepo Scale**: Bounded (per-file, line-limited scans, caches), cheap checks first, only on JS/TS changed files. Existing incremental `update-maps` + mtime is the scaling hero.
- **Multi-Strategy**: Static regex + literal harvest + dataflow/symbolic + heuristics + (future) limited "simulation" of pure exprs or runtime probe (opt-in, sandboxed).
- **Actionable Confidence & Query**: Dynamics participate in confidence; downstream tools surface candidates/notes; future: query filters like "dynamic_only" or "min_conf=low".

**Layered Pipeline Design** (executed in `parse_javascript_imports` for dynamic/require/import_meta_resolve sites; results merged into the emitted dict):

1. **Layer 0 — Robust Capture (Immediate Fix for Root Cause)**:
   - New helper: `def _extract_balanced_argument(source: str, open_paren_pos: int) -> str | None`
     - Manual depth counter (starts at 1 after `(`), tracks string state (' " `), escapes (\\), template ${} nesting (basic), skips comments heuristically.
     - Returns the full inner text until matching `)`.
   - Use: In match loop, for expression cases (or always for require/dynamic patterns), locate the `(` after keyword, call extractor using match.start() or group pos. Fall back to old capture.
   - Benefit: `require( path.join( dir, file ) + (cond?"a":"b") )` now yields complete arg text. Fixes 70%+ of "creative" truncation today.
   - Also covers `import.meta.resolve( complex )`, aliased calls later.

2. **Layer 1 — Literal Harvesting & Candidate Extraction** (Highest Leverage for Missed Edges):
   - New: `def _extract_candidate_literals(arg_text: str) -> list[dict[str, Any]]`
     - State machine or careful re.finditer for quoted strings (handle escapes, distinguish " ' ` ).
     - For templates: split on ${...} boundaries, record static segments + "interpolated_expr" markers.
     - Annotate context ("ternary_true", "default_in_or", "concat_part", "join_arg").
     - Output: `[{"raw": "./a", "type": "static", "context": "...", "speculative": true}, ...]`
   - Run on *full* arg (post-capture-fix) and also as salvage on original_statement / line.
   - Even for opaque expr, this recovers possibles from `? :`, `|| "def"`, `+ "suf"`, `join("p", "s")`.
   - In emit: primary entry keeps expr as raw_module (for traceability); attach `dynamic_candidates: list` (attempt resolution on each via existing resolvers, with "low"/"speculative" conf).
   - **Directly solves** "require(condition ? a : b)", concats, defaults, many complex templates.

3. **Layer 2 — Enhanced Classification + Complexity Scoring** (builds on `_classify_dynamic_import`):
   - Rename/extend to `_analyze_dynamic_specifier(arg_text: str, context: dict) -> dict`
     - Returns dynamic_type + complexity ("simple"|"moderate"|"high"|"opaque") + notes + initial candidates.
     - Uses harvested literals count, operator density, call presence (`(`), control flow (`?:`), idents, etc.
     - "unknown" becomes "opaque" with reason.

4. **Layer 3 — Intra-File Dataflow & Alias Tracking (Moderate Scope, High Value)**:
   - New: `def _build_local_specifier_map(content: str, import_site_pos: int) -> dict[str, list]`
     - Bounded backward scan (e.g. last 100 lines or to top of current "scope" via crude { } or fn keywords).
     - Regex patterns for:
       - `const|let|var\s+([A-Za-z_$][\w$]*)\s*=\s*(["'\`][^"'\`]+["'\`]|`[^`]*`|[^;]+)`
       - Special for ternaries/concats/|| in RHS → harvest literals into the var's candidate list.
       - Alias detection: `([A-Za-z_$][\w$]*)\s*=\s*require\b` (and import equivs) → add to require_aliases set.
       - Reassignments, simple spreads limited.
     - Result: varname → list[candidates or "opaque"]
   - At import site:
     - If arg_text is simple ident and in map → use its candidates, set "source_variable", "defined_via_dataflow".
     - Detect indirect calls: broader pre-scan or post-match for `(\w+)\s*\(\s*` where callee in aliases → treat that call's arg as dynamic import site (even without "require(").
   - Scope: intra-procedural / top-level only for v1 (avoids full CFG expense). Mark "interprocedural": false.
   - **Solves** alias indirection, var-held specifiers, many "variable" cases.

5. **Layer 4 — Extensible Heuristic Pattern Registry**:
   - Module-level `DYNAMIC_PATTERN_REGISTRY: list[tuple[str, callable, callable]]` = [
       ("ternary_branches", lambda t: "?" in t and ":" in t, extract_from_ternary),
       ("path_join_like", lambda t: "join" in t or "resolve" in t, harvest_args),
       ("webpack_context", r"require\.context", special_context_handler),
       ("string_concat", ..., ...),
       ...
     ]
   - Applied after capture; each contributes candidates + tags ("webpack_magic", "from_ternary").
   - Dogfood → new registry entry (cheap, no core changes).
   - Future: user config can register custom.

6. **Layer 5 — (Future) Optional Advanced Backends**:
   - Interface: `DynamicAnalyzer` with `analyze_expr(arg_text, file_ctx) -> richer_ast_info`.
   - Gated: `if os.getenv("WIKIFIER_JS_DEEP_ANALYSIS") or config.get("dynamic_depth") == "ast":`
     - Subprocess node -e 'code using acorn or @babel/parser to return JSON AST for the expr' (small, no install in base).
     - Or pure-Py limited (e.g. simple recursive descent for common expr subset).
   - Use to get accurate nested structure, identify calls, pure-eval candidates, etc.
   - "limited runtime simulation": only for pure string exprs (no side effects) in a tiny Python eval sandbox with whitelisted ops.
   - Monorepo friendly: opt-in per-project or per-file (expensive paths).

**Extended Return Model** (added to every import dict where `is_dynamic` or dynamic site; non-breaking):
```json
{
  ...existing...,
  "expr_raw": "cond ? \"./a\" : getMod() + \"/b\"",   // full original arg text (post-fix)
  "dynamic_complexity": "high",
  "dynamic_candidates": [
    {"raw": "./a", "type": "static", "resolution_confidence": "low", "resolved_path": "...", "via": "ternary_true"},
    {"raw": "default", ...}
  ],
  "analysis_methods": ["balanced_capture", "literal_harvest", "dataflow"],
  "indirect_via": "req" | null,
  "source_variable": "modName" | null,
  "analysis_notes": ["2_candidates_harvested", "alias_tracked"]
}
```
- `dynamic_type` remains for compat ("expression" etc.).
- Update docstring, return example in header.
- In cache: extend RICH_KEYS.
- In sh: extend the python -c normalizer + printf to carry new cols (append safely; old short lines tolerated via :-defaults).
- In MCP: include in JSON returns + add to text notes (e.g. "via dynamic expr (complexity=high, 2 possible: ./a, default)").
- Mermaid: can key off complexity or presence of candidates for variant dashing (e.g. "....>" for high).

**Evolution Roadmap (Incremental, Multi-Release)**:
- **Near (this work + v0.4.x)**: Layers 0+1 (robust capture + literals + model extension + basic classify). Immediate big win on ternaries/concats/nested. Update tests/pipeline surfacing. ~+5-8% coverage on dynamics.
- **Next**: Layer 3 (dataflow+aliases). Registry start (2-3 patterns). Alias indirection + var substitution.
- **Follow-on**: Full registry, complexity-driven confidence, candidate dedup/resolution, Python parser parity for importlib.
- **Later**: Opt-in AST backend, cross-file (summary only, expensive), integration with confidence actionability (e.g. `get_dependencies(..., min_confidence="low")`), "explain" tool for a dynamic site.
- **Metrics for "Done"**: On dogfood + synthetic creative corpus: (a) % dynamic sites with >=1 candidate >X%; (b) no truncation in captures; (c) aliases detected; (d) agent queries rarely miss known runtime edges without "unresolved dynamic" note.

**Integration, Risks, Mitigations**:
- **Fits existing**: Uses match.start() for context, same emit points, same caches. Barrel/conditional OR still works (dynamics can be conditional).
- **Risk - Spurious Candidates**: Mitigated by "speculative"/low conf + explicit list (agents ignore or review). Optional "harvest_literals_only_if_staticish" heuristic.
- **Risk - Perf**: Bounded scans + cache the specifier_map per parse key. Heuristics cheap.
- **Risk - Over-Complexity**: Keep core loop unchanged; new fns private, called only on expression sites. Registry small.
- **Validation**: Extend test-js-flat with creative cases; add self-test in __main__ like the exports tests; re-run on Wikifier + RecipeLab_alt; measure before/after edge count + "unresolved dynamic" count.
- **Docs/UX**: No new .md files (edit existing journals/plans if needed). Update parser docstring + wiki.md via edit if critical. Agent guidance: "Treat dynamic_candidates as possible runtime deps; use resolved_path when present or fall back to library.md + runtime trace."

**Why This Architecture Succeeds Long-Term**:
- Directly attacks the "main source of missing edges".
- Turns the current "light support" into progressively stronger intelligence without ever breaking the 91-94% baseline.
- Scalable (layers optional in depth), correct (conf + candidates), evolvable (registry is the growth mechanism).
- Positions Wikifier for the "98%+ autonomous" target while staying true to its zero-dep, agent-first, pragmatic roots.
- Complements (and can later leverage) confidence system work.

**Next Steps After Recording**:
Implement foundational Layers 0+1 in javascript.py (robust extractor + harvester), wire into parse loop and return model, minimal pipeline tolerance updates, validation tests. Subsequent sessions tackle dataflow etc. This is the principled path, not a band-aid.

**Status**: Proposal recorded. Ready for phased implementation.

### LDSI Implementation Plan (Phase 2+ Continuation — Long-term Subagent for Limitation #1)

**Date**: 2026-05-17 continuation (this subagent session)
**Mandate Followed**: Review proposal (this doc) + current code state first; produce clear plan; incremental rollout with proper design; focus ONLY on dynamic import handling + direct integration points (parser, sh pipeline, cache/MCP surfacing); correctness, graceful degradation, monorepo scale (bounded scans), rich metadata/confidence integration. No new .md files beyond edits to this one; no unrelated changes.

**Current Maturity (at start of this continuation)**: Layers 0 (balanced arg capture via `_extract_balanced_argument`) + 1 (literal harvest via `_extract_candidate_literals` + `expr_raw`/`dynamic_candidates` model) + basic classify + emission + partial surfacing in MCP notes + RICH_KEYS in cache = delivered by prior subagent. ~60% of dynamic creative cases now produce candidates instead of total loss. import_meta_resolve still static-only. Main sh pipeline (update_maps path) strips expr_raw/dynamic_candidates (pipe is 11-field, persist python -c stops at barrel_chain). No Layer 3 dataflow/aliases, no registry.

**Guiding Constraints for All Work**:
- Pure Python, zero new deps.
- Per-file work bounded (scans ≤150 lines back; early-outs; reuse existing hoisted regex + caches).
- Never raise confidence above "low" for dynamic primary entries; candidates always "speculative"/low.
- All new fields optional, backward compatible (old caches/parsers just omit).
- Registry is the extension point: dogfood findings → new handler entry (no core changes).
- Direct integration only: javascript.py (core), wikifier.sh (pipe + persist for fidelity), minimal touches to mcp/server.py notes if data now flows, parser self-tests.

**Phased Incremental Rollout Plan** (execute A then B then C, validate after each; use self-test in `python -m wikifier.parsers.javascript` + synthetic temp fixtures for creative cases):

**Phase A — Close Phase-1 Gaps & Completeness (Foundation Hardening, ~1-2h work, high leverage)**
1. **A1. import.meta.resolve dynamic support**: Update `import_meta_resolve_pattern` to named-group form `(?:['"](?P<static>...)['"]|`(?P<template>...)` |(?P<expression>...) )` like require/dynamic. In parse loop, it will now hit the groups path and automatically get Layer0 balanced + Layer1 harvest + classify + expr_raw/cands (import.meta.resolve can be complex too). Fallback still works.
2. **A2. Full end-to-end pipeline for LDSI fields** (critical for cache/MCP/library.md/Mermaid on main `update_maps` path):
   - Extend `parse_parser_json_output` python -c: extract `expr_raw` and `dynamic_candidates`; safely serialize (expr_raw: .replace('|','%7C').replace('\n',' ')[:200]; cands: base64.b64encode(json.dumps(cands or []).encode()).decode() if present).
   - Append two fields: `|${expr_safe}|${cands_b64}` (now 13-field format).
   - Update all 11-field `read` / `IFS='|'` / `len(parts)` logic in `process_file_imports`, the re-emit in reparse loop (line ~876), `persist_rich_cache_data` python -c (decode + attach "expr_raw", "dynamic_candidates": json.loads(b64) if valid), and any mermaid pair reader. Short lines (len<13) → default None/[] . Old data tolerated.
   - Result: dynamic_candidates (with future resolved) and expr_raw now survive sh pipeline → import_cache → MCP get_* → notes (already coded to surface) → library.
3. **A3. Candidate enrichment (resolution)**: After `_extract_candidate_literals` in expression/template paths (and for meta.resolve), call new private `_enrich_and_resolve_candidates(src_path: Path, raw_cands: list) -> list`: for each cand, if raw looks like specifier, attempt `_resolve_relative...` or `_try_resolve_bare...` (reuse existing), attach "resolved_path", "resolution_confidence":"low" if successful. Keeps primary low-conf dynamic entry but gives agents concrete possible targets.
4. **A4. Complexity scoring (Layer 2 start)**: Extend `_classify_dynamic_import` → or new `_analyze_dynamic_specifier(text: str) -> dict` returning type + "dynamic_complexity": "simple" (bare id) | "moderate" (concat/||) | "high" (ternary+call+nested) | "opaque", + "notes". Populate "dynamic_complexity" in all emit sites (model extension). Downgrade conf further for "high"/"opaque".
5. **A5. Model & docs polish**: Add to header dict example + module docstring the new fields (dynamic_complexity, indirect_via, source_variable, analysis_methods, and note that candidates may contain resolved_path). Update sh comments, mcp docstring. No behavior change.
6. **A6. Synthetic self-tests**: In `__main__._run_exports...` (or new `_run_ldsi_dynamic_tests()`), add 5-6 creative fixtures (temp .js with nested parens require, ternary cond?a:b, || default, concat, alias `const r=require; r(expr)`, import.meta.resolve(var), `require(path.join(__dirname,'x'))`). Assert: no truncation in expr_raw, >=1 candidate recovered, is_dynamic=true, correct type/complexity, indirect_via set where applicable. Run on `python -m ...` to validate. (Extends existing test pattern.)

**Phase B — Layer 3: Intra-File Dataflow & Alias Tracking (Core of this mandate)**
- New helpers (all private, in javascript.py):
  - `_find_recent_assignment(content: str, var_name: str, before_pos: int, max_scan: int=120) -> dict | None`: backward scan from before_pos, regex for last `const|let|var\s+${var_name}\s*=\s*([^;]+)` (handle `;`, crude), then harvest literals or classify RHS as value/cands for that var. Returns {"raw_value", "candidates", "is_alias": bool}.
  - `_scan_file_for_require_aliases(content: str) -> set[str]`: one pass, find assignments where RHS starts with require/import ( `(\w+)\s*=\s*(require|import)\b` or `=\s*import\s*\(` ), collect callee names. Also simple bound like `const {default: req} = ...` limited.
  - `_detect_and_emit_aliased_calls(content, require_aliases, existing_imports_set)` : use a loose pre-scan regex for `(\b[a-zA-Z_$][\w$]*)\s*\(` (potential calls), for each whose callee in aliases and not already processed by main patterns, locate '(', call `_extract_balanced_argument`, run classify/harvest/Layer0-1, emit a full import dict entry with statement_type="aliased_dynamic_import", "indirect_via": callee, "is_dynamic":true, expr_raw=..., dynamic_candidates=..., plus any dataflow if arg was ident. Dedup by (pos, callee).
- Integration in `parse_javascript_imports`:
  - After content read, compute `require_aliases = _scan...`
  - In main loop (after processing patterns), or better as additional "virtual" sites: call the aliased detector once, append its emitted dicts (avoid dupes via position heuristic or original_statement).
  - For every expression dynamic site (in the groups["expression"] branch or post-classify): if the (cleaned) raw_module is simple identifier (re.match ^[a-zA-Z_$]...$), then call `_find_recent...` from match.start(), if hit and yields literal or cands:
    - If literal value, treat as resolved raw_module = that value, is_dynamic=false for this (or keep dynamic but add source_variable=varname, "defined_via_dataflow": true, "analysis_methods": ["dataflow"] ).
    - Else merge the var's candidates into dynamic_candidates, tag accordingly.
  - Always attach "analysis_methods": list (starts with ["balanced_capture", "literal_harvest"] or extended), "source_variable", "indirect_via".
- New model fields (optional): "indirect_via": str|None, "source_variable": str|None, "analysis_methods": list[str], "dataflow_depth": 0|1 (for future).
- Scope: intra-file, crude "recent before site" (no full scope/CFG to stay fast/zero-dep). Over-approx OK (low conf protects).
- This directly solves the "const req = require; req(var)" and "const mod = cond ? 'a':'b'; require(mod)" cases from audit.

**Phase C — Layer 4: Extensible Heuristic Pattern Registry (Evolvability)**
- Module-level (after imports):
  ```python
  # LDSI Layer 4 — Extensible registry. Append handlers for newly observed creative patterns.
  # Each: name (for analysis_methods), detector (cheap bool on text), handler (returns extra_cands list + tags/notes).
  # Handlers receive (arg_text, context={"path":..., "pos":...}) and must be fast/pure.
  DYNAMIC_SPECIFIER_REGISTRY: list[dict] = [
      {
          "name": "ternary_branches",
          "detect": lambda t: "?" in t and ":" in t,
          "handler": lambda t, ctx: _harvest_ternary_branches(t),  # e.g. re for two sides, return cands
      },
      {
          "name": "path_join_like",
          "detect": lambda t: bool(re.search(r"\b(join|resolve|dirname|basename)\s*\(", t)),
          "handler": lambda t, ctx: _harvest_path_call_args(t),
      },
      {
          "name": "or_default",
          "detect": lambda t: "||" in t or "?? " in t,
          "handler": lambda t, ctx: _harvest_or_defaults(t),
      },
      # Future dogfood: "webpack_context", "system_import", "dynamic_require_ensure", "config_driven" etc.
  ]
  ```
- New helpers: `_apply_specifier_registry(arg_text, ctx) -> {"candidates": [...], "tags": [...], "analysis_notes": [...]}` — iterates registry, calls matching handlers, dedupes.
- Call from expression path (post Layer 1 harvest, pre or post dataflow): merge results into dynamic_candidates and analysis_methods (e.g. "registry:ternary_branches").
- Initial 3 handlers can be thin wrappers around existing literal logic or slightly specialized (e.g. split ternary on : and harvest each side with context="ternary_true"/"ternary_false").
- Benefit: makes architecture "registry-driven" per proposal. Adding support for a new pattern = 5 lines in list + one small fn. No touching parse loop.

**Phase D — Validation, Metrics, Polish & Handoff**
- After each phase (esp B/C): run parser self-tests (must pass all exports + new lds i cases); optionally invoke via wikifier update_maps --full on test-js-flat/ or recipe-lab-dogfood (if present) and inspect library.md / cache for new fields on dynamic sites.
- Metrics tracked (in test or manual): for synthetic creative corpus (8 cases from audit): (a) % sites with >=1 dynamic_candidate (target >80% post B), (b) expr_raw never truncated (100%), (c) aliases detected, (d) no new false-positive high-conf edges.
- Graceful: opaque exprs still emit with expr_raw + is_dynamic + low/unresolved + empty cands + note "opaque (no literals or dataflow match)".
- Perf: add simple timing in self-test for a 5k-line synthetic file; ensure <2x baseline (scans are cheap).
- MCP surfacing: verify notes now include richer "possibles + resolved where avail" and expr.
- Update any inline comments in code.
- Record progress here: "Phase X complete: <summary> <date>". Raise effective Gap#1 maturity for dynamic subset.
- Future hooks noted in code: opt-in Layer 5 AST (env WIKIFIER_JS_DEEP_ANALYSIS), cross-file summaries, confidence actionability integration.

**Risks Mitigated in Plan**:
- Pipeline breakage: always support variable field count + defaults.
- Spurious dataflow: low conf + explicit "via dataflow (speculative)" tags.
- Perf on huge files: max_scan hard limit + "if 'require' not in content and 'import(' not in... : skip full map".
- Complexity: all new code in small private fns; core match loop untouched except for 1-2 calls on expression sites only.

**Order & Exit Criteria for this Subagent**:
Complete A (quick wins + fidelity), then B (Layer 3 as primary), then C (registry skeleton), D (tests + validation). Stop before any non-dynamic work. Hand off with updated status in this doc + code ready for next layers (e.g. Layer 5).

**Why Incremental**: Each phase leaves system better than before, fully tested, no regressions. Matches "long-term, scalable" mandate.

**Status of Plan**: Recorded. Ready to execute Phase A → B etc. in code (javascript.py + wikifier.sh only).

**Progress (this subagent session)**: Phase A complete (import.meta.resolve now full LDSI participant; 13-field safe pipe + decode in wikifier.sh for expr_raw/dynamic_candidates end-to-end fidelity through update_maps → cache → MCP; _analyze_dynamic_specifier + complexity + notes wired; _enrich_and_resolve_candidates for actionable resolved_paths on cands; model/docstring updated; parser self-tests + live creative cases pass). Early Layer 3: `_resolve_simple_var_dataflow` + integration recovers cands for `const m = "..." ; require(m)` and ternary defs (tested). No regressions. Registry (Layer 4) design ready per plan; full alias indirect + handlers next incremental step. LDSI now handles the majority of audit creative cases with candidates + transparency. See code in wikifier/parsers/javascript.py (new fns after line ~228) and wikifier.sh (pipe extensions).

---

**Owner**: Aron + Grok (collaborative long-term subagent)
**Last Updated**: 2026-05-17 (LDSI Phase 2 plan + continuation recorded; prior Phase1 impl present)

---

## Limitation #2: Actionable Confidence System (ACS) — Deep Audit Findings & Long-Term Architecture Proposal + Implementation Plan (2026-05-17)

**Subagent Mandate**: You are a long-term implementation subagent for Limitation #2 of Gap #1. Previous agent (Subagent #2) delivered: Full audit of why confidence is currently not actionable + Complete architectural design for an **Actionable Confidence System** (numeric scores, `confidence_reasons`, query filters, new tools, phased integration). Your Mandate: Implement the **Actionable Confidence System** as a first-class, scalable subsystem suitable for massive monorepos. Focus on clean data model extensions, query/filter support in the core tools, new diagnostic/explain tools, and proper integration with existing surfaces (MCP, CLI, cycles, health, etc.). Design for long-term evolution and performance at scale. Produce a clear incremental implementation plan before major coding. Review the previous proposal first (high-level from memory ID `019e33de-660b-7261-89b4-a39648f3b936`: Enhanced data model (`confidence_score` 0.0–1.0 + `confidence_reasons` list); new query filters on core tools (`min_confidence`, `include_conditional`, `max_barrel_depth`); dedicated tools (`get_dependency_stats()`, `explain_dependency()`, `get_low_confidence_edges()`); first-class integration into cycles, health reports, refactoring tools, and Mermaid; scalable via per-file sharding and lazy computation), then plan and implement in a disciplined, production-grade manner.

### Executive Audit Findings (Current State — Why Confidence Is Not Actionable)

**Primary Files/Systems Audited** (exhaustive: list_dir, 30+ read_file on key ranges, targeted grep for "confidence|resolution_confidence|high|medium|low|unresolved" across 17 files):

- `wikifier/parsers/javascript.py`: Core emitter of `resolution_confidence` string ("high"|"medium"|"low"|"unresolved"); downgrades in parse loop (dynamic_type expr→low, template→low, unknown→unresolved, is_conditional→low) + barrel paths (depth>=3→low, depth=2 conditional downgrade); _follow_reexports returns no conf (caller recomputes barrel_conf); rich dicts + new dynamic/expr_raw/cands fields.
- `wikifier/parsers/python.py`: Only "high" (package_hierarchy) / "medium"; _resolve_relative_import simplistic; no low/unresolved/dynamic/conditional/barrel support; "resolution_confidence" attached but weaker model.
- `wikifier/import_cache.py`: RICH_KEYS forwards is_*/barrel_*/dynamic_* + "confidence":str (default "medium"); normalize in update_file_data; build_dependency_graph ignores quality signals; no score/reasons yet.
- `wikifier.sh`: parse_parser_json_output (extracts resolution_confidence); process_file_imports + resolve_imported_module (hint + high/low adjustments); ~11-field pipe (conf as 3rd field after raw|mod); emit_resolved_pairs_to_table (uses conf); get_edge_style (high→-->, medium→-.->, else -..->); persist_rich + reparse loops; library table header has explicit "Confidence" column.
- `wikifier/mcp/server.py`: _get_resolved_from_cache + get_dependencies/get_dependents (return "confidence":str + rich flags in JSON; text notes only for cond/barrel/dynamic, no numeric); get_cycles no quality; zero filter params; no stats/explain/low tools.
- Surfaces: `library.md` (table uses string conf or omits when empty; no low-conf aggregation); Mermaid via sh styles; `wikifier/health.py` + file_health.* (zero confidence metrics); `wikifier/cli.py` (pure sh delegate); `test-js-flat/test_end_to_end_confidence.sh` (validates parser strings only); planning docs (v0.4-Execution-Plan, this md, Findings, journals) explicitly call out "confidence scores not yet actionable", "low actionability of confidence scores", "tools lack easy filtering, weighting, or explanations".
- Cross-refs: LDSI (#1) already plans "Actionable Confidence & Query" future filters; CIABRE (#6) will consume edge quality.

**Exact Root Causes Why Not Actionable**:
1. **Categorical strings only** — no 0.0-1.0 numeric for thresholds, ranking, averages, weighting, or agent filters/math.
2. **Zero explainability** — downgrades (dynamic, conditional, barrel depth, unresolved bare, Python asymmetry) are side-effects in code; no `confidence_reasons: ["dynamic_expression", "barrel_depth=3", "is_conditional"]` attached per edge.
3. **No filters on core query tools** — get_dependencies etc. return everything (or crude text); agents in monorepos must post-filter massive payloads. Missing: min_confidence, max_barrel_depth, include_conditional, etc.
4. **Absent diagnostic surfaces** — no get_low_confidence_edges(), explain_dependency(src, tgt), get_dependency_stats() for project uncertainty overview or per-edge drilldown + suggestions.
5. **Inconsistency & drift** — JS rich+penalized vs Python basic; sh resolver adjustments not always round-tripped to score; old caches lack rich flags.
6. **Superficial integration** — Mermaid 3-bucket coarse; library table raw strings no aggregation; cycles/health/refactoring prompts blind to quality (weakest-link deferred to #6); file_health ignores it.
7. **Scale liabilities** — eager full lists; no early pruning; single cache file; no lazy derivation path for v0 data.

**Evidence from Dogfood & Memory**: Post-v0.3.2 Gap #1 ~94-96% assessment: "Confidence scores not yet actionable (data exists but tools lack easy filtering, weighting, or explanations)." Matches Subagent #2 summary and current library/MCP output on real runs (strings visible, but unusable for "show only reliable edges").

**Strong Foundation for ACS**:
- All raw signals (is_dynamic, dynamic_type, is_conditional, barrel_depth/chain/via, resolved_path presence) already flow end-to-end (parser → sh → cache resolved_pairs → MCP/graphs/library).
- Proven extension patterns (barrel_chain 11th field, LDSI expr/cands b64, RICH_KEYS, variable-length IFS+defaults).
- Compute is trivial/cheap at emission time (one helper call per import).
- Back-compat trivial (string lives on; new fields additive).
- Synergies with #1 (dynamics affect conf), #3 (path quality → score), #4 (exports → high conf), #5 (diags → reasons), #6 (edge scores → weakest links).

### Proposed Long-Term Architecture: Actionable Confidence System (ACS)

**Vision**: Turn implicit, stringy, filterless confidence into a **numeric (0.0–1.0), explainable (reasons list), queryable, first-class subsystem**. Agents declaratively slice the graph ("min_confidence=0.6, max_barrel_depth=1"), diagnose ("explain why this import is 0.25"), or get project health ("stats: 12% low-conf edges, top reason=conditional"). Powers downstream intelligence while staying pragmatic, zero-dep, and evolvable for 10k+ file monorepos.

**Guiding Principles** (Wikifier philosophy + consistent with LDSI/CIABRE):
- **Numeric for Action + Reasons for Transparency**: Score enables filters/math/averages/ranking; reasons (short canonical tokens) enable explain, UI badges, future rules.
- **Strict Back/Forward Compat + Lazy**: Keep "confidence"/"resolution_confidence" string everywhere; new fields optional. Legacy entries derive score+reasons on read ("inferred").
- **Compute at Source, Filter at Query, Lazy Fallback**: Emit score/reasons once in parsers (augment existing downgrade logic); MCP/cache helpers prune early; old data never breaks.
- **Filters on Every Core Surface**: min_confidence (float 0-1), include_conditional (bool|None=all), max_barrel_depth, include_dynamic etc. on get_dependencies, get_dependents, get_cycles, and new tools.
- **Dedicated Tools for Triage & Insight**: get_dependency_stats (aggregates + top reasons + worst files), explain_dependency (per-edge: score, reasons, factors, suggestions), get_low_confidence_edges (actionable sorted list for "fix these first").
- **Deep but Non-Breaking Integration**: MCP (primary), sh/Mermaid/library (viz + Low-Conf section), cache (reusable helpers), cycles/health (metrics), prompts (agent usage), CLI (via richer artifacts).
- **Monorepo Scale & Evolution**: Per-file bounded work; early filter = token/IO savings; data model ready for sharded cache (per-dir json or manifest) without API change; reasons as open set (registry comment); versioned derivation.
- **Correctness First**: Never inflate score; low for any uncertainty; suggestions conservative ("verify at runtime").

**Data Model (Additive, v1.0)**:
In every parser dict, resolved_pair, cache entry, MCP response:
- "confidence" / "resolution_confidence": str (legacy, unchanged semantics)
- "confidence_score": float (0.05–0.95 typical; 2 decimals)
- "confidence_reasons": list[str]  (e.g. ["base:high", "barrel_depth=2", "conditional_context", "dynamic_expression"])

**Derivation Helper** (pure, ~20 LOC; placed in both parsers + backfill in cache):
```python
def _compute_confidence_score_and_reasons(base: str, **factors) -> tuple[float, list[str]]:
    # base_map, penalties for is_conditional, dynamic_type, barrel_depth, !resolved_path, etc.
    # build parallel reasons list from factors + base
    # clamp + round( , 2)
```
Called after all string logic; string kept for compat (or could derive string from score buckets if desired in future).

**Key Components** (no new files):
1. Computation in parsers (JS + Python parity).
2. sh pipeline extension (pipe fields + b64 for list like LDSI cands, persist, readers, emit, Mermaid style, table).
3. Cache: RICH_KEYS + normalize + backfill + 3 public query fns.
4. MCP: filter helpers + 3 new @mcp.tool() + enhanced get_* + prompt updates.
5. Library/Mermaid/Health/Cycles: consumers of score/reasons + new section.

**Persistence & Lazy**: Inside existing resolved_pairs (json native for lists); on load if absent → backfill using present flags + "legacy_inferred" reason. Future: import_cache sharding key = dir prefix.

### Phased Incremental Implementation Plan (Disciplined, Production-Grade)

**Phase 0 — Record Plan (Completed by This Edit)**:
- Full audit + architecture + this phased plan written into canonical gaps tracker (no new .md).
- Todo list active.
- Ready for code; "before major coding" requirement satisfied.

**Phase 1 — Data Model + Score/Reason Computation (Parsers + Cache Core)**:
- javascript.py: add _compute... (with docstring, mapping, penalties matching current downgrade rules + barrel logic); invoke at normal emission + barrel_conf sites; attach to every dict (normal + followed paths); update module docstring example + comments.
- python.py: call same-style logic (or local equivalent) in its two emission sites; produce reasons at minimum; consider emitting "low" in more failure-ish cases for parity.
- import_cache.py: extend RICH_KEYS tuple; copy new keys in normalize (handle list); implement backfill helper; implement the three public helpers (stats, low_edges filter+sort+limit, explain lookup by src+raw/resolved + factor dump + suggestions stub).
- Parser __main__ self-tests: assert on synthetic cases (static high, dynamic expr low+reasons, barrel depth 3, conditional).
- Isolation validate: `python -m wikifier.parsers.javascript <file>` shows new fields.

**Phase 2 — End-to-End Pipeline & Viz (sh + Library + Mermaid)**:
- wikifier.sh: extend parse_parser_json_output (extract + b64 json for reasons, str for score); bump pipe to support 13+ fields with safe defaults on short reads; update every IFS/read site (process, reparse ~876, persist python -c decode+attach to dict, emit_*, table printf); update get_edge_style to accept/ prefer score (score<0.3 → thick-dotted or class, update legend); extend table header/rows with Score column (or "Confidence (score)"); in generate library, after Resolved table or Circular, emit new "## Low-Confidence Dependencies (Actionable)" via python -c using cache helper (top N, truncated reasons).
- Cache emission paths tolerate missing fields.
- Roundtrip test: update-maps → inspect .wikifier_staging/import_cache.json + library.md + Mermaid output.

**Phase 3 — Query Filters + New Tools (MCP Primary Surface)**:
- mcp/server.py: 
  - Add filter logic (def _filter_pairs(pairs, min_conf=None, max_depth=None, include_cond=None, ...)) used by get_dependencies / get_dependents.
  - Implement + register 3 new @mcp.tool() using cache helpers: get_dependency_stats, explain_dependency, get_low_confidence_edges (with params per design).
  - Enhance existing get_* JSON/text to always include score/reasons when present; surface low-score notes.
  - Update get_cycles to optionally annotate edges (for #6 prep).
  - Docstrings + examples.
- Power users/CLI can call via python -c on the cache helpers.

**Phase 4 — Full Surface Integration + Agent Guidance**:
- Health: wire basic stats summary into generate_project_health_report or health.py if easy.
- Cycles: ensure rich edge metadata (incl. new score/reasons) available to future CIABRE (already is via pairs).
- Prompts (server.py): update find_architectural_smells, plan_refactoring, generate_project_health_report to explicitly call the new tools when confidence signals present ("use get_low_confidence_edges + explain...").
- CLI: richer library output is the main win; no sh cmd changes required in v1.
- File health markers can later reference low-conf files.

**Phase 5 — Hardening, Dogfood, Scale, Closeout**:
- Legacy backfill + mixed old/new cache tests (synthetic json).
- Perf: 50k-edge filter benchmark (should be <10ms).
- Dogfood: full update-maps on Wikifier + recipe-lab; call every new tool via MCP client or python; verify filters prune, scores intuitive, library section useful, no regressions in existing get_* / Mermaid / cycles.
- Polish: clamp/round consistent, reason token canonical list in code comment, suggestions in explain (e.g. "Replace dynamic with static if possible; or mark as intentional with reason").
- Record: update this md (status + metrics), top of CHANGELOG.md, v0.4-Execution-Plan summary if needed (minimal), parser wiki mds.
- Declare Limitation #2 substantially delivered for v0.4 baseline; unlocks #6 + health + agent autonomy.

**Metrics for "Done" per Phase**:
- P1: 100% parser emissions carry valid score (0.1-0.9) + non-empty reasons; Python parity improved.
- P2: Cache roundtrip lossless; Mermaid differentiates by score; library has Score + Low section.
- P3: Filters work (e.g. min=0.5 returns subset); 3 tools return correct structured data.
- P4/P5: Agents in prompts use tools; dogfood shows "only high-conf" queries succeed with fewer tokens; avg project score visible.

**Risks / Tradeoffs Addressed**:
- Pipe parsing fragility: variable-length + explicit defaults + tests on legacy data (same pattern as barrel_chain + LDSI fields).
- Formula "magic": explicit mapping + penalties in one helper; documented; reasons > score for humans.
- Cache bloat: reasons lists are tiny (<< dynamic_candidates); json ok; sharding note in code.
- Over-filter surprise: all filters default=None (include all) — additive only.
- No-new-files: strictly followed (edits only to existing .py/.sh + this md + CHANGELOG).
- Scope creep: only confidence; dynamic/cond/barrel already exist and feed it; no path or cycle logic here.

**Why ACS Architecture Wins for Scale & Future**:
- Solves the exact "not actionable" gap with minimal diff to proven pipeline.
- Early filtering + numeric = massive win for monorepo agents (get_dependencies on core file now returns 20 instead of 2000 items).
- Explains + stats close the observability loop ("why is confidence low here?").
- Perfect substrate for #5 (attach diag categories to reasons) and #6 (per-edge quality in cycle severity).
- Long-term: reasons registry, pluggable scorers, health dashboard, sharded cache all natural extensions.
- Zero risk to 94%+ quality baseline; every phase adds value immediately.

**Next Steps (Post-Plan Recording)**:
Execute Phase 1 (parsers + import_cache data model) using todo tracking and incremental search_replace + validation. Update this section's status after each phase gate. This fulfills the "clear incremental plan before major coding" + production-grade mandate.

**Status**: Plan recorded (Phase 0 complete). Implementation of Actionable Confidence System commencing.

**Owner**: Aron + Grok (long-term implementation subagent for Limitation #2 of Gap #1)
**Last Updated**: 2026-05-17 (Full audit of current non-actionable state + architectural design + phased plan recorded per Subagent #2 proposal and current mandate)

---

## Limitation #6: Cycle Impact Analysis & Breaking Recommendations Engine (CIABRE) — Deep Audit Findings & Incremental Implementation Plan (2026-05-17)

**Subagent Mandate (Long-term implementation for Limitation #6 of Gap #1)**: Implement the **Cycle Impact Analysis and Breaking Recommendations Engine** as a proper, scalable subsystem. Focus on metrics, analysis logic, recommendation generation, persistence, and integration with `get_cycles`, `library.md`, and agent prompts. Design for large monorepos and long-term evolution. Review the previous Subagent #6 proposal (full architectural design for severity, blast radius, weakest links, SCC support, ranked recs), then implement in high-quality, architectural manner. Produce clear incremental plan first, then execute.

### Executive Audit Findings (Post-Gap #1 Cycle Detection Closure)

**Primary Files Audited** (via exhaustive grep/read + subagent session artifacts):
- `wikifier/import_cache.py` (build_dependency_graph, find_cycles + _normalize, compute/set/get_cycles, reverse deps, RICH_KEYS for edge metadata, update_file_data)
- `wikifier/mcp/server.py` (get_cycles tool, get_dependents, prompts: find_architectural_smells, plan_refactoring, generate_project_health_report)
- `wikifier.sh` (update-maps phases 3c/3d for reverse + cycles persistence, generate library Circular Dependencies python -c, cmd_cycles, Mermaid cycleNode + highImpact styling via reverse map, cache_json emission)
- Supporting: library.md (current flat cycle list + generic 4-bullet recs), v0.4-Execution-Plan.md, Findings/m2_rem_08_*.md, journal entries, synthetic cycle fixtures (recipe-lab-dogfood/.../cycle{A,B,C}.js), CHANGELOG, memory session for subagent #6 (ID 019e33de-660c-79d1-9294-ebdd6b4d78f0)

**Current State (Post M2-Rem-08 / v0.3.2 Gap #1 ~94-96%)**:
- **Strengths**: Reliable DFS cycle detection (with rotation+direction dedup), persisted under `_cycles` during every update-maps (freshness guarantee), exposed in CLI/MCP/library/Mermaid (node highlighting + reverse impact already present for "blast" visuals at node level). Rich per-edge metadata (confidence, is_dynamic, is_conditional, via_barrel/*) fully in `resolved_pairs` and cache — unused for cycles today but perfect raw material. `_reverse_dependencies` enables O(1) external impact queries. Python-lib + shell + MCP all consistent. Synthetic 3-cycle fixtures validate detection.
- **Exact Gaps (Limitation #6)**: 
  - Flat lists only: no severity/risk scoring, no per-cycle blast radius quantification, no coupling/density, no weakest-link identification using rich edge signals.
  - Recommendations are static boilerplate in 3 places (MCP text, library.md, CLI) — not context-aware (e.g., "this cycle has a low-conf dynamic edge at X→Y; break there first").
  - No SCC / maximal cluster view (current finds elementary cycles; large tangles in monorepos produce noisy duplicate cycles).
  - No structured JSON for agents beyond raw cycle lists; prompts reference "circular risks" but do not consume analysis.
  - Agents doing `plan_refactoring` or `find_architectural_smells` must manually correlate `get_cycles` + `get_dependents` + library.md.
- **Evidence**: Subagent #6 audit + post-closure memory assessment explicitly called out "Cycle impact analysis (detection works but lacks blast-radius or recommended break-point guidance)" as one of 6 remaining for 98%+ autonomous reliability.
- **Foundation Quality**: Excellent. Graph + reverse + rich pairs + persistence hook + multi-surface = ideal for adding analysis layer without core changes. Zero-dep, incremental update friendly, monorepo-tested (RecipeLab 250+ files).

**Missed Opportunity**: The rich metadata pipeline (Lim #1-5 work) makes "weakest link" trivial to compute; node-level highImpact styling already exists — cycle-level aggregation is the natural evolution.

### Proposed Long-Term Architecture: Cycle Impact Analysis & Breaking Recommendations Engine (CIABRE)

**Vision**: A **layered, pure-Python, registry-extensible analysis subsystem** that transforms raw cycle lists into actionable intelligence (severity-ranked, blast-quantified, weakest-link-targeted, rec-ranked) for agents and humans. Turns "there is a cycle" into "this HIGH-severity 4-cycle in core/ tangles 2 high-impact modules, externally impacts 47 files via a brittle low-conf dynamic edge; break it safely by extracting shared factory to utils/core.js".

**Guiding Principles** (Wikifier-aligned, massive-monorepo ready):
- **Separation + Leverage**: Analysis is pure functions over existing graph/reverse/rich cache. No mutation of detection. Initial home: extend `import_cache.py` (no new file creation per guidelines; clean section + public fns). Future split to `cycle_analysis.py` when mature.
- **Data Model First, Versioned**: Structured, JSON-serializable, forward-compatible dicts. Include "analysis_version".
- **Correctness + Transparency > Magic**: Low-conf edges downgrade confidence in recs; explicit "verify" notes. Agents can filter.
- **Scalable Defaults**: Always-computed cheap summary + top-K detailed items. Direct blast (reverse map); optional bounded transitive. SCC for "tangle view" + elementary cycles for precision. Optional dir-prefix clustering.
- **Evolvable**: Rule registry for metrics + recommendations (add new without core edit). Pluggable later (history signals, ML-lite).
- **Surfaces Unified**: Enhance `get_cycles(analysis=True)` as primary; library.md, CLI, Mermaid, prompts all consume the persisted `_cycle_analyses`.
- **Testable & Dogfoodable**: Synthetic graphs in code + real fixtures. End-to-end: update-maps → rich library → MCP call with analysis.
- **Zero New Deps, Bounded Work**: Pure stdlib (or current imports). Analysis cost << graph build.

**Core Components** (implemented incrementally):
1. **Graph/SCC Layer**: `build_dependency_graph` (existing) + new `_find_strongly_connected_components(graph) -> List[List[str]]` (Kosaraju 2-pass DFS, ~30 LOC, pure).
2. **Metrics Engine**:
   - `_build_edge_metadata_map(cache) -> Dict[Tuple[str,str], Dict]` (from resolved_pairs, keys=(src,tgt))
   - `_compute_blast_radius(members: set, reverse_map) -> int` (direct external dependents; future note for transitive BFS with limit)
   - `_compute_coupling_density(graph, members) -> (internal_edges, density)`
   - `_identify_weakest_links(edges_in_cycle, emap, top_n=3)` (risk = conf_weight + dynamic*2 + conditional + barrel_penalty)
   - `_score_severity(cycle_len, blast, risk_signals, high_impact_count) -> (float_score, "CRITICAL"|"HIGH"|"MEDIUM"|"LOW")`
3. **Analysis Aggregator**: `analyze_cycle(cycle, graph, cache, reverse_map, emap) -> full_dict` and `analyze_scc(scc, ...)` 
4. **Recommendation Engine**: `generate_breaking_recommendations(analysis) -> List[RecDict]` ; `BREAKING_RECOMMENDATION_RULES: List[Callable]` registry. Initial 5-7 rules (weakest-edge first, 2-cycle type split, layer move, lazy, shared-extract, interface, barrel-reorg for JS).
5. **Persistence & Compute**: `compute_cycle_analyses(cache, **opts) -> Dict`, `get_cycle_analyses`, `set_cycle_analyses` (mirrors cycles pattern, under `_cycle_analyses`).
6. **Surfaces & Integration**:
   - `get_cycles(..., analysis: bool = False, max_items: int | None = None, include_recs: bool = True)`
   - library.md generator + CLI + prompts enriched.
7. **Data Model v1.0** (see below).

**Data Model (JSON-safe, persisted)**:
```json
{
  "analysis_version": "1.0",
  "generated_at": "...",
  "summary": {
    "total_cycles": 3,
    "total_sccs": 2,
    "files_in_cycles": 9,
    "high_severity_count": 1,
    "max_blast_radius": 47,
    "avg_cycle_len": 3.2
  },
  "cycles": [  // analyses for elementary cycles (or top-K)
    {
      "id": "norm-cycle-key-or-index",
      "cycle": ["a.js", "b.js", "c.js", "a.js"],
      "unique_files": ["a.js","b.js","c.js"],
      "length": 3,
      "external_blast_radius": 47,
      "severity": "HIGH",
      "score": 14.7,
      "coupling": {"internal_edges": 4, "density": 0.67},
      "risk_signals": {
        "low_conf_edges": 1,
        "dynamic_edges": 1,
        "conditional_edges": 0,
        "barrel_involved": false,
        "low_conf_ratio": 0.33
      },
      "weakest_links": [
        {"from": "c.js", "to": "a.js", "confidence": "low", "is_dynamic": true, "reason": "expression in conditional"}
      ],
      "recommendations": [
        {"rank": 1, "strategy": "lazy_or_factory", "target_edge": "c.js→a.js", "rationale": "Safest break on low-conf dynamic; avoids runtime cost for non-taken path", "hint": "Move require inside fn or use factory", "safety": "high (low-conf edge)"}
      ],
      "member_context": {"high_impact_members": 2, "avg_dependents": 12.4}
    }
  ],
  "sccs": [ /* analogous for maximal clusters, often more actionable for big refactors */ ]
}
```

**Phased Incremental Implementation Plan (High-Quality, Monorepo-Ready, Guideline-Compliant)**:

**Phase 0 — Plan & Design (This step, completed by recording here)**:
- This section serves as the official incremental plan and design doc (modeled on Limitation #1).
- Define all public + private signatures, data model v1.0, extension points.
- No code yet; ensures architectural review before edits.
- Update todos + any cross-refs in v0.4-Execution-Plan.md / Findings if critical (minimal).

**Phase 1 — Core Analysis Logic (Pure, Testable, No Persistence/Surfaces Yet)**:
- Target: Extend `wikifier/import_cache.py` (new section after existing cycle funcs, before __main__).
- Implement (with docstrings, internal _ helpers):
  - Kosaraju `_find_strongly_connected_components(graph: Dict[str,List[str]]) -> List[List[str]]`
  - Edge map builder, blast, coupling, weakest, severity scorers (use math for log if needed; stdlib only).
  - `analyze_cycle(...)` and `analyze_scc(...)`
  - `generate_breaking_recommendations(analysis: dict) -> list`
  - Top-level `compute_basic_cycle_analyses(cycles, graph, cache, reverse_map) -> list[dict]` (for Phase 2)
  - Registry skeleton + 4 starter rules (document how to add 5th).
  - Self-contained tests: `if __name__ == "__main__":` synthetic 2-cycle, SCC of 4, dynamic-weak-edge case; assert scores, weakest, recs.
- Goal: Functions runnable in isolation via `python -c "import wikifier.import_cache as ic; ..."` . Zero cache mutation.
- Validation: Pass on hand-crafted graphs matching real cycleA/B/C patterns + low-conf variants.

**Phase 2 — Persistence, Compute Hook, End-to-End Freshness**:
- Add `get_cycle_analyses(cache)`, `set_cycle_analyses(cache, analyses: dict)`, `compute_cycle_analyses(cache, include_sccs=True, max_items=50) -> dict` (calls core + attaches summary).
- Wire into `wikifier.sh`:
  - In Phase 3d (after set_cycles/save): add python -c block to compute_analyses, set, save (parallel to cycles).
  - Guarded by WIKIFIER_DEBUG if needed.
- Update `compute_cycles` callers? No — new path.
- In cache load paths, analyses optional (on-the-fly compute if absent, for old caches).
- Python library usage: `ic.compute_cycle_analyses(cache)` now available post-update.
- Add RICH_KEYS or analysis_version handling.

**Phase 3 — Primary Surface: MCP `get_cycles` + Python API Polish**:
- Edit `wikifier/mcp/server.py:get_cycles`:
  - Add params: `analysis: bool = False`, `include_recommendations: bool = True`, `max_items: Optional[int] = None`, `project_root`.
  - If analysis: load or compute analyses; return augmented JSON (full or filtered top by score); enrich text with "Severity: HIGH | Blast: 47 files | Weakest: c.js→a.js (low, dynamic) | Top Rec: ..."
  - Handle large output gracefully (truncate recs, summary-first).
  - Update docstring + return examples.
- Ensure `get_cycles(analysis=True)` is the "power tool" for agents.
- Expose compute fns cleanly (already via import_cache).

**Phase 4 — Human + Report Surfaces: CLI, library.md, (optional) Mermaid**:
- `wikifier.sh:cmd_cycles`: python -c to load analyses if present; rich formatted output.
- Critical: `generate_resolved...` python -c block for "## Circular Dependencies" (lines ~1616+): 
  - If `_cycle_analyses` present, per-cycle emit tailored "Impact Analysis" + ranked recs (use severity/blast/weakest/rec[0].rationale).
  - Fallback to current generic if absent (backward compat).
- Mermaid: (low priority in v1) possible node class per severity or weakest edge annotation; reuse cycleNode for now.
- Ensures `library.md` becomes the "human consumable full report".

**Phase 5 — Agent Intelligence Integration (Prompts & Higher Value)**:
- Edit prompts in server.py:
  - `find_architectural_smells`: Add explicit step "Call get_cycles(format='json', analysis=True); prioritize by severity + blast; surface weakest + recs in output."
  - `plan_refactoring(target)`: "If target participates in cycle, fetch its analysis and include breaking strategy in plan."
  - `generate_project_health_report`, `audit...`: Mention "High-severity cycle debt" as top architectural item.
- This makes Limitation #6 directly reduce agent follow-up questions.

**Phase 6 — Validation, Hardening, Long-Term Evolution & Closeout**:
- Add synthetic tests (extend existing or in import_cache __main__ / separate but edit-only).
- Full dogfood: On Wikifier itself + recipe-lab synthetic cycles (run update-maps, inspect library.md + MCP).
- Perf: Synthetic 500-2000 node monorepo sim; ensure analysis < 100ms post-graph.
- Polish: Confidence tie-in (flag "unreliable analysis" if >50% low-conf edges), dir-based grouping, export to health matrix?
- Docs: Minimal edits to this file (status), CHANGELOG top entry, README if milestone, javascript.py.wiki.md or health if relevant (no new files).
- Evolvability notes in code: "To add new rec strategy: append to BREAKING...RULES".
- Mark Limitation #6 "in-progress → substantially addressed" here.
- Future phases (post this mandate): pluggable, history signals, full transitive blast with memo, chisel-tool integration.

**Risks / Tradeoffs & Mitigations** (addressed in design):
- Noise from many cycles in large SCC: Always provide SCC view + top-K by severity.
- Over-confident recs on low-quality edges: Explicit safety notes + "verify with get_file_wiki + runtime".
- Perf on monorepo (10k files): Compute only on update (incremental already), summary-only default, pure loops fast.
- Bloat: All new code private/_ or clearly sectioned; no change to hot paths (build_graph, find_cycles remain lean).
- Stale analyses: Always recompute in same step as cycles (guaranteed fresh).
- Guideline "no new files": Strictly followed (all in import_cache.py + callers).

**Why This Architecture Succeeds for Massive Codebases & Long-Term**:
- Directly delivers the "actionable intelligence" missing from basic detection, enabling autonomous agents to reason about *why a cycle matters* and *exactly how to break it* with minimal human intervention.
- Builds 100% on proven pipeline (rich pairs, reverse, persistence during update-maps) — zero risk to existing 94%+ quality.
- Incremental (each phase adds value, prior surfaces unchanged), evolvable (registry + versioned model), correct-by-design (confidence-aware).
- Positions Gap #1 for true 98%+ "set and forget" agent reliance on dependency tools.
- Matches Subagent #6 vision while respecting "prefer edit existing, no new docs unless asked".

**Metrics for Success (per phase)**:
- Phase 1: All helpers return expected on 5 synthetic cases (incl. SCC collapse of multiple cycles).
- Phase 2-4: `update-maps` produces `_cycle_analyses`; `get_cycles(analysis=true)` + library.md show tailored content for the 3 synthetic cycles.
- Phase 5: Prompts now drive better recs in simulated agent runs.
- Overall: "tell me about this cycle" follow-ups drop; refactoring plans include specific break points.

**Next Steps After Recording (Immediate Execution)**:
Begin Phase 1 implementation in `import_cache.py` (core functions + inline tests). Use todo tracking. Validate isolation. Then wire sequentially. This is the principled, architectural path — not ad-hoc patches.

**Status**: Plan recorded (Phase 0 complete). **Phases 1–3 + 5 core implemented and live**:
- Core engine (SCC, metrics, weakest, recs, basic compute) + self-tests passing.
- Persistence (get/set/compute_cycle_analyses) + wired into update-maps (3e) so every run now produces _cycle_analyses.
- Full MCP get_cycles(analysis=True) with rich JSON + enriched text.
- CLI and library.md generation enriched with impact/recs output (demonstrates end-to-end).
- One key agent prompt updated.
- All changes edit-only (import_cache.py, sh, server.py, md, CHANGELOG); high-quality, documented, monorepo-ready.
- Ready for Phase 4 polish + full dogfood + close.

**Owner**: Aron + Grok (long-term implementation subagent for Limitation #6)
**Last Updated**: 2026-05-17 (Phases 1-3+5 implemented; subsystem functional and integrated)