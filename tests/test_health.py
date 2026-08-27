"""Health workflow tests (Phase 0 of Findings/2026-06-10-Fix-Plan.md).

Desired contract:
- record-change -> 🟡 Yellow entry + pending_updates.md line + journal entry
- mark-green   -> 🟢 Green entry + pending line cleared
- check-changes auto-yellows dirty source files but honors exclude_patterns.txt (W8)

All operations run against an isolated temp project root passed explicitly as
project_root= — the Wikifier repo's own health state is never touched.

Nested project flock is re-entrant (locking._HELD_LOCKS). call_with_timeout is
a hang-guard only — workflow tests must complete, not be named DEADLOCK.
"""

import unittest
from datetime import datetime

from tests._base import TempProjectTestCase, call_with_timeout

from wikifier import cli

# NOTE: `from wikifier import health` returns the package-level health()
# *function* (cli re-export shadows the submodule), so import the module
# explicitly via importlib.
import importlib
health_mod = importlib.import_module("wikifier.health")

# Module-level memo: once the workflow deadlock is observed, later tests fail
# fast instead of each burning the full timeout (keeps the suite quick).
_DEADLOCK = {"seen": False}

_DEADLOCK_MSG = (
    "Workflow function exceeded 8s hang-guard (unexpected; nested flock should "
    "be re-entrant via locking._HELD_LOCKS)."
)


class WorkflowTestCase(TempProjectTestCase):
    def call_workflow(self, fn, *args, **kwargs):
        if _DEADLOCK["seen"]:
            self.fail(_DEADLOCK_MSG + " (detected earlier in this run; failing fast)")
        status, result = call_with_timeout(fn, *args, timeout=8.0, **kwargs)
        if status == "timeout":
            _DEADLOCK["seen"] = True
            self.fail(_DEADLOCK_MSG)
        return result

    def entries(self):
        return health_mod.load_health(self.root).get("entries", {})

    def pending_text(self):
        p = self.root / "pending_updates.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class TestHealthLayerDirect(TempProjectTestCase):
    """The underlying health primitives work when called without the cli
    wrapper's outer lock — proving the deadlock lives in the cli nesting,
    not in health.py itself."""

    def test_upsert_yellow_then_green_with_pending_roundtrip(self):
        self.write("src/app.py", "print('hi')\n")

        health_mod.upsert_entry(self.root, "src/app.py", "🟡 Yellow", "edit recorded")
        health_mod.add_to_pending(self.root, "src/app.py", "review needed")
        entries = health_mod.load_health(self.root)["entries"]
        self.assertTrue(entries["src/app.py"]["status"].startswith("🟡"))
        pending = (self.root / "pending_updates.md").read_text(encoding="utf-8")
        self.assertIn("src/app.py", pending)

        health_mod.upsert_entry(self.root, "src/app.py", "🟢 Green", "wiki verified")
        health_mod.remove_from_pending(self.root, "src/app.py")
        entries = health_mod.load_health(self.root)["entries"]
        self.assertTrue(entries["src/app.py"]["status"].startswith("🟢"))
        pending = (self.root / "pending_updates.md").read_text(encoding="utf-8")
        self.assertNotIn("src/app.py", pending)

        # Markdown view regenerated alongside the JSON source of truth.
        md = (self.root / "file_health.md").read_text(encoding="utf-8")
        self.assertIn("src/app.py", md)


class TestRecordChangeMarkGreen(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.write("src/app.py", "print('hi')\n")

    def _journal_text(self):
        jf = self.root / "journal" / datetime.now().strftime("%Y/%m/%d.md")
        return jf.read_text(encoding="utf-8") if jf.exists() else ""

    def test_record_change_marks_yellow_pending_and_journal(self):
        result = self.call_workflow(
            cli.record_change, "src/app.py", "test edit reason", project_root=self.root
        )
        self.assertTrue(result["success"], result)
        self.assertEqual(result["project_root"], str(self.root))

        entry = self.entries().get("src/app.py")
        self.assertIsNotNone(entry, "record_change must create a health entry")
        self.assertTrue(entry["status"].startswith("🟡"), entry["status"])
        self.assertIn("test edit reason", entry["reason"])

        self.assertIn("src/app.py", self.pending_text())
        self.assertIn("test edit reason", self.pending_text())

        journal = self._journal_text()
        self.assertIn("record-change", journal)
        self.assertIn("src/app.py", journal)
        self.assertIn("test edit reason", journal)

        # Generated artifacts exist in the temp root only.
        self.assertTrue((self.root / "file_health.json").exists())
        self.assertTrue((self.root / "file_health.md").exists())

    def test_mark_green_flips_status_and_clears_pending(self):
        self.call_workflow(
            cli.record_change, "src/app.py", "test edit reason", project_root=self.root
        )
        result = self.call_workflow(
            cli.mark_green, "src/app.py", "wiki refreshed", project_root=self.root
        )
        self.assertTrue(result["success"], result)

        entry = self.entries().get("src/app.py")
        self.assertIsNotNone(entry)
        self.assertTrue(entry["status"].startswith("🟢"), entry["status"])
        self.assertIn("wiki refreshed", entry["reason"])

        self.assertNotIn("src/app.py", self.pending_text())


class TestCheckChangesExcludes(WorkflowTestCase):
    def test_check_changes_yellows_dirty_source_files(self):
        self.write("app.py", "print('hi')\n")
        result = self.call_workflow(cli.check_changes, project_root=self.root)
        self.assertTrue(result["success"], result)
        self.assertGreaterEqual(result["changes_detected"], 1)
        entry = self.entries().get("app.py")
        self.assertIsNotNone(entry, "new source file must be auto-yellowed")
        self.assertTrue(entry["status"].startswith("🟡"))

    def test_excluded_directory_not_auto_yellowed(self):
        self.write("exclude_patterns.txt", "generated_stuff/*\n")
        self.write("app.py", "print('hi')\n")
        self.write("generated_stuff/inner.py", "print('generated')\n")
        self.call_workflow(cli.check_changes, project_root=self.root)
        entries = self.entries()
        self.assertIn("app.py", entries)
        self.assertNotIn("generated_stuff/inner.py", entries,
                         "files under an excluded directory must not be auto-yellowed")

    def test_excluded_file_glob_not_auto_yellowed(self):
        self.write("exclude_patterns.txt", "*.gen.py\n")
        self.write("app.py", "print('hi')\n")
        self.write("foo.gen.py", "print('generated')\n")
        self.call_workflow(cli.check_changes, project_root=self.root)
        entries = self.entries()
        self.assertIn("app.py", entries)
        self.assertNotIn("foo.gen.py", entries,
                         "files matching exclude_patterns.txt must not be auto-yellowed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
