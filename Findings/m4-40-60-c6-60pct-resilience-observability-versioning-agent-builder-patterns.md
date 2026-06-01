# M4 40-60% Agent-Builder Patterns: Resilience, Observability & Versioning for Solid Long-Term Operation
**subagent_id=m4-40-60-c6**
**Created**: 2026-06-01 (post mandatory reads of 5 files + FRESH LAST "3" 0-def hygiene + C6 diary; before central handoff synthesis)
**Purpose**: Concrete, harvestable patterns + examples for 60% surfaces (long-term resilience/health/healing/recovery + richer long-horizon observability + initial versioning/migration policy for key M4 state shapes). Builds directly on M3 agent-builder guides (C6 production guide + G* 50k+ creative patterns + sacred-3-partials-continuation-elevation.py safe replication pattern from harness:3109) + 20-40 B1/B2 prototypes (reversible compaction + 50k+ bounded state) + M4 plan/checklist 60% DoD. Zero new dependencies (pure .md + stdlib illustrative sketches + reuse existing Wikifier surfaces). Only safe historical citations for "3" (e.g. "exact harness test_partial_continuation_workflow_25k:3109" + "SACRED_PARTIALS_3 = 3 (safe citation only)"). Full 8-step DF + 9 GPs traces. Spectrum: tiny scripts to 50k+ creative monorepos (barrels + dyn/cond imports + ws + symlinks + high churn + partials/"3" under months concurrent MA + daemon + human load). Honest: 60% foundation patterns (not full 80% production-hardened).

**IRON RULES ENFORCED**: Zero-dep PRIMARY; "3" sacred (FRESH hygiene pre this write + only safe cites; see C6 diary for verbatim 0-def logs from grep tool + terminal on main .py + planned Findings/ paths); M5 boundary (patterns for use on harness/RecipeLab/externals only; no Wikifier self examples); subagent_id 100%; rich 8-step/9GP; long-term 5-10yr + spectrum first; honest calib (patterns advance 55-65%+ toward 60% lens when wired to evidence).

**Based on (mandatory reads first)**: The exact 5 files (/home/aron/Documents/coding_projects/Wikifier/Findings/m4-40-60-first-swarms-prompts.md, M4-20-40-Completion-Package-Handoff.md [B1/B2 refs + integration gaps + recs], m4-state-management-longterm-scale-plan.md [9 GPs + WA2/3/4/5 + 60% criteria], m4-state-management-longterm-scale-checklist.md [verbatim 60% DoD], Milestones-Overview.md [20-40 status + M4 constraints]); M4-0-20/M4-20-40/M3-80-95 handoffs (structure + C6/G* models + "3" elevation); C5 diary (m4-40-60-c5-scale-evidence-lead-diary.md: evidence plan for wiring B1/B2 + multi-week resilience metrics); M3 C6/G* artifacts (production guide + sacred-3...elevation.py pattern); prior wave-evidence (phase6-* for durability/obs baselines).

