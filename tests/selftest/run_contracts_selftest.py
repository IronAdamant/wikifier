"""Extracted self-test harness from wikifier/contracts.py (G12 agent navigability).

Run: python3 tests/selftest/run_contracts_selftest.py
Or:  python3 -m unittest tests.test_selftest_wrappers
"""
import sys
from pathlib import Path
# Ensure repo root on path when run as script
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from wikifier.contracts import *  # noqa: F403
from wikifier.contracts import __contracts_version__, STATUS

import sys

print(f"Wikifier Contracts {__contracts_version__} - {STATUS}")
print("Smoke test starting...")

# Dataclass roundtrip
trace = AnalysisTraceEntry("TestDetector", True, "foo.bar", 0.87, ["note1"])
ca = ConditionalAnalysis(True, ["feature_flag"], "if (featureFlags?.x)", ["FeatDetector"], [trace], 0.91, False)
da = DynamicAnalysis("expression", "high", ["computed_path"], "cond ? a : b", [], [], [], "m", ["def m=..."], 0.65, False)
rm = ResolutionMetadata("package-exports:./dist", "import", "./*", None, False, None, "@pkg/core", ["ts-paths", "exports"])

assert ca.is_conditional
assert "feature_flag" in ca.to_dict()["semantic_tags"]

# Serialization
packed = pack_cdia_v1(ca, da)
assert len(packed) > 10 and "=" not in packed
unpacked = unpack_cdia_v1(packed)
assert unpacked["conditional_analysis"]["is_conditional"] is True
assert unpacked["dynamic_analysis"]["dynamic_type"] == "expression"

# Legacy synthesis
leg = synthesize_conditional_from_legacy(True, "if (x)")
assert leg["degraded"] is True and "control_flow" in leg["semantic_tags"]

# Pipeline line parser
sample = "src/app.js|./utils|dist/utils.js|high|false|static|false||false||cdia_v1=eyJjb25kaXRpb25hbF9hbmFseXNpcyI6eyJpc19jb25kaXRpb25hbCI6ZmFsc2V9fQ==|res_meta_v1=eyJzdHJhdGVneSI6InRlc3QifQ=="
parsed = parse_pipeline_line(sample)
assert parsed["rich_payloads"]["cdia_v1"]
assert "res_meta_v1" in parsed["rich_payloads"]

# Decode failure tolerance
assert decode_v1_payload("!!!notbase64!!!") is None
assert decode_v1_payload("") is None

# Node identity
stamped = annotate_node_identity({"foo": 1})
assert get_node_identity_version(stamped) == NODE_IDENTITY_VERSION_V1
assert get_node_identity_version({}) == NODE_IDENTITY_VERSION_V0

# R2 ACS helper smoke (score parity + explanation quality + rich signals)
score, rs, expl = compute_acs_confidence(
    "high",
    is_conditional=True,
    conditional_analysis={"is_conditional": True, "semantic_tags": ["feature_flag"], "detectors_fired": ["FeatureFlagDetector"], "analysis_trace": [{"fired": True, "detector": "FeatureFlagDetector", "evidence": "featureFlags?.newUI"}]},
    resolution_metadata={"strategy": "package-exports:./dist"},
    strategy="package-exports:./dist",
)
assert 0.5 <= score <= 0.9
assert "base:high" in rs and any("tag:feature_flag" in r for r in rs)
assert "Base high" in expl and "feature_flag" in expl.lower() and "Recommendation:" in expl
assert "trace:" in expl or "detector" in expl.lower()  # evidence surfaced
# R2 maturity: no ugly duplication, strong strategy name surfaced, rec decision-ready
assert "barrel barrel" not in expl and "missing resolved" not in expl.lower()
assert "strong strategy" in expl or "strong resolution" in expl.lower()

score2, rs2, expl2 = compute_acs_confidence("low", in_cycle=True)
assert "cycle_participant" in rs2
assert "Cycle participant" in expl2 and "get_cycles" in expl2

