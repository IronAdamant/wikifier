# Long-horizon autonomous ops (honest runbook)

**Package:** 4.5.7+  
**Not a claim:** this document does **not** certify 72h/ multi-month 0-corruption soak. It is the supported *configuration and observation* path so agents can run unattended **safely** and collect that evidence later.

## What “ready” means

| Readiness (`autonomous-status`) | Meaning |
|----------------------------------|---------|
| `blocked` | No map/health or severe ghosts — fix first |
| `map_ok_scope_risk` | Map/health OK but monitor/root warnings |
| `ready_for_daemon` | Lean monitor, Map Ready/Good, safe for heartbeat |
| `ready_with_agent_wiki_work` | Daemon OK but actionable yellows remain for agents |
| `not_ready` | Reds or other blockers |

**Map Ready** = structure covered (stubs OK). It is **not** wiki-prose-complete.

## Before unattended run

```bash
export WIKIFIER_PROJECT_ROOT=/abs/path/to/ONE/project   # never multi-repo parent
# lean monitored_paths.txt (package roots, not bare .)
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" autonomous-status
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" validate
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" prune-pending
```

Optional env for large trees:

```bash
export WIKIFIER_DAEMON_MAPS_INTERVAL=600   # default; maps not every 30s
export WIKIFIER_DAEMON_MAPS=0              # check-changes only if maps too heavy
export WIKIFIER_CHECK_CHANGES_MAX=2000
```

## Start heartbeat

```bash
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" daemon start
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" daemon status
# Heartbeat: $WIKIFIER_PROJECT_ROOT/.wikifier_staging/daemon_heartbeat.json
# Log:       $WIKIFIER_PROJECT_ROOT/.wikifier_staging/daemon.log
```

## Metrics harness (code-backed)

```bash
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" metrics-snapshot
# files:
#   .wikifier_staging/metrics_latest.json
#   .wikifier_staging/metrics_history.jsonl
python -m wikifier --target "$WIKIFIER_PROJECT_ROOT" autonomous-status
# includes metrics + metrics_growth when ≥2 samples exist
```

Daemon auto-appends metrics every `WIKIFIER_DAEMON_METRICS_INTERVAL` seconds (default 3600; set `0` to disable periodic, start/wake still force one sample).

## Soak observation (M5.3 evidence checklist)

For each of ≥3 targets, ≥72h:

1. `daemon_heartbeat.json` `ok: true` and low `consecutive_failures`
2. `daemon.log` — no timeout/error storms
3. `metrics_history.jsonl` `staging_bytes` growth &lt; ~5–15%/day (order-of-magnitude)
4. `file_health` — no corruption; ghosts cleaned
5. `journal/` continues writing; no empty holes after wake
6. After kill/restart: daemon recovers; check-changes succeeds

Agents still own **wiki prose + mark-green**; daemon only keeps map/mtime health fresh.

## Dual scope reminder

| Knob | Controls |
|------|----------|
| `monitored_paths.txt` | check-changes / health thrash surface |
| `update-maps --directory` / `--max-files` | map build scope |
| `project_root` | which tree’s `.wikifier_staging` |

Never point `project_root` at `cloned_sample_projects/` itself.
