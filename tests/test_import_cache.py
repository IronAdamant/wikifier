"""Import-cache schema and graph-intel tests (Phase 0 of Findings/2026-06-10-Fix-Plan.md).

Canonical per-file schema round-trip through the real save_cache/load_cache,
reserved "_" key preservation, reverse dependencies on a 3-file chain, and
Tarjan cycle detection on a seeded 3-node SCC.
"""

import unittest

from tests._base import TempProjectTestCase

from wikifier import import_cache as ic


def _pair(raw, resolved, confidence="high"):
    return {"raw": raw, "resolved": resolved, "confidence": confidence}


class TestCacheRoundTrip(TempProjectTestCase):
    def test_round_trip_preserves_file_entries_and_reserved_keys(self):
        self.write("a.py", "import b\n")
        cache = {}
        ic.update_file_data(
            cache, "a.py",
            mtime=ic.get_mtime(self.root / "a.py"),
            imports=["b"],
            resolved_pairs=[_pair("b", "b.py")],
        )
        # Reserved "_" keys must survive a save/load round trip untouched.
        cache["_cycles"] = {"sccs": [], "stats": {"cyclic_scc_count": 0}}
        cache["_acs_summary"] = {"low_conf_edges": 0, "avg_confidence": 1.0}
        cache["_barrel_resolutions"] = {"deadbeef": {"importers": ["a.py"]}}

        ic.save_cache(self.root, cache)
        # SQLite is primary (4.6.6+); JSON dual-write is opt-in only
        staging = self.root / ".wikifier_staging"
        self.assertTrue(
            (staging / "import_cache.sqlite").exists()
            or (staging / "import_cache.json").exists(),
            "expected sqlite or legacy json cache",
        )

        loaded = ic.load_cache(self.root)
        self.assertEqual(loaded, cache)

        entry = ic.get_file_data(loaded, "a.py")
        self.assertIsInstance(entry["mtime"], int)
        self.assertEqual(entry["imports"], ["b"])
        self.assertEqual(entry["resolved_pairs"][0]["resolved"], "b.py")
        self.assertEqual(entry["resolved_pairs"][0]["confidence"], "high")

        self.assertEqual(loaded["_acs_summary"]["low_conf_edges"], 0)
        self.assertEqual(ic.get_barrel_resolutions(loaded), {"deadbeef": {"importers": ["a.py"]}})

    def test_update_file_data_preserves_rich_pair_fields(self):
        cache = {}
        rich = _pair("./barrel", "barrel/index.js", "medium")
        rich.update({"via_barrel": True, "barrel_depth": 2, "is_dynamic": False})
        ic.update_file_data(cache, "consumer.js", mtime=123, imports=["./barrel"],
                            resolved_pairs=[rich])
        stored = cache["consumer.js"]["resolved_pairs"][0]
        self.assertIs(stored["via_barrel"], True)
        self.assertEqual(stored["barrel_depth"], 2)
        self.assertIs(stored["is_dynamic"], False)

    def test_load_cache_missing_returns_empty_dict(self):
        self.assertEqual(ic.load_cache(self.root), {})


class TestReverseDependencies(TempProjectTestCase):
    def _seed_chain(self):
        """a.py -> b.py -> c.py"""
        cache = {}
        ic.update_file_data(cache, "a.py", 1, ["b"], resolved_pairs=[_pair(".b", "b.py")])
        ic.update_file_data(cache, "b.py", 1, ["c"], resolved_pairs=[_pair(".c", "c.py")])
        ic.update_file_data(cache, "c.py", 1, [], resolved_pairs=[])
        return cache

    def test_reverse_dependencies_on_three_file_chain(self):
        cache = self._seed_chain()
        rev = ic.rebuild_reverse_dependencies(cache)
        self.assertEqual(rev, {"b.py": ["a.py"], "c.py": ["b.py"]})

        ic.set_reverse_dependencies(cache, rev)
        ic.save_cache(self.root, cache)
        loaded = ic.load_cache(self.root)
        self.assertEqual(ic.get_reverse_dependencies(loaded),
                         {"b.py": ["a.py"], "c.py": ["b.py"]})
        # First-class signature must be persisted alongside the index.
        self.assertTrue(ic.get_reverse_signature(loaded))

    def test_incremental_maintenance_matches_rebuild(self):
        cache = self._seed_chain()
        ic.set_reverse_dependencies(cache, ic.rebuild_reverse_dependencies(cache))
        # a.py now imports c.py instead of b.py
        ic.update_file_data(cache, "a.py", 2, ["c"], resolved_pairs=[_pair(".c", "c.py")])
        ic.maintain_reverse_dependencies_for_source(cache, "a.py", ["b.py"], ["c.py"])
        self.assertEqual(ic.get_reverse_dependencies(cache),
                         {"c.py": ["a.py", "b.py"]})
        self.assertEqual(ic.get_reverse_dependencies(cache),
                         ic.rebuild_reverse_dependencies(cache))


class TestCycles(TempProjectTestCase):
    def test_compute_cycles_finds_seeded_three_node_scc(self):
        # Three real (tiny) files importing each other in a ring, seeded into
        # the cache in the canonical per-file schema, then persisted.
        for name, target in (("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "a.py")):
            self.write(name, f"# imports {target}\n")
        cache = {}
        for name, target in (("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "a.py")):
            ic.update_file_data(
                cache, name,
                mtime=ic.get_mtime(self.root / name),
                imports=[target],
                resolved_pairs=[_pair("." + target[:-3], target)],
            )
        ic.save_cache(self.root, cache)

        loaded = ic.load_cache(self.root)
        cdata = ic.compute_cycles(loaded, root=self.root)
        self.assertEqual(cdata["stats"]["cyclic_scc_count"], 1)
        self.assertEqual(cdata["sccs"][0]["nodes"], ["a.py", "b.py", "c.py"])
        self.assertEqual(cdata["sccs"][0]["size"], 3)
        self.assertEqual(sorted(cdata["all_cycle_files"]), ["a.py", "b.py", "c.py"])
        self.assertTrue(cdata["graph_signature"])

        # _cycles is a reserved key that must persist through save/load.
        ic.set_cycles(loaded, cdata)
        ic.set_graph_signature(loaded, cdata["graph_signature"])
        ic.save_cache(self.root, loaded)
        re_loaded = ic.load_cache(self.root)
        self.assertEqual(ic.get_cycles(re_loaded)["stats"]["cyclic_scc_count"], 1)

        # Unchanged topology short-circuits via graph signature.
        reused = ic.compute_cycles(re_loaded, root=self.root)
        self.assertTrue(reused.get("reused"))

    def test_acyclic_graph_reports_no_cycles(self):
        cache = {}
        ic.update_file_data(cache, "a.py", 1, ["b"], resolved_pairs=[_pair(".b", "b.py")])
        ic.update_file_data(cache, "b.py", 1, [], resolved_pairs=[])
        cdata = ic.compute_cycles(cache, root=self.root)
        self.assertEqual(cdata["stats"]["cyclic_scc_count"], 0)
        self.assertEqual(cdata["sccs"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
