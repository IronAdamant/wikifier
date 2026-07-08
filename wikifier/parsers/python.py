"""
Wikifier Python Import Parser (M2-02)

Purpose:
This module provides a lightweight, zero-dependency parser for extracting
import/dependency information from Python source files.

Design Philosophy (Long-term):
- Optimized for LLM / agent consumption ("agent as librarian").
- Returns rich, structured data to minimize ambiguity.
- Performs best-effort resolution of relative imports.
- Designed to scale from small scripts to large monorepos.
- Easy to extend with new languages (see M2-03 for JavaScript/TypeScript).

Current Capabilities (v0.4):
- Parses all standard Python import styles (single + multi-line).
- Filters out docstrings and __future__ imports.
- Returns detailed metadata for each import.
- Best-effort resolution of relative imports (with graceful fallback).

Known Limitations (v0.4):
- Very complex or heavily commented multi-line imports may occasionally be
  parsed imperfectly.
- Extremely dynamic imports (e.g. importlib.import_module(variable), __import__, alias chains,
  creative call/registry/tagged patterns) are now covered via full LDSI + CDIA + registry parity
  (mirrors JS; includes Layer 3.5 deeper aliases/CFG, creative CDIA detectors, diagnostics).
- Relative import resolution is best-effort and may not always resolve
  correctly in exotic package layouts (namespace packages, editable installs, etc.).
  (M2 Workstream D: static *relative* imports now emit resolved_path + rich diagnostic + per-edge
  provenance/strategy/metadata for parity with JS; bare absolute and some exotic layouts remain
  lower-fidelity by design. See contracts, diagnostics, import_cache surfaces.)

Performance Notes:
- Designed for typical project sizes (hundreds to low thousands of files).
- Regex-based and fast enough for interactive/agent use.
- Not optimized for extremely large monorepos (that can be addressed later if needed).

This parser is intentionally pragmatic — not perfect — but significantly more
useful for agents than naive string-based approaches.
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Any

# Module-level compiled regexes for small repeated speed win on every parse (docstring strip + dynamic import detectors).
# Zero behavior change.
_DOCSTRING_RE1 = re.compile(r'"""[\s\S]*?"""')
_DOCSTRING_RE2 = re.compile(r"'''[\s\S]*?'''")
_DYN_IMPORT_RE = re.compile(r'(?P<call>(?:importlib\.)?import_module)\s*\(', re.MULTILINE)
_DYN_DUNDER_RE = re.compile(r'(?P<call>__import__)\s*\(', re.MULTILINE)

# Diagnostics & Failure Transparency (Limitation #5) - same robust import pattern as JS parser
try:
    from . import diagnostics
except ImportError:
    try:
        from .. import diagnostics
    except ImportError:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        import wikifier.diagnostics as diagnostics

# CDIA + LDSI + registry parity for creative/dynamic imports (mirror of javascript.py Phase 1/3.5 work)
# Strictly additive, zero-dep, graceful fallbacks. Reuses shared extractors/registry/balancer where possible
# so Python gets same creative detector coverage (call_produced, registry_map, etc.) + dataflow + CDIA tags.
try:
    from .cdia import get_cdia_engine
except Exception:
    try:
        from ..cdia import get_cdia_engine
    except Exception:
        get_cdia_engine = None

try:
    from .javascript import (
        _extract_balanced_argument,
        _extract_candidate_literals,
        _apply_dynamic_registry,
        _analyze_dynamic_specifier,
    )
except Exception:
    _extract_balanced_argument = None
    _extract_candidate_literals = None
    _apply_dynamic_registry = None
    _analyze_dynamic_specifier = None


def _resolve_relative_import(
    current_file: Path, 
    raw_module: str, 
    level: int
) -> tuple[str, str, Optional[str]]:
    """
    Best-effort resolution of relative imports. (M2 Resolution Transparency parity)

    Returns (resolved_module, confidence, resolved_path_or_None).
    Now populates resolved_path (actual .py or package __init__.py on disk) for
    relatives when the target exists under the package hierarchy walk. This
    closes the historical asymmetry with javascript.py for intra-project
    relative imports.

    Confidence: "high" only when FS target successfully located (matches JS
    fidelity for relatives); otherwise "medium"/"low" with graceful degradation.
    (ACS callers receive the resolved_path and adjust "no_resolved_path" penalty.)
    Per-edge provenance (strategy + minimal metadata) is attached by callers.
    """
    if level == 0 or not raw_module.startswith('.'):
        return raw_module, "medium", None

    parent = current_file.parent

    package_hierarchy: list[str] = []
    current = parent

    if (parent / "__init__.py").exists() is False:
        pass

    while True:
        if (current / "__init__.py").exists():
            package_hierarchy.append(current.name)
        else:
            break
        if current.parent == current:
            break
        current = current.parent

    package_hierarchy.reverse()

    resolved_parts = package_hierarchy[:]
    for _ in range(level - 1):
        if resolved_parts:
            resolved_parts.pop()
        else:
            break

    cleaned = raw_module.lstrip('.')

    if resolved_parts and cleaned:
        resolved = f"{'.'.join(resolved_parts)}.{cleaned}"
    elif resolved_parts:
        resolved = '.'.join(resolved_parts)
    else:
        resolved = cleaned

    # --- NEW: compute actual FS target for resolved_path fidelity (parity) ---
    resolved_path: Optional[str] = None
    try:
        # Start from the directory implied by the package hierarchy + level
        # Re-walk to find the base dir for the import target (robust to namespace quirks)
        base = current_file.parent
        # pop level-1 parents (same as resolved_parts construction)
        for _ in range(level - 1):
            if base.parent != base:
                base = base.parent
            else:
                break
        # Now append the cleaned dotted path segments as dirs, last as .py or package
        if cleaned:
            segs = [s for s in cleaned.split('.') if s]
            target_dir = base
            for seg in segs[:-1]:
                target_dir = target_dir / seg
            if segs:
                last = segs[-1]
                # Candidate 1: direct module file
                cand_py = target_dir / f"{last}.py"
                if cand_py.exists() and cand_py.is_file():
                    resolved_path = str(cand_py.resolve())
                else:
                    # Candidate 2: package dir with __init__.py
                    cand_init = target_dir / last / "__init__.py"
                    if cand_init.exists() and cand_init.is_file():
                        resolved_path = str(cand_init.resolve())
                    else:
                        # Fallback: if no subsegs, try sibling to current
                        if not segs[1:]:
                            sib = current_file.parent / f"{last}.py"
                            if sib.exists() and sib.is_file():
                                resolved_path = str(sib.resolve())
                            else:
                                sib_init = current_file.parent / last / "__init__.py"
                                if sib_init.exists() and sib_init.is_file():
                                    resolved_path = str(sib_init.resolve())
    except Exception:
        resolved_path = None

    # Fidelity parity: high confidence requires actual FS target (like JS relatives)
    if resolved_path:
        confidence = "high"
    elif package_hierarchy:
        confidence = "medium"
    else:
        confidence = "low"
    return resolved, confidence, resolved_path


# ---------------------------------------------------------------------
# Actionable Confidence System (ACS) — Limitation #2 (Python side)
# Full parity implementation: dynamic/creative/conditional via mirrored LDSI (incl. 3.5) + CDIA + registry + ACS wiring (matches JS).
# ---------------------------------------------------------------------

def _compute_confidence_score_and_reasons(
    base_conf: str,
    *,
    is_dynamic: bool = False,
    dynamic_type: str = "static",
    is_conditional: bool = False,
    barrel_depth: int | None = None,
    via_barrel: bool = False,
    resolved_path: str | None = None,
    # P2 ACS parity + F2: same rich extension points + explanation generation as JS for consistency
    conditional_analysis: dict | None = None,
    dynamic_analysis: dict | None = None,
    resolution_metadata: dict | None = None,
    strategy: str | None = None,
    in_cycle: bool = False,
) -> tuple[float, list[str], str]:
    """
    Thin wrapper delegating to the canonical single-source implementation in
    wikifier.contracts.compute_acs_confidence (R2).

    Guarantees identical output (scores, reasons, explanations) with the
    JavaScript parser. Python CDIA/Resolution signals will flow through
    automatically once richer data is produced by the Python side.

    See contracts.py for the full R2-grade explanation builder and
    prescriptive recommendations.
    """
    from wikifier.contracts import compute_acs_confidence as _canonical_acs

    return _canonical_acs(
        base_conf,
        is_dynamic=is_dynamic,
        dynamic_type=dynamic_type,
        is_conditional=is_conditional,
        barrel_depth=barrel_depth,
        via_barrel=via_barrel,
        resolved_path=resolved_path,
        conditional_analysis=conditional_analysis,
        dynamic_analysis=dynamic_analysis,
        resolution_metadata=resolution_metadata,
        strategy=strategy,
        in_cycle=in_cycle,
    )


def _strip_docstrings(content: str) -> str:
    """
    Remove triple-quoted strings (docstrings) from the content.
    This is a lightweight heuristic to reduce false-positive imports
    that appear inside documentation or multi-line strings.

    Note: This is not perfect (e.g., it doesn't handle escaped quotes inside
    strings well), but it is good enough for v0.4 and keeps us zero-dependency.
    """
    # Remove """...""" and '''...''' (non-greedy, handles both single and double)
    content = _DOCSTRING_RE1.sub('', content)
    content = _DOCSTRING_RE2.sub('', content)
    return content


def _strip_comments(content: str) -> str:
    """Blank out # comments (outside string literals), preserving line structure.

    The dynamic-import scanner matches anywhere in the text (unlike the
    line-anchored static patterns), so a comment like
    `# importlib.import_module() now supported` produced a garbage dynamic
    edge whose raw_module was the comment text — which then leaked into
    library.md as a phantom graph node. Docstrings were already stripped;
    comments were not.
    """
    out_lines = []
    for line in content.split("\n"):
        in_str = None
        cut = None
        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in ("'", '"'):
                in_str = c
            elif c == "#":
                cut = i
                break
            i += 1
        out_lines.append(line if cut is None else line[:cut])
    return "\n".join(out_lines)


def parse_python_imports(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a Python file and return structured import information.

    This function is designed to be agent-friendly. It captures enough
    detail to allow LLMs to reason about dependencies with low ambiguity.

    Returns a list of dictionaries with the following keys:
        - module: Best-effort resolved module name
        - raw_module: Original module string from the source
        - is_relative: Whether this was a relative import
        - level: Number of leading dots (0 for absolute)
        - alias: Alias if 'as' was used
        - imported_names: List of imported names (for 'from' style imports)
        - original_statement: The full original import line(s)
        - statement_type: One of "import", "import_as", "from_import", "from_import_as", "dynamic_import_module", ...
        - resolved_path: Absolute FS path to target .py (or package __init__.py) when successfully resolved for relatives; None otherwise (M2 parity with JS)
        - resolution_confidence: "high" | "medium" | "low" | "unresolved" (legacy string; high now requires FS target for relatives)
        - confidence_score: 0.0–1.0 (ACS Limitation #2)
        - confidence_reasons: list[str] explainers (ACS)
        - confidence_explanation: full prescriptive Recommendation string (R2 ACS)
        - diagnostic: structured failure/low-conf info (category, reason, severity, suggestion_for_agent, details) — now for static relatives too (parity; see diagnostics.py)
        - parser, resolution_strategy, resolution_metadata: per-edge provenance (stored in cache resolved_pairs; enables first-class unresolved/low-conf surfaces)
        - is_dynamic / dynamic_type / expr_raw / dynamic_candidates / analysis_notes / cdia / dynamic_analysis / conditional_analysis: full creative/dynamic parity (LDSI 3.5 + CDIA)
    """
    path = Path(filepath).resolve()
    if not path.exists():
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    # Remove docstrings + comments to avoid matching imports inside
    # documentation (the dynamic scanner matches anywhere in the text).
    content = _strip_docstrings(content)
    content = _strip_comments(content)

    imports: List[Dict[str, Any]] = []

    # === Full LDSI + CDIA + Registry Parity for Extremely Creative/Dynamic Imports (Gap #1) ===
    # Mirrors javascript.py Phase 1 + Layer 3.5 work exactly in spirit (additive, zero-dep):
    # - detect python dynamic sites (import_module, __import__)
    # - balanced expr capture + candidate harvest + python-adapted dataflow (incl. alias chains)
    # - Layer 4 registry invocation (re-uses seeded creative handlers incl. python_importlib + dict)
    # - full CDIA engine call for semantic_tags, creative detectors (TaggedTemplate etc fire on py exprs too), trace
    # - wires dynamic_analysis / cdia / is_dynamic / ACS creative penalties / make_creative diag into output
    # Updates the prior "not detected" limitation; now first-class parity for real creative monorepos.
    dynamic_imports: List[Dict[str, Any]] = []
    if _extract_candidate_literals is not None and _apply_dynamic_registry is not None:
        dyn_patterns = [
            (_DYN_IMPORT_RE, "import_module"),
            (_DYN_DUNDER_RE, "dunder_import"),
        ]
        for pat, ptype in dyn_patterns:
            for match in pat.finditer(content):
                call_start = match.start()
                expr_text = None
                if _extract_balanced_argument is not None:
                    try:
                        expr_text = _extract_balanced_argument(content, call_start)
                    except Exception:
                        expr_text = None
                if not expr_text:
                    # conservative slice fallback
                    expr_text = content[call_start : min(len(content), call_start + 180)]
                # strip outer () if present
                expr_text = expr_text.strip()
                if expr_text.startswith("(") and expr_text.endswith(")"):
                    expr_text = expr_text[1:-1].strip()
                # LDSI Layer 2 via shared analyzer (works for py exprs: ops, calls, idents)
                dyn_type = "expression"
                dyn_complexity = "moderate"
                analysis_notes = ["python_dynamic", "creative_parity"]
                if _analyze_dynamic_specifier is not None:
                    try:
                        an = _analyze_dynamic_specifier(expr_text)
                        dyn_type = an.get("dynamic_type", dyn_type)
                        dyn_complexity = an.get("dynamic_complexity", dyn_complexity)
                        analysis_notes.extend(an.get("analysis_notes", []))
                    except Exception:
                        pass
                expr_raw = expr_text
                dynamic_candidates: List[Dict[str, Any]] = []
                try:
                    dynamic_candidates = _extract_candidate_literals(expr_text) or []
                except Exception:
                    pass
                # python dataflow (mirror of _resolve... incl spirit of 3.5 deeper alias)
                raw_var = expr_text.strip()
                if re.match(r"^[a-zA-Z_]\w*$", raw_var):
                    try:
                        df_win = content[max(0, call_start - 1800):call_start]
                        py_pat = re.compile(
                            r"(?:^|[\n;])\s*([a-zA-Z_]\w*)\s*=\s*([^;\n]{0,250}?)(?:;|$|\n)",
                            re.MULTILINE
                        )
                        ms = list(py_pat.finditer(df_win))
                        rhs = ""
                        for mm in reversed(ms):
                            if mm.group(1) == raw_var:
                                rhs = (mm.group(2) or "").strip()
                                break
                        if rhs:
                            for cc in (_extract_candidate_literals(rhs) or []):
                                dynamic_candidates.append(cc)
                            try:
                                rgh = _apply_dynamic_registry(rhs, {"context": "py_dataflow_3.5", "var": raw_var})
                                for ec in (rgh.get("extra_candidates") or []):
                                    dynamic_candidates.append(ec)
                            except Exception:
                                pass
                            analysis_notes.append("dataflow_var_substitution")
                    except Exception:
                        pass
                # Layer 4 registry on expr (activates richer seeds + creative)
                try:
                    reg_hit = _apply_dynamic_registry(expr_text, {"path": str(path), "context": "python_expr_path"})
                    for ex in (reg_hit.get("extra_candidates") or []):
                        dynamic_candidates.append(ex)
                    for nt in (reg_hit.get("notes") or []):
                        if nt and f"registry:{nt}" not in analysis_notes:
                            analysis_notes.append(f"registry:{nt}")
                except Exception:
                    pass
                # CDIA parity call (produces creative tags/dets for ACS/diag even on py syntax)
                cdia_payload: Dict[str, Any] = {}
                ca = {}
                da = {}
                is_conditional = False
                conditional_context = None
                if get_cdia_engine is not None:
                    try:
                        engine = get_cdia_engine()
                        cdia_payload = engine.analyze_import_site(
                            content,
                            call_start,
                            raw_var if re.match(r"^[a-zA-Z_]\w*$", raw_var) else expr_text[:60],
                            expr_raw=expr_raw,
                            dynamic_type_hint="expression",
                            statement_type=ptype,
                            dynamic_candidates=dynamic_candidates,
                        )
                        ca = cdia_payload.get("conditional_analysis", {}) or {}
                        da = cdia_payload.get("dynamic_analysis", {}) or {}
                        is_conditional = bool(ca.get("is_conditional", False))
                        ctags = ca.get("semantic_tags", [])
                        if "control_flow" in ctags or "if_statement" in ctags:
                            conditional_context = "if"
                        elif any("ternary" in str(x).lower() for x in ctags):
                            conditional_context = "ternary"
                    except Exception:
                        cdia_payload = {"conditional_analysis": {"is_conditional": False, "degraded": True}, "dynamic_analysis": {"dynamic_type": "expression", "degraded": True}}
                        ca = cdia_payload.get("conditional_analysis", {})
                        da = cdia_payload.get("dynamic_analysis", {})
                # build rich dynamic entry (same keys as static + parity extras)
                mod_for_entry = expr_text[:80]
                if dynamic_candidates:
                    c0 = dynamic_candidates[0]
                    if isinstance(c0, dict):
                        c0r = c0.get("raw", "")
                        if c0r and len(c0r) < 60:
                            mod_for_entry = c0r
                try:
                    conf_score, conf_reasons, conf_expl = _compute_confidence_score_and_reasons(
                        "low",
                        is_dynamic=True,
                        dynamic_type=dyn_type,
                        is_conditional=is_conditional,
                        barrel_depth=None,
                        via_barrel=False,
                        resolved_path=None,
                        conditional_analysis=ca,
                        dynamic_analysis=da,
                    )
                except Exception:
                    conf_score, conf_reasons, conf_expl = 0.25, ["dynamic_python"], "Low confidence due to dynamic python import (creative parity)"
                dyn_entry: Dict[str, Any] = {
                    "module": mod_for_entry,
                    "raw_module": expr_text[:200],
                    "is_relative": False,
                    "level": 0,
                    "alias": None,
                    "imported_names": [],
                    "original_statement": (match.group(0) or "")[:300],
                    "statement_type": f"dynamic_{ptype}",
                    "resolution_confidence": "low",
                    "confidence_score": conf_score,
                    "confidence_reasons": conf_reasons,
                    "confidence_explanation": conf_expl,
                    "is_dynamic": True,
                    "dynamic_type": dyn_type,
                    "dynamic_complexity": dyn_complexity,
                    "expr_raw": expr_raw,
                    "dynamic_candidates": dynamic_candidates,
                    "analysis_methods": ["balanced_capture", "literal_harvest", "python_dataflow_3.5", "registry", "cdia"],
                    "analysis_notes": analysis_notes,
                    "cdia": cdia_payload,
                    "conditional_analysis": ca,
                    "dynamic_analysis": da,
                    "is_conditional": is_conditional,
                    "conditional_context": conditional_context,
                    "diagnostic": None,
                    # Per-edge provenance for full parser parity (dynamic creative paths now also carry it)
                    "parser": "python",
                    "resolution_strategy": "python-dynamic-creative",
                    "resolution_metadata": {
                        "strategy": "python-dynamic-creative",
                        "via_ldsi_cdia_registry": True,
                        "target_on_disk": False,  # dynamics remain speculative
                    },
                }
                # creative diag dispatch parity (uses same factory as JS)
                try:
                    ctags = da.get("semantic_tags", []) if da else []
                    cdets = da.get("detectors_fired", []) if da else []
                    creative_tags = [t for t in ctags if t in ("tagged_template", "registry_map", "multi_condition_feature_wrapper", "call_produced_path")]
                    is_creative = bool(creative_tags) or any(d in ("TaggedTemplateDetector", "RegistryMapDetector", "MultiConditionFeatureWrapperDetector", "CallProducedPathDetector") for d in cdets)
                    if is_creative and hasattr(diagnostics, "make_creative_dynamic_diagnostic"):
                        dyn_entry["diagnostic"] = diagnostics.make_creative_dynamic_diagnostic(
                            expr=expr_raw or expr_text,
                            creative_tags=creative_tags or ctags,
                            detectors_fired=cdets,
                        )
                except Exception:
                    pass
                dynamic_imports.append(dyn_entry)

    # --- Main Parsing Flow ---
    # 1. Strip docstrings (to avoid false positives)
    # 2. Run regex patterns to find import statements (+ dynamic creative via LDSI/CDIA above)
    # 3. Post-process each match into a rich structured dictionary
    # 4. Filter out non-real dependencies (__future__)
    # 5. Merge dynamic parity entries + Return the list

    # --- Regex Patterns ---
    # These patterns are intentionally lightweight (regex + heuristics) to stay
    # zero-dependency while still being effective on real-world code.
    #
    # How to add a new language (for future maintainers / agents):
    # 1. Create a new file in wikifier/parsers/ (e.g. javascript.py)
    # 2. Implement a function with the same return structure as parse_python_imports()
    # 3. Wire it into cmd_update_maps() when needed.
    #
    # This design keeps the system modular and easy to extend.

    # Pattern 1: "import module" or "import module as alias"
    # Matches absolute and relative module imports at the start of a line.
    import_pattern = re.compile(
        r'^\s*import\s+([a-zA-Z0-9_.]+)(?:\s+as\s+([a-zA-Z0-9_]+))?',
        re.MULTILINE
    )

    # Pattern 2: "from module import ..." (supports multi-line with parentheses)
    # This version is more robust against common formatting (including black/isort output).
    from_import_pattern = re.compile(
        r'^\s*from\s+([.a-zA-Z0-9_]+)\s+import\s+'
        r'((?:\([\s\S]*?\)|[^#;\n]+))',
        re.MULTILINE
    )

    # Process "import ..." statements
    for match in import_pattern.finditer(content):
        raw_module = match.group(1).strip()
        alias = match.group(2)
        original = match.group(0).strip()

        is_relative = raw_module.startswith('.')
        _dots = re.match(r'\.+', raw_module) if is_relative else None
        level = len(_dots.group()) if _dots else 0

        resolved_module, confidence, resolved_path = _resolve_relative_import(path, raw_module, level)

        # ACS (Lim #2 + F2) Python parity - now passes real resolved_path when available
        conf_score, conf_reasons, conf_explanation = _compute_confidence_score_and_reasons(
            confidence,
            is_dynamic=False,
            is_conditional=False,
            barrel_depth=None,
            via_barrel=False,
            resolved_path=resolved_path,
        )

        # Rich diagnostic for low/unresolved static cases (parity with JS _make_diag_for_js + diagnostics layer)
        # Makes failure modes (missing target, relative misresolve) visible + actionable.
        diag = None
        if (confidence or "").lower() in ("low", "unresolved") or not resolved_path:
            try:
                if hasattr(diagnostics, "make_diagnostic"):
                    cat = "relative_misresolve" if is_relative and level > 0 else ("no_fs_match" if is_relative else "external_or_bare")
                    reason = (
                        f"Python relative import '{raw_module}' resolved to '{resolved_module}' "
                        "but no on-disk .py / __init__.py target located via package hierarchy."
                        if is_relative else
                        f"Absolute/bare Python import '{raw_module}' (stdlib, third-party, or intra-project bare module not resolvable by static walk)."
                    )
                    diag = diagnostics.make_diagnostic(
                        cat,
                        reason[:280],
                        severity="info" if not is_relative else "warn",
                        suggestion_for_agent=(
                            "For project-internal deps, use explicit relative imports (from .foo import) with matching files on disk. "
                            "Externals/bare are expected; safe to ignore or pin via comments for graph completeness."
                        ),
                        details={"raw_module": raw_module, "level": level, "resolved_module": resolved_module, "has_resolved_path": bool(resolved_path)},
                    )
            except Exception:
                diag = None

        # Per-edge provenance (closes asymmetry; flows to resolved_pairs/cache/MCP/ACS/CIABRE automatically via update_file_data RICH preservation)
        provenance = {
            "parser": "python",
            "resolution_strategy": "python-relative-hierarchy" if is_relative else "python-bare-or-external",
            "resolution_metadata": {
                "strategy": "python-relative-hierarchy" if is_relative else "python-bare-or-external",
                "package_hierarchy_walk": is_relative,
                "target_on_disk": bool(resolved_path),
                "relative_level": level,
            },
        }

        imports.append({
            "module": resolved_module,
            "raw_module": raw_module,
            "is_relative": is_relative,
            "level": level,
            "alias": alias,
            "imported_names": [],
            "original_statement": original,
            "statement_type": "import_as" if alias else "import",
            "resolved_path": resolved_path,
            "resolution_confidence": confidence,
            "confidence_score": conf_score,
            "confidence_reasons": conf_reasons,
            "confidence_explanation": conf_explanation,
            "diagnostic": diag,
            **provenance,
        })

    # Process "from ... import ..." statements
    for match in from_import_pattern.finditer(content):
        raw_module = match.group(1).strip()
        import_part = match.group(2).strip()
        original = match.group(0).strip()

        is_relative = raw_module.startswith('.')
        _dots = re.match(r'\.+', raw_module) if is_relative else None
        level = len(_dots.group()) if _dots else 0

        resolved_module, confidence, resolved_path = _resolve_relative_import(path, raw_module, level)

        # ACS (Lim #2 + F2) Python parity - now passes real resolved_path when available
        conf_score, conf_reasons, conf_explanation = _compute_confidence_score_and_reasons(
            confidence,
            is_dynamic=False,
            is_conditional=False,
            barrel_depth=None,
            via_barrel=False,
            resolved_path=resolved_path,
        )

        # Clean up parentheses and inline comments from multi-line imports
        # Remove comments (both after items and at end of lines inside parentheses)
        import_part = re.sub(r'#.*', '', import_part)
        import_part = import_part.replace('(', '').replace(')', '').strip()

        # Handle "import X, Y, Z" or "import X as A, Y as B"
        imported_names = []
        alias = None
        statement_type = "from_import"

        parts = [p.strip() for p in import_part.split(',') if p.strip()]

        for part in parts:
            if ' as ' in part:
                name, alias_name = [x.strip() for x in part.split(' as ', 1)]
                imported_names.append(name)
                alias = alias_name
                statement_type = "from_import_as"
            elif part == '*':
                imported_names.append('*')
                statement_type = "from_import"
            else:
                imported_names.append(part)

        # Rich diagnostic for low/unresolved static cases (parity)
        diag = None
        if (confidence or "").lower() in ("low", "unresolved") or not resolved_path:
            try:
                if hasattr(diagnostics, "make_diagnostic"):
                    cat = "relative_misresolve" if is_relative and level > 0 else ("no_fs_match" if is_relative else "external_or_bare")
                    reason = (
                        f"Python relative import '{raw_module}' resolved to '{resolved_module}' "
                        "but no on-disk .py / __init__.py target located via package hierarchy."
                        if is_relative else
                        f"Absolute/bare Python import '{raw_module}' (stdlib, third-party, or intra-project bare module not resolvable by static walk)."
                    )
                    diag = diagnostics.make_diagnostic(
                        cat,
                        reason[:280],
                        severity="info" if not is_relative else "warn",
                        suggestion_for_agent=(
                            "For project-internal deps, use explicit relative imports (from .foo import) with matching files on disk. "
                            "Externals/bare are expected; safe to ignore or pin via comments for graph completeness."
                        ),
                        details={"raw_module": raw_module, "level": level, "resolved_module": resolved_module, "has_resolved_path": bool(resolved_path)},
                    )
            except Exception:
                diag = None

        # Per-edge provenance (additive, stored in cache resolved_pairs)
        provenance = {
            "parser": "python",
            "resolution_strategy": "python-relative-hierarchy" if is_relative else "python-bare-or-external",
            "resolution_metadata": {
                "strategy": "python-relative-hierarchy" if is_relative else "python-bare-or-external",
                "package_hierarchy_walk": True,  # from the walk in resolver
                "target_on_disk": bool(resolved_path),
                "relative_level": level,
            },
        }

        imports.append({
            "module": resolved_module,
            "raw_module": raw_module,
            "is_relative": is_relative,
            "level": level,
            "alias": alias,
            "imported_names": imported_names,
            "original_statement": original,
            "statement_type": statement_type,
            "resolved_path": resolved_path,
            "resolution_confidence": confidence,
            "confidence_score": conf_score,
            "confidence_reasons": conf_reasons,
            "confidence_explanation": conf_explanation,
            "diagnostic": diag,
            **provenance,
        })

    # Final cleanup: remove __future__ imports (they are not real module dependencies)
    imports = [imp for imp in imports if not imp["raw_module"].startswith("__future__")]

    # Merge creative/dynamic parity entries (LDSI 3.5 + CDIA + registry + creative signals)
    # These are orthogonal to static import/from patterns so simple extend is safe.
    imports.extend(dynamic_imports)

    # Note: Dynamic imports via importlib.import_module() / __import__ now fully supported
    # with LDSI+CDIA+registry parity (Layer 3.5 alias CFG, creative detectors, ACS wiring).
    # See creative_dynamic long-term strategy + Phase 1/2 tracker entries.

    return imports


# ------------------------------------------------------------------
# Quick Testing / Validation Helpers (for development and agents)
# ------------------------------------------------------------------

def parse_python_imports_from_string(content: str, fake_path: str = "dummy.py") -> List[Dict[str, Any]]:
    """
    Parse Python code from a string (useful for testing).
    Uses a fake file path for relative import resolution.
    """
    import tempfile
    import os

    # Write to a temporary file so relative import resolution has a path to work with
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        return parse_python_imports(tmp_path)
    finally:
        os.unlink(tmp_path)


# For quick manual testing and validation
