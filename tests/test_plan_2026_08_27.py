"""Contract tests for Findings/2026-08-27-plan.md (4.6.13).

Drives shipped library/CLI/MCP entry points — not mocks of the unit under test.
"""
from __future__ import annotations

import importlib
import inspect
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests._base import REPO_ROOT, TempProjectTestCase


DELETED_AUDIT_PATHS = (
    "wikifier/health.py",
    "wikifier/parsers/bree.py",
    "wikifier/import_cache_impl.py",
    "wikifier/mcp/server_backup.py",
    "wikifier/parsers/javascript/_parser.py",
)


class TestDeletedAuditPrune(TempProjectTestCase):
    def test_prune_deleted_missing_removes_gone_rows(self):
        health = importlib.import_module("wikifier.health")
        health.upsert_entry(self.root, "gone.py", "🔴 Red", "DELETED — leftover audit")
        health.upsert_entry(self.root, "src/keep.py", "🟢 Green", "live")
        self.write("src/keep.py", "x = 1\n")
        found = health.find_deleted_missing(self.root)
        self.assertIn("gone.py", found)
        res = health.prune_deleted_missing(self.root)
        self.assertTrue(res.get("success"), res)
        self.assertIn("gone.py", res.get("removed_paths") or [])
        data = health.load_health(self.root)
        self.assertNotIn("gone.py", data.get("entries") or {})
        self.assertIn("src/keep.py", data.get("entries") or {})

    def test_repo_five_deleted_audits_absent_or_prunable(self):
        health = importlib.import_module("wikifier.health")
        data = health.load_health(REPO_ROOT)
        entries = data.get("entries") or {}
        present = [k for k in DELETED_AUDIT_PATHS if k in entries]
        if present:
            found = health.find_deleted_missing(REPO_ROOT)
            for k in present:
                self.assertIn(k, found, "live DELETED audits must be prunable")
        for k in DELETED_AUDIT_PATHS:
            self.assertFalse((REPO_ROOT / k).is_file(), k)


class TestLockTimeoutAndNestedRecord(TempProjectTestCase):
    def test_record_change_accepts_timeout_and_needs_mark_green(self):
        from wikifier.api import record_change

        sig = inspect.signature(record_change)
        self.assertIn("timeout", sig.parameters)
        self.write("src/app.py", "print(1)\n")
        res = record_change("src/app.py", "plan-2026-08-27 nested", project_root=self.root)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res.get("needs_mark_green"), res)
        health = importlib.import_module("wikifier.health")
        ent = (health.load_health(self.root).get("entries") or {}).get("src/app.py") or {}
        self.assertTrue(str(ent.get("status") or "").startswith("🟡"), ent)

    def test_nested_record_change_under_held_lock(self):
        from wikifier.api import record_change
        from wikifier import locking

        self.write("src/app.py", "print(1)\n")
        with locking.file_lock(self.root):
            res = record_change("src/app.py", "nested lock", project_root=self.root, timeout=2.0)
        self.assertTrue(res.get("success"), res)

    def test_file_lock_timeout_on_second_fd(self):
        from wikifier import locking

        if locking.fcntl is None:
            self.skipTest("fcntl not available")
        lock_path = self.root / locking.LOCK_FILE_NAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0x1a4)
        try:
            locking.fcntl.flock(holder, locking.fcntl.LOCK_EX)
            with self.assertRaises(locking.LockTimeoutError):
                with locking.file_lock(self.root, timeout=0.25):
                    pass
        finally:
            locking.fcntl.flock(holder, locking.fcntl.LOCK_UN)
            os.close(holder)


