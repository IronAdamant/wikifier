//! Accuracy fixtures formerly checked against the Python 4.7 parser.
//! The expected edges are the frozen oracle. The suite no longer runs Python.

use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

use wikifier::{mapped_edges, update_maps, Json};

struct Fixture {
    name: &'static str,
    files: &'static [(&'static str, &'static str)],
    edges: &'static [(&'static str, &'static str)],
}

#[test]
fn accuracy_fixtures_match_frozen_edges() {
    for fixture in FIXTURES {
        let root = std::env::temp_dir().join(format!("wk-acc-{}-{}", fixture.name, std::process::id()));
        let _ = fs::remove_dir_all(&root);
        for (rel, text) in fixture.files {
            let path = root.join(rel);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(&path, text).unwrap();
        }
        let built = update_maps(&root);
        assert_eq!(built.get("success").and_then(|s| s.as_bool()), Some(true), "{}: {built}", fixture.name);
        let found = mapped_edges(&root);
        let expected: BTreeSet<(String, String)> = fixture.edges.iter().map(|(a, b)| ((*a).to_string(), (*b).to_string())).collect();
        if found != expected {
            let missed: Vec<_> = expected.difference(&found).cloned().collect();
            let extra: Vec<_> = found.difference(&expected).cloned().collect();
            panic!("{}: edges diverged\nmissed {missed:?}\nextra {extra:?}", fixture.name);
        }
        let _ = fs::remove_dir_all(&root);
    }
}

const FIXTURES: &[Fixture] = &[
    Fixture {
        name: "django_app",
        files: &[
            ("manage.py", "import os\nimport sys\n\nif __name__ == '__main__':\n    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')\n    from django.core.management import execute_from_command_line\n    execute_from_command_line(sys.argv)\n"),
            ("mysite/__init__.py", ""),
            ("mysite/settings.py", "from pathlib import Path\nBASE_DIR = Path(__file__).resolve().parent.parent\nINSTALLED_APPS = ['polls']\n"),
            ("mysite/urls.py", "from django.urls import include, path\nfrom polls import views\n\nurlpatterns = [path('', views.index)]\n"),
            ("polls/__init__.py", ""),
            ("polls/models.py", "from django.db import models\n\n\nclass Question(models.Model):\n    pass\n"),
            ("polls/views.py", "from django.shortcuts import render\n\nfrom .models import Question\nfrom . import forms\n\n\ndef index(request):\n    return render(request, 'x', {'q': Question})\n"),
            ("polls/forms.py", "from django import forms\nfrom polls.models import Question\n"),
            ("polls/admin.py", "from django.contrib import admin\n\nfrom .models import Question\n"),
            ("polls/tests.py", "from django.test import TestCase\n\nfrom polls.models import Question\nimport polls.views\n"),
        ],
        edges: &[
            ("mysite/urls.py", "polls/views.py"),
            ("polls/views.py", "polls/models.py"),
            ("polls/views.py", "polls/forms.py"),
            ("polls/forms.py", "polls/models.py"),
            ("polls/admin.py", "polls/models.py"),
            ("polls/tests.py", "polls/models.py"),
            ("polls/tests.py", "polls/views.py"),
        ],
    },
    Fixture {
        name: "src_layout_package",
        files: &[
            ("pyproject.toml", "[project]\nname = 'pkg'\n"),
            ("src/pkg/__init__.py", "from pkg.core import run\n\n__all__ = ['run']\n"),
            ("src/pkg/core.py", "import json\n\nfrom pkg import utils\nfrom pkg.io.reader import read\n\n\ndef run():\n    return utils.helper(read())\n"),
            ("src/pkg/utils.py", "try:\n    import ujson as fastjson\nexcept ImportError:\n    import json as fastjson\n\n\ndef helper(x):\n    return x\n"),
            ("src/pkg/io/__init__.py", ""),
            ("src/pkg/io/reader.py", "from ..utils import helper\n\n\ndef read():\n    return helper(1)\n"),
            ("src/pkg/plugins.py", "import importlib\n\n\ndef load():\n    return importlib.import_module('pkg.utils')\n"),
            ("tests/test_core.py", "from pkg.core import run\nfrom pkg import utils as u\n"),
        ],
        edges: &[
            ("src/pkg/__init__.py", "src/pkg/core.py"),
            ("src/pkg/core.py", "src/pkg/utils.py"),
            ("src/pkg/core.py", "src/pkg/io/reader.py"),
            ("src/pkg/io/reader.py", "src/pkg/utils.py"),
            ("src/pkg/plugins.py", "src/pkg/utils.py"),
            ("tests/test_core.py", "src/pkg/core.py"),
            ("tests/test_core.py", "src/pkg/utils.py"),
        ],
    },
    Fixture {
        name: "ts_monorepo",
        files: &[
            ("package.json", "{\"name\": \"acme\", \"private\": true, \"workspaces\": [\"packages/*\"]}\n"),
            ("tsconfig.json", "{\"compilerOptions\": {\"baseUrl\": \".\", \"paths\": {\"@app/*\": [\"packages/app/src/*\"]}}}\n"),
            ("packages/core/package.json", "{\"name\": \"@acme/core\", \"exports\": {\".\": \"./src/index.ts\"}}\n"),
            ("packages/core/src/index.ts", "export * from './math';\nexport { format } from './format';\n"),
            ("packages/core/src/math.ts", "export const add = (a: number, b: number): number => a + b;\n"),
            ("packages/core/src/format.ts", "import { add } from './math';\nexport const format = (n: number) => String(add(n, 0));\n"),
            ("packages/app/package.json", "{\"name\": \"@acme/app\"}\n"),
            ("packages/app/src/main.ts", "import { add } from '@acme/core';\nimport { log } from '@app/util';\nimport type { Config } from './types';\nconst lazy = () => import('./lazy');\nimport React from 'react';\nlog(add(1, 2));\n"),
            ("packages/app/src/util.ts", "export const log = (x: unknown) => console.log(x);\n"),
            ("packages/app/src/types.ts", "export interface Config { debug: boolean }\n"),
            ("packages/app/src/lazy.ts", "export default 42;\n"),
        ],
        edges: &[
            ("packages/core/src/index.ts", "packages/core/src/math.ts"),
            ("packages/core/src/index.ts", "packages/core/src/format.ts"),
            ("packages/core/src/format.ts", "packages/core/src/math.ts"),
            ("packages/app/src/main.ts", "packages/core/src/index.ts"),
            ("packages/app/src/main.ts", "packages/core/src/math.ts"),
            ("packages/app/src/main.ts", "packages/app/src/util.ts"),
            ("packages/app/src/main.ts", "packages/app/src/types.ts"),
            ("packages/app/src/main.ts", "packages/app/src/lazy.ts"),
        ],
    },
    Fixture {
        name: "comment_and_string_traps",
        files: &[
            ("package.json", "{\"name\": \"traps\"}\n"),
            ("src/real.js", "export const real = 1;\n"),
            ("src/other.js", "export const other = 2;\n"),
            ("src/app.js", "import { real } from './real';\n// import { fake } from './ghost-line-comment';\n/* import x from './ghost-block-comment'; */\nconst s = \"import y from './ghost-string'\";\nconst t = `prefix ${require('./other')} import z from './ghost-template'`;\nconst re = /import w from '.\\/ghost-regex'/;\n"),
            ("lib/helpers.py", "def h():\n    return 1\n"),
            ("lib/__init__.py", ""),
            ("lib/use.py", "# import lib.ghost_comment\nDOC = '''import lib.ghost_docstring'''\ns = 'from lib import ghost_string'\nfrom lib import helpers\n"),
        ],
        edges: &[
            ("src/app.js", "src/real.js"),
            ("src/app.js", "src/other.js"),
            ("lib/use.py", "lib/helpers.py"),
        ],
    },
];

