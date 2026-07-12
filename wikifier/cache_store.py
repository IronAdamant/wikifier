"""Stdlib SQLite import-cache store (agent warm-path; zero new deps).

AGENT MAP:
  load_cache_dict / save_cache_dict  — full cache dict (file entries + _meta keys)
  load_mtime_index                   — light {rel: mtime, content_hash} for dirty
  load_meta / save_meta_key          — reserved _keys without loading pairs
  update_file_index_rows             — mtime/hash refresh without full rewrite
  backend_name / has_sqlite

Dual-read: if ``import_cache.sqlite`` missing but legacy ``import_cache.json``
exists, load JSON and migrate on next save. Warm dirty detection should use
``load_mtime_index`` so agents avoid deserializing multi‑MB pair payloads.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

STAGING = ".wikifier_staging"
SQLITE_NAME = "import_cache.sqlite"
JSON_NAME = "import_cache.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  rel_path TEXT PRIMARY KEY NOT NULL,
  mtime INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT,
  payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL
);
"""


def sqlite_path(root: Path) -> Path:
    return Path(root) / STAGING / SQLITE_NAME


def json_path(root: Path) -> Path:
    return Path(root) / STAGING / JSON_NAME


def has_sqlite(root: Path) -> bool:
    try:
        return sqlite_path(root).is_file() and sqlite_path(root).stat().st_size > 0
    except Exception:
        return False


def backend_name(root: Path) -> str:
    if has_sqlite(root):
        return "sqlite"
    if json_path(root).is_file():
        return "json"
    return "none"


