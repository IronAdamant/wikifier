"""Barrel churn invalidation tests — the E1 repro (Phase 0 of
Findings/2026-06-10-Fix-Plan.md).

Fixture: consumer.js imports './barrel'; barrel/index.js re-exports
'./leaf.js'. Parsing the consumer populates the BarrelResolutionCache
(_barrel_resolutions / _barrel_file_index in import_cache.json). Touching a
file in the chain forward must mark consumer.js stale so it gets re-parsed.
"""

import os
import time
import unittest

from tests._base import TempProjectTestCase

from wikifier import import_cache as ic


class TestBarrelInvalidation(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.leaf = self.write("barrel/leaf.js", "export const leafThing = 42;\n")
        self.barrel = self.write("barrel/index.js", "export * from './leaf.js';\n")
        self.consumer = self.write("consumer.js", "import {leafThing} from './barrel';\n")

        # Parse the consumer: this resolves './barrel' through BREE and
        # persists the barrel chain + reverse index into the import cache.
        self.reset_js_parser_state()
        from wikifier.parsers.javascript import parse_javascript_imports
        edges = parse_javascript_imports(str(self.consumer))
        self.assertTrue(edges, "fixture sanity: consumer.js should produce edges")

        # Persist canonical per-file entries with current mtimes so that
        # compute_files_needing_reparse has a clean baseline (nothing dirty).
        cache = ic.load_cache(self.root)
        self.assertTrue(ic.get_barrel_resolutions(cache),
                        "fixture sanity: parsing should populate _barrel_resolutions")
        for rel in ("consumer.js", "barrel/index.js", "barrel/leaf.js"):
            ic.update_file_data(
                cache, rel,
                mtime=ic.get_mtime(self.root / rel),
                imports=[],
                resolved_pairs=[],
            )
        ic.save_cache(self.root, cache)
        self.all_files = [self.consumer, self.barrel, self.leaf]

    def _touch_forward(self, path, seconds=3600):
        ts = time.time() + seconds
        os.utime(path, (ts, ts))

    def test_baseline_nothing_dirty(self):
        need = ic.compute_files_needing_reparse(self.root, self.all_files)
        self.assertEqual(need, [], "freshly persisted project must report no dirty files")

    def test_touched_leaf_is_itself_in_reparse_set(self):
        self._touch_forward(self.leaf)
        need = ic.compute_files_needing_reparse(self.root, self.all_files)
        rels = {str(p.relative_to(self.root)) for p in need}
        self.assertIn("barrel/leaf.js", rels)

    def test_entry_barrel_change_invalidates_consumer(self):
        # The entry barrel (barrel/index.js) is in the BRC reverse index, so
        # the fast delta path must return its registered importer.
        self._touch_forward(self.barrel)
        cache = ic.load_cache(self.root)
        stale = ic.invalidate_stale_barrel_entries(
            cache, self.root, changed_files=["barrel/index.js"]
        )
        self.assertIn("consumer.js", stale)

    def test_leaf_change_invalidates_consumer(self):
        # Currently failing — fixed by Phase 4 of Findings/2026-06-10-Fix-Plan.md
        # (E1: the BRC reverse index / mtimes_snapshot never records the
        # re-exported leaf of the chain — mtimes_snapshot is persisted empty —
        # so a change to a mid-chain/leaf file returns no affected importers).
        #
        # Desired contract: editing barrel/leaf.js (re-exported through
        # barrel/index.js) must mark consumer.js stale for re-parse.
        self._touch_forward(self.leaf)  # only the leaf changes; barrel/index.js untouched
        cache = ic.load_cache(self.root)

        stale = ic.invalidate_stale_barrel_entries(
            cache, self.root, changed_files=["barrel/leaf.js"]
        )
        need = ic.compute_files_needing_reparse(self.root, self.all_files)
        reparse_rels = {str(p.relative_to(self.root)) for p in need}
        affected = set(stale) | reparse_rels

        self.assertIn("consumer.js", affected,
                      "consumer.js must be re-parsed when a leaf of its barrel chain changes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