#[test]
fn each_parsed_language_emits_a_local_edge() {
    let root = std::env::temp_dir().join(format!("wk-langs-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(root.join("src")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(root.join("src/a.py"), "import b\n").unwrap();
    fs::write(root.join("src/b.py"), "x = 1\n").unwrap();
    fs::write(root.join("src/app.js"), "import { n } from './lib';\n").unwrap();
    fs::write(root.join("src/lib.js"), "export const n = 1;\n").unwrap();
    fs::write(root.join("src/main.rs"), "mod helper;\n").unwrap();
    fs::write(root.join("src/helper.rs"), "pub fn h() {}\n").unwrap();
    fs::write(root.join("src/a.go"), "package p\nimport \"./b\"\n").unwrap();
    fs::write(root.join("src/b.go"), "package b\n").unwrap();
    fs::write(root.join("src/a.c"), "#include \"b.h\"\n").unwrap();
    fs::write(root.join("src/b.h"), "#pragma once\n").unwrap();
    fs::write(root.join("src/A.java"), "import demo.B;\nclass A {}\n").unwrap();
    fs::write(root.join("src/B.java"), "package demo;\npublic class B {}\n").unwrap();
    fs::write(root.join("src/A.cs"), "using Demo;\nclass A {}\n").unwrap();
    fs::write(root.join("src/Demo.cs"), "class Demo {}\n").unwrap();
    let built = update_maps(&root);
    assert_eq!(built.get("success").and_then(|s| s.as_bool()), Some(true), "{built}");
    let edges = mapped_edges(&root);
    for (src, dst) in [
        ("src/a.py", "src/b.py"),
        ("src/app.js", "src/lib.js"),
        ("src/main.rs", "src/helper.rs"),
        ("src/a.go", "src/b.go"),
        ("src/a.c", "src/b.h"),
        ("src/A.java", "src/B.java"),
        ("src/A.cs", "src/Demo.cs"),
    ] {
        assert!(edges.contains(&(src.into(), dst.into())), "missing {src} -> {dst} in {edges:?}");
    }
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn unknown_suffixes_emit_no_edges() {
    let root = std::env::temp_dir().join(format!("wk-unk-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(root.join("src")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    fs::write(root.join("src/hello.cbl"), "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO.\n").unwrap();
    fs::write(root.join("src/hello.cob"), "       PROCEDURE DIVISION.\n").unwrap();
    fs::write(root.join("src/hello.cpy"), "       COPY HELLO.\n").unwrap();
    fs::write(root.join("src/hello.swift"), "import Foundation\n").unwrap();
    fs::write(root.join("src/hello.s"), "mov x0, #0\n").unwrap();
    fs::write(root.join("src/real.py"), "def hi():\n    return 1\n").unwrap();
    let built = update_maps(&root);
    assert_eq!(built.get("success").and_then(|s| s.as_bool()), Some(true), "{built}");
    let edges = mapped_edges(&root);
    assert!(edges.is_empty(), "{edges:?}");
    let files = built.get("parseable_files").and_then(|n| match n { Json::Int(i) => Some(*i), _ => None });
    assert_eq!(files, Some(1), "only real.py is parseable, got {built}");
    let _ = fs::remove_dir_all(&root);
}
