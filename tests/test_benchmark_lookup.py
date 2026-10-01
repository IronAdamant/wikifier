"""The lookup benchmark harness: reference resolver and end-to-end run on a tiny project."""

from __future__ import annotations

import importlib.util
import unittest

from tests._base import REPO_ROOT, TempProjectTestCase

_spec = importlib.util.spec_from_file_location("benchmark_lookup", REPO_ROOT / "scripts" / "benchmark_lookup.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


class TestBenchmarkLookup(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.write("src/shop/__init__.py", "")
        self.write("src/shop/models.py", "class Item: pass\n")
        self.write("src/shop/views.py", "from .models import Item\nfrom shop import utils\n")
        self.write("src/shop/utils.py", "import json\n")
        self.write("src/shop/api/__init__.py", "")
        self.write("src/shop/api/routes.py", "from ..views import Item\n\ndef f():\n    from shop.models import Item\n")
        self.write("src/other/models.py", "x = 1\n")  # same stem: a grep false positive

    def test_reference_resolves_relative_absolute_lazy_and_src_layout(self):
        files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*.py"))
        graph, failures = bench.build_reference_graph(self.root, files)
        self.assertEqual(failures, 0)
        self.assertEqual(graph["src/shop/views.py"], {"src/shop/models.py", "src/shop/utils.py", "src/shop/__init__.py"})
        # __init__ targets are recorded but excluded when scoring
        self.assertEqual(bench._not_init(graph["src/shop/api/routes.py"]), {"src/shop/views.py", "src/shop/models.py"})

    def test_end_to_end_scores_wikifier_against_reference(self):
        res = bench.run_benchmark(self.root, samples=4, seed=1)
        self.assertEqual(res["graph_accuracy"]["precision"], 1.0)
        self.assertEqual(res["graph_accuracy"]["recall"], 1.0)
        t1 = res["summary"]["t1_importers"]
        self.assertEqual(t1["wikifier"]["exact_answers"], res["samples"])
        self.assertIn("| T1 importers |", bench.render_markdown([res]))
        # The original project is never written to.
        self.assertFalse((self.root / ".wikifier_staging").exists())


if __name__ == "__main__":
    unittest.main()
