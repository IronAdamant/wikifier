"""Sharded agent folder maps vs human library.md mermaid.

Drives shipped update_maps / session_bootstrap / list_paths / CLI main.
"""

from __future__ import annotations

import importlib
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import cli
from wikifier.agent_loop import session_bootstrap
from wikifier.map_index import (
    map_index_path,
    shard_path,
    write_map_index,
)


def _seed_mapped_tree(tc: TempProjectTestCase) -> None:
    tc.write("map_paths.txt", "pkg/\n")
    tc.write("pkg/a.py", "from pkg import b\nx = 1\n")
    tc.write("pkg/b.py", "y = 2\n")
    tc.write("pkg/sub/c.py", "from pkg import a\nz = 3\n")


def _assert_names_only(tc: unittest.TestCase, payload: dict) -> None:
    blob = json.dumps(payload)
    tc.assertNotIn("```mermaid", blob)
    tc.assertNotIn("graph TD", blob)
    tc.assertNotIn("graph LR", blob)
    for f in payload.get("files") or []:
        tc.assertIsInstance(f, str)
        tc.assertNotIn(" — ", f)
        tc.assertNotIn("\n", f)
    for d in payload.get("dirs") or []:
        tc.assertIn("p", d)
        tc.assertIn("n", d)
        tc.assertNotIn(" — ", str(d.get("p") or ""))


class TestMapIndexPersist(TempProjectTestCase):
    def test_update_maps_writes_human_library_and_folder_shards(self):
        _seed_mapped_tree(self)
        res = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(res.get("success"), res)
        lib = (self.root / "library.md").read_text(encoding="utf-8")
        self.assertIn("## File Tree", lib)
        self.assertIn("```mermaid", lib)
        root_card = map_index_path(self.root)
        self.assertTrue(root_card.is_file(), root_card)
        index = json.loads(root_card.read_text(encoding="utf-8"))
        _assert_names_only(self, index)
        self.assertEqual(index.get("kind"), "root")
        self.assertEqual(index.get("depth"), 1)
        dir_paths = [str(d.get("p") or "") for d in (index.get("dirs") or [])]
        self.assertTrue(any(p.rstrip("/") == "pkg" or p == "pkg/" for p in dir_paths), index)
        self.assertNotIn("pkg/sub/c.py", index.get("files") or [])
        pkg_card = json.loads(shard_path(self.root, "pkg/").read_text(encoding="utf-8"))
        _assert_names_only(self, pkg_card)
        files = pkg_card.get("files") or []
        self.assertTrue(any(str(f).endswith("pkg/a.py") for f in files), files)
        self.assertTrue(any(str(f).endswith("pkg/b.py") for f in files), files)
        self.assertFalse(any(str(f).endswith("pkg/sub/c.py") for f in files), files)
        sub_dirs = [str(d.get("p") or "") for d in (pkg_card.get("dirs") or [])]
        self.assertTrue(any("sub" in p for p in sub_dirs), pkg_card)
        hop = pkg_card.get("hop") or {}
        self.assertEqual(hop.get("files"), "prepare_edit")
        self.assertEqual(hop.get("dirs"), "list_paths")
        mi = res.get("map_index") or {}
        self.assertTrue(mi.get("success"), mi)

    def test_zero_dirty_writes_catalog_when_missing(self):
        _seed_mapped_tree(self)
        first = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(first.get("success"), first)
        cat_path = map_index_path(self.root)
        self.assertTrue(cat_path.is_file())
        cat_path.unlink()
        second = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(second.get("success"), second)
        self.assertTrue(cat_path.is_file(), "zero-dirty must recreate missing root card")

    def test_unchanged_child_set_skips_shard_rewrite(self):
        _seed_mapped_tree(self)
        self.assertTrue(cli.update_maps(project_root=self.root, full=True).get("success"))
        again = write_map_index(self.root)
        self.assertTrue(again.get("success"), again)
        self.assertGreaterEqual(int(again.get("shards_skipped") or 0), 1, again)
        self.assertEqual(int(again.get("shards_written") or 0), 0, again)

    def test_new_file_rewrites_affected_folder_cards(self):
        _seed_mapped_tree(self)
        self.assertTrue(cli.update_maps(project_root=self.root, full=True).get("success"))
        self.write("pkg/sub/d.py", "w = 4\n")
        self.assertTrue(cli.update_maps(project_root=self.root, full=False).get("success"))
        changed = write_map_index(self.root)
        # persist already wrote shards; second write should skip if persist saw d.py
        sub = json.loads(shard_path(self.root, "pkg/sub/").read_text(encoding="utf-8"))
        files = [str(f).replace("\\", "/") for f in (sub.get("files") or [])]
        self.assertTrue(any(f.endswith("pkg/sub/d.py") for f in files), files)
        self.assertTrue(any(f.endswith("pkg/sub/c.py") for f in files), files)
        self.assertGreaterEqual(int(sub.get("file_count") or 0), 2)
        self.assertIsNotNone(changed.get("success"))


