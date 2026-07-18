"""Real-path tests for `wikifier init` lean path-list templates (4.6.8+).

Drives the shipped shell launcher (`./wikifier.sh init --target …`) so a
silent bare-`.` seed cannot regress without failing the suite.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from tests._base import REPO_ROOT, TempProjectTestCase


class TestInitSeedTemplates(TempProjectTestCase):
    """Acceptance: init must not leave only silent bare '.' without guidance."""

    def _run_init(self, target: Path) -> subprocess.CompletedProcess:
        script = REPO_ROOT / "wikifier.sh"
        self.assertTrue(script.is_file(), f"missing shipped launcher: {script}")
        # Isolated env: do not inherit WIKIFIER_PROJECT_ROOT from the test harness
        # (init --target should write into the given directory, not the harness root).
        env = os.environ.copy()
        env.pop("WIKIFIER_PROJECT_ROOT", None)
        return subprocess.run(
            ["bash", str(script), "init", "--target", str(target), "--no-copy"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_init_seeds_guided_monitored_and_map_paths(self):
        target = self.root / "fresh_project"
        target.mkdir()
        proc = self._run_init(target)
        self.assertEqual(
            proc.returncode,
            0,
            f"init failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        )

        mon = target / "monitored_paths.txt"
        maps = target / "map_paths.txt"
        self.assertTrue(mon.is_file(), "init must create monitored_paths.txt")
        self.assertTrue(maps.is_file(), "init must create map_paths.txt")

        mon_text = mon.read_text(encoding="utf-8")
        map_text = maps.read_text(encoding="utf-8")

        # Must not be the old silent single-character default.
        stripped = mon_text.strip()
        self.assertNotEqual(
            stripped,
            ".",
            "monitored_paths.txt must not be silent bare '.' only",
        )
        self.assertIn("#", mon_text, "monitored_paths.txt must include guidance comments")
        self.assertRegex(
            mon_text,
            r"(?i)(lean|package root|thrash|map_paths)",
            "monitored_paths.txt should mention lean roots / thrash / map_paths",
        )
        # Active path may still be bare "." for tiny toys, but only with comments above.
        active_mon = [
            ln.strip()
            for ln in mon_text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        self.assertTrue(active_mon, "expected at least one non-comment monitored path")

        self.assertIn("#", map_text, "map_paths.txt must include guidance comments")
        self.assertRegex(
            map_text,
            r"(?i)(import-map|package root|update-maps|monitored_paths)",
            "map_paths.txt should document independent map package roots",
        )
        # Template should not seed bare "." as the only map root.
        active_map = [
            ln.strip()
            for ln in map_text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        self.assertNotIn(
            ".",
            active_map,
            "map_paths template must not activate bare '.' as map root",
        )

        excl = target / "exclude_patterns.txt"
        self.assertTrue(excl.is_file())
        excl_text = excl.read_text(encoding="utf-8")
        self.assertIn("target", excl_text.splitlines())

    def test_packaged_launcher_matches_root_init_seed(self):
        """Root and packaged wikifier.sh must stay in sync for init templates."""
        root_sh = (REPO_ROOT / "wikifier.sh").read_text(encoding="utf-8")
        pkg_sh = (REPO_ROOT / "wikifier" / "scripts" / "wikifier.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("map_paths.txt", root_sh)
        self.assertIn("lean package roots", root_sh)
        self.assertEqual(
            root_sh,
            pkg_sh,
            "wikifier/scripts/wikifier.sh must match root wikifier.sh (init templates)",
        )


if __name__ == "__main__":
    unittest.main()
