"""
Diagnostics and Failure Transparency Layer for Wikifier (Limitation #5 / Gap #1).

This module defines the canonical schema, categories, and helpers for
resolution diagnostics. It is the single source of truth for "why" a
dependency resolution produced low/unresolved/partial confidence.

Design goals (per long-term architecture):
- Aggregates-first for monorepo scale (10k+ files).
- Backward compatible (old caches / parsers without diagnostics synthesize "unknown").
- Parser-agnostic: both JS and Python (and future) emit the same shape.
- Usable from shell (via python -c json), cache, MCP, CLI, library.md.
- Bounded detail: full diagnostics only on non-high-confidence entries.

Integration points:
- Parsers (javascript.py, python.py) attach "diagnostic" to low/partial items.
- wikifier.sh pipeline forwards the field through pipe/JSON.
- import_cache.py stores it in resolved_pairs and maintains _resolution_diagnostics aggregate.
- mcp/server.py exposes get_resolution_diagnostics() + optional enrichment on other tools.
- library.md generation consumes aggregates + samples for the dynamic section.

Phased rollout (executed 2026-05-17+):
  Phase 0 (done): Research + plan (this docstring + todos).
  Phase 1 (this file): Schema + helpers (no behavior change).
  Phase 2: Instrument parsers (JS first).
  Phase 3: Propagate + cache aggregates.
  Phase 4: MCP tool + enrichments.
  Phase 5: library.md + CLI "diagnose".
  Phase 6: Scale polish, tests, dogfood.
  Phase 7: Docs, changelog, issue closure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union


class DiagnosticCategory(str, Enum):
    """Stable string enum for machine + human consumption.

    Keep values stable (never rename without migration path).
    New categories can be added over time.
    """
    EXTERNAL = "external"
    DYNAMIC = "dynamic"                    # template literal, expression, unknown dynamic
    CREATIVE_DYNAMIC = "creative_dynamic"  # Phase 1: extremely creative (tagged templates, registry maps, call-produced, multi-cond feature wrappers via LDSI+CDIA)
    CONDITIONAL = "conditional"            # inside if/try/etc or propagated from barrel
    # Phase 5e (66): diagnostics surfaces (via get_resolution_diagnostics) complement A3 summaries (format=summary + ACS/barrel in health/MCP) as first-class for 20k+ (O(k) bounded, per 48/58 richer A3).
    NO_FS_MATCH = "no_fs_match"            # walked FS + exports, no hit
    BARREL_DEPTH_EXCEEDED = "barrel_depth_exceeded"
    BARREL_INVALIDATION = "barrel_invalidation"  # Wave 2: importer marked stale due to barrel leaf/mid change (for health yellow notes + explain via BRC reports)
    UNPARSED_DYNAMIC = "unparsed_dynamic"  # Python importlib etc.
    RELATIVE_MISRESOLVE = "relative_misresolve"
    EXPORTS_UNMATCHED = "exports_unmatched" # package.json exports present but no match
    PARSER_LIMIT = "parser_limit"          # syntax / coverage edge
    PATH_NORMALIZATION = "path_normalization"
    OTHER = "other"
    UNKNOWN = "unknown"                    # legacy cache or unspecified low-conf


Severity = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class Diagnostic:
    """Structured failure / low-confidence explanation.

    All fields are designed for:
    - Direct inclusion in JSON responses (MCP)
    - Truncation-friendly display in library.md tables
    - Agent actionability (suggestion_for_agent)
    """
    category: Union[DiagnosticCategory, str]
    reason: str                                   # <= 200 chars recommended
    severity: Severity = "warn"
    alternatives: List[str] = field(default_factory=list)  # 0-3 near-miss candidates
    suggestion_for_agent: str = ""
    details: Dict[str, Any] = field(default_factory=dict)  # deep debug only; keep small

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        cat = d.get("category")
        if isinstance(cat, DiagnosticCategory):
            d["category"] = cat.value
        elif isinstance(cat, str):
            d["category"] = cat
        else:
            d["category"] = str(cat)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Diagnostic":
        cat = d.get("category", "unknown")
        try:
            cat = DiagnosticCategory(cat)
        except ValueError:
            cat = str(cat)
        return cls(
            category=cat,
            reason=str(d.get("reason", ""))[:300],
            severity=d.get("severity", "warn"),
            alternatives=[str(x) for x in (d.get("alternatives") or [])][:5],
            suggestion_for_agent=str(d.get("suggestion_for_agent", ""))[:300],
            details=dict(d.get("details") or {}),
        )

    def __str__(self) -> str:
        return f"[{self.category}] {self.reason}"


# ---------------------------------------------------------------------------
# Factory helpers (preferred API for parser authors)
# ---------------------------------------------------------------------------

def make_diagnostic(
    category: Union[DiagnosticCategory, str],
    reason: str,
    *,
    severity: Severity = "warn",
    alternatives: Optional[List[str]] = None,
    suggestion_for_agent: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a plain dict (JSON serializable) ready for parser output / cache.

    Use this everywhere instead of hand-rolling dicts so the schema stays in one place.
    """
    if isinstance(category, str):
        try:
            category = DiagnosticCategory(category)
        except ValueError:
            category = DiagnosticCategory.UNKNOWN if category == "unknown" else category
    diag = Diagnostic(
        category=category,
        reason=reason[:300],
        severity=severity,
        alternatives=alternatives or [],
        suggestion_for_agent=suggestion_for_agent[:300],
        details=details or {},
    )
    return diag.to_dict()