# R2 deep barrel + via + clean high-fidelity cases (scale + monorepo realism)
s3, r3, e3 = compute_acs_confidence("medium", barrel_depth=4, via_barrel=True, resolved_path="x.js")
assert "deep barrel (depth=4)" in e3 and "via barrel re-export" in e3
assert "Recommendation:" in e3 and ("Deep barrel" in e3 or "barrel" in e3.split("Recommendation:")[-1])
assert "barrel barrel" not in e3  # regression guard

s4, r4, e4 = compute_acs_confidence("high", strategy="ts-paths:src", resolution_metadata={"strategy": "ts-paths:src"}, resolved_path="core.js")
assert "strong strategy 'ts-paths:src'" in e4 or "strong resolution" in e4.lower()
assert "High-fidelity" in e4 or "Safe for automated" in e4  # decision language

# ========== NEW M2 A0 shapes smoke (defensive roundtrips + factory + RESERVED) - Wave 3 finalized ==========
print("M2 A0 contracts smoke...")

scope = ScopeSpec_v1(directory="src/", focus_files=["core.ts"], transitive_closure=True, seed_reason="test-focus", resource_hints={"max_files": 500})
scope_d = scope.to_dict()
scope2 = ScopeSpec_v1.from_dict(scope_d)
assert scope2.directory == "src/"
assert "core.ts" in scope2.focus_files
assert scope2.version == "1.0"

run_id = "run-20260526-abc123"
ev = create_progress_event(
    "file_parsed",
    run_id,
    scope=scope,
    file="src/core.ts",
    progress_pct=12.5,
    provenance={"actor": "cli", "session_id": "sess-xyz"},
    acs_hook={"low_conf_delta": 1},
    barrel_signals={"depth": 2, "via_barrel": True},
    cycle_signals={"in_cycle": True, "scc_size": 4},
    checkpoint_token="after:src/core.ts:17",
)
assert ev["event_type"] == "file_parsed"
assert ev["run_id"] == run_id
assert ev["scope"]["directory"] == "src/"
assert ev["provenance"]["actor"] == "cli"
assert ev["barrel_signals"]["depth"] == 2
assert ev["cycle_signals"]["in_cycle"]
assert ev["checkpoint_token"] and ev["resumable"]
assert "acs_hook" in ev

ev2 = ProgressEvent_v1.from_dict(ev)
assert ev2.event_type == "file_parsed"
assert ev2.checkpoint_token == "after:src/core.ts:17"

run = UpdateRun_v1(run_id=run_id, started_at="2026-...", scope=scope_d, status="running", provenance={"actor": "mcp"})
run_d = run.to_dict()
run2 = UpdateRun_v1.from_dict(run_d)
assert run2.status == "running"

partial = PartialResult_v1(
    run_id=run_id,
    yielded_at="2026-...",
    scope_applied=scope_d,
    files_processed=42,
    acs_partial={"avg": 0.71},
    cycle_analyses_partial={"version": "1.3"},
    next_checkpoint_hint="after:src/core.ts:17",
)
p_d = partial.to_dict()
p2 = PartialResult_v1.from_dict(p_d)
assert p2.files_processed == 42 and p2.acs_partial and p2.next_checkpoint_hint

rev = ReverseDependencyIndex_v1(
    index={"dist/utils.js": ["src/core.ts", "src/app.ts"]},
    graph_signature="a1b2c3d4e5f6",
    provenance={"build_mode": "incremental", "reused": False},
    acs_tied=True,
    ciabre_blast_hints={"high_blast": ["dist/utils.js"]},
)
rev_d = rev.to_dict()
rev2 = ReverseDependencyIndex_v1.from_dict(rev_d)
assert "dist/utils.js" in rev2.index
assert rev2.acs_tied and rev2.graph_signature
assert rev2.node_identity_version == NODE_IDENTITY_VERSION_V1

# ========== NEW M2 A0 Scope Projector smoke (matches, closure, project_scope) - Wave 3 finalized ==========
print("M2 Scope projector smoke...")

