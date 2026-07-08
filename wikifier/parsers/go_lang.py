"""Go import parser (zero-dep, agent-first).

AGENT MAP:
  parse_go_imports(filepath) → edge list (import / import ())
Module name: go_lang (avoid stdlib `go` clash if any).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from ._edge import make_edge

_IMPORT_SINGLE = re.compile(r'^\s*import\s+(?:(\w+)\s+)?["\']([^"\']+)["\']', re.MULTILINE)
_IMPORT_BLOCK = re.compile(r"^\s*import\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
_BLOCK_LINE = re.compile(r'^\s*(?:(\w+)\s+)?["\']([^"\']+)["\']', re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


def _is_stdlib(path: str) -> bool:
    # Rough: no dot in first path segment → often stdlib (fmt, os, net/http)
    first = path.split("/")[0]
    return "." not in first and not path.startswith(".")


def _edge_for(path: str, alias: Optional[str], stmt: str) -> Dict:
    is_rel = path.startswith("./") or path.startswith("../")
    external = (not is_rel) and (_is_stdlib(path) or "." in path.split("/")[0] or True)
    # Mark non-relative as external_or_bare for ACS noise filter (module paths are rarely on-disk relative)
    diag = None
    if not is_rel:
        diag = {
            "category": "external_or_bare",
            "reason": f"Go import path '{path}' (module path; not relative filesystem).",
            "severity": "info",
            "alternatives": [],
            "suggestion_for_agent": "Relative imports are rare in Go; module paths are expected.",
            "details": {"stdlib_heuristic": _is_stdlib(path)},
        }
    return make_edge(
        module=path,
        raw_module=path,
        is_relative=is_rel,
        level=1 if is_rel else 0,
        resolution_confidence="medium",
        statement_type="import",
        original_statement=stmt.strip(),
        diagnostic=diag,
        strategy="go-import",
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
            edges.append(_edge_for(imp, alias, lm.group(0)))

    for m in _IMPORT_SINGLE.finditer(text):
        alias, imp = m.group(1), m.group(2)
        if imp in seen:
            continue
        seen.add(imp)
        edges.append(_edge_for(imp, alias, m.group(0)))

    return edges
