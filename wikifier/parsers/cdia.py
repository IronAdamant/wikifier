"""
Conditional & Dynamic Import Analysis (CDIA) — Phase 3 of Gap #1

Pluggable, explainable, registry-driven subsystem for detecting and classifying
conditional and complex dynamic imports in JavaScript/TypeScript (and Python parity via mirrored LDSI/CDIA/registry calls).

Follows the exact architectural pattern established by BREE (bree.py):
- Protocols / structural interfaces for detectors
- Central CDIARegistry for registration (priority-ordered)
- CDIAEngine as the single entry point (get_cdia_engine())
- Auto-registration of core detectors on import
- **context passing for integration (e.g. existing helpers)
- Additive, zero-dependency, evolvable design
- Rich explainability via AnalysisTraceEntry, detectors_fired, semantic_tags

Produces the authoritative shapes for `cdia_v1` (see Pre-Wave 0 contracts):
  {
    "conditional_analysis": ConditionalAnalysis(...).to_dict(),
    "dynamic_analysis": DynamicAnalysis(...).to_dict()
  }

Integration contract with javascript.py (additive):
- Call analyze_import_site(content, match_start, raw_module, expr_raw=..., **ctx)
- Legacy is_conditional / conditional_context / dynamic_* fields are derived from CDIA
  results for full backward compatibility during transition.
- Old _detect_conditional_context becomes a thin shim delegating to CDIA for the
  legacy "if"/"ternary" string (or None).

Hard cases and explainability are first-class: every detector contributes
trace entries with evidence, scores, and notes. Semantic tags are normalized
and versioned (append-only vocabulary).

Initial detector set (8 core) + Phase 1 creative extensions (12 total); Layer 3.5 dataflow + Python parity exercised via harness + hardcases:
  Conditional: ControlFlowDetector, TernaryDetector, FeatureFlagDetector,
               EnvCheckDetector, LazyWrapperDetector
  Dynamic:     ComputedPathDetector, FrameworkMagicDetector, DataflowAliasDetector,
               TaggedTemplateDetector, RegistryMapDetector, MultiConditionFeatureWrapperDetector,
               CallProducedPathDetector  (Layer 3.5 alias CFG + Python parity exercised)

Future: AST-backed detectors can be registered without touching call sites.
Policy (cost budgets, enabled_detectors) can be added via CDIAPolicy (mirrors ExpansionPolicy).

Authoritative semantic tag lists live here (cdia.py) per contracts decision.
"""

from __future__ import annotations

import re
import base64
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Callable, Protocol, Set
from pathlib import Path

# =============================================================================
# Rich Analysis Contract v1 (verbatim from Pre-Wave 0 shared contracts)
# =============================================================================

@dataclass(frozen=True)
class AnalysisTraceEntry:
    detector: str
    fired: bool
    evidence: str
    score_contrib: float
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConditionalAnalysis:
    is_conditional: bool
    semantic_tags: List[str]
    predicate_snippet: Optional[str] = None
    detectors_fired: List[str] = field(default_factory=list)
    analysis_trace: List[AnalysisTraceEntry] = field(default_factory=list)
    confidence: float = 0.0  # detector agreement (0-1), NOT edge confidence
    degraded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_conditional": self.is_conditional,
            "semantic_tags": self.semantic_tags,
            "predicate_snippet": self.predicate_snippet,
            "detectors_fired": self.detectors_fired,
            "analysis_trace": [t.to_dict() for t in self.analysis_trace],
            "confidence": self.confidence,
            "degraded": self.degraded,
        }


@dataclass
class DynamicAnalysis:
    dynamic_type: str  # "static" | "template_literal" | "expression" | "unknown"
    complexity: str    # "simple" | "moderate" | "high" | "opaque"
    semantic_tags: List[str]
    expr_raw: Optional[str] = None
    dynamic_candidates: List[Dict[str, Any]] = field(default_factory=list)
    detectors_fired: List[str] = field(default_factory=list)
    analysis_trace: List[AnalysisTraceEntry] = field(default_factory=list)
    source_variable: Optional[str] = None
    dataflow_trace: List[str] = field(default_factory=list)
    confidence: float = 0.0
    degraded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Semantic Tag Vocabulary (append-only, authoritative in CDIA)
# =============================================================================

