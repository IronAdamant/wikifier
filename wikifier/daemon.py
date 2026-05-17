#!/usr/bin/env python3
"""
Wikifier Daemon Manager

Provides a strong, reliable background daemon for long-running Wikifier work.

Features:
- Proper PID file + logging
- start / stop / status / restart / logs
- Generation of a systemd user service for Linux (survives laptop sleep/lid close)
- Resume awareness (forces a check-changes on start and after long sleeps)
- Works for both `pip install wikifier` and direct ./wikifier.sh usage

Usage (via shell wrapper or directly):
    python -m wikifier.daemon start
    python -m wikifier.daemon stop
    python -m wikifier.daemon status
    python -m wikifier.daemon install-service
"""

import os
import sys
import time
import signal
import subprocess
import platform
from pathlib import Path
from datetime import datetime

# --- Configuration ---
DAEMON_NAME = "wikifier"
POLL_INTERVAL_DEFAULT = 30  # seconds
LOG_DIR_NAME = ".wikifier_staging"
PID_FILE_NAME = "wikifier.pid"
LOG_FILE_NAME = "daemon.log"

# How long a gap between heartbeats counts as "sleep/wake"
SLEEP_THRESHOLD_SECONDS = 120


def get_state_dir() -> Path:
    """Return the .wikifier_staging directory for the current project."""
    # Respect WIKIFIER_PROJECT_ROOT if set (R6 external monorepo support)
    root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if root:
        return Path(root).expanduser().resolve() / LOG_DIR_NAME
    return Path.cwd().resolve() / LOG_DIR_NAME


def get_pid_file() -> Path:
    return get_state_dir() / PID_FILE_NAME


def get_log_file() -> Path:
    return get_state_dir() / LOG_FILE_NAME


def ensure_state_dir():
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def log(msg: str, also_to_file: bool = True):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    if also_to_file:
        try:
            log_path = get_log_file()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def read_pid() -> int | None:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        return pid
    except Exception:
        return None


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # Doesn't kill, just checks existence
        return True
    except (ProcessLookupError, PermissionError):
        return False


def write_pid(pid: int):
    ensure_state_dir()
    get_pid_file().write_text(str(pid))


def remove_pid():
    try:
        get_pid_file().unlink(missing_ok=True)
    except Exception:
        pass


def daemon_loop():
    """
    The actual background loop.
    Runs `wikifier check-changes` (or the shell equivalent) periodically.
    Detects long sleeps and forces an immediate check on resume.
    """
    log("Wikifier daemon started.")

    last_check = time.time()

    # Initial check on start (important after sleep or restart)
    _run_check_changes("initial start / resume")

    while True:
        time.sleep(POLL_INTERVAL_DEFAULT)

        now = time.time()
        gap = now - last_check

        if gap > SLEEP_THRESHOLD_SECONDS:
            log(f"Wake detected (gap of {int(gap)}s). Running forced check-changes.")
            _run_check_changes("post-sleep resume")

        _run_check_changes("periodic")
        last_check = time.time()


def _run_check_changes(reason: str):
    """Run the check-changes command in a robust way."""
    try:
        # Prefer the installed `wikifier` command if available
        cmd = [sys.executable, "-m", "wikifier", "check-changes"]
        # But if we're running from source tree, the shell script may be better.
        # For now we use the Python entry point (it will delegate to sh).

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max per run
            env=os.environ.copy(),
        )

        if result.returncode != 0:
            log(f"check-changes failed (reason={reason}): {result.stderr[:500]}")
        else:
            log(f"check-changes completed (reason={reason})")

    except subprocess.TimeoutExpired:
        log(f"check-changes timed out (reason={reason})")
    except Exception as e:
        log(f"check-changes error (reason={reason}): {e}")


# --------------------------- Command Handlers ---------------------------

