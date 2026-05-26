# Gap #1: Deep Barrel Invalidation at Real Monorepo Scale — Long-Term Zero-Dependency Strategy

**File Type**: Living architectural strategy and implementation roadmap  
**Created**: 2026-05-20  
**Last Updated**: 2026-05-20  
**Status**: Open — Ready for phased execution and review  
**Owner**: Gap #1 Closure Program (M2-Rem-08 / v0.4 continuation)  
**Related**: `Findings/gap1_dependency_intelligence_4phase_roadmap_open.md` (Phase 2 BREE), `Findings/m2_rem_08_and_v0.4_progress_tracker.md`, `wikifier/parsers/bree.py`, `wikifier/import_cache.py`, `wikifier/scripts/wikifier.sh`

---

## Executive Summary & Vision

The core promise of Gap #1 Phase 2 (BREE + BarrelResolutionCache) is now technically reachable:

> **"Edit any barrel file (leaf, intermediate, or root of a re-export chain, even in deep/overlapping graphs) → *only* the real affected importers are selected for re-analysis. No full-repo work. Ever."**

This document defines the **long-term, production-grade, strictly zero-dependency strategy** to make selective barrel invalidation a reliable, cheap, precise, and fully observable primitive at true monorepo scale (5k–50k+ files, highly creative JS/TS with heavy barrel usage, workspaces, symlinks, partial expansions).

**Vision Principles**:
- **Cheap & Precise**: Invalidation cost proportional only to number of *changed barrels* (typically 1–10 per developer/agent edit), not to #chains, #files, or graph depth.
- **Correct by Construction**: Handles overlapping chains, shared sub-chains, partial expansions, cycles (graceful), deletions, and all path identities.
- **Zero-Dependency**: Pure Python stdlib + bash. No new packages, no fs watchers (polling + mtime is the contract), no external graph DBs.
- **Observable & Debuggable**: Agents and humans can see *exactly* which barrel change(s) caused which importers to be dirtied, with chain traces, for diagnostics, health, journal, and MCP tools.
- **Clean Integration**: Lives inside the existing first-pass dirty detection, BRC persistence model, `update-maps` (incremental + `--full`), `check-changes`, daemon, and record-change flows. No new top-level concepts.
- **Durable**: Survives node-identity evolution (v0→v1 canonical), project moves, symlinked layouts, pnpm/Yarn/Nx monorepos, and long-running daemon sessions.

When complete, barrel edits become a first-class low-cost event in the system: the same way a direct source change triggers targeted reparse today, a barrel change will trigger *only its true consumers*.

---

## Current State (Post Phase 2.3 Wiring & Harness Proof)

Recent work (R8 + three-agent completeness push) has delivered:

### Implemented & Wired
- `BarrelResolutionCache` (bree.py): `resolutions` (chain_id → BarrelChainResolution with `barrel_chain`, `hops`, `results`, `importers`, `mtimes_snapshot`, `mtimes_signature`, `is_partial`, `node_identity_version`) + `file_index` (barrel_path → {chain_ids, importers} reverse map).
- Core methods: `store(...)` (merge importers + update both indexes), `is_stale(entry, root)`, `collect_stale_importers(root)` (full linear scan over resolutions), `get_affected_importers(changed_file)` (O(1) via reverse index), `clear`.
- `invalidate_stale_barrel_entries(cache, root)` (import_cache.py) — thin wrapper returning the union of stale importers.
- **Production wiring**:
  - `parsers/javascript.py`: `_follow_reexports` auto-loads BRC under `WIKIFIER_PROJECT_ROOT`, passes `{"barrel_cache", "cache_root", "importer_rel"}` to `expand_chain`. Every via-barrel path (including recursive BREE leaves) participates.
  - `expand_chain` (bree.py): mtime-validated cache *hits* (replay rich `results` + barrel_v2), fresh *stores* with snapshot of entry+leaves resolved_paths + per-level store for sub-chains, immediate `to_cache_updates` + `save_cache` (best-effort, under lock).
  - `scripts/wikifier.sh` (and root copy): after R7 `compute_files_needing_reparse` (single-spawn optimized mtime dirty), explicit barrel augmentation block using `invalidate_stale_barrel_entries` + append to `files_to_reparse`. Persist protection snapshots `_barrel_resolutions` / `_barrel_file_index` before rich normalizer and restores afterward.