CONDITIONAL_SEMANTIC_TAGS: Set[str] = {
    "control_flow",
    "if_statement",
    "ternary",
    "switch_case",
    "try_catch",
    "loop",
    "feature_flag",
    "env_check",
    "dev_only",
    "prod_only",
    "lazy_loading",
    "runtime_optional",
    "dead_code_guard",
    "error_boundary",
    "platform_check",
}

DYNAMIC_SEMANTIC_TAGS: Set[str] = {
    "computed_path",
    "template_substitution",
    "env_substitution",
    "map_lookup",
    "call_expression",
    "alias_dataflow",
    "var_substitution",
    "path_api",
    "webpack_magic",
    "system_import",
    "require_context",
    "react_lazy",
    "next_dynamic",
    "conditional_dynamic",
    # Phase 1 creative extensions (LDSI + CDIA coverage for extremely creative patterns)
    "tagged_template",
    "registry_map",
    "multi_condition_feature_wrapper",
    "call_produced_path",
}

ALL_SEMANTIC_TAGS: Set[str] = CONDITIONAL_SEMANTIC_TAGS | DYNAMIC_SEMANTIC_TAGS


def normalize_tags(tags: List[str] | Set[str]) -> List[str]:
    """Return sorted unique valid tags (unknown tags are dropped with a note in traces)."""
    return sorted({t for t in tags if t in ALL_SEMANTIC_TAGS})


# =============================================================================
# ScopeBuilder — brace-aware context + predicate harvester (lightweight)
# =============================================================================

@dataclass
class ScopeInfo:
    """Lightweight structural context around an import site."""
    nesting_depth: int = 0
    enclosing_predicates: List[str] = field(default_factory=list)  # raw predicate exprs
    control_keywords: List[str] = field(default_factory=list)      # if, for, ?, try, etc.
    recent_lines: List[str] = field(default_factory=list)          # context for debugging
    is_top_level: bool = True
    harvested_predicate_snippet: Optional[str] = None


class ScopeBuilder:
    """
    Builds ScopeInfo by walking the source with a simple brace stack + regex predicate harvest.
    Far more accurate than flat 800-char lookback because it respects nesting.
    Zero-dep, O(n) on snippet size.
    """

    CONTROL_KEYWORDS = re.compile(r'\b(if|else\s+if|else|for|while|switch|case|try|catch|finally)\b')
    TERNARY_RE = re.compile(r'\?[^:]*:')
    PREDICATE_PATTERNS = [
        re.compile(r'\bif\s*\(([^)]{0,120})\)'),
        re.compile(r'\belse\s+if\s*\(([^)]{0,120})\)'),
        re.compile(r'\bwhile\s*\(([^)]{0,120})\)'),
        re.compile(r'\bfor\s*\(([^)]{0,160})\)'),
        re.compile(r'\b(?:const|let|var)\s+\w+\s*=\s*([^;]{0,120})\s*;'),
        re.compile(r'\?\s*([^:]{0,80})\s*:'),
    ]
    FEATURE_LIKE = re.compile(r'(featureFlags?|flags?\.|isEnabled|useFeature|feature_?\w*)\s*[\.\[\(]?\s*[\w"\'\.]+\s*[\)\]]?')
    ENV_LIKE = re.compile(r'(process\.env|NODE_ENV|__DEV__|__PROD__|import\.meta\.env)\s*[\.\[ ]?[\w"\'\.]+\s*')

    def build(self, content: str, pos: int, window: int = 1200) -> ScopeInfo:
        start = max(0, pos - window)
        snippet = content[start:pos]
        after = content[pos:pos + 300]  # small forward context

        # Brace stack to compute real nesting depth at pos
        depth = 0
        last_open = -1
        for i, ch in enumerate(snippet):
            if ch == '{':
                depth += 1
                last_open = i
            elif ch == '}':
                depth = max(0, depth - 1)

        is_top = depth == 0 and '{' not in snippet[-200:]  # rough top-level signal

        # Harvest predicates by scanning backwards for control structures
        predicates: List[str] = []
        keywords: List[str] = []
        lines = snippet.splitlines()
        recent = lines[-8:] if lines else []

        # Find enclosing control keywords in the snippet (most recent first)
        for m in reversed(list(self.CONTROL_KEYWORDS.finditer(snippet))):
            kw = m.group(1) or m.group(0)
            keywords.append(kw.strip())

        # Harvest predicate expressions
        for pat in self.PREDICATE_PATTERNS:
            for m in pat.finditer(snippet):
                pred = m.group(1).strip() if m.lastindex else m.group(0).strip()
                if pred and len(pred) > 1:
                    predicates.append(pred[:140])

        # Look for ternary in immediate context
        if self.TERNARY_RE.search(snippet[-400:] or ''):
            keywords.append("ternary")
            predicates.append("ternary_expression")

        # Feature / env signals even outside full predicate (common in && guards)
        feat = self.FEATURE_LIKE.search(snippet[-600:] or '')
        if feat:
            predicates.append(feat.group(0)[:100])
            keywords.append("feature_flag")

        env = self.ENV_LIKE.search(snippet[-600:] or '')
        if env:
            predicates.append(env.group(0)[:100])
            keywords.append("env_check")

        # Pick the best (most specific) predicate snippet for the analysis
        predicate_snippet = None
        if predicates:
            # Prefer ones containing feature/env or longer ones
            best = sorted(predicates, key=lambda p: (len(p), 1 if any(x in p.lower() for x in ("feature", "env", "flag", "dev", "prod")) else 0), reverse=True)[0]
            predicate_snippet = best

        return ScopeInfo(
            nesting_depth=depth,
            enclosing_predicates=predicates[:6],
            control_keywords=list(dict.fromkeys(keywords))[:6],  # dedup preserve order
            recent_lines=recent,
            is_top_level=is_top,
            harvested_predicate_snippet=predicate_snippet,
        )


