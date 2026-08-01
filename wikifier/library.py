"""Pure-Python generator for library.md (dependency map artifact).

Port of the shell implementation in wikifier.sh (cmd_update_maps +
generate_mermaid_dependency_graph + generate_resolved_dependencies_table)
to stdlib-only Python (>=3.8).

Contract
--------
``generate_library_md(root, cache) -> str``
    Renders the full library.md content from a loaded import cache
    (the canonical ``.wikifier_staging/import_cache.json`` schema:
    top-level dict keyed by project-relative path -> {"mtime", "resolved_pairs": [...]},
    plus reserved "_"-prefixed keys such as ``_cycles``, ``_cycle_analyses``,
    ``_acs_summary``, ``_reverse_dependencies``). Missing fields and reserved
    keys are tolerated; an empty cache yields a valid, explicit library.md.

``write_library_md(root, cache=None) -> dict``
    Loads the cache via ``wikifier.import_cache.load_cache`` when not given,
    generates the content, and writes ``<root>/library.md`` atomically
    (``library.md.tmp`` + ``os.replace``). Returns
    ``{"success": bool, "path": str, "nodes": int, "edges": int}``
    plus ``"error"`` on operational failure.

Sections generated: header, Mermaid dependency graph (grouped by top-level
directory, confidence-styled edges, 280-node cap), resolved dependencies
table (500-row cap), circular dependencies, ACS risk snapshot, reverse
dependencies, barrel expansions, and conditional/dynamic intelligence.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_MERMAID_NODES = 280
MAX_MERMAID_EDGES = 600
MAX_TABLE_ROWS = 500
MAX_CYCLE_CLUSTERS = 8


# ---------------------------------------------------------------------------
# Cache traversal helpers
# ---------------------------------------------------------------------------

def _iter_pairs(cache: Dict[str, Any]):
    """Yield (source_rel_path, pair_dict) for every resolved pair in the cache."""
    for rel, data in cache.items():
        if rel.startswith("_") or not isinstance(data, dict):
            continue
        pairs = data.get("resolved_pairs") or []
        if not isinstance(pairs, list):
            continue
        for pair in pairs:
            if isinstance(pair, dict):
                yield rel, pair


def _pair_confidence(pair: Dict[str, Any]) -> str:
    """Normalize a pair's confidence to high/medium/low (string field wins)."""
    conf = pair.get("confidence")
    if conf in ("high", "medium", "low"):
        return conf
    score = pair.get("confidence_score")
    if isinstance(score, (int, float)):
        if score >= 0.8:
            return "high"
        if score >= 0.65:
            return "medium"
        return "low"
    return "medium"