- **100% emission**: Every `via_barrel` creation site (BREE leaves, early synths, unresolved) now carries full `barrel_v2` + final-hop `resolution_metadata` / `strategy` (res_meta_v1).
- **Harness proof** (`gap1_validation_harness.py:run_barrel_invalidation_proof`): synthetic deep barrel + 2 consumers + unrelated file; exercises `expand_chain` population, mtime touch on leaf, `invalidate_stale...` + `get_affected_importers`, selective dirty, re-expand refresh. Integrated into `--gap1-health`.
- Contracts (`contracts.py`): reserved top-level keys documented; `node_identity_version` (v0/v1) for chains.
- Persistence, locking, and daemon/check-changes scaffolding already in place.

### Proven Correctness (Synthetic + Partial Real)
- Overlapping chains and shared sub-chains work via per-level stores: every barrel in a chain (including intermediates) gets the top importer listed in its `file_index` entry.
- mtimes_snapshot decouples barrel freshness from importer mtime (core innovation).
- Cache hits avoid re-work; partial results are stored and replayed gracefully.
- Real dogfood (ConsistencyHub 577f, RecipeLab) shows high barrel_edge rates and correct classification.

### Known Gaps vs. Long-Term Target (at 5k–50k Scale)
1. **Hot-path cost**: `invalidate_stale_barrel_entries` / `collect_stale_importers` always performs a full linear scan over *all* stored chains + mtime probes on their snapshots. Acceptable today (`#chains << #files`), but violates "never full-repo work" for pure barrel churn at 50k.
2. **Delta vs. Scan**: No usage of the fast `get_affected_importers` path driven by the *already-known changed files* from regular dirty detection. Current sh calls the full collect unconditionally.
3. **Path Identity**: `importer_rel` uses `Path.resolve().relative_to`, resolved_paths come from central resolver (good), but BRC store/index keys are not yet *enforced* through `resolution.to_canonical_rel(..., follow_symlinks=True)` + v1 stamping everywhere. Symlink-heavy or workspace monorepos risk duplicate or missed entries.
4. **Deletion & Staleness**: `is_stale` only compares mtimes on *existing* files in snapshot; a deleted barrel in a chain does **not** trigger stale (importers of a now-broken barrel are not re-analyzed).
5. **Observability**: Returns only `List[str]` of importer relpaths. No structured "why" (which specific barrel(s) + chain_ids + detector + partial status). Hard for agents to explain "this file was re-parsed because of barrel edit X".
6. **Daemon / check-changes disconnect**: `cmd_check_changes` only walks direct `-newermt` files and marks them Yellow/pending. Barrel-affected importers (whose *source* mtime is unchanged) are invisible to health/pending/journal until an explicit `update-maps` runs. The "set & forget" daemon experience is incomplete for barrel-driven staleness.
7. **Persistence & Lifecycle**: Per-parser immediate saves + main persist protection work, but no pruning/GC of dead chains (deleted importers, removed barrels, very old partials). Cache JSON can slowly grow. No migration story for node_identity bumps on persisted chains.
8. **Partial Expansion Semantics**: Partial chains are stored and replayed, but there is no explicit policy hook on "stale partial → force deeper re-expansion on next parse of affected importers".
9. **Harness & Dogfood**: Proof is synthetic only; no symlink/workspace/deletion/50k-scale stress cases yet. Real 20k+ barrel-heavy dogfood for invalidation not yet executed end-to-end.

Current practical state: **~92–95%** on barrel-heavy large messy monorepos for normal workflows (per tracker). The primitive "works" but is not yet the cheap, precise, observable, scale-proof engine required for autonomous 50k-file operation.

---

## Target State — The Scalable Primitive

After execution of this strategy:

