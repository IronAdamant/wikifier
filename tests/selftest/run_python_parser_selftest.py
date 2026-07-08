"""Extracted self-test harness from wikifier/parsers/python.py (G12 agent navigability).

Run: python3 tests/selftest/run_python_parser_selftest.py
Or:  python3 -m unittest tests.test_selftest_wrappers
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from wikifier.parsers.python import (
    parse_python_imports,
    parse_python_imports_from_string,
)

import sys
import json

if len(sys.argv) > 1:
    # Called with a file path → output JSON (designed for shell integration)
    filepath = sys.argv[1]
    result = parse_python_imports(filepath)
    print(json.dumps(result, indent=2))
else:
    print("Running built-in validation tests...\n")

    test_cases = [
        ("import os", "Absolute import"),
        ("import sys as system", "Import with alias"),
        ("from pathlib import Path", "Simple from-import"),
        ("from typing import List, Dict, Optional, Any", "Multiple from-imports"),
        ("from . import helpers", "Simple relative import"),
        ("from ..utils import config", "Relative import (two levels)"),
        ("from .auth.jwt import create_token as jwt_auth", "Relative + alias"),
        ("from package.sub import func1, func2 as f2", "Multiple imports with alias"),
        ("import re, json", "Multiple absolute imports"),
        ("from __future__ import annotations", "__future__ import (should be filtered)"),
        ("from module import *", "Wildcard import"),
        (
            "from typing import (\n    List,\n    Dict,\n    Optional,\n)",
            "Multi-line from-import (with parentheses)"
        ),
    ]

    for code, description in test_cases:
        print(f"Test: {description}")
        print(f"Code: {repr(code)}")
        try:
            result = parse_python_imports_from_string(code)
            if result:
                for item in result:
                    print(json.dumps(item, indent=2))
            else:
                print("→ No imports detected (or filtered)")
        except Exception as e:
            print(f"→ Error: {e}")
        print("-" * 60)
    print("\nParser self-test complete.\n")
