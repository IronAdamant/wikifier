"""Run the extracted self-test scripts under unittest (output captured; shown only on failure)."""

import io
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SELFTEST = Path(__file__).resolve().parent / "selftest"


class TestExtractedSelftests(unittest.TestCase):
    def _run(self, name: str):
        path = SELFTEST / name
        self.assertTrue(path.is_file(), f"missing {path}")
        # Execute as __main__ so assert-based scripts raise on failure.
        output = io.StringIO()
        try:
            with redirect_stdout(output), redirect_stderr(output):
                runpy.run_path(str(path), run_name="__main__")
        except SystemExit as e:
            if e.code not in (0, None):
                self.fail(f"{name} exited with {e.code}\n{output.getvalue()}")
        except Exception:
            print(output.getvalue())
            raise

    def test_contracts_selftest(self):
        self._run("run_contracts_selftest.py")

    def test_python_parser_selftest(self):
        self._run("run_python_parser_selftest.py")

    def test_cdia_selftest(self):
        self._run("run_cdia_selftest.py")

    def test_resolution_selftest(self):
        self._run("run_resolution_selftest.py")

    def test_javascript_selftest(self):
        # Heavier; still must pass for agent-navigable JS parser
        self._run("run_javascript_selftest.py")


if __name__ == "__main__":
    unittest.main()
