"""C# using-directive parser (zero-dep, agent-first).

AGENT MAP:
  parse_csharp_imports(filepath) → edge list for .cs using directives
  Tiered: nearest .csproj root + project-namespace path heuristics under that root
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ._edge import make_edge

_USING_RE = re.compile(
    r"^\s*using\s+(?:static\s+)?(?:[\w.]+\s*=\s*)?([\w.]+)\s*;",
    re.MULTILINE,
)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)
_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)
_ROOT_NS_RE = re.compile(
    r"<RootNamespace>\s*([^<]+)\s*</RootNamespace>", re.IGNORECASE
)
_ASM_RE = re.compile(
    r"<AssemblyName>\s*([^<]+)\s*</AssemblyName>", re.IGNORECASE
)


def _strip(src: str) -> str:
    return _COMMENT_LINE.sub(" ", _COMMENT_BLOCK.sub(" ", src))


@lru_cache(maxsize=128)
def _find_csproj(start_dir: str) -> Optional[Tuple[str, str]]:
    """Walk up for nearest .csproj. Returns (csproj_path, project_dir) or None."""
    d = Path(start_dir)
    for _ in range(12):
        try:
            for p in d.glob("*.csproj"):
                if p.is_file():
                    return (str(p.resolve()), str(d.resolve()))
        except Exception:
            pass
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def _project_root_namespace(csproj_path: str, project_dir: str) -> str:
    try:
        text = Path(csproj_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    m = _ROOT_NS_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _ASM_RE.search(text)
    if m:
        return m.group(1).strip()
    return Path(project_dir).name


def _resolve_project_namespace(
    current: Path, ns: str, project_dir: Path, root_ns: str
) -> Optional[str]:
    """Map Project.Sub.Name → ProjectDir/Sub/Name.cs or folder with .cs files."""
    if not ns or not root_ns:
        return None
    if ns == root_ns:
        # project root
        if any(project_dir.glob("*.cs")):
            return str(project_dir)
        return None
    if not (ns == root_ns or ns.startswith(root_ns + ".")):
        return None
    rest = ns[len(root_ns) :].lstrip(".")
    if not rest:
        return str(project_dir) if project_dir.is_dir() else None
    parts = rest.split(".")
    # Try file at leaf
    folder = project_dir.joinpath(*parts[:-1]) if len(parts) > 1 else project_dir
    leaf = parts[-1]
    for cand in (
        folder / f"{leaf}.cs",
        project_dir.joinpath(*parts) / f"{leaf}.cs",
        project_dir.joinpath(*parts),
    ):
        if cand.is_file() and cand.suffix == ".cs":
            return str(cand.resolve())
        if cand.is_dir() and any(cand.glob("*.cs")):
            return str(cand.resolve())
    # Flatten: Project/Sub/Name.cs from dotted path
    flat = project_dir.joinpath(*parts)
    if flat.is_dir() and any(flat.glob("*.cs")):
        return str(flat.resolve())
    file_cs = project_dir.joinpath(*parts[:-1], parts[-1] + ".cs") if len(parts) > 1 else project_dir / f"{parts[0]}.cs"
    if file_cs.is_file():
        return str(file_cs.resolve())
    return None


def parse_csharp_imports(filepath: str) -> List[Dict]:
    path = Path(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _strip(text)
    edges: List[Dict] = []
    seen = set()

    found = _find_csproj(str(path.parent))
    root_ns = ""
    project_dir: Optional[Path] = None
    if found:
        csproj_path, pdir = found
        project_dir = Path(pdir)
        root_ns = _project_root_namespace(csproj_path, pdir)

    for m in _USING_RE.finditer(text):
        ns = m.group(1).strip()
        if not ns or ns in seen:
            continue
        seen.add(ns)
        is_framework = (
            ns == "System"
            or ns.startswith("System.")
            or ns.startswith("Microsoft.")
            or ns.startswith("Windows.")
        )
        resolved = None
        if not is_framework and project_dir is not None and root_ns:
            resolved = _resolve_project_namespace(path, ns, project_dir, root_ns)

        diag = None
        if not resolved:
            diag = {
                "category": "external_or_bare" if is_framework else "no_fs_match",
                "reason": f"C# using '{ns}'"
                + (" (framework)." if is_framework else " (no project path match)."),
                "severity": "info",
                "alternatives": [],
                "suggestion_for_agent": (
                    "Framework usings are expected external."
                    if is_framework
                    else "Project namespaces resolve when nearest .csproj + RootNamespace match on-disk folders."
                ),
                "details": {"framework": is_framework, "root_namespace": root_ns or None},
            }
        edges.append(
            make_edge(
                module=ns,
                raw_module=ns,
                is_relative=bool(resolved),
                resolved_path=resolved,
                resolution_confidence="high" if resolved else ("medium" if is_framework else "low"),
                statement_type="using",
                original_statement=m.group(0).strip(),
                diagnostic=diag,
                strategy="csharp-project-ns" if resolved else "csharp-using",
            )
        )
    return edges
