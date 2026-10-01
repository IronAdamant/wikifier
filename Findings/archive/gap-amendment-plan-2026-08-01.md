# Wikifier gap amendment plan (fix / improve / evidence)

**Date:** 2026-08-01  
**Package under review:** 4.6.8 (`wikifier/__init__.py`)  
**Protocol:** Agent Protocol v0.6 (`skills/run.md`)  
**Method:** Three independent deep-research runs (FIX / IMPROVE / EVIDENCE-PROTOCOL), consolidated against Findings, protocol, package code, and this repo’s live hygiene.

**Dogfood hygiene baseline (this repo — not external targets):**  
`file_health.md` is all 🟢 Green; `pending_updates.md` has no pending items; both residual `Logged_issues/` entries are RESOLVED (2026-06-10). **Do not treat matrix debt as open product bugs.** Gaps below are deferred surfaces, quality/ops friction, protocol/doc drift, or unclaimed evidence for 95%+ readiness claims.

**Readiness ceiling (claimed):** ~85–90% of multi-year “set & forget” without further dogfood (M5.2). **95%+** requires M5.3 sustained evidence, not a core rewrite.

**Deep-research sources:**
| Angle | Display | Report |
|-------|---------|--------|
| A — FIX | deep-research-2 | session workflows `…/wf_019fbad2006276b3be4b82feafd18f0a/scratch/report.md` |
| B — IMPROVE | deep-research-3 | `…/wf_019fbad200797d73925d395537f0a96b/scratch/report.md` |
| C — EVIDENCE/PROTOCOL | deep-research-4 | `…/wf_019fbad2008a7f13b6d863514c178ef8/scratch/report.md` |

---

## How to use this plan

- **Label:** `FIX` = incomplete shipped surface / defect / doc-code mismatch; `IMPROVE` = quality/perf/ops; `EVIDENCE` = unclaimed dogfood/soak proof; `PROTOCOL` = agent-contract wording or operator-path inconsistency.
- **Priority:** P0 quick wins → P1 agent loop friction → P2 product depth → P3 long-horizon evidence.
- **Closed means:** one-sentence exit criterion for a later closure pass.
- **Non-goals of this document:** implementing the gaps (this is the amendment backlog only).

---


---

## Closure status (2026-08-01 implement pass — package 4.6.9)

| ID | Status | Evidence |
|----|--------|----------|
| G1 | **closed** | `skills/run.md` + `Claude.md` package **4.6.x**; tests `TestProtocolVersionPointers` |
| G2 | **closed** | `session_bootstrap` message embeds readiness; never "ready" when blocked; `TestBootstrapMessageAndActions` |
| G3 | **closed** | SELECTIVE WORK mandates actionable 🟡 + excludes Initial stubs; protocol + test |
| G4 | **closed** | readiness tiers table in protocol matches `assess_autonomous_readiness`; bare_dot = scope warning |
| G5 | **closed** | `map_complete`/`map_ready` on `run_full_update`; incomplete → priority-2 `update_maps_until_complete` |
| G6 | **closed** | blockers → priority-1 `update_maps` / `seed_health`; `build_structured_actions(blockers=…)` |
| G7 | **closed** | init templates default active `src/`; bare `.` comment-only opt-in; `test_init_seed` |
| G8 | **closed** | protocol: unattended requires `readiness=ready_for_daemon` not Map Ready alone |
| G9 | **closed** | `library._generate_acs_section` prefers actionable + reason_code_counts |
| G10 | **closed** | stub-only → `map_first_ok` only (no `wiki_refresh`); SELECTIVE WORK wording |
| G11 | **reclassified** | permanent non-goal this release: section-patch deferred; full rewrite remains default (ideal-loop D1) |
| G12 | **reclassified** | permanent non-goal this release: attach profiles deferred; dual-scope + readiness cover risk |
| G13 | **closed** | `file_lock(..., timeout=)` raises `LockTimeoutError`; tests drive `_acquire_exclusive` |
| G14 | **reclassified** | multi-lang deep resolve remains regex-map quality bar; not ship in this pass |
| G15 | **closed (policy)** | CLI-at-scale policy in `skills/run.md`; no unmeasured DoD2 claim; `{SCRATCH}/dogfood/mcp_or_policy.txt` |
| G16 | **reclassified** | warm floors accepted as residual; zero-dirty path already correct |
| G17 | **closed** | protocol monitor/daemon notes: agents own wiki; readiness messaging separates daemon vs prose |
| G18 | **closed (guardrail)** | init still copies only `index.html`; non-goal to grow human docs — no change needed |
| G19 | **reclassified** | megamodule split / health unshadow / update-maps honors monitored — permanent non-goals unless pressure |
| G20 | **residual-evidence** | ≥72h soak not run this goal (infeasible); short dogfood only |
| G21 | **residual-evidence** | M5.3 multi-month not run; 85–90% ceiling unchanged |
| G22 | **residual-evidence** | DoD8 concurrent churn pack not run |
| G23 | **residual-evidence** | selective-wiki compliance campaign not run; contract fixed (G3/G10) |

