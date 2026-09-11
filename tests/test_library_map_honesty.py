"""library.md must name only files that exist on disk.

Drives the shipped generator and the committed dogfood artifact — not mocks.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests._base import REPO_ROOT, TempProjectTestCase
from wikifier.library import generate_library_md

# 4.6.10 leftovers that must not reappear in the committed map.
GONE_PATHS = (
    "wikifier/mcp/tools/intel.py",
    "wikifier/mcp/tools/status.py",
    "wikifier/mcp/tools/workflow.py",
    "wikifier/parsers/javascript/_parser.py",
    "wikifier/parsers/javascript/__init__.py",
    "wikifier/health.py",
    "wikifier/mcp/server_backup.py",
    "wikifier/parsers/bree.py",
)

GONE_MERMAID_IDS = (
    "wikifier_mcp_tools_intel_py",
    "wikifier_mcp_tools_status_py",
    "wikifier_mcp_tools_workflow_py",
    "wikifier_parsers_javascript__parser_py",
    "wikifier_health_py",
    "wikifier_mcp_server_backup_py",
    "wikifier_parsers_bree_py",
)

# Project-relative source paths as they appear in tables / reverse-deps / prose.
_REL_PATH_RE = re.compile(
    r"(?:`)?((?:wikifier|tests|skills|Findings|docs|\.github)"
    r"/[A-Za-z0-9_./+-]+\.[A-Za-z0-9.]+)"
)


def _parse_file_tree_paths(text: str):
    """Reconstruct project-relative paths from the File Tree fence."""
    m = re.search(r"## File Tree.*?```text\n(.*?)```", text, re.S)
    if not m:
        return []
    paths = []
    stack = []  # (depth, dir_name)
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith("…"):
            continue
        if re.match(r"^[^│├└].*/\s+\(\d+ files\)\s*$", line):
            continue
        mm = re.match(r"^([ │]*)(?:├── |└── )(.+)$", line)
        if not mm:
            continue
        prefix, rest = mm.groups()
        depth = len(prefix) // 4
        name = rest.split(" — ", 1)[0].strip()
        if name.startswith("…"):
            continue
        name = re.sub(r"\s+\(\d+ files\)\s*$", "", name)
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if name.endswith("/"):
            stack.append((depth, name.rstrip("/")))
            continue
        parts = [d[1] for d in stack] + [name]
        paths.append("/".join(parts))
    return paths


def _named_rel_paths(text: str):
    found = set(_parse_file_tree_paths(text))
    for m in _REL_PATH_RE.finditer(text):
        found.add(m.group(1).rstrip("`"))
    return sorted(found)


class TestGenerateLibraryOmitsMissingFiles(TempProjectTestCase):
    def test_generate_library_md_omits_missing_cache_keys(self):
        self.write("pkg/live.py", "import os\n")
        cache = {
            "pkg/live.py": {
                "mtime": 1,
                "resolved_pairs": [{
                    "raw": "os",
                    "resolved": "",
                    "confidence": "medium",
                }],
            },
            "pkg/gone.py": {
                "mtime": 1,
                "resolved_pairs": [{
                    "raw": "./helper",
                    "resolved": "pkg/helper.py",
                    "confidence": "high",
                }],
            },
            "_reverse_dependencies": {
                "pkg/helper.py": ["pkg/gone.py", "pkg/live.py"],
                "pkg/live.py": ["pkg/gone.py"],
            },
        }
        md = generate_library_md(self.root, cache)
        self.assertIn("live.py", md)
        self.assertNotIn("gone.py", md)
        self.assertNotIn("helper.py", md)
        self.assertNotIn("pkg/gone.py", md)
        self.assertNotIn("pkg/helper.py", md)

    def test_file_tree_prefers_wiki_not_health_reason(self):
        self.write("pkg/mod.py", "x = 1\n")
        self.write(
            "pkg/mod.py.wiki.md",
            "# pkg/mod.py\n\n## Purpose\n\nImport parser helper.\n",
        )
        health = {
            "entries": {
                "pkg/mod.py": {
                    "status": "🟢 Green",
                    "reason": "4.6.13 plan aligned",
                }
            }
        }
        (self.root / "file_health.json").write_text(
            json.dumps(health), encoding="utf-8"
        )
        cache = {"pkg/mod.py": {"mtime": 1, "resolved_pairs": []}}
        md = generate_library_md(self.root, cache)
        self.assertIn("Import parser helper", md)
        self.assertNotIn("plan aligned", md)

    def test_wiki_role_colon_inside_bold(self):
        self.write("pkg/mod.py", "x = 1\n")
        self.write(
            "pkg/mod.py.wiki.md",
            "# pkg/mod.py\n\n**Role:** Gap-closure regressions.\n",
        )
        md = generate_library_md(
            self.root, {"pkg/mod.py": {"mtime": 1, "resolved_pairs": []}}
        )
        self.assertIn("Gap-closure regressions.", md)
        self.assertNotIn("Role:**", md)


class TestCommittedLibraryMdMatchesTree(unittest.TestCase):
    def test_library_md_paths_exist_on_disk(self):
        lib = REPO_ROOT / "library.md"
        self.assertTrue(lib.is_file(), "committed library.md missing")
        text = lib.read_text(encoding="utf-8")
        missing = []
        for rel in _named_rel_paths(text):
            if not (REPO_ROOT / rel).is_file():
                missing.append(rel)
        self.assertEqual(
            missing,
            [],
            "library.md names paths that are not files on disk: {0}".format(
                missing[:20]
            ),
        )

    def test_library_md_omits_deleted_4_6_10_leftovers(self):
        text = (REPO_ROOT / "library.md").read_text(encoding="utf-8")
        present = [p for p in GONE_PATHS if p in text]
        self.assertEqual(present, [], present)
        ids = [i for i in GONE_MERMAID_IDS if i in text]
        self.assertEqual(ids, [], ids)


class TestBootstrapCacheBackendHonesty(TempProjectTestCase):
    def test_empty_sqlite_is_not_cache_backend_none(self):
        from wikifier.agent_loop import session_bootstrap
        from wikifier import cache_store as cs

        boot = session_bootstrap(project_root=self.root)
        self.assertTrue(boot.get("success"), boot)
        self.assertIn("cache_empty", boot)
        self.assertIn("cache_files_indexed", boot)
        if cs.has_sqlite(self.root) or cs.json_path(self.root).is_file():
            self.assertNotEqual(
                boot.get("cache_backend"),
                "none",
                "empty sqlite/json store must not report cache_backend=none",
            )
        if boot.get("cache_backend") == "none":
            self.assertTrue(boot.get("cache_empty"))
            self.assertEqual(boot.get("cache_files_indexed"), 0)


if __name__ == "__main__":
    unittest.main()
