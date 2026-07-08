"""C/C++ #include parser (zero-dep, agent-first).

AGENT MAP:
  parse_c_cpp_imports(filepath) → edge list for .c/.h/.cpp/.hpp/.cc/.cxx
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from ._edge import make_edge

_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*([<"])([^>"]+)([>"])',
    re.MULTILINE,
)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


def _resolve_local(current: Path, inc: str) -> Optional[str]:
    parent = current.parent
    cand = (parent / inc).resolve()
    if cand.is_file():
        return str(cand)
    # walk up a few parents for monorepo headers (bounded)
    for _ in range(4):
        parent = parent.parent
        cand = (parent / inc).resolve()
        if cand.is_file():
            return str(cand)
    return None


def parse_c_cpp_imports(filepath: str) -> List[Dict]:
    path = Path(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _strip(text)
    edges: List[Dict] = []

    for m in _INCLUDE_RE.finditer(text):
        quote, inc, _ = m.group(1), m.group(2), m.group(3)
        is_system = quote == "<"
        is_rel = not is_system
        rp = _resolve_local(path, inc) if is_rel else None
        diag = None
        if is_system or not rp:
            diag = {
                "category": "external_or_bare" if is_system else "no_fs_match",
                "reason": f"#include {'<' if is_system else '\"'}{inc}{' >' if is_system else '\"'}",
                "severity": "info",
                "alternatives": [],
                "suggestion_for_agent": (
                    "System includes are expected external."
                    if is_system
                    else "Could not resolve local include on disk (include paths not fully modeled)."
                ),
                "details": {},
            }
        edges.append(
            make_edge(
                module=inc,
                raw_module=inc,
                is_relative=is_rel,
                level=1 if is_rel else 0,
                resolved_path=rp,
                resolution_confidence="high" if rp else ("medium" if is_system else "low"),
                statement_type="include",
                original_statement=m.group(0).strip(),
                diagnostic=diag,
                strategy="c-include" if is_system else "c-include-local",
            )
        )
    return edges
