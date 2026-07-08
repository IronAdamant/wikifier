"""
Wikifier Daemon (Gap #1 long-running health + dependency intelligence).

Provides `wikifier daemon start|stop|status|logs|restart|run|install-service|uninstall-service`.

Key features:
- Double-fork background daemonization (cmd_start).
- Sleep/laptop lid/wake detection: if the poll gap exceeds SLEEP_THRESHOLD_SECONDS,
  forces an immediate `check-changes` on resume before resuming normal periodic work.
- Robust `check-changes` runner with timeout and error logging.
- Systemd user service generator (survives reboots and sleep on laptops).
- All state (pid, logs) lives under the *discovered project root* /.wikifier_staging (Wave 3: full discover_project_root ...; Wave 5: run_full_update wired for direct pure-Py periodic/post-sleep update-maps calls without sh).

Designed to keep the Health Matrix, journal, and (future) incremental update-maps
fresh with minimal manual intervention on long-running projects.
"""
# Phase 5e (66): daemon + journal paths now note health summaries / ACS/barrel / format=summary as first-class default for 20k+ creative (O(k) bounded ACS/CIABRE per 48/58/50; for long-running Gate4 hygiene).

from __future__ import annotations

import os
import sys
import time
import signal
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

# Gap #1 Wave 3 External/Packaged: import unified discover_project_root for robust
# state dir selection when daemon is invoked directly (python -m, systemd, subdir cwd,
# symlink or pnpm-store cwd inside external monorepo after `pip install wikifier`).
# Falls back gracefully; central discover now includes logical PWD hardening.
try:
    from .cli import discover_project_root, run_full_update
except Exception:
    discover_project_root = None  # type: ignore[assignment]
    run_full_update = None  # type: ignore[assignment]

# =============================================================================
# Configuration (must match wikifier.sh POLL_INTERVAL default and prior daemon)
# =============================================================================

DAEMON_NAME = "wikifier"
POLL_INTERVAL_DEFAULT = 30  # seconds — check-changes heartbeat
# G11: do NOT run full update-maps every poll on large monorepos (was 30s → IO bomb).
# Override: WIKIFIER_DAEMON_MAPS_INTERVAL (seconds; 0 = never periodic maps, only start/wake).
# WIKIFIER_DAEMON_MAPS=0 disables all background update-maps (check-changes only; like monitor).
SLEEP_THRESHOLD_SECONDS = 120  # if sleep gap > this, treat as wake-from-sleep and force check


def _maps_enabled() -> bool:
    return os.environ.get("WIKIFIER_DAEMON_MAPS", "1").strip() not in ("0", "false", "no")


def _maps_interval_sec() -> int:
    raw = os.environ.get("WIKIFIER_DAEMON_MAPS_INTERVAL", "600")
    try:
        return max(0, int(raw))
    except ValueError:
        return 600

LOG_DIR_NAME = ".wikifier_staging"
LOG_FILE_NAME = "daemon.log"
PID_FILE_NAME = "wikifier.pid"


# =============================================================================
# State directory helpers (respect WIKIFIER_PROJECT_ROOT for external monorepos)
# Wave 2: now uses full discover_project_root (walk-up for .git etc markers) so that
# `cd external-monorepo/subdir; wikifier daemon start` (post-pip) correctly targets
# the monorepo root for .wikifier_staging/ (not the subdir). Mirrors CLI/MCP/shell.
# =============================================================================

def get_state_dir() -> Path:
    """Return the .wikifier_staging directory for the current project.

    Wave 3 External improvement: prefers the canonical discover_project_root()
    (handles subdir cwd, symlinks, pnpm/yarn store layouts via logical PWD ancestor walk,
    markers, common project files) for packaged + external monorepo scenarios.
    Env var still honored as highest priority via discover.
    """
    if discover_project_root is not None:
        try:
            root = discover_project_root()
            if root and root.exists():
                return root / LOG_DIR_NAME
        except Exception:
            pass  # fall through to env/cwd
    root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if root:
        return Path(root).expanduser().resolve() / LOG_DIR_NAME
    return Path.cwd().resolve() / LOG_DIR_NAME


def get_pid_file() -> Path:
    return get_state_dir() / PID_FILE_NAME