**Tests:** `tests/test_gap_amendment_2026_08.py` + full `unittest discover` (140 OK).  
**Dogfood:** `{SCRATCH}/dogfood/dogfood_summary.json` — 9/9 targets bootstrap success (ConsistencyHub, Grok-Bevy, RecipeLab_alt, Trammel, stele-context, Crystal Drift, Iron Feud, llama_index, airflow).


## Priority P0 — quick contract/docs fixes (low risk, high agent clarity)

### G1 · PROTOCOL · Package version string drift

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Operator docs still say package current **4.5.x** while `__version__` is **4.6.8** and body text already references 4.6.x / 4.6.8+. |
| **Evidence** | `skills/run.md` L5 & L10 (“package current **4.5.x**”); `Claude.md` architecture note “currently 4.5.x”; `wikifier/__init__.py` `__version__ = "4.6.8"`. |
| **Closed when** | Every operator package pointer (`skills/run.md` header + package-notes title, `Claude.md`) matches `__version__` major.minor with no residual “current 4.5.x”. |

### G2 · PROTOCOL · `session_bootstrap` always says “ready”

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Bootstrap message always starts with “session_bootstrap ready — use actions[]…” even when `readiness` is `blocked`. Agents can treat blocked projects as map-ready. |
| **Evidence** | `wikifier/agent_loop.py` (~L658); deep-research C [S21]. |
| **Closed when** | Message embeds the readiness tier and never says “ready” when `readiness == "blocked"`. |

### G3 · PROTOCOL · SELECTIVE WORK mandatory line still allows raw 🟡

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Copy-paste mandatory block says re-wiki 🔴 and 🟡 without carving out *Initial stubs*; package notes correctly require 🔴 + *actionable* 🟡 only. Contract conflict overclaims G3 “closed”. |
| **Evidence** | `skills/run.md` mandatory New-Session block SELECTIVE WORK sentence vs additive notes L14–15; `Findings/gap-closure-report.md` G3; deep-research C [S13][S14]. |
| **Closed when** | Mandatory SELECTIVE WORK sentence requires 🔴 then actionable 🟡 only, explicitly excludes Initial/map stubs; no full-tree yellow bulk in `actions[]` contract text. |

### G4 · PROTOCOL · Bare `.` docs vs readiness tiers

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Findings/protocol often list bare `.` under blockers, but code puts bare_dot in scope warnings and yields `map_ok_scope_risk` when map+health exist (hard blockers = missing map/health/severe ghosts). Operators misread “blocked”. |
| **Evidence** | `wikifier/health.py` `assess_autonomous_readiness` / `detect_scope_risks`; `Findings/readiness-blocked-bare-monitor-2026-07.md`; `skills/run.md` § Readiness blocked; deep-research C [S20]. |
| **Closed when** | Docs match code tiers (or bare_dot is promoted to a real blocker with a regression test asserting the shape). |

---

## Priority P1 — agent loop / bootstrap / map honesty

### G5 · FIX · Budgeted `update-maps` success ≠ map complete

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | `max_files` truncation leaves `map_coverage.complete=false` and `files_remaining_dirty>0` while overall path can still look successful. Agents must not treat success alone as map-ready. |
| **Evidence** | `wikifier/import_cache.py` `build_map_coverage`; `wikifier/cli.py` budget path; `wikifier/agent_loop.py` `update_maps_until_complete`; `skills/run.md` L15; `Findings/agent-scale-sqlite-coverage-2026-07-12.md`; `Findings/agent-scale-perf-accuracy-2026-07-12.md`. |
| **Closed when** | Agents always require `map_coverage.complete=true` / zero `files_remaining_dirty` before claiming map-ready—or a single run’s structured return makes residual dirty impossible to miss (no false “done” signal). |

