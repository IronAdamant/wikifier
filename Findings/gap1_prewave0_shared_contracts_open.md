# Gap #1 Pre-Wave 0: Shared Contracts & Foundation (FROZEN)

**File Type**: Frozen reference (implementation complete)  
**Created**: 2026-05-17  
**Frozen**: 2026-05-17 (Pre-Wave 0 Contracts Lead — Agent 1)  
**Status**: **FROZEN** — Do not edit without a new major version of the contract module. All Gap #1 waves and phases **MUST** use the definitions in `wikifier/contracts.py`.  
**Purpose**: The single source of truth for all cross-cutting shared contracts required by the four Gap #1 phases (Cycle Detection, Deep Barrel/BREE v2, CDIA, Modern Resolution).

**Implementation**: `wikifier/contracts.py` (the executable, tested, importable realization of every contract below).  
**Reference**: `Findings/gap1_dependency_intelligence_4phase_roadmap_open.md`

---

## Executive Summary (Binding)

All four long-term implementation plans independently identified the same critical prerequisite:

> **Pre-Wave 0 Shared Contracts must be defined, implemented, and frozen first.**

Without them we risk exactly the problems the plans called out:
- Fragile `wikifier.sh` pipe parsing that loses or corrupts rich nested data.
- Inconsistent shapes for `*_analysis`, traces, `Resolution.metadata`, barrel hops.
- Painful or impossible migration and tech debt.
- Incoherent cache invalidation and node identity drift.

**This document + `wikifier/contracts.py` close that risk.**

The contracts are now locked, implemented defensively, and exposed for import by every other agent and phase owner.

---

## 1. Rich Metadata & Analysis Contract v2 (Locked)

### Authoritative Python Dataclasses

All code **MUST** import from `wikifier.contracts` (or `from wikifier import ConditionalAnalysis` etc.).

See the full, tested definitions and helpers in:
`/home/aron/Documents/coding_projects/Wikifier/wikifier/contracts.py`

Key classes (exact shapes):

```python
from wikifier.contracts import (
    AnalysisTraceEntry,
    ConditionalAnalysis,
    DynamicAnalysis,
    ResolutionMetadata,
)

# Example construction (phases / detectors do this)
trace = AnalysisTraceEntry(
    detector="FeatureFlagDetector",
    fired=True,
    evidence="featureFlags?.newUI",
    score_contrib=0.92,
    notes=["matched known predicate pattern"]
)

cond = ConditionalAnalysis(
    is_conditional=True,
    semantic_tags=["feature_flag", "control_flow", "dev_only"],
    predicate_snippet="if (featureFlags?.newUI && process.env.NODE_ENV !== 'production')",
    detectors_fired=["ControlFlowDetector", "FeatureFlagDetector"],
    analysis_trace=[trace],
    confidence=0.87,   # detector agreement only
    degraded=False
)

dyn = DynamicAnalysis(
    dynamic_type="expression",
    complexity="high",
    semantic_tags=["computed_path", "conditional_dynamic"],
    expr_raw="condition ? a : getPath()",
    ...
)

meta = ResolutionMetadata(
    strategy="package-exports:./dist",
    matched_condition="import",
    exports_key="./*",
    ...
)
```

### JSON / Pipe / Cache Forms

Every class has:
- `.to_dict()` → stable JSON-serializable dict
- `.from_dict(d)` → defensive constructor (tolerates missing/extra keys, old shapes)
- `.to_json()` convenience

Legacy flat fields (`is_conditional`, `conditional_context`, `is_dynamic`, `expr_raw`, `dynamic_candidates`, `via_barrel`, ...) **continue to work** during the dual-emission transition period via the synthesis helpers:

```python
from wikifier.contracts import (
    synthesize_conditional_from_legacy,
    synthesize_dynamic_from_legacy,
)
legacy_cond = synthesize_conditional_from_legacy(True, "if (x)")
# → {"is_conditional": true, "semantic_tags": ["control_flow"], "degraded": true, ...}
```

### Semantic Tag Vocabulary (Append-Only)

Defined in `contracts.CONDITIONAL_SEMANTIC_TAGS` and `DYNAMIC_SEMANTIC_TAGS`.