def _connect(root: Path) -> sqlite3.Connection:
    path = sqlite_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def _db(root: Path) -> Iterator[sqlite3.Connection]:
    conn = _connect(root)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def load_mtime_index(root: Path) -> Dict[str, Dict[str, Any]]:
    """Light index for dirty detection: rel → {mtime, content_hash}.

    Prefers SQLite. Falls back to scanning legacy JSON (expensive once).
    """
    root = Path(root)
    if has_sqlite(root):
        out: Dict[str, Dict[str, Any]] = {}
        try:
            with _db(root) as conn:
                for rel, mtime, chash in conn.execute(
                    "SELECT rel_path, mtime, content_hash FROM files"
                ):
                    out[str(rel)] = {
                        "mtime": int(mtime or 0),
                        "content_hash": chash,
                    }
            return out
        except Exception:
            pass
    # Legacy JSON fallback
    jp = json_path(root)
    if not jp.is_file():
        return {}
    try:
        with open(jp, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    out = {}
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        if not isinstance(k, str) or k.startswith("_") or not isinstance(v, dict):
            continue
        out[k] = {
            "mtime": int(v.get("mtime", 0) or 0),
            "content_hash": v.get("content_hash"),
        }
    return out


def load_meta(root: Path, keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Load reserved meta keys (``_acs_summary``, ``_cycles``, …) without file payloads."""
    root = Path(root)
    want = set(keys) if keys is not None else None
    if has_sqlite(root):
        try:
            with _db(root) as conn:
                rows = conn.execute("SELECT key, value FROM meta").fetchall()
            out: Dict[str, Any] = {}
            for k, raw in rows:
                if want is not None and k not in want:
                    continue
                try:
                    out[str(k)] = json.loads(raw)
                except Exception:
                    out[str(k)] = raw
            return out
        except Exception:
            pass
    # JSON fallback — still full parse (legacy only)
    jp = json_path(root)
    if not jp.is_file():
        return {}
    try:
        with open(jp, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k.startswith("_"):
            continue
        if want is not None and k not in want:
            continue
        out[k] = v
    return out


def load_cache_dict(root: Path) -> Dict[str, Any]:
    """Full cache dict: file entries + reserved keys (same shape as historical JSON)."""
    root = Path(root)
    if has_sqlite(root):
        try:
            cache: Dict[str, Any] = {}
            with _db(root) as conn:
                for rel, mtime, chash, payload in conn.execute(
                    "SELECT rel_path, mtime, content_hash, payload FROM files"
                ):
                    try:
                        ent = json.loads(payload) if payload else {}
                    except Exception:
                        ent = {}
                    if not isinstance(ent, dict):
                        ent = {}
                    ent["mtime"] = int(mtime or 0)
                    if chash:
                        ent["content_hash"] = chash
                    cache[str(rel)] = ent
                for k, raw in conn.execute("SELECT key, value FROM meta"):
                    try:
                        cache[str(k)] = json.loads(raw)
                    except Exception:
                        cache[str(k)] = raw
            return cache
        except Exception:
            pass
    jp = json_path(root)
    if not jp.is_file():
        return {}
    try:
        with open(jp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache_dict(root: Path, cache: Dict[str, Any], write_json: Optional[bool] = None) -> str:
    """Persist cache to SQLite (primary). Optionally dual-write compact JSON.

    ``write_json``: None → dual-write if env WIKIFIER_CACHE_JSON=1 or file count ≤ 400
    (keeps small projects greppable; avoids rewriting 20MB+ JSON on large monorepos).

    Returns backend name written: ``sqlite`` or ``sqlite+json``.
    """
    root = Path(root)
    if not isinstance(cache, dict):
        return "none"
    # Barrel preservation: merge missing barrel keys from existing store
    _BARREL = ("_barrel_resolutions", "_barrel_file_index")
    if any(k not in cache for k in _BARREL):
        try:
            prev = load_cache_dict(root)
            for k in _BARREL:
                if k not in cache and prev.get(k):
                    cache[k] = prev[k]
        except Exception:
            pass

    file_n = sum(
        1
        for k, v in cache.items()
        if isinstance(k, str) and not k.startswith("_") and isinstance(v, dict)
    )
    if write_json is None:
        env = os.environ.get("WIKIFIER_CACHE_JSON", "").strip().lower()
        if env in ("1", "true", "yes", "always"):
            write_json = True
        elif env in ("0", "false", "no", "never"):
            write_json = False
        else:
            write_json = file_n <= 400

    with _db(root) as conn:
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM meta")
        for k, v in cache.items():
            if not isinstance(k, str):
                continue
            if k.startswith("_"):
                try:
                    raw = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    raw = json.dumps(str(v))
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    (k, raw),
                )
            elif isinstance(v, dict):
                mtime = int(v.get("mtime", 0) or 0)
                chash = v.get("content_hash")
                try:
                    payload = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    payload = "{}"
                conn.execute(
                    "INSERT OR REPLACE INTO files(rel_path, mtime, content_hash, payload) "
                    "VALUES (?, ?, ?, ?)",
                    (k, mtime, chash, payload),
                )

    if write_json:
        jp = json_path(root)
        jp.parent.mkdir(parents=True, exist_ok=True)
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
        return "sqlite+json"
    # If dual-write disabled, leave legacy json in place for dual-read until removed;
    # do not delete automatically (safe migration).
    return "sqlite"


def update_file_index_rows(
    root: Path,
    rows: List[Tuple[str, int, Optional[str]]],
) -> int:
    """Update mtime/content_hash for existing file rows without rewriting payloads.

    rows: (rel_path, mtime, content_hash|None)
    Returns number of rows updated (SQLite only; 0 if no db).
    """
    root = Path(root)
    if not has_sqlite(root) or not rows:
        return 0
    n = 0
    with _db(root) as conn:
        for rel, mtime, chash in rows:
            if chash:
                cur = conn.execute(
                    "UPDATE files SET mtime = ?, content_hash = ? WHERE rel_path = ?",
                    (int(mtime), chash, rel),
                )
            else:
                cur = conn.execute(
                    "UPDATE files SET mtime = ? WHERE rel_path = ?",
                    (int(mtime), rel),
                )
            n += int(cur.rowcount or 0)
    return n


def save_meta_key(root: Path, key: str, value: Any) -> bool:
    """Write a single meta key to SQLite (warm ACS upgrade without full rewrite)."""
    root = Path(root)
    if not key.startswith("_"):
        return False
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return False
    if not has_sqlite(root):
        # Fall back: load full, set, save
        cache = load_cache_dict(root)
        cache[key] = value
        save_cache_dict(root, cache)
        return True
    with _db(root) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, raw),
        )
    return True


def get_map_coverage_from_meta(root: Path) -> Dict[str, Any]:
    """Read last map_coverage snapshot from meta if present."""
    meta = load_meta(root, keys=("_map_coverage", "_acs_summary"))
    cov = meta.get("_map_coverage") if isinstance(meta.get("_map_coverage"), dict) else {}
    acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
    return {
        "map_coverage": cov,
        "acs_version": acs.get("acs_version"),
        "cache_backend": backend_name(root),
        "actionable_low_conf_edges": acs.get("actionable_low_conf_edges"),
        "reason_code_counts": acs.get("reason_code_counts"),
    }
