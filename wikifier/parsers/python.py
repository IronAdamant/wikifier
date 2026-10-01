"""
Python import parser (stdlib only).

Static imports are read with :mod:`ast`, so multi-line statements, comments and
strings are handled exactly; files the running interpreter cannot parse fall
back to a line-based regex scan. Dynamic ``importlib.import_module(...)`` /
``__import__(...)`` sites are analysed with the shared LDSI/CDIA machinery.

Resolution (``resolved_path`` = absolute path of the target file on disk):
  - relative imports: walk up ``level`` packages from the importing file;
  - absolute imports: look in the importing file's top-level package root,
    the project root, and ``<project>/src`` — the places a project's own code
    is importable from. Anything not found there is external (stdlib/3rd party);
  - ``from pkg import name`` where ``name`` is a submodule resolves to the
    submodule file (one edge per submodule), not to ``pkg/__init__.py``.

Each edge follows the shared parser contract (see ``wikifier.parsers._edge``):
module, raw_module, is_relative, level, alias, imported_names, statement_type,
line, resolved_path, resolution_confidence, confidence_score/_reasons/_explanation,
diagnostic, parser, resolution_strategy, resolution_metadata (+ dynamic fields).
"""

from __future__ import annotations

import ast
import functools
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import diagnostics
from ..contracts import compute_acs_confidence
from ._ldsi import (
    _analyze_dynamic_specifier,
    _apply_dynamic_registry,
    _extract_balanced_argument,
    _extract_candidate_literals,
)
from .cdia import get_cdia_engine

_DYN_IMPORT_RE = re.compile(r"(?P<call>(?:importlib\.)?import_module)\s*\(", re.MULTILINE)
_DYN_DUNDER_RE = re.compile(r"(?P<call>__import__)\s*\(", re.MULTILINE)
_STRING_LITERAL_RE = re.compile(r"""^(?P<q>['"])(?P<body>[A-Za-z_][\w.]*)(?P=q)$""")
_PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", ".git", ".wikifier")
_CREATIVE_TAGS = ("tagged_template", "registry_map", "multi_condition_feature_wrapper", "call_produced_path")
_CREATIVE_DETECTORS = (
    "TaggedTemplateDetector", "RegistryMapDetector",
    "MultiConditionFeatureWrapperDetector", "CallProducedPathDetector",
)


# ---------------------------------------------------------------------------
# Statement extraction
# ---------------------------------------------------------------------------

class _ImportStatement:
    __slots__ = ("kind", "module", "level", "names", "line", "original", "guard")

    def __init__(self, kind: str, module: str, level: int, names: List[Tuple[str, Optional[str]]], line: int, original: str, guard: Optional[str] = None):
        self.kind = kind          # "import" | "from"
        self.module = module      # dotted module without leading dots
        self.level = level        # number of leading dots (0 = absolute)
        self.names = names        # [(name, asname)]
        self.line = line
        self.original = original
        self.guard = guard        # innermost enclosing "if" / "try" (None at module/function level)


_GUARD_NODES = ((ast.If, "if"), (ast.Try, "try"), (ast.While, "while"), (ast.For, "for"))


def _guarded_nodes(tree: ast.AST):
    """Yield (node, innermost_guard) for every node; guards are if/try/while/for blocks."""
    stack = [(tree, None)]
    while stack:
        node, guard = stack.pop()
        yield node, guard
        for kind, label in _GUARD_NODES:
            if isinstance(node, kind):
                guard = label
                break
        for child in ast.iter_child_nodes(node):
            stack.append((child, guard))