# =============================================================================
# Detector Protocols (BREE-style)
# =============================================================================

class ConditionalDetector(Protocol):
    name: str

    def analyze(
        self,
        content: str,
        pos: int,
        scope: ScopeInfo,
        raw_module: str,
        **context: Any,
    ) -> Optional[AnalysisTraceEntry]:
        ...


class DynamicDetector(Protocol):
    name: str

    def analyze(
        self,
        content: str,
        pos: int,
        scope: ScopeInfo,
        raw_module: str,
        expr_raw: Optional[str] = None,
        **context: Any,
    ) -> Optional[AnalysisTraceEntry]:
        ...


# =============================================================================
# Core Detectors (6–8 initial production set)
# =============================================================================

class ControlFlowDetector:
    """Detects import inside if / for / while / switch / try."""
    name = "ControlFlowDetector"

    KEYWORDS = ("if", "for", "while", "switch", "case", "try", "catch")

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, **ctx) -> Optional[AnalysisTraceEntry]:
        fired = False
        evidence = ""
        notes = []
        score = 0.0

        for kw in scope.control_keywords:
            if any(k in kw.lower() for k in self.KEYWORDS):
                fired = True
                evidence = kw
                score = 0.78
                notes.append(f"enclosing_{kw}")
                break

        # Also check nesting depth + recent lines as secondary signal
        if not fired and scope.nesting_depth > 0:
            joined = " ".join(scope.recent_lines).lower()
            if any(k in joined for k in self.KEYWORDS):
                fired = True
                evidence = "nested_control_flow"
                score = 0.55
                notes.append("brace_nesting>0")

        if not fired:
            return AnalysisTraceEntry(self.name, False, "", 0.0, [])

        tags_note = "control_flow" if any(k in ("if", "for") for k in scope.control_keywords) else ""
        return AnalysisTraceEntry(
            detector=self.name,
            fired=True,
            evidence=evidence[:120],
            score_contrib=score,
            notes=notes + (["control_flow"] if tags_note else []),
        )