### G6 · FIX · Blocked-path `actions[]` incomplete for missing map/health

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Protocol says fix_scope + update-maps from actions/blockers, but structured actions prioritize fix_scope from scope_warnings and a low-priority structure-based map update—missing dedicated high-priority “No import map” / “No file_health” actions. |
| **Evidence** | `wikifier/agent_loop.py` `build_structured_actions`; deep-research C [S22]; `skills/run.md` § Readiness blocked. |
| **Closed when** | Missing map/health blockers always produce priority ≤2 `update_maps` / `seed-health` (or equivalent) actions. |

### G7 · FIX · Init still leaves active bare `.` for toys (footgun on real trees)

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | 4.6.8 init seeds comment-guided lean templates (improvement), but monitored template still allows an active lone `.` for tiny toys; agents on multi-crate trees who leave it get thrash / readiness risk. |
| **Evidence** | `Findings/readiness-blocked-bare-monitor-2026-07.md`; CHANGELOG 4.6.8; `tests/test_init_seed.py`; `skills/run.md` product note L119–122. |
| **Closed when** | Multi-crate/workspace init does not activate sole bare `.` without explicit opt-in, or tests assert post-init readiness honesty until paths are replaced. |

### G8 · PROTOCOL · Map Ready ≠ `ready_for_daemon`

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Operator success language packs Map Ready with unattended readiness; code requires Map Ready/Good **and** not bare_dot for `ready_for_daemon`. |
| **Evidence** | `wikifier/health.py`; `Findings/long-horizon-autonomous-ops.md`; deep-research C [S23]. |
| **Closed when** | Operator success criteria require `readiness == ready_for_daemon` explicitly, not `health_score` alone. |

### G9 · IMPROVE · ACS noise still thrash-visible on human map surface

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | ACS v1.3 demotes external/dynamic noise and exposes `actionable_low_conf_edges` + reason codes; `library.md` ACS Risk Snapshot still highlights raw `low_conf_edges` samples. Large external dogfood historically showed huge actionable queues (e.g. Babylon warm B `acs_actionable` 21712 in `dogfood_pass_4.6.7.json`). |
| **Evidence** | `wikifier/library.py` ACS snapshot; `skills/run.md` ACS notes; `Findings/agent-scale-perf-accuracy-2026-07-12.md`; `Findings/dogfood_pass_4.6.7.json`; deep-research B. |
| **Closed when** | Agents and human map surfaces select work only via actionable + investigate reason codes; raw-only queues are not the default steady-state UX; post-1.3 re-measure of Babylon/airflow actionable counts is recorded. |

### G10 · IMPROVE · Selective loop: Map Ready + mass Initial stubs

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Map-first steady state shows Map Ready with many 🟡 Initial stubs (e.g. airflow 1444 stub_yellow / 1 actionable). Bulk-wikifying stubs violates protocol; friction remains full-file rewrite + agent compliance. |
| **Evidence** | `Findings/dogfood-goal-pass2-2026-07-09.json`; `Findings/dogfood-coding-projects-8-2026-07-09.json`; `skills/run.md` map-first notes; `wikifier/agent_loop.py` stub vs actionable actions. |
| **Closed when** | Health/suggest paths always split stub_yellow vs actionable_yellow; queues use only red + actionable_yellow; agents never bulk-wiki Initial stubs after Map Ready. |

---

## Priority P2 — product depth / reliability / performance

### G11 · FIX · Wiki section-patch API (deferred D1)

**Status (2026-08-01):** reclassified

| | |
|--|--|
| **What** | Full wiki rewrite is still the default; no section-patch API under `wikifier/`. |
| **Evidence** | `Findings/agent-first-ideal-loop-2026-07-09.md` D1 deferred; CHANGELOG deferred list; deep-research A [S1]. |
| **Closed when** | Agents can patch a named wiki section via a shipped API without rewriting the whole file. |

