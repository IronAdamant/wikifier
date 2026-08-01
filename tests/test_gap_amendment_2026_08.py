"""Real-path tests for gap amendment plan G1–G13/G15 closed-when bars.

Drives shipped library functions (session_bootstrap, build_structured_actions,
file_lock, build_map_coverage / run_full_update, library ACS section, protocol
strings). No theater: asserts against live code outputs.
"""

from __future__ import annotations

import importlib
import os
import unittest

from tests._base import REPO_ROOT, TempProjectTestCase

from wikifier import __version__
from wikifier.agent_loop import build_structured_actions, session_bootstrap
from wikifier import cli
from wikifier import locking
from wikifier.library import _generate_acs_section

health_mod = importlib.import_module("wikifier.health")


class TestProtocolVersionPointers(unittest.TestCase):
    """G1: operator package pointers match live major.minor."""

    def test_version_is_4_6(self):
        self.assertTrue(
            __version__.startswith("4.6."),
            f"expected 4.6.x package, got {__version__}",
        )

    def test_skills_run_header_not_4_5(self):
        text = (REPO_ROOT / "skills" / "run.md").read_text(encoding="utf-8")
        # Header / package-notes must not claim current 4.5.x
        first_30 = "\n".join(text.splitlines()[:30])
        self.assertNotIn("package current **4.5.x**", first_30)
        self.assertIn("4.6.x", first_30)
        # SELECTIVE WORK excludes Initial stubs (G3)
        self.assertIn("actionable", text)
        self.assertIn("Initial", text)
        self.assertRegex(
            text,
            r"SELECTIVE WORK.*actionable.*Initial",
        )
        # G15 CLI-at-scale policy present
        self.assertIn("CLI-at-scale policy", text)
        # G8 ready_for_daemon not Map Ready alone
        self.assertIn("ready_for_daemon", text)
        self.assertIn("not Map Ready alone", text)

    def test_claude_md_not_4_5(self):
        for name in ("Claude.md", "CLAUDE.md"):
            p = REPO_ROOT / name
            if not p.is_file():
                continue
            t = p.read_text(encoding="utf-8")
            self.assertNotIn("currently 4.5.x", t)
            self.assertIn("4.6.x", t)


class TestBootstrapMessageAndActions(TempProjectTestCase):
    """G2/G5/G6: bootstrap message + blocker actions."""

    def test_bootstrap_message_blocked_never_says_ready(self):
        # Fresh temp root: no cache, no health → blocked
        boot = session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"))
        readiness = boot.get("readiness")
        msg = str(boot.get("message") or "")
        if readiness == "blocked":
            self.assertIn("readiness=blocked", msg)
            self.assertNotRegex(msg, r"^session_bootstrap ready")
            self.assertNotIn("session_bootstrap ready —", msg)
        # Always embeds readiness=
        self.assertIn("readiness=", msg)

    def test_blockers_produce_priority_leq_2_map_or_health(self):
        acts = build_structured_actions(
            blockers=[
                "No import map (run update-maps first).",
                "No file_health — run seed-health or update-maps.",
            ],
            scope_warnings=["monitored_paths is bare '.' — thrash risk"],
            red=0,
            actionable_yellow=0,
            clean=True,
        )
        kinds = {a["action"] for a in acts}
        self.assertIn("update_maps", kinds)
        self.assertIn("seed_health", kinds)
        self.assertIn("fix_scope", kinds)
        for a in acts:
            if a["action"] in ("update_maps", "seed_health"):
                self.assertLessEqual(int(a["priority"]), 2, a)
            if a["action"] == "fix_scope":
                self.assertLessEqual(int(a["priority"]), 2, a)

    def test_map_incomplete_action_priority(self):
        acts = build_structured_actions(
            map_coverage={
                "complete": False,
                "files_remaining_dirty": 12,
                "files_skipped": 12,
                "budget_max_files": 5,
            },
            red=0,
            actionable_yellow=0,
        )
        incomplete = [a for a in acts if a["action"] == "update_maps_until_complete"]
        self.assertTrue(incomplete)
        self.assertLessEqual(int(incomplete[0]["priority"]), 2)
        self.assertIn("success alone", incomplete[0]["reason"].lower())

    def test_stub_only_map_first_ok_no_wiki_refresh(self):
        acts = build_structured_actions(
            stub_yellow=100,
            actionable_yellow=0,
            red=0,
            actionable_yellow_files=[],
            clean=False,
        )
        kinds = {a["action"] for a in acts}
        self.assertIn("map_first_ok", kinds)
        self.assertNotIn("wiki_refresh", kinds)


