"""Wiki verification on mark_green, the widened watch set, and git-driven record_changes."""

from __future__ import annotations

import shutil
import subprocess
import unittest

from tests._base import TempProjectTestCase
from wikifier import api, health_pkg as health
from wikifier.health_pkg.verify import public_symbols

HAS_GIT = shutil.which("git") is not None


class TestPublicSymbols(TempProjectTestCase):
    def test_python_uses_all_or_public_top_level_names(self):
        a = self.write("a.py", "def pub(): pass\ndef _priv(): pass\nclass Thing: pass\nX = 1\n")
        b = self.write("b.py", "__all__ = ['only']\ndef only(): pass\ndef other(): pass\n")
        self.assertEqual(public_symbols(a), ["Thing", "pub"])
        self.assertEqual(public_symbols(b), ["only"])

    def test_js_exports_ignore_comments_and_strings(self):
        f = self.write("m.ts", (
            "export function foo() {}\n// export function inComment() {}\n"
            "const s = 'export function inString() {}';\n"
            "export const BAR = 1;\nexport { x as y };\nexport default class Widget {}\n"
        ))
        self.assertEqual(public_symbols(f), ["BAR", "Widget", "foo", "y"])

    def test_unsupported_language_is_none(self):
        self.assertIsNone(public_symbols(self.write("main.rs", "pub fn x() {}\n")))


class TestMarkGreenVerification(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.write("store.py", "def load():\n    return 1\n")
        self.write("store.py.wiki.md", "# store.py\n\n`load()` reads.\n")
        res = api.mark_green("store.py", "baseline")
        self.assertTrue(res["success"], res)
        self.assertEqual(res["verification"], "verified")

    def test_new_symbol_without_wiki_update_is_refused(self):
        self.write("store.py", "def load():\n    return 1\n\ndef save(x):\n    pass\n")
        res = api.mark_green("store.py", "added save")
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "WikiVerificationError")
        codes = {i["code"] for i in res["issues"]}
        self.assertEqual(codes, {"undocumented_new_symbols", "wiki_not_updated_for_api_change"})
        # A refused Green must not advance the baseline it is judged against.
        self.assertEqual(health.load_health(self.root)["entries"]["store.py"]["public_symbols"], "load")

    def test_documented_new_symbol_passes(self):
        self.write("store.py", "def load():\n    return 1\n\ndef save(x):\n    pass\n")
        self.write("store.py.wiki.md", "# store.py\n\n`load()` reads, `save(x)` writes.\n")
        res = api.mark_green("store.py", "added save")
        self.assertTrue(res["success"], res)
        self.assertEqual(health.load_health(self.root)["entries"]["store.py"]["public_symbols"], "load save")

    def test_internal_change_needs_no_wiki_edit(self):
        self.write("store.py", "def load():\n    return 2  # bug fix\n")
        self.assertTrue(api.mark_green("store.py", "fixed load")["success"])

    def test_removed_symbol_still_referenced_is_refused(self):
        self.write("store.py", "def read():\n    return 1\n")
        self.write("store.py.wiki.md", "# store.py\n\n`read()` reads (was `load`).\n")
        res = api.mark_green("store.py", "renamed")
        self.assertFalse(res["success"])
        self.assertEqual([i["code"] for i in res["issues"]], ["wiki_mentions_removed_symbols"])

    def test_force_needs_reason_and_is_recorded(self):
        self.write("store.py", "def load():\n    return 1\n\ndef save(x):\n    pass\n")
        self.assertFalse(api.mark_green("store.py", force=True)["success"])
        res = api.mark_green("store.py", "save() is internal-only, documented elsewhere", force=True)
        self.assertTrue(res["success"], res)
        self.assertEqual(res["verification"], "forced")
        self.assertEqual(health.get_summary(self.root)["green_breakdown"]["forced"], 1)

    def test_no_wiki_is_allowed_but_counted(self):
        self.write("plain.py", "def f(): pass\n")
        res = api.mark_green("plain.py", "no wiki yet")
        self.assertEqual(res["verification"], "no_wiki")
        breakdown = health.get_summary(self.root)["green_breakdown"]
        self.assertEqual((breakdown["verified"], breakdown["no_wiki"]), (1, 1))

    def test_verify_wikis_audits_greens(self):
        self.write("store.py", "def load():\n    return 1\n\ndef save(x):\n    pass\n")
        res = api.verify_wikis()
        self.assertEqual(res["failing_count"], 1)
        self.assertEqual(res["failing"][0]["file"], "store.py")


