"""Agent-first ideal-loop tests: content-dirty, bootstrap, suggest actions, preflight, journal."""

import importlib
import os
import time
import unittest
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import cli
from wikifier.health import classify_content_dirty, compute_source_content_hash
from wikifier.agent_loop import (
    session_bootstrap,
    prepare_edit,
    search_journal,
    why_file,
    build_structured_actions,
)

health_mod = importlib.import_module("wikifier.health")


class TestContentHonestDirty(TempProjectTestCase):
    def test_classify_touch_only_vs_rewrite(self):
        p = self.write("src/a.py", "x = 1\n")
        h1 = compute_source_content_hash(p)
        self.assertIsNotNone(h1)
        v = classify_content_dirty(p, h1)
        self.assertFalse(v["content_dirty"])
        self.assertEqual(v["reason"], "content_unchanged")
        # mtime thrash without content change
        os.utime(p, None)
        v2 = classify_content_dirty(p, h1)
        self.assertFalse(v2["content_dirty"])
        self.assertEqual(v2["reason"], "content_unchanged")
        # rewrite bytes
        p.write_text("x = 2\n", encoding="utf-8")
        v3 = classify_content_dirty(p, h1)
        self.assertTrue(v3["content_dirty"])
        self.assertEqual(v3["reason"], "content_changed")

    def test_check_changes_skips_mtime_only_after_mark_green(self):
        p = self.write("mod.py", "print(1)\n")
        # Seed health green with source baseline via mark_green
        res_mg = cli.mark_green("mod.py", "baseline", project_root=self.root)
        self.assertTrue(res_mg.get("success"), res_mg)
        data = health_mod.load_health(self.root)
        ent = data["entries"]["mod.py"]
        self.assertIn("source_content_hash", ent)
        baseline = ent["source_content_hash"]
        # Ensure import_cache may list file as dirty via mtime: touch only
        from wikifier import import_cache as ic
        cache = {}
        ic.update_file_data(cache, "mod.py", mtime=1, imports=[], resolved_pairs=[])
        ic.save_cache(self.root, cache)
        time.sleep(0.05)
        os.utime(p, None)
        # Force compute dirty by setting cache mtime older than file
        cache = ic.load_cache(self.root)
        cache["mod.py"]["mtime"] = 1
        ic.save_cache(self.root, cache)
        r = cli.check_changes(project_root=self.root)
        self.assertTrue(r.get("success"), r)
        # Content unchanged → should not Yellow for content
        data2 = health_mod.load_health(self.root)
        st = data2["entries"]["mod.py"]["status"]
        self.assertIn("Green", st)
        self.assertEqual(data2["entries"]["mod.py"].get("source_content_hash"), baseline)
        # Real content edit → Yellow
        p.write_text("print(2)\n", encoding="utf-8")
        cache = ic.load_cache(self.root)
        cache["mod.py"]["mtime"] = 1
        ic.save_cache(self.root, cache)
        r2 = cli.check_changes(project_root=self.root)
        self.assertTrue(r2.get("success"), r2)
        data3 = health_mod.load_health(self.root)
        self.assertIn("Yellow", data3["entries"]["mod.py"]["status"])
        self.assertIn("content", data3["entries"]["mod.py"]["reason"].lower())


