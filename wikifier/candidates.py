"""Scoped source candidate collection (agent warm-path walk cliff).

AGENT MAP:
  resolve_map_scope / MapScope       — single map-scope contract (walk roots + prefixes)
  collect_candidate_source_files     — map candidates under MapScope
  filter_index_to_map_scope          — mtime index keys under MapScope only
  evaluate_candidate_reuse           — pure reuse decision (no I/O)
  try_cached_candidate_rels / resolve_candidates / candidate_list_meta

Map collection rules (critical):
  - ``monitored_paths.txt`` is the *wiki health* surface (often individual .md files).
    It is NOT the sole map walk set. Only **directory** entries that look like package
    roots are used; wiki-only file lists fall back to full/package tree walk.
  - ``map_paths.txt`` is the *map package roots* surface (independent of wiki).
  - ``--directory=`` always wins for map scope.
  - Collect, live count, index filter, and prune all honor the same MapScope.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".rs", ".go",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh",
    ".cs", ".java",
}

# Wiki/docs/shell — never treat as map-only roots when they appear alone in monitored_paths
NON_MAP_FILE_EXTS = {
    ".md", ".txt", ".rst", ".html", ".json", ".yml", ".yaml", ".toml",
    ".sh", ".bat", ".ps1", ".css", ".svg", ".png", ".jpg",
}

DEFAULT_EXCLUDES = {
    "node_modules", ".git", "dist", "build", ".next", "coverage",
    "__pycache__", "tmp", "temp", ".turbo", ".cache", "target", "out",
    ".pnpm", ".yarn", ".store", "store", "virtual-store", ".pnp",
    ".pnp.cjs", ".wikifier_staging",
    # Virtualenv dirs only — do NOT exclude bare "env" (drops rust sys/env/*.rs etc.)
    "venv", ".venv",
}


def _max_dir_mtime_ns(walk: Path, excludes: Optional[Set[str]] = None) -> int:
    """Max directory mtime under walk (catches nested file creates; O(dirs))."""
    excludes = excludes or DEFAULT_EXCLUDES
    mx = 0
    try:
        walk = Path(walk)
        for dirpath, dirnames, _filenames in os.walk(str(walk)):
            # prune
            dirnames[:] = [
                d for d in dirnames
                if d not in excludes and not d.startswith(".")
            ]
            try:
                st = os.stat(dirpath)
                mx = max(mx, int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))))
            except Exception:
                continue
    except Exception:
        pass
    return mx


def scope_fingerprint(root: Path, directory: Optional[str] = None) -> str:
    """Fingerprint for candidate-list reuse.

    Uses max *directory* mtime under the walk root (not just the root itself) so
    creating a nested file invalidates reuse. Content-only edits do not change
    dir mtimes → list reuse remains valid; content-hash dirty still catches edits.
    """
    root = Path(root)
    walk = (root / directory) if directory else root
    if directory and not walk.is_dir():
        walk = root
    try:
        rp = os.path.realpath(str(walk))
        mx = _max_dir_mtime_ns(walk)
        return f"{rp}:d{mx}"
    except Exception:
        return f"{walk}:0"


def _read_path_list_file(root: Path, name: str) -> List[str]:
    """Read a one-path-per-line config file (skips comments, bare '.')."""
    fp = root / name
    if not fp.is_file():
        return []
    out: List[str] = []
    try:
        for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
            p = line.strip()
            if not p or p.startswith("#"):
                continue
            p = p.split()[0].rstrip("/")
            if p in (".", "./"):
                continue  # bare-dot thrash
            out.append(p)
    except Exception:
        return []
    return out


def _read_monitored_paths(root: Path) -> List[str]:
    """Wiki/health watch list (files or dirs). Not the map walk set by itself."""
    return _read_path_list_file(root, "monitored_paths.txt")


def _read_map_paths(root: Path) -> List[str]:
    """Map package roots (map_paths.txt) — independent of monitored_paths."""
    return _read_path_list_file(root, "map_paths.txt")


def _map_walk_roots_from_map_paths(root: Path) -> List[Path]:
    """Directory (or file) roots for *map* collection from map_paths.txt."""
    dirs: List[Path] = []
    files: List[Path] = []
    for mp in _read_map_paths(root):
        p = Path(mp) if os.path.isabs(mp) else (root / mp)
        if p.is_dir():
            dirs.append(p)
        elif p.is_file() and p.suffix.lower() in SOURCE_EXTS:
            files.append(p)
    return dirs  # files handled via directory entries; single-file map_paths rare


def _map_walk_roots_from_monitored(root: Path) -> List[Path]:
    """Legacy fallback: directory roots only from monitored_paths (never wiki files)."""
    dirs: List[Path] = []
    for mp in _read_monitored_paths(root):
        p = Path(mp) if os.path.isabs(mp) else (root / mp)
        if p.is_dir():
            dirs.append(p)
    return dirs


@dataclass(frozen=True)
class MapScope:
    """Authoritative map scope: walk roots + project-relative prefixes.

    Full-tree scope has ``is_full_tree=True`` and ``rel_prefixes=()``.
    Narrow scope (``directory=`` or ``map_paths``) has one or more prefixes;
    index filter / prune keep only keys under those prefixes.
    """

    root: Path
    directory: Optional[str]
    walk_roots: Tuple[Path, ...]
    rel_prefixes: Tuple[str, ...]  # posix-style; empty tuple means full tree
    is_full_tree: bool

    def key_in_scope(self, rel: str) -> bool:
        """True if a project-relative path belongs to this map scope."""
        if not isinstance(rel, str) or not rel or rel.startswith("_"):
            return False
        if self.is_full_tree:
            return True
        # Normalize separators
        r = rel.replace("\\", "/").lstrip("./")
        for pref in self.rel_prefixes:
            if not pref:
                return True
            if r == pref or r.startswith(pref + "/"):
                return True
        return False


def resolve_map_scope(
    root: Path,
    directory: Optional[str] = None,
    *,
    use_monitored: bool = True,
    use_map_paths: bool = True,
) -> MapScope:
    """Build MapScope from directory / map_paths / monitored / full root."""
    try:
        root_res = Path(root).resolve()
    except Exception:
        root_res = Path(root)
    walk_roots = _resolve_map_walk_roots(
        root_res,
        directory,
        use_monitored=use_monitored,
        use_map_paths=use_map_paths,
    )
    prefixes: List[str] = []
    full = False
    for wr in walk_roots:
        try:
            rel = os.path.relpath(str(wr), str(root_res)).replace("\\", "/")
        except Exception:
            rel = "."
        if rel in (".", "", os.curdir):
            full = True
            prefixes = []
            break
        prefixes.append(rel.rstrip("/"))
    # De-dupe preserve order
    seen: Set[str] = set()
    uniq: List[str] = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return MapScope(
        root=root_res,
        directory=directory,
        walk_roots=tuple(walk_roots),
        rel_prefixes=tuple(uniq),
        is_full_tree=full or not uniq,
    )


def filter_index_to_map_scope(
    index: Dict[str, Any],
    scope: MapScope,
) -> Dict[str, Any]:
    """Keep only mtime-index keys under *map* scope (not full tree when map_paths set).

    Critical for full-tree→map_paths migration: leftover outside keys must not
    poison reuse (would force permanent candidates_relisted).
    """
    if not index:
        return {}
    if scope.is_full_tree:
        return {k: v for k, v in index.items() if isinstance(k, str) and not k.startswith("_")}
    out: Dict[str, Any] = {}
    for k, v in index.items():
        if isinstance(k, str) and scope.key_in_scope(k):
            out[k] = v
    return out


def filter_index_to_scope(
    index: Dict[str, Any],
    directory: Optional[str] = None,
    *,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Filter mtime index keys to map scope.

    When ``root`` is provided, honors ``map_paths`` / monitored roots (MapScope).
    When only ``directory`` is given (legacy callers), filters by that prefix;
    ``directory=None`` without root returns the full index (legacy behavior).
    Prefer ``filter_index_to_map_scope`` + ``resolve_map_scope`` for new code.
    """
    if root is not None:
        return filter_index_to_map_scope(index, resolve_map_scope(root, directory))
    if not directory:
        return dict(index or {})
    d = directory.rstrip("/").replace("\\", "/")
    pref = d + "/"
    out: Dict[str, Any] = {}
    for k, v in (index or {}).items():
        if not isinstance(k, str):
            continue
        kk = k.replace("\\", "/")
        if kk == d or kk.startswith(pref):
            out[k] = v
    return out


