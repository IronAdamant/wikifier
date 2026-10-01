# scripts/benchmark_lookup.py

**Purpose:** measure whether Wikifier lookups are cheaper and more correct than grep, on any Python project. `python scripts/benchmark_lookup.py REPO… [--samples 40] [--seed 7] [--detail full] [--json OUT] [--md OUT]`.

- `run_benchmark(repo, samples, seed, detail)`: copies the project's `.py` files to a temp dir (the original is never written), runs `update_maps`, then for sampled targets answers T1 importers (`get_dependents` vs grep of import lines), T2 transitive impact depth ≤ 3, T3 what it imports (`get_dependencies` vs reading the file). Cost = characters read / 4 (`tokens`, `CHARS_PER_TOKEN`); correctness = precision/recall vs the reference.
- Reference: `build_reference_graph` — stdlib `modulefinder` bytecode scan per file via `_ShallowFinder` (real dotted names so relative imports work, PEP 420 namespace packages, nothing scanned beyond the file). `__init__.py` targets and self-imports are excluded on every side (`score`, `_not_init`).
- `grep_importers` models `grep -rn` over import lines for the module stem; `copy_python_tree`, `render_markdown` (summary tables), `main`.
- Known reference gap: imports that only resolve through tool config (e.g. pytest `pythonpath`) count against Wikifier even when it is right.
