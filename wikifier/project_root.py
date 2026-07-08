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


def discover_project_root() -> Path:
    """
    Unified discovery helper for the *target project root* (user codebase / monorepo).

    This is the canonical implementation for CLI, MCP, direct Python use, and
    is mirrored (same priority + markers) by the shell script's discover_project_root().

    Highest-leverage fix for External / Packaged Full-Update Robustness (Gap #1):
    Makes `pip install wikifier` + `wikifier ...` (or direct packaged sh) reliable
    from any external monorepo cwd without requiring manual WIKIFIER_PROJECT_ROOT
    or --target on every invocation. Zero-dependency.

    Wave 3 hardening (symlinks + pnpm/yarn stores):
    - Consults $PWD (and $OLDPWD) logical cwd in addition to Path.cwd() / .resolve().
    - Walks parent chains from *logical* start points first; this ensures that when
      cwd is deep inside a pnpm symlinked store layout (e.g. monorepo/node_modules/.pnpm/pkg@1/.../pkg
      whose physical target is /global-store/...), the logical ancestor chain still reaches
      the real project root markers (.git, package.json etc.) outside the store.
    - Falls back to resolved physical; returns the outermost marker root found.
    - Prevents packaged/parser/daemon from accidentally using a store dir as PROJECT_ROOT.

    Wave 4 further hardening for complex monorepo layouts:
    - Collects *all* candidate marker roots across logical/physical/realpath chains (no early return).
    - Selects the outermost (shallowest fs path) preferring .git roots, then lockfiles (pnpm/yarn), then other.
      This correctly picks true monorepo root even when deep sub-packages have their own package.json / yarn workspaces.
    - Expanded common markers: pnpm-lock.yaml, yarn.lock, lerna.json, nx.json, turbo.json, rush.json, workspace yamls.
    - Explicit skipping of node_modules/.pnpm / .yarn / .pnp internals as candidate roots (even on logical paths).
    - Additional os.path.realpath chains for nested/broken symlink monorepo layouts.
    - Daemon, parsers (via _get_*_fallback), run_full_update all inherit automatically.
    """
    # 1. Explicit env var (highest priority, supports all the R6 --target flows)
    env_root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    # Wave 3/4: logical cwd (PWD/OLDPWD) + physical + realpath fallbacks for symlink/pnpm/yarn/nested
    cwd = Path.cwd()
    logical_cwd_str = os.environ.get("PWD") or os.environ.get("OLDPWD") or str(cwd)
    try:
        logical_cwd = Path(logical_cwd_str).expanduser()
    except Exception:
        logical_cwd = cwd

    start_points: List[Path] = []
    for start in (logical_cwd, cwd, cwd.resolve()):
        if start and start not in start_points:
            start_points.append(start)

    # Wave 4: realpath variants for deeper symlink nest robustness (e.g. git submodules + pnpm links)
    for sp in list(start_points):
        try:
            rp = Path(os.path.realpath(str(sp)))
            if rp not in start_points:
                start_points.append(rp)
        except Exception:
            continue

    # 2/3. Markers: wikifier-specific + expanded common monorepo (Wave 4)
    common_markers = [
        ".git", "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "go.mod", ".hg",
        # Wave 4 monorepo root indicators (for workspace/subpkg layouts + yarn/pnpm detection)
        "pnpm-lock.yaml", "yarn.lock", "lerna.json", "nx.json", "turbo.json",
        "rush.json", "workspace.json", "pnpm-workspace.yaml", ".yarnrc.yml"
    ]
    store_indicators = (".pnpm", ".yarn", ".pnp", ".pnp.cjs", "virtual-store", ".store")

    candidates: List[Path] = []
    for start in start_points:
        try:
            parent_chain = [start] + list(start.parents)
        except Exception:
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
            except Exception:
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
            except Exception:
                continue

    if candidates:
        # Wave 4: pick outermost/shallowest, with strong preference for .git (true monorepo root)
        # even if a deeper packages/*/package.json also matches. Solves workspace subdir case.
        def _root_key(p: Path):
            try:
                rp = p.resolve()
                has_git = (rp / ".git").exists() or (rp / ".git").is_file()  # worktree support
                depth = len(rp.parts)
                return (0 if has_git else 1, depth, str(rp))
            except Exception:
                return (99, 99999, str(p))

        best = min(candidates, key=_root_key)
        try:
            return best.resolve() if best.exists() else best
        except Exception:
            return best

    # 4. Last-resort sensible default: the directory the user is running from.
    #    This is the key robustness fix vs. old "fall back to package dir".
    #    Prefer resolved for the final fallback.
    try:
        return cwd.resolve()
    except Exception:
        return cwd
