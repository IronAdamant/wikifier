# wikifier/cli.py

**Purpose:** `wikifier` / `python -m wikifier` — an argparse front end over `wikifier.api`; every command is Python (the `.sh`/`.ps1`/`.bat` launchers only exec this). `main(argv)` returns the exit code (`__main__.py` passes it to `SystemExit`).

- `--target DIR` / `--project-root DIR` and `--use-canonical` are accepted anywhere on the line (`_extract_global_options`); a missing target exits 1.
- Command names accept `_` or `-` and the historical aliases (`bootstrap`, `suggest`, `why`, `deps`, …).
- Commands: core loop (`mark-green --force --json`), batch (`record-changes -r PATH=WHY --reasons FILE --default --only --since --green --dry-run`), `verify-wikis`, lookup (`dependencies [--full]`, `dependents`, `cycles`, `journal`, `issues`), maps (`update-maps --stream`), hygiene/healing, `init`, `monitor`, `serve`, `daemon`.
- JSON to stdout for machine commands; exit code 1 when `success` is false (`validate`: 1 if anything is missing; `autonomous-status`: 2 when blocked).
- Re-exports the api functions so `from wikifier.cli import check_changes` keeps working.