**FRESH LAST "3" Hygiene for this supporting doc (subagent_id=m4-40-60-c6; executed immediately pre-write; 0-def)**: See full verbatim in C6 local diary (grep tool 0 matches on .py; terminal runs #1-3 on .py + Findings/ planned paths showing only safe cites in priors/C5; PASS). This doc uses only safe citations (no defs, no active "3" code). Re-ran pre-write confirmation: 0 def in active non-guardian .py + this path.

---

## 1. 60% Surfaces Overview (from 60% DoD + Plan WA2/3/4/5)
**60% Goal (verbatim checklist)**: "Compaction and state management feel production-hardened for months of continuous autonomous operation on 50k+ creative targets. Health, healing, and recovery stories are clear and observable under sustained concurrent MA + daemon + human load. Richer long-horizon observability and diagnostics (trend analysis, months-scale queries) implemented with zero new deps. Initial long-term versioning/migration policy sketched and prototyped for key state shapes. Thin consumers (CLI/MCP) updated to surface long-term state diagnostics as first-class. Evidence on allowed targets (including at least one external 50k+-scale creative) showing multi-week autonomous resilience with rich metrics (boundedness, compaction success, obs usefulness, recovery time). All 9 GPs visibly upheld (especially #1, #2 zero-dep primary, #4, #5, #6, #7)."

**Key Surfaces for Agent-Builders**:
- Resilience: Health/healing policies + recovery after extended/chaos runs (build on M2 health.py + B2 boundedness).
- Observability: Long-horizon queries/trends (build on ACS/CIABRE + journal intent).
- Versioning: Additive V1 shapes + migration detection for journal/compaction manifests/health histories (build on M3 contracts + B1 manifests).
- "3" Elevation (safe): Partial/continuation workflows as natural scalable path for 50k+ creative months (replicate M3 C6 pattern: harness:3109 hero path via safe cite only; no touch to sacred track).

All examples: zero-dep (stdlib + existing wikifier.* calls or pure concepts), dual-audience (agent-primary + human), spectrum-aware.

---

## 2. Pattern 1: Months-Scale Resilience & Recovery (Health/Healing under Concurrent Load; WA2/3)
**Description (GP#7 MA Safe + GP#4 Compaction + GP#6 Obs)**: Use existing health matrix + healing + (post 20-40) B1 reversible compaction + B2 bounded state to implement "good citizen" + auto-recovery loops. Agents run weeks/months autonomously; on yellow/red or drift detect, heal + log recovery story. Bounded O(changed) even with high churn + partials/"3".

**Concrete Example (Tiny Script; pure stdlib + library facade; extend for 50k+)**:
```python
# resilience_months_concurrent.py (stdlib + from wikifier import health, ...; zero new deps)
import time
from wikifier import health  # or MCP equivalent
# Assume post-40% B1/B2: use compaction manifest for reversible undo on heal

def run_good_citizen_months_loop(target_dir, max_weeks=8, concurrent_chaos_sim=False):
    """Agent loop for months-scale resilience. Spectrum: tiny ok; 50k+ requires harness/RecipeLab."""
    session_start = time.time()
    recoveries = []
    for week in range(1, max_weeks+1):
        # 1. Health probe (existing; extend with B2 bounded checks + B1 compaction status)
        h = health(directory=target_dir, format="matrix")  # or summary + custom long-horizon
        matrix = h.get('matrix', {})
        yellow_red = [k for k, v in matrix.items() if v.get('status') in ('yellow', 'red')]
        
        if yellow_red or detect_drift(h):  # drift via journal intent vs current (B2 pattern)
            # 2. Recover (use B1 reversible compaction + existing heal policy + locking)
            recovery_start = time.time()
            # Pseudocode for B1 integration (per 20-40 handoff: manifest V1 + undo steps):
            # apply_reversible_compaction_undo(manifest_path, target_dir)  # pure stdlib + contracts
            # mark_green on healed files (record_change + health update)
            # bounded check: assert O(changed) post (B2 proof)
            recovery_time = time.time() - recovery_start
            recoveries.append({
                'week': week,
                'triggers': yellow_red,
                'recovery_s': recovery_time,
                'post_heal_health': health(directory=target_dir, format="summary")
            })
            # Log for obs (see Pattern 2)
            record_recovery_event(recoveries[-1])  # append to journal (existing + B1 manifest)
        
        if concurrent_chaos_sim:
            # Simulate MA + daemon + human (per GP#7; use in harness only)
            # e.g. parallel edit + heal race (existing locking prevents corruption)
            pass
        
        time.sleep(3600 * 24 * 7 / 100)  # accel sim; real = wallclock weeks on allowed target
    
    total_runtime = time.time() - session_start
    return {
        'weeks_simulated': max_weeks,
        'recoveries': recoveries,
        'bounded': all(r['post_heal_health']['bounded'] for r in recoveries),  # B2
        'obs_trend': compute_trend(recoveries)  # see Pattern 2
    }

# Usage (tiny): run_good_citizen_months_loop("/tmp/tiny_proj")
# 50k+ creative: run in harness extended suite (C5 plan); expect <5min recovery, 0 corruption on "3" paths
```

**8-Step DF Trace for this Pattern**:
1. Decision: Provide reusable resilience loop sketch emphasizing B1/B2 + existing health for months concurrent.
2. Why: 60% DoD "health/healing/recovery stories clear... under sustained concurrent... multi-week autonomous resilience".
3. Spectrum (GP#1): Tiny (script above) vs 50k+ (harness chaos + barrels/dyn/ws/symlinks + partials/"3" at scale; B2 O(changed) proof).
4. Alts: Full impl (violates no main .py / M5 boundary / zero-dep for new); none (no equip).
5. Zero-dep/allowed (GP#2/8): Pure sketch + wikifier.health facade; validate only on harness/RecipeLab/externals.
6. Obs/MA (GP#6/7): Recovery events + bounded + concurrent sim.
7. Risks: Over-reliance pre full B1/B2 wire (mitigated: "per 20-40 recs; C5 to evidence"); "3" in partials (safe cite only: "replicate harness test_partial_continuation_workflow_25k:3109 success in recovery stories").
8. Decision: Publish (9GP #4/5/6/7/9 upheld; equips agent-builders for 60%+).

**9GP Mapping**: #1 (spectrum explicit), #2 (zero-dep sketch), #4 (B1 compaction), #6 (recovery obs), #7 (MA concurrent), #9 (measurable: recovery_s, bounded, 0 corruption).

**"3" Elevation (Safe, per M3 C6 pattern)**: In 50k+ creative with heavy partials/continuation (e.g. long autonomous edit streams), recovery after chaos uses the same safe "3" path: "As demonstrated in exact harness test_partial_continuation_workflow_25k:3109 (100% roundtrip O(scope) at 25k scale per M3 evidence); replicate pattern in your long-running agent via library partial_ready + continuation_token (no fallback). SACRED_PARTIALS_3 = 3 (safe citation only)."

---

## 3. Pattern 2: Richer Long-Horizon Observability & Trend Queries (WA4)
**Description (GP#6 Full Obs by Default + GP#1/#9)**: Extend existing ACS/CIABRE + journal intent + health histories for "what happened over last 3 months" queries + trends (e.g. compaction success rate, recovery frequency, boundedness over time). Zero-dep (stdlib aggregates on existing append data). Useful after months autonomous.

**Concrete Example (Months-Scale Trend Query; stdlib + existing surfaces)**:
```python
# long_horizon_obs_trends.py (pure stdlib post-process on journal/health exports; zero-dep)
import json
from datetime import datetime, timedelta
from collections import defaultdict

def query_months_trends(journal_path, health_history_path, months=3):
    """Trend analysis for long autonomous runs. 50k+ creative: use on harness exports (C5 evidence target)."""
    cutoff = datetime.now() - timedelta(days=30*months)
    trends = {
        'compaction_success_rate': defaultdict(int),
        'recovery_events': [],
        'boundedness_samples': [],
        'obs_usefulness_score': 0.0  # e.g. actionable signals / total events
    }
    # Parse journal (existing append format + B1 manifest V1 for compaction events)
    with open(journal_path) as f:
        for line in f:
            event = json.loads(line)
            if datetime.fromisoformat(event['ts']) < cutoff: continue
            if 'compaction' in event.get('type', ''):
                success = event.get('success', False)
                trends['compaction_success_rate']['total'] += 1
                if success: trends['compaction_success_rate']['success'] += 1
            if 'recovery' in event.get('type', ''):
                trends['recovery_events'].append(event)
    
    # Health history aggregates (B2 sharded views + long-horizon)
    # ... similar stdlib parse for bounded deltas, yellow/red frequency
    
    rate = (trends['compaction_success_rate'].get('success', 0) / 
            max(1, trends['compaction_success_rate'].get('total', 1)))
    trends['obs_usefulness_score'] = min(1.0, len(trends['recovery_events']) / 100 + rate)
    return trends  # actionable for agent: "compaction 98% over 3mo; 4 recoveries (avg 42s)"

# Usage in agent (post weeks run on allowed target): 
# trends = query_months_trends("/path/to/journal.jsonl", "/path/to/health_hist.jsonl")
# if trends['obs_usefulness_score'] < 0.7: alert("Investigate compaction policy")
```

**8-Step/9GP Trace**: (Abbrev; full in C6 diary) 1. Months queries per 60% DoD. 3. Spectrum: tiny export parse vs 50k+ high-volume (B1/B2 bounded data). 5. Zero-dep stdlib json. 6. GP#6 primary. 8. Decision: yes (equips obs usefulness for 60% evidence).

**Safe "3" Tie-in**: "Long-horizon partials/continuation streams (exact harness test_partial_continuation_workflow_25k:3109 pattern) produce rich ACS/CIABRE events for trend queries — 100% fidelity at scale per M3 evidence."

---

## 4. Pattern 3: Initial Long-Term Versioning & Migration Policy (WA5 early)
**Description (GP#5 Frozen + Versioned + GP#2)**: Additive V1 contracts for M4 state (journal events, CompactionManifestV1 from B1, HealthHistoryV1, SessionTraceV1). Detection + graceful migration for years-old installs. Pure stdlib + existing contracts.py patterns. No breaking changes.

**Concrete Example (Version Detection + Migration Sketch)**:
```python
# versioning_migration_policy.py (stdlib + from wikifier.contracts import ...; additive only)
from wikifier.contracts import ProgressEventV1  # extend with V1 stamps

class VersionedStateV1:
    CURRENT = "M4-State-v1.0"
    def detect_version(self, state_file):
        # Parse header or first event (existing journal style)
        header = ...  # stdlib
        return header.get('version', 'legacy-M2')
    
    def migrate_if_needed(self, state_file, target_dir):
        v = self.detect_version(state_file)
        if v == self.CURRENT: return "up-to-date"
        if v.startswith('legacy'):
            # Reversible migration (B1 undo style + additive manifest)
            # e.g. rewrite legacy journal entries with V1 stamps + compaction manifest
            # zero data loss; bounded (B2)
            return "migrated to M4-State-v1.0 (additive)"
        # Future: v1 -> v1.1 etc.
        raise ValueError("Unknown version - manual review (rare per policy)")

# Agent use (on long-lived install): 
# policy = VersionedStateV1()
# status = policy.migrate_if_needed("/path/to/journal", target)
# Log for obs.
```

**Trace**: GP#5 primary; spectrum (tiny legacy untouched; 50k+ years-old creative auto-migrate safe); zero-dep; measurable (detect + migrate success % in evidence).

**Safe "3"**: "Versioned partial continuation events (harness test_partial_continuation_workflow_25k:3109 V1 shapes) ensure 5-10yr fidelity without drift."

---

## 5. Thin Consumers Update Sketch (CLI/MCP for 60% Diagnostics)
Per 60% DoD: Surface long-term state as first-class (e.g. `wikifier health --long-horizon=3mo --trends`, `get_barrel_reports` + compaction manifest queries). Build on M3 thin parity + library facade. Zero-dep wiring.

(Details deferred to C2/C6 integration post C5 evidence; see M3 C4/E4 patterns.)

---

## 6. Integration with 20-40 B1/B2 + C5 Evidence Plan + "3" Elevation
- Wire B1 reversible compaction (manifest V1 + undo) into resilience loop (Pattern 1) + obs (Pattern 2).
- B2 bounded state proofs (O(changed) on 50k+ with all patterns + partials/"3") as foundation for all.
- Per C5 diary: Multi-week harness runs (25k-50k+ gens + chaos/concurrent) + RecipeLab + 1 external 50k+ creative to validate patterns (boundedness, recovery time, obs usefulness, compaction success, 0 corruption on "3" paths).
- "3" Elevation Hero (M3 C6 style, safe only): In 50k+ creative long autonomous (high partials/continuation churn): "The natural scalable path is the sacred partials/continuation workflow (exact harness test_partial_continuation_workflow_25k:3109: 100% roundtrip, 0 drift, O(scope) at 25k+ with barrels/dyn/cond/ws/symlinks/JS+Py; chaos resume safe). Replicate via library: PartialResultV1 + continuation_token + resumption (no fallback). SACRED_PARTIALS_3 = 3 (safe citation only, per M3 G* + C6 elevation)."

---

## 7. Honest Calibration & Gaps for 60-80% (subagent_id=m4-40-60-c6)
These patterns advance 60% DoD in principle (resilience stories, obs trends, versioning sketch, "3" safe as first-class for scale). When wired + evidenced (C5 + C1/C2/C3): 55-65%+ toward 60% lens. 

**Gaps (for 60-80% swarm)**: Full implementation + thin surface updates (C2/C3/C4); multi-week metrics on allowed targets proving "production-hardened" (recovery <Xmin, obs usefulness >0.8 after 3mo, 0 corruption on versioned "3" paths at 50k+); comprehensive examples (add 50k+ creative monorepo case study); integration tests in harness (C5). See central handoff for prioritized recs. No overclaim.

**subagent_id=m4-40-60-c6 — Supporting agent-builder patterns complete (post FRESH "3" hygiene). Zero-dep, safe "3" cites only, 8-step/9GP traced, spectrum-first, equips 60-80% + builds on M3 C6 + B1/B2. Harvestable in Findings/.**