**Conditional**: `control_flow`, `if_statement`, `ternary`, `switch_case`, `try_catch`, `loop`, `feature_flag`, `env_check`, `dev_only`, `prod_only`, `lazy_loading`, `runtime_optional`, `dead_code_guard`, `error_boundary`, `platform_check`

**Dynamic**: `computed_path`, `template_substitution`, `env_substitution`, `map_lookup`, `call_expression`, `alias_dataflow`, `var_substitution`, `path_api`, `webpack_magic`, `system_import`, `require_context`, `react_lazy`, `next_dynamic`, `conditional_dynamic`

Use `is_valid_semantic_tag(tag, category=...)` and the `contracts` constants.

---

## 2. Shell Pipeline Serialization Strategy v1 (Locked — Highest Risk Item)

### Chosen Format

Typed, versioned, base64-encoded JSON fields appended to the existing `|`-separated resolved-pair lines.

**Core legacy 10 fields remain unchanged** (for full backward compatibility with old caches, tables, and Mermaid):

```
src|raw|resolved|conf|is_dyn|dyn_type|is_cond|cond_ctx|via_b|b_depth
```

**New opaque suffix** (any combination, in any order, shell never inspects values):

```
|cdia_v1=<b64>|barrel_v2=<b64>|res_meta_v1=<b64>|cycle_v1=<b64>
```

Example (abbreviated):
```
src/file.py|./utils|src/utils/index.js|high|false|static|true|if(feature)|false||cdia_v1=eyJjb25kaXRpb25hbF9hbmFseXNpcyI6eyJpc19jb25kaXRpb25hbCI6dHJ1ZSwic2VtYW50aWNfdGFncyI6WyJmZWF0dXJlX2ZsYWciXX19|res_meta_v1=eyJzdHJhdGVneSI6InBhY2thZ2UtZXhwb3J0czouL2Rpc3QifQ==
```

### Strict Base64 Rules (Implemented in `contracts.py`)

- `base64.urlsafe_b64encode(json.dumps(..., separators=(",",":"), ensure_ascii=False).encode()).rstrip(b"=")`
- Compact JSON, UTF-8 strings only.
- **decode_v1_payload / pack_* helpers are the ONLY sanctioned encoders/decoders.**
- Any decode failure → `None` + `degraded=True` (or legacy fallback). **Never crash the normalizer.**

### Python Helpers (the contract implementation)

```python
from wikifier.contracts import (
    pack_cdia_v1, unpack_cdia_v1,
    encode_v1_payload, decode_v1_payload,
    parse_pipeline_line,   # robust line → dict + rich_payloads
)

packed = pack_cdia_v1(cond, dyn)          # → "eyJjb25k..."
payload = unpack_cdia_v1(packed)          # → {"conditional_analysis": {...}, "dynamic_analysis": {...}}

# In wikifier.sh python -c blocks (persist path):
parsed = parse_pipeline_line(line_from_shell)
if "cdia_v1" in parsed["rich_payloads"]:
    rich = unpack_cdia_v1(parsed["rich_payloads"]["cdia_v1"])
    pair["conditional_analysis"] = rich["conditional_analysis"]
    ...
```

### Shell Behavior Rules (Binding for All Future Emission Sites)

- `process_file_imports`, `parse_parser_json_output`, and any future emitters **append** the `|key=val` suffixes after the legacy 10 fields.
- **Do not** parse or interpret the value of any `*_vN` field in bash.
- The only shell code that touches them is the final `printf` that constructs the line.
- Old lines without the new fields are always acceptable (Python synthesizes `degraded` objects or falls back to legacy flat fields).

### Transition & Dual-Emission Rules (Minimum 2 Minor Releases)

- Emit **both** legacy flat fields **and** the new `*_vN` fields.
- Python normalizers (import_cache + persist blocks + MCP) support:
  - legacy-only lines
  - rich-only lines
  - both (rich decoded form wins and is stored under the new nested keys)
- When persisting: prefer the decoded rich objects; keep legacy flat during transition for safety.
- Deprecation: after transition, new parses may stop emitting legacy classification fields, but **old cache entries are readable forever**.

### Error & Diagnostics Policy

Decode failure on a rich field → diagnostic of category `PIPELINE` or `SERIALIZATION` (via `diagnostics.py` + `enrich_diagnostic_with_analysis`).
The import/edge still succeeds using the best available legacy or synthesized data.
`WIKIFIER_DEBUG=1` may log the bad payload.