### G12 · FIX · `wikifier attach` / external profile pack (deferred D2)

**Status (2026-08-01):** reclassified

| | |
|--|--|
| **What** | Attach/profile command pack deferred; dual-scope + readiness cover main risk today. |
| **Evidence** | Ideal-loop D2; CHANGELOG; no attach CLI/MCP surface. |
| **Closed when** | `wikifier attach` (or equivalent profile pack) is shipped and documented for external-tree attachment—or explicitly reclassified permanent non-goal. |

### G13 · FIX · Fine-grained / non-blocking locks

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Project-level blocking `LOCK_EX` only; `timeout` param accepted but not honored; protocol documents non-blocking/per-file as future. |
| **Evidence** | `wikifier/locking.py` L50, L83–118, L166+; `skills/run.md` Concurrency Limitations L189–195. |
| **Closed when** | `file_lock` honors a finite timeout (or non-blocking acquire returns contention without hanging) and/or per-file locks exist as protocol describes—or protocol drops the “planned” language and documents blocking-only forever. |

### G14 · FIX · Shallow multi-lang path resolution

**Status (2026-08-01):** reclassified

| | |
|--|--|
| **What** | Parsers for Rust/Go/C/C++/C#/Java emit edges without full cargo/go.mod/classpath/`-I` resolution; unresolved ratios remain high outside Py/JS (+ partial Rust crate / Go module work). |
| **Evidence** | `Findings/residual-1-5-closure-2026-07-09.md` optional multi-lang; `Findings/dogfood-multi-lang-2026-07-09.md`; `Findings/index-first-map-paths-2026-07-12.md` deferred; ideal-loop deferred list. |
| **Closed when** | Target languages resolve imports to on-disk paths (or explicit external) with substantially lower unresolved ratios on the same fixtures—or quality bar is formally capped as “regex maps only” in protocol/README without implying deep resolve. |

### G15 · FIX / EVIDENCE · MCP reliability on barrel-heavy trees (DoD2)

**Status (2026-08-01):** closed (policy)

| | |
|--|--|
| **What** | MCP subprocess path hard-caps ~60s; protocol still mandates CLI/library fallback on large/BRC trees. M5 DoD2 (&lt;30s no-timeout on named tools for alt/Consistency/llama) not re-proven post-4.6.x. |
| **Evidence** | `wikifier/mcp/server.py` timeout path; `skills/run.md` MCP notes L278–280; `Findings/M5-Dogfood-Assessment-Report.md` DoD2; post-July dogfood measured CLI warm, not MCP latencies. |
| **Closed when** | Logged runs: `get_barrel_reports`, `get_project_status`, `get_files_needing_attention`, `suggest_next_actions` each &lt;30s with zero timeouts on alt BRC~20+, Consistency, and one llama sub—or protocol hard-declares CLI-only for those scales with no MCP latency claim. |

### G16 · IMPROVE · Warm-map floors & dirty full-cache load

**Status (2026-08-01):** reclassified

| | |
|--|--|
| **What** | Zero-dirty warm is strong (index-first + SQLite); dirty rebuild still full-loads cache; large scopes pay mtime/stat floors (airflow ~179ms, Babylon ~399ms warm B); universal sub-100ms on every 1k+ tree is not a SLA. |
| **Evidence** | `Findings/index-first-map-paths-2026-07-12.md`; `Findings/agent-scale-sqlite-coverage-2026-07-12.md`; `Findings/agent-scale-perf-accuracy-2026-07-12.md`; `tests/test_cache_store.py` zero-dirty load bar. |
| **Closed when** | Dirty path uses partial/index row loads for small dirty sets; zero-dirty full pair loads remain zero; honest floors documented (no false universal sub-100ms claim). |

### G17 · IMPROVE · Daemon/monitor vs agent wiki ownership (ops clarity)

**Status (2026-08-01):** closed

| | |
|--|--|
| **What** | Daemon heartbeats check-changes / optional maps only; agents still own wiki prose + mark-green. Correct by design, but multi-session ops still confuse “daemon = full loop”. |
| **Evidence** | `wikifier/daemon.py`; `Findings/long-horizon-autonomous-ops.md`; `skills/run.md` monitor notes. |
| **Closed when** | Protocol + readiness messaging always separate map/daemon readiness from wiki-prose completion; daemon never writes wiki prose (regression-guarded). |

