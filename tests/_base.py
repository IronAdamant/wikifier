"""Shared temp-project scaffolding for the Wikifier test suite (stdlib only).

Each TestCase gets a fresh tempfile.TemporaryDirectory as its project root,
with WIKIFIER_PROJECT_ROOT pointed at it for the duration of the test and
restored afterwards. This guarantees tests never read or mutate the Wikifier
repository's own dogfood state (file_health.json, import_cache.json, journal).
"""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

# Make the repo importable no matter where the runner was started from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TempProjectTestCase(unittest.TestCase):
    """Base class: isolated temp project root + env var hygiene."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(prefix="wikifier_test_")
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name).resolve()

        self._old_env = os.environ.get("WIKIFIER_PROJECT_ROOT")
        os.environ["WIKIFIER_PROJECT_ROOT"] = str(self.root)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._old_env is None:
            os.environ.pop("WIKIFIER_PROJECT_ROOT", None)
        else:
            os.environ["WIKIFIER_PROJECT_ROOT"] = self._old_env

    # ---- helpers ----

    def write(self, rel: str, content: str) -> Path:
        """Write a file under the temp project root, creating parent dirs."""
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def reset_js_parser_state(self):
        """Clear module-level caches/singletons in the JS parser + BREE so
        state from a previous test (or project root) cannot leak."""
        from wikifier.parsers import javascript as js
        from wikifier.parsers import bree
        bree.reset_bree_engine()
        js._clear_parse_cache()
        js._clear_reexport_cache()
        try:
            js._clear_package_marker_cache()
        except Exception:
            pass


def call_with_timeout(fn, *args, timeout=8.0, **kwargs):
    """Run fn(*args, **kwargs) in a daemon thread with a hard timeout.

    Returns ("ok", result) or ("timeout", None). Needed because the current
    Python-primary workflow functions (cli.record_change / mark_green /
    check_changes) self-deadlock on the non-reentrant project flock (see
    tests/test_health.py); a plain call would hang the suite forever instead
    of failing. Exceptions from fn are re-raised in the caller.
    """
    box = {}

    def _target():
        try:
            box["result"] = fn(*args, **kwargs)
        except BaseException as e:  # surfaced to the test below
            box["exc"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return ("timeout", None)
    if "exc" in box:
        raise box["exc"]
    return ("ok", box.get("result"))


def find_edge(edges, **criteria):
    """Return the first edge dict matching all key=value criteria, or None."""
    for e in edges:
        if all(e.get(k) == v for k, v in criteria.items()):
            return e
    return None