class TestBootstrapCatalog(TempProjectTestCase):
    def test_session_bootstrap_root_card_no_mermaid(self):
        _seed_mapped_tree(self)
        res = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(res.get("success"), res)
        boot = session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"), boot)
        blob = json.dumps(boot)
        self.assertNotIn("```mermaid", blob)
        self.assertNotIn("graph TD", blob)
        mi = boot.get("map_index") or {}
        self.assertTrue(mi.get("success"), mi)
        _assert_names_only(self, mi)
        self.assertEqual(mi.get("depth"), 1)
        self.assertEqual(mi.get("kind"), "root")
        dir_paths = [str(d.get("p") or "") for d in (mi.get("dirs") or [])]
        self.assertTrue(any("pkg" in p for p in dir_paths), mi)
        self.assertNotIn("pkg/sub/c.py", mi.get("files") or [])
        hop = mi.get("hop") or {}
        self.assertEqual(hop.get("files"), "prepare_edit")
        self.assertEqual(hop.get("dirs"), "list_paths")

    def test_session_bootstrap_caps_fat_root_files_only(self):
        self.write("map_paths.txt", ".\n")
        for i in range(5):
            self.write("m{0}.py".format(i), "x = {0}\n".format(i))
        res = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(res.get("success"), res)
        boot = session_bootstrap(project_root=self.root, map_index_file_budget=2)
        mi = boot.get("map_index") or {}
        self.assertTrue(mi.get("files_truncated"), mi)
        self.assertLessEqual(len(mi.get("files") or []), 2)
        self.assertGreaterEqual(int(mi.get("file_count") or 0), 5)


class TestListPaths(TempProjectTestCase):
    def test_list_paths_depth1_is_one_folder_card(self):
        _seed_mapped_tree(self)
        res = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(res.get("success"), res)
        out = cli.list_paths(prefix="pkg", project_root=self.root, depth=1)
        self.assertTrue(out.get("success"), out)
        _assert_names_only(self, out)
        files = [str(f).replace("\\", "/") for f in (out.get("files") or [])]
        self.assertTrue(any(f.endswith("pkg/a.py") for f in files), files)
        self.assertFalse(any(f.endswith("pkg/sub/c.py") for f in files), files)
        dirs = [str(d.get("p") or "") for d in (out.get("dirs") or [])]
        self.assertTrue(any("sub" in p for p in dirs), out)
        self.assertEqual((out.get("hop") or {}).get("files"), "prepare_edit")

    def test_list_paths_nested_folder_and_recursive(self):
        _seed_mapped_tree(self)
        res = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(res.get("success"), res)
        nested = cli.list_paths(prefix="pkg/sub", project_root=self.root)
        files = [str(f).replace("\\", "/") for f in (nested.get("files") or [])]
        self.assertTrue(any(f.endswith("pkg/sub/c.py") for f in files), files)
        rec = cli.list_paths(prefix="pkg", project_root=self.root, depth=0)
        rec_files = [str(f).replace("\\", "/") for f in (rec.get("files") or [])]
        self.assertTrue(any(f.endswith("pkg/sub/c.py") for f in rec_files), rec_files)
        self.assertTrue(any(f.endswith("pkg/a.py") for f in rec_files), rec_files)


class TestCliCatalog(TempProjectTestCase):
    def test_cli_session_bootstrap_and_list_paths(self):
        _seed_mapped_tree(self)
        up = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(up.get("success"), up)
        from wikifier.cli import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--target", str(self.root), "session-bootstrap"])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("map_index", out)
        self.assertIn("pkg/", out)
        self.assertNotIn("Unknown command", out)
        self.assertNotIn("```mermaid", out)

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = main(["--target", str(self.root), "list-paths", "pkg/sub"])
        out2 = buf2.getvalue()
        self.assertEqual(rc2, 0, out2)
        self.assertIn("pkg/sub/c.py", out2)
        data = json.loads(out2)
        self.assertTrue(data.get("success"), data)
        self.assertEqual((data.get("hop") or {}).get("files"), "prepare_edit")


class TestMcpListPathsRegistered(unittest.TestCase):
    def test_list_paths_on_server_module_when_mcp_extra(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("optional mcp extra not installed")
        srv = importlib.import_module("wikifier.mcp.server_impl")
        self.assertTrue(hasattr(srv, "list_paths"))
        self.assertTrue(callable(srv.list_paths))
        import inspect
        params = inspect.signature(srv.list_paths).parameters
        self.assertIn("depth", params)


class TestPyprojectZeroDep(unittest.TestCase):
    def test_pyproject_dependencies_empty(self):
        text = Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("dependencies = []", text)