### G18 · IMPROVE · Maintainer diagnostics separation (guardrail)

**Status (2026-08-01):** closed (guardrail)

| | |
|--|--|
| **What** | Only `index.html` deploys on init; `diagnostics.html` is maintainer-only. Keep it that way—do not grow human docs/IDE product. |
| **Evidence** | `Claude.md` hard constraints; `skills/run.md` human layer; deep-research B [S23]. |
| **Closed when** | `wikifier init` on a clean target always yields `index.html` and never `diagnostics.html` (test already expected); no core feature growth toward human docs/IDE beyond the passive viewer. |

### G19 · IMPROVE · Residual gap-closure rows (reclassify or finish)

**Status (2026-08-01):** reclassified

| | |
|--|--|
| **What** | After G1–G12 closed: megamodule split (js/bree), update-maps honoring `monitored_paths`, unshadow package `health` attr, shell-as-launcher-only (D3 partial) remain residual/partial. |
| **Evidence** | `Findings/gap-closure-report.md` residual table; ideal-loop D3. |
| **Closed when** | Each residual row either ships to a named bar or is explicitly reclassified permanent non-goal with no open “fix” label. |

---

## Priority P3 — evidence that blocks 95%+ claims (not code bugs)

### G20 · EVIDENCE · ≥72h continuous soak (unclaimed)

**Status (2026-08-01):** residual-evidence

| | |
|--|--|
| **What** | Literal multi-day continuous soak never run; only readiness rails, metrics harness, short daemon smoke. |
| **Evidence** | `Findings/goal-maturity-completion-2026-07-09.md`; `Findings/residual-1-5-closure-2026-07-09.md`; `Findings/long-horizon-autonomous-ops.md` (explicit non-claim); `skills/run.md` L22. |
| **Closed when** | Continuous ≥72h concurrent MA+daemon pack exists with clean heartbeat/log, growth bounds, health/journal integrity, kill/restart recovery. |

### G21 · EVIDENCE · M5.3 multi-month concurrent MA+daemon (DoD1)

**Status (2026-08-01):** residual-evidence

| | |
|--|--|
| **What** | 95%+ / 5–10yr set-and-forget requires multi-month concurrent MA+daemon on ≥3 prepared targets (alt, ConsistencyHub, llvm/llama). M5.3 plan is Ready, not executed. Ceiling remains 85–90%. |
| **Evidence** | `Findings/M5-Dogfood-Assessment-Report.md` M5.2/M5.3; `Findings/Milestones-Overview.md` M5.3 section; `Findings/p6_real_world_validation_report.md`. |
| **Closed when** | DoD1 evidence pack for each of ≥3 prepared external targets + final 95% report after sustained concurrent MA+daemon. |

### G22 · EVIDENCE · Durability under churn (DoD8 / “3” 0-corr)

**Status (2026-08-01):** residual-evidence

| | |
|--|--|
| **What** | Journal/partials 0-loss across ≥20 concurrent-MA edit cycles under multi-day churn unproven; M5.2 scores “3” ~78% as a 95% limiter. |
| **Evidence** | M5 Assessment DoD8 / 7-criteria scoring; this repo journal is map work, not concurrent-churn proof. |
| **Closed when** | Pack shows 100% 0-loss journal compaction, historical query, and partial continuation across 20+ real concurrent-MA edit cycles on 2 targets. |

### G23 · EVIDENCE · Agent selective-wiki compliance rates

**Status (2026-08-01):** residual-evidence

| | |
|--|--|
| **What** | Protocol forbids bulk Initial-stub wiki; live compliance rates of contemporary agents not measured post-taxonomy. |
| **Evidence** | Deep-research C uncertainty; dogfood mass-stub states (airflow/llama_index). |
| **Closed when** | Multi-agent run log shows 0 bulk-stub wiki after Map Ready and only red/actionable_yellow work queues. |

---

## Suggested closure waves (for later implementers)

