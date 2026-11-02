//! Advisory project lock at `.wikifier_staging/.lock`.
//! Re-entrant on the same thread. Taken before the cache `wk.lock`.

use std::cell::Cell;
use std::fs::{self, OpenOptions};
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

thread_local! {
    static DEPTH: Cell<u32> = const { Cell::new(0) };
}

pub struct ProjectLock {
    path: Option<PathBuf>,
}

impl Drop for ProjectLock {
    fn drop(&mut self) {
        DEPTH.with(|depth| {
            let now = depth.get();
            if now > 0 {
                depth.set(now - 1);
            }
        });
        if let Some(path) = &self.path {
            let _ = fs::remove_file(path);
        }
    }
}

impl ProjectLock {
    pub fn acquire(root: &Path) -> Result<Self, String> {
        let nested = DEPTH.with(|depth| {
            let now = depth.get();
            if now > 0 {
                depth.set(now + 1);
                true
            } else {
                false
            }
        });
        if nested {
            return Ok(ProjectLock { path: None });
        }
        let dir = root.join(".wikifier_staging");
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let path = dir.join(".lock");
        let deadline = Instant::now() + Duration::from_secs(30);
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    let stamp = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
                    writeln!(file, "{}\n{stamp}", std::process::id()).map_err(|e| e.to_string())?;
                    file.sync_all().map_err(|e| e.to_string())?;
                    DEPTH.with(|depth| depth.set(1));
                    return Ok(ProjectLock { path: Some(path) });
                }
                Err(err) if err.kind() == ErrorKind::AlreadyExists => {
                    if try_steal(&path) {
                        continue;
                    }
                    if Instant::now() >= deadline {
                        let text = fs::read_to_string(&path).unwrap_or_default();
                        let pid = text.lines().next().unwrap_or("?").trim();
                        return Err(format!(
                            "project locked by pid {pid}; another wikifier run holds {} — wait for it to finish, or remove the lock if that process is gone",
                            path.display()
                        ));
                    }
                    std::thread::sleep(Duration::from_millis(50));
                }
                Err(err) => return Err(format!("failed to lock project: {err}")),
            }
        }
    }
}

fn try_steal(path: &Path) -> bool {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(_) => return false,
    };
    let pid: i32 = text.lines().next().unwrap_or("0").trim().parse().unwrap_or(0);
    let stale = if pid > 0 {
        !crate::proc::pid_alive(pid)
    } else {
        fs::metadata(path)
            .ok()
            .and_then(|meta| meta.modified().ok())
            .and_then(|t| t.elapsed().ok())
            .map(|age| age.as_secs() >= 5)
            .unwrap_or(true)
    };
    if !stale {
        return false;
    }
    if fs::read_to_string(path).unwrap_or_default() != text {
        return false;
    }
    fs::remove_file(path).is_ok()
}
