# Dogfood issue fixes — cloned_sample_projects (Wikifier 4.5.6)

**Date:** 2026-07-09  
**JSON:** `Findings/dogfood-hygiene-fix-2026-07-09.json`

## Issues → fixes

| Issue | Root cause | Fix |
|-------|------------|-----|
| llama_index maps, no health | Health stubs only on dirty parse; warm cache = 0 parse | `seed_health_from_map` after every update-maps; CLI `seed-health` |
| validate huge missing_count | Counted all files under monitor incl. non-source; full map vs lean monitor | Map-first validate: parseable only + in-scope map gaps |
| Seed failed on deep paths | `_entry_is_under_root` treated `len(parts)>5` as abs | Depth heuristic removed |
| Yellow/pending floods | `monitored=.` thrash + auto-detected pending | Lean monitors + prune pending (auto) / health outside monitored |
| Parent container pollution | Wiki state at multi-project root | Removed parent staging/journal/library; README only |

## Post-fix (all 8 projects)

| Project | Health rows | Pending | Validate missing | Notes |
|---------|-------------|---------|------------------|-------|
| airflow | 1445 | 0 | 0 | seeded in-scope map |
| Babylon.js | 1644 | 0 | 0 | |
| dotnet-dotnet | 26 | 0 | 0 | lean test monitor |
| linux | 13 | 0 | 0 | init |
| **llama_index** | **724** | **0** | **0** | **file_health.json created** |
| llvm-project | 424 | 0 | 0 | Support dirs |
| redox | 27 | 0 | 0 | |
| rust | 669 | 0 | 0 | map + disk seed |

All yellow = map-first stubs (expected). No reds. Parent `.wikifier_staging` / `library.md` removed.

## Commands

```bash
wikifier --target <project> seed-health
wikifier --target <project> prune-pending
wikifier --target <project> prune-health
wikifier --target <project> validate
wikifier --target <project> health --summary
```