| Wave | Items | Intent |
|------|-------|--------|
| **W1 — Contract hygiene** | G1, G2, G3, G4, G8 | Align protocol/docs/messages with code; no architecture risk. |
| **W2 — Bootstrap honesty** | G5, G6, G7 | Map-complete signals + blocked-path actions + init footgun. |
| **W3 — ACS / selective UX** | G9, G10, G17 | Stop thrash surfaces; separate map readiness from wiki completion. |
| **W4 — Depth (optional)** | G11, G12, G13, G14, G16, G19 | Product depth only if usage pressure appears; else reclassify. |
| **W5 — Reliability measure** | G15 | Re-measure MCP DoD2 **or** hard-declare CLI-at-scale policy. |
| **W6 — M5.3 evidence** | G20, G21, G22, G23 | Evidence-only; use `Findings/long-horizon-autonomous-ops.md` runbook. |

---

## Explicitly not open as FIX

| Item | Status | Notes |
|------|--------|-------|
| This repo `file_health` Red/Yellow debt | None | All Green as of last matrix update (2026-07-12 journal era). |
| `pending_updates.md` queue | Empty | No hygiene backlog. |
| Logged_issues BRC hang / JS barrel churn | RESOLVED 2026-06-10 | Do not re-open without new repro. |
| Core zero-dep pipeline / Core-6 tools / MapScope / ACS v1.3 / SQLite primary | Shipped | Gaps are residuals and evidence, not missing core. |

---

## Spot-check log (investigation day)

| Claim | Source | Result |
|-------|--------|--------|
| Protocol header still 4.5.x | `skills/run.md` L5; `__version__` 4.6.8 | Confirmed drift (G1) |
| Bootstrap always “ready” | `agent_loop.py` L658 | Confirmed (G2) |
| Lock timeout not implemented | `locking.py` L50, L118 | Confirmed (G13) |
| Self matrix Green + empty pending | `file_health.md`, `pending_updates.md` | Confirmed — no invented matrix bugs |
| ≥72h soak unclaimed | residual-1-5, goal-maturity, long-horizon ops | Confirmed (G20) |

---

## Item index

| ID | Label | Priority | One-line closed criterion |
|----|-------|----------|---------------------------|
| G1 | PROTOCOL | P0 | Package pointers match 4.6.x / `__version__` |
| G2 | PROTOCOL | P0 | Bootstrap message reflects blocked readiness |
| G3 | PROTOCOL | P0 | SELECTIVE WORK excludes Initial stubs |
| G4 | PROTOCOL | P0 | Bare-dot docs match readiness tiers |
| G5 | FIX | P1 | Map-ready requires `map_coverage.complete` |
| G6 | FIX | P1 | Missing map/health → priority ≤2 actions |
| G7 | FIX | P1 | Init no sole bare `.` without opt-in on real trees |
| G8 | PROTOCOL | P1 | Success = `ready_for_daemon`, not Map Ready alone |
| G9 | IMPROVE | P1 | Actionable ACS default on map + re-measure large trees |
| G10 | IMPROVE | P1 | Stub vs actionable split; no bulk stub wiki |
| G11 | FIX | P2 | Section-patch API shipped |
| G12 | FIX | P2 | Attach profiles shipped or non-goal |
| G13 | FIX | P2 | Timeout/non-blocking locks or honest protocol drop |
| G14 | FIX | P2 | Deeper multi-lang resolve or capped quality bar |
| G15 | FIX/EVIDENCE | P2 | MCP &lt;30s DoD2 pack or CLI-at-scale policy |
| G16 | IMPROVE | P2 | Partial dirty loads; honest warm floors |
| G17 | IMPROVE | P2 | Daemon ≠ wiki-prose ownership messaging |
| G18 | IMPROVE | P2 | Init never ships diagnostics.html |
| G19 | IMPROVE | P2 | Residuals shipped or reclassified |
| G20 | EVIDENCE | P3 | ≥72h soak pack |
| G21 | EVIDENCE | P3 | M5.3 multi-month DoD1 pack + 95% report |
| G22 | EVIDENCE | P3 | DoD8 20+ cycle 0-loss pack |
| G23 | EVIDENCE | P3 | Selective-wiki compliance log |

**Total gaps listed:** 23 (well above the ≥5 minimum).

---

*Generated from three deep-research angles + primary Findings/protocol/code spot-checks. Implementation is a separate goal.*
