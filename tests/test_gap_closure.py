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

    def test_dynamic_literal_noise_demoted_from_actionable(self):
        """ACS v1.2+: importlib.import_module(\"pkg\") static dynamics are not actionable."""
        dyn_lit = {
            "raw": "\"wikifier.health\"",
            "resolved": "wikifier.health",
            "resolved_path": None,
            "is_dynamic": True,
            "dynamic_type": "static",
            "confidence_score": 0.05,
            "confidence_reasons": [
                "base:low", "conditional_context", "dynamic",
                "detector:TernaryDetector",
            ],
            "confidence_explanation": (
                'Base low (0.05). TernaryDetector=importlib.import_module("wikifier.health"). '
                "Recommendation: Runtime optional load is expected noise."
            ),
            "resolution_metadata": {"strategy": "python-dynamic"},
        }
        project_fragile = {
            "raw": "./missing_local",
            "resolved": "missing_local",
            "resolved_path": None,
            "is_dynamic": False,
            "confidence_score": 0.35,
            "confidence_reasons": ["base:low", "no_resolved_path"],
            "confidence_explanation": "Unresolved project-local. Recommendation: fix path.",
            "diagnostic": {"category": "project"},
            "resolution_metadata": {"strategy": "relative-fs"},
        }
        cache = {
            "mod.py": {
                "mtime": 1,
                "resolved_pairs": [dyn_lit, project_fragile],
            }
        }
        self.assertTrue(ic._edge_is_dynamic_literal_noise(dyn_lit))
        self.assertFalse(ic._edge_is_dynamic_literal_noise(project_fragile))
        summary = ic.compute_acs_summary(cache)
        # v1.3 additive (reason codes); still demotes dynamic literals from actionable
        self.assertGreaterEqual(str(summary.get("acs_version") or ""), "1.2")
        self.assertGreaterEqual(summary["low_conf_edges"], 2)
        self.assertEqual(summary["actionable_low_conf_edges"], 1)
        self.assertGreaterEqual(summary.get("dynamic_literal_noise_edges", 0), 1)
        if "reason_code_counts" in summary:
            self.assertIn("dynamic_literal", summary["reason_code_counts"] or {})
        action = ic.get_low_confidence_edges(cache, actionable_only=True)
        self.assertEqual(len(action), 1)
        self.assertIn("missing_local", str(action[0].get("raw") or action[0].get("resolved")))


class TestLoadSafetyNoImportCycle(unittest.TestCase):
    """Load-time safety: core modules import without circular-import failure."""

    def test_import_wikifier_and_cycle_trio(self):
        import importlib
        import wikifier
        self.assertTrue(hasattr(wikifier, "discover_project_root"))
        # Fresh submodule loads (project_root breaks former cli↔cache↔bree SCC)
        for name in (
            "wikifier.project_root",
            "wikifier.cli",
            "wikifier.import_cache",
            "wikifier.parsers.bree",
        ):
            mod = importlib.import_module(name)
            self.assertIsNotNone(mod)
        from wikifier.project_root import discover_project_root as dpr
        from wikifier.cli import discover_project_root as dpr_cli
        self.assertIs(dpr, dpr_cli)
        root = dpr()
        self.assertTrue(root.exists())

    def test_bree_does_not_import_cli_at_module_level(self):
        """Static check: bree source must not load-time import wikifier.cli."""
        from pathlib import Path
        bree_src = Path(__file__).resolve().parents[1] / "wikifier" / "parsers" / "bree" / "_bree.py"
        text = bree_src.read_text(encoding="utf-8")
        self.assertNotIn("from ..cli import", text)
        self.assertNotIn("from wikifier.cli import", text)
        self.assertIn("from ..project_root import", text)


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

    def test_record_deletion_rejects_flag_paths(self):
        res = cli.record_deletion("--help", "oops", project_root=self.root)
        self.assertFalse(res.get("success"))
        self.assertIn("flag", (res.get("error") or "").lower())


