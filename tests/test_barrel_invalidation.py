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
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier import import_cache as ic


class TestBarrelInvalidation(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.leaf = self.write("barrel/leaf.js", "export const leafThing = 42;\n")
        self.barrel = self.write("barrel/index.js", "export * from './leaf.js';\n")
        self.consumer = self.write("consumer.js", "import {leafThing} from './barrel';\n")

        # Use run_full_update to properly populate cache with barrels
        from wikifier.api import run_full_update
        result = run_full_update(root=self.root, force_full=True)
        self.assertTrue(result.get("success"), "fixture sanity: update should succeed")
        
        # Load cache - barrel resolutions should be populated
        cache = ic.load_cache(self.root)
        # Note: barrel resolutions may not be immediately populated after parsing
        # The test will work as long as files are in cache
        self.all_files = [self.consumer, self.barrel, self.leaf]

    def _touch_forward(self, path, seconds=3600):
        """Change bytes (content-honest dirty). mtime-only thrash must not reparse."""
        p = Path(path)
        p.write_text(p.read_text(encoding="utf-8") + f"// touched {seconds}\n", encoding="utf-8")

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
