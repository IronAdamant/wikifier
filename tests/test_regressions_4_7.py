"""Regression tests for the 4.7.0 review fixes (one test per defect)."""

from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests._base import REPO_ROOT, TempProjectTestCase

from wikifier import api, cache_store as cs, health_pkg as health, import_cache as ic, locking
from wikifier.cli import main as cli_main


def run_cli(*args):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        code = cli_main(list(args))
    return code, buf.getvalue()


class TestProjectRootIsStrict(TempProjectTestCase):
    def test_missing_explicit_root_is_an_error_and_writes_nothing(self):
        bogus = str(self.root / "does-not-exist")
        before = set(os.listdir(self.root))
        for call in (
            lambda: api.record_change("a.py", "x", project_root=bogus),
            lambda: api.mark_green("a.py", project_root=bogus),
            lambda: api.check_changes(project_root=bogus),
            lambda: api.record_deletion("a.py", "x", project_root=bogus),
            lambda: api.prepare_edit("a.py", project_root=bogus),
            lambda: api.session_bootstrap(project_root=bogus),
        ):
            res = call()
            self.assertFalse(res["success"], res)
            self.assertIn("not an existing directory", res["error"])
        self.assertEqual(set(os.listdir(self.root)), before)

    def test_missing_env_root_is_an_error(self):
        os.environ["WIKIFIER_PROJECT_ROOT"] = str(self.root / "nope")
        res = api.check_changes()
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "ProjectRootError")

    def test_cli_rejects_missing_target(self):
        code, _ = run_cli("--target", str(self.root / "nope"), "check-changes")
        self.assertEqual(code, 1)


class TestPathNormalization(TempProjectTestCase):
    def test_absolute_path_round_trip_uses_one_key_and_clears_pending(self):
        self.write("src/a.py", "x = 1\n")
        absolute = str(self.root / "src" / "a.py")
        self.assertTrue(api.record_change(absolute, "edit")["success"])
        res = api.mark_green(absolute, "ok")
        self.assertTrue(res["success"], res)
        self.assertEqual(res["file"], "src/a.py")
        entries = health.load_health(self.root)["entries"]
        self.assertEqual(list(entries), ["src/a.py"])
        self.assertIn("🟢", entries["src/a.py"]["status"])
        self.assertTrue(entries["src/a.py"].get("source_content_hash"))
        self.assertEqual(health.count_pending(self.root), 0)

    def test_dot_prefixed_names_are_not_mangled(self):
        self.write(".github/workflow.py", "x = 1\n")
        res = api.record_change("./.github/workflow.py", "edit")
        self.assertEqual(res["file"], ".github/workflow.py")

    def test_mark_green_and_record_change_reject_missing_files(self):
        self.assertFalse(api.mark_green("ghost.py")["success"])
        self.assertFalse(api.record_change("ghost.py", "x")["success"])
        self.assertEqual(health.load_health(self.root)["entries"], {})

    def test_record_change_outside_root_is_rejected(self):
        res = api.record_change("/etc/hosts", "x")
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "ProjectPathError")

    def test_relative_keys_that_look_absolute_are_kept(self):
        for rel in ("tmp/x.py", "home/page.py", "Users/u.py", "var/v.py"):
            self.write(rel, "x = 1\n")
            health.upsert_entry(self.root, rel, health.YELLOW, "edit")
        self.assertEqual(set(health.load_health(self.root)["entries"]), {"tmp/x.py", "home/page.py", "Users/u.py", "var/v.py"})


class TestPending(TempProjectTestCase):
    def test_remove_is_exact_not_substring(self):
        for name in ("a.py", "data.py", "src/a.py.bak"):
            health.add_to_pending(self.root, name, "edit")
        health.remove_from_pending(self.root, "a.py")
        text = (self.root / "pending_updates.md").read_text()
        self.assertNotIn("- a.py:", text)
        self.assertIn("- data.py:", text)
        self.assertIn("- src/a.py.bak:", text)


