"""Java import parser (zero-dep, agent-first).

AGENT MAP:
  parse_java_imports(filepath) → edge list for .java import statements
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from ._edge import make_edge

_IMPORT_RE = re.compile(
    r"^\s*import\s+(static\s+)?([\w.]+)(?:\.\*)?\s*;",
    re.MULTILINE,
)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


def parse_java_imports(filepath: str) -> List[Dict]:
    path = Path(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _strip(text)
    edges: List[Dict] = []
    seen = set()

    for m in _IMPORT_RE.finditer(text):
        is_static = bool(m.group(1))
        name = m.group(2).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        is_jdk = name.startswith("java.") or name.startswith("javax.") or name.startswith("jdk.")
        diag = {
            "category": "external_or_bare",
            "reason": f"Java import '{name}'" + (" (static)" if is_static else ""),
            "severity": "info",
            "alternatives": [],
            "suggestion_for_agent": "Package names are symbolic without classpath resolution.",
            "details": {"jdk": is_jdk, "static": is_static},
        }
        edges.append(
            make_edge(
                module=name,
                raw_module=name,
                is_relative=False,
                resolution_confidence="medium",
                statement_type="import_static" if is_static else "import",
                original_statement=m.group(0).strip(),
                diagnostic=diag,
                strategy="java-import",
            )
        )
    return edges
