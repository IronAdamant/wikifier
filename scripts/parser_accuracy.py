#!/usr/bin/env python3
"""Print parser precision/recall per accuracy fixture (track this per release).

    python3 scripts/parser_accuracy.py
"""

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.accuracy_fixtures import FIXTURES, materialize, measure  # noqa: E402


def main() -> int:
    worst = 1.0
    print(f"{'fixture':28} {'precision':>9} {'recall':>7}")
    for name, fixture in FIXTURES.items():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            materialize(root, fixture)
            result = measure(root, fixture)
        worst = min(worst, result["precision"], result["recall"])
        print(f"{name:28} {result['precision']:9.2f} {result['recall']:7.2f}")
        for edge in result["false_positives"]:
            print(f"    invented: {edge[0]} -> {edge[1]}")
        for edge in result["missed"]:
            print(f"    missed:   {edge[0]} -> {edge[1]}")
    return 0 if worst == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
