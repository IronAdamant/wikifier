# src/main.rs

**Role:** Argument parsing for the `wikifier` binary.

`<command> --help`, `<command> -h`, and `help <command>` print that command's usage line from `command_help` and return before anything runs (so `init --help` no longer initialises). `init DIR` uses that directory as the project root when `--target` was not passed. `--json`, `--full`, `--summary`, `--force`, `--stream`, `--quiet`, `--dry-run`, and `--green` become the string `true`. `-r` / `--reason` and `--only` accumulate. `--reasons FILE` loads reason lines. Other `--key value` flags are stored once and dispatched, including `--directory`, `--max-files`, `--since`, and `monitor --interval`. `monitor` help says the loop is the cheap health pass and does not run `update-maps`. `daemon` help names the separate map interval.
