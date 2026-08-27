# wikifier/parsers/_ldsi.py

Shared LDSI helpers (`_extract_balanced_argument`, `_extract_candidate_literals`, `_analyze_dynamic_specifier`, `_apply_dynamic_registry`) used by both Python and JS parsers.

**Why separate:** `import wikifier.parsers.python` must not load `javascript.py` / BREE / CDIA. 4.6.13 moved these off the JS megamodule.