class TestPendingAndPollutionHygiene(TempProjectTestCase):
    def test_pending_empty_marker_not_counted_and_no_dual_state(self):
        health_mod = importlib.import_module("wikifier.health")
        # Dual-state pollution (historical bug): empty marker + real items
        p = self.root / "pending_updates.md"
        p.write_text(
            "# Pending Updates\n\n(no active items)\n- src/a.py: review\n",
            encoding="utf-8",
        )
        self.assertEqual(health_mod.count_pending(self.root), 1)
        # Normalize via remove of the only item → empty marker only
        health_mod.remove_from_pending(self.root, "src/a.py")
        text = p.read_text(encoding="utf-8")
        self.assertIn("no pending", text.lower())
        self.assertNotIn("- src/a.py", text)
        self.assertEqual(health_mod.count_pending(self.root), 0)
        # Add clears empty marker
        health_mod.add_to_pending(self.root, "src/b.py", "need wiki")
        text2 = p.read_text(encoding="utf-8")
        self.assertIn("- src/b.py:", text2)
        self.assertNotIn("no pending", text2.lower())
        self.assertNotIn("no active", text2.lower())
        self.assertEqual(health_mod.count_pending(self.root), 1)
        summary = health_mod.get_summary(self.root)
        self.assertEqual(summary["pending_updates"], 1)

    def test_superseded_and_flag_deleted_keys_pruned(self):
        health_mod = importlib.import_module("wikifier.health")
        # Inject pollution keys directly then save
        data = {
            "version": 2,
            "last_updated": "2026-01-01",
            "entries": {
                "M5.3 Cycle1 evidence append: 3 subs spawned": {
                    "status": "🔴 Red",
                    "reason": "DELETED — Historical early M5.3 launch note",
                    "last_updated": "2026-01-01",
                },
                "--help": {
                    "status": "🔴 Red",
                    "reason": "DELETED — removed",
                    "last_updated": "2026-01-01",
                },
                "real.py": {
                    "status": "🟢 Green",
                    "reason": "ok",
                    "last_updated": "2026-01-01",
                },
            },
        }
        health_mod.save_health(self.root, data)
        entries = health_mod.load_health(self.root)["entries"]
        self.assertNotIn("M5.3 Cycle1 evidence append: 3 subs spawned", entries)
        self.assertNotIn("--help", entries)
        self.assertIn("real.py", entries)
        # Real path DELETED audit is kept
        health_mod.upsert_entry(self.root, "gone_real.py", "🔴 Red", "DELETED — intentional")
        entries2 = health_mod.load_health(self.root)["entries"]
        self.assertIn("gone_real.py", entries2)


class TestMapFirstTaxonomyAndReadiness(TempProjectTestCase):
    def test_stub_yellow_is_map_ready_not_needs_attention(self):
        health_mod = importlib.import_module("wikifier.health")
        health_mod.upsert_entry(
            self.root, "a.py", "🟡 Yellow",
            "Initial stub — present in dependency map; agent should wiki + mark-green when editing",
        )
        health_mod.upsert_entry(
            self.root, "b.py", "🟡 Yellow",
            "Initial stub — parseable source under monitored_paths; agent should wiki + mark-green when editing",
        )
        s = health_mod.get_summary(self.root)
        self.assertEqual(s.get("stub_yellow"), 2)
        self.assertEqual(s.get("actionable_yellow"), 0)
        self.assertEqual(s.get("health_score"), "Map Ready")

    def test_actionable_yellow_needs_attention(self):
        health_mod = importlib.import_module("wikifier.health")
        health_mod.upsert_entry(
            self.root, "a.py", "🟡 Yellow",
            "mtime changed since last check-changes (Python primary auto-detected)",
        )
        s = health_mod.get_summary(self.root)
        self.assertEqual(s.get("actionable_yellow"), 1)
        self.assertEqual(s.get("health_score"), "Needs Attention")

    def test_suggest_does_not_bulk_wiki_stubs(self):
        health_mod = importlib.import_module("wikifier.health")
        health_mod.upsert_entry(self.root, "a.py", "🟡 Yellow", "Initial stub — present in dependency map")
        text = cli.suggest_next_actions(project_root=self.root, format="text")
        self.assertIn("Map-first", text)
        self.assertNotIn("Review the 1 🟡 Yellow file(s) only", text)

    def test_detect_multi_project_container(self):
        health_mod = importlib.import_module("wikifier.health")
        for name in ("proj_a", "proj_b", "proj_c"):
            d = self.root / name
            d.mkdir()
            (d / ".git").mkdir()
        scope = health_mod.detect_scope_risks(self.root)
        self.assertGreaterEqual(scope.get("child_project_count"), 3)
        self.assertFalse(scope.get("ok"))
        self.assertTrue(any("multi-project" in w.lower() for w in scope.get("warnings") or []))

    def test_autonomous_readiness_shape(self):
        health_mod = importlib.import_module("wikifier.health")
        (self.root / "monitored_paths.txt").write_text("src\n", encoding="utf-8")
        self.write("src/app.py", "x=1\n")
        health_mod.upsert_entry(self.root, "src/app.py", "🟡 Yellow", "Initial stub — present in dependency map")
        r = health_mod.assess_autonomous_readiness(self.root)
        self.assertTrue(r.get("success"))
        self.assertIn(r.get("readiness"), (
            "blocked", "map_ok_scope_risk", "ready_for_daemon",
            "ready_with_agent_wiki_work", "not_ready",
        ))
        self.assertIn("long_horizon_note", r)
        self.assertIn("metrics", r)

    def test_write_metrics_snapshot_history(self):
        health_mod = importlib.import_module("wikifier.health")
        (self.root / "monitored_paths.txt").write_text("src\n", encoding="utf-8")
        self.write("src/app.py", "x=1\n")
        health_mod.upsert_entry(self.root, "src/app.py", "🟢 Green", "ok")
        s1 = health_mod.write_metrics_snapshot(self.root, source="test1")
        self.assertTrue(s1.get("success"))
        latest = self.root / ".wikifier_staging" / "metrics_latest.json"
        hist = self.root / ".wikifier_staging" / "metrics_history.jsonl"
        self.assertTrue(latest.exists())
        self.assertTrue(hist.exists())
        s2 = health_mod.write_metrics_snapshot(self.root, source="test2")
        self.assertTrue(s2.get("success"))
        rows = health_mod.read_metrics_history(self.root, limit=10)
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[-1].get("source"), "test2")
        self.assertIn("staging_bytes", rows[-1])
        self.assertIn("health_score", rows[-1])