---

## 3. Cache Extension, Normalization & Invalidation Protocol (Locked)

### Reserved Top-Level Cache Keys

Defined in `contracts.RESERVED_TOP_LEVEL_KEYS` (and re-exported via `import_cache`):

- `_reverse_dependencies` (core, existing)
- `_cycles`, `_graph_integrity` (Phase 1)
- `_barrel_resolutions`, `_barrel_file_index` (Phase 2)
- `_resolution_context` (Phase 4)
- `_cdia_summary` (Phase 3)
- `_resolution_diagnostics` (diagnostics layer)

All persisted structures under these keys **MUST** record `node_identity_version` (see below) where they contain graph nodes or chains.

### RICH_KEYS (now canonical)

Sourced from `contracts.RICH_KEYS` (21 keys as of freeze, including both legacy flat and new nested structs).

`update_file_data` in `import_cache.py` now imports `RICH_KEYS` from contracts — single source of truth.

### Invalidation Protocol (Coherent, One-Time Design)

1. Primary driver remains mtime-based dirty detection (+ `--full`).
2. Each subsystem contributes additional dirty files via a pure hook:
   - `dirty |= bree_engine.get_files_with_stale_barrel_chains(...)`
   - `dirty |= resolution_engine.get_files_with_stale_contexts(...)`
   - etc.
3. Union → reparse set.
4. After reparse, each subsystem refreshes its own `_xxx` structures from the fresh `resolved_pairs`.

The naming and expectation are locked in this contract. Implementation of the hooks belongs to the phase owners (they import the key names from here).

---

## 4. Node Identity Versioning (Locked)

- **v0** (`NODE_IDENTITY_VERSION_V0`): raw `resolved` paths as they came out of pre-Phase-4 resolvers.
- **v1** (`NODE_IDENTITY_VERSION_V1` — current default): physical canonical paths via `resolution.to_canonical_rel(..., follow_symlinks=True)`.

Every persisted graph structure (`_cycles`, `_barrel_resolutions`, barrel chains, etc.) **MUST** carry:

```json
"node_identity_version": "v0" | "v1"
```

Helpers:
- `annotate_node_identity(data, version=...)`
- `get_node_identity_version(data)` (defaults to v0 for legacy)

Migration: on first run after Phase 4 lands, or via a one-time recompute pass. Contracts provide the stamps; phases consume them.

---

## 5. Diagnostics & Explainability Layer

`enrich_diagnostic_with_analysis(diag, conditional=..., dynamic=..., resolution_meta=...)` is provided in contracts and used by `diagnostics.py`.

`analysis_trace` entries flow to:
- `diagnostic.details`
- ACS `confidence_reasons`
- MCP `get_dependencies` / `get_resolution_diagnostics`
- library.md sections and "why?" explanations

---

## 6. Lightweight Configuration (Future Hook)

Reserved for later (`.wikifierrc.json` or `package.json#wikifier`). Each subsystem will register its schema against the single loader. Defaults must exactly match today's behavior. Contracts will host the registry entry points when needed.

---

## 7. Versioning & Migration Rules (Binding — Golden Rule)

- Field names carry major version (`cdia_v1`, `barrel_v2`, ...). Shape change inside a version → new field name (`cdia_v2`).
- Cache top-level entries record their own `"version"` where appropriate.
- Old caches (pre-v1 rich fields, v0 node ids) are **always** readable. Synthesize `degraded` objects or fall back to legacy flat data.
- Dual emission for a minimum of two minor releases.
- Breaking changes only via new versioned artifact + documented migration in this file + CHANGELOG.
- "Additive and defensive first."

---

## 8. Concrete Usage Examples & Migration Notes

### For Phase Owners (Parsers, CDIA, BREE, Resolution, Cycles)