def _statements_from_ast(source: str) -> List[_ImportStatement]:
    tree = ast.parse(source)
    lines = source.splitlines()
    out: List[_ImportStatement] = []
    for node, guard in _guarded_nodes(tree):
        if isinstance(node, ast.Import):
            kind, module, level = "import", "", 0
            names = [(a.name, a.asname) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            kind, module, level = "from", node.module or "", node.level or 0
            names = [(a.name, a.asname) for a in node.names]
        else:
            continue
        end = getattr(node, "end_lineno", None) or node.lineno
        original = " ".join(l.strip() for l in lines[node.lineno - 1:end])
        out.append(_ImportStatement(kind, module, level, names, node.lineno, original[:300], guard))
    out.sort(key=lambda s: s.line)
    return out


_IMPORT_LINE_RE = re.compile(r"^\s*import\s+([^\n#;]+)", re.MULTILINE)
_FROM_LINE_RE = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\s+(\([^)]*\)|[^#;\n]+)", re.MULTILINE)


def _statements_from_regex(source: str) -> List[_ImportStatement]:
    """Fallback for sources the running interpreter cannot parse (e.g. Python 2)."""
    out: List[_ImportStatement] = []
    for match in _IMPORT_LINE_RE.finditer(source):
        names = []
        for chunk in match.group(1).split(","):
            parts = re.split(r"\s+as\s+", chunk.strip(), maxsplit=1)
            if parts[0] and re.match(r"^[\w.]+$", parts[0]):
                names.append((parts[0], parts[1].strip() if len(parts) > 1 else None))
        if names:
            line = source.count("\n", 0, match.start()) + 1
            out.append(_ImportStatement("import", "", 0, names, line, match.group(0).strip()))
    for match in _FROM_LINE_RE.finditer(source):
        body = re.sub(r"#.*", "", match.group(3)).strip("() \n")
        names = []
        for chunk in body.split(","):
            parts = re.split(r"\s+as\s+", chunk.strip(), maxsplit=1)
            if parts[0]:
                names.append((parts[0], parts[1].strip() if len(parts) > 1 else None))
        line = source.count("\n", 0, match.start()) + 1
        out.append(_ImportStatement("from", match.group(2), len(match.group(1)), names, line, match.group(0).strip()[:300]))
    out.sort(key=lambda s: s.line)
    return out


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=4096)
def _dir_names(directory: str, mtime_ns: int) -> frozenset:
    """Entries of ``directory`` (cache keyed by its mtime, so new files show up)."""
    return frozenset(os.listdir(directory))


def _exists_exact_case(base: Path, candidate: Path) -> bool:
    """``candidate`` is a file whose every component below ``base`` matches a
    directory entry exactly. On case-insensitive filesystems (macOS, Windows)
    ``is_file()`` alone would accept ``from pkg import DagRun`` as ``pkg/DagRun.py``
    when only ``pkg/dagrun.py`` exists — Python itself would not."""
    if not candidate.is_file():
        return False
    current = base
    for name in candidate.relative_to(base).parts:
        try:
            if name not in _dir_names(str(current), current.stat().st_mtime_ns):
                return False
        except OSError:
            return False
        current = current / name
    return True


def _module_file(base: Path, dotted: str) -> Optional[Path]:
    """``base/a/b.py`` or ``base/a/b/__init__.py`` for dotted ``a.b`` (or None)."""
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        init = base / "__init__.py"
        return init if init.is_file() else None
    target = base.joinpath(*parts)
    for candidate in (target.with_name(target.name + ".py"), target / "__init__.py", target.with_name(target.name + ".pyi")):
        if _exists_exact_case(base, candidate):
            return candidate
    return None


def _project_root_for(path: Path) -> Path:
    env = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env:
        root = Path(env).resolve()
        try:
            path.relative_to(root)
            return root
        except ValueError:
            pass
    for parent in path.parents:
        if any((parent / marker).exists() for marker in _PROJECT_MARKERS):
            return parent
    return path.parent


def _search_roots(path: Path) -> List[Path]:
    """Directories a project's own absolute imports can resolve from (most specific first)."""
    roots: List[Path] = []
    top = path.parent
    while (top / "__init__.py").is_file() and top.parent != top:
        top = top.parent
    project = _project_root_for(path)
    for candidate in (top, project, project / "src"):
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def _relative_base(path: Path, level: int) -> Path:
    base = path.parent
    for _ in range(max(0, level - 1)):
        base = base.parent
    return base


def _package_name(path: Path, level: int) -> str:
    """Dotted package that a relative import with ``level`` dots refers to."""
    parts: List[str] = []
    current = path.parent
    while (current / "__init__.py").is_file() and current.parent != current:
        parts.append(current.name)
        current = current.parent
    parts.reverse()
    drop = max(0, level - 1)
    return ".".join(parts[: len(parts) - drop] if drop else parts)


def _resolve(path: Path, module: str, level: int, roots: Sequence[Path]) -> Optional[Path]:
    if level:
        return _module_file(_relative_base(path, level), module)
    for root in roots:
        found = _module_file(root, module)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# Edge construction
# ---------------------------------------------------------------------------

def _diagnostic_for(raw: str, level: int, module: str, resolved: Optional[Path]) -> Optional[Dict[str, Any]]:
    if resolved is not None:
        return None
    if level:
        return diagnostics.make_diagnostic(
            "relative_misresolve",
            f"Relative import '{raw}' ({module}) has no matching .py / __init__.py on disk.",
            severity="warn",
            suggestion_for_agent="Check the package layout; the target module may have moved or been deleted.",
            details={"raw_module": raw, "level": level, "resolved_module": module},
        )
    return diagnostics.make_diagnostic(
        "external_or_bare",
        f"Absolute import '{raw}' is not a module of this project (stdlib or third-party).",
        severity="info",
        suggestion_for_agent="External dependency; no action needed for the project graph.",
        details={"raw_module": raw, "level": 0, "resolved_module": module},
    )


def _edge(
    *,
    raw: str,
    module: str,
    level: int,
    statement_type: str,
    imported_names: List[str],
    alias: Optional[str],
    line: int,
    original: str,
    resolved: Optional[Path],
    guard: Optional[str] = None,
) -> Dict[str, Any]:
    is_relative = level > 0
    confidence = "high" if resolved else ("low" if is_relative else "medium")
    strategy = (
        "python-relative-hierarchy" if is_relative
        else "python-absolute-project" if resolved
        else "python-bare-or-external"
    )
    resolved_str = str(resolved.resolve()) if resolved else None
    score, reasons, explanation = compute_acs_confidence(
        confidence, resolved_path=resolved_str, strategy=strategy, is_conditional=bool(guard)
    )
    return {
        "module": module,
        "raw_module": raw,
        "is_relative": is_relative,
        "level": level,
        "alias": alias,
        "imported_names": imported_names,
        "original_statement": original,
        "statement_type": statement_type,
        "line": line,
        "resolved_path": resolved_str,
        "resolution_confidence": confidence,
        "confidence_score": score,
        "confidence_reasons": reasons,
        "confidence_explanation": explanation,
        "diagnostic": _diagnostic_for(raw, level, module, resolved),
        "is_dynamic": False,
        "is_conditional": bool(guard),
        "conditional_context": guard,
        "parser": "python",
        "resolution_strategy": strategy,
        "resolution_metadata": {
            "strategy": strategy,
            "target_on_disk": bool(resolved),
            "relative_level": level,
        },
    }


def _edges_for_statement(stmt: _ImportStatement, path: Path, roots: Sequence[Path]) -> List[Dict[str, Any]]:
    if stmt.kind == "import":
        edges = []
        for name, asname in stmt.names:
            if name.split(".")[0] == "__future__":
                continue
            edges.append(_edge(
                raw=name, module=name, level=0,
                statement_type="import_as" if asname else "import",
                imported_names=[], alias=asname, line=stmt.line, original=stmt.original,
                resolved=_resolve(path, name, 0, roots), guard=stmt.guard,
            ))
        return edges

    if stmt.module.split(".")[0] == "__future__":
        return []
    raw = "." * stmt.level + stmt.module
    if stmt.level:
        package = _package_name(path, stmt.level)
        module = ".".join(p for p in (package, stmt.module) if p) or stmt.module
    else:
        module = stmt.module
    names = [n for n, _ in stmt.names]
    aliases = [a for _, a in stmt.names if a]
    statement_type = "from_import_as" if aliases else "from_import"

    # Names that are submodules are real file dependencies of their own.
    submodules: List[Tuple[str, Path]] = []
    for name in names:
        if name == "*":
            continue
        dotted = f"{stmt.module}.{name}" if stmt.module else name
        target = _resolve(path, dotted, stmt.level, roots)
        if target is not None:
            submodules.append((name, target))
    container = _resolve(path, stmt.module, stmt.level, roots)
    all_submodules = names and len(submodules) == len([n for n in names if n != "*"]) and "*" not in names

    primary_target = submodules[0][1] if all_submodules and submodules else container
    edges = [_edge(
        raw=raw, module=module, level=stmt.level, statement_type=statement_type,
        imported_names=names, alias=aliases[-1] if aliases else None,
        line=stmt.line, original=stmt.original, resolved=primary_target, guard=stmt.guard,
    )]
    seen = {str(primary_target)} if primary_target else set()
    for name, target in submodules:
        if str(target) in seen:
            continue
        seen.add(str(target))
        sub_raw = f"{raw}{'' if raw.endswith('.') else '.'}{name}"
        edges.append(_edge(
            raw=sub_raw, module=f"{module}.{name}" if module else name, level=stmt.level,
            statement_type="from_import_submodule", imported_names=[name], alias=None,
            line=stmt.line, original=stmt.original, resolved=target, guard=stmt.guard,
        ))
    return edges


# ---------------------------------------------------------------------------
# Dynamic imports
# ---------------------------------------------------------------------------

def _strip_comments(content: str) -> str:
    """Blank out ``#`` comments outside string literals (keeps line numbers)."""
    out_lines = []
    for line in content.split("\n"):
        quote = None
        cut = None
        i = 0
        while i < len(line):
            c = line[i]
            if quote:
                if c == "\\":
                    i += 2
                    continue
                if c == quote:
                    quote = None
            elif c in ("'", '"'):
                quote = c
            elif c == "#":
                cut = i
                break
            i += 1
        out_lines.append(line if cut is None else line[:cut])
    return "\n".join(out_lines)


_DOCSTRING_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')


def _strip_docstrings(content: str) -> str:
    """Blank triple-quoted strings while preserving line structure."""
    return _DOCSTRING_RE.sub(lambda m: "\n" * m.group(0).count("\n"), content)


def _dataflow_candidates(content: str, call_start: int, var: str) -> List[Dict[str, Any]]:
    """Literal candidates from the nearest preceding ``var = ...`` assignment."""
    window = content[max(0, call_start - 1800):call_start]
    rhs = ""
    for m in re.finditer(r"(?:^|[\n;])\s*([A-Za-z_]\w*)\s*=\s*([^;\n]{0,250}?)(?:;|$|\n)", window, re.MULTILINE):
        if m.group(1) == var:
            rhs = (m.group(2) or "").strip()
    if not rhs:
        return []
    found = list(_extract_candidate_literals(rhs) or [])
    found.extend(_apply_dynamic_registry(rhs, {"context": "py_dataflow", "var": var}).get("extra_candidates") or [])
    return found


def _dynamic_imports(content: str, path: Path, roots: Sequence[Path]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    engine = get_cdia_engine()
    for pattern, kind in ((_DYN_IMPORT_RE, "import_module"), (_DYN_DUNDER_RE, "dunder_import")):
        for match in pattern.finditer(content):
            start = match.start()
            expr = (_extract_balanced_argument(content, start) or content[start:start + 180]).strip()
            if expr.startswith("(") and expr.endswith(")"):
                expr = expr[1:-1].strip()
            first_arg = expr.split(",")[0].strip()
            analysis = _analyze_dynamic_specifier(expr) or {}
            dynamic_type = analysis.get("dynamic_type", "expression")
            notes = ["python_dynamic"] + list(analysis.get("analysis_notes") or [])
            candidates = list(_extract_candidate_literals(expr) or [])
            if re.match(r"^[A-Za-z_]\w*$", first_arg):
                extra = _dataflow_candidates(content, start, first_arg)
                if extra:
                    candidates.extend(extra)
                    notes.append("dataflow_var_substitution")
            registry = _apply_dynamic_registry(expr, {"path": str(path), "context": "python_expr_path"}) or {}
            candidates.extend(registry.get("extra_candidates") or [])
            notes.extend(f"registry:{n}" for n in (registry.get("notes") or []) if n)

            literal = _STRING_LITERAL_RE.match(first_arg)
            module_name = literal.group("body") if literal else None
            resolved = _resolve(path, module_name, 0, roots) if module_name else None
            if literal:
                dynamic_type = "literal"

            cdia = engine.analyze_import_site(
                content, start, first_arg[:60], expr_raw=expr, dynamic_type_hint="expression",
                statement_type=kind, dynamic_candidates=candidates, language="python",
            )
            conditional = cdia.get("conditional_analysis", {}) or {}
            dynamic = cdia.get("dynamic_analysis", {}) or {}
            tags = conditional.get("semantic_tags", []) or []
            context = "if" if ("control_flow" in tags or "if_statement" in tags) else (
                "ternary" if any("ternary" in str(t).lower() for t in tags) else None
            )
            base = "high" if resolved else "low"
            score, reasons, explanation = compute_acs_confidence(
                base, is_dynamic=True, dynamic_type=dynamic_type,
                is_conditional=bool(conditional.get("is_conditional")),
                resolved_path=str(resolved) if resolved else None,
                conditional_analysis=conditional, dynamic_analysis=dynamic,
            )
            display = module_name or next(
                (c.get("raw") for c in candidates if isinstance(c, dict) and c.get("raw") and len(c["raw"]) < 60),
                expr[:80],
            )
            diagnostic = None
            dyn_tags = dynamic.get("semantic_tags", []) or []
            detectors = dynamic.get("detectors_fired", []) or []
            creative = [t for t in dyn_tags if t in _CREATIVE_TAGS]
            if creative or any(d in _CREATIVE_DETECTORS for d in detectors):
                diagnostic = diagnostics.make_creative_dynamic_diagnostic(
                    expr=expr, creative_tags=creative or dyn_tags, detectors_fired=detectors,
                )
            edges.append({
                "module": display,
                "raw_module": module_name or expr[:200],
                "is_relative": False,
                "level": 0,
                "alias": None,
                "imported_names": [],
                "original_statement": content[start:start + 300].split("\n")[0],
                "statement_type": f"dynamic_{kind}",
                "line": content.count("\n", 0, start) + 1,
                "resolved_path": str(resolved.resolve()) if resolved else None,
                "resolution_confidence": base,
                "confidence_score": score,
                "confidence_reasons": reasons,
                "confidence_explanation": explanation,
                "is_dynamic": True,
                "dynamic_type": dynamic_type,
                "dynamic_complexity": analysis.get("dynamic_complexity", "moderate"),
                "expr_raw": expr,
                "dynamic_candidates": candidates,
                "analysis_notes": notes,
                "cdia": cdia,
                "conditional_analysis": conditional,
                "dynamic_analysis": dynamic,
                "is_conditional": bool(conditional.get("is_conditional")),
                "conditional_context": context,
                "diagnostic": diagnostic,
                "parser": "python",
                "resolution_strategy": "python-dynamic-literal" if literal else "python-dynamic-expression",
                "resolution_metadata": {
                    "strategy": "python-dynamic-literal" if literal else "python-dynamic-expression",
                    "target_on_disk": bool(resolved),
                },
            })
    return edges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_python_imports(filepath: str) -> List[Dict[str, Any]]:
    """Structured import edges for a Python file ([] if it cannot be read)."""
    path = Path(filepath).resolve()
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        statements = _statements_from_ast(source)
        parse_mode = "ast"
    except (SyntaxError, ValueError):
        statements = _statements_from_regex(_strip_comments(_strip_docstrings(source)))
        parse_mode = "regex-fallback"
    roots = _search_roots(path)
    edges: List[Dict[str, Any]] = []
    for stmt in statements:
        for edge in _edges_for_statement(stmt, path, roots):
            edge["parse_mode"] = parse_mode
            edges.append(edge)
    edges.extend(_dynamic_imports(_strip_comments(_strip_docstrings(source)), path, roots))
    return edges


def parse_python_imports_from_string(content: str, fake_path: str = "dummy.py") -> List[Dict[str, Any]]:
    """Parse source text (written to a temporary file so relative resolution has a path)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return parse_python_imports(tmp_path)
    finally:
        os.unlink(tmp_path)


__all__: Iterable[str] = ("parse_python_imports", "parse_python_imports_from_string")