# FS level matches + globs + depth
spec = ScopeSpec_v1(directory="src/", include_globs=["*.ts"], exclude_globs=["*.d.ts"], max_depth=3)
assert matches_scope(spec, "src/core.ts")
assert matches_scope(spec, "src/deep/nested/foo.ts")
assert not matches_scope(spec, "src/deep/nested/foo.js")  # glob
assert not matches_scope(spec, "src/deep/nested/foo.d.ts")  # exclude
assert not matches_scope(spec, "tests/bar.ts")  # wrong dir
# depth calc: src/a/b/c/d.ts under src/ -> after prefix 'a/b/c/d' -> count(/)=3 +1 =4 > max=3 => False
assert not matches_scope(spec, "src/a/b/c/d.ts")
spec2 = ScopeSpec_v1(directory="src/", max_depth=4)
assert matches_scope(spec2, "src/a/b/c/d.ts")

# Globs empty = match all under dir
spec3 = ScopeSpec_v1(directory="lib/")
assert matches_scope(spec3, "lib/foo/bar.py")

# Focus closure using synthetic reverse index (dependents)
rev_idx = {
    "src/core.ts": ["src/app.ts", "src/pages/home.ts"],
    "src/utils.ts": ["src/core.ts", "src/app.ts"],
    "src/app.ts": ["tests/test_app.ts"],
}
clos = compute_focus_closure(["src/core.ts"], reverse_index=rev_idx)
assert "src/core.ts" in clos["closure"]
assert "src/app.ts" in clos["closure"]
assert "tests/test_app.ts" in clos["closure"]  # transitive
assert clos["stats"]["size"] >= 3 and not clos["stats"].get("degraded")

# Full project_scope integration (FS + focus)
candidates = ["src/core.ts", "src/utils.ts", "src/app.ts", "tests/test_app.ts", "lib/other.js"]
proj = project_scope(
    ScopeSpec_v1(directory="src/", focus_files=["src/core.ts"], transitive_closure=True),
    candidates,
    reverse_index=rev_idx,
)
assert "matched_files" in proj and "focus_closure" in proj and "stats" in proj
assert "src/core.ts" in proj["matched_files"]
assert "src/app.ts" in proj["matched_files"]
assert proj["stats"]["num_matched"] >= 2
assert proj["next_checkpoint_hint"] and "scope-proj" in proj["next_checkpoint_hint"]
assert proj["version"] == "1.0"

# Degrade gracefully with no index
proj2 = project_scope(ScopeSpec_v1(focus_files=["src/core.ts"]), candidates, reverse_index=None)
assert proj2["stats"]["degraded_focus"] is True
assert "src/core.ts" in proj2["matched_files"]  # seeds still

# V1 alias smoke (plan naming + dual access)
assert ScopeSpecV1 is ScopeSpec_v1
s_v1 = ScopeSpecV1(directory="src")
assert s_v1.directory == "src"
ev_v1 = ProgressEventV1.from_dict({"event_type": "test", "run_id": "r1", "scope": {}})
assert ev_v1.version == "1.0"

# Cleaned projector intersect regression (focus limits matched proportionally)
proj3 = project_scope(
    ScopeSpec_v1(focus_files=["src/core.ts"]),
    candidates + ["other/out.ts"],
    reverse_index=rev_idx,
)
assert "src/core.ts" in proj3["matched_files"]
assert "src/app.ts" in proj3["matched_files"]
assert "other/out.ts" not in proj3["matched_files"]  # outside focus closure
assert not any("lib/" in m for m in proj3["matched_files"])

print("M2 Scope projector smoke: PASS")

# RESERVED keys present and documented
assert "_reverse_dependency_index_v1" in RESERVED_TOP_LEVEL_KEYS
assert "M2 A0/A1" in RESERVED_TOP_LEVEL_KEYS["_reverse_dependency_index_v1"]
assert "_update_runs" in RESERVED_TOP_LEVEL_KEYS
assert "_partial_results" in RESERVED_TOP_LEVEL_KEYS

# contracts_info now surfaces M2
info = get_contracts_info()
assert "m2_contracts_version" in info
assert "ScopeSpec_v1" in info.get("m2_shapes", [])
assert "ScopeSpecV1" in info.get("m2_shapes", [])
assert any(k.startswith("_reverse_dependency") for k in info.get("m2_reserved_keys", []))

print("M2 A0 shape roundtrips + factory + RESERVED + info extension: PASS")

print("All smoke tests passed. Contracts are stable and defensive.")
print(json.dumps(get_contracts_info(), indent=2))
sys.exit(0)
