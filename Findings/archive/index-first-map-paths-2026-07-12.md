# Index-first warm dirty + map_paths + JSON dual-write deprecation (4.6.6–4.6.7)

**subid:** index-first-map-paths / map-scope  
**Package:** 4.6.7

## Index-first
`resolve_candidates()` peels collect: when fingerprint + map-scoped sqlite index agree with `_candidate_list` and live source count matches, no git re-list (`index_first_dirty=true`, `candidates_relisted=false`). Poison: scoped index larger than blob / different keys → re-list.

## MapScope (4.6.7 structural fix)
One `MapScope` (`resolve_map_scope`) drives:

| Path | Behavior |
|------|----------|
| `collect_candidate_source_files` | walk roots from directory / map_paths / monitored dirs / full |
| `_live_source_count` | same roots (no full-tree vs map-subset thrash) |
| `filter_index_to_map_scope` | keep only index keys under map prefixes |
| `prune_file_index_outside_scope` | drop leftover full-tree rows after narrow |
| `evaluate_candidate_reuse` | pure decision; I/O only in `try_cached_candidate_rels` |

**Migration repro fixed:** full map n=3 → write `map_paths=pkg/` → warm2/3 `candidates_reused=True`; outside index keys pruned. Prior bug: `filter_index_to_scope(directory=None)` returned the full leftover index → permanent re-list.

## Warm floors (4.6.7 dogfood pass B)
| Target | Warm B | n | reused |
|--------|--------|---|--------|
| Wikifier (map_paths wikifier+tests) | **30 ms** | 50 | yes |
| llama_index / llama-index-core | **76 ms** | 724 | yes |
| airflow / airflow-core | **179 ms** | 1920 | yes |
| rust / library/std | **79 ms** | 719 | yes |
| Babylon.js / packages | **399 ms** | 3895 | yes |
| redox | **150 ms** | 27 | yes |

Residual floor on large scopes is mtime/stat + live count under scope (not full JSON re-walk). Sub-100ms on every 1k+ tree is not a hard SLA; airflow ~180ms and Babylon ~400ms are honest floors with **stable reuse** (no thrash).

## map_paths vs monitored_paths
- `map_paths.txt` = package roots for **map**
- `monitored_paths.txt` = wiki/health only
Self: `map_paths.txt` → `wikifier/` + `tests/`

## JSON dual-write
Default **sqlite only**; `WIKIFIER_CACHE_JSON=1` opt-in. Dual-read migrate remains. `cache_status` marks dual-write DEPRECATED.

## ACS / agents
Prefer `actionable_low_conf_edges` + reason codes — not raw `low_conf_edges` averages. Human dashboard untouched.

## Deferred / residual
- Deep multi-lang monorepo graphs (local resolvers only)
- Human dashboard investment
- Universal sub-100ms on every 1k+ scope
- Megamodule density (AGENT MAPs + tests; no big-bang peel beyond collect/dirty)

## Tests
125 unittest OK including `TestCandidateReuseScopeMatrix` + migration integration test. Double dogfood self + 5 clones (all warm B reused).
