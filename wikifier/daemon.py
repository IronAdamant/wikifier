"""
Background daemon: keeps health and the dependency map fresh on long-running projects.

  wikifier daemon start|stop|restart|status|logs [-f]|run|install-service|uninstall-service

- Every ``WIKIFIER_POLL_INTERVAL`` seconds (default 30): check-changes.
- update-maps at start, on wake from sleep, and at most every
  ``WIKIFIER_DAEMON_MAPS_INTERVAL`` seconds (default 600; 0 = start/wake only).
  ``WIKIFIER_DAEMON_MAPS=0`` disables background update-maps entirely.
- A poll gap longer than ``SLEEP_THRESHOLD_SECONDS`` is treated as wake-from-sleep.
- ``start`` refuses projects whose readiness is ``blocked`` (pass ``--force``).
- ``stop`` sends SIGTERM and waits; SIGKILL only if the loop does not exit.
- State (pid, log, heartbeat) lives in ``<project>/.wikifier_staging``.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import health_pkg as health_mod
from .api import check_changes, run_full_update
from .paths import resolve_root

POLL_INTERVAL_DEFAULT = int(os.environ.get("WIKIFIER_POLL_INTERVAL", "30") or "30")
SLEEP_THRESHOLD_SECONDS = 120
STOP_GRACE_SECONDS = 15
LOG_DIR_NAME = ".wikifier_staging"
LOG_FILE_NAME = "daemon.log"
PID_FILE_NAME = "wikifier.pid"


def _maps_enabled() -> bool:
    return os.environ.get("WIKIFIER_DAEMON_MAPS", "1").strip().lower() not in ("0", "false", "no")


def _maps_interval_sec() -> int:
    try:
        return max(0, int(os.environ.get("WIKIFIER_DAEMON_MAPS_INTERVAL", "600")))
    except ValueError:
        return 600


def project_root() -> Path:
    return resolve_root()


def get_state_dir() -> Path:
    return project_root() / LOG_DIR_NAME


def get_pid_file() -> Path:
    return get_state_dir() / PID_FILE_NAME


def get_log_file() -> Path:
    return get_state_dir() / LOG_FILE_NAME


def ensure_state_dir() -> Path:
    state = get_state_dir()
    state.mkdir(parents=True, exist_ok=True)
    return state


def write_pid(pid: int) -> None:
    ensure_state_dir()
    get_pid_file().write_text(str(pid))


def read_pid() -> Optional[int]:
    try:
        return int(get_pid_file().read_text().strip())
    except (OSError, ValueError):
        return None


def remove_pid() -> None:
    try:
        get_pid_file().unlink()
    except FileNotFoundError:
        pass


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def log(msg: str, also_to_file: bool = True) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    if also_to_file:
        try:
            with open(get_log_file(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:  # logging must never kill the loop
            print(f"[daemon] log write failed: {exc}", file=sys.stderr)


def _write_heartbeat(event: str, ok: bool, detail: str = "") -> None:
    """Persist the last step outcome for autonomous-status."""
    path = ensure_state_dir() / "daemon_heartbeat.json"
    previous = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8")) or {}
        except ValueError:
            previous = {}
    streak = 0 if ok else int(previous.get("consecutive_failures", 0) or 0) + 1
    path.write_text(json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "ok": ok,
        "detail": (detail or "")[:400],
        "consecutive_failures": streak,
        "project_root": str(project_root()),
    }, indent=2) + "\n", encoding="utf-8")
    if streak >= 5:
        log(f"WARNING: {streak} consecutive daemon step failures — inspect daemon.log; "
            "consider lean monitored_paths or WIKIFIER_DAEMON_MAPS=0")


def _run_check_changes(reason: str) -> None:
    res = check_changes(project_root=project_root(), timeout=300)
    ok = bool(res.get("success"))
    log(f"check-changes ({reason}): {res.get('message') if ok else res.get('error')}")
    _write_heartbeat(f"check-changes:{reason}", ok, "" if ok else str(res.get("error")))


def _run_update_maps(reason: str, force_full: bool = False) -> None:
    res = run_full_update(root=project_root(), force_full=force_full)
    ok = bool(res.get("success"))
    log(
        f"update-maps ({reason}): parsed={res.get('files_parsed')}/{res.get('files_to_reparse')} "
        f"edges={res.get('edges_persisted')} complete={res.get('map_complete')} success={ok}"
        + ("" if ok else f" error={res.get('error')}")
    )
    _write_heartbeat(f"update-maps:{reason}", ok, "" if ok else str(res.get("error")))


_STOP_REQUESTED = False


def _request_stop(signum, _frame) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    log(f"received signal {signum}; stopping after the current step")


def daemon_loop(max_cycles: Optional[int] = None) -> None:
    """Run until SIGTERM/SIGINT (or ``max_cycles`` polls, for tests)."""
    ensure_state_dir()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _request_stop)
    maps_interval = _maps_interval_sec()
    maps_on = _maps_enabled()
    try:
        metrics_interval = max(0, int(os.environ.get("WIKIFIER_DAEMON_METRICS_INTERVAL", "3600") or "3600"))
    except ValueError:
        metrics_interval = 3600
    log(
        f"daemon started for {project_root()} (check every {POLL_INTERVAL_DEFAULT}s; maps="
        + ("off" if not maps_on else f"every {maps_interval}s" if maps_interval else "start/wake only")
        + ")"
    )
    last_metrics = 0.0

    def metrics(reason: str, force: bool = False) -> None:
        nonlocal last_metrics
        now = time.time()
        if not force and (metrics_interval <= 0 or now - last_metrics < metrics_interval):
            return
        snap = health_mod.write_metrics_snapshot(project_root(), source=f"daemon:{reason}")
        log(f"metrics ({reason}): staging_bytes={snap.get('staging_bytes')} score={snap.get('health_score')}")
        last_metrics = now

    _run_check_changes("start")
    last_maps = 0.0
    if maps_on:
        _run_update_maps("start")
        last_maps = time.time()
    metrics("start", force=True)
    last_poll = time.time()
    cycles = 0
    while not _STOP_REQUESTED and (max_cycles is None or cycles < max_cycles):
        cycles += 1
        try:
            time.sleep(POLL_INTERVAL_DEFAULT)
            if _STOP_REQUESTED:
                break
            if time.time() - last_poll > SLEEP_THRESHOLD_SECONDS + POLL_INTERVAL_DEFAULT:
                log("wake from sleep detected")
                if maps_on:
                    _run_update_maps("wake")
                    last_maps = time.time()
                metrics("wake", force=True)
            _run_check_changes("periodic")
            if maps_on and maps_interval and time.time() - last_maps >= maps_interval:
                _run_update_maps("interval")
                last_maps = time.time()
            metrics("periodic")
        except Exception as exc:  # one bad cycle must not end a long-running daemon
            log(f"daemon loop error (continuing): {type(exc).__name__}: {exc}")
            _write_heartbeat("loop", False, str(exc))
        last_poll = time.time()
    log("daemon stopped")


def _readiness_blocked() -> Optional[str]:
    ready = health_mod.assess_autonomous_readiness(project_root(), write_metrics=False)
    if ready.get("readiness") == "blocked":
        return "; ".join(ready.get("blockers") or ["readiness=blocked"])
    return None


def cmd_start(force: bool = False) -> int:
    """Start the daemon in the background (fork + setsid)."""
    if not hasattr(os, "fork"):
        print("The background daemon needs os.fork (Unix). On Windows run `wikifier daemon run` "
              "in a terminal or under a process manager.")
        return 1
    ensure_state_dir()
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Wikifier daemon already running (PID {pid})")
        return 0
    blocked = None if force else _readiness_blocked()
    if blocked:
        print(f"Refusing to start: project readiness is blocked ({blocked}). Fix it or pass --force.")
        return 2
    log_file = get_log_file()
    pid = os.fork()
    if pid > 0:
        write_pid(pid)
        print(f"Wikifier daemon started (PID {pid})")
        print(f"Logs: {log_file}")
        return 0
    os.setsid()
    with open(log_file, "a", buffering=1, encoding="utf-8") as logf:
        os.dup2(logf.fileno(), sys.stdout.fileno())
        os.dup2(logf.fileno(), sys.stderr.fileno())
    with open(os.devnull, "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("daemon interrupted")
    finally:
        remove_pid()
        os._exit(0)


def cmd_stop() -> int:
    """SIGTERM the daemon and wait; SIGKILL only if it does not exit in time."""
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Wikifier daemon is not running.")
        remove_pid()
        return 0
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + STOP_GRACE_SECONDS + POLL_INTERVAL_DEFAULT
    while time.time() < deadline and is_process_running(pid):
        time.sleep(0.25)
    if is_process_running(pid):
        os.kill(pid, signal.SIGKILL)
        print(f"Daemon (PID {pid}) did not exit in time; killed.")
    else:
        print(f"Stopped Wikifier daemon (PID {pid})")
    remove_pid()
    return 0


def cmd_status() -> int:
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Wikifier daemon is running (PID {pid})")
        print(f"Log file: {get_log_file()}")
        return 0
    print("Wikifier daemon is not running.")
    remove_pid()
    return 0


def cmd_logs(follow: bool = False, lines: int = 100) -> int:
    log_file = get_log_file()
    if not log_file.exists():
        print("No daemon log file found yet.")
        return 0
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f.readlines()[-lines:]:
            print(line, end="")
        if not follow:
            return 0
        try:
            while True:
                line = f.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            return 0


def cmd_restart(force: bool = False) -> int:
    cmd_stop()
    return cmd_start(force=force)


def generate_systemd_unit(root: Optional[Path] = None) -> str:
    """systemd user unit that runs the daemon in the foreground for one project."""
    root = root or project_root()
    executable = shutil.which("wikifier") or f"{sys.executable} -m wikifier"
    log_path = root / LOG_DIR_NAME / LOG_FILE_NAME
    return f"""[Unit]
