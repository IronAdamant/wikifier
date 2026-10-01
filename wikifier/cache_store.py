"""
SQLite import-cache store (stdlib ``sqlite3``).

Tables:
  files(rel_path, mtime, content_hash, payload)  one row per mapped source file
  edges(src, dst, raw, confidence, score)        resolved internal edges, indexed both ways
  meta(key, value)                               reserved ``_*`` keys (cycles, ACS, barrels…)

Per-file lookups (``load_file_entry``, ``load_dependents``) use indexed queries so
agent tools never deserialize the whole cache. ``load_cache_dict`` still returns
the historical dict shape for whole-graph work (cycles, library.md).

Legacy ``import_cache.json`` is read only when no SQLite database exists and is
migrated on the next save. JSON dual-write is opt-in (``WIKIFIER_CACHE_JSON=1``).
Errors reading an existing database propagate — a corrupt cache must be visible,
not silently replaced by stale JSON.
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
CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  raw TEXT NOT NULL DEFAULT '',
  confidence TEXT,
  score REAL
);
CREATE INDEX IF NOT EXISTS edges_by_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS edges_by_src ON edges(src);
"""

# Marker meta key: edges table has been populated for this database.
_EDGES_READY = "_edges_ready"


def sqlite_path(root: Path) -> Path:
    return Path(root) / STAGING / SQLITE_NAME


def json_path(root: Path) -> Path:
    return Path(root) / STAGING / JSON_NAME


def has_sqlite(root: Path) -> bool:
    path = sqlite_path(root)
    return path.is_file() and path.stat().st_size > 0


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
    except sqlite3.Error:
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


def _load_legacy_json(root: Path) -> Dict[str, Any]:
    path = json_path(root)
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _decode(raw: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _edge_rows(rel: str, entry: Dict[str, Any]) -> List[Tuple[str, str, str, Optional[str], Optional[float]]]:
    """Resolved internal edges of one file entry, deduplicated by target."""
    rows = []
    seen = set()
    for pair in entry.get("resolved_pairs") or []:
        if not isinstance(pair, dict):
            continue
        dst = str(pair.get("resolved") or "")
        if not dst or dst == rel or dst in seen:
            continue
        seen.add(dst)
        score = pair.get("confidence_score")
        rows.append((
            rel,
            dst,
            str(pair.get("raw") or ""),
            pair.get("confidence"),
            float(score) if isinstance(score, (int, float)) else None,
        ))
    return rows


def _ensure_edges(conn: sqlite3.Connection) -> None:
    """Backfill the edges table for databases written before it existed."""
    if conn.execute("SELECT 1 FROM meta WHERE key = ?", (_EDGES_READY,)).fetchone():
        return
    conn.execute("DELETE FROM edges")
    rows = []
    for rel, payload in conn.execute("SELECT rel_path, payload FROM files"):
        entry = _decode(payload)
        if isinstance(entry, dict):
            rows.extend(_edge_rows(str(rel), entry))
    conn.executemany("INSERT INTO edges(src, dst, raw, confidence, score) VALUES (?, ?, ?, ?, ?)", rows)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (_EDGES_READY, "true"))


def load_mtime_index(root: Path) -> Dict[str, Dict[str, Any]]:
    """Light index for dirty detection: ``rel → {mtime, content_hash}``."""
    root = Path(root)
    if has_sqlite(root):
        with _db(root) as conn:
            return {
                str(rel): {"mtime": int(mtime or 0), "content_hash": chash}
                for rel, mtime, chash in conn.execute("SELECT rel_path, mtime, content_hash FROM files")
            }
    return {
        k: {"mtime": int(v.get("mtime", 0) or 0), "content_hash": v.get("content_hash")}
        for k, v in _load_legacy_json(root).items()
        if isinstance(k, str) and not k.startswith("_") and isinstance(v, dict)
    }


