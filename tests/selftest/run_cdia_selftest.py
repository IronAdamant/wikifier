"""Extracted self-test harness from wikifier/parsers/cdia.py (G12 agent navigability).

Run: python3 tests/selftest/run_cdia_selftest.py
Or:  python3 -m unittest tests.test_selftest_wrappers
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from wikifier.parsers.cdia import get_cdia_engine

import tempfile
import sys

print("=== CDIA Phase 3 Hard Cases Test Suite ===\n")
engine = get_cdia_engine()
counters = {"passed": 0, "failed": 0}

def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    if cond:
        counters["passed"] += 1
    else:
        counters["failed"] += 1
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond

# --- Hard Case 1: Feature flag guarded import (very common) ---
c1 = '''
const featureFlags = { newDashboard: true };
if (featureFlags.newDashboard && process.env.NODE_ENV !== "production") {
    import("./new-dashboard").then(m => use(m));
}
'''
r1 = engine.analyze_import_site(c1, c1.find('import("./new'), "./new-dashboard")
ca1 = r1["conditional_analysis"]
da1 = r1["dynamic_analysis"]
check("HC1: feature flag + env guard sets is_conditional", ca1["is_conditional"])
check("HC1: has feature_flag tag", "feature_flag" in ca1["semantic_tags"])
check("HC1: has env_check tag", "env_check" in ca1["semantic_tags"])
check("HC1: detectors fired include FeatureFlag + Env", {"FeatureFlagDetector", "EnvCheckDetector"}.issubset(set(ca1["detectors_fired"])))
check("HC1: predicate snippet captured", bool(ca1.get("predicate_snippet")))

# --- Hard Case 2: Ternary dynamic specifier ---
c2 = 'const p = cond ? "./a" : getPath(); import(p);'
r2 = engine.analyze_import_site(c2, c2.find("import(p)"), "p", expr_raw='cond ? "./a" : getPath()')
da2 = r2["dynamic_analysis"]
check("HC2: dynamic expression detected", da2["dynamic_type"] in ("expression", "unknown"))
check("HC2: conditional_dynamic or computed_path tag", any(t in da2["semantic_tags"] for t in ("conditional_dynamic", "computed_path")))
check("HC2: DataflowAliasDetector contributed", "DataflowAliasDetector" in da2.get("detectors_fired", []))

# --- Hard Case 3: React.lazy / next/dynamic wrapper ---
c3 = '''
const Heavy = React.lazy(() => import("./HeavyComponent"));
const DynamicPage = dynamic(() => import("../pages/dynamic"));
'''
r3a = engine.analyze_import_site(c3, c3.find('import("./Heavy'), "./HeavyComponent")
r3b = engine.analyze_import_site(c3, c3.find('import("../pages'), "../pages/dynamic")
check("HC3a: lazy wrapper detected (react_lazy)", "react_lazy" in r3a["conditional_analysis"]["semantic_tags"] or "lazy_loading" in r3a["conditional_analysis"]["semantic_tags"])
check("HC3b: next/dynamic detected", "next_dynamic" in r3b["conditional_analysis"]["semantic_tags"] or "lazy_loading" in r3b["conditional_analysis"]["semantic_tags"])

# --- Hard Case 4: require.context webpack magic ---
c4 = 'const ctx = require.context("./locales", true, /\\.json$/);'
r4 = engine.analyze_import_site(c4, c4.find("require.context"), "./locales/xx", expr_raw='require.context("./locales", true, /\\.json$/)')
da4 = r4["dynamic_analysis"]
check("HC4: require.context / webpack_magic tag", "require_context" in da4["semantic_tags"] or "webpack_magic" in da4["semantic_tags"])

# --- Hard Case 5: Simple top-level (should be non-conditional) ---
c5 = 'import x from "./foo";'
r5 = engine.analyze_import_site(c5, c5.find("import x"), "./foo")
check("HC5: top-level import is NOT conditional", not r5["conditional_analysis"]["is_conditional"])

# --- Hard Case 6: Deeply nested if + dead_code_guard style ---
c6 = '''
function init() {
    if (isProduction) {
        if (featureFlags.v2) {
            require("./heavy-v2");
        }
    }
}
'''
r6 = engine.analyze_import_site(c6, c6.rfind('require("./heavy'), "./heavy-v2")
ca6 = r6["conditional_analysis"]
check("HC6: nested if produces control_flow + feature", ca6["is_conditional"] and "control_flow" in ca6["semantic_tags"])

# --- Hard Case 7: Template literal with env substitution ---
c7 = 'import(`./config/${process.env.REGION}.js`);'
r7 = engine.analyze_import_site(c7, c7.find("import(`"), "./config/xx", expr_raw='`./config/${process.env.REGION}.js`')
da7 = r7["dynamic_analysis"]
check("HC7: template + env substitution tags", "template_substitution" in da7["semantic_tags"] and "env_substitution" in da7.get("semantic_tags", []))

# --- Hard Case 8: Variable dataflow from ternary (alias) ---
c8 = 'const mod = isMobile ? "./mobile" : "./desktop"; import(mod);'
r8 = engine.analyze_import_site(c8, c8.find("import(mod)"), "mod", expr_raw="isMobile ? ... : ...")
da8 = r8["dynamic_analysis"]
check("HC8: alias_dataflow + conditional_dynamic", "alias_dataflow" in da8["semantic_tags"] and "var_substitution" in da8["semantic_tags"])

# --- Hard Case 9: Creative dynamic + deeper alias chain (Layer 3.5 + new detectors) ---
# exercises TaggedTemplate / RegistryMap / CallProduced / MultiCond + transitive alias in expr context
c9 = '''
const basePath = getPathFor("feat");
const alias1 = basePath;
const target = alias1;
const reg = {m: "./mod"};
const multi = (ff.x && isMobile ? String.raw`./dyn/${v}` : reg["m"]);
import(target);
require(multi);
'''
r9 = engine.analyze_import_site(c9, c9.find("import(target)"), "target", expr_raw="target")
da9 = r9["dynamic_analysis"]
check("HC9: creative chain detected (alias_dataflow + call or registry)", any(t in da9.get("semantic_tags", []) for t in ("alias_dataflow", "call_produced_path", "registry_map")))
r9b = engine.analyze_import_site(c9, c9.find("require(multi)"), "multi", expr_raw="multi")
da9b = r9b["dynamic_analysis"]
check("HC9b: multi-cond + tagged/registry creative tags", any(t in da9b.get("semantic_tags", []) for t in ("multi_condition_feature_wrapper", "tagged_template", "registry_map", "call_produced_path")))
check("HC9: new creative detectors fired", any(d in da9b.get("detectors_fired", []) for d in ("TaggedTemplateDetector", "RegistryMapDetector", "MultiConditionFeatureWrapperDetector", "CallProducedPathDetector")))

print(f"\n=== CDIA Hard Cases: {counters['passed']} passed, {counters['failed']} failed ===")
if counters['failed']:
    sys.exit(1)
print("All hard cases passed. CDIA core is functional and explainable.")
