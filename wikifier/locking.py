"""
Project-level advisory locking for Wikifier state files.

Protects file_health.json/.md, pending_updates.md, the import cache and journal
writes against concurrent agents, the daemon and humans.

- POSIX: ``fcntl.flock`` on ``.wikifier_staging/.lock``; Windows: ``msvcrt.locking``.
  If neither primitive exists the lock is a no-op (advisory best-effort).
- Re-entrant **per thread**: a thread that already holds the lock may nest
  acquisitions (e.g. record_change → upsert_entry). Other threads of the same
  process still block, because each acquisition opens its own descriptor and
  flock/msvcrt locks conflict across descriptors.
- ``timeout=None`` blocks; a finite timeout raises ``LockTimeoutError``.

    from wikifier import locking
    with locking.file_lock(project_root, timeout=5.0):
        ...  # safe to call the _do_* helpers
"""

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

LOCK_FILE_NAME = ".wikifier_staging/.lock"

# {resolved_root: depth} for the current thread only.
_THREAD_STATE = threading.local()


class LockTimeoutError(TimeoutError):
    """Raised when file_lock cannot acquire within the given timeout."""


def _held() -> Dict[str, int]:
    held = getattr(_THREAD_STATE, "held", None)
    if held is None:
        held = {}
        _THREAD_STATE.held = held
    return held


def _try_lock(fd: int) -> bool:
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _acquire_exclusive(fd: int, timeout: Optional[float]) -> None:
    if timeout is not None and timeout < 0:
        raise ValueError("timeout must be None or >= 0")
    if fcntl is not None and timeout is None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return
    deadline = None if timeout is None else time.monotonic() + float(timeout)
    while not _try_lock(fd):
        if deadline is not None and time.monotonic() >= deadline:
            raise LockTimeoutError(f"project lock not acquired within {timeout}s")
        remaining = 0.05 if deadline is None else deadline - time.monotonic()
        time.sleep(min(0.05, max(0.001, remaining)))


def _release(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    elif msvcrt is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextmanager
def file_lock(root: Path, timeout: Optional[float] = None):
    """Exclusive advisory project lock (re-entrant within a thread)."""
    root = Path(root)
    try:
        key = str(root.resolve())
    except OSError:
        key = str(root)
    held = _held()
    if key in held:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return

    lock_path = root / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _acquire_exclusive(fd, timeout)
        held[key] = 1
        try:
            yield
        finally:
            held.pop(key, None)
            _release(fd)
    finally:
        os.close(fd)


def with_lock(root: Optional[Path] = None):
    """Decorator form of :func:`file_lock` (defaults to the current directory)."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with file_lock(root or Path(".")):
                return func(*args, **kwargs)
        return wrapper
    return decorator
