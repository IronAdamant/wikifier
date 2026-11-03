# src/project_lock.rs

**Role:** The project-wide advisory lock at `.wikifier_staging/.lock`.

`ProjectLock::acquire` creates the pid file, waits 30 seconds, and steals the file when the recorded pid is dead. The same thread may re-enter. The outer guard is the one that deletes the file. Callers take this lock before the cache lock.

Public names: `ProjectLock`.
