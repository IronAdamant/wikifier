"""Stdlib SQLite import-cache store (agent warm-path; zero new deps).

AGENT MAP:
  load_cache_dict / save_cache_dict  — full cache dict (file entries + _meta keys)
  load_mtime_index                   — light {rel: mtime, content_hash} for dirty
  load_meta / save_meta_key          — reserved _keys without loading pairs
  update_file_index_rows             — mtime/hash refresh without full rewrite
  prune_file_index_outside_scope     — drop files rows outside MapScope prefixes
  backend_name / has_sqlite / cache_status

Dual-read: if ``import_cache.sqlite`` missing but legacy ``import_cache.json``
exists, load JSON and migrate on next save. Dual-write is opt-in only
(``WIKIFIER_CACHE_JSON=1``). Warm dirty detection should use
``load_mtime_index`` so agents avoid deserializing multi‑MB pair payloads.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

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
    """Persist cache to SQLite (primary). Optional legacy JSON dual-write (deprecated).

    Dual-read of legacy ``import_cache.json`` remains for migrate forever.

    ``write_json`` policy (4.6.6+ deprecation):
      - None → **opt-in only**: dual-write iff ``WIKIFIER_CACHE_JSON=1|true|yes|always``
        (default is sqlite-only — no silent multi‑MB JSON rewrite)
      - True / False → force on/off

    Returns backend name written: ``sqlite`` or ``sqlite+json``.
    """
    root = Path(root)
    if not isinstance(cache, dict):
        return "none"
    # Barrel preservation: merge missing barrel keys from meta only (no pair hydrate)
    _BARREL = ("_barrel_resolutions", "_barrel_file_index")
    if any(k not in cache for k in _BARREL):
        try:
            prev = load_meta(root, keys=_BARREL)
            for k in _BARREL:
                if k not in cache and prev.get(k):
                    cache[k] = prev[k]
        except Exception:
            pass

    if write_json is None:
        env = os.environ.get("WIKIFIER_CACHE_JSON", "").strip().lower()
        # Deprecated default dual-write for small trees removed: opt-in only
        write_json = env in ("1", "true", "yes", "always")

    with _db(root) as conn:
        keep_files = set()
        keep_meta = set()
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
                keep_meta.add(k)
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
                keep_files.add(k)
        # Drop rows the in-memory cache no longer owns (ghosts / scoped full rebuild)
        if keep_files:
            existing = [r[0] for r in conn.execute("SELECT rel_path FROM files")]
            for rel in existing:
                if rel not in keep_files:
                    conn.execute("DELETE FROM files WHERE rel_path = ?", (rel,))
        if keep_meta:
            existing_m = [r[0] for r in conn.execute("SELECT key FROM meta")]
            for key in existing_m:
                if key not in keep_meta:
                    conn.execute("DELETE FROM meta WHERE key = ?", (key,))

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


def prune_file_index_outside_scope(
    root: Path,
    rel_prefixes: Sequence[str],
    *,
    is_full_tree: bool = False,
) -> int:
    """Delete files-table rows outside map scope prefixes (SQLite).

    Full-tree scope (``is_full_tree`` or empty/'.' prefixes) → no prune.
    Used after narrowing map_paths so leftover full-tree index keys cannot
    poison candidate-list reuse forever.

    Returns number of rows deleted.
    """
    root = Path(root)
    if is_full_tree or not has_sqlite(root):
        return 0
    prefixes = [
        str(p).replace("\\", "/").strip().rstrip("/")
        for p in (rel_prefixes or [])
        if p is not None and str(p).strip() and str(p).strip() not in (".", "./")
    ]
    if not prefixes:
        return 0

    def _in_scope(rel: str) -> bool:
        r = rel.replace("\\", "/").lstrip("./")
        for pref in prefixes:
            if r == pref or r.startswith(pref + "/"):
                return True
        return False

    deleted = 0
    with _db(root) as conn:
        rows = [r[0] for r in conn.execute("SELECT rel_path FROM files")]
        for rel in rows:
            if not isinstance(rel, str) or not rel:
                continue
            if not _in_scope(rel):
                conn.execute("DELETE FROM files WHERE rel_path = ?", (rel,))
                deleted += 1
    return deleted


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


def cache_status(root: Path) -> Dict[str, Any]:
    """Machine-readable dual-cache status for agents/ops (zero full pair load)."""
    root = Path(root)
    sp = sqlite_path(root)
    jp = json_path(root)
    backend = backend_name(root)
    sqlite_bytes = int(sp.stat().st_size) if sp.is_file() else 0
    json_bytes = int(jp.stat().st_size) if jp.is_file() else 0
    snap = get_map_coverage_from_meta(root)
    meta = load_meta(root, keys=("_acs_summary", "_map_coverage", "_candidate_list"))
    acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
    cand = meta.get("_candidate_list") if isinstance(meta.get("_candidate_list"), dict) else {}
    return {
        "success": True,
        "project_root": str(root.resolve()) if root.exists() else str(root),
        "cache_backend": backend,
        "sqlite_path": str(sp) if sp.is_file() else None,
        "json_path": str(jp) if jp.is_file() else None,
        "sqlite_bytes": sqlite_bytes,
        "json_bytes": json_bytes,
        "acs_version": acs.get("acs_version") or snap.get("acs_version"),
        "actionable_low_conf_edges": acs.get("actionable_low_conf_edges"),
        "map_coverage": snap.get("map_coverage") or meta.get("_map_coverage"),
        "candidate_list_count": cand.get("count"),
        "candidate_list_directory": cand.get("directory"),
        "dual_write_policy": (
            "SQLite is primary. Legacy JSON dual-read remains for migrate. "
            "JSON dual-write is DEPRECATED default-off; set WIKIFIER_CACHE_JSON=1 to opt in. "
            "Prefer sqlite for warm agents."
        ),
        "migrate_note": (
            "update_maps migrates legacy import_cache.json → import_cache.sqlite once "
            "when sqlite is missing. Dual-read never deletes legacy JSON automatically."
        ),
        "map_paths_note": (
            "map_paths.txt = map package roots; monitored_paths.txt = wiki/health watch list. "
            "They are independent; wiki-only monitored lists do not define the map."
        ),
    }
