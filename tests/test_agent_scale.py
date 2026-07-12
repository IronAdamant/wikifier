"""Agent-scale perf/accuracy path tests (zero-dirty, content-hash dirty, ACS v1.3).

Drives shipped library APIs only — no reimplementation of the unit under test.
"""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import cli
from wikifier import import_cache as ic
from wikifier.import_cache import (
    classify_edge_agent_signal,
    compute_acs_summary,
    compute_file_content_hash,
)


class TestContentHashDirty(TempProjectTestCase):
    def test_mtime_thrash_does_not_reparse_when_content_hash_matches(self):
        p = self.write("pkg/a.py", "import os\nx = 1\n")
        # First map: populates cache + content_hash
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        self.assertGreaterEqual(int(r1.get("files_parsed") or 0), 1)
        cache = ic.load_cache(self.root)
        ent = cache.get("pkg/a.py") or cache.get("a.py")
        # find entry
        if ent is None:
            for k, v in cache.items():
                if str(k).endswith("a.py") and isinstance(v, dict):
                    ent = v
                    break
        self.assertIsInstance(ent, dict, msg=f"cache keys={list(cache)[:20]}")
        self.assertIn("content_hash", ent)
        stored = ent["content_hash"]
        live = compute_file_content_hash(p)
        self.assertEqual(stored, live)

        # Force stale mtime in cache, then touch file (same bytes)
        ent["mtime"] = 1
        ic.save_cache(self.root, cache)
        time.sleep(0.05)
        os.utime(p, None)

        updates = []
        need = ic.compute_files_needing_reparse(
            self.root, [p], full_rebuild=False, content_stable_mtime_updates=updates
        )
        self.assertEqual(need, [], msg=f"should not reparse content-stable; updates={updates}")
        self.assertGreaterEqual(len(updates), 1)

    def test_content_change_does_reparse(self):
        p = self.write("b.py", "y = 1\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        cache = ic.load_cache(self.root)
        ent = cache.get("b.py")
        self.assertIsInstance(ent, dict)
        ent["mtime"] = 1
        # Keep old hash so mtime+hash mismatch forces reparse after rewrite
        ic.save_cache(self.root, cache)
        p.write_text("y = 2\n", encoding="utf-8")
        time.sleep(0.02)
        need = ic.compute_files_needing_reparse(self.root, [p], full_rebuild=False)
        self.assertEqual(len(need), 1)
        self.assertEqual(need[0].resolve(), p.resolve())


class TestZeroDirtyFastPath(TempProjectTestCase):
    def test_second_update_maps_uses_fast_path(self):
        self.write("m.py", "print(1)\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        # Ensure library exists so fast path can skip rewrite
        self.assertTrue((self.root / "library.md").is_file() or r1.get("library", {}).get("success"))

        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        self.assertEqual(int(r2.get("files_parsed") or 0), 0)
        self.assertEqual(int(r2.get("files_to_reparse") or 0), 0)
        self.assertTrue(r2.get("zero_dirty_fast_path"), r2)
        lib = r2.get("library") or {}
        self.assertTrue(lib.get("success"), lib)
        # Prefer skip when library already present
        if (self.root / "library.md").is_file():
            self.assertTrue(lib.get("skipped") or lib.get("path"))

    def test_zero_dirty_persists_acs_v13_to_disk(self):
        """Warm zero-dirty path must write ACS 1.3 + reason_code_counts to import_cache."""
        self.write("n.py", "import os\nx=1\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        # Simulate pre-1.3 cache left on disk (the bug: warm path upgraded memory only)
        cache = ic.load_cache(self.root)
        cache["_acs_summary"] = {
            "acs_version": "1.2",
            "total_scored_edges": 1,
            "avg_confidence": 0.5,
            "low_conf_edges": 1,
            "actionable_low_conf_edges": 0,
        }
        ic.save_cache(self.root, cache)
        on_disk = ic.load_cache(self.root)
        self.assertEqual(str((on_disk.get("_acs_summary") or {}).get("acs_version")), "1.2")

        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        self.assertTrue(r2.get("zero_dirty_fast_path"), r2)
        self.assertEqual((r2.get("acs") or {}).get("acs_version"), "1.3")

        reloaded = ic.load_cache(self.root)
        acs = reloaded.get("_acs_summary") or {}
        self.assertEqual(acs.get("acs_version"), "1.3", msg=acs)
        self.assertIn("reason_code_counts", acs)
        self.assertIsInstance(acs.get("reason_code_counts"), dict)

    def test_max_files_skip_honesty(self):
        for i in range(5):
            self.write(f"f{i}.py", f"v = {i}\n")
        r = cli.update_maps(project_root=self.root, full=True, max_files=2)
        self.assertTrue(r.get("success"), r)
        self.assertEqual(int(r.get("files_parsed") or 0), 2)
        self.assertEqual(int(r.get("files_skipped") or 0), 3)


class TestACSv13(TempProjectTestCase):
    def test_classify_edge_reason_codes(self):
        ext = {
            "raw": "os",
            "resolved": "",
            "confidence_score": 0.48,
            "diagnostic": {"category": "external_or_bare"},
            "resolution_metadata": {"strategy": "python-bare-or-external"},
        }
        sig = classify_edge_agent_signal(ext)
        self.assertEqual(sig["agent_signal"], "skip")
        self.assertEqual(sig["reason_code"], "external_or_bare")
        self.assertFalse(sig["actionable"])

        unres = {"raw": ".missing", "resolved": "", "confidence_score": 0.4}
        sig2 = classify_edge_agent_signal(unres)
        self.assertEqual(sig2["agent_signal"], "investigate")
        self.assertEqual(sig2["reason_code"], "unresolved_project")
        self.assertTrue(sig2["actionable"])

        ok = {"raw": "./x", "resolved": "x.py", "confidence_score": 0.95}
        sig3 = classify_edge_agent_signal(ok)
        self.assertEqual(sig3["reason_code"], "high_confidence_ok")
        self.assertFalse(sig3["actionable"])

    def test_compute_acs_summary_v13_shape(self):
        cache = {
            "a.py": {
                "mtime": 1,
                "resolved_pairs": [
                    {
                        "raw": "os",
                        "resolved": "",
                        "confidence_score": 0.48,
                        "diagnostic": {"category": "external_or_bare"},
                        "resolution_metadata": {"strategy": "python-bare-or-external"},
                    },
                    {
                        "raw": ".b",
                        "resolved": "b.py",
                        "confidence_score": 0.5,
                        "confidence_explanation": "low internal",
                    },
                    {
                        "raw": ".missing",
                        "resolved": "",
                        "confidence_score": 0.4,
                        "confidence_explanation": "unresolved project",
                    },
                ],
            }
        }
        acs = compute_acs_summary(cache)
        self.assertEqual(acs["acs_version"], "1.3")
        self.assertIn("reason_code_counts", acs)
        self.assertIn("agent_signal_counts", acs)
        self.assertGreaterEqual(acs["actionable_low_conf_edges"], 2)
        self.assertGreaterEqual(acs["external_noise_edges"], 1)
        self.assertIn("investigate", acs["agent_signal_counts"])


class TestCoreLoopEdges(TempProjectTestCase):
    def test_session_bootstrap_and_prepare_edit(self):
        self.write("hub.py", "import os\n")
        cli.update_maps(project_root=self.root, full=True)
        boot = cli.session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"), boot)
        self.assertIn("actions", boot)
        pe = cli.prepare_edit("hub.py", project_root=self.root)
        self.assertTrue(pe.get("success"), pe)
        self.assertIn("status", pe)

    def test_invalid_project_root_structured(self):
        # missing path should not crash core helpers
        missing = self.root / "no_such_project_dir"
        r = cli.check_changes(project_root=missing)
        self.assertIsInstance(r, dict)
        # either success with empty or structured failure — never exception
        self.assertIn("success", r)

    def test_prepare_edit_missing_file_fails(self):
        r = cli.prepare_edit("does_not_exist_xyz.py", project_root=self.root)
        self.assertIsInstance(r, dict)
        self.assertFalse(r.get("success"), r)
        self.assertIn("error", r)

    def test_multi_repo_parent_scope_warning_or_ok_flag(self):
        # Bootstrap on a real root must set scope.ok; parent-of-many is agent anti-pattern
        boot = cli.session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"), boot)
        scope = boot.get("scope") or {}
        self.assertIn("ok", scope)


class TestRustCrateResolve(TempProjectTestCase):
    def test_crate_use_resolves_sibling_module(self):
        from wikifier.parsers import rust as rust_parser

        lib = self.write("src/lib.rs", "mod foo;\npub use crate::foo::bar;\n")
        self.write("src/foo.rs", "pub fn bar() {}\n")
        edges = rust_parser.parse_rust_imports(str(lib))
        uses = [e for e in edges if e.get("statement_type") == "use"]
        self.assertTrue(uses)
        # at least one use should resolve to foo.rs when crate path works
        resolved_any = [e for e in uses if e.get("resolved_path")]
        self.assertTrue(
            resolved_any,
            msg=f"expected crate:: resolve; edges={uses}",
        )


if __name__ == "__main__":
    unittest.main()
