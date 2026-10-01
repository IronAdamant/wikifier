"""
Journal: the semantic audit trail (``journal/YYYY/MM/DD.md``) + Logged_issues listing.

Each entry::

    ## [2026-10-01 15:07:59] record-change
    **File:** src/a.py
    **Reason:** why the agent edited it

Writes happen under the project lock and raise on failure — a workflow call
must never report success while its audit entry was lost. An entry identical to
the previous one for the same file within ``DEDUPE_WINDOW_S`` is skipped, so a
retried call (e.g. after an MCP timeout) does not double-record.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import locking

JOURNAL_DIR = "journal"
ISSUES_DIR = "Logged_issues"
DEDUPE_WINDOW_S = 120

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_ENTRY_RE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] (?P<action>\S+)\n\*\*File:\*\* (?P<file>.*)\n\*\*Reason:\*\* (?P<reason>.*)$",
    re.M,
)


def day_path(root: Path, when: Optional[datetime] = None) -> Path:
    when = when or datetime.now()
    return Path(root) / JOURNAL_DIR / when.strftime("%Y") / when.strftime("%m") / f"{when.strftime('%d')}.md"


def _last_entry(text: str) -> Optional[Dict[str, str]]:
    matches = list(_ENTRY_RE.finditer(text))
    return matches[-1].groupdict() if matches else None


def append_entry(root: Path, action: str, file: str, reason: str, now: Optional[datetime] = None) -> bool:
    """Append one entry (locked). Returns False when skipped as a duplicate retry."""
    now = now or datetime.now()
    path = day_path(root, now)
    reason = " ".join(str(reason or "No reason provided.").split())
    with locking.file_lock(Path(root)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            last = _last_entry(path.read_text(encoding="utf-8"))
            if last and (last["action"], last["file"], last["reason"]) == (action, file, reason):
                try:
                    last_ts = datetime.strptime(last["ts"][:19], _TS_FORMAT)
                except ValueError:
                    last_ts = None
                if last_ts and now - last_ts <= timedelta(seconds=DEDUPE_WINDOW_S):
                    return False
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"## [{now.strftime(_TS_FORMAT)}] {action}\n**File:** {file}\n**Reason:** {reason}\n\n")
    return True


def read_day(root: Path, date: Optional[str] = None) -> Dict[str, Any]:
    """Entries for ``date`` (``YYYY-MM-DD``; default today)."""
    when = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    path = day_path(root, when)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "success": True,
        "date": when.strftime("%Y-%m-%d"),
        "path": str(path.relative_to(root)),
        "exists": path.exists(),
        "entries": [m.groupdict() for m in _ENTRY_RE.finditer(text)],
        "content": text,
    }


def list_issues(root: Path, severity: str = "all") -> Dict[str, Any]:
    """Markdown files under Logged_issues/ (optionally one severity subfolder)."""
    base = Path(root) / ISSUES_DIR
    if severity and severity != "all":
        base = base / severity
    files: List[str] = []
    if base.is_dir():
        files = sorted(p.relative_to(root).as_posix() for p in base.rglob("*.md"))
    return {
        "success": True,
        "severity": severity,
        "issues": files,
        "count": len(files),
        "has_map": (Path(root) / ISSUES_DIR / "map.md").is_file(),
    }