def load_meta(root: Path, keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Reserved ``_*`` keys without file payloads (all keys when ``keys`` is None)."""
    root = Path(root)
    wanted = set(keys) if keys is not None else None
    if has_sqlite(root):
        with _db(root) as conn:
            rows = conn.execute("SELECT key, value FROM meta").fetchall()
        return {
            str(k): _decode(raw)
            for k, raw in rows
            if k != _EDGES_READY and (wanted is None or k in wanted)
        }
    return {
        k: v
        for k, v in _load_legacy_json(root).items()
        if isinstance(k, str) and k.startswith("_") and (wanted is None or k in wanted)
    }


def _row_to_entry(mtime: Any, chash: Any, payload: Any) -> Dict[str, Any]:
    entry = _decode(payload) if payload else {}
    if not isinstance(entry, dict):
        entry = {}
    entry["mtime"] = int(mtime or 0)
    if chash:
        entry["content_hash"] = chash
    return entry


def load_cache_dict(root: Path) -> Dict[str, Any]:
    """Full cache dict: file entries + reserved keys (historical JSON shape)."""
    root = Path(root)
    if not has_sqlite(root):
        return _load_legacy_json(root)
    cache: Dict[str, Any] = {}
    with _db(root) as conn:
        for rel, mtime, chash, payload in conn.execute(
            "SELECT rel_path, mtime, content_hash, payload FROM files"
        ):
            cache[str(rel)] = _row_to_entry(mtime, chash, payload)
        for key, raw in conn.execute("SELECT key, value FROM meta"):
            if key != _EDGES_READY:
                cache[str(key)] = _decode(raw)
    return cache


def load_file_entry(root: Path, rel: str) -> Optional[Dict[str, Any]]:
    """One file's cache entry (or None) without loading the rest of the cache."""
    root = Path(root)
    if not has_sqlite(root):
        entry = _load_legacy_json(root).get(rel)
        return entry if isinstance(entry, dict) else None
    with _db(root) as conn:
        row = conn.execute(
            "SELECT mtime, content_hash, payload FROM files WHERE rel_path = ?", (rel,)
        ).fetchone()
    return _row_to_entry(*row) if row else None


def load_dependents(root: Path, rel: str) -> List[str]:
    """Files that import ``rel`` (indexed lookup; sorted)."""
    root = Path(root)
    if not has_sqlite(root):
        cache = _load_legacy_json(root)
        return sorted(
            src for src, entry in cache.items()
            if isinstance(entry, dict) and not src.startswith("_")
            and any(dst == rel for _, dst, *_ in _edge_rows(src, entry))
        )
    with _db(root) as conn:
        _ensure_edges(conn)
        return [r[0] for r in conn.execute("SELECT DISTINCT src FROM edges WHERE dst = ? ORDER BY src", (rel,))]


def load_dependencies(root: Path, rel: str) -> List[str]:
    """Internal files that ``rel`` imports (indexed lookup; sorted)."""
    root = Path(root)
    if not has_sqlite(root):
        entry = _load_legacy_json(root).get(rel)
        return sorted({dst for _, dst, *_ in _edge_rows(rel, entry)}) if isinstance(entry, dict) else []
    with _db(root) as conn:
        _ensure_edges(conn)
        return [r[0] for r in conn.execute("SELECT DISTINCT dst FROM edges WHERE src = ? ORDER BY dst", (rel,))]


def save_cache_dict(root: Path, cache: Dict[str, Any], write_json: Optional[bool] = None) -> str:
    """Persist the cache dict to SQLite (files, edges, meta in one transaction).

    Rows the dict no longer owns are deleted. ``write_json`` (default: env
    ``WIKIFIER_CACHE_JSON``) additionally writes the legacy JSON file.
    Returns the backend written: ``sqlite`` or ``sqlite+json``.
    """
    root = Path(root)
    if not isinstance(cache, dict):
        raise TypeError("cache must be a dict")
    # Barrel structures are flushed separately by BREE; keep them if absent here.
    barrel_keys = ("_barrel_resolutions", "_barrel_file_index")
    if any(k not in cache for k in barrel_keys) and has_sqlite(root):
        previous = load_meta(root, keys=barrel_keys)
        for key in barrel_keys:
            if key not in cache and previous.get(key):
                cache[key] = previous[key]
    if write_json is None:
        write_json = os.environ.get("WIKIFIER_CACHE_JSON", "").strip().lower() in ("1", "true", "yes", "always")

    file_rows = []
    edge_rows = []
    meta_rows = []
    for key, value in cache.items():
        if not isinstance(key, str):
            continue
        if key.startswith("_"):
            meta_rows.append((key, json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)))
        elif isinstance(value, dict):
            file_rows.append((
                key,
                int(value.get("mtime", 0) or 0),
                value.get("content_hash"),
                json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str),
            ))
            edge_rows.extend(_edge_rows(key, value))
    with _db(root) as conn:
        # A dict without file entries (or without meta) must never wipe the other half.
        if file_rows:
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM edges")
            conn.executemany(
                "INSERT INTO files(rel_path, mtime, content_hash, payload) VALUES (?, ?, ?, ?)", file_rows
            )
            conn.executemany(
                "INSERT INTO edges(src, dst, raw, confidence, score) VALUES (?, ?, ?, ?, ?)", edge_rows
            )
        if meta_rows:
            conn.execute("DELETE FROM meta")
            conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", meta_rows)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (_EDGES_READY, "true"))

    if write_json:
        path = json_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, separators=(",", ":"), default=str)
        return "sqlite+json"
    return "sqlite"


