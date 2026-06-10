"""
Wikifier dashboard server (stdlib-only).

Serves the project folder (so index.html can fetch the wiki artifacts —
browsers block fetch() on file:// pages) and adds a small, safe control
surface for the dashboard:

    GET  /__wikifier/status     -> {"wikifier_serve": true, "project": ...}
    POST /__wikifier/run        -> run a WHITELISTED wikifier command in the
                                   project root; body {"cmd": "update-maps"}
    POST /__wikifier/shutdown   -> stop this server ("kill server" button)

Safety model: binds 127.0.0.1 only, rejects non-local Host headers (DNS
rebinding) and cross-origin POSTs, and only ever executes the fixed command
whitelist below — never caller-supplied argv.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8787

# The ONLY commands the /run endpoint will execute (exact-match keys).
ALLOWED_COMMANDS = {
    "update-maps": ["update-maps"],
    "update-maps --full": ["update-maps", "--full"],
    "check-changes": ["check-changes"],
}
RUN_TIMEOUT_SECONDS = 1800


def _project_root() -> Path:
    env = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    try:
        from .cli import discover_project_root
        return Path(discover_project_root()).resolve()
    except Exception:
        return Path.cwd().resolve()


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "WikifierServe"
    root: Path = Path.cwd()

    # ---- helpers -----------------------------------------------------------
    def _host_is_local(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]", "::1")

    def _origin_is_local(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # same-origin fetches may omit it; Host check still applies
        return origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost")

    def _send_json(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter: suppress the 404 noise for optional files
        msg = fmt % args
        if "file_health.json" in msg or "favicon.ico" in msg or "com.chrome.devtools" in msg:
            return
        super().log_message(fmt, *args)

    # ---- routes ------------------------------------------------------------
    def do_GET(self):
        if not self._host_is_local():
            self._send_json(403, {"error": "non-local Host header rejected"})
            return
        if self.path.split("?")[0] == "/__wikifier/status":
            version = "?"
            try:
                from . import __version__ as version
            except Exception:
                pass
            self._send_json(200, {
                "wikifier_serve": True,
                "version": version,
                "project": self.root.name,
                "root": str(self.root),
                "allowed_commands": sorted(ALLOWED_COMMANDS.keys()),
            })
            return
        super().do_GET()

    def do_POST(self):
        if not (self._host_is_local() and self._origin_is_local()):
            self._send_json(403, {"error": "cross-origin or non-local request rejected"})
            return
        path = self.path.split("?")[0]

        if path == "/__wikifier/shutdown":
            self._send_json(200, {"ok": True, "message": "server stopping"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if path == "/__wikifier/run":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                cmd_key = str(payload.get("cmd", ""))
            except Exception:
                self._send_json(400, {"ok": False, "error": "invalid JSON body"})
                return
            args = ALLOWED_COMMANDS.get(cmd_key)
            if args is None:
                self._send_json(400, {
                    "ok": False,
                    "error": f"command not allowed: {cmd_key!r}",
                    "allowed": sorted(ALLOWED_COMMANDS.keys()),
                })
                return
            env = dict(os.environ, WIKIFIER_PROJECT_ROOT=str(self.root))
            import time
            t0 = time.time()
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "wikifier"] + args,
                    cwd=self.root, env=env, capture_output=True, text=True,
                    timeout=RUN_TIMEOUT_SECONDS,
                )
                out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                self._send_json(200, {
                    "ok": proc.returncode == 0,
                    "cmd": cmd_key,
                    "returncode": proc.returncode,
                    "duration_s": round(time.time() - t0, 1),
                    "output": out[-8000:],  # tail; full detail stays in the terminal/artifacts
                })
            except subprocess.TimeoutExpired:
                self._send_json(200, {
                    "ok": False, "cmd": cmd_key,
                    "error": f"timed out after {RUN_TIMEOUT_SECONDS}s",
                    "duration_s": round(time.time() - t0, 1),
                })
            except Exception as e:
                self._send_json(500, {"ok": False, "cmd": cmd_key, "error": str(e)})
            return

        self._send_json(404, {"error": "unknown endpoint"})


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    port = DEFAULT_PORT
    for a in argv:
        if a.isdigit():
            port = int(a)
    root = _project_root()
    os.chdir(root)
    DashboardHandler.root = root

    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"[wikifier] Serving {root}")
    print(f"[wikifier] Dashboard: http://localhost:{port}/index.html  (Ctrl+C to stop, "
          f"or use the Stop server button in the dashboard)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[wikifier] Server stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