def _collect_edges(cache: Dict[str, Any]) -> List[Tuple[str, str, str, str, bool]]:
    """Build deduplicated edges: (source, raw, target, confidence, is_internal_target).

    The target is the resolved project-relative path when resolution succeeded,
    otherwise the raw import specifier (treated as external/bare).
    """
    edges = []
    seen = set()
    for src, pair in _iter_pairs(cache):
        raw = str(pair.get("raw") or "").strip()
        resolved = str(pair.get("resolved") or "").strip()
        if not raw and not resolved:
            continue
        if "\n" in raw or "\n" in resolved:
            # Parser artifact (e.g. comment/doc text captured as a dynamic
            # specifier) — never let multi-line "modules" become graph nodes.
            continue
        internal = bool(resolved)
        target = resolved if internal else raw
        conf = _pair_confidence(pair)
        key = (src, raw, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append((src, raw or target, target, conf, internal))
    return edges


# ---------------------------------------------------------------------------
# Mermaid graph
# ---------------------------------------------------------------------------

def _sanitize_node_id(name: str) -> str:
    """Mermaid-safe node id: every non-alphanumeric character becomes '_'."""
    nid = re.sub(r"[^A-Za-z0-9]", "_", name)
    if nid and nid[0].isdigit():
        nid = "n_" + nid
    return nid or "_unknown"


def _node_label(path: str) -> str:
    base = os.path.basename(path.rstrip("/")) or path
    # Labels must never carry newlines/quotes/brackets — garbage raw modules
    # once leaked multi-line comment text into the rendered graph.
    base = re.sub(r"\s+", " ", base).replace('"', "'").replace("[", "(").replace("]", ")")
    return (base[:48] + "…") if len(base) > 49 else base


def _top_level_group(path: str) -> str:
    """Group internal nodes by their top-level directory ('root' for flat files)."""
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "root"


def _edge_arrow(confidence: str) -> str:
    if confidence == "high":
        return "-->"
    if confidence == "medium":
        return "-.->"
    return "-. ? .->"


def _generate_mermaid_section(edges: List[Tuple[str, str, str, str, bool]]) -> List[str]:
    lines = ["## Dependency Graph (Mermaid)", "", "```mermaid", "graph TD"]

    # nodes: id -> (label, group_or_None_for_external)
    nodes: Dict[str, Tuple[str, Optional[str]]] = {}
    degree: Dict[str, int] = {}
    graph_edges: List[Tuple[str, str, str]] = []  # (src_id, arrow, tgt_id)
    edge_seen = set()

    for src, _raw, target, conf, internal in edges:
        src_id = _sanitize_node_id(src)
        tgt_id = _sanitize_node_id(target)
        if src_id not in nodes:
            nodes[src_id] = (_node_label(src), _top_level_group(src))
        if tgt_id not in nodes:
            nodes[tgt_id] = (_node_label(target),
                             _top_level_group(target) if internal else None)
        ekey = (src_id, tgt_id)
        if ekey in edge_seen:
            continue
        edge_seen.add(ekey)
        graph_edges.append((src_id, _edge_arrow(conf), tgt_id))
        degree[src_id] = degree.get(src_id, 0) + 1
        degree[tgt_id] = degree.get(tgt_id, 0) + 1

    if not nodes:
        lines.append("    %% No dependency edges recorded yet — run update-maps after parsing.")
        lines.append("    Empty[\"(no import edges in cache)\"]")
        lines.extend(["```", ""])
        return lines

    # Node cap: keep the highest-degree nodes when over the limit.
    kept = set(nodes)
    if len(nodes) > MAX_MERMAID_NODES:
        ranked = sorted(nodes, key=lambda n: (-degree.get(n, 0), n))
        kept = set(ranked[:MAX_MERMAID_NODES])
        lines.append("    %% WARNING: Graph has {0} nodes (capped at {1} for readability;"
                     " highest-degree nodes kept)".format(len(nodes), MAX_MERMAID_NODES))

    # Subgraphs per top-level directory for internal nodes.
    groups: Dict[str, List[str]] = {}
    external_nodes: List[str] = []
    for nid in sorted(kept):
        _label, group = nodes[nid]
        if group is None:
            external_nodes.append(nid)
        else:
            groups.setdefault(group, []).append(nid)

    for group in sorted(groups):
        lines.append("    subgraph {0}".format(_sanitize_node_id(group)))
        for nid in groups[group]:
            lines.append('        {0}["{1}"]'.format(nid, nodes[nid][0]))
        lines.append("    end")

    if external_nodes:
        lines.append("    subgraph External")
        for nid in external_nodes:
            lines.append('        {0}["{1}"]'.format(nid, nodes[nid][0]))
        lines.append("    end")

    emitted = 0
    for src_id, arrow, tgt_id in graph_edges:
        if src_id not in kept or tgt_id not in kept:
            continue
        if emitted >= MAX_MERMAID_EDGES:
            break
        lines.append("    {0} {1} {2}".format(src_id, arrow, tgt_id))
        emitted += 1
    if len(graph_edges) > emitted:
        lines.append("    %% (Graph truncated — {0} total edges, {1} shown)".format(
            len(graph_edges), emitted))

    if external_nodes:
        lines.append("    classDef external fill:#eeeeee,stroke:#888888,stroke-dasharray: 3 3")
        lines.append("    class {0} external".format(",".join(external_nodes)))

    lines.extend(["```", ""])
    return lines


# ---------------------------------------------------------------------------
# Resolved dependencies table
# ---------------------------------------------------------------------------

def _generate_table_section(edges: List[Tuple[str, str, str, str, bool]]) -> List[str]:
    lines = ["## Resolved Dependencies", ""]
    if not edges:
        lines.append("(No resolved import pairs in the cache — run `wikifier update-maps`.)")
        lines.append("")
        return lines
    lines.append("| Source | Import → Resolved | Confidence |")
    lines.append("|--------|-------------------|------------|")
    rows = sorted(edges, key=lambda e: (e[0], e[1]))
    for src, raw, target, conf, _internal in rows[:MAX_TABLE_ROWS]:
        shown_target = target if target else "(unresolved)"
        lines.append("| {0} | {1} → {2} | {3} |".format(src, raw, shown_target, conf))
    if len(rows) > MAX_TABLE_ROWS:
        lines.append("")
        lines.append("> Table truncated to {0} of {1} rows. Use the cache/MCP "
                     "`get_dependencies` for the complete set.".format(
                         MAX_TABLE_ROWS, len(rows)))
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Circular dependencies
# ---------------------------------------------------------------------------

def _generate_cycles_section(cache: Dict[str, Any]) -> List[str]:
    lines = ["## Circular Dependencies", ""]
    cdata = cache.get("_cycles") or {}
    sccs = cdata.get("sccs") if isinstance(cdata, dict) else None
    sccs = sccs or []
    stats = cdata.get("stats", {}) if isinstance(cdata, dict) else {}

    if not sccs:
        lines.append("✅ No circular dependencies detected in the current dependency graph.")
        lines.append("")
        return lines

    lines.append("**Status**: {0} cyclic cluster(s) involving {1} file(s). "
                 "Largest cluster size: {2}".format(
                     stats.get("cyclic_scc_count", len(sccs)),
                     stats.get("total_files_in_cycles",
                               sum(len(s.get("nodes", [])) for s in sccs)),
                     stats.get("largest_scc_size",
                               max((s.get("size", 0) for s in sccs), default=0))))
    lines.append("**Signals across cycles**: dynamic={0} | conditional={1} | via_barrel={2}".format(
        stats.get("dynamic_edges_in_cycles", 0),
        stats.get("conditional_edges_in_cycles", 0),
        stats.get("barrel_edges_in_cycles", 0)))
    lines.append("")

    # Index per-cluster analyses (severity + recommendations) by sorted node set.
    analyses = cache.get("_cycle_analyses") or {}
    a_map = {}
    if isinstance(analyses, dict):
        for a in analyses.get("analyses", []) or []:
            if isinstance(a, dict):
                a_map[tuple(sorted(a.get("nodes", [])))] = a

    lines.append("Top cyclic clusters:")
    for idx, scc in enumerate(sccs[:MAX_CYCLE_CLUSTERS], 1):
        nodes = scc.get("nodes", []) or []
        example = scc.get("example_path") or " → ".join(nodes[:5]) or "?"
        sig = scc.get("signals", {}) or {}
        extra = ""
        dyn, cond, barr = (sig.get("dynamic_edge_count", 0),
                           sig.get("conditional_edge_count", 0),
                           sig.get("barrel_edge_count", 0))
        if dyn or cond or barr:
            extra = "  (dyn={0} cond={1} barrel={2})".format(dyn, cond, barr)
        lines.append("- {0}. size={1} : {2}{3}".format(idx, scc.get("size", len(nodes)),
                                                       example, extra))
        analysis = a_map.get(tuple(sorted(nodes)), {})
        severity = analysis.get("severity")
        if severity:
            rec = (analysis.get("recommendations") or [{}])[0]
            rec_str = ""
            if rec.get("strategy"):
                rec_str = " | top rec: {0} — {1}".format(
                    rec.get("strategy"), rec.get("rationale") or "")
            lines.append("    **SEVERITY**: {0} (score={1}, blast={2}){3}".format(
                severity, analysis.get("score", 0),
                analysis.get("external_blast_radius", 0), rec_str))
    if len(sccs) > MAX_CYCLE_CLUSTERS:
        lines.append("- ... ({0} more clusters — use MCP `get_cycles(analysis=True)` "
                     "for complete details)".format(len(sccs) - MAX_CYCLE_CLUSTERS))
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# ACS, reverse dependencies, barrels, conditional/dynamic
# ---------------------------------------------------------------------------

def _generate_acs_section(cache: Dict[str, Any]) -> List[str]:
    """ACS section for library.md — prefer actionable + reason codes (G9)."""
    lines = ["## ACS Risk Snapshot", ""]
    acs = cache.get("_acs_summary") or {}
    if not isinstance(acs, dict) or not acs.get("total_scored_edges"):
        lines.append("(No ACS summary persisted yet — run `wikifier update-maps` "
                     "to score edge confidence.)")
        lines.append("")
        return lines
    actionable = acs.get("actionable_low_conf_edges")
    if actionable is None:
        actionable = acs.get("low_conf_edges", 0)
    lines.append(
        "**Scored edges**: {0} | **avg_confidence**: {1} | "
        "**actionable_low_conf**: {2} | raw low-conf (telemetry): {3} "
        "(threshold {4})".format(
            acs.get("total_scored_edges"),
            acs.get("avg_confidence"),
            actionable,
            acs.get("low_conf_edges", 0),
            acs.get("low_conf_threshold", 0.65),
        )
    )
    lines.append(
        "**Agent work queue**: use `actionable_low_conf_edges` + "
        "`reason_code_counts` / `agent_signal=investigate` only — "
        "do **not** thrash on raw `low_conf_edges` (includes external/bare)."
    )
    rcc = acs.get("reason_code_counts") or {}
    if isinstance(rcc, dict) and rcc:
        lines.append(
            "**reason_code_counts**: "
            + ", ".join("{0}:{1}".format(k, v) for k, v in list(rcc.items())[:8])
        )
    top_reasons = acs.get("top_risk_reasons") or {}
    if top_reasons:
        lines.append("**Top risk reasons**: " + ", ".join(
            "{0}:{1}".format(k, v) for k, v in list(top_reasons.items())[:4]))
    # Prefer actionable samples when present
    samples = (
        acs.get("sample_actionable_explanations")
        or acs.get("sample_low_conf_explanations")
        or []
    )
    if samples:
        label = (
            "Sample actionable edges"
            if acs.get("sample_actionable_explanations")
            else "Sample low-confidence edges (telemetry; prefer actionable)"
        )
        lines.append("**{0}**:".format(label))
        for i, sample in enumerate(samples[:3], 1):
            lines.append("  {0}. {1}".format(i, sample))
    lines.append("")
    return lines


def _generate_reverse_section(cache: Dict[str, Any]) -> List[str]:
    lines = ['## Reverse Dependencies ("Who depends on me")', ""]
    rev = cache.get("_reverse_dependencies") or {}
    if not isinstance(rev, dict) or not rev:
        lines.append("(No reverse dependencies recorded — run `wikifier update-maps` "
                     "to populate the index.)")
        lines.append("")
        return lines
    total_edges = sum(len(v) for v in rev.values() if isinstance(v, list))
    lines.append("**Targets with dependents**: {0} | **Total reverse edges**: {1}".format(
        len(rev), total_edges))
    lines.append("")
    lines.append("**High-impact modules (most reverse dependents)**:")
    ranked = sorted(((k, v) for k, v in rev.items() if isinstance(v, list)),
                    key=lambda kv: (-len(kv[1]), kv[0]))
    for target, sources in ranked[:10]:
        sample = ", ".join(sources[:4])
        lines.append("- `{0}` ← {1} files depend on it (e.g. {2})".format(
            target, len(sources), sample))
    lines.append("")
    return lines


def _generate_barrel_section(cache: Dict[str, Any]) -> List[str]:
    lines = ["## Barrel Expansions", ""]
    summary = None
    try:
        from wikifier import import_cache as ic
        fn = getattr(ic, "summarize_barrel_expansions", None)
        if callable(fn):
            summary = fn(cache)
    except Exception:
        summary = None

    if not isinstance(summary, dict):
        # Fallback: derive a basic summary directly from the pairs.
        per_file: Dict[str, Dict[str, int]] = {}
        total = 0
        max_depth = 0
        for src, pair in _iter_pairs(cache):
            if not pair.get("via_barrel"):
                continue
            total += 1
            depth = pair.get("barrel_depth") or 0
            max_depth = max(max_depth, depth if isinstance(depth, int) else 0)
            entry = per_file.setdefault(src, {"count": 0, "max_depth": 0})
            entry["count"] += 1
            entry["max_depth"] = max(entry["max_depth"],
                                     depth if isinstance(depth, int) else 0)
        summary = {
            "total_via_barrel_imports": total,
            "files_using_barrels": len(per_file),
            "max_barrel_depth_observed": max_depth,
            "top_barrel_users": [
                {"file": f, "count": d["count"], "max_depth": d["max_depth"]}
                for f, d in sorted(per_file.items(),
                                   key=lambda kv: (-kv[1]["count"], kv[0]))
            ],
        }

    lines.append("**Total via-barrel imports**: {0}".format(
        summary.get("total_via_barrel_imports", 0)))
    lines.append("**Files using barrel re-exports**: {0}".format(
        summary.get("files_using_barrels", 0)))
    lines.append("**Max observed barrel depth**: {0}".format(
        summary.get("max_barrel_depth_observed", 0)))
    lines.append("")
    top_users = (summary.get("top_barrel_users") or [])[:8]
    if top_users:
        lines.append("Top barrel users (by import count):")
        for user in top_users:
            lines.append("- `{0}`: {1} imports (max_depth={2})".format(
                user.get("file", "?"), user.get("count", 0), user.get("max_depth", 0)))
    else:
        lines.append("(No barrel usage detected in this run)")
    note = summary.get("note")
    if note:
        lines.append("")
        lines.append("> {0}".format(note))
    lines.append("")
    return lines


def _generate_conditional_dynamic_section(cache: Dict[str, Any]) -> List[str]:
    lines = ["## Conditional & Dynamic Intelligence", ""]
    summary = None
    try:
        from wikifier import import_cache as ic
        fn = getattr(ic, "summarize_conditional_dynamic", None)
        if callable(fn):
            summary = fn(cache)
    except Exception:
        summary = None

    if not isinstance(summary, dict):
        cond_examples = []
        dyn_examples = []
        cond = dyn = 0
        for src, pair in _iter_pairs(cache):
            if pair.get("is_conditional"):
                cond += 1
                if len(cond_examples) < 5:
                    cond_examples.append({"source": src, "import": pair.get("raw", "?"),
                                          "context": pair.get("conditional_context", "")})
            if pair.get("is_dynamic"):
                dyn += 1
                if len(dyn_examples) < 5:
                    dyn_examples.append({"source": src, "import": pair.get("raw", "?"),
                                         "type": pair.get("dynamic_type", "?")})
        summary = {"conditional_imports": cond, "dynamic_imports": dyn,
                   "conditional_examples": cond_examples, "dynamic_examples": dyn_examples}

    lines.append("**Conditional imports detected**: {0}".format(
        summary.get("conditional_imports", 0)))
    lines.append("**Dynamic imports detected**: {0}".format(
        summary.get("dynamic_imports", 0)))
    lines.append("")
    cond_examples = summary.get("conditional_examples") or []
    if cond_examples:
        lines.append("Sample conditional imports (fragile / feature-flagged paths):")
        for ex in cond_examples[:5]:
            ctx = str(ex.get("context") or "")[:55]
            lines.append("- `{0}` → `{1}`  (ctx: {2})".format(
                ex.get("source", "?"), ex.get("import", "?"), ctx))
    dyn_examples = summary.get("dynamic_examples") or []
    if dyn_examples:
        lines.append("Sample dynamic imports (runtime / template-driven):")
        for ex in dyn_examples[:5]:
            lines.append("- `{0}` → `{1}`  (type: {2})".format(
                ex.get("source", "?"), ex.get("import", "?"), ex.get("type", "?")))
    note = summary.get("note")
    if note:
        lines.append("")
        lines.append("> {0}".format(note))
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# File tree (the primary human/agent view of project shape)
# ---------------------------------------------------------------------------

def _clean_reason(reason: str) -> Optional[str]:
    """Normalise a health reason into a short description, or None for
    auto-yellow boilerplate (it describes the tracking system, not the file)."""
    reason = re.sub(r"\s+", " ", str(reason or "")).strip()
    if not reason or reason.startswith("mtime changed") or "auto-detected" in reason:
        return None
    return (reason[:90] + "…") if len(reason) > 91 else reason


def _load_health_descriptions(root: Path) -> Dict[str, str]:
    """file -> short description, from file_health.json or file_health.md.

    Projects maintained through the shell workflow only have the .md table
    (the JSON is written by the Python health module), so both are read.
    """
    desc: Dict[str, str] = {}
    try:
        with open(root / "file_health.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", data) if isinstance(data, dict) else {}
        for file, e in entries.items():
            r = _clean_reason((e or {}).get("reason"))
            if r:
                desc[str(file)] = r
    except Exception:
        pass
    if desc:
        return desc
    try:  # .md fallback: | File | Status | Last Updated | Reason / Intent |
        with open(root / "file_health.md", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("|") or line.startswith("|--") or "| File | Status" in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 6 and parts[1]:
                    r = _clean_reason(parts[4])
                    if r:
                        desc[parts[1]] = r
    except Exception:
        pass
    return desc


TREE_DIR_FILE_CAP = 40      # files listed per directory before "… +N more"
TREE_TOTAL_LINE_CAP = 900   # hard ceiling so huge monorepos stay readable


def _generate_tree_section(root: Path, cache: Dict[str, Any]) -> List[str]:
    """Indented file tree of parsed + wiki-tracked files, with descriptions.

    The Mermaid graph shows *dependencies* (which reads as soup at monorepo
    scale); this tree is the readable answer to "what is in this project":

        wikifier/
        ├── parsers/
        │   ├── bree.py — barrel & re-export chain engine
        │   └── python.py
        └── cli.py — entry point + full update pipeline
    """
    descriptions = _load_health_descriptions(root)
    parsed = {k for k in cache.keys() if isinstance(k, str) and not k.startswith("_")}
    # Health keys are free text (audit records may use whole sentences as the
    # "file"; some entries point at directories): only real on-disk files —
    # or parser-confirmed ones — belong in the tree.
    tracked = set()
    for k in descriptions:
        k2 = k.rstrip("/")
        if not k2 or k2 in parsed:
            continue
        try:
            if (root / k2).is_file():
                tracked.add(k2)
        except OSError:
            continue
    files = sorted(parsed | tracked)
    if not files:
        return ["## File Tree", "", "```text",
                "(no files parsed yet — run update-maps)", "```", ""]

    # Nested {name: subtree}; directory keys end with '/', file leaves are None.
    tree: Dict[str, Any] = {}
    for path in files:
        node = tree
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = None

    def count_leaves(node: Dict[str, Any]) -> int:
        return sum(count_leaves(v) if isinstance(v, dict) else 1 for v in node.values())

    out: List[str] = []
    truncated = False

    def render(node: Dict[str, Any], prefix: str, path_prefix: str) -> None:
        nonlocal truncated
        dirs = sorted(k for k in node if k.endswith("/"))
        leaves = sorted(k for k in node if not k.endswith("/"))
        shown = leaves[:TREE_DIR_FILE_CAP]
        hidden = len(leaves) - len(shown)
        items = dirs + shown + (["\x00more"] if hidden > 0 else [])
        for i, name in enumerate(items):
            if len(out) >= TREE_TOTAL_LINE_CAP:
                truncated = True
                return
            last = i == len(items) - 1
            connector = "└── " if last else "├── "
            child_prefix = prefix + ("    " if last else "│   ")
            if name == "\x00more":
                out.append(prefix + connector + "… +{0} more files".format(hidden))
            elif name.endswith("/"):
                sub = node[name]
                n = count_leaves(sub)
                suffix = "  ({0} files)".format(n) if n > TREE_DIR_FILE_CAP else ""
                out.append(prefix + connector + name + suffix)
                render(sub, child_prefix, path_prefix + name)
            else:
                d = descriptions.get(path_prefix + name)
                out.append(prefix + connector + name + ((" — " + d) if d else ""))

    render(tree, "", "")

    lines = [
        "## File Tree", "",
        "> Every parsed/tracked file, organised by folder. Descriptions come from",
        "> the agent wiki (file_health). The dependency graph is further below.",
        "", "```text",
        "{0}/  ({1} files)".format(root.name, len(files)),
    ]
    lines.extend(out)
    if truncated:
        lines.append("… (tree capped at {0} lines — full file list lives in the import cache)".format(TREE_TOTAL_LINE_CAP))
    lines.extend(["```", ""])
    return lines


def generate_library_md(root: Path, cache: Dict[str, Any]) -> str:
    """Render library.md content from an import cache (see module docstring)."""
    if not isinstance(cache, dict):
        cache = {}
    edges = _collect_edges(cache)

    lines = [
        "# Library & Imports Map (auto-generated by wikifier update-maps)",
        "",
        "> This file is regenerated. Manual edits will be overwritten.",
        '> Run `wikifier record-change library.md "..."` if you need to annotate.',
        "",
    ]
    lines.extend(_generate_tree_section(root, cache))
    lines.extend(_generate_mermaid_section(edges))
    lines.extend(_generate_table_section(edges))
    lines.extend(_generate_cycles_section(cache))
    lines.extend(_generate_acs_section(cache))
    lines.extend(_generate_reverse_section(cache))
    lines.extend(_generate_barrel_section(cache))
    lines.extend(_generate_conditional_dynamic_section(cache))
    return "\n".join(lines).rstrip() + "\n"


def _graph_stats(cache: Dict[str, Any]) -> Tuple[int, int]:
    """Return (node_count, edge_count) for the deduplicated dependency graph."""
    edges = _collect_edges(cache)
    nodes = set()
    for src, _raw, target, _conf, _internal in edges:
        nodes.add(src)
        nodes.add(target)
    return len(nodes), len(edges)


def write_library_md(root: Path, cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generate and atomically write <root>/library.md.

    Loads the cache via wikifier.import_cache.load_cache when not supplied.
    Writes via library.md.tmp + os.replace so a failed build never destroys
    the previous artifact. Returns {"success", "path", "nodes", "edges"} and
    "error" on operational failure.
    """
    root = Path(root)
    out_path = root / "library.md"
    result = {"success": False, "path": str(out_path), "nodes": 0, "edges": 0}
    try:
        if cache is None:
            from wikifier.import_cache import load_cache
            cache = load_cache(root)
        if not isinstance(cache, dict):
            cache = {}
        content = generate_library_md(root, cache)
        nodes, edges = _graph_stats(cache)
        tmp_path = out_path.with_name(out_path.name + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(out_path))
        result.update({"success": True, "nodes": nodes, "edges": edges})
    except Exception as exc:  # operational failure -> structured error
        result["error"] = "{0}: {1}".format(type(exc).__name__, exc)
    return result


if __name__ == "__main__":
    # Self-check: render from a known real-world cache without touching it.
    import json
    import tempfile

    sample = Path("/home/aron/Documents/coding_projects/RecipeLab_alt"
                  "/.wikifier_staging/import_cache.json")
    if not sample.exists():
        print("self-check skipped: sample cache not found at", sample)
    else:
        with open(str(sample), "r", encoding="utf-8") as fh:
            sample_cache = json.load(fh)
        node_count, edge_count = _graph_stats(sample_cache)
        content = generate_library_md(sample.parent.parent, sample_cache)
        print("self-check: nodes={0} edges={1} chars={2}".format(
            node_count, edge_count, len(content)))
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as tmp:
            tmp.write(content)
            print("self-check: wrote preview to", tmp.name)
        assert "```mermaid" in content and content.count("```") >= 2
        assert "## Resolved Dependencies" in content
        print("self-check: OK")