def _load_excludes(root: Path) -> Tuple[Set[str], Set[str]]:
    excludes = set(DEFAULT_EXCLUDES)
    globs: Set[str] = set()
    ep_root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", str(root)))
    for ep in (ep_root / "exclude_patterns.txt", root / "exclude_patterns.txt"):
        if not ep.is_file():
            continue
        try:
            for line in ep.read_text(errors="ignore").splitlines():
                p = line.strip()
                if not p or p.startswith("#"):
                    continue
                p = p.split()[0]
                if any(ch in p for ch in "*?["):
                    globs.add(p)
                excludes.add(p.rstrip("/*"))
        except Exception:
            pass
        break
    return excludes, globs


def _git_scope_dirty(root: Path, directory: Optional[str]) -> Optional[bool]:
    """True if git sees changes under scope (incl. untracked). None if not a git repo / error."""
    if not ((root / ".git").exists() or (root / ".git" / "HEAD").exists()):
        return None
    try:
        cmd = ["git", "status", "--porcelain", "-unormal", "--"]
        if directory:
            cmd.append(str(directory).rstrip("/") + "/")
        else:
            cmd.append(".")
        out = subprocess.check_output(cmd, cwd=str(root), stderr=subprocess.DEVNULL)
        return len(out.strip()) > 0
    except Exception:
        return None


