"""
Wiki-vs-code verification: what makes 🟢 Green mean something.

``mark_green`` records the file's public symbols next to the source hash. On
the next ``mark_green`` the symbols are compared with that baseline:

- new public symbols must be mentioned in the wiki;
- removed symbols must no longer be referenced in the wiki (in backticks);
- if the public surface changed, the wiki file itself must have changed.

A change that leaves the public surface alone (a bug fix inside a function)
passes without touching the wiki. Languages without a symbol extractor are
``unchecked``; files without a wiki are ``no_wiki`` (map-first: allowed, but
counted separately so Green-without-wiki is visible).

Pure functions + one read of the source and wiki; no locks, no writes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .wikis import _compute_wiki_content_hash, _find_existing_wiki_file

class WikiVerificationError(Exception):
    """mark_green refused: the wiki does not reflect the code's public surface."""

    def __init__(self, rel: str, check: Dict[str, Any]):
        self.rel = rel
        self.check = check
        issues = "; ".join(i["message"] for i in check.get("issues", []))
        super().__init__(f"wiki for {rel} does not match the code: {issues}")


VERIFIED = "verified"
NO_WIKI = "no_wiki"
UNCHECKED = "unchecked"
FORCED = "forced"

_JS_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"})
_JS_DECL = re.compile(
    r"\bexport\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function\s*\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)"
)
_JS_LIST = re.compile(r"\bexport\s+(?:type\s+)?\{([^}]*)\}(?!\s*from)")
_JS_LIST_FROM = re.compile(r"\bexport\s+(?:type\s+)?\{([^}]*)\}\s*from\b")


