"""Wikifier regression net (Phase 0 of Findings/2026-06-10-Fix-Plan.md).

Pure stdlib unittest only — the zero-dependency constraint applies to tests too.
Run with:  python -m unittest discover tests -v
Every test operates on its own tempfile.TemporaryDirectory project root and
never touches this repository's own wiki/health state.
"""
