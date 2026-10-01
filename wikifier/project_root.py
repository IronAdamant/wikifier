"""
Canonical project-root discovery (load-time safe).

AGENT MAP:
  discover_project_root() — env → markers → cwd (no imports of cli/import_cache/bree)
  Used by cli (re-export), import_cache, bree, daemon, serve, mcp
  Extracted so bree/import_cache never import cli (breaks cyclic SCC).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

# Filesystem/OS failures on arbitrary user trees (never programming errors).
_FS_ERRORS = (OSError, ValueError, RuntimeError)


def discover_project_root() -> Path:
    """The target project root for CLI, MCP, daemon and library use.

    1. ``WIKIFIER_PROJECT_ROOT`` when it names an existing directory
       (strict callers use :func:`wikifier.paths.resolve_root`, which errors instead).
    2. Otherwise walk up from the logical cwd (``$PWD``), the physical cwd and their
       realpaths, collecting directories with Wikifier markers (``.wikifier/``,
       ``monitored_paths.txt``) or project markers (``.git``, ``package.json``,
       ``pyproject.toml``, lockfiles, workspace configs, …). Paths inside
       ``node_modules`` package stores are never candidates.
    3. Pick the outermost candidate, preferring one with ``.git`` — the true
       monorepo root even when sub-packages carry their own ``package.json``.
    4. Fall back to the current directory.
    """
    # 1. Explicit env var
    env_root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    # logical cwd (PWD/OLDPWD) + physical + realpath fallbacks for symlink/pnpm/yarn/nested
    cwd = Path.cwd()
    logical_cwd_str = os.environ.get("PWD") or os.environ.get("OLDPWD") or str(cwd)
    try:
        logical_cwd = Path(logical_cwd_str).expanduser()
    except _FS_ERRORS:
        logical_cwd = cwd

    start_points: List[Path] = []
    for start in (logical_cwd, cwd, cwd.resolve()):
        if start and start not in start_points:
            start_points.append(start)

    # realpath variants for deeper symlink nest robustness (e.g. git submodules + pnpm links)
    for sp in list(start_points):
        try:
            rp = Path(os.path.realpath(str(sp)))
            if rp not in start_points:
                start_points.append(rp)
        except _FS_ERRORS:
            continue

    # 2/3. Markers: wikifier-specific + expanded common monorepo
    common_markers = [
        ".git", "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "go.mod", ".hg",
        # monorepo root indicators (for workspace/subpkg layouts + yarn/pnpm detection)
        "pnpm-lock.yaml", "yarn.lock", "lerna.json", "nx.json", "turbo.json",
        "rush.json", "workspace.json", "pnpm-workspace.yaml", ".yarnrc.yml"
    ]
    store_indicators = (".pnpm", ".yarn", ".pnp", ".pnp.cjs", "virtual-store", ".store")

    candidates: List[Path] = []
    for start in start_points:
        try:
            parent_chain = [start] + list(start.parents)
        except _FS_ERRORS:
            parent_chain = [start]

        # Wikifier markers (post-init)
        for parent in parent_chain:
            try:
                pstr = str(parent)
                if any(ind in pstr for ind in store_indicators) and "node_modules" in pstr:
                    continue  # never treat deep pnpm/yarn store paths as project root
                if ((parent / ".wikifier").is_dir() or
                        (parent / "monitored_paths.txt").exists() or
                        (parent / ".wikifier/config").exists()):
                    if parent not in candidates:
                        candidates.append(parent)
            except _FS_ERRORS:
                continue

        # Common + monorepo markers (any-scale external)
        for parent in parent_chain:
            try:
                pstr = str(parent)
                if any(ind in pstr for ind in store_indicators) and "node_modules" in pstr:
                    continue
                for marker in common_markers:
                    if (parent / marker).exists():
                        if parent not in candidates:
                            candidates.append(parent)
            except _FS_ERRORS:
                continue

    if candidates:
        # pick outermost/shallowest, with strong preference for .git (true monorepo root)
        # even if a deeper packages/*/package.json also matches. Solves workspace subdir case.
        def _root_key(p: Path):
            try:
                rp = p.resolve()
                has_git = (rp / ".git").exists() or (rp / ".git").is_file()  # worktree support
                depth = len(rp.parts)
                return (0 if has_git else 1, depth, str(rp))
            except _FS_ERRORS:
                return (99, 99999, str(p))

        best = min(candidates, key=_root_key)
        try:
            return best.resolve() if best.exists() else best
        except _FS_ERRORS:
            return best

    # 4. Last-resort sensible default: the directory the user is running from.
    #    This is the key robustness fix vs. old "fall back to package dir".
    #    Prefer resolved for the final fallback.
    try:
        return cwd.resolve()
    except _FS_ERRORS:
        return cwd