def _python_symbols(text: str) -> Optional[List[str]]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:  # an explicit __all__ is the module's own answer
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                names = [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                return sorted(set(names))
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
    return sorted(names)


def _js_symbols(text: str) -> List[str]:
    from ..parsers.javascript import _in_spans, _lex_mask

    masked, strings = _lex_mask(text)
    names = {m.group(1) for m in _JS_DECL.finditer(masked) if not _in_spans(strings, m.start())}
    for pattern in (_JS_LIST, _JS_LIST_FROM):
        for m in pattern.finditer(masked):
            if _in_spans(strings, m.start()):
                continue
            for spec in m.group(1).split(","):
                spec = spec.strip()
                if not spec:
                    continue
                exported = spec.split(" as ")[-1].strip().replace("type ", "")
                if re.match(r"^[A-Za-z_$][\w$]*$", exported) and exported != "default":
                    names.add(exported)
    return sorted(names)


def public_symbols(path: Path) -> Optional[List[str]]:
    """Public top-level names of a source file, or None if the language is unsupported.

    Python: ``__all__`` when present, else top-level functions/classes without a
    leading underscore. JS/TS: exported declarations and export lists.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".py", ".pyi"} | _JS_SUFFIXES:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return _python_symbols(text) if suffix in {".py", ".pyi"} else _js_symbols(text)


def _mentioned(name: str, text: str) -> bool:
    return re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", text) is not None


def _backticked(name: str, text: str) -> bool:
    """``name`` appears inside an inline code span (the way wikis reference symbols)."""
    return re.search(r"`[^`\n]*(?<![\w$])" + re.escape(name) + r"(?![\w$])[^`\n]*`", text) is not None


def _split(stored: Any) -> Optional[Set[str]]:
    if not isinstance(stored, str):
        return None
    return {s for s in stored.split() if s}


def verify_wiki(root: Path, rel: str, entry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Check ``rel``'s wiki against its code and the last Green baseline in ``entry``.

    Returns ``ok`` plus ``verification`` (verified | no_wiki | unchecked),
    ``issues`` (blocking), ``warnings`` (non-blocking), ``symbols`` and
    ``coverage`` (share of public symbols the wiki mentions).
    """
    root = Path(root)
    entry = entry or {}
    source = root / rel
    symbols = public_symbols(source)
    out: Dict[str, Any] = {
        "file": rel, "ok": True, "issues": [], "warnings": [],
        "symbols": symbols, "coverage": None, "wiki_file": None,
    }
    wiki = _find_existing_wiki_file(root, rel)
    if wiki is None:
        out["verification"] = NO_WIKI
        return out
    try:
        out["wiki_file"] = wiki.relative_to(root).as_posix()
    except ValueError:
        out["wiki_file"] = str(wiki)
    if symbols is None:
        out["verification"] = UNCHECKED
        return out
    text = wiki.read_text(encoding="utf-8", errors="replace")
    current = set(symbols)
    mentioned = {s for s in current if _mentioned(s, text)}
    out["coverage"] = round(len(mentioned) / len(current), 2) if current else 1.0

    previous = _split(entry.get("public_symbols"))
    if previous is None:
        # First verification for this file: no baseline to diff against.
        missing = sorted(current - mentioned)
        if missing:
            out["warnings"].append({"code": "undocumented_symbols", "symbols": missing[:20],
                                    "message": f"{len(missing)} public symbol(s) not mentioned in the wiki"})
        out["verification"] = VERIFIED
        return out

    added, removed = sorted(current - previous), sorted(previous - current)
    undocumented = [s for s in added if s not in mentioned]
    if undocumented:
        out["issues"].append({"code": "undocumented_new_symbols", "symbols": undocumented,
                              "message": "new public symbol(s) not mentioned in the wiki: " + ", ".join(undocumented)})
    stale = [s for s in removed if _backticked(s, text)]
    if stale:
        out["issues"].append({"code": "wiki_mentions_removed_symbols", "symbols": stale,
                              "message": "wiki still references removed symbol(s): " + ", ".join(stale)})
    wiki_unchanged = entry.get("wiki_content_hash") and entry.get("wiki_content_hash") == _compute_wiki_content_hash(wiki)
    if (added or removed) and wiki_unchanged:
        out["issues"].append({"code": "wiki_not_updated_for_api_change", "symbols": added + removed,
                              "message": "public surface changed (" + ", ".join(["+" + s for s in added] + ["-" + s for s in removed])
                              + ") but the wiki file is unchanged since the last mark-green"})
    other_missing = sorted(current - mentioned - set(added))
    if other_missing:
        out["warnings"].append({"code": "undocumented_symbols", "symbols": other_missing[:20],
                                "message": f"{len(other_missing)} older public symbol(s) not mentioned in the wiki"})
    out["ok"] = not out["issues"]
    out["verification"] = VERIFIED
    return out


def verify_wikis(root: Path, directory: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    """Audit every Green file with a wiki against its last baseline (read-only).

    Returns counts by ``verification`` for Green rows, the files whose wiki no
    longer matches the code (``failing``, bounded by ``limit``) and the average
    symbol coverage of wikis.
    """
    from .store import _coerce_root, load_health

    root = _coerce_root(root)
    prefix = directory.rstrip("/") if directory else None
    breakdown = {VERIFIED: 0, NO_WIKI: 0, UNCHECKED: 0, FORCED: 0, "legacy": 0}
    failing: List[Dict[str, Any]] = []
    coverages: List[float] = []
    checked = 0
    for rel, entry in sorted((load_health(root).get("entries") or {}).items()):
        if prefix and not (rel == prefix or rel.startswith(prefix + "/")):
            continue
        if not isinstance(entry, dict) or "🟢" not in str(entry.get("status") or ""):
            continue
        if not (root / rel).is_file():
            continue
        breakdown[entry.get("verification") if entry.get("verification") in breakdown else "legacy"] += 1
        check = verify_wiki(root, rel, entry)
        if check["wiki_file"] is None:
            continue
        checked += 1
        if check["coverage"] is not None:
            coverages.append(check["coverage"])
        if not check["ok"] and len(failing) < limit:
            failing.append({"file": rel, "wiki_file": check["wiki_file"], "issues": check["issues"]})
    return {
        "success": True,
        "checked": checked,
        "failing_count": len(failing),
        "failing": failing,
        "green_breakdown": breakdown,
        "avg_symbol_coverage": round(sum(coverages) / len(coverages), 2) if coverages else None,
        "directory": directory or ".",
    }


def symbols_field(symbols: Optional[List[str]]) -> Optional[str]:
    """Storage form of a symbol list (space-separated; health entries hold strings)."""
    return " ".join(symbols) if symbols is not None else None


__all__ = [
    "FORCED", "NO_WIKI", "UNCHECKED", "VERIFIED", "WikiVerificationError",
    "public_symbols", "symbols_field", "verify_wiki", "verify_wikis",
]