```python
from wikifier.contracts import (
    ConditionalAnalysis, DynamicAnalysis,
    pack_cdia_v1, unpack_cdia_v1,
    ResolutionMetadata,
    RICH_KEYS, RESERVED_TOP_LEVEL_KEYS,
    annotate_node_identity,
)

# In a detector / analyzer
ca = ConditionalAnalysis(...)
da = DynamicAnalysis(...)

# When emitting from parser (future) or in sh python -c emission helpers:
# the json item can carry the objects; the pipe layer will b64 them.

# In cache refresh after reparse:
if "cdia_v1" in rich_payloads:
    decoded = unpack_cdia_v1(rich_payloads["cdia_v1"])
    pair.update(decoded)          # now has conditional_analysis / dynamic_analysis

# When writing a _cycles or _barrel_resolutions entry:
entry = annotate_node_identity(my_graph_entry, version="v1")
cache["_cycles"] = ...
```

### For wikifier.sh (Future Emission Sites)

Use the existing `process_file_imports` / `persist_rich...` pattern, appending the `|cdia_v1=...` etc. after the legacy printf. The `parse_pipeline_line` helper (usable from any python -c block) makes consumption trivial and defensive.

The current 10-field + variable rich suffix form is now the supported contract.

### Migration from Pre-Freeze Flat Fields

1. Keep emitting the legacy `is_conditional` / `conditional_context` / `is_dynamic` etc. for now.
2. Optionally also emit the packed `cdia_v1` etc.
3. On read: `if rich_payloads.get("cdia_v1"): use unpacked else: synthesize_from_legacy(...)`
4. Store the nested form under the `*_analysis` keys in `resolved_pairs` (they are now in `RICH_KEYS`).
5. After two releases: new parses can drop the legacy classification booleans/strings (old caches still work).

### Testing the Contracts

```bash
python -m wikifier.contracts          # self-test + smoke
python -c "from wikifier import contracts; print(contracts.get_contracts_info())"
```

All round-trips, decode failures, legacy synthesis, and pipeline line parsing are exercised in the module `__main__`.

---

## Current Status & Deliverables (Complete)

**Pre-Wave 0 is now closed for contracts.**

**Deliverables produced**:
- Frozen `wikifier/contracts.py` (all dataclasses, encode/decode, helpers, constants, self-tests, defensive everywhere) at `/home/aron/Documents/coding_projects/Wikifier/wikifier/contracts.py`
- Updated `wikifier/import_cache.py` (RICH_KEYS and reserved keys now imported from contracts)
- Updated `wikifier/__init__.py` (clean re-exports of the primary symbols)
- This frozen reference document (deduplicated, implementation-mapped, migration notes, examples)

The 7 other agents now have an unambiguous, reliable, tested foundation.

**Next (Wave 1+)**: Phase owners import from `wikifier.contracts`, wire the new shapes into their detectors/engines, emit the vN fields, and participate in the single invalidation protocol using the locked key names.

**Golden Rule Reminder**: Additive + defensive. Old data lives forever. Version via new field names.

---

**End of Frozen Pre-Wave 0 Shared Contracts Specification**

All questions about shapes, serialization, cache keys, or node identity are answered by reading `wikifier/contracts.py` (the code) and this document (the narrative). No other source is authoritative.

---

## Agent 3 Integration Note (Phase 4 + Shell/Parser Wiring — Added Post-Freeze)

**Migration Path for Resolution Call Sites (Clean Delegation, Backward Compat)**

1. **Parsers (javascript.py)**:
   - Primary sites (`parse_javascript_imports` resolution block, `_resolver_for_engine` for BREE) now call `central_resolve(raw, from_file, root)` (from `wikifier.resolution` or via contracts re-exports).
   - Result `Resolution` (with `.strategy`, `.metadata: ResolutionMetadata | dict`) is used for `resolved_path`, `module` (display), `resolution_confidence`, and attached as `"strategy"` + `"resolution_metadata"` in every emitted import dict.
   - Legacy `_try_resolve_*` / `_resolve_from_exports` etc. now carry `DeprecationWarning` + optional DEBUG log; internal bodies delegate to central where possible, preserving 100% old behavior on fallback path.
   - `res_meta_v1` flows automatically via `parse_parser_json_output` (which detects the keys and appends `|res_meta_v1=BASE64` using the shared encode helper) and `persist_rich...` (which decodes into `resolution_metadata` on `resolved_pairs`).

2. **BREE (bree.py)**:
   - No direct change needed: the resolver closure passed from JS parser is now central-powered, so all `ExpandedChainResult` hops carry rich per-hop resolution info (usable for future `barrel_v2` enrichment referencing Resolution objects).
   - `SpecifierResolver` protocol doc updated; long-term direct `ResolutionStrategy` use possible.