def make_unknown_diagnostic(reason: str = "Legacy cache entry or unspecified low-confidence resolution") -> Dict[str, Any]:
    """Synthesize a minimal diagnostic for backward-compat paths."""
    return make_diagnostic(
        DiagnosticCategory.UNKNOWN,
        reason,
        severity="info",
        suggestion_for_agent="Re-run `update_maps --full` to obtain fresh structured diagnostics.",
    )


def make_creative_dynamic_diagnostic(
    *,
    expr: str = "",
    creative_tags: Optional[List[str]] = None,
    detectors_fired: Optional[List[str]] = None,
    severity: Severity = "warn",
    suggestion_for_agent: str = "Creative dynamic pattern detected by CDIA (LDSI coverage). Provide static mapping or treat edge as runtime-only for reliable graphs.",
) -> Dict[str, Any]:
    """Phase 1: dedicated factory for wiring extremely creative CDIA signals into diagnostics.
    Used by JS parser (and future Python parity) when new detectors (TaggedTemplate etc.) fire.
    """
    tags = creative_tags or []
    dets = detectors_fired or []
    reason = "Extremely creative dynamic import pattern"
    if tags:
        reason += f" ({', '.join(tags[:3])})"
    if expr:
        reason += f" expr={expr[:60]}"
    details = {
        "creative_tags": tags,
        "cdia_detectors": dets,
        "expr_raw": expr[:120] if expr else "",
    }
    return make_diagnostic(
        DiagnosticCategory.CREATIVE_DYNAMIC,
        reason[:280],
        severity=severity,
        suggestion_for_agent=suggestion_for_agent[:280],
        details=details,
    )


def is_high_confidence(confidence: Optional[str]) -> bool:
    """True only for values that normally omit diagnostics."""
    return (confidence or "").lower() in ("high", "medium")  # medium may still carry in future


# ---------------------------------------------------------------------------
# Aggregation helpers (used by cache + MCP for monorepo scale)
# ---------------------------------------------------------------------------

def summarize_diagnostics(
    resolved_pairs: List[Dict[str, Any]],
    *,
    max_samples_per_category: int = 5,
    max_total_samples: int = 50,
) -> Dict[str, Any]:
    """Produce an aggregates-first summary suitable for _resolution_diagnostics and MCP.

    Never returns the full per-import list unless asked; always starts with counts + top samples.
    Safe to call on large lists (O(n) with early cutoffs).
    """
    by_category: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []
    low_or_unresolved = 0
    total = len(resolved_pairs)

    for p in resolved_pairs:
        conf = (p.get("confidence") or "").lower()
        diag = p.get("diagnostic")
        if not diag:
            if conf in ("low", "unresolved"):
                diag = make_unknown_diagnostic()
            else:
                continue

        cat = diag.get("category", "unknown") if isinstance(diag, dict) else "unknown"
        by_category[cat] = by_category.get(cat, 0) + 1
        low_or_unresolved += 1

        if len(samples) < max_total_samples:
            # Keep a compact sample record
            sample = {
                "src": p.get("src") or p.get("source") or "?",
                "raw": p.get("raw", ""),
                "resolved": p.get("resolved", ""),
                "confidence": conf,
                "category": cat,
                "reason": (diag.get("reason", "") if isinstance(diag, dict) else "")[:120],
                "suggestion": (diag.get("suggestion_for_agent", "") if isinstance(diag, dict) else "")[:120],
            }
            # Only add if it actually has a diagnostic story
            if sample["reason"] or cat != "unknown":
                samples.append(sample)

    # Sort categories by frequency desc for nice presentation
    sorted_cats = sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "total_imports": total,
        "low_or_unresolved_count": low_or_unresolved,
        "by_category": {k: v for k, v in sorted_cats},
        "top_categories": [k for k, _ in sorted_cats[:5]],
        "samples": samples[:max_total_samples],
        "has_more": low_or_unresolved > len(samples),
    }


def empty_diagnostics_summary() -> Dict[str, Any]:
    return {
        "total_imports": 0,
        "low_or_unresolved_count": 0,
        "by_category": {},
        "top_categories": [],
        "samples": [],
        "has_more": False,
    }


# Convenience for python -c usage from wikifier.sh
def diagnostics_summary_as_json(resolved_pairs_json: str) -> str:
    """Helper for shell: takes JSON array string, returns summary JSON string."""
    try:
        pairs = json.loads(resolved_pairs_json)
        if not isinstance(pairs, list):
            pairs = []
    except Exception:
        pairs = []
    summary = summarize_diagnostics(pairs)
    return json.dumps(summary, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Self-test / smoke
    d = make_diagnostic(
        "dynamic",
        "Template literal require with runtime expression",
        severity="warn",
        alternatives=["./foo.js", "bar"],
        suggestion_for_agent="Static analysis cannot resolve; consider manual mapping or runtime probe.",
        details={"expr": "require(`./${x}`)"},
    )
    print(json.dumps(d, indent=2))
    s = summarize_diagnostics([{"confidence": "low", "raw": "x", "diagnostic": d}])
    print("Summary keys:", list(s.keys()))
    print("OK")