Description=Wikifier daemon for {root}
After=network.target

[Service]
Type=simple
WorkingDirectory={root}
Environment=WIKIFIER_PROJECT_ROOT={root}
ExecStart={executable} daemon run
Restart=always
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec={STOP_GRACE_SECONDS + POLL_INTERVAL_DEFAULT}
StandardOutput=append:{log_path}
StandardError=append:{log_path}

[Install]
WantedBy=default.target
"""


def _service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "wikifier.service"


def cmd_install_service() -> int:
    if platform.system().lower() != "linux":
        print("systemd user services are Linux-only. Use `wikifier daemon start` (or launchd/tmux) instead.")
        return 1
    path = _service_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_state_dir()
    path.write_text(generate_systemd_unit())
    print(f"Wrote {path}\nEnable with:\n  systemctl --user daemon-reload\n  systemctl --user enable --now wikifier")
    return 0


def cmd_uninstall_service() -> int:
    path = _service_path()
    if path.exists():
        path.unlink()
        print("Removed wikifier.service — run: systemctl --user daemon-reload")
    else:
        print("No wikifier.service found.")
    return 0


def cmd_run() -> int:
    """Foreground loop (for systemd or a terminal)."""
    ensure_state_dir()
    print(f"Wikifier daemon (foreground). Logs: {get_log_file()}")
    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("foreground daemon stopped by user")
    return 0


USAGE = "Usage: wikifier daemon <start [--force]|stop|restart|status|logs [-f]|run|install-service|uninstall-service>"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE)
        return 1
    action, rest = argv[0], argv[1:]
    force = "--force" in rest
    handlers = {
        "start": lambda: cmd_start(force=force),
        "stop": cmd_stop,
        "restart": lambda: cmd_restart(force=force),
        "status": cmd_status,
        "logs": lambda: cmd_logs(follow="-f" in rest or "--follow" in rest),
        "run": cmd_run,
        "install-service": cmd_install_service,
        "uninstall-service": cmd_uninstall_service,
    }
    handler = handlers.get(action)
    if handler is None:
        print(f"Unknown daemon command: {action}\n{USAGE}")
        return 1
    return int(handler() or 0)


if __name__ == "__main__":
    sys.exit(main())
