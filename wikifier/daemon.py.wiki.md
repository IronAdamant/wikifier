# wikifier/daemon.py

**Purpose:** `wikifier daemon start|stop|restart|status|logs|run|install-service|uninstall-service`.

Loop: check-changes every `WIKIFIER_POLL_INTERVAL` (30 s), update-maps at start/wake and every `WIKIFIER_DAEMON_MAPS_INTERVAL` (600 s; `WIKIFIER_DAEMON_MAPS=0` disables), hourly metrics, heartbeat file. `start` refuses `readiness=blocked` without `--force`; `stop` sends SIGTERM and waits before SIGKILL; the systemd unit pins `WorkingDirectory` and `WIKIFIER_PROJECT_ROOT`.
