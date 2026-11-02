# src/main.rs

**Role:** Argument parsing for the `wikifier` binary.

`--json`, `--full`, `--summary`, `--force`, `--stream`, `--quiet`, `--dry-run`, and `--green` become the string `true`. `-r` / `--reason` and `--only` accumulate. `--reasons FILE` loads reason lines. Other `--key value` flags are stored once and dispatched, including `--directory`, `--max-files`, and `--since`.
