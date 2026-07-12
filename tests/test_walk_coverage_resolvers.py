"""Walk cost, Core map_coverage, thin C#/C++ resolve, cache-status (shipped APIs)."""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import cli
from wikifier import cache_store as cs
from wikifier.candidates import (
    collect_candidate_source_files,
    try_cached_candidate_rels,
    candidate_list_meta,
)
from wikifier.agent_loop import build_structured_actions


class TestScopedCollect(TempProjectTestCase):
    def test_directory_scope_limits_candidates(self):
        self.write("pkg/a.py", "x=1\n")
        self.write("other/b.py", "y=1\n")
        cands = collect_candidate_source_files(self.root, directory="pkg")
        rels = []
        for p in cands:
            try:
                rels.append(str(Path(p).resolve().relative_to(self.root.resolve())))
            except Exception:
                rels.append(os.path.realpath(str(p)))
        self.assertTrue(any("pkg" in r and r.endswith("a.py") for r in rels), rels)
        self.assertFalse(any("other" in r for r in rels), rels)

    def test_wiki_monitored_paths_do_not_collapse_map(self):
        """monitored_paths with only wiki files must not yield a 1-file map."""
        self.write("pkg/a.py", "x=1\n")
        self.write("pkg/b.py", "y=1\n")
        self.write("skills/run.md", "# wiki\n")
        self.write(
            "monitored_paths.txt",
            "# wiki only\nskills/run.md\nREADME.md\npkg/a.py\n",
        )
        self.write("README.md", "# r\n")
        cands = collect_candidate_source_files(self.root, directory=None, use_monitored=True)
        # Must walk full tree, not just a.py from monitored
        py = [p for p in cands if p.suffix == ".py"]
        self.assertGreaterEqual(len(py), 2, [str(p) for p in py])

    def test_candidate_reuse_true_when_git_clean(self):
        """Second warm reuses candidate list when scope clean — honest assert."""
        self.write("m.py", "print(1)\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        n1 = int(r1.get("parseable_files") or 0)
        self.assertGreaterEqual(n1, 1)
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        r3 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r3.get("success"), r3)
        self.assertTrue(
            r3.get("candidates_reused") is True,
            f"expected reuse on third warm; r2={r2.get('candidates_reused')} r3={r3}",
        )
        self.assertEqual(int(r3.get("parseable_files") or 0), n1)

    def test_nested_new_file_invalidates_reuse(self):
        """Adding a nested source file must expand candidates (not stale reuse)."""
        self.write("pkg/a.py", "x=1\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        n1 = int(r1.get("parseable_files") or 0)
        # Nested new file under existing package
        self.write("pkg/nested/b.py", "y=2\n")
        time.sleep(0.05)
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        n2 = int(r2.get("parseable_files") or 0)
        self.assertGreater(
            n2, n1,
            f"nested add must expand parseable_files: before={n1} after={n2} reused={r2.get('candidates_reused')}",
        )
        # Must not have reused stale list of size n1
        if r2.get("candidates_reused"):
            self.fail("must not reuse candidate list after nested source add")

    def test_poisoned_one_file_blob_not_reused(self):
        """Plant 1-file candidate blob with matching fp; live tree has 2 sources → no reuse."""
        self.write("pkg/a.py", "x=1\n")
        self.write("pkg/b.py", "y=2\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        live_n = int(r1.get("parseable_files") or 0)
        self.assertGreaterEqual(live_n, 2)
        # Poison meta: same directory scope, current fp, but only one rel
        from wikifier.candidates import scope_fingerprint, candidate_list_meta
        from wikifier import cache_store as cs
        fp = scope_fingerprint(self.root, None)
        poison = {
            "fp": fp,
            "directory": None,
            "count": 1,
            "rels": ["pkg/a.py"],
        }
        cs.save_meta_key(self.root, "_candidate_list", poison)
        # Direct API: try_cached must return None
        meta = cs.load_meta(self.root, keys=("_candidate_list",))
        from wikifier.candidates import try_cached_candidate_rels
        cached = try_cached_candidate_rels(meta, self.root, None)
        self.assertIsNone(
            cached,
            f"poisoned 1-file blob must not reuse when live has {live_n} sources",
        )
        # Shipped update_maps must not report parseable_files=1 with reused=true
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        self.assertGreaterEqual(int(r2.get("parseable_files") or 0), 2, r2)
        self.assertFalse(
            r2.get("candidates_reused") is True and int(r2.get("parseable_files") or 0) == 1,
            r2,
        )


class TestCoverageInCore(TempProjectTestCase):
    def test_suggest_surfaces_incomplete_map_action(self):
        for i in range(5):
            self.write(f"f{i}.py", f"v={i}\n")
        r = cli.update_maps(project_root=self.root, full=True, max_files=2)
        self.assertTrue(r.get("success"), r)
        cov = r.get("map_coverage") or {}
        self.assertFalse(cov.get("complete"), cov)
        sug = cli.suggest_next_actions(project_root=self.root, format="json")
        self.assertTrue(sug.get("success"), sug)
        self.assertIn("map_coverage", sug)
        self.assertFalse((sug.get("map_coverage") or {}).get("complete"))
        actions = sug.get("actions") or []
        kinds = [a.get("action") for a in actions]
        self.assertIn("update_maps_until_complete", kinds, actions)
        text = " ".join(sug.get("suggestions") or [])
        self.assertIn("INCOMPLETE", text.upper())

    def test_build_structured_actions_incomplete(self):
        acts = build_structured_actions(
            clean=True,
            map_coverage={"complete": False, "files_remaining_dirty": 9},
        )
        self.assertTrue(any(a["action"] == "update_maps_until_complete" for a in acts))


class TestCacheStatus(TempProjectTestCase):
    def test_cache_status_shape(self):
        self.write("z.py", "z=1\n")
        cli.update_maps(project_root=self.root, full=True)
        st = cli.cache_status(project_root=self.root)
        self.assertTrue(st.get("success"), st)
        self.assertIn(st.get("cache_backend"), ("sqlite", "sqlite+json", "json"))
        self.assertIn("sqlite_bytes", st)
        self.assertIn("dual_write_policy", st)
        self.assertIn("migrate_note", st)
        st2 = cs.cache_status(self.root)
        self.assertEqual(st2.get("cache_backend"), st.get("cache_backend"))


class TestCsharpProjectResolve(TempProjectTestCase):
    def test_project_namespace_resolves(self):
        from wikifier.parsers import csharp as cs_parser

        self.write(
            "Demo.csproj",
            "<Project><PropertyGroup><RootNamespace>Demo</RootNamespace></PropertyGroup></Project>\n",
        )
        self.write("Util/Helper.cs", "namespace Demo.Util { class Helper {} }\n")
        main = self.write(
            "Program.cs",
            "using Demo.Util;\nnamespace Demo { class Program {} }\n",
        )
        edges = cs_parser.parse_csharp_imports(str(main))
        self.assertTrue(edges)
        resolved = [e for e in edges if e.get("resolved_path")]
        self.assertTrue(resolved, msg=f"edges={edges}")
        self.assertTrue(
            any("Util" in (e.get("resolved_path") or "") for e in resolved),
            resolved,
        )


class TestCCppLocalInclude(TempProjectTestCase):
    def test_include_dir_resolve(self):
        from wikifier.parsers import c_cpp as cc

        self.write("include/foo.h", "#pragma once\n")
        src = self.write("src/main.c", '#include "foo.h"\nint main(){return 0;}\n')
        edges = cc.parse_c_cpp_imports(str(src))
        self.assertTrue(edges)
        self.assertTrue(
            any(e.get("resolved_path") and "foo.h" in e["resolved_path"] for e in edges),
            edges,
        )


if __name__ == "__main__":
    unittest.main()