class TernaryDetector:
    """Detects ternary (?:) expressions and conditional expressions around the site."""
    name = "TernaryDetector"

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, **ctx) -> Optional[AnalysisTraceEntry]:
        # Look in harvested or immediate context
        snippet = " ".join(scope.enclosing_predicates + scope.recent_lines)
        if "ternary" in scope.control_keywords or re.search(r'\?[^:]{0,60}:', snippet):
            return AnalysisTraceEntry(
                self.name, True, "?: expression or ternary guard",
                0.82, ["ternary", "control_flow"]
            )
        # Look directly around the match point in original content
        local = content[max(0, pos-200):pos+80]
        if re.search(r'\?\s*[^:]+:', local) or re.search(r':\s*[^;]+$', local):
            return AnalysisTraceEntry(self.name, True, local[-80:], 0.65, ["ternary"])
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class FeatureFlagDetector:
    """Detects common feature flag / A/B / rollout patterns."""
    name = "FeatureFlagDetector"

    PAT = re.compile(
        r'(featureFlags?|fflags?|flags?\.|isEnabled|useFeature|featureFlag|rollout|experiment|abTest|'
        r'newUI|beta|alpha|darkMode|enable\w+)\s*[\.\[\(]?\s*["\']?[\w\.\-]+["\']?\s*[\)\]\.]?',
        re.I
    )

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, **ctx) -> Optional[AnalysisTraceEntry]:
        hay = " ".join(scope.enclosing_predicates + scope.recent_lines) + " " + content[max(0, pos-400):pos]
        m = self.PAT.search(hay)
        if m:
            return AnalysisTraceEntry(
                self.name, True, m.group(0)[:110],
                0.91, ["feature_flag", "runtime_optional"]
            )
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class EnvCheckDetector:
    """Detects NODE_ENV, process.env, __DEV__, import.meta.env, platform checks."""
    name = "EnvCheckDetector"

    PAT = re.compile(
        r'(process\.env\.|NODE_ENV|__DEV__|__PROD__|import\.meta\.env|'
        r'window\.location|navigator\.|process\.platform|os\.platform|isServer|isClient|'
        r'__SERVER__|__BROWSER__)\s*',
        re.I
    )

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, **ctx) -> Optional[AnalysisTraceEntry]:
        hay = " ".join(scope.enclosing_predicates) + " " + content[max(0, pos-350):pos+50]
        m = self.PAT.search(hay)
        if m:
            ev = m.group(0)[:90]
            notes = ["env_check"]
            if "dev" in ev.lower() or "__DEV__" in ev:
                notes.append("dev_only")
            if "prod" in ev.lower():
                notes.append("prod_only")
            return AnalysisTraceEntry(self.name, True, ev, 0.87, notes)
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class LazyWrapperDetector:
    """Detects React.lazy, next/dynamic, dynamic(import()), lazy-loaded routes etc."""
    name = "LazyWrapperDetector"

    PAT = re.compile(
        r'(React\.lazy|lazy\s*\(|next/dynamic|dynamic\s*\(\s*\(\s*\)\s*=>|'
        r'loadable\s*\(|createAsyncComponent|lazyLoad|Suspense)',
        re.I
    )

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, **ctx) -> Optional[AnalysisTraceEntry]:
        hay = content[max(0, pos-600):pos+200]
        m = self.PAT.search(hay)
        if m:
            notes = ["lazy_loading"]
            if "react" in m.group(0).lower():
                notes.append("react_lazy")
            if "next" in m.group(0).lower() or "dynamic" in m.group(0).lower():
                notes.append("next_dynamic")
            return AnalysisTraceEntry(self.name, True, m.group(0)[:80], 0.89, notes)
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


# --- Dynamic detectors ---

