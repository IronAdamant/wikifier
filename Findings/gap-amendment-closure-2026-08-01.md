# Gap amendment closure (2026-08-01)

**Package:** 4.6.9  
**Plan:** `Findings/gap-amendment-plan-2026-08-01.md`  
**subid:** gap-amendment-closure  

## Summary

Implemented P0/P1 closed-when bars (G1–G10), shipped lock timeout (G13), ACS library prefer-actionable (G9), init lean default (G7), CLI-at-scale policy (G15). Reclassified deep product items G11/G12/G14/G16/G19. Left G20–G23 as residual-evidence (multi-day/multi-month not in scope).

## Verification

- `python -m unittest discover tests` → **140 OK**
- New: `tests/test_gap_amendment_2026_08.py`
- Dogfood: 9/9 bootstrap on ConsistencyHub, Grok-Bevy, RecipeLab_alt, Trammel, stele-context, Crystal Drift, Iron Feud, llama_index, airflow (budgeted where noted)

## Key code paths

| Area | Files |
|------|-------|
| Bootstrap / actions | `wikifier/agent_loop.py` |
| Map flags | `wikifier/cli.py` |
| ACS surface | `wikifier/library.py` |
| Locks | `wikifier/locking.py` |
| Init | `wikifier.sh`, `wikifier/scripts/wikifier.sh` |
| Protocol | `skills/run.md`, `Claude.md` |
