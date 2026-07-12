"""Go import parser (zero-dep, agent-first).

AGENT MAP:
  parse_go_imports(filepath) → edge list (import / import ())
  Tiered resolve: relative imports + same-module paths via go.mod (when present)

Module name: go_lang (avoid stdlib `go` clash if any).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ._edge import make_edge

_IMPORT_SINGLE = re.compile(r'^\s*import\s+(?:(\w+)\s+)?["\']([^"\']+)["\']', re.MULTILINE)
_IMPORT_BLOCK = re.compile(r"^\s*import\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
_BLOCK_LINE = re.compile(r'^\s*(?:(\w+)\s+)?["\']([^"\']+)["\']', re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)
_MODULE_RE = re.compile(r"^\s*module\s+(\S+)", re.MULTILINE)


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


def _is_stdlib(path: str) -> bool:
    # Rough: no dot in first path segment → often stdlib (fmt, os, net/http)
    first = path.split("/")[0]
    return "." not in first and not path.startswith(".")


@lru_cache(maxsize=64)
def _find_go_mod(start_dir: str) -> Optional[Tuple[str, str]]:
    """Walk up for go.mod. Returns (module_path, module_root_dir) or None."""
    d = Path(start_dir)
    for _ in range(16):
        gm = d / "go.mod"
        if gm.is_file():
            try:
                text = gm.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return None
            m = _MODULE_RE.search(text)
            if m:
                return (m.group(1).strip(), str(d.resolve()))
            return None
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def _pkg_dir_has_go(pkg: Path) -> bool:
    try:
        if not pkg.is_dir():
            return False
        for p in pkg.iterdir():
            if p.is_file() and p.suffix == ".go" and not p.name.endswith("_test.go"):
                return True
            if p.is_file() and p.suffix == ".go":
                return True
    except Exception:
        return False
    return False


def _resolve_go_import(current: Path, imp: str) -> Optional[str]:
    """Best-effort resolve relative or same-module import to a package directory."""
    if imp.startswith("./") or imp.startswith("../"):
        base = (current.parent / imp).resolve()
        if _pkg_dir_has_go(base):
            return str(base)
        if base.is_file() and base.suffix == ".go":
            return str(base)
        return None
    found = _find_go_mod(str(current.parent))
    if not found:
        return None
    module_path, module_root = found
    if imp == module_path or imp.startswith(module_path + "/"):
        rest = imp[len(module_path) :].lstrip("/")
        pkg = Path(module_root) / rest if rest else Path(module_root)
        if _pkg_dir_has_go(pkg):
            return str(pkg.resolve())
    return None


def _edge_for(current: Path, path: str, alias: Optional[str], stmt: str) -> Dict:
    is_rel = path.startswith("./") or path.startswith("../")
    resolved = _resolve_go_import(current, path)
    found_mod = _find_go_mod(str(current.parent))
    same_module = bool(
        found_mod
        and (
            path == found_mod[0]
            or path.startswith(found_mod[0] + "/")
        )
    )
    # External / stdlib when not relative and not resolved same-module
    external = (not is_rel) and (not resolved) and (not same_module or not resolved)
    if resolved:
        external = False
    diag = None
    if external and not is_rel:
        diag = {
            "category": "external_or_bare",
            "reason": f"Go import path '{path}' (stdlib/third-party module path).",
            "severity": "info",
            "alternatives": [],
            "suggestion_for_agent": (
                "Same-module paths resolve when go.mod is present; "
                "stdlib/third-party remain external_or_bare (expected noise)."
            ),
            "details": {"stdlib_heuristic": _is_stdlib(path)},
        }
    conf = "high" if resolved else ("medium" if is_rel or same_module else "medium")
    return make_edge(
        module=path,
        raw_module=path,
        is_relative=is_rel or same_module,
        level=1 if (is_rel or same_module) else 0,
        resolved_path=resolved,
        resolution_confidence=conf if resolved else ("medium" if not external else "medium"),
        statement_type="import",
        original_statement=stmt.strip(),
        diagnostic=diag,
        strategy="go-import" if not resolved else "go-mod-resolve",
        imported_names=[alias] if alias else [],
    )


def parse_go_imports(filepath: str) -> List[Dict]:
    path = Path(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _strip(text)
    edges: List[Dict] = []
    seen = set()

    for m in _IMPORT_BLOCK.finditer(text):
        block = m.group(1)
        for lm in _BLOCK_LINE.finditer(block):
            alias, imp = lm.group(1), lm.group(2)
            if imp in seen:
                continue
            seen.add(imp)
            edges.append(_edge_for(path, imp, alias, lm.group(0)))

    for m in _IMPORT_SINGLE.finditer(text):
        alias, imp = m.group(1), m.group(2)
        if imp in seen:
            continue
        seen.add(imp)
        edges.append(_edge_for(path, imp, alias, m.group(0)))

    return edges