def update_file_index_rows(root: Path, rows: List[Tuple[str, int, Optional[str]]]) -> int:
    """Refresh mtime/content_hash for existing rows without rewriting payloads."""
    root = Path(root)
    if not has_sqlite(root) or not rows:
        return 0
    updated = 0
    with _db(root) as conn:
        for rel, mtime, chash in rows:
            if chash:
                cur = conn.execute(
                    "UPDATE files SET mtime = ?, content_hash = ? WHERE rel_path = ?", (int(mtime), chash, rel)
                )
            else:
                cur = conn.execute("UPDATE files SET mtime = ? WHERE rel_path = ?", (int(mtime), rel))
            updated += int(cur.rowcount or 0)
    return updated


def prune_file_index_outside_scope(root: Path, rel_prefixes: Sequence[str], *, is_full_tree: bool = False) -> int:
    """Delete file (and edge) rows outside the map scope prefixes. Returns rows deleted."""
    root = Path(root)
    if is_full_tree or not has_sqlite(root):
        return 0
    prefixes = []
    for prefix in rel_prefixes or []:
        p = str(prefix or "").replace("\\", "/").strip().rstrip("/")
        while p.startswith("./"):
            p = p[2:]
        if p and p != ".":
            prefixes.append(p)
    if not prefixes:
        return 0

    def in_scope(rel: str) -> bool:
        return any(rel == p or rel.startswith(p + "/") for p in prefixes)

    with _db(root) as conn:
        doomed = [r[0] for r in conn.execute("SELECT rel_path FROM files") if not in_scope(str(r[0]))]
        conn.executemany("DELETE FROM files WHERE rel_path = ?", [(rel,) for rel in doomed])
        conn.executemany("DELETE FROM edges WHERE src = ?", [(rel,) for rel in doomed])
    return len(doomed)


def save_meta_key(root: Path, key: str, value: Any) -> bool:
    """Write one reserved meta key without rewriting file payloads."""
    root = Path(root)
    if not key.startswith("_"):
        return False
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if not has_sqlite(root):
        cache = load_cache_dict(root)
        cache[key] = value
        save_cache_dict(root, cache)
        return True
    with _db(root) as conn:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, raw))
    return True


def cache_status(root: Path) -> Dict[str, Any]:
    """Machine-readable cache status (no payload load)."""
    root = Path(root)
    sp = sqlite_path(root)
    jp = json_path(root)
    meta = load_meta(root, keys=("_acs_summary", "_map_coverage", "_candidate_list"))
    acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
    cand = meta.get("_candidate_list") if isinstance(meta.get("_candidate_list"), dict) else {}
    edge_count = None
    if has_sqlite(root):
        with _db(root) as conn:
            _ensure_edges(conn)
            edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    return {
        "success": True,
        "project_root": str(root.resolve()) if root.exists() else str(root),
        "cache_backend": backend_name(root),
        "sqlite_path": str(sp) if sp.is_file() else None,
        "json_path": str(jp) if jp.is_file() else None,
        "sqlite_bytes": int(sp.stat().st_size) if sp.is_file() else 0,
        "json_bytes": int(jp.stat().st_size) if jp.is_file() else 0,
        "edge_count": edge_count,
        "acs_version": acs.get("acs_version"),
        "actionable_low_conf_edges": acs.get("actionable_low_conf_edges"),
        "map_coverage": meta.get("_map_coverage"),
        "candidate_list_count": cand.get("count"),
        "candidate_list_directory": cand.get("directory"),
        "dual_write_policy": (
            "SQLite is primary. JSON dual-write is DEPRECATED and off by default; "
            "set WIKIFIER_CACHE_JSON=1 to also write import_cache.json."
        ),
        "migrate_note": (
            "Legacy import_cache.json is read only when no SQLite database exists and is "
            "migrated on the next update_maps; it is never deleted automatically."
        ),
        "map_paths_note": (
            "map_paths.txt = map package roots; monitored_paths.txt = wiki/health watch list. "
            "They are independent."
        ),
    }
