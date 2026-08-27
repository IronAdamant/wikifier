"""LDSI helpers shared by python and javascript parsers.

Kept out of javascript.py so `import wikifier.parsers.python` does not load
the JS parser, BREE, or CDIA.
"""
from __future__ import annotations

import re
from typing import Any

def _classify_dynamic_import(raw: str) -> tuple[str, str]:
    """
    Classify a captured dynamic import/require argument.
    Returns (dynamic_type, cleaned_raw_module)
    """
    raw = raw.strip()

    # Static string
    if (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        return "static", raw[1:-1]

    # Template literal
    if raw.startswith("`") and raw.endswith("`"):
        return "template_literal", raw[1:-1]

    # Simple identifier (most common variable case)
    if re.match(r'^[a-zA-Z_$][\w$]*$', raw):
        return "expression", raw

    # More complex expression (function call, concatenation, ternary, or, member, index etc.)
    if any(op in raw for op in ['(', ')', '+', '?', ':', '.', '[', ']', '|', '||', '??']):
        return "expression", raw

    return "unknown", raw


def _analyze_dynamic_specifier(arg_text: str) -> dict[str, Any]:
    """
    LDSI Layer 2 (enhanced classification) + foundation for Layer 3.

    Analyzes a (possibly complex) argument expression for a dynamic import/require
    or import.meta.resolve. Returns richer info than the basic _classify_dynamic_import:
      - dynamic_type (delegates to classifier)
      - dynamic_complexity: "simple" | "moderate" | "high" | "opaque"
      - analysis_notes: list of detected traits (for metadata + future registry)
      - cleaned: the cleaned raw_module

    Used to populate "dynamic_complexity" and seed "analysis_methods".
    Pure, fast, zero-dep. Over- and under-estimation OK because confidence stays low
    for all non-static dynamics.
    """
    text = (arg_text or "").strip()
    dyn_type, cleaned = _classify_dynamic_import(text)

    complexity = "simple"
    notes: list[str] = []

    if not text:
        complexity = "opaque"
        notes.append("empty")
        return {"dynamic_type": dyn_type, "dynamic_complexity": complexity, "analysis_notes": notes, "cleaned": cleaned}

    # Cheap feature detection (no AST)
    has_ternary = "?" in text and ":" in text
    has_or_default = "||" in text or "??" in text
    has_concat = "+" in text
    has_call = bool(re.search(r"\w\s*\(", text))  # looks like fn call
    has_member = "." in text
    has_brackets = "[" in text
    op_density = sum(text.count(c) for c in "?:+.|[]()") + text.count("||") + text.count("??")
    is_simple_ident = bool(re.match(r"^[a-zA-Z_$][\w$]*$", text))

    if is_simple_ident:
        complexity = "simple"
        notes.append("simple_variable")
    elif has_ternary or has_or_default:
        complexity = "moderate"
        if has_ternary:
            notes.append("contains_ternary")
        if has_or_default:
            notes.append("contains_or_default")
    elif has_concat or has_call or has_member or has_brackets:
        complexity = "moderate"

    if has_call or op_density >= 5:
        complexity = "high"
        if has_call:
            notes.append("contains_call")
    if op_density >= 8 or len(text) > 120 or text.count(",") >= 5:
        complexity = "opaque"
        notes.append("high_complexity_or_long")

    if dyn_type == "unknown":
        complexity = "opaque"
        notes.append("unknown_shape")

    return {
        "dynamic_type": dyn_type,
        "dynamic_complexity": complexity,
        "analysis_notes": notes,
        "cleaned": cleaned,
    }


def _extract_balanced_argument(content: str, call_start: int) -> str | None:
    """
    Robust extractor for the argument text of require(...), import(...), etc.

    Starts searching from call_start (position of the keyword in source), finds
    the opening '(', then walks with paren-depth + string-state tracking to
    return the *full* inner argument text even when it contains nested calls,
    parentheses inside strings, or complex expressions.

    This directly solves the core regex limitation ( [^)]+? stops at first inner ) ).

    Respects " ' ` strings (basic escape handling). Sufficient for real-world
    creative dynamic imports without a full JS parser.
    """
    # Locate the first '(' after the call keyword
    paren_pos = content.find('(', call_start)
    if paren_pos == -1:
        return None

    i = paren_pos + 1
    depth = 1
    chars: list[str] = []
    in_string = None  # one of ' " `
    escape = False
    # Simple template ${} awareness is not deeply tracked (we want the whole expr anyway)

    while i < len(content) and depth > 0:
        ch = content[i]
        if escape:
            chars.append(ch)
            escape = False
            i += 1
            continue
        if ch == '\\':
            escape = True
            chars.append(ch)
            i += 1
            continue
        if in_string is not None:
            chars.append(ch)
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"', '`'):
            in_string = ch
            chars.append(ch)
            i += 1
            continue
        if ch == '(':
            depth += 1
            chars.append(ch)
        elif ch == ')':
            depth -= 1
            if depth > 0:
                chars.append(ch)
            # else: this is the closing one; do not append
        else:
            chars.append(ch)
        i += 1

    if depth == 0:
        return ''.join(chars).strip()
    return None


def _extract_candidate_literals(arg_text: str) -> list[dict[str, Any]]:
    """
    Harvest statically recognizable string literals (and template segments)
    from a (possibly complex/dynamic) import/require argument expression.

    This is the key mechanism for recovering *possible* module targets from
    creative patterns such as:
      - require(cond ? "./a" : "./b")
      - require( foo || "default" )
      - require( "./p" + "/suf" )
      - require( path.join("dir", name) )
      - require( `./${x}/mod` )  (static parts + template marker)

    Returns list of unique candidates:
      [{"raw": "...", "type": "static"|"template_part"|"template_expr", "context": "..."}]

    Used to populate "dynamic_candidates" so that dependency edges are not
    completely lost for runtime-computed imports. Confidence for candidates
    is always low/speculative; primary entry remains the expr for traceability.

    Pure-Python, no deps, fast. Deduplicates while preserving first-seen order.
    """
    if not arg_text:
        return []

    candidates: list[dict[str, Any]] = []

    # Double-quoted strings (basic, no full unicode escape needed for paths)
    for m in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', arg_text):
        val = m.group(1)
        candidates.append({"raw": val, "type": "static", "context": "double_quoted"})

    # Single-quoted
    for m in re.finditer(r"'([^'\\]*(?:\\.[^'\\]*)*)'", arg_text):
        val = m.group(1)
        candidates.append({"raw": val, "type": "static", "context": "single_quoted"})

    # Backtick templates (whole + static segments around ${...})
    for m in re.finditer(r'`([^`]*)`', arg_text):
        tcontent = m.group(1)
        if "${" in tcontent:
            candidates.append({
                "raw": tcontent,
                "type": "template_expr",
                "context": "template_literal_with_expr"
            })
            # Crude static segments (prefixes/suffixes between interpolations)
            parts = re.split(r"\$\{[^}]*\}", tcontent)
            for p in parts:
                p = p.strip()
                if p:
                    candidates.append({
                        "raw": p,
                        "type": "template_part",
                        "context": "template_static_segment"
                    })
        else:
            candidates.append({
                "raw": tcontent,
                "type": "static",
                "context": "template_literal"
            })

    # Deduplicate by raw value, keep first occurrence
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        if c["raw"] not in seen:
            seen.add(c["raw"])
            unique.append(c)
    return unique

DYNAMIC_SPECIFIER_REGISTRY: list[dict[str, Any]] = [
    # Phase 1: seed with a few always-on creative handlers (additive, safe, zero-dep).
    # These complement the new CDIA detectors by also harvesting literal candidates from call/map/tagged exprs.
    {"name": "call_produced_or_registry",
     "detect": lambda t: bool(re.search(r'\b(get\w*Path|resolve\w*Path|registry|modMap|create\w*Path|pathFor)\s*[\(\[]', t or "", re.I)),
     "handler": lambda t, ctx: {
         "extra_candidates": _extract_candidate_literals(t or ""),
         "tags": ["call_produced_path", "registry_map"],
         "notes": ["registry_hit"]
     }},
    {"name": "tagged_template_creative",
     "detect": lambda t: bool(re.search(r'\b\w+\s*`[^`]*\$\{', t or "")) or ("`" in (t or "") and re.search(r'\w+`', t or "")),
     "handler": lambda t, ctx: {
         "extra_candidates": _extract_candidate_literals(t or ""),
         "tags": ["tagged_template"],
         "notes": ["tagged_template_hit"]
     }},
    # Richer Phase 2 seeds (per creative_dynamic wave): python importlib parity + stronger map/dict lookups
    # (activates for both JS and Python dynamic exprs when registry invoked from dataflow/expr paths)
    {"name": "python_importlib_creative",
     "detect": lambda t: bool(re.search(r'(import_module|__import__|importlib\.|pkgutil)', t or "", re.I)),
     "handler": lambda t, ctx: {
         "extra_candidates": _extract_candidate_literals(t or ""),
         "tags": ["call_produced_path", "registry_map"],
         "notes": ["python_dynamic", "importlib_hit"]
     }},
    {"name": "dict_map_lookup_registry",
     "detect": lambda t: bool(re.search(r'[\w\.\]]+\s*[\.\[]\s*[\'\"][^\'\"]+[\'\"]\s*\]|\.get\s*\(\s*[\'\"][^\'\"]+', t or "", re.I)),
     "handler": lambda t, ctx: {
         "extra_candidates": _extract_candidate_literals(t or ""),
         "tags": ["registry_map", "map_lookup"],
         "notes": ["dict_lookup_hit"]
     }},
]

def _apply_dynamic_registry(arg_text: str, ctx: dict | None = None) -> dict[str, Any]:
    """Layer 4 stub. Extend REGISTRY to activate. Safe and cheap."""
    ctx = ctx or {}
    out = {"extra_candidates": [], "tags": [], "notes": []}
    for e in DYNAMIC_SPECIFIER_REGISTRY:
        try:
            if e.get("detect") and e["detect"](arg_text or ""):
                h = e.get("handler")
                if h:
                    c = h(arg_text or "", ctx) or {}
                    for k in out:
                        out[k].extend(c.get(k) or [])
        except Exception:
            pass
    return out