class ComputedPathDetector:
    """Detects computed / expression-based specifiers (calls, +, templates, variables)."""
    name = "ComputedPathDetector"

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        expr = expr_raw or raw_module or ""
        fired = False
        notes = []
        evidence = expr[:100]
        score = 0.3

        if expr_raw:
            # template or expression already known from parser
            if "`" in expr_raw or "${" in expr_raw:
                fired = True
                notes.append("template_substitution")
                score = 0.75
            if re.search(r'process\.env|NODE_ENV|import\.meta\.env', expr_raw, re.I):
                fired = True
                notes.append("env_substitution")
                score = max(score, 0.80)
            if re.search(r'\+|\?|:|\|\||&&', expr_raw):
                fired = True
                notes.append("conditional_dynamic")
                score = max(score, 0.68)
            if re.search(r'\w+\s*\(', expr_raw):  # function call producing path
                fired = True
                notes.append("call_expression")
                score = max(score, 0.72)

        # variable used as specifier (dataflow candidate)
        if re.match(r'^[a-zA-Z_$][\w$]*$', raw_module.strip()):
            fired = True
            notes.append("var_substitution")
            score = max(score, 0.55)

        if fired:
            return AnalysisTraceEntry(self.name, True, evidence, score, notes + ["computed_path"])
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class FrameworkMagicDetector:
    """Catches webpack require.context, system imports, special framework loaders."""
    name = "FrameworkMagicDetector"

    PAT = re.compile(
        r'(require\.context|require\.ensure|__webpack_|import\.meta\.glob|'
        r'system\.import|__non_webpack_require__|createRequire|'
        r'viem|wagmi|trpc|prisma|drizzle)\b',
        re.I
    )

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        hay = (expr_raw or "") + " " + content[max(0, pos-500):pos+150]
        m = self.PAT.search(hay)
        if m:
            name = m.group(0)
            notes = ["path_api"]
            if "require.context" in name:
                notes += ["require_context", "webpack_magic"]
            if "webpack" in name.lower():
                notes.append("webpack_magic")
            if "system" in name.lower():
                notes.append("system_import")
            return AnalysisTraceEntry(self.name, True, name[:80], 0.93, notes)
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class DataflowAliasDetector:
    """
    Limited dataflow: detects when the specifier came from a prior variable assignment
    (const m = cond ? a : b; import(m) or require(m)).
    Re-uses / mirrors the spirit of the existing _resolve_simple_var_dataflow in javascript.py.
    """
    name = "DataflowAliasDetector"

    VAR_ASSIGN = re.compile(
        r'(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*([^;]{0,180});',
        re.M
    )

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        if not re.match(r'^[a-zA-Z_$][\w$]*$', (raw_module or "").strip()):
            return AnalysisTraceEntry(self.name, False, "", 0.0, [])

        var_name = raw_module.strip()
        # Search backwards from pos for the most recent assignment to this var
        before = content[max(0, pos - 1400):pos]
        matches = list(self.VAR_ASSIGN.finditer(before))
        for m in reversed(matches):
            if m.group(1) == var_name:
                rhs = m.group(2).strip()[:160]
                notes = ["alias_dataflow", "var_substitution"]
                if "?" in rhs or ":" in rhs:
                    notes.append("conditional_dynamic")
                evidence = f"{var_name} = {rhs[:80]}"
                return AnalysisTraceEntry(self.name, True, evidence, 0.71, notes)

        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


# --- Phase 1 Creative/Dynamic detectors (additive Layer 1 coverage for extremely creative patterns) ---


class TaggedTemplateDetector:
    """Detects tagged template literals used to produce dynamic import specifiers
    (e.g. String.raw`./foo/${bar}`, pathTag`...`, t`mod/${x}`).
    Common in creative bundler/plugin code and i18n/path builders.
    """
    name = "TaggedTemplateDetector"

    TAGGED_TMPL = re.compile(r'\b[a-zA-Z_$][\w$]*\s*`[^`]*`', re.M)

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        expr = expr_raw or raw_module or ""
        hay = expr + " " + content[max(0, pos-300):pos+100]
        if "`" in expr and self.TAGGED_TMPL.search(expr):
            # distinguish from plain template by leading ident before `
            if re.search(r'\b[a-zA-Z_$][\w$]*\s*`', expr):
                return AnalysisTraceEntry(
                    self.name, True, expr[:90],
                    0.78, ["tagged_template", "computed_path", "template_substitution"]
                )
        # fallback scan in hay for creative tagged usage near site
        m = self.TAGGED_TMPL.search(hay)
        if m and "import" not in m.group(0).lower()[:20]:
            return AnalysisTraceEntry(self.name, True, m.group(0)[:80], 0.62, ["tagged_template"])
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class RegistryMapDetector:
    """Detects registry / map / dict lookup patterns for module resolution
    (e.g. registry[key], mods.get(name), MODULES[cond ? a : b], requireMap[foo]).
    """
    name = "RegistryMapDetector"

    MAP_LOOKUP = re.compile(
        r'(registry|map|modules?|registryMap|modMap|requireMap|dynamicMap|paths?Map)'
        r'\s*[\.\[]\s*[\w\'"\.\$]+',
        re.I
    )
    GET_CALL = re.compile(r'\.(get|resolve|lookup)\s*\(\s*[\'"\w\$\.]+\s*\)', re.I)

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        expr = (expr_raw or raw_module or "").strip()
        hay = expr + " " + content[max(0, pos-450):pos+120]
        if self.MAP_LOOKUP.search(expr) or self.GET_CALL.search(expr):
            notes = ["registry_map", "map_lookup", "computed_path"]
            return AnalysisTraceEntry(self.name, True, expr[:85] or "registry/map lookup", 0.74, notes)
        if self.MAP_LOOKUP.search(hay) or self.GET_CALL.search(hay):
            m = self.MAP_LOOKUP.search(hay) or self.GET_CALL.search(hay)
            return AnalysisTraceEntry(self.name, True, m.group(0)[:70], 0.59, ["registry_map"])
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class MultiConditionFeatureWrapperDetector:
    """Detects deeply multi-condition feature-flag / wrapper expressions guarding
    or producing dynamic paths (e.g. (ff.a && isMobile && !isProd ? getPath() : ... )).
    """
    name = "MultiConditionFeatureWrapperDetector"

    MULTI_COND = re.compile(r'(&&|\|\||\band\b|\bor\b).{0,40}(&&|\|\||\band\b|\bor\b)', re.I)
    FEAT_WRAPPER = re.compile(
        r'(feature|flag|enabled?|isMobile|isProd|isServer|useFeature|checkFlag)',
        re.I
    )

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        expr = expr_raw or raw_module or ""
        hay = " ".join(scope.enclosing_predicates) + " " + expr + " " + content[max(0, pos-500):pos]
        if self.MULTI_COND.search(expr) and self.FEAT_WRAPPER.search(hay):
            notes = ["multi_condition_feature_wrapper", "conditional_dynamic", "feature_flag"]
            return AnalysisTraceEntry(self.name, True, expr[:75], 0.81, notes)
        if self.MULTI_COND.search(hay) and self.FEAT_WRAPPER.search(hay):
            return AnalysisTraceEntry(self.name, True, "multi-cond feature wrapper", 0.66, ["multi_condition_feature_wrapper"])
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


