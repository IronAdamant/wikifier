"""SQLite cache store + map_coverage + warm path (shipped APIs, zero-dep)."""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import cli
from wikifier import import_cache as ic
from wikifier import cache_store as cs


class TestSqliteCacheRoundTrip(TempProjectTestCase):
    def test_save_load_sqlite_primary(self):
        self.write("a.py", "import os\n")
        r = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r.get("success"), r)
        self.assertTrue(cs.has_sqlite(self.root), "sqlite should exist after save")
        cache = ic.load_cache(self.root)
        self.assertIn("a.py", cache)
        self.assertIsInstance(cache["a.py"].get("mtime"), int)
        # light index works without requiring pairs field presence
        idx = ic.load_mtime_index(self.root)
        self.assertIn("a.py", idx)
        self.assertEqual(idx["a.py"]["mtime"], cache["a.py"]["mtime"])

    def test_legacy_json_dual_read_then_migrate(self):
        # Plant legacy JSON only (no sqlite)
        staging = self.root / ".wikifier_staging"
        staging.mkdir(parents=True, exist_ok=True)
        import json
        legacy = {
            "x.py": {
                "mtime": 1,
                "content_hash": "sha256:abc",
                "imports": ["os"],
                "resolved": [],
                "resolved_pairs": [{"raw": "os", "resolved": "", "confidence_score": 0.48}],
            },
            "_acs_summary": {
                "acs_version": "1.2",
                "total_scored_edges": 1,
                "actionable_low_conf_edges": 0,
                "low_conf_edges": 1,
            },
        }
        (staging / "import_cache.json").write_text(
            json.dumps(legacy), encoding="utf-8"
        )
        loaded = ic.load_cache(self.root)
        self.assertIn("x.py", loaded)
        # update_maps migrates
        self.write("x.py", "import os\n")
        r = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r.get("success"), r)
        self.assertTrue(cs.has_sqlite(self.root))


class TestWarmPathNoFullJsonTax(TempProjectTestCase):
    def test_zero_dirty_reports_sqlite_backend_and_coverage(self):
        self.write("m.py", "print(1)\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        self.assertTrue(r2.get("zero_dirty_fast_path"), r2)
        self.assertIn(r2.get("cache_backend"), ("sqlite", "sqlite+json", "json"))
        cov = r2.get("map_coverage") or {}
        self.assertTrue(cov.get("complete"), cov)
        self.assertIn("files_remaining_dirty", cov)
        self.assertEqual(int(cov["files_remaining_dirty"]), 0)

    def test_zero_dirty_skips_full_payload_load_cache_dict(self):
        """Shipped warm path must not deserialize full file payloads on 0-dirty.

        Criterion: after SQLite is warm, zero-dirty update_maps must not call
        cache_store.load_cache_dict (full pairs) or ic.load_cache (legacy full).
        Light index + meta only.
        """
        self.write("warm.py", "print(0)\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        self.assertTrue(cs.has_sqlite(self.root))
        # Second run seeds zero-dirty + sqlite
        r_seed = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r_seed.get("zero_dirty_fast_path"), r_seed)

        full_loads = {"load_cache_dict": 0, "load_cache": 0}
        real_lcd = cs.load_cache_dict
        real_lc = ic.load_cache

        def counting_lcd(root):
            full_loads["load_cache_dict"] += 1
            return real_lcd(root)

        def counting_lc(root):
            full_loads["load_cache"] += 1
            return real_lc(root)

        # Patch at the modules the shipped path imports from
        import wikifier.cache_store as cs_mod
        import wikifier.import_cache as ic_mod
        orig_cs = cs_mod.load_cache_dict
        orig_ic = ic_mod.load_cache
        cs_mod.load_cache_dict = counting_lcd  # type: ignore
        ic_mod.load_cache = counting_lc  # type: ignore
        try:
            r2 = cli.update_maps(project_root=self.root, full=False)
        finally:
            cs_mod.load_cache_dict = orig_cs  # type: ignore
            ic_mod.load_cache = orig_ic  # type: ignore

        self.assertTrue(r2.get("success"), r2)
        self.assertTrue(r2.get("zero_dirty_fast_path"), r2)
        self.assertEqual(
            full_loads["load_cache_dict"],
            0,
            f"warm 0-dirty must not call load_cache_dict; counts={full_loads}",
        )
        self.assertEqual(
            full_loads["load_cache"],
            0,
            f"warm 0-dirty must not call load_cache; counts={full_loads}",
        )

    def test_max_files_coverage_incomplete(self):
        for i in range(6):
            self.write(f"f{i}.py", f"v={i}\n")
        r = cli.update_maps(project_root=self.root, full=True, max_files=2)
        self.assertTrue(r.get("success"), r)
        cov = r.get("map_coverage") or {}
        self.assertFalse(cov.get("complete"), cov)
        self.assertEqual(int(cov.get("files_skipped") or 0), 4)
        self.assertGreaterEqual(int(cov.get("files_remaining_dirty") or 0), 4)
        self.assertIn("agent_note", cov)

    def test_mtime_index_skips_content_stable(self):
        p = self.write("s.py", "x=1\n")
        cli.update_maps(project_root=self.root, full=True)
        cache = ic.load_cache(self.root)
        ent = cache["s.py"]
        ent["mtime"] = 1
        ic.save_cache(self.root, cache)
        time.sleep(0.05)
        os.utime(p, None)
        updates = []
        need = ic.compute_files_needing_reparse(
            self.root, [p], content_stable_mtime_updates=updates
        )
        # content_hash should make this stable once hash stored
        if ent.get("content_hash"):
            self.assertEqual(need, [])
            self.assertGreaterEqual(len(updates), 1)


class TestBootstrapCoverageAndAcsGuidance(TempProjectTestCase):
    def test_bootstrap_surfaces_acs_guidance(self):
        self.write("h.py", "import os\n")
        cli.update_maps(project_root=self.root, full=True)
        boot = cli.session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"), boot)
        self.assertIn("acs_guidance", boot)
        self.assertIn("actionable_low_conf_edges", boot["acs_guidance"])
        acs = boot.get("acs") or {}
        self.assertIn("acs_version", acs)


class TestGoModResolve(TempProjectTestCase):
    def test_same_module_import_resolves(self):
        from wikifier.parsers import go_lang as go

        self.write(
            "go.mod",
            "module example.com/demo\n\ngo 1.21\n",
        )
        self.write("pkg/util/util.go", "package util\nfunc X() {}\n")
        main = self.write(
            "cmd/main.go",
            'package main\nimport "example.com/demo/pkg/util"\n',
        )
        edges = go.parse_go_imports(str(main))
        self.assertTrue(edges)
        resolved = [e for e in edges if e.get("resolved_path")]
        self.assertTrue(resolved, msg=f"edges={edges}")
        self.assertIn("util", resolved[0]["resolved_path"])


if __name__ == "__main__":
    unittest.main()
