"""Sharded names-only agent catalog (folder cards + hops).

AGENT MAP:
  ensure_map_index(root, cache)   — batch-write folder shards after persist
  bootstrap_map_index(root)       — root card only (depth-1)
  list_paths(root, prefix, depth) — one folder card (default depth=1)
  load_folder_card(root, prefix)  — read one shard

Each directory is a small map of *immediate* children. Child folders link
via list_paths; files link via prepare_edit (import-cache edges). Not a
second crawl, no wiki, no mermaid. Shards live under .wikifier_staging/maps/
and rewrite only when that folder's child set (names + child counts) changes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

MAP_INDEX_VERSION = 2
STAGING_DIRNAME = ".wikifier_staging"
MAPS_DIRNAME = "maps"
ROOT_SHARD_NAME = "_root.json"
DIR_SHARD_NAME = "_index.json"
# Cap immediate files on one fat folder card (not a whole-tree dump).
BOOTSTRAP_MAP_INDEX_FILE_BUDGET = 80
HOP = {"dirs": "list_paths", "files": "prepare_edit"}


def maps_dir(root: Union[str, Path]) -> Path:
    return Path(root) / STAGING_DIRNAME / MAPS_DIRNAME


def map_index_path(root: Union[str, Path]) -> Path:
    """Root folder card (replaces the old single dump)."""
    return maps_dir(root) / ROOT_SHARD_NAME


def _posix(rel: str) -> str:
    return str(rel).replace("\\", "/").lstrip("./")


def _normalize_prefix(prefix: Optional[str]) -> str:
    if not prefix:
        return ""
    p = _posix(str(prefix).strip())
    if p in (".", "/"):
        return ""
    return p


def _dir_key(prefix: str) -> str:
    """Canonical directory key: '' for root, else 'pkg/'."""
    p = _normalize_prefix(prefix)
    if not p:
        return ""
    if p.endswith("/"):
        return p
    return p + "/"


def shard_path(root: Union[str, Path], prefix: Optional[str] = None) -> Path:
    key = _dir_key(prefix or "")
    base = maps_dir(root)
    if not key:
        return base / ROOT_SHARD_NAME
    return base / key / DIR_SHARD_NAME


def mapped_files_from_cache(cache: Dict[str, Any]) -> List[str]:
    """Project-relative mapped source paths (import-cache keys, no reserved)."""
    files: List[str] = []
    if not isinstance(cache, dict):
        return files
    for k in cache:
        if not isinstance(k, str) or not k or k.startswith("_"):
            continue
        path = _posix(k)
        if not path or "\n" in path or path.startswith("_"):
            continue
        files.append(path)
    files.sort()
    return files


def mapped_files_from_root(
    root: Union[str, Path],
    cache: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Prefer cache keys; else SQLite file index (no pair payloads)."""
    if cache:
        files = mapped_files_from_cache(cache)
        if files:
            return files
    try:
        from . import cache_store as cs
        idx = cs.load_mtime_index(Path(root)) or {}
        out = sorted(
            _posix(k)
            for k in idx
            if isinstance(k, str) and k and not k.startswith("_") and "\n" not in k
        )
        if out:
            return out
    except Exception:
        pass
    return mapped_files_from_cache(_load_cache(Path(root)))


def dirs_from_files(files: List[str]) -> List[Dict[str, Any]]:
    """All ancestor directories + recursive file counts (compat helper)."""
    counts: Dict[str, int] = {}
    for path in files:
        parts = path.split("/")
        if len(parts) < 2:
            continue
        acc: List[str] = []
        for part in parts[:-1]:
            if not part or part == ".":
                continue
            acc.append(part)
            d = "/".join(acc) + "/"
            counts[d] = counts.get(d, 0) + 1
    return [{"p": p, "n": counts[p]} for p in sorted(counts)]


