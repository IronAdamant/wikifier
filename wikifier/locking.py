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
- Finite ``timeout`` (seconds) is honored on Unix (non-blocking poll loop);
  ``timeout=None`` still blocks until free. Per-file / sharded locks remain
  out of scope for M2 scale.
- Fine-grained (per-file) locking is a permanent non-goal unless extreme
  concurrency pressure appears on very large multi-agent setups.

For the current scale (including heavy multi-agent dogfooding), project-level
advisory locking is sufficient, safe, and has been battle-tested.
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

try:
    import fcntl  # Unix advisory locking
except ImportError:
    fcntl = None

try:
    import msvcrt  # Windows byte-range locking fallback
except ImportError:
    msvcrt = None

LOCK_FILE_NAME = ".wikifier_staging/.lock"

# Per-process re-entrancy bookkeeping. flock/msvcrt locks are NOT re-entrant
# across file descriptors: a second acquire of the same project lock from the
# same process (e.g. cli.record_change holding the lock while calling
# health.upsert_entry, which locks again) would block forever. We refcount
# per resolved root instead, so nested acquires are no-ops.
_HELD_LOCKS: dict = {}  # {resolved_root_str: {"fd": int, "depth": int}}


class LockTimeoutError(TimeoutError):
    """Raised when file_lock cannot acquire within the given timeout."""


def _acquire_exclusive(lock_fd: int, timeout: Optional[float]) -> None:
    """Acquire exclusive lock; honor finite timeout on Unix (G13)."""
    if fcntl is not None:
        if timeout is None:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            return
        if timeout < 0:
            raise ValueError("timeout must be None or >= 0")
        deadline = time.monotonic() + float(timeout)
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(
                        "project lock not acquired within {0}s".format(timeout)
                    )
                # Short sleep to avoid busy-spin; remaining time may be < sleep.
                remaining = deadline - time.monotonic()
                time.sleep(min(0.05, max(0.001, remaining)))
    elif msvcrt is not None:
        # Windows: LK_LOCK retries ~10s then OSError; loop for blocking.
        if timeout is None:
            while True:
                try:
                    os.lseek(lock_fd, 0, os.SEEK_SET)
                    msvcrt.locking(lock_fd, msvcrt.LK_LOCK, 1)
                    return
                except OSError:
                    continue
        deadline = time.monotonic() + float(timeout)
        while True:
            try:
                os.lseek(lock_fd, 0, os.SEEK_SET)
                msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(
                        "project lock not acquired within {0}s".format(timeout)
                    )
                remaining = deadline - time.monotonic()
                time.sleep(min(0.05, max(0.001, remaining)))
    # If neither primitive exists, proceed unlocked (advisory best-effort).


@contextmanager
def file_lock(root: Path, timeout: Optional[float] = None):
    """
    Context manager that acquires an exclusive advisory lock on the project.

    This is the primary locking primitive used by health.py and import_cache.py.

    Behavior: blocking acquire when ``timeout is None``; with a finite
    ``timeout`` (seconds) raises ``LockTimeoutError`` if the lock is not free
    in time. Re-entrant within the same process (nested acquires refcounted).

    Usage (agents rarely need this directly):
        with file_lock(Path(project_root)):
            ... critical section ...
        with file_lock(Path(project_root), timeout=5.0):
            ... fail fast on contention ...
    """
    lock_path = root / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        key = str(Path(root).resolve())
    except OSError:
        key = str(root)

    held = _HELD_LOCKS.get(key)
    if held is not None:
        # Re-entrant acquire from this process: just bump the depth.
        held["depth"] += 1
        try:
            yield
        finally:
            held["depth"] -= 1
        return

    lock_fd = None
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        _acquire_exclusive(lock_fd, timeout)
        # If neither primitive exists, proceed unlocked (advisory best-effort).
        _HELD_LOCKS[key] = {"fd": lock_fd, "depth": 1}
        yield
    finally:
        if lock_fd is not None:
            _HELD_LOCKS.pop(key, None)
            try:
                if fcntl is not None:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                elif msvcrt is not None:
                    os.lseek(lock_fd, 0, os.SEEK_SET)
                    msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
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
    if fcntl is None:
        return False  # no non-blocking probe available on this platform
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
