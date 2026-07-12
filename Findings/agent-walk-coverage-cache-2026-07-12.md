# Walk cost + Core coverage + thin resolvers + cache-status (4.6.5)

**subid:** agent-walk-coverage-cache  
**Package:** 4.6.5

## Wins (warm2, same machine)

| Target | Baseline warm2 | After | Δ |
|--------|---------------:|------:|---|
| Wikifier | 17.7 ms | **3.7 ms** (reused) | −79% |
| llama_index scoped | 237.7 ms | **139.5 ms** | −41% |
| airflow-core/src | 514.0 ms | **298.3 ms** | −42% |

Collect ms also dropped (llama 74→23, airflow 152→32 on pass2 collect measurement). Candidate list reuse `candidates_reused=true` on stable scope fingerprints.

## Core coverage
`suggest_next_actions` / bootstrap include `map_coverage` and `update_maps_until_complete` when incomplete (max_files dogfood + unit tests).

## Resolvers
C# `.csproj` RootNamespace path; C/C++ `include/` local headers. Go/Rust prior.

## Cache ops
`wikifier cache-status` / `cache_status()` — backend, bytes, ACS, coverage, dual-write policy.

## Residuals
- ~100ms class **not** universal: llama ~140ms, airflow ~300ms floors (git list + stats on 700–1400 files still cost).
- Unscoped huge trees still out of budget by design.
- Dual-read JSON remains for migrate safety.

## Skeptic fixes (same day)
1. **monitored_paths ≠ map roots:** wiki-file lists (skills/run.md, README, …) no longer become the sole collect set (had collapsed self to `n=1` / `server.py` only). Map collect uses **directory package roots** from monitored or falls back to full source walk. Self repaired: **parseable_files=49**, edges=520.
2. **Fingerprint:** max **directory** mtime under walk (not walk-root only) so nested file creates invalidate reuse; honest tests for reuse + nested expand.
3. Fair self warm after repair: **~6.3 ms**, `candidates_reused=true`, parseable=49 (not a fake n=1 win).

## Skeptic (poison reuse)
- `try_cached_candidate_rels` now requires **live source count == stored count** (git pathspec count), so a matching-fp 1-file blob cannot yield parseable_files=1 when collect has 2+.
- Unit: `test_poisoned_one_file_blob_not_reused`. Re-dogfood pass1/2: Wikifier **n_cands=49**, parseable=49 both passes.

## Tests
103 unittest OK; dogfood self repair + llama/airflow/redox.
