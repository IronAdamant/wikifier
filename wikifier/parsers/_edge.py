"""Shared edge helpers for language parsers (zero-dep, agent-first)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def make_edge(
    *,
    module: str,
    raw_module: str,
    is_relative: bool = False,
    level: int = 0,
    resolved_path: Optional[str] = None,
    resolution_confidence: str = "medium",
    confidence_score: Optional[float] = None,
    confidence_reasons: Optional[List[str]] = None,
    is_dynamic: bool = False,
    statement_type: str = "import",
    original_statement: str = "",
    diagnostic: Optional[Dict[str, Any]] = None,
    strategy: str = "lang-static",
    imported_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a parser edge dict matching the shared py/js contract (additive fields OK)."""
    conf = resolution_confidence
    if confidence_score is None:
        confidence_score = {"high": 0.9, "medium": 0.6, "low": 0.4, "unresolved": 0.2}.get(conf, 0.5)
    reasons = list(confidence_reasons or [f"base:{conf}"])
    if not resolved_path and "no_resolved_path" not in reasons:
        reasons.append("no_resolved_path")
    expl = f"Base {conf} ({confidence_score:.2f})."
    if not resolved_path:
        expl += " unresolved/partial target."
    if diagnostic and diagnostic.get("category") == "external_or_bare":
        expl += " External/stdlib-style include."
    expl += " Recommendation: Use project-relative edges for automation trust; externals are expected noise."

    edge: Dict[str, Any] = {
        "module": module,
        "raw_module": raw_module,
        "is_relative": is_relative,
        "level": level,
        "alias": None,
        "imported_names": imported_names or [],
        "original_statement": original_statement or raw_module,
        "statement_type": statement_type,
        "resolved_path": resolved_path,
        "resolved": resolved_path or module,
        "resolution_confidence": conf,
        "confidence": conf,
        "confidence_score": float(confidence_score),
        "confidence_reasons": reasons,
        "confidence_explanation": expl,
        "is_dynamic": is_dynamic,
        "dynamic_type": "static" if not is_dynamic else "expression",
        "is_conditional": False,
        "via_barrel": False,
        "barrel_depth": 0,
        "resolution_metadata": {
            "strategy": strategy,
            "package_hierarchy_walk": False,
            "target_on_disk": bool(resolved_path),
            "relative_level": level,
        },
        "parser": strategy.split("-")[0] if strategy else "unknown",
        "strategy": strategy,
    }
    if diagnostic:
        edge["diagnostic"] = diagnostic
    return edge
