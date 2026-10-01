# Lookup benchmark: Wikifier vs grep on real repositories (2026-10-01)

Question: is a Wikifier lookup cheaper and more correct than what an agent does
without it? Measured with `scripts/benchmark_lookup.py` (stdlib only, reproducible:
`python scripts/benchmark_lookup.py REPO --samples 40 --seed 7`).

## Method

- **Repos:** Apache Airflow at `4cf176e6a4` — `airflow-core/` (1,143 Python files) and the
  whole monorepo (7,174) — and LlamaIndex at `23bd65aaf`, `llama-index-core/` (724). Each
  project's `.py` files are copied to a temp dir; the originals are never written.
- **Questions** (40 sampled targets per repo, 3/4 of them imported by something):
  - T1 *which files import M?* — `get_dependents(M)` vs `grep -rn` over import lines for M's module name.
  - T2 *what could break if I change M?* — importers to depth 3, repeating T1 for each.
  - T3 *what does M import?* — `get_dependencies(M)` vs reading M (whole file, or just its import lines).
- **Cost:** characters the agent must read (tool output as the CLI prints it, grep's
  `path:line:text` output, file bytes) ÷ 4 ≈ tokens. Transitive questions stop expanding at
  200k tokens (about one large context window); the answer is whatever was found by then.
- **Correctness:** precision/recall against an independent reference — the stdlib
  `modulefinder` bytecode scanner run per file (real dotted names, namespace packages,
  lazy imports inside functions). It shares no code with Wikifier's parser. Spot-checked by
  hand on several files. `__init__.py` targets and self-imports are excluded on every side.

## Results (after the fixes below)

| Repo | Question | Tool | Precision | Recall | Exactly right | Tokens, median | Tokens, total (40 q) | Over 200k budget |
|---|---|---|---|---|---|---|---|---|
| llama-index-core | T1 importers | **Wikifier** | 1.00 | 1.00 | 40/40 | 72 | 4,490 | — |
| | | grep | 0.72 | 1.00 | 27/40 | 84 | 110,169 | — |
| | T2 impact ≤3 | **Wikifier** | 1.00 | 1.00 | 40/40 | 487 | 136,402 | 0 |
| | | grep | 0.49 | 0.78 | 11/40 | 209 | 3,348,391 | 15 |
| | T3 imports | **Wikifier** | 1.00 | 1.00 | 40/40 | 286 | 11,821 | — |
| | | read file | — | — | — | 1,173 | 54,564 | — |
| airflow-core | T1 importers | **Wikifier** | 0.98 | 1.00 | 39/40 | 111 | 9,460 | — |
| | | grep | 0.73 | 1.00 | 23/40 | 266 | 49,291 | — |
| | T2 impact ≤3 | **Wikifier** | 0.98 | 1.00 | 36/40 | 584 | 268,408 | 0 |
| | | grep | 0.52 | 0.89 | 12/40 | 21,676 | 3,116,963 | 8 |
| | T3 imports | **Wikifier** | 1.00 | 1.00 | 40/40 | 252 | 14,795 | — |
| | | read file | — | — | — | 1,000 | 125,773 | — |

Whole-graph agreement with the reference: llama-index-core 2,620 / 2,620 edges (precision
1.00, recall 1.00); airflow-core 3,571 vs 3,549 (precision 0.994, recall 1.00). `update-maps`
from scratch: 2.3 s (724 files), 4.5 s (1,143), 21 s (7,174).

**Reading the numbers**

- **Accuracy is the main difference.** grep matches module *names*: common names (`base`,
  `utils`, `types`) pull in every same-named module, and relative or aliased imports are easy
  to misread. It was exactly right on 23–27 of 40 direct questions and 11–12 of 40 impact
  questions; Wikifier on 36–40.
- **Cost is similar for a typical file, and very different on bad cases.** Median direct
  lookups cost 70–270 tokens either way, but one grep for a common name cost up to 17.6k
  tokens (100k on the full monorepo) while Wikifier's largest answer was 1.7k. For impact
  questions grep hit the 200k budget on 8–15 of 40 targets and still answered with
  precision 0.5.
- **T3:** `get_dependencies` costs about 1/4 of reading the file and resolves every import
  to a path. Reading only the import lines is cheaper (~100 tokens) but leaves the agent to
  map module names to files itself.
- The remaining airflow-core misses are reference gaps, not Wikifier errors: tests import
  `unit.listeners…`, which only resolves because Airflow's pytest config adds `tests/` to the
  path. Wikifier resolves it to the right file; the reference cannot see it.

## What the benchmark found (fixed in 4.7.0)

| Finding | Before | After |
|---|---|---|
| `get_dependencies` returned a paragraph of boilerplate per import (stdlib included): **more tokens than reading the file** | median 2,151 / 2,619 tokens per file | 286 / 252 (compact default; `detail="full"` keeps the old records) |
| Phantom edges on case-insensitive filesystems: `from airflow.models import DagRun` became an edge to a non-existent `models/DagRun.py` because `models/dagrun.py` exists on macOS/Windows | graph precision 0.978 / 0.959 | 1.00 / 0.994 |

## Not measured / known limits

- **Full Airflow monorepo: accuracy not scored.** Airflow splits one `airflow` package
  across ~100 `providers/*/src` roots that are merged at install time. The reference
  cannot model that without an installed environment (it found 26 edges), so only cost and
  scale are reported: Wikifier T1 median 73 tokens vs grep 71 (max 168 vs 100,393); T2 grep
  over budget on 16/40.
- **Wikifier has the same blind spot:** a provider importing another provider
  (`airflow.providers.postgres…` from `providers/pgvector/`) is treated as external because
  the target lives in a different `src/` root. Proposed fix: a configurable list of Python
  import roots (e.g. every `*/src` in `map_paths.txt`), consulted after the file's own
  package root.
- Python only (the reference is Python's own bytecode scanner). JS/TS accuracy is covered by
  the fixture suite (`scripts/parser_accuracy.py`), not by this benchmark.
- Cost counts what the agent reads, not what it writes or reasons; tokens ≈ characters/4.
- This measures lookups, not whole tasks. A live A/B (the same edit task run by an agent
  with and without Wikifier, comparing total tokens and mistakes) is the next step; it costs
  model usage, so it is not part of the default run.
