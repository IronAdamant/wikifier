"""
Long-horizon readiness (is a target safe for an unattended daemon?) + metrics history.

``ready_for_daemon`` means the configuration is safe for unattended
check-changes/update-maps loops. It is not a multi-day soak proof.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .pending import count_pending
from .scope import detect_scope_risks, find_ghost_entries
from .store import RootLike, _coerce_root
from .summary import get_summary

STAGING = ".wikifier_staging"
_HISTORY_MAX = 500


def _staging_byte_total(staging: Path) -> int:
    if not staging.exists():
        return 0
    total = 0
    for path in staging.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _cache_bytes(staging: Path) -> int:
    total = 0
    for name in ("import_cache.sqlite", "import_cache.json"):
        path = staging / name
        if path.exists():
            total += path.stat().st_size
    return total


def _read_heartbeat(staging: Path) -> Optional[Dict[str, Any]]:
    path = staging / "daemon_heartbeat.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "unreadable"}


def write_metrics_snapshot(
    root: RootLike,
    source: str = "manual",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a metrics sample (metrics_latest.json + bounded metrics_history.jsonl)."""
    root = _coerce_root(root)
    staging = root / STAGING
    staging.mkdir(parents=True, exist_ok=True)
    summary = get_summary(root)
    scope = detect_scope_risks(root)
    heartbeat = _read_heartbeat(staging)
    journal_root = root / "journal"
    snap: Dict[str, Any] = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "root": str(root),
        "health_score": summary.get("health_score"),
        "total": summary.get("total"),
        "green": summary.get("green"),
        "yellow": summary.get("yellow"),
        "red": summary.get("red"),
        "stub_yellow": summary.get("stub_yellow"),
        "actionable_yellow": summary.get("actionable_yellow"),
        "pending_updates": summary.get("pending_updates"),
        "ghost_count": len(find_ghost_entries(root)),
        "cache_bytes": _cache_bytes(staging),
        "staging_bytes": _staging_byte_total(staging),
        "journal_files": sum(1 for _ in journal_root.rglob("*.md")) if journal_root.exists() else 0,
        "bare_dot_monitor": scope.get("bare_dot_monitor"),
        "scope_ok": scope.get("ok"),
        "daemon_heartbeat_ok": heartbeat.get("ok") if isinstance(heartbeat, dict) else None,
        "daemon_fail_streak": heartbeat.get("consecutive_failures") if isinstance(heartbeat, dict) else None,
    }
    if extra:
        snap["extra"] = extra
    latest_path = staging / "metrics_latest.json"
    hist_path = staging / "metrics_history.jsonl"
    latest_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    with open(hist_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    lines = hist_path.read_text(encoding="utf-8").splitlines()
    if len(lines) > _HISTORY_MAX:
        hist_path.write_text("\n".join(lines[-_HISTORY_MAX:]) + "\n", encoding="utf-8")
    snap.update({
        "success": True,
        "metrics_latest_path": str(latest_path),
        "metrics_history_path": str(hist_path),
    })
    return snap


def read_metrics_history(root: RootLike, limit: int = 20) -> List[Dict[str, Any]]:
    """Most recent ``limit`` metrics samples (oldest first)."""
    hist_path = _coerce_root(root) / STAGING / "metrics_history.jsonl"
    if not hist_path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in hist_path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, _HISTORY_MAX)):]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _daemon_pid(staging: Path) -> Optional[int]:
    pid_path = staging / "wikifier.pid"
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def assess_autonomous_readiness(root: RootLike, write_metrics: bool = True) -> Dict[str, Any]:
    """Checklist for unattended operation: map, health, scope, ghosts, daemon state."""
    root = _coerce_root(root)
    summary = get_summary(root)
    scope = detect_scope_risks(root)
    ghosts = find_ghost_entries(root)
    pending_n = count_pending(root)
    staging = root / STAGING
    cache_bytes = _cache_bytes(staging)
    staging_bytes = _staging_byte_total(staging)
    journal_root = root / "journal"
    journal_files = list(journal_root.rglob("*.md")) if journal_root.exists() else []
    daemon_pid = _daemon_pid(staging)
    has_health = (root / "file_health.json").exists() or (root / "file_health.md").exists()
    has_library = (root / "library.md").exists()
    has_cache = (staging / "import_cache.sqlite").exists() or (staging / "import_cache.json").exists()

    metrics_snap = write_metrics_snapshot(root, source="autonomous-status") if write_metrics else None
    history = read_metrics_history(root, limit=5)
    growth_note = None
    if len(history) >= 2:
        first, last = history[0], history[-1]
        growth_note = {
            "samples": len(history),
            "staging_bytes_delta": int(last.get("staging_bytes") or 0) - int(first.get("staging_bytes") or 0),
            "first_ts": first.get("ts"),
            "last_ts": last.get("ts"),
        }

    blockers: List[str] = []
    recs: List[str] = list(scope["warnings"])
    if not has_cache and not has_library:
        blockers.append("No import map (run update-maps first).")
    if not has_health:
        blockers.append("No file_health — run seed-health or update-maps.")
    if len(ghosts) > 50:
        blockers.append(f"Many ghost health keys ({len(ghosts)}); run record-deletion / prune.")
    elif ghosts:
        recs.append(f"{len(ghosts)} ghost health entries — clean with record-deletion.")
    if pending_n > 500:
        recs.append(f"pending_updates={pending_n} is large; run prune-pending (auto-detected noise).")
    if cache_bytes > 200 * 1024 * 1024:
        recs.append(
            f"import cache is large ({cache_bytes // (1024 * 1024)}MB); "
            "prefer scoped update-maps and lean monitors for long runs."
        )
    if staging_bytes > 500 * 1024 * 1024:
        recs.append(f".wikifier_staging ~{staging_bytes // (1024 * 1024)}MB — watch disk growth.")
    if daemon_pid is None:
        recs.append(
            "Daemon not running. For long-horizon: `wikifier daemon start` "
            "(maps interval default 600s; WIKIFIER_DAEMON_MAPS=0 for check-only)."
        )
    else:
        recs.append(f"Daemon running (PID {daemon_pid}).")

    score = summary.get("health_score") or "Unknown"
    if blockers:
        readiness = "blocked"
    elif scope["warnings"] and summary.get("actionable_yellow", 0) == 0 and summary.get("red", 0) == 0:
        readiness = "map_ok_scope_risk"
    elif score in ("Map Ready", "Good") and not scope["bare_dot_monitor"]:
        readiness = "ready_for_daemon"
    elif score == "Needs Attention" and summary.get("red", 0) == 0:
        readiness = "ready_with_agent_wiki_work"
    else:
        readiness = "not_ready"

    return {
        "success": True,
        "root": str(root),
        "readiness": readiness,
        "health_score": score,
        "health_summary": summary,
        "scope": scope,
        "ghost_count": len(ghosts),
        "pending_updates": pending_n,
        "artifacts": {
            "has_health": has_health,
            "has_library": has_library,
            "has_cache": has_cache,
            "cache_bytes": cache_bytes,
            "staging_bytes": staging_bytes,
            "journal_files": len(journal_files),
            "journal_day_dirs": len({p.parent for p in journal_files}),
            "metrics_latest": str(staging / "metrics_latest.json") if (staging / "metrics_latest.json").exists() else None,
        },
        "daemon": {
            "running": daemon_pid is not None,
            "pid": daemon_pid,
            "heartbeat": _read_heartbeat(staging),
            "log": str(staging / "daemon.log") if (staging / "daemon.log").exists() else None,
            "maps_env": {
                "WIKIFIER_DAEMON_MAPS": os.environ.get("WIKIFIER_DAEMON_MAPS", "1"),
                "WIKIFIER_DAEMON_MAPS_INTERVAL": os.environ.get("WIKIFIER_DAEMON_MAPS_INTERVAL", "600"),
            },
        },
        "metrics": metrics_snap,
        "metrics_growth": growth_note,
        "lock_path": str(staging / ".lock"),
        "blockers": blockers,
        "recommendations": recs,
        "long_horizon_note": (
            "ready_for_daemon = safe config for unattended check-changes/maps heartbeat, "
            "not a multi-day soak proof. For soak evidence, run the daemon on lean-monitored "
            "targets and watch metrics_history.jsonl (staging_bytes delta, heartbeat failures)."
        ),
        "map_first_note": summary.get("map_first_note"),
    }
