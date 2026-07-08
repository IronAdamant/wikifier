"""Rust import/use parser (zero-dep, agent-first).

AGENT MAP:
  parse_rust_imports(filepath) → edge list (use / mod / extern crate)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from ._edge import make_edge

_USE_RE = re.compile(
    r"^\s*(?:pub\s+)?use\s+((?:crate|super|self|::)?(?:::)?[\w:{}*,\s]+);",
    re.MULTILINE,
)
_MOD_RE = re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;", re.MULTILINE)
_EXTERN_RE = re.compile(r"^\s*extern\s+crate\s+(\w+)\s*;", re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)


def _strip_comments(src: str) -> str:
    src = _COMMENT_BLOCK.sub(" ", src)
    src = _COMMENT_LINE.sub(" ", src)
    return src


def _resolve_mod(current: Path, name: str) -> Optional[str]:
    parent = current.parent
    for cand in (
        parent / f"{name}.rs",
        parent / name / "mod.rs",
        parent / name / "lib.rs",
        parent / name / "main.rs",
    ):
        if cand.is_file():
            return str(cand.resolve())
    return None


def parse_rust_imports(filepath: str) -> List[Dict]:
    path = Path(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _strip_comments(text)
    edges: List[Dict] = []

    for m in _USE_RE.finditer(text):
        raw = m.group(1).strip()
        # Collapse use foo::{a, b} to foo
        base = raw.split("::")[0].replace("{", "").replace("}", "").strip().split(",")[0].strip()
        is_rel = base in ("crate", "super", "self") or raw.startswith("crate::") or raw.startswith("super::")
        conf = "medium" if is_rel else "medium"
        diag = None
        if not is_rel and base not in ("std", "core", "alloc"):
            # external crate name
            diag = {
                "category": "external_or_bare",
                "reason": f"Rust crate/path use '{raw}' (not crate/super/self-local).",
                "severity": "info",
                "alternatives": [],
                "suggestion_for_agent": "Local crate::/super::/mod edges are preferred for graph trust.",
                "details": {},
            }
        if base in ("std", "core", "alloc") or (not is_rel and "::" not in raw and base.isidentifier()):
            if base in ("std", "core", "alloc") or (diag and not is_rel):
                diag = diag or {
                    "category": "external_or_bare",
                    "reason": f"Rust std/external use '{raw}'.",
                    "severity": "info",
                    "alternatives": [],
                    "suggestion_for_agent": "Expected for std/external crates.",
                    "details": {},
                }
        edges.append(
            make_edge(
                module=raw.replace(" ", ""),
                raw_module=raw,
                is_relative=is_rel,
                level=1 if is_rel else 0,
                resolution_confidence=conf,
                statement_type="use",
                original_statement=m.group(0).strip(),
                diagnostic=diag,
                strategy="rust-use",
            )
        )

    for m in _MOD_RE.finditer(text):
        name = m.group(1)
        rp = _resolve_mod(path, name)
        edges.append(
            make_edge(
                module=name,
                raw_module=name,
                is_relative=True,
                level=1,
                resolved_path=rp,
                resolution_confidence="high" if rp else "medium",
                statement_type="mod",
                original_statement=m.group(0).strip(),
                strategy="rust-mod",
            )
        )

    for m in _EXTERN_RE.finditer(text):
        name = m.group(1)
        edges.append(
            make_edge(
                module=name,
                raw_module=name,
                is_relative=False,
                resolution_confidence="medium",
                statement_type="extern_crate",
                original_statement=m.group(0).strip(),
                diagnostic={
                    "category": "external_or_bare",
                    "reason": f"extern crate {name}",
                    "severity": "info",
                    "alternatives": [],
                    "suggestion_for_agent": "External crate.",
                    "details": {},
                },
                strategy="rust-extern",
            )
        )

    return edges
