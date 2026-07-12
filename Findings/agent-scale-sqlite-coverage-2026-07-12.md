# Agent-scale SQLite + map_coverage (4.6.4) — 2026-07-12

**subid:** agent-scale-sqlite-coverage  
**Package:** 4.6.4  

## Problem closed

1. **JSON tax** — warm `update_maps` no longer requires deserializing multi‑MB `import_cache.json` pair payloads every time (SQLite mtime index + meta).
2. **Partial maps** — `map_coverage.complete` / `files_remaining_dirty` on structured returns.
3. **ACS thrash** — bootstrap `acs_guidance` + protocol/README: actionable + reason codes only.
4. **Go accuracy (tiered)** — same-module resolve via `go.mod` under scoped trees.

Human dashboard untouched.

## Warm perf (same machine)

| Target | Baseline warm2 (JSON era) | After (SQLite warm) | Δ |
|--------|---------------------------:|--------------------:|---|
| Wikifier self | 42.2 ms | **~21–27 ms** | −35–50% |
| llama_index `llama-index-core` | 569.9 ms | **~237–356 ms** | −37–58% |
| redox `src` | 15.6 ms | 17.0 ms | ~noise |

**Skeptic fix:** barrel merge no longer calls full `load_cache` on 0-dirty; only mtime-index dirty + meta. Instrumented: `load_cache_dict` / `load_cache` call count **0** on warm llama path (`perf_after_barrel_fix.json`).

Pass2 stable (no thrash). Backend `sqlite` on all dogfood targets after first migrate.

## Dogfood (2 passes, single-project roots)

| Project | Pass1 warm2 | Pass2 warm2 | Coverage |
|---------|------------:|------------:|----------|
| Wikifier | 29 ms fast | 27 ms fast | complete |
| redox | 17 ms fast | 17 ms fast | complete |
| llama_index | 344 ms fast | 356 ms fast | complete |
| rust `library/std/src` max40 | remaining 179→…→99 | remaining drains | **incomplete** until budget clears |
| airflow scoped | ~920 ms fast | ~921 ms fast | complete |

Multi-repo parent: still `scope.ok=false` + warnings (not used as root).

## Residuals

- Full `load_cache` still used for dirty parse + graph rebuild (not warm zero-dirty).
- Large monorepo **candidate walk** still costs (airflow ~0.9s warm even with sqlite).
- Multi-lang deep resolve beyond Go same-module / Rust crate:: remains shallow by design.
- Optional dual-write JSON only for small projects (≤400 files) or `WIKIFIER_CACHE_JSON=1`.

## Tests

`python3 -m unittest discover tests` — 93 OK.