def cmd_start():
    ensure_state_dir()
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Wikifier daemon already running (PID {pid})")
        sys.exit(0)

    log_file = get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Fork into background
    pid = os.fork()
    if pid > 0:
        # Parent
        write_pid(pid)
        print(f"Wikifier daemon started (PID {pid})")
        print(f"Logs: {log_file}")
        sys.exit(0)

    # Child (daemon)
    os.setsid()
    os.umask(0)

    # Redirect stdio to log file
    with open(log_file, "a", buffering=1, encoding="utf-8") as logf:
        os.dup2(logf.fileno(), sys.stdout.fileno())
        os.dup2(logf.fileno(), sys.stderr.fileno())

    # Close stdin
    with open(os.devnull, "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())

    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("Daemon received SIGINT, shutting down.")
    finally:
        remove_pid()


def cmd_stop():
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Wikifier daemon is not running.")
        remove_pid()
        sys.exit(0)

    try:
        os.kill(pid, signal.SIGTERM)
        # Give it a moment
        time.sleep(1)
        if is_process_running(pid):
            os.kill(pid, signal.SIGKILL)
        print(f"Stopped Wikifier daemon (PID {pid})")
    except ProcessLookupError:
        print("Process already gone.")
    finally:
        remove_pid()


def cmd_status():
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Wikifier daemon is running (PID {pid})")
        print(f"Log file: {get_log_file()}")
    else:
        print("Wikifier daemon is not running.")
        remove_pid()


def cmd_logs(follow: bool = False):
    log_file = get_log_file()
    if not log_file.exists():
        print("No daemon log file found yet.")
        return

    cmd = ["tail", "-n", "100", "-f" if follow else ""] if follow else ["cat"]
    cmd = [c for c in cmd if c] + [str(log_file)]
    subprocess.run(cmd)


def cmd_restart():
    cmd_stop()
    time.sleep(1)
    cmd_start()


def generate_systemd_unit() -> str:
    """Generate a systemd user service file content."""
    wikifier_cmd = "wikifier"

    # Try to find the actual executable
    which = subprocess.run(["which", "wikifier"], capture_output=True, text=True)
    if which.returncode == 0:
        wikifier_cmd = which.stdout.strip()

    unit = f"""[Unit]
Description=Wikifier Background Daemon (Gap #1 Health Matrix + Dependency Intelligence)
After=network.target

[Service]
Type=simple
ExecStart={wikifier_cmd} daemon run
Restart=always
RestartSec=10
# Give the daemon a chance to finish current work on shutdown
KillMode=mixed
TimeoutStopSec=30

# Nice to have on laptops
StandardOutput=append:%h/.wikifier_staging/daemon.log
StandardError=append:%h/.wikifier_staging/daemon.log

[Install]
WantedBy=default.target
"""
    return unit


def cmd_install_service():
    if platform.system().lower() != "linux":
        print("systemd user services are currently only supported on Linux.")
        print("You can still use `wikifier daemon start` with nohup/tmux/screen.")
        return

    unit_content = generate_systemd_unit()
    user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
    user_systemd_dir.mkdir(parents=True, exist_ok=True)

    service_file = user_systemd_dir / "wikifier.service"
    service_file.write_text(unit_content)

    print("Systemd user service written to:")
    print(f"  {service_file}")
    print()
    print("To enable and start (survives laptop sleep/lid close):")
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now wikifier")
    print()
    print("Useful commands:")
    print("  systemctl --user status wikifier")
    print("  journalctl --user -u wikifier -f")
    print("  systemctl --user restart wikifier")


def cmd_uninstall_service():
    service_file = Path.home() / ".config" / "systemd" / "user" / "wikifier.service"
    if service_file.exists():
        service_file.unlink()
        print("Removed wikifier.service")
        print("Run: systemctl --user daemon-reload")
    else:
        print("No wikifier.service found.")


def cmd_run():
    """The actual foreground runner used by systemd / manual execution."""
    ensure_state_dir()
    log_file = get_log_file()
    print(f"Wikifier daemon (foreground) running. Logs: {log_file}")

    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("Foreground daemon stopped by user.")


def main():
    if len(sys.argv) < 2:
        print("Usage: wikifier daemon <start|stop|restart|status|logs|run|install-service|uninstall-service>")
        sys.exit(1)

    sub = sys.argv[1]
    args = sys.argv[2:]

    if sub == "start":
        cmd_start()
    elif sub == "stop":
        cmd_stop()
    elif sub == "restart":
        cmd_restart()
    elif sub == "status":
        cmd_status()
    elif sub == "logs":
        follow = "--follow" in args or "-f" in args
        cmd_logs(follow=follow)
    elif sub == "run":
        # Used by systemd and advanced users
        cmd_run()
    elif sub == "install-service":
        cmd_install_service()
    elif sub == "uninstall-service":
        cmd_uninstall_service()
    else:
        print(f"Unknown daemon command: {sub}")
        sys.exit(1)


if __name__ == "__main__":
    main()
