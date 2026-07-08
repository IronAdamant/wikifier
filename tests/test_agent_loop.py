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

    def test_legacy_green_without_hash_rewrite_yellows(self):
        """Criterion 2: Green with no source_content_hash + real rewrite must Yellow.

        Must not seed post-edit hash and stay Green (post-upgrade / legacy path).
        """
        p = self.write("legacy.py", "print('v1')\n")
        # Legacy Green: upsert only — no source_content_hash baseline
        health_mod.upsert_entry(self.root, "legacy.py", "🟢 Green", "legacy green no hash")
        data = health_mod.load_health(self.root)
        self.assertNotIn("source_content_hash", data["entries"]["legacy.py"] or {})
        from wikifier import import_cache as ic
        cache = {}
        ic.update_file_data(cache, "legacy.py", mtime=1, imports=[], resolved_pairs=[])
        ic.save_cache(self.root, cache)
        # Real content rewrite
        p.write_text("print('v2-rewritten')\n", encoding="utf-8")
        cache = ic.load_cache(self.root)
        cache["legacy.py"]["mtime"] = 1  # force dirty vs disk
        ic.save_cache(self.root, cache)
        r = cli.check_changes(project_root=self.root)
        self.assertTrue(r.get("success"), r)
        self.assertGreaterEqual(int(r.get("changes_detected") or 0), 1)
        data2 = health_mod.load_health(self.root)
        ent = data2["entries"]["legacy.py"]
        self.assertIn("Yellow", ent["status"])
        # Must not have silently stored the post-edit hash as trusted baseline
        self.assertNotEqual(
            ent.get("source_content_hash"),
            compute_source_content_hash(p),
            "must not seed post-edit content hash without mark_green",
        )
        # After mark_green, baseline is set and further touch-only stays green
        cli.mark_green("legacy.py", "re-baselined", project_root=self.root)
        data3 = health_mod.load_health(self.root)
        self.assertIn("source_content_hash", data3["entries"]["legacy.py"])
        baseline = data3["entries"]["legacy.py"]["source_content_hash"]
        cache = ic.load_cache(self.root)
        cache["legacy.py"]["mtime"] = 1
        ic.save_cache(self.root, cache)
        os.utime(p, None)
        r2 = cli.check_changes(project_root=self.root)
        self.assertTrue(r2.get("success"), r2)
        data4 = health_mod.load_health(self.root)
        self.assertIn("Green", data4["entries"]["legacy.py"]["status"])
        self.assertEqual(data4["entries"]["legacy.py"]["source_content_hash"], baseline)


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


class TestSeedSourceHashes(TempProjectTestCase):
    def test_seed_then_touch_ok_rewrite_yellows(self):
        p = self.write("seeded.py", "print(0)\n")
        health_mod.upsert_entry(self.root, "seeded.py", "🟢 Green", "legacy no hash")
        data = health_mod.load_health(self.root)
        self.assertNotIn("source_content_hash", data["entries"]["seeded.py"] or {})
        res = health_mod.seed_source_content_hashes(self.root, only_green=True)
        self.assertTrue(res.get("success"), res)
        self.assertGreaterEqual(int(res.get("seeded") or 0), 1)
        data2 = health_mod.load_health(self.root)
        ent = data2["entries"]["seeded.py"]
        self.assertIn("Green", ent["status"])
        self.assertTrue(ent.get("source_content_hash"))
        baseline = ent["source_content_hash"]
        from wikifier import import_cache as ic
        cache = {}
        ic.update_file_data(cache, "seeded.py", mtime=1, imports=[], resolved_pairs=[])
        ic.save_cache(self.root, cache)
        os.utime(p, None)
        cache = ic.load_cache(self.root)
        cache["seeded.py"]["mtime"] = 1
        ic.save_cache(self.root, cache)
        r = cli.check_changes(project_root=self.root)
        self.assertTrue(r.get("success"), r)
        data3 = health_mod.load_health(self.root)
        self.assertIn("Green", data3["entries"]["seeded.py"]["status"])
        self.assertEqual(data3["entries"]["seeded.py"]["source_content_hash"], baseline)
        p.write_text("print(99)\n", encoding="utf-8")
        cache = ic.load_cache(self.root)
        cache["seeded.py"]["mtime"] = 1
        ic.save_cache(self.root, cache)
        r2 = cli.check_changes(project_root=self.root)
        self.assertTrue(r2.get("success"), r2)
        self.assertGreaterEqual(int(r2.get("changes_detected") or 0), 1)
        data4 = health_mod.load_health(self.root)
        self.assertIn("Yellow", data4["entries"]["seeded.py"]["status"])


class TestCoreSurfaceListing(unittest.TestCase):
    def test_list_core_tools_has_six(self):
        from wikifier.agent_loop import list_core_tools, CORE_DAILY_NAMES
        res = list_core_tools()
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("core_count"), 6)
        names = res.get("core_names") or []
        for n in (
            "session_bootstrap", "check_changes", "prepare_edit",
            "suggest_next_actions", "record_change", "mark_green",
        ):
            self.assertIn(n, names)
        self.assertEqual(names, CORE_DAILY_NAMES)
        adv = res.get("advanced_intel") or []
        self.assertTrue(adv)
        self.assertNotIn("session_bootstrap", adv)  # core not listed as advanced-only


class TestPrepareEditReverseShapes(TempProjectTestCase):
    def test_flat_and_nested_reverse_index(self):
        self.write("lib/t.py", "x=1\n")
        health_mod.upsert_entry(self.root, "lib/t.py", "🟢 Green", "ok")
        from wikifier import import_cache as ic
        from wikifier.agent_loop import prepare_edit, resolve_dependents_from_cache

        # Flat shape
        cache_flat = {
            "lib/t.py": {"mtime": 1, "resolved_pairs": []},
            "lib/a.py": {"mtime": 1, "resolved_pairs": [{"resolved": "lib/t.py", "resolved_path": "lib/t.py"}]},
            "_reverse_dependencies": {"lib/t.py": ["lib/a.py", "lib/b.py"]},
        }
        deps = resolve_dependents_from_cache(cache_flat, "lib/t.py")
        self.assertIn("lib/a.py", deps)
        self.assertIn("lib/b.py", deps)
        ic.save_cache(self.root, cache_flat)
        pe = prepare_edit("lib/t.py", project_root=self.root)
        self.assertTrue(pe.get("success"))
        self.assertIn("lib/a.py", pe.get("dependents") or [])

        # Nested index shape
        cache_nest = {
            "lib/t.py": {"mtime": 1, "resolved_pairs": []},
            "_reverse_dependencies": {
                "index": {"lib/t.py": ["lib/nested1.py", "lib/nested2.py"]},
                "version": 1,
            },
        }
        deps2 = resolve_dependents_from_cache(cache_nest, "lib/t.py")
        self.assertEqual(set(deps2), {"lib/nested1.py", "lib/nested2.py"})
        ic.save_cache(self.root, cache_nest)
        pe2 = prepare_edit("lib/t.py", project_root=self.root)
        self.assertTrue(pe2.get("success"))
        self.assertIn("lib/nested1.py", pe2.get("dependents") or [])

        # Dict value shape
        cache_dict = {
            "_reverse_dependencies": {
                "lib/t.py": {"importers": ["lib/from_dict.py"]},
            }
        }
        deps3 = resolve_dependents_from_cache(cache_dict, "lib/t.py")
        self.assertIn("lib/from_dict.py", deps3)


if __name__ == "__main__":
    unittest.main()
