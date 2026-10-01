"""
What changed, according to git — the input for ``record_changes``.

Reads ``git diff --name-status`` against a base ref (default ``HEAD``: staged
and unstaged work) plus untracked files, limited to and relative to the project
root (which may be a subdirectory of the repository). git is an optional
external tool, not a Python dependency: without it, callers get
``GitUnavailableError`` and fall back to per-file ``record_change``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

# git's well-known empty tree: the base for a repository with no commits yet.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

_STATUS = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "C": "copied", "T": "modified"}


class GitUnavailableError(RuntimeError):
    """git is not installed, or the project is not inside a git work tree."""


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
        )
    except FileNotFoundError as exc:
        raise GitUnavailableError("git is not installed; record changes per file with record_change") from exc
    if proc.returncode != 0:
        raise GitUnavailableError(proc.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
    return proc.stdout.decode("utf-8", "surrogateescape")


def _resolve_base(root: Path, since: Optional[str]) -> str:
    ref = since or "HEAD"
    try:
        return _git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}").strip()
    except GitUnavailableError:
        if since:
            raise GitUnavailableError(f"unknown git ref: {since}") from None
        return EMPTY_TREE  # no commits yet: everything is new


def changed_files(root: Path, since: Optional[str] = None) -> Dict[str, object]:
    """Files changed under ``root`` since ``since`` (default HEAD), plus untracked files.

    Returns ``{"base": sha, "changes": [{"path", "status", "old_path"?}]}`` with
    project-relative POSIX paths. ``status`` is added | modified | deleted |
    renamed | copied | untracked.
    """
    root = Path(root)
    _git(root, "rev-parse", "--is-inside-work-tree")
    base = _resolve_base(root, since)
    changes: List[Dict[str, str]] = []
    tokens = _git(root, "diff", "--name-status", "-z", "-M", "--relative", base, "--").split("\0")
    i = 0
    while i < len(tokens) and tokens[i]:
        code = tokens[i][0]
        if code in ("R", "C"):
            old, new = tokens[i + 1], tokens[i + 2]
            changes.append({"path": new, "status": _STATUS[code], "old_path": old})
            i += 3
        else:
            changes.append({"path": tokens[i + 1], "status": _STATUS.get(code, "modified")})
            i += 2
    for path in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if path:
            changes.append({"path": path, "status": "untracked"})
    return {"base": base, "changes": changes}


__all__ = ["EMPTY_TREE", "GitUnavailableError", "changed_files"]
