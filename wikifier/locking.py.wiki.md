# wikifier/locking.py

**Purpose:** advisory project lock on `.wikifier_staging/.lock` (`fcntl.flock`; `msvcrt` on Windows). Re-entrant within a thread, exclusive across threads and processes (a held depth is tracked in `threading.local`). `file_lock(root, timeout=None)` blocks; a finite timeout raises `LockTimeoutError`.