def get_log_file() -> Path:
    return get_state_dir() / LOG_FILE_NAME


def ensure_state_dir() -> Path:
    state = get_state_dir()
    state.mkdir(parents=True, exist_ok=True)
    return state


# =============================================================================
# PID / process helpers
# =============================================================================

def write_pid(pid: int) -> None:
    ensure_state_dir()
    get_pid_file().write_text(str(pid))


def read_pid() -> Optional[int]:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except Exception:
        return None


def remove_pid() -> None:
    try:
        get_pid_file().unlink(missing_ok=True)
    except Exception:
        pass


def is_process_running(pid: int) -> bool:
    """Return True if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# =============================================================================
# Logging
# =============================================================================

def log(msg: str, also_to_file: bool = True) -> None:
    """Timestamped log to stdout + (optionally) the daemon log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if also_to_file:
        try:
            log_path = get_log_file()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # Never let logging failure kill the daemon
            pass


# =============================================================================
# Core check runner (used by both initial, periodic, and post-sleep paths)
# =============================================================================

def _write_heartbeat(event: str, ok: bool, detail: str = "") -> None:
    """Persist last daemon success/failure for autonomous-status / long-horizon ops."""
    try:
        import json as _json
        path = ensure_state_dir() / "daemon_heartbeat.json"
        prev = {}
        if path.exists():
            try:
                prev = _json.loads(path.read_text(encoding="utf-8")) or {}
            except Exception:
                prev = {}
        fail_streak = int(prev.get("consecutive_failures", 0) or 0)
        if ok:
            fail_streak = 0
        else:
            fail_streak += 1
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "ok": ok,
            "detail": (detail or "")[:400],
            "consecutive_failures": fail_streak,
            "project_root": str(
                (discover_project_root() if discover_project_root else Path.cwd()).resolve()
            ),
        }
        path.write_text(_json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if fail_streak >= 5:
            log(
                f"LONG-HORIZON WARN: {fail_streak} consecutive daemon step failures — "
                "inspect daemon.log; consider lean monitored_paths / WIKIFIER_DAEMON_MAPS=0"
            )
    except Exception:
        pass


def _run_check_changes(reason: str) -> None:
    """
    Run the check-changes command in a robust way.

    Uses `python -m wikifier check-changes` so it works correctly from a
    pip-installed wikifier (no reliance on ./wikifier.sh in PATH).
    Captures output, enforces a 5-minute timeout, and logs failures.
    """
    cmd = [sys.executable, "-m", "wikifier", "check-changes"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            msg = (result.stderr or "")[:500]
            log(f"check-changes failed (reason={reason}): {msg}")
            _write_heartbeat(f"check-changes:{reason}", False, msg)
            return
        log(f"check-changes completed (reason={reason})")
        _write_heartbeat(f"check-changes:{reason}", True)
    except subprocess.TimeoutExpired:
        log(f"check-changes timed out (reason={reason})")
        _write_heartbeat(f"check-changes:{reason}", False, "timeout")
    except Exception as e:
        log(f"check-changes error (reason={reason}): {e}")
        _write_heartbeat(f"check-changes:{reason}", False, str(e))


def _run_python_primary_update(reason: str, force_full: bool = False) -> None:
    """
    Wave 5: Wire run_full_update direct (pure Python primary path, no sh/subprocess)
    into daemon for External/Packaged robustness.

    Called on initial, periodic, and especially post-sleep to keep dependency intel
    fresh using the deepened pipeline (dirty + parser + persist + barrel/creative)
    directly from Python. Best-effort, never blocks the loop; logs summary.
    Respects discovery for external monorepos. Guarded by import success.
    """
    if run_full_update is None:
        log(f"python-primary update skipped (no run_full_update import) reason={reason}")
        return
    try:
        res = run_full_update(root=None, force_full=force_full, verbose=False, use_canonical=True, use_python_primary=True)
        files = res.get("files_to_reparse", 0)
        persisted = res.get("sample_persisted_pairs", 0)
        tied = res.get("barrel_creative_tied_in_pure_path", False)
        ok = bool(res.get("success", True))
        log(
            f"python-primary update completed (reason={reason}): "
            f"files_to_reparse={files} persisted_pairs={persisted} barrel_creative_tied={tied} "
            f"root={res.get('root')} success={ok}"
        )
        _write_heartbeat(
            f"update-maps:{reason}",
            ok,
            f"parsed={res.get('files_parsed')} edges={res.get('edges_persisted')}",
        )
    except Exception as e:
        log(f"python-primary update error (reason={reason}): {e}")
        _write_heartbeat(f"update-maps:{reason}", False, str(e))


# =============================================================================
# The background loop (heart of the daemon)
# =============================================================================

def daemon_loop() -> None:
    """
    The actual background loop.

    - Every POLL_INTERVAL: check-changes (health/mtime heartbeat).
    - update-maps (run_full_update): at most every WIKIFIER_DAEMON_MAPS_INTERVAL
      (default 600s), plus once at start and on wake — not every 30s (G11).
    - WIKIFIER_DAEMON_MAPS=0 → check-changes only (monitor-like).
    """
    maps_iv = _maps_interval_sec()
    maps_on = _maps_enabled()
    log(
        f"Wikifier daemon started (check every {POLL_INTERVAL_DEFAULT}s; "
        f"maps={'off' if not maps_on else f'every {maps_iv}s' if maps_iv else 'start/wake only'})."
    )

    last_check = time.time()
    last_maps = 0.0
    last_metrics = 0.0
    # Metrics cadence (seconds); default 1h for soak growth without spam
    try:
        metrics_iv = max(0, int(os.environ.get("WIKIFIER_DAEMON_METRICS_INTERVAL", "3600") or "3600"))
    except ValueError:
        metrics_iv = 3600

    def _maybe_metrics(reason: str, force: bool = False) -> None:
        nonlocal last_metrics
        if metrics_iv <= 0 and not force:
            return
        now_m = time.time()
        if not force and metrics_iv > 0 and (now_m - last_metrics) < metrics_iv:
            return
        try:
            from . import health as health_mod
            if hasattr(health_mod, "write_metrics_snapshot"):
                root = None
                if discover_project_root is not None:
                    try:
                        root = discover_project_root()
                    except Exception:
                        root = None
                snap = health_mod.write_metrics_snapshot(
                    root or Path.cwd(),
                    source=f"daemon:{reason}",
                )
                log(
                    f"metrics-snapshot (reason={reason}): "
                    f"staging_bytes={snap.get('staging_bytes')} "
                    f"score={snap.get('health_score')} ok={snap.get('success')}"
                )
                last_metrics = now_m
        except Exception as me:
            log(f"metrics-snapshot error (reason={reason}): {me}")

    _run_check_changes("initial start / resume")
    if maps_on:
        _run_python_primary_update("initial start / resume", force_full=False)
        last_maps = time.time()
    _maybe_metrics("initial", force=True)

    while True:
        try:
            time.sleep(POLL_INTERVAL_DEFAULT)

            now = time.time()
            gap = now - last_check

            if gap > SLEEP_THRESHOLD_SECONDS:
                log(f"Wake detected (gap of {int(gap)}s). Forced check-changes + optional maps.")
                _run_check_changes("post-sleep resume")
                if maps_on:
                    _run_python_primary_update("post-sleep resume", force_full=False)
                    last_maps = time.time()
                _maybe_metrics("post-sleep", force=True)

            _run_check_changes("periodic")
            if maps_on and maps_iv > 0 and (time.time() - last_maps) >= maps_iv:
                _run_python_primary_update("periodic maps interval", force_full=False)
                last_maps = time.time()
            _maybe_metrics("periodic")
            last_check = time.time()
        except KeyboardInterrupt:
            raise
        except Exception as loop_err:
            # Never die on a single cycle — long-horizon autonomous ops requirement
            log(f"daemon loop error (continuing): {loop_err}")
            _write_heartbeat("loop", False, str(loop_err))
            time.sleep(POLL_INTERVAL_DEFAULT)


# =============================================================================
# Command implementations
# =============================================================================

def cmd_start() -> None:
    """Start the daemon in the background (double-fork, daemonize)."""
    if not hasattr(os, "fork"):
        print("The background daemon requires a Unix-like OS (os.fork is unavailable here).")
        print("On Windows, run 'wikifier daemon run' in a terminal (foreground) or use an external process manager.")
        sys.exit(1)
    ensure_state_dir()

    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Wikifier daemon already running (PID {pid})")
        sys.exit(0)

    log_file = get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    pid = os.fork()
    if pid > 0:
        # Parent: record PID and exit
        write_pid(pid)
        print(f"Wikifier daemon started (PID {pid})")
        print(f"Logs: {log_file}")
        sys.exit(0)

    # Child 1: become session leader
    os.setsid()
    os.umask(0)

    # Redirect stdio to the log file
    with open(log_file, "a", buffering=1, encoding="utf-8") as logf:
        os.dup2(logf.fileno(), sys.stdout.fileno())
        os.dup2(logf.fileno(), sys.stderr.fileno())

    # Redirect stdin from /dev/null
    with open(os.devnull, "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())

    # Now become the real daemon
    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("Daemon received SIGINT, shutting down.")
    finally:
        remove_pid()


def cmd_stop() -> None:
    """Stop a running daemon (SIGKILL if necessary)."""
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Wikifier daemon is not running.")
        remove_pid()
        sys.exit(0)

    try:
        os.kill(pid, signal.SIGKILL)
        print(f"Stopped Wikifier daemon (PID {pid})")
    except ProcessLookupError:
        print("Process already gone.")
    finally:
        remove_pid()


def cmd_status() -> None:
    """Print whether the daemon is running and where its log lives."""
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Wikifier daemon is running (PID {pid})")
        print(f"Log file: {get_log_file()}")
        return

    print("Wikifier daemon is not running.")
    remove_pid()


def cmd_logs(follow: bool = False) -> None:
    """Show the last 100 lines of the daemon log (optionally follow with tail -f)."""
    log_file = get_log_file()
    if not log_file.exists():
        print("No daemon log file found yet.")
        return

    if follow:
        cmd = ["tail", "-n", "100", "-f", str(log_file)]
    else:
        cmd = ["cat", str(log_file)]

    subprocess.run(cmd)


def cmd_restart() -> None:
    """Stop then start the daemon."""
    cmd_stop()
    time.sleep(1)
    cmd_start()


def cmd_install_service() -> None:
    """Generate and install a systemd user service unit (Linux only)."""
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


def generate_systemd_unit() -> str:
    """Generate a systemd user service file content."""
    # Try to find the real `wikifier` executable in PATH for the unit
    wikifier_cmd = "wikifier"
    try:
        which = subprocess.run(
            ["which", "wikifier"],
            capture_output=True,
            text=True,
        )
        if which.returncode == 0:
            wikifier_cmd = which.stdout.strip()
    except Exception:
        pass

    return f"""[Unit]
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


def cmd_uninstall_service() -> None:
    """Remove the systemd user service unit if present."""
    service_file = Path.home() / ".config" / "systemd" / "user" / "wikifier.service"
    if service_file.exists():
        service_file.unlink()
        print("Removed wikifier.service")
        print("Run: systemctl --user daemon-reload")
    else:
        print("No wikifier.service found.")


def cmd_run() -> None:
    """
    The actual foreground runner used by systemd / manual execution.

    Does not double-fork; just runs the loop directly (systemd or the user
    is responsible for keeping it alive).
    """
    ensure_state_dir()
    log_file = get_log_file()
    print(f"Wikifier daemon (foreground) running. Logs: {log_file}")

    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("Foreground daemon stopped by user.")


# =============================================================================
# Main dispatcher (supports both `python -m wikifier.daemon <cmd>` and internal calls)
# =============================================================================

def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: wikifier daemon <start|stop|restart|status|logs|run|"
            "install-service|uninstall-service>"
        )
        sys.exit(1)

    sub = sys.argv[1]
    args = sys.argv[2:]

    if sub == "start":
        cmd_start()
        return
    if sub == "stop":
        cmd_stop()
        return
    if sub == "restart":
        cmd_restart()
        return
    if sub == "status":
        cmd_status()
        return
    if sub == "logs":
        follow = "--follow" in args or "-f" in args
        cmd_logs(follow=follow)
        return
    if sub == "run":
        cmd_run()
        return
    if sub == "install-service":
        cmd_install_service()
        return
    if sub == "uninstall-service":
        cmd_uninstall_service()
        return

    print(f"Unknown daemon command: {sub}")
    sys.exit(1)


if __name__ == "__main__":
    main()
