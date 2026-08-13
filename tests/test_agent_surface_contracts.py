"""Contract tests for agent-facing CLI / library / MCP / cache split.

Drives shipped entry points — not mocks of the unit under test.
"""

from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests._base import TempProjectTestCase


class TestLibraryImport(unittest.TestCase):
    def test_import_wikifier_and_check_changes_shape(self):
        import wikifier
        from wikifier import check_changes, health
        self.assertTrue(hasattr(wikifier, "__version__"))
        self.assertTrue(str(wikifier.__version__).startswith("4.6."))
        # health() is the convenience function
        self.assertTrue(callable(health))
        self.assertTrue(callable(check_changes))

    def test_javascript_is_module_not_package_decoy(self):
        import wikifier.parsers.javascript as js
        self.assertTrue(js.__file__.endswith("javascript.py"), js.__file__)
        self.assertTrue(hasattr(js, "parse_javascript_imports"))

    def test_bree_is_package(self):
        import wikifier.parsers.bree as bree
        self.assertTrue(bree.__file__.endswith("__init__.py"), bree.__file__)
        self.assertFalse(Path("wikifier/parsers/bree.py").is_file())

    def test_import_cache_hash_prefix(self):
        from wikifier.import_cache import compute_file_content_hash
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write("x = 1\n")
            path = fh.name
        try:
            h = compute_file_content_hash(Path(path))
        finally:
            os.unlink(path)
        self.assertIsNotNone(h)
        self.assertTrue(str(h).startswith("sha256:"), h)

    def test_no_import_cache_impl_module(self):
        with self.assertRaises(ImportError):
            importlib.import_module("wikifier.import_cache_impl")

    def test_cache_package_exports_real_io(self):
        from wikifier.cache import io as cio
        from wikifier.cache import files as cfiles
        from wikifier import import_cache as ic
        self.assertIs(ic.load_cache, cio.load_cache)
        self.assertIs(ic.compute_file_content_hash, cfiles.compute_file_content_hash)
        self.assertIs(ic.compute_files_needing_reparse, cfiles.compute_files_needing_reparse)


class TestCliMainArgv(TempProjectTestCase):
    def test_prepare_edit_is_known_command(self):
        self.write("src/app.py", "print(1)\n")
        from wikifier.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--target", str(self.root), "prepare-edit", "src/app.py"])
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("success", buf.getvalue())

    def test_record_deletion_is_known_command(self):
        from wikifier.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--target", str(self.root), "record-deletion", "gone.py", "removed in test"])
        self.assertEqual(rc, 0, buf.getvalue())

    def test_session_bootstrap_is_known_command(self):
        from wikifier.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--target", str(self.root), "session-bootstrap"])
        out = buf.getvalue()
        self.assertIn("success", out)
        self.assertNotIn("Unknown command", out)

    def test_health_summary_via_main(self):
        from wikifier.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--target", str(self.root), "health", "--summary"])
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertTrue(buf.getvalue().strip())


class TestMcpEntry(unittest.TestCase):
    def test_server_has_main(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("optional mcp extra not installed")
        srv = importlib.import_module("wikifier.mcp.server")
        self.assertTrue(hasattr(srv, "main"), "wikifier-mcp entry requires server.main")
        self.assertTrue(callable(srv.main))
        self.assertTrue(hasattr(srv, "mcp"))

    def test_no_server_backup(self):
        self.assertFalse(Path("wikifier/mcp/server_backup.py").is_file())


class TestGraphSignaturePersist(TempProjectTestCase):
    def test_compute_cycles_persists_signature_for_reuse(self):
        from wikifier import import_cache as ic

        cache = {
            "a.py": {
                "mtime": 1,
                "imports": ["b"],
                "resolved": ["b.py"],
                "resolved_pairs": [{"raw": "b", "resolved": "b.py", "confidence": "high"}],
            },
            "b.py": {
                "mtime": 1,
                "imports": [],
                "resolved": [],
                "resolved_pairs": [],
            },
        }
        first = ic.compute_cycles(cache)
        self.assertIn("graph_signature", first)
        self.assertTrue(first.get("graph_signature"))
        self.assertFalse(first.get("reused"))
        self.assertEqual(cache.get("_graph_signature"), first["graph_signature"])
        second = ic.compute_cycles(cache)
        self.assertTrue(second.get("reused"), second)
        self.assertEqual(second.get("reuse_reason"), "graph_signature_match")


class TestRecordChangeSetsMeaningfulEdit(TempProjectTestCase):
    def test_record_change_writes_last_meaningful_edit(self):
        self.write("src/app.py", "print(1)\n")
        from wikifier.api import record_change
        import importlib
        health_mod = importlib.import_module("wikifier.health")
        res = record_change("src/app.py", "test edit for meaningful timestamp", project_root=self.root)
        self.assertTrue(res.get("success"), res)
        data = health_mod.load_health(self.root)
        ent = data.get("entries", {}).get("src/app.py") or {}
        self.assertTrue(ent.get("last_meaningful_edit"), ent)


class TestTransplantedMonitorDoesNotScanRoot(TempProjectTestCase):
    def test_missing_monitored_entries_do_not_walk_entire_root(self):
        """COBOL-farm / Linux-path transplant: do not fall back to bare root."""
        (self.root / "monitored_paths.txt").write_text(
            "/home/aron/Documents/coding_projects/lang_cobol_sample_projects_for_testing/NOTICE.txt\n",
            encoding="utf-8",
        )
        # Many files that would be expensive to walk if we fell back to root
        for i in range(5):
            self.write(f"proj{i}/a.cob", "IDENTIFICATION DIVISION.\n")
        from wikifier.api import check_changes
        res = check_changes(project_root=self.root)
        self.assertTrue(res.get("success"), res)
        # No candidates → no hang, dirty_total 0
        self.assertEqual(int(res.get("dirty_total") or 0), 0)


class TestReservedCacheKeys(unittest.TestCase):
    def test_new_reserved_keys_registered(self):
        from wikifier.contracts import RESERVED_TOP_LEVEL_KEYS
        for k in ("_candidate_list", "_map_coverage", "_reverse_signature"):
            self.assertIn(k, RESERVED_TOP_LEVEL_KEYS)


if __name__ == "__main__":
    unittest.main()