def build_map_index(cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compat full snapshot (tests / recursive list_paths). Not written as one dump."""
    files = mapped_files_from_cache(cache or {})
    return {
        "v": MAP_INDEX_VERSION,
        "file_count": len(files),
        "dirs": dirs_from_files(files),
        "files": files,
    }


def _load_cache(root: Path) -> Dict[str, Any]:
    try:
        from . import import_cache as ic
        cache = ic.load_cache(root) or {}
        return cache if isinstance(cache, dict) else {}
    except Exception:
        return {}


def build_folder_cards(files: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """dir_key -> {n, files (immediate), child_dirs}."""
    cards: Dict[str, Dict[str, Any]] = {}

    def ensure(key: str) -> Dict[str, Any]:
        slot = cards.get(key)
        if slot is None:
            slot = {"n": 0, "files": [], "child_dirs": set()}
            cards[key] = slot
        return slot

    ensure("")
    for raw in files:
        path = _posix(raw)
        if not path:
            continue
        parts = [p for p in path.split("/") if p and p != "."]
        if not parts:
            continue
        ensure("")["n"] += 1
        acc: List[str] = []
        parent = ""
        for part in parts[:-1]:
            acc.append(part)
            d = "/".join(acc) + "/"
            ensure(d)["n"] += 1
            ensure(parent)["child_dirs"].add(d)
            parent = d
        ensure(parent)["files"].append("/".join(parts))
    for slot in cards.values():
        slot["files"] = sorted(set(slot["files"]))
        slot["child_dirs"] = sorted(slot["child_dirs"])
    return cards


def _child_sig(immediate_files: List[str], dirs: List[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for f in immediate_files:
        h.update(b"f:")
        h.update(f.encode("utf-8"))
        h.update(b"\n")
    for d in dirs:
        h.update(b"d:")
        h.update(str(d.get("p") or "").encode("utf-8"))
        h.update(b":")
        h.update(str(d.get("n") or 0).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()[:16]


def _dir_entries(card: Dict[str, Any], cards: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for child in card.get("child_dirs") or []:
        n = int((cards.get(child) or {}).get("n") or 0)
        out.append({
            "p": child,
            "n": n,
            "list_paths": child.rstrip("/"),
        })
    return out


def folder_card_payload(
    dir_key: str,
    card: Dict[str, Any],
    cards: Dict[str, Dict[str, Any]],
    file_budget: Optional[int] = None,
) -> Dict[str, Any]:
    files = list(card.get("files") or [])
    dirs = _dir_entries(card, cards)
    budget = BOOTSTRAP_MAP_INDEX_FILE_BUDGET if file_budget is None else max(0, int(file_budget))
    truncated = len(files) > budget
    shown = files if not truncated else files[:budget]
    return {
        "v": MAP_INDEX_VERSION,
        "kind": "root" if not dir_key else "folder",
        "p": dir_key or ".",
        "depth": 1,
        "file_count": int(card.get("n") or 0),
        "dirs": dirs,
        "files": shown,
        "files_complete": not truncated,
        "files_truncated": truncated,
        "files_budget": budget,
        "sig": _child_sig(files, dirs),
        "hop": dict(HOP),
    }


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _existing_sig(path: Path) -> Optional[str]:
    data = _read_json(path)
    if not data:
        return None
    sig = data.get("sig")
    return str(sig) if sig else None


def write_map_index(
    root: Union[str, Path],
    cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Batch-write depth-1 folder shards. Skip a shard when its child-set sig matches."""
    root_p = Path(root)
    out_path = map_index_path(root_p)
    result: Dict[str, Any] = {
        "success": False,
        "path": str(out_path),
        "file_count": 0,
        "dir_count": 0,
        "shards_written": 0,
        "shards_skipped": 0,
        "shards_pruned": 0,
    }
    try:
        files = mapped_files_from_root(root_p, cache)
        cards = build_folder_cards(files)
        maps = maps_dir(root_p)
        maps.mkdir(parents=True, exist_ok=True)
        keep_paths = set()
        written = 0
        skipped = 0
        for key, card in cards.items():
            payload = folder_card_payload(key, card, cards)
            dest = shard_path(root_p, key)
            keep_paths.add(dest.resolve())
            if _existing_sig(dest) == payload.get("sig"):
                skipped += 1
                continue
            _atomic_write_json(dest, payload)
            written += 1
        pruned = 0
        if maps.is_dir():
            for p in [maps / ROOT_SHARD_NAME, *maps.rglob(DIR_SHARD_NAME)]:
                if not p.is_file():
                    continue
                if p.resolve() not in keep_paths:
                    try:
                        p.unlink()
                        pruned += 1
                    except Exception:
                        pass
        result.update({
            "success": True,
            "file_count": int((cards.get("") or {}).get("n") or 0),
            "dir_count": len(cards),
            "shards_written": written,
            "shards_skipped": skipped,
            "shards_pruned": pruned,
            "skipped": False,
        })
    except Exception as exc:
        result["error"] = "{0}: {1}".format(type(exc).__name__, exc)
    return result


def ensure_map_index(
    root: Union[str, Path],
    cache: Optional[Dict[str, Any]] = None,
    reuse_if_present: bool = False,
) -> Dict[str, Any]:
    """Write shards, or reuse the existing root card on zero-dirty warm maps."""
    root_p = Path(root)
    path = map_index_path(root_p)
    if reuse_if_present and path.is_file():
        return {
            "success": True,
            "path": str(path),
            "skipped": True,
            "reason": "zero_dirty_reuse",
        }
    return write_map_index(root_p, cache)


def load_folder_card(
    root: Union[str, Path],
    prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Load one folder card from disk, or build it from the cache index."""
    root_p = Path(root)
    key = _dir_key(prefix or "")
    path = shard_path(root_p, key)
    data = _read_json(path)
    if data and isinstance(data.get("files"), list):
        data["success"] = True
        data["path"] = str(path)
        data.setdefault("hop", dict(HOP))
        data.setdefault("v", MAP_INDEX_VERSION)
        return data
    files = mapped_files_from_root(root_p)
    if not files:
        return {
            "success": False,
            "error": "no map_index — run update_maps",
            "p": key or ".",
            "dirs": [],
            "files": [],
            "file_count": 0,
            "hop": dict(HOP),
            "path": str(path),
        }
    cards = build_folder_cards(files)
    card = cards.get(key)
    if card is None:
        # prefix might be an exact file
        return {
            "success": True,
            "kind": "file",
            "p": _normalize_prefix(prefix or ""),
            "dirs": [],
            "files": [_normalize_prefix(prefix)] if _normalize_prefix(prefix) in files else [],
            "file_count": 1 if _normalize_prefix(prefix) in files else 0,
            "files_complete": True,
            "files_truncated": False,
            "hop": dict(HOP),
            "path": str(path),
            "v": MAP_INDEX_VERSION,
        }
    payload = folder_card_payload(key, card, cards)
    payload["success"] = True
    payload["path"] = str(path)
    return payload


def path_matches_prefix(path: str, prefix: str) -> bool:
    if not prefix:
        return True
    p = _posix(path)
    if prefix.endswith("/"):
        return p.startswith(prefix)
    return p == prefix or p.startswith(prefix + "/")


def _rel_depth(path: str, prefix: str) -> int:
    p = _posix(path).rstrip("/")
    pre = _dir_key(prefix) if prefix else ""
    if pre:
        if p == pre.rstrip("/"):
            return 0
        if not path_matches_prefix(p if not p.endswith("/") else p, pre.rstrip("/")):
            return -1
        rest = p[len(pre):] if p.startswith(pre) else p[len(pre.rstrip("/")):].lstrip("/")
    else:
        rest = p
    rest = rest.strip("/")
    if not rest:
        return 0
    return rest.count("/") + 1


def resolve_file_budget(explicit: Optional[int] = None) -> int:
    if explicit is not None:
        try:
            return max(0, int(explicit))
        except (TypeError, ValueError):
            return BOOTSTRAP_MAP_INDEX_FILE_BUDGET
    env = os.environ.get("WIKIFIER_BOOTSTRAP_MAP_FILES")
    if env:
        try:
            return max(0, int(env))
        except (TypeError, ValueError):
            pass
    return BOOTSTRAP_MAP_INDEX_FILE_BUDGET


def bootstrap_map_index(
    root: Union[str, Path],
    directory: Optional[str] = None,
    file_budget: Optional[int] = None,
) -> Dict[str, Any]:
    """Root (or scoped) folder card for session_bootstrap. Depth-1, never mermaid."""
    prefix = directory
    card = load_folder_card(root, prefix)
    budget = resolve_file_budget(file_budget)
    files = [f for f in (card.get("files") or []) if isinstance(f, str)]
    truncated = len(files) > budget
    shown = files if not truncated else files[:budget]
    out = {
        "v": MAP_INDEX_VERSION,
        "success": bool(card.get("success", True)) and "error" not in card,
        "kind": card.get("kind") or ("root" if not _dir_key(prefix or "") else "folder"),
        "p": card.get("p") or (_dir_key(prefix or "") or "."),
        "depth": 1,
        "file_count": int(card.get("file_count") or 0),
        "dirs": list(card.get("dirs") or []),
        "files": shown,
        "files_complete": (not truncated) and bool(card.get("files_complete", True)),
        "files_truncated": truncated or bool(card.get("files_truncated")),
        "files_budget": budget,
        "hop": dict(HOP),
        "path": card.get("path"),
    }
    if card.get("error") and not out["dirs"] and not files:
        out["success"] = False
        out["error"] = card.get("error")
    return out


def list_paths(
    root: Union[str, Path],
    prefix: Optional[str] = None,
    max_files: Optional[int] = None,
    depth: int = 1,
) -> Dict[str, Any]:
    """Names-only folder query. Default depth=1 (one card). depth=0 is recursive."""
    root_p = Path(root)
    pre = _normalize_prefix(prefix)
    try:
        depth_i = int(depth)
    except (TypeError, ValueError):
        depth_i = 1
    hop = dict(HOP)
    if depth_i == 1 or depth_i < 0:
        card = load_folder_card(root_p, pre)
        files = list(card.get("files") or [])
        dirs = list(card.get("dirs") or [])
        total = len(files)
        truncated = bool(card.get("files_truncated"))
        if max_files is not None:
            try:
                cap = max(0, int(max_files))
                if len(files) > cap:
                    files = files[:cap]
                    truncated = True
            except (TypeError, ValueError):
                pass
        success = bool(card.get("success", True))
        err = card.get("error")
        if err and not files and not dirs:
            success = False
        out: Dict[str, Any] = {
            "success": success,
            "project_root": str(root_p),
            "prefix": pre or None,
            "p": card.get("p") or (_dir_key(pre) or "."),
            "depth": 1,
            "file_count": int(card.get("file_count") or total),
            "dirs": dirs,
            "files": files,
            "files_complete": not truncated,
            "files_truncated": truncated,
            "hop": hop,
            "v": MAP_INDEX_VERSION,
        }
        if err and not success:
            out["error"] = err
        return out

    # Recursive (depth=0) or N-level expand from the file list.
    files_all = mapped_files_from_root(root_p)
    if not files_all:
        return {
            "success": False,
            "project_root": str(root_p),
            "prefix": pre or None,
            "file_count": 0,
            "dirs": [],
            "files": [],
            "files_complete": True,
            "files_truncated": False,
            "hop": hop,
            "depth": depth_i,
            "v": MAP_INDEX_VERSION,
            "error": "no map_index — run update_maps",
        }
    if pre:
        scoped = [f for f in files_all if path_matches_prefix(f, pre)]
    else:
        scoped = list(files_all)
    if depth_i > 1:
        scoped_files = [f for f in scoped if 0 < _rel_depth(f, pre) <= depth_i]
    else:
        scoped_files = list(scoped)
    cards = build_folder_cards(scoped if not pre else files_all)
    dirs: List[Dict[str, Any]] = []
    want_key = _dir_key(pre)
    for key, card in cards.items():
        if not key:
            continue
        if pre and not path_matches_prefix(key.rstrip("/"), pre.rstrip("/") if pre else ""):
            if key != want_key:
                continue
        dpt = _rel_depth(key, pre)
        if depth_i > 1 and not (0 < dpt <= depth_i):
            continue
        if depth_i == 0 or (depth_i > 1 and 0 < dpt <= depth_i) or key == want_key:
            if key == want_key:
                continue
            dirs.append({
                "p": key,
                "n": int(card.get("n") or 0),
                "list_paths": key.rstrip("/"),
            })
    dirs.sort(key=lambda d: str(d.get("p") or ""))
    total = len(scoped_files)
    truncated = False
    shown = scoped_files
    if max_files is not None:
        try:
            cap = max(0, int(max_files))
            if len(shown) > cap:
                shown = shown[:cap]
                truncated = True
        except (TypeError, ValueError):
            pass
    return {
        "success": True,
        "project_root": str(root_p),
        "prefix": pre or None,
        "depth": depth_i,
        "file_count": total,
        "dirs": dirs,
        "files": shown,
        "files_complete": not truncated,
        "files_truncated": truncated,
        "hop": hop,
        "v": MAP_INDEX_VERSION,
    }