class CallProducedPathDetector:
    """Detects paths produced by function calls (beyond simple 'contains_call'),
    including helpers, getters, and factory calls: getModulePath(), resolvePath(x),
    createImportSpecifier(), pathFor('feature').
    """
    name = "CallProducedPathDetector"

    PRODUCER = re.compile(
        r'\b(get\w*Path|resolve\w*Path|make\w*Path|create\w*(Path|Import|Module)|pathFor|'
        r'moduleFor|specifierFor|dynamicFor|getDynamic|loadPath|compute\w*)\s*\(',
        re.I
    )
    GENERIC_CALL = re.compile(r'\b[a-zA-Z_$][\w$]*\s*\([^)]{0,80}\)\s*[\+\s\?\/]?\s*["\']?[\w\./]')

    def analyze(self, content: str, pos: int, scope: ScopeInfo, raw_module: str, expr_raw: Optional[str] = None, **ctx) -> Optional[AnalysisTraceEntry]:
        expr = expr_raw or raw_module or ""
        if self.PRODUCER.search(expr):
            return AnalysisTraceEntry(
                self.name, True, expr[:80],
                0.83, ["call_produced_path", "call_expression", "computed_path"]
            )
        # secondary: any call in expr context that is not a known plain template/ident
        if re.search(r'\w\s*\(', expr) and len(expr) > 3:
            # avoid overfiring on simple require( call ) already caught higher; still contribute
            if not re.match(r'^[a-zA-Z_$][\w$]*$', expr.strip()):
                return AnalysisTraceEntry(self.name, True, expr[:70], 0.61, ["call_produced_path"])
        hay = content[max(0, pos-350):pos+80]
        if self.PRODUCER.search(hay):
            m = self.PRODUCER.search(hay)
            return AnalysisTraceEntry(self.name, True, m.group(0)[:60], 0.55, ["call_produced_path"])
        return AnalysisTraceEntry(self.name, False, "", 0.0, [])


# =============================================================================
# Registry (BREE pattern)
# =============================================================================

