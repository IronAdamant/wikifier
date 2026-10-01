"""Small real-world project layouts with their true internal dependency edges.

Each fixture maps project-relative paths to file contents, plus the exact set
of internal (src, dst) edges a correct parser must report. Used by
tests/test_parser_accuracy.py and scripts/parser_accuracy.py (precision/recall
report to track per release).
"""

DJANGO_APP = {
    "files": {
        "manage.py": "import os\nimport sys\n\nif __name__ == '__main__':\n    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')\n    from django.core.management import execute_from_command_line\n    execute_from_command_line(sys.argv)\n",
        "mysite/__init__.py": "",
        "mysite/settings.py": "from pathlib import Path\nBASE_DIR = Path(__file__).resolve().parent.parent\nINSTALLED_APPS = ['polls']\n",
        "mysite/urls.py": "from django.urls import include, path\nfrom polls import views\n\nurlpatterns = [path('', views.index)]\n",
        "polls/__init__.py": "",
        "polls/models.py": "from django.db import models\n\n\nclass Question(models.Model):\n    pass\n",
        "polls/views.py": "from django.shortcuts import render\n\nfrom .models import Question\nfrom . import forms\n\n\ndef index(request):\n    return render(request, 'x', {'q': Question})\n",
        "polls/forms.py": "from django import forms\nfrom polls.models import Question\n",
        "polls/admin.py": "from django.contrib import admin\n\nfrom .models import Question\n",
        "polls/tests.py": "from django.test import TestCase\n\nfrom polls.models import Question\nimport polls.views\n",
    },
    "edges": {
        ("mysite/urls.py", "polls/views.py"),
        ("polls/views.py", "polls/models.py"),
        ("polls/views.py", "polls/forms.py"),
        ("polls/forms.py", "polls/models.py"),
        ("polls/admin.py", "polls/models.py"),
        ("polls/tests.py", "polls/models.py"),
        ("polls/tests.py", "polls/views.py"),
    },
}

SRC_LAYOUT_PACKAGE = {
    "files": {
        "pyproject.toml": "[project]\nname = 'pkg'\n",
        "src/pkg/__init__.py": "from pkg.core import run\n\n__all__ = ['run']\n",
        "src/pkg/core.py": "import json\n\nfrom pkg import utils\nfrom pkg.io.reader import read\n\n\ndef run():\n    return utils.helper(read())\n",
        "src/pkg/utils.py": "try:\n    import ujson as fastjson\nexcept ImportError:\n    import json as fastjson\n\n\ndef helper(x):\n    return x\n",
        "src/pkg/io/__init__.py": "",
        "src/pkg/io/reader.py": "from ..utils import helper\n\n\ndef read():\n    return helper(1)\n",
        "src/pkg/plugins.py": "import importlib\n\n\ndef load():\n    return importlib.import_module('pkg.utils')\n",
        "tests/test_core.py": "from pkg.core import run\nfrom pkg import utils as u\n",
    },
    "edges": {
        ("src/pkg/__init__.py", "src/pkg/core.py"),
        ("src/pkg/core.py", "src/pkg/utils.py"),
        ("src/pkg/core.py", "src/pkg/io/reader.py"),
        ("src/pkg/io/reader.py", "src/pkg/utils.py"),
        ("src/pkg/plugins.py", "src/pkg/utils.py"),
        ("tests/test_core.py", "src/pkg/core.py"),
        ("tests/test_core.py", "src/pkg/utils.py"),
    },
}