class TestWatchScope(TempProjectTestCase):
    def test_mapped_file_outside_monitored_paths_is_flagged(self):
        self.write("monitored_paths.txt", "app.py\n")
        self.write("app.py", "import lib\n")
        self.write("lib.py", "x = 1\n")
        api.update_maps(full=True)
        api.mark_green("lib.py", "baseline")
        self.write("lib.py", "x = 2\n")
        res = api.check_changes()
        self.assertIn("lib.py", res["changed_files"], res)
        self.assertIn("lib.py", (self.root / "pending_updates.md").read_text())


@unittest.skipUnless(HAS_GIT, "git not installed")
class TestRecordChanges(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write("src/a.py", "def a(): pass\n")
        self.write("src/b.py", "def b(): pass\n")
        self.write("old.py", "x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_missing_reasons_write_nothing(self):
        self.write("src/a.py", "def a(): return 1\n")
        res = api.record_changes()
        self.assertFalse(res["success"])
        self.assertEqual(res["missing_reasons"], ["src/a.py"])
        self.assertEqual(res["template"], {"src/a.py": ""})
        self.assertFalse((self.root / "journal").exists())

    def test_reasons_by_path_and_prefix_with_deletion_and_rename(self):
        self.write("src/a.py", "def a(): return 1\n")
        self.write("src/new.py", "y = 1\n")
        self.git("mv", "src/b.py", "src/b2.py")
        (self.root / "old.py").unlink()
        res = api.record_changes(
            {"src/a.py": "fix a", "src/": "src work", "nothing/*": "unused"},
            default_reason="cleanup",
        )
        self.assertTrue(res["success"], res)
        reasons = {p["file"]: p["reason"] for p in res["plan"]}
        self.assertEqual(reasons["src/a.py"], "fix a")
        self.assertEqual(reasons["src/new.py"], "src work")
        self.assertEqual(reasons["old.py"], "cleanup")
        self.assertIn("renamed to src/b2.py", reasons["src/b.py"])
        self.assertEqual(sorted(res["deleted"]), ["old.py", "src/b.py"])
        self.assertEqual(res["unused_reasons"], ["nothing/*"])
        self.assertIn("fix a", api.why_file("src/a.py")["health_reason"])

    def test_green_marks_verified_and_reports_failures(self):
        self.write("src/a.py.wiki.md", "`a()` does a.\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "wiki")
        api.mark_green("src/a.py", "baseline")
        self.write("src/a.py", "def a(): pass\ndef extra(): pass\n")
        self.write("src/b.py", "def b(): return 2\n")
        res = api.record_changes(default_reason="work", green=True)
        self.assertTrue(res["success"], res)
        self.assertEqual([g["file"] for g in res["marked_green"]], ["src/b.py"])
        self.assertEqual(res["verification_failed"][0]["file"], "src/a.py")
        status = health.load_health(self.root)["entries"]["src/a.py"]["status"]
        self.assertIn("🟡", status)

    def test_only_limits_the_batch(self):
        self.write("src/a.py", "def a(): return 1\n")
        self.write("src/b.py", "def b(): return 1\n")
        res = api.record_changes({"src/a.py": "mine"}, only=["src/a.py"])
        self.assertTrue(res["success"], res)
        self.assertEqual(res["recorded"], ["src/a.py"])

    def test_not_a_git_repo_is_a_clean_error(self):
        shutil.rmtree(self.root / ".git")
        res = api.record_changes(default_reason="x")
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "GitUnavailableError")


if __name__ == "__main__":
    unittest.main()