class CDIARegistry:
    """Central pluggable registry. Detectors are discovered here."""

    _conditional_detectors: List[Tuple[int, ConditionalDetector]] = []
    _dynamic_detectors: List[Tuple[int, DynamicDetector]] = []

    @classmethod
    def register_conditional_detector(cls, detector: ConditionalDetector, priority: int = 0) -> None:
        cls._conditional_detectors.append((priority, detector))
        cls._conditional_detectors.sort(key=lambda t: -t[0])

    @classmethod
    def register_dynamic_detector(cls, detector: DynamicDetector, priority: int = 0) -> None:
        cls._dynamic_detectors.append((priority, detector))
        cls._dynamic_detectors.sort(key=lambda t: -t[0])

    @classmethod
    def get_conditional_detectors(cls) -> List[ConditionalDetector]:
        return [d for _, d in cls._conditional_detectors]

    @classmethod
    def get_dynamic_detectors(cls) -> List[DynamicDetector]:
        return [d for _, d in cls._dynamic_detectors]

    @classmethod
    def clear(cls) -> None:
        """Test / reset helper."""
        cls._conditional_detectors.clear()
        cls._dynamic_detectors.clear()


# Auto-register the 8 core detectors (executed once at import time)
_default_cond_detectors = [
    (ControlFlowDetector(), 100),
    (TernaryDetector(), 95),
    (FeatureFlagDetector(), 90),
    (EnvCheckDetector(), 85),
    (LazyWrapperDetector(), 80),
]
for det, pri in _default_cond_detectors:
    CDIARegistry.register_conditional_detector(det, priority=pri)

_default_dyn_detectors = [
    (ComputedPathDetector(), 100),
    (FrameworkMagicDetector(), 90),
    (DataflowAliasDetector(), 75),
    # Phase 1: four new creative/dynamic detectors for extremely creative patterns (lower pri so core fire first)
    (TaggedTemplateDetector(), 70),
    (RegistryMapDetector(), 65),
    (MultiConditionFeatureWrapperDetector(), 60),
    (CallProducedPathDetector(), 55),
]
for det, pri in _default_dyn_detectors:
    CDIARegistry.register_dynamic_detector(det, priority=pri)


# =============================================================================
# The CDIA Engine
# =============================================================================