TS_MONOREPO = {
    "files": {
        "package.json": '{"name": "acme", "private": true, "workspaces": ["packages/*"]}\n',
        "tsconfig.json": '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["packages/app/src/*"]}}}\n',
        "packages/core/package.json": '{"name": "@acme/core", "exports": {".": "./src/index.ts"}}\n',
        "packages/core/src/index.ts": "export * from './math';\nexport { format } from './format';\n",
        "packages/core/src/math.ts": "export const add = (a: number, b: number): number => a + b;\n",
        "packages/core/src/format.ts": "import { add } from './math';\nexport const format = (n: number) => String(add(n, 0));\n",
        "packages/app/package.json": '{"name": "@acme/app"}\n',
        "packages/app/src/main.ts": (
            "import { add } from '@acme/core';\n"
            "import { log } from '@app/util';\n"
            "import type { Config } from './types';\n"
            "const lazy = () => import('./lazy');\n"
            "import React from 'react';\n"
            "log(add(1, 2));\n"
        ),
        "packages/app/src/util.ts": "export const log = (x: unknown) => console.log(x);\n",
        "packages/app/src/types.ts": "export interface Config { debug: boolean }\n",
        "packages/app/src/lazy.ts": "export default 42;\n",
    },
    "edges": {
        ("packages/core/src/index.ts", "packages/core/src/math.ts"),
        ("packages/core/src/index.ts", "packages/core/src/format.ts"),
        ("packages/core/src/format.ts", "packages/core/src/math.ts"),
        ("packages/app/src/main.ts", "packages/core/src/index.ts"),
        ("packages/app/src/main.ts", "packages/core/src/math.ts"),
        ("packages/app/src/main.ts", "packages/app/src/util.ts"),
        ("packages/app/src/main.ts", "packages/app/src/types.ts"),
        ("packages/app/src/main.ts", "packages/app/src/lazy.ts"),
    },
}

COMMENT_AND_STRING_TRAPS = {
    "files": {
        "package.json": '{"name": "traps"}\n',
        "src/real.js": "export const real = 1;\n",
        "src/other.js": "export const other = 2;\n",
        "src/app.js": (
            "import { real } from './real';\n"
            "// import { fake } from './ghost-line-comment';\n"
            "/* import x from './ghost-block-comment'; */\n"
            "const s = \"import y from './ghost-string'\";\n"
            "const t = `prefix ${require('./other')} import z from './ghost-template'`;\n"
            "const re = /import w from '.\\/ghost-regex'/;\n"
        ),
        "lib/helpers.py": "def h():\n    return 1\n",
        "lib/__init__.py": "",
        "lib/use.py": (
            "# import lib.ghost_comment\n"
            "DOC = '''import lib.ghost_docstring'''\n"
            "s = 'from lib import ghost_string'\n"
            "from lib import helpers\n"
        ),
    },
    "edges": {
        ("src/app.js", "src/real.js"),
        ("src/app.js", "src/other.js"),
        ("lib/use.py", "lib/helpers.py"),
    },
}

FIXTURES = {
    "django_app": DJANGO_APP,
    "src_layout_package": SRC_LAYOUT_PACKAGE,
    "ts_monorepo": TS_MONOREPO,
    "comment_and_string_traps": COMMENT_AND_STRING_TRAPS,
}


def materialize(root, fixture):
    """Write a fixture's files under ``root`` (a pathlib.Path)."""
    for rel, text in fixture["files"].items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def measure(root, fixture):
    """Run update-maps on a materialized fixture; return precision/recall details."""
    import os

    from wikifier import import_cache as ic
    from wikifier.api import run_full_update

    os.environ["WIKIFIER_PROJECT_ROOT"] = str(root)
    result = run_full_update(root=root, force_full=True)
    if not result.get("success"):
        raise AssertionError(f"update-maps failed: {result.get('error')}")
    cache = ic.load_cache(root)
    found = set()
    for src, entry in cache.items():
        if src.startswith("_") or not isinstance(entry, dict):
            continue
        for pair in entry.get("resolved_pairs") or []:
            if pair.get("resolved") and pair["resolved"] != src:
                found.add((src, pair["resolved"]))
    expected = set(fixture["edges"])
    hit = found & expected
    return {
        "precision": len(hit) / len(found) if found else 1.0,
        "recall": len(hit) / len(expected) if expected else 1.0,
        "false_positives": sorted(found - expected),
        "missed": sorted(expected - found),
    }
