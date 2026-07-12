"""Scoped source candidate collection (agent warm-path walk cliff).

AGENT MAP:
  collect_candidate_source_files(root, directory=None) → List[Path]
  try_cached_candidate_rels / candidate_list_meta

Map collection rules (critical):
  - ``monitored_paths.txt`` is the *wiki health* surface (often individual .md files).
    It is NOT the sole map walk set. Only **directory** entries that look like package
    roots are used; wiki-only file lists fall back to full/package tree walk.
  - ``--directory=`` always wins for map scope.
  - Candidate-list reuse requires git porcelain clean under scope (new nested files
    invalidate). Walk-root mtime alone is insufficient.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
    ".pnp.cjs", ".wikifier_staging", "venv", ".venv", "env",
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


def _read_monitored_paths(root: Path) -> List[str]:
    mp = root / "monitored_paths.txt"
    if not mp.is_file():
        return []
    out: List[str] = []
    try:
        for line in mp.read_text(encoding="utf-8", errors="ignore").splitlines():
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


def _map_walk_roots_from_monitored(root: Path) -> List[Path]:
    """Return directory roots suitable for *map* collection from monitored_paths.

    Wiki-oriented lists (skills/run.md, README.md, …) must not become the only
    candidates — that collapses the import graph to a single file.
    """
    dirs: List[Path] = []
    for mp in _read_monitored_paths(root):
        p = Path(mp) if os.path.isabs(mp) else (root / mp)
        if p.is_dir():
            dirs.append(p)
        # Individual source files under a package are OK as extras but not sole roots
        # (handled separately only when we also have directory roots)
    return dirs


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


def collect_candidate_source_files(
    root: Path,
    directory: Optional[str] = None,
    *,
    use_monitored: bool = True,
) -> List[Path]:
    """Collect source files under root, scoped to directory or safe monitored dirs.

    When ``directory`` is None and monitored_paths has only wiki/doc files (not
    package directories), falls back to a full project source walk — never a
    one-file graph.
    """
    try:
        root_res = Path(root).resolve()
    except Exception:
        root_res = Path(root)
    root = root_res

    excludes, exclude_globs = _load_excludes(root)
    root_norm = os.path.realpath(str(root))

    walk_roots: List[Path] = []
    if directory:
        d = root / directory
        walk_roots = [d if d.is_dir() else root]
    elif use_monitored:
        walk_roots = _map_walk_roots_from_monitored(root)
        if not walk_roots:
            # Wiki-file monitored_paths only → map the whole package tree
            walk_roots = [root]
    else:
        walk_roots = [root]

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
        for part in Path(key).parts:
            if part in excludes:
                return False
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


def _live_source_count(root: Path, directory: Optional[str] = None) -> Optional[int]:
    """Count source files under scope (git pathspec preferred; no Path.resolve per file).

    Used to sanity-check cached candidate lists against reality. Returns None if
    count cannot be obtained (caller should not reuse).
    """
    root = Path(root)
    try:
        root = root.resolve()
    except Exception:
        pass
    excludes, _globs = _load_excludes(root)
    n = 0

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
            # skip excluded path segments
            parts = Path(rel).parts
            if any(part in excludes for part in parts):
                continue
            cnt += 1
        return cnt

    if directory:
        d = root / directory
        if not d.is_dir():
            return 0
        c = _count_git(directory)
        if c is not None:
            return c
        # scandir count fallback
        cnt = 0
        for dirpath, dirnames, filenames in os.walk(str(d)):
            dirnames[:] = [
                x for x in dirnames
                if x not in excludes and not x.startswith(".")
            ]
            for fn in filenames:
                if Path(fn).suffix.lower() in SOURCE_EXTS:
                    cnt += 1
        return cnt

    # Unscoped: full tree source count via git
    c = _count_git(None)
    if c is not None:
        return c
    cnt = 0
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [
            x for x in dirnames
            if x not in excludes and not x.startswith(".")
        ]
        for fn in filenames:
            if Path(fn).suffix.lower() in SOURCE_EXTS:
                cnt += 1
    return cnt


def try_cached_candidate_rels(
    meta: Dict[str, Any],
    root: Path,
    directory: Optional[str],
) -> Optional[List[Path]]:
    """Reuse stored candidate rel list only when safe.

    Invalidates when:
      - missing/empty blob or directory mismatch
      - scope_fingerprint mismatch (max dir mtime under walk — nested creates)
      - **live source count ≠ stored count** (poisoned 1-file blob vs real tree)
    """
    blob = meta.get("_candidate_list") if isinstance(meta, dict) else None
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
    fp = scope_fingerprint(root, directory)
    if blob.get("fp") != fp:
        return None
    # Mandatory sanity: poisoned caches can share fp after partial wipes
    live = _live_source_count(root, directory)
    if live is None or live != stored_count:
        return None
    root = Path(root)
    return [root / r for r in rels if isinstance(r, str) and r]


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
