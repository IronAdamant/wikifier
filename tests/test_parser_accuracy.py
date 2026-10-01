"""Parser accuracy on realistic layouts: every internal edge found, nothing invented.

Run scripts/parser_accuracy.py for the precision/recall table to track per release.
"""

import unittest

from tests._base import TempProjectTestCase
from tests.accuracy_fixtures import FIXTURES, materialize, measure


class TestParserAccuracy(TempProjectTestCase):
    def _check(self, name):
        self.reset_js_parser_state()
        fixture = FIXTURES[name]
        materialize(self.root, fixture)
        result = measure(self.root, fixture)
        self.assertEqual(result["false_positives"], [], f"{name}: invented edges")
        self.assertEqual(result["missed"], [], f"{name}: missed edges")

    def test_django_app(self):
        self._check("django_app")

    def test_src_layout_package(self):
        self._check("src_layout_package")

    def test_ts_monorepo(self):
        self._check("ts_monorepo")

    def test_comment_and_string_traps(self):
        self._check("comment_and_string_traps")


if __name__ == "__main__":
    unittest.main()