class TestSessionBootstrapAndSuggest(TempProjectTestCase):
    def test_session_bootstrap_shape(self):
        self.write("a.py", "import os\n")
        health_mod.upsert_entry(self.root, "a.py", "🟡 Yellow", "record-change: edit")
        boot = session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"))
        self.assertEqual(Path(boot["project_root"]).resolve(), self.root)
        self.assertIn("health_summary", boot)
        self.assertIn("actions", boot)
        self.assertIsInstance(boot["actions"], list)
        self.assertTrue(any("action" in a for a in boot["actions"]))
        self.assertIn("session_bootstrap", boot.get("core_surface") or [])

    def test_suggest_json_has_structured_actions(self):
        health_mod.upsert_entry(self.root, "b.py", "🔴 Red", "DELETED — gone")
        health_mod.upsert_entry(self.root, "c.py", "🟡 Yellow", "content changed")
        res = cli.suggest_next_actions(project_root=self.root, format="json")
        self.assertTrue(res.get("success"))
        actions = res.get("actions") or []
        self.assertTrue(actions, "expected dispatchable actions")
        for a in actions:
            self.assertIn("action", a)
            self.assertIn("priority", a)
            self.assertIn("reason", a)
        kinds = {a["action"] for a in actions}
        self.assertTrue(kinds & {"investigate_red", "wiki_refresh", "review_acs", "update_maps_if_structure", "lookup_only", "map_first_ok", "fix_scope"})


class TestPrepareEditAndJournal(TempProjectTestCase):
    def test_prepare_edit_returns_status_and_lists(self):
        self.write("pkg/x.py", "from . import y\n")
        health_mod.upsert_entry(self.root, "pkg/x.py", "🟢 Green", "ok")
        # minimal cache edge
        from wikifier import import_cache as ic
        cache = {}
        ic.update_file_data(
            cache,
            "pkg/x.py",
            mtime=1,
            imports=["./y"],
            resolved_pairs=[{
                "raw": "./y",
                "resolved": "pkg/y.py",
                "resolved_path": "pkg/y.py",
                "confidence_score": 0.9,
            }],
        )
        cache["_reverse_dependencies"] = {"pkg/x.py": ["pkg/z.py"]}
        ic.save_cache(self.root, cache)
        pe = prepare_edit("pkg/x.py", project_root=self.root)
        self.assertTrue(pe.get("success"))
        self.assertEqual(pe.get("file"), "pkg/x.py")
        self.assertIn("Green", str(pe.get("status") or ""))
        self.assertTrue(isinstance(pe.get("dependencies"), list))
        self.assertIn("pkg/z.py", pe.get("dependents") or [])

    def test_journal_search_and_why_file(self):
        self.write("tracked.py", "v=1\n")
        r = cli.record_change("tracked.py", "semantic reason alpha-subid", project_root=self.root)
        self.assertTrue(r.get("success"), r)
        sj = search_journal(project_root=self.root, query="alpha-subid")
        self.assertTrue(sj.get("success"))
        self.assertGreaterEqual(len(sj.get("matches") or []), 1)
        self.assertTrue(any("alpha-subid" in (m.get("reason") or "") for m in sj["matches"]))
        sj2 = search_journal(project_root=self.root, file="tracked.py")
        self.assertGreaterEqual(len(sj2.get("matches") or []), 1)
        why = why_file("tracked.py", project_root=self.root)
        self.assertTrue(why.get("success"))
        self.assertTrue(why.get("health_reason") or why.get("journal_matches"))


class TestBuildActionsUnit(unittest.TestCase):
    def test_build_structured_actions_priorities(self):
        acts = build_structured_actions(
            red_files=["a.py"],
            actionable_yellow_files=["b.py"],
            red=1,
            actionable_yellow=1,
            acs_actionable=3,
            clean=False,
        )
        self.assertTrue(any(a["action"] == "investigate_red" and a["file"] == "a.py" for a in acts))
        self.assertTrue(any(a["action"] == "wiki_refresh" and a["file"] == "b.py" for a in acts))
        self.assertTrue(any(a["action"] == "review_acs" for a in acts))
        # sorted by priority
        pris = [a["priority"] for a in acts]
        self.assertEqual(pris, sorted(pris))


class TestCliBootstrapEntry(TempProjectTestCase):
    def test_cli_session_bootstrap_function(self):
        self.write("z.py", "pass\n")
        res = cli.session_bootstrap(project_root=self.root)
        self.assertTrue(res.get("success"))
        self.assertIn("actions", res)


if __name__ == "__main__":
    unittest.main()