- In any `update-maps` (incremental or full) or daemon-assisted flow:
  1. Regular mtime/new-file dirty set is computed (R7 single-spawn `compute_files_needing_reparse`).
  2. For every file in that dirty set that appears in BRC `file_index`, the *fast* `get_affected_importers(changed_rel)` is called. Union of results is added to the reparse set.
  3. Cost: O(#changed files that happen to be barrels) × small constant. Zero scans over the BRC resolutions dict.
  4. Only the true transitive consumers (across all overlapping chains that mention the changed barrel) are re-parsed. Their BREE expansions refresh the snapshots/indexes.
- `is_stale` treats any non-existent file in a snapshot as stale → importers of broken chains get refreshed (they will see the deletion or failure naturally).
- All stored paths (barrel_chain, snapshot keys, importer_rel, file_index keys) are **canonical physical relpaths** (v1) produced by `resolution.to_canonical_rel(..., follow_symlinks=True)`.
- `invalidate_stale_barrel_entries` (and new sibling) returns **structured reports**:
  ```python
  [
    {
      "importer": "src/components/Foo.js",
      "triggering_barrels": ["barrels/index.js", "barrels/leaf.js"],
      "chain_ids": ["a1b2c3d4", ...],
      "partial": False,
      "reason": "mtime of leaf.js increased"
    },
    ...
  ]
  ```
  Logged verbosely under `WIKIFIER_DEBUG=1`, surfaced in diagnostics, MCP, and journal.
- `check-changes` (and therefore the daemon monitor) also runs a lightweight barrel-delta pass on its newly-detected changed files and marks *affected importers* Yellow with a precise note ("stale via barrel re-export from X").
- BRC has optional lightweight self-pruning (on save or explicit `gc_stale_entries`).
- Full round-trip harness + real-monorepo dogfood (including symlinked workspace layout) passes at 50k-simulated scale with <50 ms invalidation overhead.
- Contracts + BRC dataclass carry `node_identity_version`; future v2 bump has a documented one-time migration path.

Result: barrel invalidation is no longer "a clever cache" — it is a **first-class, low-cost, explainable primitive** of the dependency intelligence engine.

---

## Zero-Dependency Design Constraints & Trade-offs

**Non-negotiables**:
- No `watchdog`, `inotify`, `pyinotify`, or platform fs-event libs.
- No graph libraries (NetworkX etc.). The reverse `file_index` + `barrel_chain` lists *are* the graph.
- No persistent embedded DB (SQLite etc.). The single `import_cache.json` (with two reserved top-level dicts) remains the sole store.
- No new top-level cache files.
- All Python code stays importable with zero extra `pip` requirements (matches current `pyproject.toml`).

**Accepted Trade-offs** (already proven workable):
- Polling + mtime (with the snapshot decoupling) instead of events.
- JSON (human-readable, lockable, streamable) vs. binary.
- Linear `collect_stale` retained as *fallback/safety* path only (used on `--full`, first run, or when no prior dirty list is available).
- Best-effort immediate persist from parser subprocesses (protected by the snapshot/restore dance in sh).
- In-memory BRC objects are thread-unsafe by design (CLI/MCP/daemon single-threaded usage model).

**Extensibility without deps**: Future richer policies or precomputed barrel indexes can be added inside BREE (registry pattern already exists) or as optional helpers behind `if os.environ.get("WIKIFIER_ADVANCED_BARRELS")`.

---

## Scalability Analysis — 5k to 50k+ Files

| Dimension              | Current (scan) Risk at 50k | Target (delta) Behavior                          | Notes |
|------------------------|----------------------------|--------------------------------------------------|-------|
| # barrel chains stored | 500–5k (realistic)        | Same; dict lookup only on changed barrels       | Chains are created only when an importer actually expands them |
| Invalidation CPU/IO    | O(#chains × avg chain len) mtime probes per run | O(#barrels among the N dirty files)             | Typical N=1–20; worst-case still << full |
| BRC memory (in python) | Few hundred KB to low MB  | Same                                            | Only two top-level dicts; JSON load is fast |
| JSON size on disk      | <5 MB even at 50k         | Same + optional age pruning                     | Text, compressible, human-inspectable |
| Overlapping chains     | Correct via multi-level stores + index fan-in | Same + explicit canonical dedup                 | A 10-hop chain touching 30 importers still produces only ~10 entries |
| Partial / deep graphs  | Handled per-level         | Same + explicit "stale partial forces re-expand" | BREE policy already bounds fanout/depth |
| Symlinks / workspaces  | Risk of duplication       | Eliminated by canonical v1 enforcement          | Single physical identity for inode |
| Daemon/check-changes   | Blind to transitive       | Direct + barrel-delta marks all affected Yellow | Still O(changed) |
| First-pass reparse set | May over-reparse          | Minimal exact set                               | Massive win for creative monorepos with 100s of barrel consumers |

**Key Enabler**: The regular dirty detection *already* identifies every changed barrel file (they are just ordinary source files in the candidate list). We simply treat "this barrel is dirty" as a signal to consult the reverse index for its consumers. No separate full-repo barrel walk is ever required.

---

## Roadmap (Sequenced Waves — Early Value, Low Risk)

### Wave 1 — Delta Invalidation + Correctness Hardening (Immediate, 2–4 days)
Goal: Make the hot path O(changed) and close the two correctness bugs.
1. Refactor `invalidate_stale_barrel_entries` (import_cache) and callers:
   - Add optional `changed_files: Optional[Iterable[str]] = None`.
   - If provided (or derivable from known dirty), iterate only those, call `brc.get_affected_importers(f)` for each, union. Fall back to `collect_stale_importers` only when `changed_files` is None/empty or `full_rebuild`.
2. Update sh `perform_first_pass...` / barrel augmentation block (both copies) to pass the just-computed `files_to_reparse` (or the subset that are JS/TS) as the changed list.
3. Fix `BarrelResolutionCache.is_stale`: if any `f` in snapshot does not exist on disk → return True (stale).
4. Canonical normalization pass:
   - In `javascript.py` (importer_rel) and in BRC `store` / `_make_chain_id` paths: convert every path through `from wikifier.resolution import to_canonical_rel` (follow_symlinks=True) + stamp `node_identity_version = "v1"`.
   - Update `BarrelChainResolution` and index helpers.
5. Extend harness `run_barrel_invalidation_proof` (and a new `run_barrel_invalidation_scale_proof`) with:
   - Symlinked barrel layout.
   - Deleted leaf barrel.
   - Deep overlapping (A→B→C, D→B→C).
   - Assert structured return shape (once added).
6. Wire the new behavior into `--gap1-health`.

**Deliverable**: "edit barrel → only affected importers re-analyzed" is now the normal cheap path. Full-repo work only on `--full`.

### Wave 2 — Structured Observability & Diagnostics (1 week)
1. Introduce `BarrelInvalidationReport` (light dataclass or TypedDict in bree.py or contracts).
2. Change `get_affected_importers` / `invalidate...` to support rich mode (or new `get_barrel_invalidation_report(changed_files, root) → List[Report]`).
3. In sh: when DEBUG, print the full "Barrel X (mtime=...) touched → importers Y (via chains C1, detector=Z, partial=...)" for every augmentation.
4. Surface in `diagnostics.py` (new category `barrel_invalidation`), MCP tools (`get_files_needing_attention` or dedicated), library.md summary section, and journal entries.
5. Update contracts + `RESERVED_TOP_LEVEL_KEYS` if an aggregate `_barrel_invalidation_log` is desired (optional; start with per-run).

**Deliverable**: Agents can answer "why was this file re-parsed?" with concrete barrel evidence.

### Wave 3 — Daemon & check-changes Integration (1 week)
1. In `cmd_check_changes` (sh): after the direct `-newermt` pass, run a tiny python snippet:
   ```python
   changed = [...]  # from the find
   stale = ic.invalidate_stale_barrel_entries(..., changed_files=changed)  # or the report form
   for rel in stale: upsert_health(..., "🟡 Yellow", f"stale via barrel re-export: {reasons}")
   ```
2. This makes the background `monitor` / daemon loop automatically surface transitive barrel staleness in `pending_updates.md` and the health matrix — without requiring a manual `update-maps`.
3. Add daemon CLI flag or env to enable/disable the barrel-delta pass (default on).
4. Ensure the BRC load is cheap and graceful when cache is absent or empty.

**Deliverable**: True "set & forget" for barrel edits under long-running daemon.

### Wave 4 — Lifecycle, Pruning, Stress & v2 (2–3 weeks)
1. Pruning/GC:
   - On `record-deletion <file>`, or opportunistically in persist, remove any BRC entries whose `barrel_chain` or importers mention the deleted path.
   - Optional `brc.prune(max_age_days=90, max_entries=5000)` called on `--full` or explicit `wikifier gc-barrels`.
2. Node identity migration helper (when v2 appears): one-time scan + rewrite of old v0 chains using current canonicalizer.
3. Policy hook: `ExpansionPolicy` gains `force_full_on_stale_partial=True` (default); affected importers of a partial stale chain always attempt a non-partial re-expansion.
4. Large-scale harness additions: 10k–50k synthetic barrel fanout graphs; timed invalidation assertions (<100 ms); real external monorepo with symlinked packages + pnpm workspace.
5. Performance & size metrics published in health matrix and `gap1_validation_harness` report.

**Deliverable**: Battle-tested at the 50k target with full lifecycle hygiene.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Canonical path mismatch on symlinked monorepos causes missed or duplicate invalidations | Medium | High (silent correctness bug) | Wave 1 enforcement + harness symlink case + dogfood on real pnpm/yarn layout before Wave 4 |
| BRC JSON bloat from thousands of fine-grained partial chains | Low–Medium | Medium (slow load, disk) | Wave 4 pruning + per-barrel cap in index + age-based GC |
| Concurrent daemon + manual update-maps race on BRC writes | Low (locking exists) | Medium | Existing `locking.file_lock`; add explicit BRC-level merge on load if needed |
| Partial-chain stale semantics cause either over-reparse or missed updates | Low | Medium | Explicit policy + harness coverage of partials in Wave 1 |
| Agents rely on "why" before Wave 2 → poor debuggability | Medium | Low | Document current list-only return as transitional; accelerate Wave 2 |
| Sh duplication (root vs scripts/) causes one path to lag | Ongoing | Low | Treat scripts/ as source; sync script or build step already present |
| Future central resolution changes break importer_rel or resolved paths | Low | Medium | All paths go through documented `to_canonical_rel`; BRC stores the versioned form |

Overall risk posture: **Low**. The data structures and reverse index already provide the necessary information; the work is primarily refactoring call sites, adding normalization, and extending observability.

---

## Immediate Next Steps (Actionable Checklist)

1. **This document** is the authoritative long-term reference. Link it from the progress tracker and from `Findings/gap1_dependency_intelligence_4phase_roadmap_open.md` Phase 2 section.
2. Update `Findings/m2_rem_08_and_v0.4_progress_tracker.md`:
   - Add "Deep Barrel Invalidation — Long-Term Strategy" milestone with the four waves.
   - Mark current wiring as "Foundation complete (Wave 0)".
3. **Wave 1 kickoff**:
   - Primary owner: import_cache.py + bree.py (invalidate refactor + is_stale fix + canonical helper).
   - Secondary: wikifier/scripts/wikifier.sh (and root copy) call-site + debug logging.
   - javascript.py (importer_rel normalization).
   - gap1_validation_harness.py (new test cases).
   - resolution.py (export a convenience `canonical_for_bree` if useful).
4. Run full `--gap1-health` and a real-monorepo `update-maps --full` + targeted barrel edit before/after to generate before/after metrics.
5. After Wave 1 green: publish short "Barrel Invalidation is Now O(changed)" note in CHANGELOG and journal.
6. Schedule Wave 2 review with agent-protocol / MCP owners for observability surface.

---

**Conclusion**

With the BRC foundation, mtimes_snapshot + reverse file_index, and recent production wiring already in place, the remaining distance to a world-class, scale-proof, zero-dep barrel invalidation primitive is short and well-scoped. Executing the four waves will turn the current "working proof" into the reliable, cheap, explainable primitive that autonomous agents and large creative monorepos can depend on for years.

"Edit a barrel → only the real affected importers are re-analyzed" will be boring, fast, and correct — exactly what a production-grade dependency intelligence system should deliver.

---

*End of Long-Term Strategy Document*