"""Parser edge-contract tests (Phase 0 of Findings/2026-06-10-Fix-Plan.md).

Python + JavaScript parsers on small temp fixtures: static / relative /
dynamic imports plus one barrel chain. Asserts the canonical per-edge
contract (raw module, relative resolution, real booleans, confidence fields).
"""

import textwrap
import unittest

from tests._base import TempProjectTestCase, find_edge


PY_A_SOURCE = textwrap.dedent("""\
    import os
    from . import b
    from .b import y
    from .sub.c import x
    import importlib
    mod = importlib.import_module("pkg.b")
""")


class TestPythonParser(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.write("pkg/__init__.py", "")
        self.write("pkg/b.py", "y = 1\n")
        self.write("pkg/sub/__init__.py", "")
        self.write("pkg/sub/c.py", "x = 2\n")
        self.a_path = self.write("pkg/a.py", PY_A_SOURCE)

        from wikifier.parsers.python import parse_python_imports
        self.edges = parse_python_imports(str(self.a_path))

    def test_absolute_stdlib_import(self):
        edge = find_edge(self.edges, raw_module="os")
        self.assertIsNotNone(edge, "import os not detected")
        self.assertIs(edge["is_relative"], False)
        self.assertEqual(edge["level"], 0)
        self.assertEqual(edge["module"], "os")
        self.assertEqual(edge["statement_type"], "import")

    def test_relative_from_dot_import(self):
        # from . import b
        edge = find_edge(self.edges, raw_module=".")
        self.assertIsNotNone(edge, "`from . import b` not detected")
        self.assertIs(edge["is_relative"], True)
        self.assertEqual(edge["level"], 1)
        self.assertIn("b", edge["imported_names"])
        self.assertEqual(edge["module"], "pkg")

    def test_relative_sibling_module_resolves_to_path(self):
        # from .b import y -> pkg/b.py on disk
        edge = find_edge(self.edges, raw_module=".b")
        self.assertIsNotNone(edge, "`from .b import y` not detected")
        self.assertIs(edge["is_relative"], True)
        self.assertEqual(edge["level"], 1)
        self.assertTrue(edge["resolved_path"], "relative import should resolve to a FS path")
        self.assertTrue(str(edge["resolved_path"]).endswith("pkg/b.py"))
        self.assertEqual(edge["resolution_confidence"], "high")

    def test_relative_nested_module_resolves_to_path(self):
        # from .sub.c import x -> pkg/sub/c.py on disk
        edge = find_edge(self.edges, raw_module=".sub.c")
        self.assertIsNotNone(edge, "`from .sub.c import x` not detected")
        self.assertIs(edge["is_relative"], True)
        self.assertEqual(edge["level"], 1)
        self.assertEqual(edge["module"], "pkg.sub.c")
        self.assertIn("x", edge["imported_names"])
        self.assertTrue(str(edge["resolved_path"]).endswith("pkg/sub/c.py"))
        self.assertEqual(edge["resolution_confidence"], "high")

    def test_dynamic_importlib_import_module_detected(self):
        dyn = [e for e in self.edges if e.get("is_dynamic")]
        self.assertTrue(dyn, "importlib.import_module call not detected as dynamic")
        edge = dyn[0]
        self.assertTrue(edge["statement_type"].startswith("dynamic_"))
        self.assertIn("pkg.b", edge["raw_module"])

    def test_confidence_fields_present_on_all_edges(self):
        self.assertTrue(self.edges)
        for edge in self.edges:
            self.assertIsInstance(edge.get("confidence_score"), float, edge.get("raw_module"))
            self.assertGreaterEqual(edge["confidence_score"], 0.0)
            self.assertLessEqual(edge["confidence_score"], 1.0)
            self.assertIsInstance(edge.get("confidence_reasons"), list)
            self.assertIsInstance(edge.get("confidence_explanation"), str)
            self.assertIn(
                edge.get("resolution_confidence"),
                ("high", "medium", "low", "unresolved"),
            )


JS_INDEX_SOURCE = textwrap.dedent("""\
    import {x} from './a.js';
    const y = require('./b');
    async function go() { const m = await import('./c.js'); }
    import {leafThing} from './barrel';
""")


class TestJavaScriptParser(TempProjectTestCase):
    def setUp(self):
        super().setUp()
        self.write("a.js", "export const x = 1;\n")
        self.write("b.js", "module.exports = {};\n")
        self.write("c.js", "export default 3;\n")
        self.write("barrel/leaf.js", "export const leafThing = 42;\n")
        self.write("barrel/index.js", "export * from './leaf.js';\n")
        self.index_path = self.write("index.js", JS_INDEX_SOURCE)

        self.reset_js_parser_state()
        from wikifier.parsers.javascript import parse_javascript_imports
        self.edges = parse_javascript_imports(str(self.index_path))

    def test_es_import_edge_found_and_resolved(self):
        edge = find_edge(self.edges, raw_module="./a.js", statement_type="es_import")
        self.assertIsNotNone(edge, "es import of ./a.js not detected")
        self.assertEqual(edge["resolved_path"], "a.js")
        self.assertTrue((self.root / edge["resolved_path"]).exists())

    def test_require_edge_found_and_resolved(self):
        edge = find_edge(self.edges, raw_module="./b", statement_type="require")
        self.assertIsNotNone(edge, "require('./b') not detected")
        self.assertEqual(edge["resolved_path"], "b.js")
        self.assertTrue((self.root / edge["resolved_path"]).exists())

    def test_dynamic_import_edge_found_and_resolved(self):
        edge = find_edge(self.edges, raw_module="./c.js", statement_type="dynamic_import")
        self.assertIsNotNone(edge, "dynamic import('./c.js') not detected")
        self.assertEqual(edge["resolved_path"], "c.js")
        self.assertTrue((self.root / edge["resolved_path"]).exists())

    def test_barrel_import_flagged_via_barrel_and_resolved(self):
        edge = find_edge(self.edges, raw_module="./barrel")
        self.assertIsNotNone(edge, "import from './barrel' not detected")
        self.assertTrue(edge.get("via_barrel"), "barrel expansion should flag via_barrel")
        self.assertEqual(edge["resolved_path"], "barrel/index.js")
        self.assertTrue((self.root / edge["resolved_path"]).exists())
        self.assertGreaterEqual(edge.get("barrel_depth") or 0, 1)

    def test_static_es_import_is_not_dynamic_and_not_via_barrel(self):
        # Currently failing — fixed by Phase 4 of Findings/2026-06-10-Fix-Plan.md
        # (W10 canonical edge representation). Today the parser marks a plain
        # `import {x} from './a.js'` as is_dynamic=True / via_barrel=True with
        # confidence "low", even though it is a static, resolved, direct-file
        # import that involves no barrel at all.
        edge = find_edge(self.edges, raw_module="./a.js", statement_type="es_import")
        self.assertIsNotNone(edge)
        self.assertFalse(edge.get("is_dynamic"), "static es_import must not be flagged dynamic")
        self.assertFalse(edge.get("via_barrel"), "direct-file import must not be flagged via_barrel")
        self.assertEqual(edge.get("resolution_confidence"), "high")


class TestBarrelLeafExplosionPolicy(TempProjectTestCase):
    """Leaf-explosion policy: name routing + reported cap.

    A named import through an `export *` barrel must emit the entry edge plus
    only the leaves that export the requested names (precision); imports with
    no usable names (side-effect/namespace/dynamic) fall back to a cap whose
    truncation is reported via barrel_leaf_selection — never silent.
    """

    LEAVES = 30

    def setUp(self):
        super().setUp()
        lines = []
        for i in range(self.LEAVES):
            self.write(f"big/leaf{i}.js", f"export const thing{i} = {i};\n")
            lines.append(f"export * from './leaf{i}.js';")
        self.write("big/index.js", "\n".join(lines) + "\n")
        self.write("named.js", "import { thing7 } from './big';\n")
        self.write("nameless.js", "import * as big from './big';\n")

    def _parse(self, rel):
        self.reset_js_parser_state()
        from wikifier.parsers.javascript import parse_javascript_imports
        return parse_javascript_imports(str(self.root / rel))

    def test_named_import_routes_to_defining_leaf(self):
        edges = self._parse("named.js")
        paths = [e.get("resolved_path") for e in edges]
        self.assertIn("big/index.js", paths, "entry-barrel edge must be kept")
        self.assertIn("big/leaf7.js", paths, "the leaf defining thing7 must be kept")
        self.assertLessEqual(
            len(edges), 4,
            f"name routing should drop non-matching leaves, got {len(edges)}: {paths}",
        )
        edge = find_edge(edges, raw_module="./big")
        self.assertIn("thing7", edge.get("imported_names") or [])

    def test_nameless_import_is_capped_with_reported_selection(self):
        import os
        old = os.environ.get("WIKIFIER_BARREL_LEAF_CAP")
        os.environ["WIKIFIER_BARREL_LEAF_CAP"] = "5"
        try:
            edges = self._parse("nameless.js")
        finally:
            if old is None:
                os.environ.pop("WIKIFIER_BARREL_LEAF_CAP", None)
            else:
                os.environ["WIKIFIER_BARREL_LEAF_CAP"] = old
        barrel_edges = [e for e in edges if e.get("via_barrel")]
        self.assertLessEqual(len(barrel_edges), 6, "cap must bound emission (entry + 5 leaves)")
        sels = [e.get("barrel_leaf_selection") for e in edges if e.get("barrel_leaf_selection")]
        self.assertTrue(sels, "truncation must be reported via barrel_leaf_selection")
        self.assertTrue(sels[0].get("truncated"))
        self.assertEqual(sels[0].get("leaves_emitted"), 5)
        self.assertEqual(sels[0].get("leaves_total"), self.LEAVES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
