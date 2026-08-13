# cli.py

Hybrid agent CLI. Re-exports `wikifier.api` so `from wikifier.cli import check_changes` works. `main()` is Python-primary for Core + validate/seed/prune/readiness/update-maps; unknown verbs (init/monitor/daemon/serve/journal) forward to `wikifier.sh`.