class TestMapFirstHealthAndValidate(TempProjectTestCase):
    def test_deep_relative_keys_are_under_root(self):
        """Regression: deep monorepo rel paths must not be treated as abs pollution."""
        health_mod = importlib.import_module("wikifier.health")
        deep = "airflow-core/src/airflow/api/client/local_client.py"
        self.assertTrue(health_mod._entry_is_under_root(self.root, deep))
        self.assertTrue(health_mod._entry_is_under_root(self.root, "pkg/a.py"))

    def test_seed_health_from_map_creates_stubs(self):
        health_mod = importlib.import_module("wikifier.health")
        from wikifier import import_cache as ic

        self.write("pkg/a.py", "import b\n")
        self.write("pkg/b.py", "x=1\n")
        self.write("README.md", "# hi\n")
        cache = {}
        ic.update_file_data(cache, "pkg/a.py", mtime=1, imports=["b"], resolved_pairs=[])
        ic.update_file_data(cache, "pkg/b.py", mtime=1, imports=[], resolved_pairs=[])
        ic.save_cache(self.root, cache)

        # No health file yet
        self.assertFalse((self.root / "file_health.json").exists())
        res = health_mod.seed_health_from_map(self.root)
        self.assertTrue(res.get("success"))
        self.assertGreaterEqual(res.get("seeded"), 2)
        entries = health_mod.load_health(self.root)["entries"]
        self.assertIn("pkg/a.py", entries)
        self.assertIn("pkg/b.py", entries)
        self.assertTrue(entries["pkg/a.py"]["status"].startswith("🟡"))

    def test_validate_ignores_non_source_and_reports_mapped_gaps(self):
        health_mod = importlib.import_module("wikifier.health")
        from wikifier import import_cache as ic

        self.write("src/app.py", "print(1)\n")
        self.write("src/notes.md", "docs\n")
        self.write("src/logo.png", "x")
        (self.root / "monitored_paths.txt").write_text("src\n", encoding="utf-8")
        cache = {}
        ic.update_file_data(cache, "src/app.py", mtime=1, imports=[], resolved_pairs=[])
        ic.update_file_data(cache, "src/other.py", mtime=1, imports=[], resolved_pairs=[])
        ic.save_cache(self.root, cache)

        # No health yet — in-scope mapped + monitored parseable gaps
        v = health_mod.validate_health(self.root)
        self.assertTrue(v.get("map_first"))
        self.assertGreaterEqual(v.get("mapped_in_scope_without_health_count", 0), 1)
        self.assertGreaterEqual(v.get("missing_count", 0), 1)
        # notes.md / logo.png must not appear as monitored-source gaps
        mon_missing = v.get("missing_monitored_source") or []
        self.assertTrue(all(not m.endswith(".md") and not m.endswith(".png") for m in mon_missing))

        health_mod.seed_health_from_map(self.root)  # only_monitored default
        # Seed in-scope map keys; app.py on disk + mapped in-scope covered
        v2 = health_mod.validate_health(self.root)
        self.assertEqual(v2.get("mapped_in_scope_without_health_count"), 0)
        # missing_count may still include on-disk sources not in map (ok if 0 after seed of map keys only)
        self.assertEqual(v2.get("mapped_in_scope_without_health_count"), 0)

    def test_prune_pending_and_health_to_monitored(self):
        health_mod = importlib.import_module("wikifier.health")
        (self.root / "monitored_paths.txt").write_text("src\n", encoding="utf-8")
        self.write("src/keep.py", "k=1\n")
        self.write("other/out.py", "o=1\n")
        health_mod.upsert_entry(self.root, "src/keep.py", "🟡 Yellow", "in scope")
        health_mod.upsert_entry(self.root, "other/out.py", "🟡 Yellow", "out of scope")
        health_mod.add_to_pending(self.root, "src/keep.py", "need wiki")
        health_mod.add_to_pending(self.root, "other/out.py", "noise")

        pr = health_mod.prune_pending_to_monitored(self.root)
        self.assertEqual(pr.get("removed"), 1)
        self.assertEqual(health_mod.count_pending(self.root), 1)

        hr = health_mod.prune_health_outside_monitored(self.root)
        self.assertEqual(hr.get("removed"), 1)
        entries = health_mod.load_health(self.root)["entries"]
        self.assertIn("src/keep.py", entries)
        self.assertNotIn("other/out.py", entries)


if __name__ == "__main__":
    unittest.main()