class TestPrepareEdit(TempProjectTestCase):
    def test_dependencies_show_resolved_targets_and_dependents(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/a.py", "from pkg import b\nimport os\n")
        self.write("pkg/b.py", "x = 1\n")
        self.assertTrue(api.update_maps(full=True)["success"])
        pe = api.prepare_edit("pkg/a.py")
        targets = {d["raw"]: d["resolved_path"] for d in pe["dependencies"]}
        self.assertEqual(targets["pkg"], "pkg/b.py")
        self.assertIsNone(targets["os"])
        self.assertEqual(api.prepare_edit("pkg/b.py")["dependents"], ["pkg/a.py"])


class TestCyclesConsistency(TempProjectTestCase):
    def test_report_ignores_stale_integrity_copy(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "x = 1\n")
        self.assertTrue(api.update_maps(full=True)["success"])
        cs.save_meta_key(self.root, "_graph_integrity", {"summary": "1 cyclic SCC(s) involving 3 files"})
        report = api.cycles_report()
        self.assertEqual(report["count"], 0)
        self.assertIn("0 cyclic", report["integrity"]["summary"])
        self.write("b.py", "x = 2\n")
        api.update_maps()
        self.assertNotIn("_graph_integrity", ic.load_cache(self.root), "update-maps drops the stale copy")

    def test_cycle_detected(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "import a\n")
        self.assertTrue(api.update_maps(full=True)["success"])
        report = api.cycles_report()
        self.assertEqual(report["count"], 1)
        self.assertIn("a.py", report["sccs"][0]["nodes"])


class TestCliCommands(TempProjectTestCase):
    def test_heal_stubs_and_shell_ported_commands_run(self):
        for args in (("heal-stubs", "--dry-run"), ("healing-stats",), ("journal",), ("issues",), ("cycles",)):
            code, out = run_cli("--target", str(self.root), *args)
            self.assertEqual(code, 0, (args, out))

    def test_read_only_commands_do_not_write_dashboards(self):
        run_cli("--target", str(self.root), "journal")
        run_cli("--target", str(self.root), "health")
        self.assertFalse((self.root / "index.html").exists())

    def test_init_writes_templates_and_dashboard(self):
        target = self.root / "fresh"
        code, _ = run_cli("init", str(target))
        self.assertEqual(code, 0)
        for name in ("monitored_paths.txt", "map_paths.txt", "exclude_patterns.txt", "index.html", ".wikifier/config"):
            self.assertTrue((target / name).exists(), name)

    def test_space_separated_directory_option(self):
        self.write("src/a.py", "x = 1\n")
        self.write("other/b.py", "y = 1\n")
        code, _ = run_cli("update-maps", "--full", "--directory", "src", "--quiet")
        self.assertEqual(code, 0)
        self.assertEqual(set(cs.load_mtime_index(self.root)), {"src/a.py"})


class TestJavascriptParser(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.reset_js_parser_state()

    def test_overlapping_patterns_emit_one_edge_and_dynamic_is_flagged(self):
        from wikifier.parsers.javascript import parse_javascript_imports

        self.write("src/b.ts", "export const b = 1;\n")
        self.write("src/d.ts", "export default 1;\n")
        self.write("src/a.ts", "export * from './b';\nimport type { T } from './b';\nconst d = await import('./d');\n")
        edges = parse_javascript_imports(str(self.root / "src" / "a.ts"))
        by_stmt = [(e["statement_type"], e["raw_module"]) for e in edges]
        self.assertEqual(by_stmt.count(("export_star", "./b")), 1, by_stmt)
        self.assertNotIn(("export_from", "./b"), by_stmt)
        self.assertIn(("import_type", "./b"), by_stmt)
        dynamic = [e for e in edges if e["raw_module"] == "./d"]
        self.assertTrue(dynamic[0]["is_dynamic"])
        self.assertEqual(dynamic[0]["dynamic_type"], "literal")

    def test_top_level_import_after_code_is_not_conditional(self):
        from wikifier.parsers.javascript import parse_javascript_imports

        self.write("src/x.ts", "export const x = 1;\n")
        self.write("src/a.ts", (
            "const opts: Record<string, number> = { a: 1 };\n"
            "if (opts.a) { console.log('enableFeature'); }\n"
            "import { x } from './x';\n"
            "if (process.env.DEBUG) {\n  require('./x');\n}\n"
        ))
        edges = parse_javascript_imports(str(self.root / "src" / "a.ts"))
        static = next(e for e in edges if e["statement_type"] == "es_import")
        guarded = next(e for e in edges if e["statement_type"] == "require")
        self.assertFalse(static["is_conditional"])
        self.assertTrue(guarded["is_conditional"])

    def test_external_package_is_not_a_barrel(self):
        from wikifier.parsers.javascript import parse_javascript_imports

        self.write("src/a.ts", "import React from 'react';\n")
        edge = parse_javascript_imports(str(self.root / "src" / "a.ts"))[0]
        self.assertFalse(edge["via_barrel"])

    def test_unresolved_relative_import_is_not_a_graph_node(self):
        self.write("src/a.js", "import x from './missing';\n")
        self.assertTrue(api.update_maps(full=True)["success"])
        pairs = ic.load_cache(self.root)["src/a.js"]["resolved_pairs"]
        self.assertEqual([p["resolved"] for p in pairs], [""])


class TestPythonParser(TempProjectTestCase):
    def test_guarded_imports_are_conditional(self):
        from wikifier.parsers.python import parse_python_imports_from_string

        edges = parse_python_imports_from_string(
            "import os\ntry:\n    import ujson\nexcept ImportError:\n    import json\nif os.name == 'nt':\n    import winreg\n"
        )
        flags = {e["raw_module"]: (e["is_conditional"], e["conditional_context"]) for e in edges}
        self.assertEqual(flags["os"], (False, None))
        self.assertEqual(flags["ujson"], (True, "try"))
        self.assertEqual(flags["winreg"], (True, "if"))

    def test_regex_fallback_for_unparseable_source(self):
        from wikifier.parsers.python import parse_python_imports_from_string

        edges = parse_python_imports_from_string("import os\nprint 'python 2'\nfrom json import loads\n")
        self.assertEqual({e["raw_module"] for e in edges}, {"os", "json"})
        self.assertEqual({e["parse_mode"] for e in edges}, {"regex-fallback"})


class TestCheckChanges(TempProjectTestCase):
    def test_monitored_markdown_files_are_watched_and_pending_survives(self):
        (self.root / "monitored_paths.txt").write_text("README.md\n", encoding="utf-8")
        self.write("README.md", "# v1\n")
        self.assertTrue(api.mark_green("README.md")["success"])
        self.write("README.md", "# v2\n")
        res = api.check_changes()
        self.assertEqual(res["changes_detected"], 1, res)
        self.assertIn("README.md", (self.root / "pending_updates.md").read_text())

    def test_already_flagged_files_are_not_rejournaled(self):
        (self.root / "monitored_paths.txt").write_text("src/\n", encoding="utf-8")
        self.write("src/a.py", "x = 1\n")
        api.check_changes()
        api.check_changes()
        journal = api.journal()["entries"]
        self.assertEqual(sum(1 for e in journal if e["file"] == "src/a.py"), 1)

    def test_warm_runs_do_not_hash_unchanged_files(self):
        for i in range(5):
            self.write(f"src/m{i}.py", f"x = {i}\n")
        self.assertTrue(api.update_maps(full=True)["success"])
        with mock.patch("wikifier.cache.files.compute_file_content_hash") as hashed:
            dirty = ic.compute_files_needing_reparse(self.root, sorted((self.root / "src").glob("*.py")))
        self.assertEqual(dirty, [])
        hashed.assert_not_called()


class TestDerivedSummariesRefresh(TempProjectTestCase):
    def test_acs_summary_recomputed_when_edges_change(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "x = 1\n")
        api.update_maps(full=True)
        first = cs.load_meta(self.root, keys=("_acs_summary",))["_acs_summary"]["total_scored_edges"]
        self.write("a.py", "import b\nimport c\nimport d\n")
        api.update_maps()
        second = cs.load_meta(self.root, keys=("_acs_summary",))["_acs_summary"]["total_scored_edges"]
        self.assertEqual(second, first + 2)


class TestBarrelCache(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.reset_js_parser_state()

    def test_barrel_cache_persists_and_invalidation_is_exact(self):
        self.write("a/index.js", "export * from './leaf.js';\n")
        self.write("a/leaf.js", "export const v = 1;\n")
        self.write("b/index.js", "export const w = 2;\n")
        self.write("consumer.js", "import { v } from './a';\n")
        self.write("other.js", "import { w } from './b';\n")
        self.assertTrue(api.update_maps(full=True)["success"])
        meta = cs.load_meta(self.root)
        self.assertTrue(meta.get("_barrel_resolutions"), "barrel cache must persist")
        stale = ic.invalidate_stale_barrel_entries(meta, self.root, changed_files=["a/leaf.js"])
        self.assertIn("consumer.js", stale)
        self.assertNotIn("other.js", stale, "a basename match must not invalidate unrelated importers")

    def test_full_rebuild_in_fresh_process(self):
        self.write("barrel/index.js", "export * from './leaf.js';\n")
        self.write("barrel/leaf.js", "export const v = 1;\n")
        self.write("consumer.js", "import { v } from './barrel';\n")
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), WIKIFIER_PROJECT_ROOT=str(self.root))
        for _ in range(2):
            proc = subprocess.run([sys.executable, "-m", "wikifier", "update-maps", "--full", "--quiet"],
                                  env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestDeletion(TempProjectTestCase):
    def test_record_deletion_cleans_graph(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "x = 1\n")
        api.update_maps(full=True)
        (self.root / "b.py").unlink()
        res = api.record_deletion("b.py", "removed")
        self.assertTrue(res["success"], res)
        self.assertTrue(res["graph_cleanup"]["removed_entry"])
        self.assertNotIn("b.py", ic.load_cache(self.root))


class TestCacheStore(TempProjectTestCase):
    def test_corrupt_database_is_an_error_not_a_silent_fallback(self):
        self.write("a.py", "x = 1\n")
        api.update_maps(full=True)
        cs.sqlite_path(self.root).write_bytes(b"not a database" * 100)
        with self.assertRaises(sqlite3.DatabaseError):
            ic.load_cache(self.root)

    def test_dependents_use_indexed_edges(self):
        self.write("a.py", "import c\n")
        self.write("b.py", "import c\n")
        self.write("c.py", "x = 1\n")
        api.update_maps(full=True)
        self.assertEqual(cs.load_dependents(self.root, "c.py"), ["a.py", "b.py"])
        self.assertEqual(cs.load_dependencies(self.root, "a.py"), ["c.py"])


class TestJournal(TempProjectTestCase):
    def test_identical_retry_is_deduplicated(self):
        self.write("a.py", "x = 1\n")
        first = api.record_change("a.py", "same reason")
        retry = api.record_change("a.py", "same reason")
        self.assertTrue(first["journaled"])
        self.assertFalse(retry["journaled"])
        self.assertEqual(len(api.journal()["entries"]), 1)


class TestHealingStatistics(TempProjectTestCase):
    def test_stubs_are_counted(self):
        self.write("a.py", "x = 1\n")
        health.seed_health_from_map(self.root, map_keys=["a.py"], only_monitored=False)
        self.write("a.py.wiki.md", "# A\n\n## Purpose\n" + "word " * 300)
        stats = health.get_healing_statistics(self.root)
        self.assertEqual(stats["current_initial_stubs"], 1)
        self.assertEqual(stats["healable_stubs"]["total"], 1)


class TestLocking(TempProjectTestCase):
    def test_reentrancy_is_per_thread(self):
        acquired = threading.Event()
        with locking.file_lock(self.root):
            def other():
                try:
                    with locking.file_lock(self.root, timeout=0.2):
                        acquired.set()
                except locking.LockTimeoutError:
                    pass
            t = threading.Thread(target=other)
            t.start()
            t.join()
            with locking.file_lock(self.root, timeout=0.2):  # same thread: re-entrant
                pass
        self.assertFalse(acquired.is_set(), "another thread must not enter while the lock is held")


class TestStreaming(TempProjectTestCase):
    def test_stream_persists_the_map(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "x = 1\n")
        from wikifier.streaming import run_update_stream

        events = list(run_update_stream(root=self.root, force_full=True))
        kinds = [e["event_type"] for e in events]
        self.assertEqual(kinds[0], "start")
        self.assertEqual(kinds[-1], "complete")
        self.assertEqual(kinds.count("file_parsed"), 2)
        self.assertEqual(cs.load_dependents(self.root, "b.py"), ["a.py"])


class TestDaemon(TempProjectTestCase):
    def test_systemd_unit_targets_the_project(self):
        from wikifier import daemon

        unit = daemon.generate_systemd_unit(self.root)
        self.assertIn(f"WorkingDirectory={self.root}", unit)
        self.assertIn(f"WIKIFIER_PROJECT_ROOT={self.root}", unit)

    def test_metrics_snapshot_uses_the_health_module(self):
        from wikifier import daemon

        with mock.patch.object(daemon, "POLL_INTERVAL_DEFAULT", 0), \
             mock.patch.object(daemon, "_run_update_maps"), \
             mock.patch.object(daemon, "_run_check_changes"), \
             redirect_stdout(io.StringIO()):
            daemon.daemon_loop(max_cycles=0)
        self.assertTrue((self.root / ".wikifier_staging" / "metrics_latest.json").exists())


class TestMcpAdapter(TempProjectTestCase):
    def test_server_has_no_shell_fallback(self):
        src = (REPO_ROOT / "wikifier" / "mcp" / "server_impl.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", src)
        self.assertNotIn("_run_wikifier_command", src)

    def test_bad_root_is_an_error(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("optional mcp extra not installed")
        from wikifier.mcp import server_impl as server

        res = server.record_change("a.py", "x", project_root=str(self.root / "nope"))
        self.assertFalse(res["success"])
        um = server.update_maps(project_root=str(self.root / "nope"))
        self.assertFalse(um.success)


if __name__ == "__main__":
    unittest.main()


class TestServeApi(TempProjectTestCase):
    def test_read_only_api(self):
        import json
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer

        from wikifier import serve

        self.write("a.py", "import b\n")
        self.write("b.py", "x = 1\n")
        self.write("b.py.wiki.md", "# b\nHolds x.\n")
        api.update_maps(full=True)
        serve.DashboardHandler.root = self.root
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve.DashboardHandler)
        server.RequestHandlerClass.log_message = lambda *a: None
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def get(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        status, info = get("/__wikifier/status")
        self.assertEqual(status, 200)
        self.assertIn("file", info["api"])
        status, data = get("/__wikifier/api/file?path=b.py")
        self.assertEqual(status, 200)
        self.assertEqual(data["dependents"], ["a.py"])
        self.assertIn("Holds x", data["wiki"])
        status, data = get("/__wikifier/api/file?path=../outside.py")
        self.assertEqual(status, 400)
        status, _ = get("/__wikifier/api/unknown")
        self.assertEqual(status, 404)


class TestIncrementalDeletion(TempProjectTestCase):
    def test_incremental_update_drops_deleted_files(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "import c\n")
        self.write("c.py", "x = 1\n")
        api.update_maps(full=True)
        (self.root / "b.py").unlink()
        res = api.update_maps()
        self.assertEqual(res.get("files_removed"), 1, res)
        self.assertNotIn("b.py", cs.load_mtime_index(self.root))
        self.assertEqual(cs.load_dependents(self.root, "c.py"), [])


class TestDiagnosticSamples(unittest.TestCase):
    def test_actionable_samples_not_crowded_out_by_externals(self):
        from wikifier import diagnostics as d

        def pair(raw, cat):
            return {"src": "a.py", "raw": raw, "confidence": "low",
                    "diagnostic": {"category": cat, "reason": "r"}}

        pairs = [pair("ext%d" % i, "external_or_bare") for i in range(200)]
        pairs += [pair("dyn%d" % i, "creative_dynamic") for i in range(3)]
        s = d.summarize_diagnostics(pairs)
        cats = [x["category"] for x in s["samples"]]
        self.assertEqual(cats[:3], ["creative_dynamic"] * 3)
        self.assertEqual(cats.count("external_or_bare"), 5)
        self.assertTrue(s["has_more"])


class TestCheckChangesAfterUpdateMaps(TempProjectTestCase):
    def test_edit_seen_even_if_update_maps_ran_first(self):
        self.write("a.py", "x = 1\n")
        api.update_maps(full=True)
        self.assertTrue(api.mark_green("a.py", "baseline")["success"])
        time.sleep(0.01)
        self.write("a.py", "x = 2\n")
        api.update_maps()  # advances the parse cache before check_changes runs
        res = api.check_changes()
        self.assertIn("a.py", res["changed_files"], res)

    def test_touch_without_change_is_not_flagged_and_not_rehashed(self):
        self.write("a.py", "x = 1\n")
        api.update_maps(full=True)
        api.mark_green("a.py", "baseline")
        os.utime(self.root / "a.py", ns=(1, 1))
        res = api.check_changes()
        self.assertEqual(res["changed_files"], [])
        self.assertEqual(res["skipped_mtime_only"], 1)
        self.assertEqual(api.check_changes()["dirty_total"], 0)


class TestModuleExitCode(TempProjectTestCase):
    def test_python_dash_m_propagates_failure(self):
        env = dict(os.environ, WIKIFIER_PROJECT_ROOT=str(self.root),
                   PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        proc = subprocess.run([sys.executable, "-m", "wikifier", "mark-green", "missing.py"],
                              cwd=str(self.root), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)


class TestPythonCaseExactSubmodules(TempProjectTestCase):
    def test_class_import_is_not_a_submodule_on_case_insensitive_fs(self):
        self.write("pkg/__init__.py", "from .dagrun import DagRun\n")
        self.write("pkg/dagrun.py", "class DagRun: pass\n")
        self.write("app.py", "from pkg import DagRun\n")
        api.update_maps(full=True)
        deps = cs.load_dependencies(self.root, "app.py")
        self.assertNotIn("pkg/DagRun.py", deps)
        self.assertIn("pkg/__init__.py", deps)
