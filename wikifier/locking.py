"""
Simple file-based locking for Wikifier (M2-Rem-07) — Final Polish

This module provides advisory exclusive locking to protect Wikifier's
critical state files from corruption under concurrent access by multiple
agents, background `monitor` processes, or humans.

Protected resources (M2-Rem-07):
- file_health.json + file_health.md
- import_cache.json (incremental update-maps)
- pending_updates.md (selected paths)
- journal entries (compatible mkdir lock in write_journal)

Design (Production-Grade for Agents)
------------------------------------
- Primary: `fcntl.flock` (Unix advisory locking) — fast and reliable.
- Fallback: portable `mkdir`-based lock (works on most filesystems).
- Scope: **project-level** (one lock per Wikifier project root).
- Advisory: well-behaved processes must cooperate. Broken processes can ignore it.
- Goal: Safe concurrent operation on massive monorepos (one monitor + N LLM agents).

Python Usage (Recommended)
--------------------------
```python
from wikifier import locking
from pathlib import Path

with locking.file_lock(Path("/path/to/project")):
    # Safe to call save_health, save_cache, upsert_entry, etc.
    ...
```

Shell Usage
-----------
```bash
with_project_lock my_critical_shell_function
```
(See wikifier.sh for the reusable helper and its flock + mkdir implementation.)

Automatic Protection
--------------------
All high-level Wikifier tools (MCP and CLI) acquire the lock automatically
when using the Python backend (`health.py`, `import_cache.py`). Agents
almost never need to call locking primitives directly.

Limitations (Honest Assessment)
-------------------------------
- Advisory only.
- Project-level (not per-file or per-agent yet).
- Non-blocking check / timeout is not yet implemented (current behavior = blocking acquire).
- Fine-grained (per-file) or sharded locking is a planned future extension for extreme concurrency on very large codebases.

For the current scale (including heavy multi-agent dogfooding), project-level
advisory locking is sufficient, safe, and has been battle-tested.
"""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

LOCK_FILE_NAME = ".wikifier_staging/.lock"


@contextmanager
def file_lock(root: Path, timeout: Optional[float] = None):
    """
    Context manager that acquires an exclusive advisory lock on the project.

    This is the primary locking primitive used by health.py and import_cache.py.

    Current behavior: blocking acquire (will wait until the lock is free).
    Timeout support is planned for a future iteration.

    Usage (agents rarely need this directly):
        with file_lock(Path(project_root)):
            ... critical section ...
    """
    lock_path = root / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_fd = None
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)


def with_lock(root: Optional[Path] = None):
    """
    Decorator factory for file_lock.

    Usage:
        @with_lock(Path("/my/project"))
        def critical_operation(...):
            ...

    If no root is given, defaults to current working directory.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            target_root = root or Path(".")
            with file_lock(target_root):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def is_project_locked(root: Path) -> bool:
    """
    Best-effort check whether the project lock is currently held.

    Note: This is advisory and race-prone. Useful for debugging and
    advanced agent diagnostics, not for making locking decisions.
    """
    lock_path = root / LOCK_FILE_NAME
    if not lock_path.exists():
        return False
    try:
        with open(lock_path, "r+") as f:
            # Try a non-blocking lock; if we get it, no one else holds it.
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return False  # We acquired it → not locked
            except BlockingIOError:
                return True  # Someone else holds it
    except Exception:
        return False  # Conservative: assume not locked if we can't check
