"""Index-first dirty, map_paths vs monitored_paths, JSON dual-write deprecation."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import cli
from wikifier import cache_store as cs
from wikifier.candidates import (
    collect_candidate_source_files,
    resolve_candidates,
    try_cached_candidate_rels,
    scope_fingerprint,
)
from wikifier import import_cache as ic


class TestMapPathsSeparate(TempProjectTestCase):
    def test_map_paths_not_wiki_monitored(self):
        """Wiki monitored_paths + map_paths package dirs: map covers package sources."""
        self.write("skills/run.md", "# wiki\n")
        self.write("monitored_paths.txt", "skills/run.md\nREADME.md\n")
        self.write("README.md", "# r\n")
        self.write("map_paths.txt", "pkg/\n")
        self.write("pkg/a.py", "x=1\n")
        self.write("pkg/b.py", "y=2\n")
        self.write("other/c.py", "z=3\n")
        cands = collect_candidate_source_files(self.root, directory=None)
        rels = []
        for p in cands:
            try:
                rels.append(str(Path(p).resolve().relative_to(self.root.resolve())))
            except Exception:
                rels.append(str(p))
        self.assertTrue(any(r.endswith("a.py") for r in rels), rels)
        self.assertTrue(any(r.endswith("b.py") for r in rels), rels)
        self.assertFalse(any("other" in r for r in rels), rels)
        r = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r.get("success"), r)
        self.assertGreaterEqual(int(r.get("parseable_files") or 0), 2, r)

    def test_directory_overrides_map_paths(self):
        self.write("map_paths.txt", "pkg/\n")
        self.write("pkg/a.py", "1\n")
        self.write("other/b.py", "2\n")
        cands = collect_candidate_source_files(self.root, directory="other")
        keys = [os.path.realpath(str(p)) for p in cands]
        self.assertTrue(any(k.endswith("b.py") for k in keys), keys)
        self.assertFalse(any("/pkg/" in k for k in keys), keys)

    def test_map_paths_subset_reuses_despite_outside_sources(self):
        """map_paths=pkg/ with extra sources outside: warm2 must reuse (live count scoped)."""
        self.write("map_paths.txt", "pkg/\n")
        self.write("monitored_paths.txt", "docs/note.md\n")
        self.write("docs/note.md", "# wiki only\n")
        self.write("pkg/a.py", "x=1\n")
        self.write("pkg/b.py", "y=2\n")
        self.write("outside/c.py", "z=3\n")  # not in map_paths
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        n1 = int(r1.get("parseable_files") or 0)
        self.assertEqual(n1, 2, r1)  # only pkg/, not outside/
        # Second and third warm: live count must match map scope (2), not full tree (3)
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        r3 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r3.get("success"), r3)
        self.assertEqual(int(r3.get("parseable_files") or 0), 2, r3)
        self.assertTrue(
            r3.get("candidates_reused") is True,
            f"map_paths subset must reuse on warm; r2={r2.get('candidates_reused')} r3={r3}",
        )
        self.assertFalse(r3.get("candidates_relisted"), r3)


class TestIndexFirstResolve(TempProjectTestCase):
    def test_resolve_candidates_index_first_flag(self):
        self.write("a.py", "print(1)\n")
        self.write("b.py", "print(2)\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r1.get("success"), r1)
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        r3 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r3.get("success"), r3)
        self.assertTrue(r3.get("candidates_reused") or r3.get("index_first_dirty"), r3)
        self.assertFalse(r3.get("candidates_relisted"), r3)
        self.assertEqual(int(r3.get("parseable_files") or 0), 2)

    def test_poison_blob_rejected_via_index(self):
        self.write("a.py", "1\n")
        self.write("b.py", "2\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertGreaterEqual(int(r1.get("parseable_files") or 0), 2)
        index = ic.load_mtime_index(self.root)
        poison = {
            "fp": scope_fingerprint(self.root, None),
            "directory": None,
            "count": 1,
            "rels": ["a.py"],
        }
        cs.save_meta_key(self.root, "_candidate_list", poison)
        meta = cs.load_meta(self.root, keys=("_candidate_list",))
        # Full index has a+b → larger than blob → reject
        self.assertIsNone(try_cached_candidate_rels(meta, self.root, None, index=index))
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertGreaterEqual(int(r2.get("parseable_files") or 0), 2, r2)

    def test_empty_index_uses_live_count_not_false_reuse(self):
        """Empty index must not trust blob alone (live-count path)."""
        self.write("a.py", "1\n")
        self.write("b.py", "2\n")
        r1 = cli.update_maps(project_root=self.root, full=True)
        self.assertGreaterEqual(int(r1.get("parseable_files") or 0), 2)
        poison = {
            "fp": scope_fingerprint(self.root, None),
            "directory": None,
            "count": 1,
            "rels": ["a.py"],
        }
        cs.save_meta_key(self.root, "_candidate_list", poison)
        meta = cs.load_meta(self.root, keys=("_candidate_list",))
        # empty dict and None both force live count → poison count 1 ≠ live 2
        self.assertIsNone(try_cached_candidate_rels(meta, self.root, None, index={}))
        self.assertIsNone(try_cached_candidate_rels(meta, self.root, None, index=None))

    def test_partial_index_same_count_different_keys_relists(self):
        """Index {a} vs blob {b} same count → must not reuse."""
        self.write("a.py", "1\n")
        self.write("b.py", "2\n")
        cli.update_maps(project_root=self.root, full=True)
        fp = scope_fingerprint(self.root, None)
        blob = {"fp": fp, "directory": None, "count": 1, "rels": ["b.py"]}
        partial_index = {"a.py": {"mtime": 1, "content_hash": None}}
        meta = {"_candidate_list": blob}
        self.assertIsNone(
            try_cached_candidate_rels(meta, self.root, None, index=partial_index)
        )

    def test_partial_index_subset_requires_live_count(self):
        """Index {a} subset of blob {a,b}: live count decides (not silent reuse on index alone)."""
        self.write("a.py", "1\n")
        self.write("b.py", "2\n")
        cli.update_maps(project_root=self.root, full=True)
        fp = scope_fingerprint(self.root, None)
        # Correct blob for 2 files but partial index
        blob = {
            "fp": fp,
            "directory": None,
            "count": 2,
            "rels": ["a.py", "b.py"],
        }
        partial = {"a.py": {"mtime": 1}}
        meta = {"_candidate_list": blob}
        # Live count == 2 → may reuse after live count; must not reject solely on partial
        got = try_cached_candidate_rels(meta, self.root, None, index=partial)
        self.assertIsNotNone(got)
        self.assertEqual(len(got), 2)
        # Poison blob count 1 with partial index {a}
        poison = {"fp": fp, "directory": None, "count": 1, "rels": ["a.py"]}
        self.assertIsNone(
            try_cached_candidate_rels(
                {"_candidate_list": poison}, self.root, None, index=partial
            )
        )


class TestJsonDualWriteDeprecated(TempProjectTestCase):
    def test_default_save_sqlite_only(self):
        self.write("x.py", "x=1\n")
        os.environ.pop("WIKIFIER_CACHE_JSON", None)
        r = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r.get("success"), r)
        self.assertTrue(cs.has_sqlite(self.root))
        st = cli.cache_status(project_root=self.root)
        self.assertIn("DEPRECATED", (st.get("dual_write_policy") or "").upper())
        cache = {"a.py": {"mtime": 1, "imports": [], "resolved_pairs": []}}
        for i in range(5):
            cache[f"f{i}.py"] = {"mtime": 1, "imports": [], "resolved_pairs": []}
        backend = cs.save_cache_dict(self.root, cache)
        self.assertEqual(backend, "sqlite", backend)

    def test_opt_in_dual_write(self):
        self.write("y.py", "y=1\n")
        os.environ["WIKIFIER_CACHE_JSON"] = "1"
        try:
            cache = {"y.py": {"mtime": 1, "imports": [], "resolved_pairs": []}}
            backend = cs.save_cache_dict(self.root, cache)
            self.assertEqual(backend, "sqlite+json", backend)
            self.assertTrue(cs.json_path(self.root).is_file())
        finally:
            os.environ.pop("WIKIFIER_CACHE_JSON", None)


class TestResolveCandidatesHelper(TempProjectTestCase):
    def test_resolve_candidates_peel(self):
        self.write("m.py", "1\n")
        cli.update_maps(project_root=self.root, full=True)
        index = ic.load_mtime_index(self.root)
        meta = cs.load_meta(self.root, keys=("_candidate_list",))
        r = resolve_candidates(
            self.root, directory=None, force_full=False, index=index, meta=meta
        )
        self.assertTrue(r.get("reused") or r.get("relisted"))
        self.assertGreaterEqual(len(r.get("paths") or []), 1)


class TestEnvDirNotExcluded(TempProjectTestCase):
    def test_env_package_dir_collected(self):
        """Bare 'env' must not be a DEFAULT_EXCLUDE (rust sys/env/*.rs)."""
        self.write("sys/env/mod.rs", "pub fn x() {}\n")
        self.write("sys/env/other.rs", "pub fn y() {}\n")
        cands = collect_candidate_source_files(self.root, directory="sys")
        names = [p.name for p in cands]
        self.assertIn("mod.rs", names, names)
        self.assertIn("other.rs", names, names)


class TestCandidateReuseScopeMatrix(TempProjectTestCase):
    """Pure evaluate_candidate_reuse + MapScope filter matrix (no shell)."""

    def test_evaluate_poison_n1_empty_index(self):
        from wikifier.candidates import evaluate_candidate_reuse

        blob = {
            "fp": "fp1",
            "directory": None,
            "count": 1,
            "rels": ["a.py"],
        }
        # empty index + live 2 → reject
        self.assertIsNone(
            evaluate_candidate_reuse(
                blob,
                fingerprint="fp1",
                directory=None,
                scoped_index_keys=set(),
                live_count=2,
            )
        )
        # None index + live 2 → reject
        self.assertIsNone(
            evaluate_candidate_reuse(
                blob,
                fingerprint="fp1",
                directory=None,
                scoped_index_keys=None,
                live_count=2,
            )
        )
        # live agrees with poison count 1 but would still "reuse" wrong set —
        # caller's live_count must be real; here live=1 allows return
        got = evaluate_candidate_reuse(
            blob,
            fingerprint="fp1",
            directory=None,
            scoped_index_keys=None,
            live_count=1,
        )
        self.assertEqual(got, ["a.py"])

    def test_evaluate_same_count_different_keys(self):
        from wikifier.candidates import evaluate_candidate_reuse

        blob = {
            "fp": "fp1",
            "directory": None,
            "count": 1,
            "rels": ["b.py"],
        }
        self.assertIsNone(
            evaluate_candidate_reuse(
                blob,
                fingerprint="fp1",
                directory=None,
                scoped_index_keys={"a.py"},
                live_count=1,
            )
        )

    def test_evaluate_true_set_agreement(self):
        from wikifier.candidates import evaluate_candidate_reuse

        blob = {
            "fp": "fp1",
            "directory": None,
            "count": 2,
            "rels": ["pkg/a.py", "pkg/b.py"],
        }
        got = evaluate_candidate_reuse(
            blob,
            fingerprint="fp1",
            directory=None,
            scoped_index_keys={"pkg/a.py", "pkg/b.py"},
            live_count=2,
        )
        self.assertEqual(set(got or []), {"pkg/a.py", "pkg/b.py"})

    def test_evaluate_partial_subset_live_ok(self):
        from wikifier.candidates import evaluate_candidate_reuse

        blob = {
            "fp": "fp1",
            "directory": None,
            "count": 2,
            "rels": ["a.py", "b.py"],
        }
        got = evaluate_candidate_reuse(
            blob,
            fingerprint="fp1",
            directory=None,
            scoped_index_keys={"a.py"},
            live_count=2,
        )
        self.assertIsNotNone(got)
        self.assertEqual(len(got), 2)

    def test_evaluate_fp_mismatch(self):
        from wikifier.candidates import evaluate_candidate_reuse

        blob = {"fp": "old", "directory": None, "count": 1, "rels": ["a.py"]}
        self.assertIsNone(
            evaluate_candidate_reuse(
                blob,
                fingerprint="new",
                directory=None,
                scoped_index_keys=None,
                live_count=1,
            )
        )

    def test_filter_index_to_map_scope_narrows(self):
        from wikifier.candidates import (
            filter_index_to_map_scope,
            resolve_map_scope,
        )

        self.write("map_paths.txt", "pkg/\n")
        self.write("pkg/a.py", "1\n")
        self.write("outside/c.py", "2\n")
        scope = resolve_map_scope(self.root, None)
        self.assertFalse(scope.is_full_tree, scope)
        self.assertIn("pkg", scope.rel_prefixes)
        index = {
            "pkg/a.py": {"mtime": 1},
            "outside/c.py": {"mtime": 2},
            "pkg/b.py": {"mtime": 3},
        }
        scoped = filter_index_to_map_scope(index, scope)
        self.assertIn("pkg/a.py", scoped)
        self.assertIn("pkg/b.py", scoped)
        self.assertNotIn("outside/c.py", scoped)

    def test_full_index_with_map_paths_does_not_poison_reuse(self):
        """Leftover full-tree index keys must not force permanent re-list."""
        from wikifier.candidates import (
            evaluate_candidate_reuse,
            filter_index_to_map_scope,
            resolve_map_scope,
            try_cached_candidate_rels,
        )

        self.write("map_paths.txt", "pkg/\n")
        self.write("pkg/a.py", "1\n")
        self.write("pkg/b.py", "2\n")
        self.write("outside/c.py", "3\n")
        # Simulate post-migration index still containing outside keys
        full_index = {
            "pkg/a.py": {"mtime": 1},
            "pkg/b.py": {"mtime": 1},
            "outside/c.py": {"mtime": 1},
        }
        scope = resolve_map_scope(self.root, None)
        scoped = filter_index_to_map_scope(full_index, scope)
        self.assertEqual(set(scoped.keys()), {"pkg/a.py", "pkg/b.py"})
        fp = scope_fingerprint(self.root, None)
        blob = {
            "fp": fp,
            "directory": None,
            "count": 2,
            "rels": ["pkg/a.py", "pkg/b.py"],
        }
        # Pure: map-scoped keys + live 2 → reuse
        got = evaluate_candidate_reuse(
            blob,
            fingerprint=fp,
            directory=None,
            scoped_index_keys=set(scoped.keys()),
            live_count=2,
        )
        self.assertIsNotNone(got)
        # I/O path: try_cached must filter before set check
        meta = {"_candidate_list": blob}
        paths = try_cached_candidate_rels(
            meta, self.root, None, index=full_index
        )
        self.assertIsNotNone(paths, "full leftover index must not poison map_paths reuse")
        self.assertEqual(len(paths), 2)


class TestMapPathsMigration(TempProjectTestCase):
    def test_map_paths_migration_reuses_after_full_tree_map(self):
        """Phase0 full map n=3 → map_paths=pkg/ → warm2/3 candidates_reused."""
        self.write("pkg/a.py", "x=1\n")
        self.write("pkg/b.py", "y=2\n")
        self.write("outside/c.py", "z=3\n")
        # No map_paths yet: full tree
        r0 = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r0.get("success"), r0)
        n0 = int(r0.get("parseable_files") or 0)
        self.assertEqual(n0, 3, r0)
        # Narrow map surface
        self.write("map_paths.txt", "pkg/\n")
        # Warm after narrow: may re-list once, then reuse
        r1 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r1.get("success"), r1)
        self.assertEqual(int(r1.get("parseable_files") or 0), 2, r1)
        r2 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r2.get("success"), r2)
        r3 = cli.update_maps(project_root=self.root, full=False)
        self.assertTrue(r3.get("success"), r3)
        self.assertEqual(int(r3.get("parseable_files") or 0), 2, r3)
        self.assertTrue(
            r3.get("candidates_reused") is True,
            f"after full→map_paths migration warm must reuse; r1={r1} r2={r2} r3={r3}",
        )
        self.assertFalse(r3.get("candidates_relisted"), r3)
        # Index keys must be ⊆ pkg (pruned or filtered)
        index = ic.load_mtime_index(self.root) or {}
        outside = [k for k in index if isinstance(k, str) and k.startswith("outside")]
        self.assertEqual(
            outside,
            [],
            f"outside keys must be pruned after map_paths narrow: {list(index.keys())}",
        )


class TestPruneFileIndexOutsideScope(TempProjectTestCase):
    def test_prune_removes_outside_rows(self):
        self.write("pkg/a.py", "1\n")
        self.write("outside/c.py", "2\n")
        r = cli.update_maps(project_root=self.root, full=True)
        self.assertTrue(r.get("success"), r)
        # Manually ensure both keys present then prune
        index = ic.load_mtime_index(self.root) or {}
        self.assertGreaterEqual(len(index), 2, index)
        n = cs.prune_file_index_outside_scope(self.root, ["pkg"], is_full_tree=False)
        self.assertGreaterEqual(n, 1, "should delete outside rows")
        index2 = ic.load_mtime_index(self.root) or {}
        self.assertTrue(all(not k.startswith("outside") for k in index2), index2)
        self.assertTrue(any(k.startswith("pkg") for k in index2), index2)


if __name__ == "__main__":
    unittest.main()
