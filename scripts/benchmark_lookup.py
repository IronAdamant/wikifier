#!/usr/bin/env python3
"""Measure what Wikifier lookups cost and how often they are right, against grep.

Usage:
    python scripts/benchmark_lookup.py REPO [--samples 40] [--seed 7] [--json OUT] [--md OUT]

For a Python project REPO (copied to a temp dir first; the original is never
written), three questions an agent asks before editing are answered three ways:

  T1  "Which files import M?"            Wikifier get_dependents  vs  grep of import lines
  T2  "What could break if I change M?"  transitive importers, depth <= 3, same tools
  T3  "What does M import?"              Wikifier get_dependencies  vs  reading M

Cost is the text the agent has to read (tool output / grep output / file
bytes), reported in tokens at ~4 characters per token. Correctness is scored
against an independent reference: the stdlib ``modulefinder`` bytecode scanner,
run per file with namespace-package support. ``__init__.py`` targets are
excluded on every side (importing ``pkg.mod`` always executes ``pkg/__init__``;
counting it would measure convention, not lookup quality).

Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import json
import modulefinder
import os
import random
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CHARS_PER_TOKEN = 4
# An agent cannot read more than about one large context window for one question;
# transitive searches stop expanding once they have cost this much.
DEFAULT_BUDGET_TOKENS = 200_000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", ".tox", "__pycache__", ".wikifier_staging", "build", "dist"}


def tokens(chars: int) -> int:
    return (chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# Reference resolver (independent of Wikifier's parser)
# ---------------------------------------------------------------------------

class _ShallowFinder(modulefinder.ModuleFinder):
    """ModuleFinder that scans one file and records each import's target file.

    Other modules are located but never scanned, namespace packages (PEP 420)
    are supported, and the scanned file gets its real dotted name so relative
    imports resolve.
    """

    def __init__(self, path: List[str]):
        super().__init__(path=path)
        self.targets: Set[str] = set()
        self._recording = False
        self._namespaces: Dict[str, List[str]] = {}

    def find_module(self, name, path, parent=None):
        fullname = f"{parent.__name__}.{name}" if parent else name
        spec = importlib.machinery.PathFinder.find_spec(name, path if path is not None else self.path)
        if spec is None:
            raise ImportError(name)
        if spec.submodule_search_locations is not None and spec.origin in (None, "namespace"):
            # namespace package (loader is None before 3.11, NamespaceLoader after)
            locations = list(spec.submodule_search_locations or [])
            self._namespaces[fullname] = locations
            return None, locations[0], ("", "", modulefinder._PKG_DIRECTORY)
        if spec.origin and spec.origin.endswith(".py"):
            kind = modulefinder._PY_SOURCE
            if os.path.basename(spec.origin) == "__init__.py":
                return None, os.path.dirname(spec.origin), ("", "", modulefinder._PKG_DIRECTORY)
            return None, spec.origin, (".py", "rb", kind)
        raise ImportError(name)  # extensions, bytecode-only: outside the project graph

    def load_package(self, fqname, pathname):
        m = self.add_module(fqname)
        if fqname in self._namespaces:
            m.__path__ = self._namespaces[fqname]
            m.__file__ = None
        else:
            m.__path__ = [pathname]
            m.__file__ = os.path.join(pathname, "__init__.py")
        return m

    def load_module(self, fqname, fp, pathname, file_info):
        if file_info[2] == modulefinder._PKG_DIRECTORY:
            return self.load_package(fqname, pathname)
        m = self.add_module(fqname)
        m.__file__ = pathname
        return m

    def import_hook(self, name, caller=None, fromlist=None, level=-1):
        parent = self.determine_parent(caller, level=level)
        q, tail = self.find_head_package(parent, name)
        m = self.load_tail(q, tail)
        if self._recording:
            if m.__file__:
                self.targets.add(m.__file__)
            for sub in fromlist or ():
                if sub != "*" and m.__path__:
                    subm = self.import_module(sub, f"{m.__name__}.{sub}", m)
                    if subm is not None and subm.__file__:
                        self.targets.add(subm.__file__)
        return q

    def scan_file(self, path: Path, fqname: str, is_pkg: bool) -> None:
        code = compile(path.read_bytes(), str(path), "exec")
        parent = fqname if is_pkg else fqname.rpartition(".")[0]
        if parent:
            try:
                self.import_hook(parent)
            except ImportError:
                pass
        m = self.add_module(fqname)
        m.__file__ = str(path)
        if is_pkg:
            m.__path__ = [str(path.parent)]
        self._recording = True
        try:
            self.scan_code(code, m)
        finally:
            self._recording = False


def _search_roots(root: Path) -> List[Path]:
    roots = [root / "src"] if (root / "src").is_dir() else []
    return roots + [root]


def _dotted_name(root: Path, roots: List[Path], path: Path) -> Tuple[str, bool]:
    for base in roots:
        try:
            rel = path.relative_to(base)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        if parts and all(p.isidentifier() for p in parts):
            return ".".join(parts), is_pkg
    return "", False


def build_reference_graph(root: Path, files: List[str]) -> Tuple[Dict[str, Set[str]], int]:
    """``{file: {imported project files}}`` from the stdlib bytecode scanner."""
    roots = _search_roots(root)
    path = [str(r) for r in roots]
    graph: Dict[str, Set[str]] = {}
    failures = 0
    for rel in files:
        abspath = root / rel
        fqname, is_pkg = _dotted_name(root, roots, abspath)
        finder = _ShallowFinder(path)
        try:
            finder.scan_file(abspath, fqname or "__main__", is_pkg)
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError):
            failures += 1
            graph[rel] = set()
            continue
        out = set()
        for target in finder.targets:
            try:
                out.add(Path(target).resolve().relative_to(root).as_posix())
            except ValueError:
                continue
        graph[rel] = {t for t in out if t != rel}
    return graph, failures


# ---------------------------------------------------------------------------
# Baseline: what an agent sees from grep
# ---------------------------------------------------------------------------

_IMPORT_LINE = re.compile(r"^\s*(?:from\s+\S+\s+import\b|import\s+\S)")


def _import_lines(root: Path, files: List[str]) -> Dict[str, List[Tuple[int, str]]]:
    out: Dict[str, List[Tuple[int, str]]] = {}
    for rel in files:
        try:
            lines = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        out[rel] = [(i + 1, line) for i, line in enumerate(lines) if _IMPORT_LINE.match(line)]
    return out


def grep_importers(target: str, import_lines: Dict[str, List[Tuple[int, str]]]) -> Tuple[Set[str], int]:
    """Files with an import line naming ``target``'s module stem, and the size of
    ``grep -rn`` output an agent would read (``path:line:text`` per hit)."""
    stem = Path(target).stem
    pattern = re.compile(r"(?<![\w.])" + re.escape(stem) + r"\b|\." + re.escape(stem) + r"\b")
    hits: Set[str] = set()
    chars = 0
    for rel, lines in import_lines.items():
        if rel == target:
            continue
        for lineno, line in lines:
            if pattern.search(line):
                hits.add(rel)
                chars += len(f"{rel}:{lineno}:{line}\n")
    return hits, chars


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _not_init(paths: Iterable[str]) -> Set[str]:
    return {p for p in paths if not p.endswith("__init__.py")}


def score(found: Set[str], truth: Set[str]) -> Tuple[float, float]:
    found, truth = _not_init(found), _not_init(truth)
    if not found and not truth:
        return 1.0, 1.0
    tp = len(found & truth)
    precision = tp / len(found) if found else (1.0 if not truth else 0.0)
    recall = tp / len(truth) if truth else 1.0
    return precision, recall


def _reverse(graph: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    rev: Dict[str, Set[str]] = {k: set() for k in graph}
    for src, dsts in graph.items():
        for dst in dsts:
            rev.setdefault(dst, set()).add(src)
    return rev


class _Budget:
    def __init__(self, tokens_allowed: Optional[int]):
        self.allowed = tokens_allowed
        self.chars = 0
        self.exhausted = False

    def spend(self, chars: int) -> None:
        self.chars += chars
        if self.allowed is not None and tokens(self.chars) >= self.allowed:
            self.exhausted = True


def _closure(start: str, step, depth: int = 3, budget: Optional[_Budget] = None) -> Set[str]:
    """Nodes reachable from ``start`` in ``depth`` steps (breadth-first); stops
    expanding when ``budget`` is exhausted — the agent answers with what it has."""
    seen: Set[str] = set()
    frontier = {start}
    for _ in range(depth):
        nxt: Set[str] = set()
        for node in sorted(frontier):
            if budget is not None and budget.exhausted:
                return seen | nxt
            nxt |= step(node) - seen - {start}
        seen |= nxt
        frontier = nxt
    return seen


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def copy_python_tree(src: Path, dst: Path) -> List[str]:
    files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not (name.endswith(".py") or name in {"pyproject.toml", "setup.cfg", "setup.py"}):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(src)
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst / rel)
            if name.endswith(".py"):
                files.append(rel.as_posix())
    return sorted(files)


def run_benchmark(
    repo: Path,
    samples: int = 40,
    seed: int = 7,
    detail: Optional[str] = None,
    budget_tokens: Optional[int] = DEFAULT_BUDGET_TOKENS,
) -> Dict[str, object]:
    from wikifier import api, cache_store as cs

    repo = Path(repo).resolve()
    work = Path(tempfile.mkdtemp(prefix="wikifier_bench_")).resolve()
    try:
        files = copy_python_tree(repo, work)
        t0 = time.time()
        update = api.update_maps(full=True, project_root=str(work))
        setup_s = round(time.time() - t0, 2)
        if not update.get("success"):
            raise RuntimeError(f"update_maps failed: {update.get('error') or update}")

        t0 = time.time()
        reference, ref_failures = build_reference_graph(work, files)
        reference_s = round(time.time() - t0, 2)
        ref_rev = _reverse(reference)
        lines = _import_lines(work, files)

        # Whole-graph agreement between Wikifier's map and the reference.
        wik_graph: Dict[str, Set[str]] = {}
        for rel in files:
            wik_graph[rel] = {d for d in cs.load_dependencies(work, rel) if d != rel}
        wik_edges = {(s, d) for s, ds in wik_graph.items() for d in _not_init(ds)}
        ref_edges = {(s, d) for s, ds in reference.items() for d in _not_init(ds)}
        tp = len(wik_edges & ref_edges)
        # If the reference resolves far fewer edges than Wikifier, it does not
        # understand this layout (e.g. one package split across many src/ roots and
        # merged at install time); accuracy against it would be meaningless.
        reference_ok = len(ref_edges) >= 0.5 * len(wik_edges)
        graph_accuracy = {
            "reference_ok": reference_ok,
            "reference_edges": len(ref_edges),
            "wikifier_edges": len(wik_edges),
            "precision": round(tp / len(wik_edges), 3) if wik_edges else None,
            "recall": round(tp / len(ref_edges), 3) if ref_edges else None,
            "sample_missed": sorted(ref_edges - wik_edges)[:15],
            "sample_extra": sorted(wik_edges - ref_edges)[:15],
        }

        candidates = sorted(f for f in files if not f.endswith("__init__.py"))
        rng = random.Random(seed)
        imported = [f for f in candidates if ref_rev.get(f)]
        others = [f for f in candidates if not ref_rev.get(f)]
        n_imported = min(len(imported), (samples * 3) // 4)
        targets = rng.sample(imported, n_imported) + rng.sample(others, min(len(others), samples - n_imported))

        def wik_dependents(rel: str) -> Tuple[Set[str], int]:
            res = api.get_dependents(rel, project_root=str(work))
            return set(res.get("dependents") or []), len(json.dumps(res, indent=2))

        kwargs = {"detail": detail} if detail else {}
        rows = []
        for target in targets:
            truth1 = ref_rev.get(target, set())
            w1, w1_chars = wik_dependents(target)
            g1, g1_chars = grep_importers(target, lines)

            truth2 = _closure(target, lambda f: ref_rev.get(f, set()))
            w_budget, g_budget = _Budget(budget_tokens), _Budget(budget_tokens)

            def w_step(f):
                found, chars = wik_dependents(f)
                w_budget.spend(chars)
                return found

            def g_step(f):
                found, chars = grep_importers(f, lines)
                g_budget.spend(chars)
                return found

            w2 = _closure(target, w_step, budget=w_budget)
            g2 = _closure(target, g_step, budget=g_budget)

            deps = api.get_dependencies(target, project_root=str(work), **kwargs)
            if "internal" in deps:  # compact (default)
                w3 = {e["path"] for e in deps["internal"]}
            else:
                w3 = {d["resolved_path"] for d in deps.get("imports", []) if d.get("resolved_path")}
            w3.discard(target)  # self-imports (inside functions) are excluded on both sides
            text = (work / target).read_text(encoding="utf-8", errors="replace")
            rows.append({
                "target": target,
                "t1": {"truth": len(truth1), "wikifier": score(w1, truth1), "grep": score(g1, truth1),
                       "wikifier_tokens": tokens(w1_chars), "grep_tokens": tokens(g1_chars)},
                "t2": {"truth": len(truth2), "wikifier": score(w2, truth2), "grep": score(g2, truth2),
                       "wikifier_tokens": tokens(w_budget.chars), "grep_tokens": tokens(g_budget.chars),
                       "wikifier_budget_exhausted": w_budget.exhausted, "grep_budget_exhausted": g_budget.exhausted},
                "t3": {"truth": len(reference.get(target, ())), "wikifier": score(w3, reference.get(target, set())),
                       "wikifier_tokens": tokens(len(json.dumps(deps, indent=2))),
                       "file_tokens": tokens(len(text)),
                       "import_lines_tokens": tokens(sum(len(l) + 1 for _, l in lines.get(target, [])))},
            })

        def agg(task: str, key: str) -> Dict[str, Optional[float]]:
            if not reference_ok:
                return {"precision": None, "recall": None, "exact_answers": None}
            ps = [r[task][key][0] for r in rows]
            rs = [r[task][key][1] for r in rows]
            exact = sum(1 for r in rows if r[task][key] == (1.0, 1.0))
            return {"precision": _mean(ps), "recall": _mean(rs), "exact_answers": exact}

        def tok(task: str, key: str) -> Dict[str, int]:
            vals = sorted(r[task][key] for r in rows)
            return {"total": sum(vals), "median": vals[len(vals) // 2] if vals else 0}

        summary = {
            "t1_importers": {"wikifier": {**agg("t1", "wikifier"), "tokens": tok("t1", "wikifier_tokens")},
                             "grep": {**agg("t1", "grep"), "tokens": tok("t1", "grep_tokens")}},
            "t2_impact_depth3": {
                "wikifier": {**agg("t2", "wikifier"), "tokens": tok("t2", "wikifier_tokens"),
                             "budget_exhausted": sum(r["t2"]["wikifier_budget_exhausted"] for r in rows)},
                "grep": {**agg("t2", "grep"), "tokens": tok("t2", "grep_tokens"),
                         "budget_exhausted": sum(r["t2"]["grep_budget_exhausted"] for r in rows)}},
            "t3_imports": {"wikifier": {**agg("t3", "wikifier"), "tokens": tok("t3", "wikifier_tokens")},
                           "read_file": {"tokens": tok("t3", "file_tokens")},
                           "read_import_lines": {"tokens": tok("t3", "import_lines_tokens")}},
        }
        return {
            "repo": str(repo),
            "python_files": len(files),
            "samples": len(rows),
            "seed": seed,
            "dependencies_detail": detail or "default",
            "budget_tokens_per_question": budget_tokens,
            "setup": {"update_maps_seconds": setup_s, "reference_seconds": reference_s,
                      "reference_parse_failures": ref_failures},
            "graph_accuracy": graph_accuracy,
            "summary": summary,
            "rows": rows,
            "method": {"tokens": f"characters / {CHARS_PER_TOKEN}",
                       "reference": "stdlib modulefinder bytecode scan per file (namespace packages supported)",
                       "excluded": "__init__.py targets on every side"},
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def render_markdown(results: List[Dict[str, object]]) -> str:
    out = ["| Repo | Files | Task | Tool | Precision | Recall | Exact | Tokens (total) | Tokens (median) | Over budget |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for res in results:
        name = Path(str(res["repo"])).name
        for task, label in (("t1_importers", "T1 importers"), ("t2_impact_depth3", "T2 impact (≤3)"),
                            ("t3_imports", "T3 imports")):
            for tool, data in res["summary"][task].items():
                out.append("| {} | {} | {} | {} | {} | {} | {} | {:,} | {:,} | {} |".format(
                    name, res["python_files"], label, tool,
                    data.get("precision", "—") if data.get("precision") is not None else "—",
                    data.get("recall", "—") if data.get("recall") is not None else "—",
                    f"{data['exact_answers']}/{res['samples']}" if data.get("exact_answers") is not None else "—",
                    data["tokens"]["total"], data["tokens"]["median"],
                    f"{data['budget_exhausted']}/{res['samples']}" if "budget_exhausted" in data else "—"))
    out += ["", "| Repo | update-maps (s) | Reference edges | Wikifier edges | Graph precision | Graph recall |",
            "|---|---|---|---|---|---|"]
    for res in results:
        g = res["graph_accuracy"]
        p, r = (g["precision"], g["recall"]) if g.get("reference_ok") else ("not scored", "not scored")
        out.append(f"| {Path(str(res['repo'])).name} | {res['setup']['update_maps_seconds']} | {g['reference_edges']:,} | "
                   f"{g['wikifier_edges']:,} | {p} | {r} |")
    return "\n".join(out) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("repos", nargs="+", help="Python project directories")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--detail", help="get_dependencies detail level to measure (if supported)")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET_TOKENS,
                        help="token budget per transitive question (0 = unlimited)")
    parser.add_argument("--json", help="write full results (with per-target rows) here")
    parser.add_argument("--md", help="write the summary tables here")
    args = parser.parse_args(argv)
    results = []
    for repo in args.repos:
        print(f"benchmarking {repo} …", file=sys.stderr)
        results.append(run_benchmark(Path(repo), samples=args.samples, seed=args.seed, detail=args.detail,
                                     budget_tokens=args.budget or None))
    table = render_markdown(results)
    print(table)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, default=list), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(table, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