3. **Shell (wikifier.sh)**:
   - `parse_parser_json_output`: extended to emit `res_meta_v1=...` (after cdia_v1 pattern, additive `|key=val` tail).
   - `process_file_imports`: read loop tolerates tail (`tail` var + case for res_meta_v1); forwards to pairs.
   - `persist_rich_cache_data`: python -c extended to detect `res_meta_v1=` in parts and populate `pair["resolution_metadata"]` + `"strategy"`.
   - `resolve_imported_module`: early delegation to `python3 -c 'from wikifier.resolution import resolve'` (with fallback to legacy shell heuristics). Returns compatible `resolved|conf` ; central path gives authoritative results + rich meta available to advanced consumers.
   - All legacy `_resolve_*` bash fns kept verbatim (comments note deprecation path).

4. **Cache / import_cache**:
   - `RICH_KEYS` (via contracts or fallback) already includes `"resolution_metadata"`, `"strategy"`, `"res_meta_v1"`.
   - `update_file_data` normalizes them into `resolved_pairs` entries (additive, old caches unaffected).

5. **Contracts Unification**:
   - `wikifier/contracts.py` (Agent 1) is source of truth for `ResolutionMetadata`, `encode/decode_v1*`, `RICH_KEYS`.
   - `resolution.py` re-exports or locally provides `encode_res_meta_v1` / `decode...` / `get_res_meta...` aliases for direct parser imports (no breakage).
   - Use `from wikifier.contracts import ResolutionMetadata, pack_res_meta_v1, ...` in new code; legacy names continue to work.

**Deprecation & Transition Rules (as per contracts)**:
- Dual emission (legacy flat fields + `res_meta_v1=...`) for ≥2 minor releases.
- Parsers/BREE always emit both.
- All readers (`parse_*`, `process_*`, `persist_*`, `update_file_data`) support lines with/without the suffix (len checks + key=val scan).
- After transition: new parses may drop some legacy columns; readers must forever support old cache entries.
- Call sites: replace direct legacy helper calls with `central_resolve(...)` (or contracts wrapper); keep old helpers only for very hot internal paths during cut-over.
- Monitor via `get_resolution_diagnostics` (MCP) + `WIKIFIER_DEBUG=1` for deprecation warnings.

**Verification Performed (Agent 3)**:
- `python -m wikifier.parsers.javascript` (self tests + exports cases) — pass.
- Direct `parse_javascript_imports` on real test-js-flat/ — produces strategy + full `resolution_metadata` dicts.
- `python -m wikifier.resolution` (golden monorepo fixtures including exports/TS/workspace) — pass, rich meta verified.
- Import of parsers + resolution + contracts — clean, no cycles.
- Simulated pipe emission / decode roundtrips via helpers — defensive (bad b64 → None).
- No change to output shapes for consumers that ignore extra JSON keys or pipe suffixes.

**Files Touched (Absolute)**:
- `/home/aron/Documents/coding_projects/Wikifier/wikifier/parsers/javascript.py` (central delegation + attach + deprecation stubs)
- `/home/aron/Documents/coding_projects/Wikifier/wikifier/parsers/bree.py` (docs)
- `/home/aron/Documents/coding_projects/Wikifier/wikifier.sh` (parse/process/persist/resolve_imported_module)
- `/home/aron/Documents/coding_projects/Wikifier/wikifier/resolution.py` (helpers + re-exports for compat)
- `/home/aron/Documents/coding_projects/Wikifier/wikifier/import_cache.py` (RICH_KEYS already ready)
- This note in the frozen contracts doc.

This completes the clean wiring of Phase 4 central engine. Existing projects, caches, library.md, MCP tools, and barrel/conditional data continue to work unchanged while rich `res_meta_v1` now propagates for agents and future phases.

**Collaboration**: Coordinated with Agent 1 (contracts.py + frozen MD) via shared artifacts and parallel execution. Agent 2 output (resolution engine + strategies) was the foundation used for delegation. All changes additive + tested.

Ready for Wave 2+ (CDIA + full barrel_v2 propagation using the same res_meta pattern). 

— Agent 3 (Phase 4 + Shell/Parser Integration)