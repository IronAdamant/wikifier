"""C# using-directive parser (zero-dep, agent-first).

AGENT MAP:
  parse_csharp_imports(filepath) → edge list for .cs using directives
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from ._edge import make_edge

_USING_RE = re.compile(
    r"^\s*using\s+(?:static\s+)?(?:[\w.]+\s*=\s*)?([\w.]+)\s*;",
    re.MULTILINE,
)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


def parse_csharp_imports(filepath: str) -> List[Dict]:
    path = Path(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _strip(text)
    edges: List[Dict] = []
    seen = set()

    for m in _USING_RE.finditer(text):
        ns = m.group(1).strip()
        if not ns or ns in seen:
            continue
        seen.add(ns)
        # Project namespaces often PascalCase multi-part; System.* is framework
        is_framework = ns == "System" or ns.startswith("System.") or ns.startswith("Microsoft.")
        diag = {
            "category": "external_or_bare",
            "reason": f"C# using '{ns}' (namespace; not a filesystem path).",
            "severity": "info",
            "alternatives": [],
            "suggestion_for_agent": "Namespace graph is symbolic; pair with project structure for deeper maps.",
            "details": {"framework": is_framework},
        }
        edges.append(
            make_edge(
                module=ns,
                raw_module=ns,
                is_relative=False,
                resolution_confidence="medium",
                statement_type="using",
                original_statement=m.group(0).strip(),
                diagnostic=diag,
                strategy="csharp-using",
            )
        )
    return edges
