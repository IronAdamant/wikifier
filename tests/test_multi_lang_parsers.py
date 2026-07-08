"""Multi-language parser smoke tests (Rust, Go, C/C++, C#)."""

import unittest
from pathlib import Path

from tests._base import TempProjectTestCase

from wikifier.parsers import rust, go_lang, c_cpp, csharp, java
from wikifier.cli import run_full_update, check_changes
import importlib
import os


class TestRustParser(TempProjectTestCase):
    def test_use_and_mod(self):
        self.write("lib.rs", "mod foo;\nuse crate::foo::Bar;\nuse std::io;\n")
        self.write("foo.rs", "pub struct Bar;\n")
        edges = rust.parse_rust_imports(str(self.root / "lib.rs"))
        kinds = {e.get("statement_type") for e in edges}
        self.assertIn("mod", kinds)
        self.assertIn("use", kinds)
        mod_e = next(e for e in edges if e.get("statement_type") == "mod")
        self.assertTrue(mod_e.get("resolved_path") and mod_e["resolved_path"].endswith("foo.rs"))


class TestGoParser(TempProjectTestCase):
    def test_import_block(self):
        self.write("main.go", 'package main\nimport (\n\t"fmt"\n\t"os"\n)\n')
        edges = go_lang.parse_go_imports(str(self.root / "main.go"))
        mods = {e["raw_module"] for e in edges}
        self.assertIn("fmt", mods)
        self.assertIn("os", mods)


class TestCParser(TempProjectTestCase):
    def test_local_and_system_include(self):
        self.write("a.c", '#include "b.h"\n#include <stdio.h>\n')
        self.write("b.h", "int x;\n")
        edges = c_cpp.parse_c_cpp_imports(str(self.root / "a.c"))
        self.assertGreaterEqual(len(edges), 2)
        local = next(e for e in edges if e["raw_module"] == "b.h")
        self.assertTrue(local.get("resolved_path"))
        sys_e = next(e for e in edges if e["raw_module"] == "stdio.h")
        self.assertEqual((sys_e.get("diagnostic") or {}).get("category"), "external_or_bare")


class TestCsharpParser(TempProjectTestCase):
    def test_using(self):
        self.write("A.cs", "using System;\nusing System.IO;\nusing MyApp.Core;\n")
        edges = csharp.parse_csharp_imports(str(self.root / "A.cs"))
        mods = {e["raw_module"] for e in edges}
        self.assertIn("System", mods)
        self.assertIn("MyApp.Core", mods)


class TestJavaParser(TempProjectTestCase):
    def test_import(self):
        self.write("A.java", "import java.util.List;\nimport com.foo.Bar;\n")
        edges = java.parse_java_imports(str(self.root / "A.java"))
        mods = {e["raw_module"] for e in edges}
        self.assertIn("java.util.List", mods)
        self.assertIn("com.foo.Bar", mods)


class TestPipelineMultiLang(TempProjectTestCase):
    def test_run_full_update_parses_all_langs(self):
        self.write("a.py", "import os\n")
        self.write("b.rs", "mod x;\n")
        self.write("x.rs", "pub fn f() {}\n")
        self.write("c.go", 'package p\nimport "fmt"\n')
        self.write("d.c", '#include "e.h"\n')
        self.write("e.h", "int y;\n")
        self.write("f.cs", "using System;\n")
        self.write("G.java", "import java.io.File;\n")
        res = run_full_update(root=self.root, force_full=True, verbose=False)
        self.assertTrue(res.get("success"))
        self.assertGreaterEqual(res.get("files_parsed", 0), 5)
        self.assertIn("languages_parsed", res)
        self.assertGreaterEqual(res.get("health_stubs_seeded", 0), 1)
        health_mod = importlib.import_module("wikifier.health")
        entries = health_mod.load_health(self.root).get("entries") or {}
        self.assertTrue(any(k.endswith((".py", ".rs", ".java", ".cs", ".go", ".c")) for k in entries))

    def test_check_changes_cap_env(self):
        self.write("monitored_paths.txt", ".\n")
        for i in range(5):
            self.write(f"f{i}.py", f"x={i}\n")
        run_full_update(root=self.root, force_full=True, verbose=False)
        import time
        time.sleep(0.05)
        for i in range(5):
            (self.root / f"f{i}.py").write_text(f"x={i + 1}\n")
        os.environ["WIKIFIER_CHECK_CHANGES_MAX"] = "2"
        try:
            r = check_changes(project_root=self.root)
            self.assertTrue(r.get("success"))
            self.assertLessEqual(r.get("changes_detected", 0), 2)
            self.assertTrue(r.get("dirty_truncated") or (r.get("dirty_total") or 0) <= 2)
        finally:
            os.environ.pop("WIKIFIER_CHECK_CHANGES_MAX", None)


if __name__ == "__main__":
    unittest.main()