class TestMcpStubsValidateDeadline(unittest.TestCase):
    def test_server_impl_does_not_import_stub_registrars(self):
        src = (REPO_ROOT / "wikifier" / "mcp" / "server_impl.py").read_text(encoding="utf-8")
        self.assertNotIn("register_intel_tools", src)
        self.assertNotIn("Not yet implemented", src)
        tools_init = (REPO_ROOT / "wikifier" / "mcp" / "tools" / "__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("register_intel_tools", tools_init)
        self.assertFalse((REPO_ROOT / "wikifier" / "mcp" / "tools" / "intel.py").is_file())

    def test_validate_is_in_process(self):
        src = (REPO_ROOT / "wikifier" / "mcp" / "server_impl.py").read_text(encoding="utf-8")
        idx = src.find("def validate(")
        self.assertGreater(idx, 0)
        chunk = src[idx : idx + 1200]
        self.assertIn("validate_health", chunk)
        self.assertNotIn("_run_wikifier_command", chunk)

    def test_deadline_helper_times_out_without_waiting(self):
        from wikifier.mcp.deadline import call_with_deadline

        def boom():
            raise AssertionError("should not run")

        res = call_with_deadline(boom, timeout_s=0)
        self.assertTrue(res.get("timed_out"), res)
        self.assertFalse(res.get("success"))

    def test_status_ops_timeout_s_zero_hits_helper(self):
        """Shipped status tools wrap health/cache work in call_with_deadline."""
        from wikifier.mcp.status_ops import (
            run_files_needing_attention,
            run_project_status,
        )

        root = REPO_ROOT
        st = run_project_status(root, format="json", timeout_s=0)
        self.assertTrue(isinstance(st, dict), st)
        self.assertTrue(st.get("timed_out"), st)
        att = run_files_needing_attention(root, format="json", timeout_s=0)
        self.assertTrue(isinstance(att, dict), att)
        self.assertTrue(att.get("timed_out"), att)

    def test_status_ops_runs_health_cache_work(self):
        """Positive timeout actually loads health (not a t<=0 fake)."""
        from wikifier.mcp.status_ops import run_project_status, run_files_needing_attention

        st = run_project_status(REPO_ROOT, format="json", timeout_s=30)
        self.assertTrue(isinstance(st, dict), st)
        self.assertFalse(st.get("timed_out"), st)
        self.assertTrue(st.get("success"), st)
        self.assertIn("green", st)
        self.assertIn("dependency_intel", st)
        att = run_files_needing_attention(REPO_ROOT, format="json", timeout_s=30)
        self.assertTrue(isinstance(att, dict), att)
        self.assertFalse(att.get("timed_out"), att)
        self.assertIn("files", att)

    def test_server_impl_status_tools_delegate_to_deadline_wrap(self):
        src = (REPO_ROOT / "wikifier" / "mcp" / "server_impl.py").read_text(encoding="utf-8")
        a = src.find("def get_files_needing_attention")
        b = src.find("def get_current_project_root")
        chunk = src[a:b]
        self.assertIn("run_files_needing_attention", chunk)
        self.assertIn("run_project_status", chunk)
        self.assertNotIn("if t <= 0", chunk)
        ops = (REPO_ROOT / "wikifier" / "mcp" / "status_ops.py").read_text(encoding="utf-8")
        self.assertIn("call_with_deadline", ops)
        self.assertIn("ensure_acs_summary_persisted", ops)
        self.assertIn("get_files_needing_attention", ops)


class TestParserMapHonesty(TempProjectTestCase):
    def test_source_exts_include_extra_js(self):
        from wikifier.candidates import SOURCE_EXTS
        from wikifier.health_impl import PARSEABLE_SOURCE_SUFFIXES

        for ext in (".mjs", ".cjs", ".mts", ".cts"):
            self.assertIn(ext, SOURCE_EXTS, ext)
            self.assertIn(ext, PARSEABLE_SOURCE_SUFFIXES, ext)

    def test_mts_collected_and_parsed_as_js(self):
        self.write("src/a.mts", "import './b.js';\n")
        self.write("src/b.js", "export const x = 1;\n")
        from wikifier.candidates import collect_candidate_source_files
        from wikifier.parsers.javascript import parse_javascript_imports

        cands = collect_candidate_source_files(self.root)
        self.assertTrue(any(p.name == "a.mts" for p in cands), cands)
        self.reset_js_parser_state()
        edges = parse_javascript_imports(str(self.root / "src" / "a.mts"))
        self.assertTrue(edges, edges)
        raws = [e.get("raw_module") for e in edges]
        self.assertTrue(any("b" in str(r) for r in raws), raws)

    def test_import_a_b_two_python_edges(self):
        self.write("src/m.py", "import os, json\n")
        from wikifier.parsers.python import parse_python_imports

        edges = parse_python_imports(str(self.root / "src" / "m.py"))
        raws = [e.get("raw_module") for e in edges]
        self.assertIn("os", raws, raws)
        self.assertIn("json", raws, raws)

    def test_cjs_destructure_keeps_names(self):
        self.write("src/x.js", "module.exports = { a: 1, b: 2 };\n")
        self.write("src/use.js", "const { a, b } = require('./x');\n")
        from wikifier.parsers.javascript import parse_javascript_imports

        self.reset_js_parser_state()
        edges = parse_javascript_imports(str(self.root / "src" / "use.js"))
        names = []
        for e in edges:
            names.extend(e.get("imported_names") or [])
        self.assertIn("a", names, edges)
        self.assertIn("b", names, edges)

    def test_python_parser_import_does_not_load_javascript(self):
        code = (
            "import sys, importlib\n"
            "importlib.import_module('wikifier.parsers.python')\n"
            "bad = [k for k in sys.modules if k == 'wikifier.parsers.javascript' "
            "or k.startswith('wikifier.parsers.javascript.')]\n"
            "assert not bad, bad\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_src_does_not_walk_root(self):
        (self.root / "monitored_paths.txt").write_text("src/\n", encoding="utf-8")
        (self.root / "map_paths.txt").write_text("src/\n", encoding="utf-8")
        self.write("other/app.py", "print(1)\n")
        from wikifier.candidates import collect_candidate_source_files
        from wikifier.api import check_changes

        cands = collect_candidate_source_files(self.root)
        self.assertEqual(cands, [], cands)
        res = check_changes(project_root=self.root)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(int(res.get("dirty_total") or 0), 0)

    def test_pair_from_parser_edge_does_not_fill_unresolved(self):
        from wikifier.api import _pair_from_parser_edge

        pair = _pair_from_parser_edge(
            {"raw_module": "java.util", "module": "display.mod", "resolved_path": None},
            self.root,
        )
        self.assertEqual(pair.get("resolved") or "", "")


class TestCloseLoopMarkGreen(TempProjectTestCase):
    def test_suggest_and_bootstrap_emit_mark_green(self):
        from wikifier.api import record_change, suggest_next_actions, session_bootstrap

        self.write("src/app.py", "print(1)\n")
        rec = record_change("src/app.py", "plan close-loop", project_root=self.root)
        self.assertTrue(rec.get("needs_mark_green"), rec)
        sugg = suggest_next_actions(project_root=self.root, format="json")
        self.assertTrue(sugg.get("success"), sugg)
        acts = sugg.get("actions") or []
        self.assertTrue(
            any(a.get("action") == "mark_green" and a.get("file") == "src/app.py" for a in acts),
            acts,
        )
        boot = session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"), boot)
        bacts = boot.get("actions") or []
        self.assertTrue(
            any(a.get("action") == "mark_green" and a.get("file") == "src/app.py" for a in bacts),
            bacts,
        )

    def test_record_change_does_not_auto_green(self):
        from wikifier.api import record_change

        self.write("src/app.py", "print(1)\n")
        record_change("src/app.py", "no auto green", project_root=self.root)
        health = importlib.import_module("wikifier.health")
        ent = (health.load_health(self.root).get("entries") or {}).get("src/app.py") or {}
        self.assertTrue(str(ent.get("status") or "").startswith("🟡"), ent)


class TestBreeAdvertisedNames(unittest.TestCase):
    def test_follow_barrel_chain_is_callable(self):
        import wikifier.parsers.bree as bree

        self.assertTrue(callable(getattr(bree, "follow_barrel_chain", None)))
        self.assertTrue(callable(getattr(bree, "get_barrel_cache_stats", None)))


class TestVersionAndDeps(unittest.TestCase):
    def test_version_is_4_6_13(self):
        import wikifier

        self.assertEqual(wikifier.__version__, "4.6.13")

    def test_pyproject_core_deps_empty(self):
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("dependencies = []", text)


if __name__ == "__main__":
    unittest.main()
