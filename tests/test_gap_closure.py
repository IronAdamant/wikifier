"""Gap-closure regressions (G4 ACS actionable, G5 health module, G7 ghosts/deletion)."""

import importlib
import unittest

from tests._base import TempProjectTestCase

from wikifier import import_cache as ic
from wikifier import cli


class TestHealthModuleImportG5(unittest.TestCase):
    def test_importlib_health_is_module_with_get_summary(self):
        mod = importlib.import_module("wikifier.health")
        self.assertTrue(hasattr(mod, "get_summary"))
        self.assertTrue(hasattr(mod, "find_ghost_entries"))
        self.assertTrue(callable(mod.get_summary))

    def test_health_module_alias_on_package(self):
        import wikifier
        self.assertTrue(hasattr(wikifier, "health_module"))
        self.assertTrue(hasattr(wikifier.health_module, "get_summary"))
        # Convenience function still exported as wikifier.health
        self.assertTrue(callable(wikifier.health))


class TestAcsActionableG4(TempProjectTestCase):
    def test_external_noise_excluded_from_actionable_low_conf(self):
        cache = {}
        # Project-internal low-conf edge
        ic.update_file_data(
            cache,
            "app.py",
            mtime=1,
            imports=["./util"],
            resolved_pairs=[{
                "raw": "./util",
                "resolved": "util.py",
                "resolved_path": "util.py",
                "confidence_score": 0.4,
                "confidence_reasons": ["base:low", "via_barrel"],
                "confidence_explanation": "Base low. Recommendation: Review project edge.",
                "diagnostic": {"category": "project"},
                "resolution_metadata": {"strategy": "relative-fs"},
            }],
        )
        # External/stdlib-style edge (noise)
        ic.update_file_data(
            cache,
            "app.py",
            mtime=1,
            imports=["json", "./util"],
            resolved_pairs=[
                {
                    "raw": "./util",
                    "resolved": "util.py",
                    "resolved_path": "util.py",
                    "confidence_score": 0.4,
                    "confidence_reasons": ["base:low"],
                    "confidence_explanation": "Project low. Recommendation: Review.",
                    "resolution_metadata": {"strategy": "relative-fs"},
                },
                {
                    "raw": "json",
                    "resolved": "json",
                    "resolved_path": "",
                    "confidence_score": 0.48,
                    "confidence_reasons": ["base:medium", "no_resolved_path"],
                    "confidence_explanation": "stdlib. Recommendation: harden import.",
                    "diagnostic": {"category": "external_or_bare"},
                    "resolution_metadata": {"strategy": "python-bare-or-external"},
                },
            ],
        )
        # Note: update_file_data may replace pairs — set explicitly
        cache["app.py"]["resolved_pairs"] = [
            {
                "raw": "./util",
                "resolved": "util.py",
                "resolved_path": "util.py",
                "confidence_score": 0.4,
                "confidence_reasons": ["base:low"],
                "confidence_explanation": "Project low. Recommendation: Review.",
                "resolution_metadata": {"strategy": "relative-fs"},
            },
            {
                "raw": "json",
                "resolved": "json",
                "confidence_score": 0.48,
                "confidence_reasons": ["base:medium"],
                "confidence_explanation": "stdlib noise. Recommendation: ignore.",
                "diagnostic": {"category": "external_or_bare"},
                "resolution_metadata": {"strategy": "python-bare-or-external"},
            },
        ]
        summary = ic.compute_acs_summary(cache)
        self.assertGreaterEqual(summary["low_conf_edges"], 1)
        self.assertEqual(summary["actionable_low_conf_edges"], 1)
        self.assertGreaterEqual(summary["external_noise_edges"], 1)
        action = ic.get_low_confidence_edges(cache, actionable_only=True)
        self.assertTrue(all(
            (p.get("diagnostic") or {}).get("category") != "external_or_bare"
            for p in action
        ))


class TestGhostAndDeletionG7(TempProjectTestCase):
    def test_find_ghost_and_record_deletion(self):
        health_mod = importlib.import_module("wikifier.health")
        self.write("keep.py", "x=1\n")
        self.write("gone.py", "y=1\n")
        health_mod.upsert_entry(self.root, "keep.py", "🟢 Green", "ok")
        health_mod.upsert_entry(self.root, "gone.py", "🟢 Green", "ok")
        (self.root / "gone.py").unlink()

        ghosts = health_mod.find_ghost_entries(self.root)
        self.assertIn("gone.py", ghosts)
        self.assertNotIn("keep.py", ghosts)

        res = cli.record_deletion("gone.py", "removed in cleanup", project_root=self.root)
        self.assertTrue(res.get("success"))
        entries = health_mod.load_health(self.root)["entries"]
        self.assertIn("🔴", entries["gone.py"]["status"])
        self.assertIn("DELETED", entries["gone.py"]["reason"])


if __name__ == "__main__":
    unittest.main()