def _resolve_map_walk_roots(
    root: Path,
    directory: Optional[str] = None,
    *,
    use_monitored: bool = True,
    use_map_paths: bool = True,
) -> List[Path]:
    """Same walk-root precedence as collect / live_source_count (must stay aligned).

    1. ``directory=``
    2. ``map_paths.txt`` dirs
    3. directory entries from ``monitored_paths.txt``
    4. full project root
    """
    try:
        root = Path(root).resolve()
    except Exception:
        root = Path(root)
    if directory:
        d = root / directory
        return [d if d.is_dir() else root]
    walk_roots: List[Path] = []
    if use_map_paths:
        walk_roots = _map_walk_roots_from_map_paths(root)
    if not walk_roots and use_monitored:
        walk_roots = _map_walk_roots_from_monitored(root)
    if not walk_roots:
        walk_roots = [root]
    return walk_roots


def collect_candidate_source_files(
    root: Path,
    directory: Optional[str] = None,
    *,
    use_monitored: bool = True,
    use_map_paths: bool = True,
) -> List[Path]:
    """Collect source files under root for the *map* pipeline.

    Scope precedence:
      1. ``directory=`` (CLI/API)
      2. ``map_paths.txt`` package roots (map surface — not wiki)
      3. directory entries from ``monitored_paths.txt`` (legacy fallback)
      4. full project source walk

    Wiki-only monitored file lists never become the sole map set.
    """
    try:
        root_res = Path(root).resolve()
    except Exception:
        root_res = Path(root)
    root = root_res

    excludes, exclude_globs = _load_excludes(root)
    root_norm = os.path.realpath(str(root))

    walk_roots = _resolve_map_walk_roots(
        root, directory, use_monitored=use_monitored, use_map_paths=use_map_paths
    )

    seen: Set[str] = set()
    candidates: List[Path] = []

    def ok_file(p: Path) -> bool:
        if p.suffix.lower() not in SOURCE_EXTS:
            return False
        try:
            key = os.path.realpath(str(p))
        except Exception:
            key = os.path.normpath(str(p))
        if key in seen:
            return False
        if not (key == root_norm or key.startswith(root_norm + os.sep)):
            return False
        # Only check relative path parts within project, not absolute path
        try:
            relp = os.path.relpath(key, root_norm)
            for part in Path(relp).parts:
                if part in excludes:
                    return False
        except Exception:
            # Fallback: check file's parent directory names only
            pass
        if exclude_globs:
            name = p.name
            try:
                relp = os.path.relpath(key, root_norm)
            except Exception:
                relp = name
            if any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(relp, g) for g in exclude_globs):
                return False
        seen.add(key)
        return True

    def add_file(p: Path) -> None:
        if ok_file(p):
            candidates.append(p)

    def scandir_walk(d: Path) -> None:
        try:
            with os.scandir(d) as it:
                for entry in it:
                    try:
                        name = entry.name
                        if entry.is_dir(follow_symlinks=False):
                            if name in excludes or name.startswith("."):
                                continue
                            scandir_walk(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            add_file(Path(entry.path))
                    except Exception:
                        continue
        except Exception:
            pass

    git_available = (root / ".git").exists() or (root / ".git" / "HEAD").exists()

    for walk_root in walk_roots:
        used_git = False
        if git_available:
            try:
                try:
                    rel_scope = os.path.relpath(str(walk_root), str(root))
                except Exception:
                    rel_scope = "."
                git_cmd = [
                    "git", "ls-files", "--cached", "--others",
                    "--exclude-standard", "-z",
                ]
                if rel_scope not in (".", ""):
                    git_cmd.extend(["--", rel_scope.rstrip("/") + "/"])
                out = subprocess.check_output(
                    git_cmd, cwd=str(root), stderr=subprocess.DEVNULL
                )
                for entry in out.split(b"\0"):
                    if not entry:
                        continue
                    rel = entry.decode("utf-8", "ignore")
                    add_file(root / rel)
                used_git = True
            except Exception:
                used_git = False
        if not used_git:
            scandir_walk(walk_root)

    return candidates


def _live_source_count(
    root: Path,
    directory: Optional[str] = None,
    scope: Optional[MapScope] = None,
) -> Optional[int]:
    """Count source files under the *same* roots as collect (map_paths-aware).

    Must match ``collect_candidate_source_files`` scope precedence so a
    map_paths subset is not compared to a full-tree live count (that caused
    permanent re-list thrash when outside sources exist).

    Git pathspec preferred; no Path.resolve per file. Returns None if count
    cannot be obtained (caller should not reuse).
    """
    if scope is None:
        scope = resolve_map_scope(root, directory)
    root = scope.root
    excludes, _globs = _load_excludes(root)
    walk_roots = list(scope.walk_roots)

    def _count_git(pathspec: Optional[str]) -> Optional[int]:
        if not ((root / ".git").exists() or (root / ".git" / "HEAD").exists()):
            return None
        try:
            cmd = [
                "git", "ls-files", "--cached", "--others",
                "--exclude-standard", "-z",
            ]
            if pathspec:
                cmd.extend(["--", pathspec.rstrip("/") + "/"])
            out = subprocess.check_output(cmd, cwd=str(root), stderr=subprocess.DEVNULL)
        except Exception:
            return None
        cnt = 0
        for entry in out.split(b"\0"):
            if not entry:
                continue
            rel = entry.decode("utf-8", "ignore")
            low = rel.lower()
            if not any(low.endswith(ext) for ext in SOURCE_EXTS):
                continue
            parts = Path(rel).parts
            if any(part in excludes for part in parts):
                continue
            cnt += 1
        return cnt

    def _count_walk(walk: Path) -> int:
        cnt = 0
        for dirpath, dirnames, filenames in os.walk(str(walk)):
            dirnames[:] = [
                x for x in dirnames
                if x not in excludes and not x.startswith(".")
            ]
            for fn in filenames:
                if Path(fn).suffix.lower() in SOURCE_EXTS:
                    cnt += 1
        return cnt

    total = 0
    used_git = False
    for walk_root in walk_roots:
        try:
            rel_scope = os.path.relpath(str(walk_root), str(root))
        except Exception:
            rel_scope = "."
        if rel_scope in (".", ""):
            c = _count_git(None)
        else:
            c = _count_git(rel_scope)
        if c is not None:
            total += c
            used_git = True
        else:
            total += _count_walk(walk_root)
    # When multiple map_paths roots are counted via git with pathspecs, sums are
    # correct; full-root git once is used only when walk_roots == [root].
    if used_git and len(walk_roots) == 1 and walk_roots[0] == root:
        # single full-tree git already exact
        return total
    return total


def evaluate_candidate_reuse(
    blob: Dict[str, Any],
    *,
    fingerprint: str,
    directory: Optional[str],
    scoped_index_keys: Optional[Set[str]],
    live_count: Optional[int],
) -> Optional[List[str]]:
    """Pure reuse decision: return blob rels if safe, else None.

    No filesystem I/O. Callers supply fingerprint, map-scoped index keys, and
    live source count. Invalidates when:
      - missing/empty blob or directory mismatch
      - fingerprint mismatch
      - scoped index larger than blob / not subset / same-count different keys
      - live_count is None or ≠ stored count

    Empty ``scoped_index_keys`` (empty set) is treated as no index (live count
    still required). Pass ``None`` when index was not loaded.
    """
    if not isinstance(blob, dict):
        return None
    if (blob.get("directory") or None) != (directory or None):
        return None
    rels = blob.get("rels")
    if not isinstance(rels, list) or not rels:
        return None
    stored_count = int(blob.get("count") or len(rels))
    if stored_count != len(rels):
        return None
    if blob.get("fp") != fingerprint:
        return None

    blob_set = {r for r in rels if isinstance(r, str) and r}
    if not blob_set:
        return None

    # Empty set → treat as no index (same as None)
    keys = scoped_index_keys
    if keys is not None and len(keys) == 0:
        keys = None

    if keys is not None:
        # Index larger than blob or keys not in blob → poison / incomplete blob
        if len(keys) > stored_count or not keys.issubset(blob_set):
            return None
        # Same-count different keys → re-list
        if len(keys) == stored_count and keys != blob_set:
            return None
        # True set agreement or partial subset: still require live count below

    if live_count is None or live_count != stored_count:
        return None
    return [r for r in rels if isinstance(r, str) and r]


def try_cached_candidate_rels(
    meta: Dict[str, Any],
    root: Path,
    directory: Optional[str],
    index: Optional[Dict[str, Any]] = None,
    scope: Optional[MapScope] = None,
) -> Optional[List[Path]]:
    """Reuse stored candidate rel list only when safe (index-first preferred).

    Builds MapScope, filters index to map scope (not full tree when map_paths),
    then delegates to pure ``evaluate_candidate_reuse``.
    """
    blob = meta.get("_candidate_list") if isinstance(meta, dict) else None
    if not isinstance(blob, dict):
        return None
    if scope is None:
        scope = resolve_map_scope(root, directory)
    root = scope.root
    fp = scope_fingerprint(root, directory)

    # Empty index → same as None
    if index is not None and len(index) == 0:
        index = None

    scoped_keys: Optional[Set[str]] = None
    if index is not None:
        scoped = filter_index_to_map_scope(index, scope)
        scoped_keys = set(scoped.keys()) if scoped else set()

    live = _live_source_count(root, directory, scope=scope)
    rels = evaluate_candidate_reuse(
        blob,
        fingerprint=fp,
        directory=directory,
        scoped_index_keys=scoped_keys,
        live_count=live,
    )
    if rels is None:
        return None
    return [root / r for r in rels]


def resolve_candidates(
    root: Path,
    directory: Optional[str] = None,
    *,
    force_full: bool = False,
    index: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Peelable collect stage: candidates + reuse/index-first flags.

    Re-lists only when fingerprint/count/index disagree with the cached set.
    """
    root = Path(root)
    scope = resolve_map_scope(root, directory)
    fp = scope_fingerprint(scope.root, directory)
    out: Dict[str, Any] = {
        "paths": [],
        "reused": False,
        "index_first": False,
        "relisted": False,
        "fingerprint": fp,
        "reason": "",
        "map_scope_full_tree": scope.is_full_tree,
        "map_scope_prefixes": list(scope.rel_prefixes),
    }
    if not force_full and meta is not None:
        # Normalize empty index → None for live-count path
        idx = index if index else None
        cached = try_cached_candidate_rels(
            meta, scope.root, directory, index=idx, scope=scope
        )
        if cached is not None:
            out["paths"] = cached
            out["reused"] = True
            # Non-empty index was present (map-scoped filter may still leave keys)
            out["index_first"] = bool(idx)
            out["reason"] = "fingerprint_and_live_count_agree"
            return out
    paths = collect_candidate_source_files(scope.root, directory=directory)
    out["paths"] = paths
    out["relisted"] = True
    out["reason"] = "force_full_or_disagreement"
    return out


def candidate_list_meta(
    root: Path,
    directory: Optional[str],
    paths: List[Path],
) -> Dict[str, Any]:
    root = Path(root)
    try:
        root = root.resolve()
    except Exception:
        pass
    rels: List[str] = []
    for p in paths:
        try:
            rels.append(str(Path(p).resolve().relative_to(root)))
        except Exception:
            try:
                rels.append(os.path.relpath(str(p), str(root)))
            except Exception:
                continue
    return {
        "fp": scope_fingerprint(root, directory),
        "directory": directory,
        "count": len(rels),
        "rels": rels,
    }
