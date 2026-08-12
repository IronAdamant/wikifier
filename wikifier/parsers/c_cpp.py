"""C/C++ #include parser (zero-dep, agent-first).

AGENT MAP:
  parse_c_cpp_imports(filepath) → edge list for .c/.h/.cpp/.hpp/.cc/.cxx
  Tiered local resolve: same-dir, include/, sibling src/, bounded walk under scope
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

_LOCAL_SUBDIRS = ("include", "inc", "src", "Source", "Headers", "public", "private")


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


def _resolve_local(current: Path, inc: str) -> Optional[str]:
    """Resolve quoted #include to an on-disk header (project-local, bounded)."""
    parent = current.parent
    # 1) same directory / relative path as written
    cand = (parent / inc)
    if cand.is_file():
        return str(cand.resolve())
    # 2) common include/ layout next to file and parents
    d = parent
    for _ in range(6):
        for sub in ("",) + _LOCAL_SUBDIRS:
            base = d / sub if sub else d
            c = base / inc
            if c.is_file():
                return str(c.resolve())
            # basename-only fallback in include/
            c2 = base / Path(inc).name
            if c2.is_file():
                return str(c2.resolve())
        parent_d = d.parent
        if parent_d == d:
            break
        d = parent_d
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
        # Also try angle includes that are actually project headers (optional, scoped)
        if is_system and not rp:
            # only same-dir / include/ — never whole monorepo
            maybe = _resolve_local(path, inc)
            if maybe:
                rp = maybe
                is_rel = True
                is_system = False
        diag = None
        if is_system or not rp:
            open_char = '<' if is_system else '"'
            close_char = '>' if is_system else '"'
            diag = {
                "category": "external_or_bare" if is_system else "no_fs_match",
                "reason": f"#include {open_char}{inc}{close_char}",
                "severity": "info",
                "alternatives": [],
                "suggestion_for_agent": (
                    "System includes are expected external."
                    if is_system
                    else "Could not resolve local include (try include/ next to sources)."
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
                strategy="c-include" if is_system and not rp else "c-include-local",
            )
        )
    return edges