class CDIAEngine:
    """
    The central Conditional & Dynamic Import Analysis engine.
    Obtain via get_cdia_engine().

    Primary public API for parsers:
        engine.analyze_import_site(content, match_start, raw_module, expr_raw=..., **ctx)
        -> {"conditional_analysis": dict, "dynamic_analysis": dict}
    """

    def __init__(self, registry: Optional[CDIARegistry] = None):
        self.registry = registry or CDIARegistry
        self._scope_builder = ScopeBuilder()
        self._memo: Dict[str, Any] = {}  # short per-run memo

    def analyze_import_site(
        self,
        content: str,
        match_start: int,
        raw_module: str,
        *,
        expr_raw: Optional[str] = None,
        dynamic_type_hint: Optional[str] = None,
        statement_type: Optional[str] = None,
        **context: Any,
    ) -> Dict[str, Any]:
        """
        Main entry point. Returns the full cdia_v1 payload shape (ready for
        serialization or direct attachment to parser results).
        """
        key = f"cdia::{match_start}::{hash((raw_module, expr_raw))}"
        if key in self._memo:
            return self._memo[key]

        scope = self._scope_builder.build(content, match_start)

        # --- Conditional analysis ---
        cond_trace: List[AnalysisTraceEntry] = []
        cond_tags: Set[str] = set()
        cond_fired_names: List[str] = []
        total_cond_score = 0.0
        cond_count = 0

        for det in self.registry.get_conditional_detectors():
            try:
                entry = det.analyze(content, match_start, scope, raw_module, **context)
            except Exception:
                continue
            if entry:
                cond_trace.append(entry)
                if entry.fired:
                    cond_fired_names.append(det.name)
                    total_cond_score += entry.score_contrib
                    cond_count += 1
                    # Detectors may embed tags in notes
                    for n in entry.notes:
                        if n in CONDITIONAL_SEMANTIC_TAGS:
                            cond_tags.add(n)

        is_conditional = cond_count > 0 or bool(scope.control_keywords) or bool(scope.enclosing_predicates)
        if is_conditional and not cond_tags:
            # Derive from keywords
            for kw in scope.control_keywords:
                if "if" in kw:
                    cond_tags.add("if_statement")
                elif "ternary" in kw:
                    cond_tags.add("ternary")
            cond_tags.add("control_flow")

        cond_conf = min(1.0, (total_cond_score / max(1, cond_count)) * 0.95) if cond_count else (0.35 if is_conditional else 0.0)

        ca = ConditionalAnalysis(
            is_conditional=is_conditional,
            semantic_tags=normalize_tags(list(cond_tags)),
            predicate_snippet=scope.harvested_predicate_snippet,
            detectors_fired=cond_fired_names,
            analysis_trace=cond_trace,
            confidence=round(cond_conf, 3),
            degraded=False,
        )

        # --- Dynamic analysis ---
        dyn_trace: List[AnalysisTraceEntry] = []
        dyn_tags: Set[str] = set()
        dyn_fired_names: List[str] = []
        total_dyn_score = 0.0
        dyn_count = 0
        source_var: Optional[str] = None
        dataflow: List[str] = []

        dyn_type = dynamic_type_hint or ("expression" if expr_raw else "static")
        complexity = "simple"

        for det in self.registry.get_dynamic_detectors():
            try:
                entry = det.analyze(content, match_start, scope, raw_module, expr_raw=expr_raw, **context)
            except Exception:
                continue
            if entry:
                dyn_trace.append(entry)
                if entry.fired:
                    dyn_fired_names.append(det.name)
                    total_dyn_score += entry.score_contrib
                    dyn_count += 1
                    for n in entry.notes:
                        if n in DYNAMIC_SEMANTIC_TAGS:
                            dyn_tags.add(n)
                    if "var_substitution" in entry.notes or "alias_dataflow" in entry.notes:
                        source_var = raw_module

        if dyn_count > 0:
            if "template_substitution" in dyn_tags or (expr_raw and "`" in expr_raw):
                complexity = "moderate"
            if any(x in dyn_tags for x in ("conditional_dynamic", "call_expression", "alias_dataflow")):
                complexity = "high"

        dyn_conf = min(1.0, (total_dyn_score / max(1, dyn_count)) * 0.9) if dyn_count else 0.0

        # If the parser already told us it is dynamic, ensure we at least mark it
        if dyn_type != "static" and not dyn_tags:
            dyn_tags.add("computed_path")
            dyn_conf = max(dyn_conf, 0.4)

        da = DynamicAnalysis(
            dynamic_type=dyn_type,
            complexity=complexity,
            semantic_tags=normalize_tags(list(dyn_tags)),
            expr_raw=expr_raw,
            dynamic_candidates=context.get("dynamic_candidates", []),
            detectors_fired=dyn_fired_names,
            analysis_trace=dyn_trace,
            source_variable=source_var,
            dataflow_trace=dataflow,
            confidence=round(dyn_conf, 3),
            degraded=False,
        )

        result = {
            "conditional_analysis": ca.to_dict(),
            "dynamic_analysis": da.to_dict(),
        }
        self._memo[key] = result
        return result

    def legacy_detect_conditional_context(self, content: str, match_start: int) -> str | None:
        """
        Backward-compatible thin shim for the old _detect_conditional_context.
        Returns "if", "ternary", "switch", "unknown", or None.
        Used during the transition so all call sites keep working.
        """
        payload = self.analyze_import_site(content, match_start, "__legacy__")
        ca = payload["conditional_analysis"]
        if not ca.get("is_conditional"):
            return None

        tags = ca.get("semantic_tags", [])
        pred = (ca.get("predicate_snippet") or "").lower()

        if "ternary" in tags or "ternary" in pred:
            return "ternary"
        if "if_statement" in tags or "if" in pred:
            return "if"
        if "switch" in pred or "case" in pred:
            return "switch"
        if tags:
            return "unknown"
        return "unknown"


# Singleton engine accessor (exactly like get_bree_engine)
_engine: Optional[CDIAEngine] = None

def get_cdia_engine() -> CDIAEngine:
    global _engine
    if _engine is None:
        _engine = CDIAEngine()
    return _engine


def reset_cdia_engine() -> None:
    """Primarily for tests."""
    global _engine
    _engine = None
    CDIARegistry.clear()


# =============================================================================
# Convenience: serialize to the cdia_v1 payload (b64 ready)
# =============================================================================

def make_cdia_v1_payload(analysis: Dict[str, Any]) -> str:
    """Return compact JSON string suitable for later base64 encoding into cdia_v1=..."""
    return json.dumps(analysis, separators=(",", ":"), ensure_ascii=False)


# =============================================================================
# Self-contained hard-cases test suite (run with: python -m wikifier.parsers.cdia)
# =============================================================================