class TestMapCoverageHonesty(TempProjectTestCase):
    """G5: update_maps surfaces map_complete / map_ready."""

    def test_run_full_update_exposes_map_ready_flags(self):
        self.write("pkg/a.py", "import os\n")
        (self.root / "monitored_paths.txt").write_text("pkg/\n", encoding="utf-8")
        (self.root / "map_paths.txt").write_text("pkg/\n", encoding="utf-8")
        res = cli.run_full_update(root=self.root, directory="pkg/")
        self.assertTrue(res.get("success"), res)
        self.assertIn("map_coverage", res)
        self.assertIn("map_complete", res)
        self.assertIn("map_ready", res)
        # map_ready must track complete + remaining dirty
        mc = res["map_coverage"]
        expected_ready = bool(mc.get("complete")) and int(
            mc.get("files_remaining_dirty") or 0
        ) == 0
        self.assertEqual(res["map_ready"], expected_ready)
        self.assertEqual(res["map_complete"], bool(mc.get("complete")))

    def test_budgeted_max_files_incomplete_flags(self):
        for i in range(6):
            self.write(f"src/m{i}.py", f"x={i}\n")
        (self.root / "monitored_paths.txt").write_text("src/\n", encoding="utf-8")
        (self.root / "map_paths.txt").write_text("src/\n", encoding="utf-8")
        res = cli.run_full_update(
            root=self.root, directory="src/", max_files=2
        )
        self.assertTrue(res.get("success"), res)
        self.assertIn("map_coverage", res)
        # With budget, remaining dirty may be > 0
        rem = int((res.get("map_coverage") or {}).get("files_remaining_dirty") or 0)
        if rem > 0 or (res.get("map_coverage") or {}).get("complete") is False:
            self.assertFalse(res.get("map_ready"))
            acts = build_structured_actions(map_coverage=res["map_coverage"])
            self.assertTrue(
                any(a["action"] == "update_maps_until_complete" for a in acts)
            )


class TestLockTimeout(TempProjectTestCase):
    """G13: file_lock honors finite timeout."""

    def test_timeout_raises_when_held(self):
        """Hold exclusive lock on a second fd; finite timeout must raise (G13)."""
        if locking.fcntl is None:
            self.skipTest("fcntl not available")
        lock_path = self.root / locking.LOCK_FILE_NAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            locking.fcntl.flock(holder_fd, locking.fcntl.LOCK_EX)
            contender_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                with self.assertRaises(locking.LockTimeoutError):
                    locking._acquire_exclusive(contender_fd, 0.25)
            finally:
                os.close(contender_fd)
        finally:
            locking.fcntl.flock(holder_fd, locking.fcntl.LOCK_UN)
            os.close(holder_fd)

    def test_reentrant_still_works(self):
        with locking.file_lock(self.root):
            with locking.file_lock(self.root):
                pass  # nested re-entrant


class TestAcsLibrarySection(unittest.TestCase):
    """G9: library ACS prefers actionable."""

    def test_acs_section_prefers_actionable(self):
        cache = {
            "_acs_summary": {
                "total_scored_edges": 100,
                "avg_confidence": 0.7,
                "low_conf_edges": 40,
                "actionable_low_conf_edges": 5,
                "low_conf_threshold": 0.65,
                "reason_code_counts": {
                    "external_or_bare": 30,
                    "unresolved_project": 5,
                },
                "sample_low_conf_explanations": ["raw sample"],
            }
        }
        lines = _generate_acs_section(cache)
        text = "\n".join(lines)
        self.assertIn("actionable_low_conf", text)
        self.assertIn("reason_code_counts", text)
        self.assertIn("thrash", text.lower())
        self.assertIn("actionable_low_conf_edges", text)
        self.assertIn("actionable", text.lower())


class TestReadinessTiersDocShape(TempProjectTestCase):
    """G4: readiness tiers match code for missing map/health."""

    def test_no_map_is_blocked(self):
        ready = health_mod.assess_autonomous_readiness(self.root)
        self.assertEqual(ready.get("readiness"), "blocked")
        blockers = " ".join(ready.get("blockers") or [])
        self.assertTrue(
            "import map" in blockers.lower() or "file_health" in blockers.lower(),
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
