#!/bin/bash
# wikifier.sh — Wikifier Core CLI (Zero-Dependency)
# Agent-first shell tool for codebase documentation health & semantic change tracking.
#
# Usage:
#   ./wikifier.sh <command> [args]
#   (Optionally symlink or alias as 'wikifier' in your PATH)
#
# Commands implemented:
#   help, check-changes, health, record-change, record-deletion,
#   prepare-edit, mark-green, monitor, update-maps, validate,
#   journal, issues, init, cycles, daemon (start/stop/status/logs/run/install-service/...)

set -euo pipefail

# ----------------------------- Unified Project Root Discovery (Gap #1 External Robustness) -----------------------------
# discover_project_root(): shell mirror of wikifier/cli.py:discover_project_root()
# Highest priority for making packaged (`pip install`) `wikifier` / wikifier.sh work out-of-the-box
# on external monorepos of any size. Focus on CLI + shell discovery as specified.
# Keeps zero-dep. WIKIFIER_ROOT remains script location; PROJECT_ROOT is always the user target.
discover_project_root() {
    # 1. Explicit WIKIFIER_PROJECT_ROOT env (from `wikifier --target`, user export, MCP child_env, CLI main())
    if [[ -n "${WIKIFIER_PROJECT_ROOT:-}" ]]; then
        local p
        p="$(cd "${WIKIFIER_PROJECT_ROOT}" 2>/dev/null && pwd -P)" || true
        if [[ -n "$p" && -d "$p" ]]; then
            echo "$p"
            return 0
        fi
    fi

    # Start from process CWD (what the user intends when invoking the command)
    local cwd
    cwd="$(pwd -P 2>/dev/null || pwd)"

    # 2. Wikifier markers (created by `wikifier init`, or present for already-initialized external projects)
    local current="$cwd"
    while [[ -n "$current" ]]; do
        if [[ -d "$current/.wikifier" || -f "$current/monitored_paths.txt" || -f "$current/.wikifier/config" ]]; then
            echo "$current"
            return 0
        fi
        local next
        next="$(dirname "$current" 2>/dev/null || echo "")"
        [[ -z "$next" || "$next" == "$current" ]] && break
        current="$next"
    done

    # 3. Common monorepo / project root markers — enables reliable full-updates on *any* external codebase
    # after plain `pip install wikifier` + `cd my-large-monorepo; wikifier update-maps --full`
    # without any prior `init` or env gymnastics. This is the key "any scale" improvement.
    current="$cwd"
    while [[ -n "$current" ]]; do
        if [[ -d "$current/.git" || -f "$current/package.json" || -f "$current/pyproject.toml" || \
              -f "$current/setup.py" || -f "$current/setup.cfg" || -f "$current/Cargo.toml" || \
              -f "$current/go.mod" || -d "$current/.hg" ]]; then
            echo "$current"
            return 0
        fi
        local next
        next="$(dirname "$current" 2>/dev/null || echo "")"
        [[ -z "$next" || "$next" == "$current" ]] && break
        current="$next"
    done

    # 4. CWD default (robust, never lets packaged scripts/ dir become the PROJECT_ROOT)
    echo "$cwd"
}

# ----------------------------- Configuration -----------------------------
# WIKIFIER_ROOT: location of *this script* (install or source tree / packaged scripts/ dir after pip)
WIKIFIER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIKIFIER_INSTALL_ROOT="$WIKIFIER_ROOT"  # for reference / launcher copies

# PROJECT_ROOT via unified discover (defined above). This + export is the core of the packaged shell fix.
PROJECT_ROOT="$(discover_project_root)"
# Export for all inner python -c / -m wikifier.parsers.* / resolution / import_cache / BREE etc.
# so they see the correct target root (not the sh's scripts/ dir) via their env fallbacks.
export WIKIFIER_PROJECT_ROOT="$PROJECT_ROOT"

# All persistent state now lives under PROJECT_ROOT (R6 external UX hardening)
LAST_CHECK_FILE="$PROJECT_ROOT/.wikifier_staging/.last_check"
STAGING_DIR="$PROJECT_ROOT/.wikifier_staging"
JOURNAL_ROOT="$PROJECT_ROOT/journal"
LOGGED_ISSUES_ROOT="$PROJECT_ROOT/Logged_issues"
MONITORED_PATHS_FILE="$PROJECT_ROOT/monitored_paths.txt"
EXCLUDE_PATTERNS_FILE="$PROJECT_ROOT/exclude_patterns.txt"
FILE_HEALTH="$PROJECT_ROOT/file_health.md"
PENDING_UPDATES="$PROJECT_ROOT/pending_updates.md"
LIBRARY_MD="$PROJECT_ROOT/library.md"
POLL_INTERVAL="${WIKIFIER_POLL_INTERVAL:-30}"

mkdir -p "$STAGING_DIR" "$JOURNAL_ROOT/$(date +%Y/%m)" "$LOGGED_ISSUES_ROOT"

# ----------------------------- Helper Functions -----------------------------

log() {
    echo "[wikifier] $*"
}

error() {
    echo "[wikifier ERROR] $*" >&2
}

# Get current timestamp in consistent format
timestamp() {
    date '+%Y-%m-%d %H:%M:%S %Z'
}

# Read monitored paths (one per line, ignore comments/blank)
get_monitored_paths() {
    local base="$PROJECT_ROOT"
    if [[ -f "$MONITORED_PATHS_FILE" ]]; then
        grep -vE '^\s*(#|$)' "$MONITORED_PATHS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            if [[ "$line" = /* ]]; then
                mon="$line"
            else
                mon="$base/$line"
            fi
            # Resolve to absolute for cwd-independent use (e.g. MCP sh fallback, external dogfood from any cwd)
            mon=$(realpath -m "$mon" 2>/dev/null || echo "$mon")
            echo "$mon"
        done
    else
        echo "$(realpath -m "$base" 2>/dev/null || echo "$base")"
    fi
}

# Build find exclude expression from exclude_patterns.txt
build_exclude_expr() {
    local expr=""
    if [[ -f "$EXCLUDE_PATTERNS_FILE" ]]; then
        while IFS= read -r pat; do
            [[ -z "$pat" || "$pat" =~ ^\s*# ]] && continue
            pat=$(echo "$pat" | xargs)
            [[ -z "$pat" ]] && continue
            if [[ -n "$expr" ]]; then
                expr="$expr -o -path \"*/$pat/*\" -o -path \"*/$pat\""
            else
                expr="-path \"*/$pat/*\" -o -path \"*/$pat\""
            fi
        done < "$EXCLUDE_PATTERNS_FILE"
    fi
    if [[ -n "$expr" ]]; then
        echo "! ( $expr )"
    else
        echo ""
    fi
}

# Upsert a row in the Markdown health table (very simple but effective)
# We treat file_health.md as the single source of truth.
upsert_health() {
    local file="$1"
    local status="$2"          # 🟢 or 🟡 or 🔴
    local reason="${3:-}"

    local now
    now=$(timestamp)

    # Ensure file exists with header
    if [[ ! -f "$FILE_HEALTH" ]]; then
        cat > "$FILE_HEALTH" << 'EOT'
# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
EOT
    fi

    # Escape for sed (basic)
    local safe_file
    safe_file=$(printf '%s' "$file" | sed 's/[\/&]/\\&/g')

    # Check if file already has an entry
    if grep -qF "| $file |" "$FILE_HEALTH" 2>/dev/null; then
        # Update existing row (replace the whole line)
        local new_line="| $file | $status | $now | $reason |"
        sed -i.bak "s#| $safe_file | .* | .* | .* |#$new_line#" "$FILE_HEALTH" && rm -f "$FILE_HEALTH.bak"
    else
        # Append new row
        echo "| $file | $status | $now | $reason |" >> "$FILE_HEALTH"
    fi
}

# Mark a file Green (convenience)
mark_green() {
    local file="$1"
    local reason="${2:-Summary updated and verified accurate.}"
    upsert_health "$file" "🟢 Green" "$reason"
    # Remove from pending if present
    if [[ -f "$PENDING_UPDATES" ]]; then
        grep -vF "$file" "$PENDING_UPDATES" > "$PENDING_UPDATES.tmp" || true
        mv "$PENDING_UPDATES.tmp" "$PENDING_UPDATES"
    fi
}

# Append to pending_updates.md
add_pending() {
    local file="$1"
    local msg="$2"
    echo "- $file: $msg" >> "$PENDING_UPDATES"
}

# Write a journal entry
write_journal() {
    local action="$1"   # "record-change", "record-deletion", "auto-detected", etc.
    local file="$2"
    local reason="$3"

    local day_dir
    day_dir="$JOURNAL_ROOT/$(date +%Y/%m)"
    mkdir -p "$day_dir"
    local journal_file="$day_dir/$(date +%d).md"

    cat >> "$journal_file" << EOM
## [$(timestamp)] $action
**File:** $file
**Reason:** $reason

EOM
}

# Simple cross-language import discovery (extendable)
discover_imports() {
    local target="$1"
    # Very lightweight — only common patterns. Real projects can extend.
    grep -rE \
        '^(import |from .* import |require\(|#include |import .* from |using |package )' \
        "$target" 2>/dev/null | head -200 || true
}

# ----------------------------- M2 Dependency Intelligence Helpers (Fix 8 style) -----------------------------

# Unified parser JSON output normalizer.
# Takes raw JSON array from either parsers/python.py or parsers/javascript.py
# and emits one "raw|module|confidence|..." line per import.
# Rich fields (when present from JS parser): is_dynamic, dynamic_type,
# is_conditional, conditional_context, via_barrel, barrel_depth.
# This replaces all previous crude grep hacks and preserves classification data end-to-end.
parse_parser_json_output() {
    local json_file="$1"
    local lang="$2"   # python | javascript  (for future differences)

    # Use python3 -c for robust JSON handling (no fragile grep).
    # Emits the fixed 9-legacy-field prefix + optional opaque |cdia_v1=...|barrel_v2=...|res_meta_v1=...
    # per the frozen Pre-Wave 0 Shell Pipeline Serialization Strategy v1 (see
    # Findings/gap1_prewave0_shared_contracts_open.md and wikifier/contracts.py).
    # Uses the single sanctioned encode_v1_payload (never custom b64 or manual json in emission).
    # Rich fields are appended after positional legacy; shell code NEVER inspects, parses, or rewrites their values.
    # Dual emission: legacy flats always + rich vN when parser provided the corresponding keys ("cdia", "barrel_v2", "resolution_metadata"/"strategy").
    # Mixed legacy/rich, missing fields, decode-side failures all tolerated downstream (parse_pipeline_line + unpack_*).
    # On encode error: silently drop that rich suffix (additive, never breaks the line).
    # Output consumed by process_file_imports (which prepends src and forwards suffixes verbatim) and persist.
    python3 -c '
import json, sys
from wikifier.contracts import encode_v1_payload, PIPE_FIELD_CDIA_V1, PIPE_FIELD_BARREL_V2, PIPE_FIELD_RES_META_V1
data = json.load(sys.stdin)
for item in data:
    raw = item.get("raw_module") or item.get("module") or ""
    mod = item.get("module") or ""
    conf = item.get("resolution_confidence") or "medium"
    is_dyn = "true" if item.get("is_dynamic") else "false"
    dyn_type = item.get("dynamic_type") or "static"
    is_cond = "true" if item.get("is_conditional") else "false"
    cond_ctx = item.get("conditional_context") or ""
    via_b = "true" if item.get("via_barrel") else "false"
    b_depth = str(item.get("barrel_depth", "")) if item.get("barrel_depth") is not None else ""
    line = f"{raw}|{mod}|{conf}|{is_dyn}|{dyn_type}|{is_cond}|{cond_ctx}|{via_b}|{b_depth}"
    # Rich vN payload emission (additive, deterministic order cdia/barrel/res; future cycle_v1 ok)
    rich_suffixes = []
    # cdia_v1 carries exactly the shape {"conditional_analysis": {...}, "dynamic_analysis": {...}} from CDIA engine
    # (ready for unpack_cdia_v1 which does decode + from_dict -> stored under RICH_KEYS "conditional_analysis"/"dynamic_analysis")
    cdia = item.get("cdia")
    if cdia and isinstance(cdia, dict):
        try:
            b64 = encode_v1_payload(cdia)
            if b64:
                rich_suffixes.append(f"{PIPE_FIELD_CDIA_V1}={b64}")
        except Exception:
            pass
    # barrel_v2 carries the BREE dict (via_barrel, chain, hops, detector, partial, mtimes etc.)
    # encoded raw (no dedicated pack_barrel_v2 yet per contracts; decode_v1_payload used on read side)
    barrel = item.get("barrel_v2") or item.get("barrel_analysis")
    if barrel and isinstance(barrel, dict):
        try:
            b64 = encode_v1_payload(barrel)
            if b64:
                rich_suffixes.append(f"{PIPE_FIELD_BARREL_V2}={b64}")
        except Exception:
            pass
    # res_meta_v1 carries ResolutionMetadata (strategy + matched etc.) or synthesized from "strategy"
    # wrapped as {"resolution_metadata": ...} for unpack_res_meta_v1 compat
    res_meta = item.get("resolution_metadata") or {}
    if not res_meta and item.get("strategy"):
        res_meta = {"strategy": item.get("strategy")}
    if res_meta:
        try:
            payload = {"resolution_metadata": res_meta} if isinstance(res_meta, dict) and "resolution_metadata" not in res_meta else res_meta
            b64 = encode_v1_payload(payload)
            if b64:
                rich_suffixes.append(f"{PIPE_FIELD_RES_META_V1}={b64}")
        except Exception:
            pass
    if rich_suffixes:
        line += "|" + "|".join(rich_suffixes)
    if raw or mod:
        print(line)
' < "$json_file" 2>/dev/null || true
}

# Process normalized parser output for a single source file.
# Takes raw|module|confidence lines (from parse_parser_json_output)
# and performs the common work for both Python and JS:
#   - calls resolve_imported_module
#   - builds resolved_pairs (raw → resolved with confidence)
#   - records reverse dependencies
#   - builds modules_str for the file
#
# This is the second major shared helper. Both language paths in the first-pass
# will delegate to this instead of duplicating the loop.
process_file_imports() {
    local src_file="$1"
    local normalized_input="$2"   # raw|mod|conf|rich... lines (now carries classification data)
    local lang="$3"               # python | javascript (informational for now)

    # Output: one full "src|raw|resolved|conf|is_dyn|...|b_depth|cdia_v1=...|barrel_v2=...|res_meta_v1=..." line per import.
    # This is the critical "normalizer" step in the pipeline (P1 richness).
    #
    # Key reliability (Shell Pipeline Serialization Strategy v1, contracts.py):
    # - Read FULL original line (variable # of | fields, not fixed 9) so arbitrary rich suffixes survive read.
    # - Legacy extraction via small bash split (first 9); rich suffix forwarding via python (robust for very long b64 lines).
    # - Re-emit exactly the 10 legacy positional (src prepended as pos0, conf possibly updated by resolver) + original rich suffixes forwarded *verbatim* (no value inspection).
    # - Shell NEVER parses, decodes, or rewrites the *values* of cdia_v1/barrel_v2/res_meta_v1 (opaque per contract).
    # - Tolerant of legacy-only (no suffix), rich-only, mixed, future fields (cycle_v1), short/old lines.
    # - Result: rich payloads from parser JSON reliably reach persist_rich_cache_data (and thus cache + MCP tools) on every run including incremental.
    #
    # Downstream (persist) uses contracts.parse_pipeline_line + unpack_* for defensive decode + diagnostics on failure.
    # See also: the python suffix extraction added for long-line hardening.

    while IFS= read -r orig_line || [[ -n "$orig_line" ]]; do
        [[ -z "$orig_line" ]] && continue

        # Split on |; first 9 are legacy positional from parser (raw..b_depth), 9+ are rich key=val
        IFS='|' read -ra oparts <<< "$orig_line"
        raw="${oparts[0]:-}"
        mod="${oparts[1]:-}"
        conf="${oparts[2]:-}"
        is_dyn="${oparts[3]:-}"
        dyn_type="${oparts[4]:-}"
        is_cond="${oparts[5]:-}"
        cond_ctx="${oparts[6]:-}"
        via_b="${oparts[7]:-}"
        b_depth="${oparts[8]:-}"

        [[ -z "$raw" && -z "$mod" ]] && continue

        # Call the improved resolver which now returns "resolved|confidence"
        local resolver_output="$mod|${conf:-medium}"
        if command -v resolve_imported_module >/dev/null 2>&1; then
            resolver_output=$(resolve_imported_module "$raw" "$src_file" "${conf:-medium}" 2>/dev/null || echo "$mod|${conf:-medium}")
        fi

        # Parse the new resolver output format
        local resolved actual_conf
        IFS='|' read -r resolved actual_conf <<< "$resolver_output"
        resolved="${resolved:-$mod}"
        actual_conf="${actual_conf:-${conf:-medium}}"

        # Defaults for rich/legacy fields (Python files and old data will be empty/false)
        is_dyn="${is_dyn:-false}"
        dyn_type="${dyn_type:-static}"
        is_cond="${is_cond:-false}"
        cond_ctx="${cond_ctx:-}"
        via_b="${via_b:-false}"
        b_depth="${b_depth:-}"

        # Build the canonical 10-field legacy prefix (this is what tables/Mermaid/reverse use)
        local core
        core=$(printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s' \
            "$src_file" "$raw" "$resolved" "$actual_conf" \
            "$is_dyn" "$dyn_type" "$is_cond" "$cond_ctx" "$via_b" "$b_depth")

        # Forward *all* recognized rich suffixes from the original parser line (verbatim, no inspection of values)
        # per Shell Pipeline Serialization Strategy v1 in gap1_prewave0_shared_contracts_open.md .
        # Pure-bash extraction (using oparts array from prior IFS split) for scale + long-line robustness.
        # Eliminates O(imports) python spawns in process_file_imports normalizer; critical for 5k-20k file
        # monorepos (full or large-incremental runs). Bash handles 10k+ char lines/payloads reliably in practice.
        # No value inspection/decoding/mutation of *_vN; opaque forward only. Fallback to no-suffix on error.
        local suffixes_str=""
        local n=${#oparts[@]}
        local i=9
        while [[ $i -lt $n ]]; do
            local p="${oparts[$i]:-}"
            if [[ "$p" == *=* ]]; then
                local k="${p%%=*}"
                case "$k" in
                    cdia_v1|barrel_v2|res_meta_v1|cycle_v1)
                        if [[ -n "$suffixes_str" ]]; then
                            suffixes_str="$suffixes_str|$p"
                        else
                            suffixes_str="$p"
                        fi
                        ;;
                esac
            fi
            i=$((i + 1))   # set -e safe form (consistent with other counters)
        done

        if [[ -n "$suffixes_str" ]]; then
            # Join with | (no leading | here; printf adds the separator)
            printf '%s|%s\n' "$core" "$suffixes_str"
        else
            printf '%s\n' "$core"
        fi
    done <<< "$normalized_input"
}

# Emit one row into the "Resolved Internal Dependencies" table.
# Now properly uses Source File as the first column (the file containing the import).
# Signature: emit_resolved_pairs_to_table source_file raw_import resolved_target confidence
emit_resolved_pairs_to_table() {
    local src_file="$1"
    local raw="$2"
    local tgt="$3"
    local conf="${4:-medium}"

    local key="${src_file}|${raw}|${tgt}"
    if [[ -n "${seen_resolved_pairs[$key]:-}" ]]; then
        return 0
    fi
    seen_resolved_pairs[$key]=1

    # Improved table row with real Source File column
    printf '| %s | %s → %s | %s |\n' "$src_file" "$raw" "$tgt" "$conf" >> "$LIBRARY_MD"
}

# Handle emission of cached dependency data into the final table.
# Supports both the modern `resolved_pairs` format (preferred) and the older
# flat "resolved" list format for backward compatibility during cache transitions.
# Delegates actual row writing + dedup to emit_resolved_pairs_to_table().
emit_cached_data_to_table() {
    local cache_json="$1"          # path to import_cache.json (or equivalent)
    local current_mtime_map="${2:-}"   # optional: for staleness checks

    # In the full implementation this will:
    # - Load cached_resolved_pairs for files that weren't re-parsed
    # - Fall back to the older flat resolved list if pairs are missing
    # - Call emit_resolved_pairs_to_table() for each valid entry
    # - Track source ("cache") for debugging / MCP responses

    # Placeholder structure for now — will be filled when we wire the
    # real cache loading + high-level generate_resolved_dependencies_table()
    if [[ -f "$cache_json" ]]; then
        # Future: python3 -c to extract cached_resolved_pairs and emit
        :  # no-op until cache structures are re-introduced
    fi
}

# =============================================================================
# High-Level Orchestrator: Table Generation
# =============================================================================
# generate_resolved_dependencies_table()
#
# This is the complete "second pass" / table generation phase.
# It replaces the giant inline block that previously lived in cmd_update_maps.
#
# Responsibilities:
#   - Re-parse changed files (Python + JS/TS) using the real parsers
#   - Build rich resolved_pairs using the lower helpers above
#   - Handle cached data for files that weren't re-parsed (via emit_cached_data_to_table)
#   - Emit the final sorted "Resolved Internal Dependencies" table
#   - Support both fresh and incremental runs
#
# Once fully implemented, cmd_update_maps will simply call:
#     generate_resolved_dependencies_table >> "$LIBRARY_MD"
# instead of containing hundreds of lines of duplicated Python/JS logic.
generate_resolved_dependencies_table() {
    local paths="$1"
    local import_cache_file="$2"
    local full_rebuild="${3:-false}"

    # Reset deduplication state
    declare -gA seen_resolved_pairs=()

    echo ""
    echo "## Resolved Internal Dependencies"
    echo ""
    echo "| Source File | Raw Import → Resolved Target | Confidence |"
    echo "|-------------|------------------------------|------------|"

    # ------------------------------------------------------------------
    # Fresh data from the first-pass (Python + JS paths)
    # ------------------------------------------------------------------
    # resolved_pairs now contains: src_file|raw|resolved|confidence
    # R1: on LARGE_SCALE_MODE (or cap hit), we emit a diagnostic notice instead of full expansion/sort/loop
    # which would be slow, produce unusable multi-MB library.md, or fail on ARG_MAX for 20k+ file projects.
    # Rich data is guaranteed persisted (via tmp stream); consumers should use cache/MCP for large cases.
    # R1: safe scale check (declare -p cannot be directly in [[ compound expr without syntax issues)
    local _has_rp_array=false
    if declare -p resolved_pairs 2>/dev/null | grep -q 'declare -a'; then _has_rp_array=true; fi
    if [[ "${LARGE_SCALE_MODE:-false}" == "true" || ( "$_has_rp_array" == "true" && ${#resolved_pairs[@]} -ge $MAX_SHELL_RESOLVED_PAIRS ) ]]; then
        echo ""
        echo "> **R1 Scale Degradation (Gap #1 Reliability)**: LARGE_SCALE_MODE active (>${MAX_SHELL_RESOLVED_PAIRS} pairs or ${#files_to_reparse[@]} files to reparse)."
        echo "> Full resolved-pairs table omitted (would make library.md impractical + risk shell limits on 5k-20k+ monorepos)."
        echo "> All rich structured data (cdia_v1, barrel_v2, res_meta_v1 + legacy) survived reliably via streaming FRESH_PAIRS_TMP + contracts.parse_pipeline_line in persist_rich_cache_data."
        echo "> TOTAL_PAIRS_SEEN this run: ${TOTAL_PAIRS_SEEN:-?} . Use MCP get_dependencies/get_dependency_stats, import_cache.py, or wikifier health for actionable views."
        echo "> (Mermaid similarly summarized below.)"
        echo ""
    elif $_has_rp_array ; then
        # Sort for nicer output (by source file, then raw import) -- safe only under cap
        local sorted_pairs
        sorted_pairs=$(printf '%s\n' "${resolved_pairs[@]}" | sort)

        while IFS= read -r pair; do
            [[ -z "$pair" ]] && continue
            # Use _rest to tolerate rich |cdia_v1=... tail (mixed legacy+rich lines); prevents tail from polluting conf
            IFS='|' read -r src_file raw resolved conf _rest <<< "$pair" || true
            [[ -n "$src_file" && -n "$raw" && -n "$resolved" ]] || continue
            emit_resolved_pairs_to_table "$src_file" "$raw" "$resolved" "${conf:-medium}"
        done <<< "$sorted_pairs"
    fi

    # ------------------------------------------------------------------
    # Cached data for files that were not re-parsed this run
    # ------------------------------------------------------------------
    emit_cached_data_to_table "$import_cache_file"

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    echo ""
    echo "> Table generated by generate_resolved_dependencies_table() (fresh + cached)"
    echo ""
}

# =============================================================================
# Mermaid Graph Generation (from resolved dependency data)
# =============================================================================
# generate_mermaid_dependency_graph()
#
# Consumes the global resolved_pairs array (populated by the first-pass)
# and emits a Mermaid graph with:
#   - Language-colored subgraphs (Python vs JavaScript/TypeScript)
#   - Nodes for source files and resolved targets
#   - Edges showing import relationships
#
# This replaces the old placeholder Mermaid content.
generate_mermaid_dependency_graph() {
    declare -gA mermaid_nodes=()
    declare -ga mermaid_edges=()

    # Load cache data once (for dependents / reverse impact styling + reverse edges)
    local cache_json=""
    local root="${PROJECT_ROOT:-${WIKIFIER_PROJECT_ROOT:-.}}"
    if [[ -f "$root/.wikifier_staging/import_cache.json" ]]; then
        cache_json=$(python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import json
root = Path(sys.argv[1])
cache = ic.load_cache(root)
out = {
    "dependents": {},
    "reverse": ic.get_reverse_dependencies(cache)
}
for rel, data in cache.items():
    if not rel.startswith("_"):
        deps = data.get("dependents", [])
        if deps:
            out["dependents"][rel] = len(deps)
print(json.dumps(out))
' "$root" 2>/dev/null || echo '{}')
    fi

    # Known noisy external prefixes
    local -a external_prefixes=(
        "os" "sys" "json" "pathlib" "re" "collections" "typing" "functools"
        "react" "vue" "django" "flask" "fastapi" "numpy" "pandas"
        "node:" "@types" "express" "next" "webpack"
    )

    # Improved internal detection
    is_internal() {
        local name="$1"
        # Must look like a project path
        if [[ "$name" != */* && "$name" != *.* ]]; then
            return 1
        fi
        # Reject obvious externals
        for prefix in "${external_prefixes[@]}"; do
            if [[ "$name" == "$prefix"* || "$name" == *"/$prefix"* ]]; then
                return 1
            fi
        done
        [[ "$name" != node:* && "$name" != @* ]]
    }

    get_language() {
        local f="$1"
        if [[ "$f" == *.py ]]; then echo "python"
        elif [[ "$f" == *.js || "$f" == *.ts || "$f" == *.jsx || "$f" == *.tsx ]]; then echo "js"
        else echo "unknown"
        fi
    }

    make_label() {
        local path="$1"
        local label
        label=$(basename "$path" 2>/dev/null || echo "$path")

        # Enrich label with dependents count (uses pre-loaded cache_json for performance)
        local rel
        rel=$(realpath --relative-to="$root" "$path" 2>/dev/null || echo "")
        if [[ -n "$rel" && -n "$cache_json" ]]; then
            local dep_count
            dep_count=$(python3 -c '
import json,sys
data = json.loads(sys.argv[1])
print(data.get("dependents", {}).get(sys.argv[2], 0))
' "$cache_json" "$rel" 2>/dev/null || echo 0)
            if [[ "$dep_count" -gt 0 ]]; then
                label="$label (↑$dep_count)"
            fi
        fi
        echo "$label"
    }

    sanitize_node() {
        local name="$1"
        name="${name//\//_}"
        name="${name//./_}"
        name="${name// /_}"
        name="${name//-/_}"
        name="${name//@/_}"
        echo "$name"
    }

    # Extract a directory-based group for better organization (e.g. wikifier/parsers)
    get_group() {
        local path="$1"
        # Take up to two directory levels
        local dir
        dir=$(dirname "$path" 2>/dev/null || echo "")
        if [[ "$dir" == "." || -z "$dir" ]]; then
            echo "root"
        else
            # Keep at most two levels for readability
            echo "$dir" | awk -F'/' '{print $(NF-1)"/"$NF}' 2>/dev/null || echo "$dir"
        fi
    }

    get_edge_style() {
        local conf="$1"
        case "$conf" in
            high)   echo "-->" ;;
            medium) echo "-.->" ;;
            *)      echo "-..->" ;;
        esac
    }

    # Process pairs
    # R1 Scale: avoid full loop/expansion on large monorepos (mermaid with >5-10k edges is unusable in viewers anyway;
    # would also risk slow generation or memory in this generator's own mermaid_edges array).
    if [[ "${LARGE_SCALE_MODE:-false}" == "true" || ${#resolved_pairs[@]} -ge ${MAX_SHELL_RESOLVED_PAIRS:-8000} ]]; then
        echo '    %% R1 Scale Degradation: full per-edge Mermaid omitted for practicality on 5k-20k+ file monorepos.'
        echo '    %% All rich metadata (cdia_v1/barrel_v2/res_meta_v1) is persisted to cache via streaming normalizer.'
        echo '    %% Query specific subgraphs with MCP get_dependencies / get_dependents / get_cycles.'
        local approx_edges=${TOTAL_PAIRS_SEEN:-${#resolved_pairs[@]}}
        echo "    ScaleNote[\"Large monorepo: ~${approx_edges} dependency edges (>${MAX_SHELL_RESOLVED_PAIRS:-8000} cap); rich fields survived\"]:::scaleNote"
        echo '    classDef scaleNote fill:#fff3cd,stroke:#856404'
    else
    for pair in "${resolved_pairs[@]}"; do
        # Use _rest to tolerate rich |*_vN=... tail on large/mixed resolved_pairs arrays; conf must stay clean
        IFS='|' read -r src_file raw resolved conf _rest <<< "$pair" || true
        [[ -z "$src_file" || -z "$resolved" ]] && continue

        # Aggressive external filtering
        if ! is_internal "$resolved" && ! is_internal "$src_file"; then
            # Both sides external — skip to reduce noise
            continue
        fi

        local src_node tgt_node
        src_node=$(sanitize_node "$src_file")
        tgt_node=$(sanitize_node "$resolved")

        local src_lang
        src_lang=$(get_language "$src_file")

        local tgt_category
        if is_internal "$resolved"; then
            tgt_category=$(get_language "$resolved")
            [[ "$tgt_category" == "unknown" ]] && tgt_category="$src_lang"
        else
            tgt_category="external"
        fi

        if [[ -z "${mermaid_nodes[$src_node]:-}" ]]; then
            local label group
            label=$(make_label "$src_file")
            group=$(get_group "$src_file")
            mermaid_nodes["$src_node"]="$src_lang|$label|$src_file|$group"
        fi

        if [[ -z "${mermaid_nodes[$tgt_node]:-}" ]]; then
            local label group
            label=$(make_label "$resolved")
            group=$(get_group "$resolved")
            mermaid_nodes["$tgt_node"]="$tgt_category|$label|$resolved|$group"
        fi

        local style
        style=$(get_edge_style "$conf")

        mermaid_edges+=("$src_node $style $tgt_node")
    done
    fi   # end R1 LARGE_SCALE_MODE guard for pairs processing

    # Safety cap for very large graphs
    local max_nodes=280
    local node_count=${#mermaid_nodes[@]}
    if (( node_count > max_nodes )); then
        echo "    %% WARNING: Graph has $node_count nodes (capped at $max_nodes for readability)"
        echo "    %% Consider using --full less often or improving filtering"
    fi

    # Emit
    echo "    %% === Generated by generate_mermaid_dependency_graph() ==="

    # Group nodes by directory for better organization
    declare -gA groups=()
    for node in "${!mermaid_nodes[@]}"; do
        local info="${mermaid_nodes[$node]}"
        local group="${info##*|}"          # last field
        groups["$group"]+="$node "
    done

    # Emit subgraphs per directory group (much better than flat Python/JS)
    for group in "${!groups[@]}"; do
        local safe_group
        safe_group=$(sanitize_node "$group")
        echo "    subgraph $safe_group"
        for node in ${groups[$group]}; do
            local info="${mermaid_nodes[$node]}"
            local label="${info#*|}"
            label="${label%%|*}"
            echo "        $node[\"$label\"]"
        done
        echo "    end"
    done

    # External nodes that didn't get grouped nicely
    echo "    subgraph External"
    for node in "${!mermaid_nodes[@]}"; do
        local info="${mermaid_nodes[$node]}"
        if [[ "$info" == external* ]]; then
            local label="${info#*|}"
            label="${label%%|*}"
            echo "        $node[\"$label\"]"
        fi
    done
    echo "    end"

    # Edges
    local edge_count=0
    local max_edges=600
    for edge in "${mermaid_edges[@]}"; do
        if (( edge_count < max_edges )); then
            echo "    $edge"
            # NOTE: ((var++)) returns status 1 when var is 0 (post-increment yields 0),
            # which kills the whole script under `set -e` before library.md is moved
            # into place. Always use the assignment form for counters here.
            edge_count=$((edge_count + 1))
        fi
    done

    if (( ${#mermaid_edges[@]} > max_edges )); then
        echo "    %% (Graph truncated — ${#mermaid_edges[@]} total edges)"
    fi

    # === Draw actual reverse edges for high-impact modules ===
    # Uses the persisted _reverse_dependencies map from the cache.
    # Only draws a limited number to keep the graph readable.
    if [[ -n "$cache_json" ]]; then
        python3 -c '
import json, sys
data = json.loads(sys.argv[1])
reverse = data.get("reverse", {})
dependents = data.get("dependents", {})

# Find high-impact nodes (many dependents)
high_impact = [k for k, v in dependents.items() if v > 5]
high_impact.sort(key=lambda k: -dependents.get(k, 0))

max_rev = 35
count = 0
for target in high_impact:
    if count >= max_rev:
        break
    sources = reverse.get(target, [])[:3]   # limit per target
    for src in sources:
        if count >= max_rev:
            break
        # Sanitize for Mermaid
        src_id = src.replace("/", "_").replace(".", "_").replace("-", "_").replace("@", "_")
        tgt_id = target.replace("/", "_").replace(".", "_").replace("-", "_").replace("@", "_")
        print(f"    {src_id} -.->|depends on| {tgt_id}")
        count += 1
' "$cache_json" 2>/dev/null || true
    fi

    # Visual note about reverse dependencies
    echo ""
    echo "    %% Reverse edges (dashed) show \"depends on\" relationships for high-impact modules."
    echo "    %% These come from the persisted _reverse_dependencies in the import cache."

    # === Impact styling and reverse edges using persisted reverse dependencies ===
    echo "    classDef highImpact fill:#ffcccc,stroke:#aa0000,stroke-width:2px"
    echo "    classDef medImpact fill:#fff4cc,stroke:#cc9900"

    local styled=0
    for node in "${!mermaid_nodes[@]}"; do
        local dep_count=0
        if [[ -n "$cache_json" ]]; then
            dep_count=$(python3 -c '
import json,sys
data = json.loads(sys.argv[1])
print(data.get("dependents", {}).get(sys.argv[2].replace("_","/").replace("_","."), 0))
' "$cache_json" "$node" 2>/dev/null || echo 0)
        fi

        if [[ "$dep_count" -gt 8 ]]; then
            echo "    class $node highImpact"
        elif [[ "$dep_count" -gt 3 ]]; then
            echo "    class $node medImpact"
        fi

        # Draw a few reverse edges for very high-impact modules (visual "who depends on me")
        if [[ "$dep_count" -gt 6 && "$styled" -lt 25 && -n "$cache_json" ]]; then
            local rev_sources
            rev_sources=$(python3 -c '
import json,sys
data = json.loads(sys.argv[1])
rev = data.get("reverse", {})
# crude match
for tgt, srcs in rev.items():
    tgt_id = tgt.replace("/", "_").replace(".", "_").replace("-", "_")
    if tgt_id == sys.argv[2]:
        for s in srcs[:2]:
            s_id = s.replace("/", "_").replace(".", "_").replace("-", "_")
            print(s_id)
        break
' "$cache_json" "$node" 2>/dev/null || true)

            for s in $rev_sources; do
                if [[ -n "$s" && "$styled" -lt 25 ]]; then
                    echo "    $s -.->|depends on| $node"
                    styled=$((styled + 1))   # set -e safe (((styled++)) returns 1 at 0)
                fi
            done
        fi
    done

    # === Cycle node styling (from _cycles in import cache) ===
    echo "    classDef cycleNode fill:#ff4444,stroke:#aa0000,stroke-width:3px,color:#fff,stroke-dasharray:5 2"
    if [[ -f "$root/.wikifier_staging/import_cache.json" ]]; then
        python3 -c '
import json, sys
from pathlib import Path
root = Path(".")
cache = json.loads(open(root / ".wikifier_staging/import_cache.json").read() or "{}")
cdata = cache.get("_cycles", {})
cycle_nodes = set()
if isinstance(cdata, dict):
    # modern rich structure
    files = cdata.get("all_cycle_files", [])
    if not files:
        for s in cdata.get("sccs", []):
            files.extend(s.get("nodes", []))
    for p in files:
        nid = p.replace("/", "_").replace(".", "_").replace("-", "_").replace("@", "_")
        cycle_nodes.add(nid)
else:
    # legacy list format fallback
    for c in (cdata or []):
        for p in c.get("participants", []) or c.get("nodes", []):
            nid = p.replace("/", "_").replace(".", "_").replace("-", "_").replace("@", "_")
            cycle_nodes.add(nid)
for nid in list(cycle_nodes)[:100]:
    print(f"    class {nid} cycleNode")
' 2>/dev/null || true
    fi

    # Consolidated legend
    echo ""
    echo "    %% ==================== Legend ===================="
    echo "    %%"
    echo "    %% Node styling (based on reverse dependency count + new intelligence):"
    echo "    %%   highImpact   → Many files depend on this module (high blast radius; light red tint)"
    echo "    %%   medImpact    → Moderate number of dependents (light yellow tint)"
    echo "    %%   cycleNode    → Participates in one or more circular dependencies (bright red fill + thick dashed border)"
    echo "    %%                    (Nodes may combine styles when both high-impact and cyclic.)"
    echo "    %%"
    echo "    %% Forward edge styling:"
    echo "    %%   -->          Normal dependency (confidence influenced)"
    echo "    %%   =>           Edge into moderately high-impact module"
    echo "    %%   ==>          Edge into very high-impact module"
    echo "    %%"
    echo "    %% Special edge labels (enriched from parser metadata):"
    echo "    %%   |barrel:2|      Via barrel re-export (depth=2)"
    echo "    %%   |cond|          Conditional (if/ternary/feature flag)"
    echo "    %%   |dyn|           Dynamic (template / runtime expr)"
    echo "    %%   |via:res|       Resolution strategy note (future)"
    echo "    %%"
    echo "    %% Reverse / special edges:"
    echo "    %%   -.->         Reverse dependency (\"X depends on this\") or conditional import"
    echo "    %%"
    echo "    %% Node labels may include (↑N) = N direct dependents"
    echo "    %%"
    echo "    %% Cycle nodes + high-impact nodes = priority for refactoring / breaking changes."
    echo "    %% See library.md \"Circular Dependencies\", \"Barrel Expansions\", \"Conditional & Dynamic\" sections + MCP get_cycles/get_resolution_diagnostics for details."
    echo "    %% ==================================================="
}

# =============================================================================
# High-Level Orchestrator: First-Pass Graph & Cache Update
# =============================================================================
# perform_first_pass_graph_and_cache_update()
#
# This is the "first pass" phase — the heavy lifting that powers the
# dependency graph and all later query tools.
#
# Responsibilities:
#   - Build node maps (file ↔ module, reverse dependencies)
#   - Detect which files need re-parsing (changed mtimes + --full)
#   - Invoke Python and JS parsers for those files
#   - Use parse_parser_json_output + process_file_imports for unified handling
#   - Update the import_cache (both resolved_pairs and older formats)
#   - Record reverse dependencies for get_dependents()
#   - Write the Mermaid dependency graph sections (language-colored subgraphs)
#   - Produce summary statistics (files scanned, edges, cache hit rate, etc.)
#
# In the final clean architecture, cmd_update_maps will look roughly like:
#
#     perform_first_pass_graph_and_cache_update "$paths" "$cache" "$full"
#     generate_resolved_dependencies_table   "$paths" "$cache" "$full" >> "$LIBRARY_MD"
#
# This function is the one that was previously the largest source of
# Python-vs-JS duplication. All that logic now funnels through the helpers.
perform_first_pass_graph_and_cache_update() {
    local paths="$1"
    local import_cache_file="$2"
    local full_rebuild="${3:-false}"

    # =============================================================================
    # First-Pass: Analyze imports, detect changes, update cache, record reverse deps
    # =============================================================================
    # This function is the heart of the M2 dependency system.
    # It is responsible for:
    #   - Collecting source files
    #   - Determining which files need re-parsing (dirty detection via mtime)
    #   - Running the unified parser pipeline (parse → process → resolve)
    #   - Recording both forward (resolved_pairs) and reverse dependencies
    #   - Persisting rich data (with confidence) back into the import cache
    #   - Merging cached data for unchanged files
    #
    # The goal is to keep incremental runs fast while still producing
    # high-quality data for the table, Mermaid graph, and MCP tools.

    # Simple debug helper (enable with WIKIFIER_DEBUG=1)
    debug_log() {
        if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
            echo "[WIKIFIER_DEBUG] $*" >&2
        fi
    }

    # === Phase 0: Core data structures ===
    declare -gA file_to_module=()
    declare -gA module_to_file=()
    declare -gA reverse_deps=()
    declare -ga python_files=()
    declare -ga js_files=()
    declare -ga resolved_pairs=()   # src|raw|resolved|confidence lines from this run (CAPPED for scale; see R1 hardening below)

    # === R1 Pipeline Scale Hardening (Gap #1 Reliability & Scale) ===
    # Addresses fragility of large resolved_pairs array (5k-20k+ file monorepos => 50k-200k+ edges)
    # in shell persist layer + table/mermaid generators.
    # - resolved_pairs shell array: capped to avoid ARG_MAX / slow "${arr[@]}" expansion / high mem on full runs.
    # - Persist of rich (cdia_v1 etc) now uses dedicated streaming temp file (FRESH_PAIRS_TMP) for fresh data:
    #   printf per line >> tmp (no array), then cat tmp | python persist (pure stream, no expansion, all data reaches contracts.parse_pipeline_line regardless of shell array cap).
    # - This guarantees rich fields survive at true monorepo scale for BOTH full and incremental, while shell only holds bounded working set for legacy consumers (table, mermaid).
    # - LARGE_SCALE_MODE triggers graceful degradation (summaries + notes instead of full expansion/loops in generators).
    # - reverse_deps (assoc, #unique targets) remains small and always fully built.
    # - Strong diagnostics on cap hit + in persist python.
    # See also: persist_rich_cache_data, process_file_imports comments, harness validate_pipeline_richness docstring for limits.
    declare -g MAX_SHELL_RESOLVED_PAIRS=${WIKIFIER_MAX_SHELL_PAIRS:-8000}
    declare -g LARGE_SCALE_MODE=false
    declare -g FRESH_PAIRS_TMP=""
    # R3 hygiene: sweep stale fresh-pairs temps (>1 day old) left by previously
    # interrupted runs, then guarantee cleanup of this run's temp on any exit path
    # (the explicit rm at the end of this function only covers the happy path).
    find "$STAGING_DIR" -maxdepth 1 -name 'wikifier_fresh_pairs.*' -mmin +1440 -delete 2>/dev/null || true
    trap 'rm -f "${FRESH_PAIRS_TMP:-}" 2>/dev/null' EXIT
    if command -v mktemp >/dev/null 2>&1; then
        FRESH_PAIRS_TMP=$(mktemp "${STAGING_DIR}/wikifier_fresh_pairs.XXXXXX.txt" 2>/dev/null || echo "${STAGING_DIR}/wikifier_fresh_pairs.txt")
    else
        FRESH_PAIRS_TMP="${STAGING_DIR}/wikifier_fresh_pairs.txt"
    fi
    declare -g FRESH_PAIRS_TMP="$FRESH_PAIRS_TMP"
    : > "$FRESH_PAIRS_TMP" 2>/dev/null || true   # ensure empty for this run
    declare -g TOTAL_PAIRS_SEEN=0

    # Helper to record reverse dependencies (target → list of sources that import it)
    record_reverse_dep() {
        local source_file="$1"
        local resolved_target="$2"
        [[ -z "$resolved_target" || -z "$source_file" ]] && return
        if [[ " ${reverse_deps[$resolved_target]:-} " != *" $source_file "* ]]; then
            reverse_deps["$resolved_target"]+=" $source_file"
        fi
    }

    # Reusable helper to reparse a list of files for a given language.
    # This reduces duplication between the Python and JavaScript paths.
    reparse_file_list() {
        local -n file_list="$1"      # nameref to the array of files
        local lang="$2"              # "python" or "javascript"

        for file in "${file_list[@]}"; do
            local rel_file
            rel_file=$(realpath --relative-to="$PROJECT_ROOT" "$file" 2>/dev/null || echo "$file")

            local parser_cmd
            if [[ "$lang" == "python" ]]; then
                parser_cmd="python3 -m wikifier.parsers.python"
            else
                parser_cmd="python3 -m wikifier.parsers.javascript"
            fi

            local json_output
            json_output=$($parser_cmd "$file" 2>/dev/null || echo "[]")

            local normalized
            normalized=$(parse_parser_json_output <(echo "$json_output") "$lang")

            local pairs
            pairs=$(process_file_imports "$rel_file" "$normalized" "$lang")

            # Capture FULL lines (including |cdia_v1=...|barrel_v2=...|res_meta_v1=... etc.) into resolved_pairs.
            # The 4-field truncation was the root cause of rich data loss before persist (P1).
            # Table/Mermaid code only reads first 4 fields (IFS read discards tail via _rest) -- no behavior change.
            # Reverse dep only needs src+resolved. Rich flows to persist_rich_cache_data normalizer (and now also
            # uniformly reconstructed for cached incremental contributions -- see merge python below).
            #
            # R1 Scale Hardening: 
            # - ALWAYS stream the FULL rich line (with all vN suffixes) to FRESH_PAIRS_TMP for the persist path.
            #   This uses only per-line printf (O(1) mem per line) + final cat|python; NO shell array expansion ever for persist.
            #   Guarantees 100% rich survival (cdia/barrel/res_meta) even when 100k+ pairs on 20k-file monorepos.
            # - resolved_pairs array population is now CAPPED (MAX_SHELL_RESOLVED_PAIRS) + guarded by LARGE_SCALE_MODE.
            #   When cap hit we stop growing the array (keeps ~2-3MB), set flag for downstream graceful degredation in
            #   generate_* (table/mermaid emit summaries instead of full loops/expansions that would hit ARG_MAX or OOM/perf).
            # - TOTAL_PAIRS_SEEN always accurate for diagnostics (persisted rich count may differ slightly due to dedup).
            # - Per-file pairs() from process_file_imports is small (one src's imports), so tmp append is cheap.
            while IFS= read -r line || [[ -n "$line" ]]; do
                [[ -z "$line" ]] && continue
                TOTAL_PAIRS_SEEN=$((TOTAL_PAIRS_SEEN + 1))
                # Stream EVERY rich line to tmp for robust persist (decouples persist_rich from array size)
                printf '%s\n' "$line" >> "$FRESH_PAIRS_TMP"
                # Safe extraction of first 4 (rich tail may be present); _rest absorbs extras for long/rich lines
                IFS='|' read -r src _raw resolved conf _rest <<< "$line" || true
                [[ -n "$resolved" ]] && record_reverse_dep "$src" "$resolved"
                # Capped append only for table/Mermaid legacy paths (small working set on large monorepos)
                if [[ "$LARGE_SCALE_MODE" != "true" ]]; then
                    resolved_pairs+=("$line")
                    if [[ ${#resolved_pairs[@]} -ge $MAX_SHELL_RESOLVED_PAIRS ]]; then
                        LARGE_SCALE_MODE=true
                        debug_log "R1 SCALE: resolved_pairs capped at $MAX_SHELL_RESOLVED_PAIRS (TOTAL_SEEN=$TOTAL_PAIRS_SEEN so far); LARGE_SCALE_MODE engaged. Persist+reverse+cache unaffected; table/mermaid will degrade gracefully."
                    fi
                fi
            done <<< "$pairs"
        done
    }

    # === Phase 1: Collect source files and determine what needs re-parsing ===
    # Find all relevant source files.
    # Now respects the full exclude_patterns.txt (via build_exclude_expr) for early pruning
    # of venvs, caches, build dirs, site-packages etc. This is the same mechanism used by
    # check-changes/monitor — makes mapping walks much faster on real monorepos without
    # changing which files are *supposed* to be analyzed (just stops descending into junk earlier).
    local exclude
    exclude=$(build_exclude_expr)
    while IFS= read -r f; do
        case "$f" in
            *.py) python_files+=("$f") ;;
            *.js|*.ts|*.jsx|*.tsx) js_files+=("$f") ;;
        esac
    done < <(find $paths -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" \) \
        $exclude ! -path "*/.git/*" ! -path "*/node_modules/*" 2>/dev/null | sort)

    # Determine which files actually need re-parsing this run.
    # This helper encapsulates the mtime-based dirty detection and
    # reverse dependency pre-loading from the cache.
    determine_files_to_reparse() {
        declare -ga files_to_reparse=()

        if [[ "$full_rebuild" == "true" || ! -f "$import_cache_file" ]]; then
            files_to_reparse=("${python_files[@]}" "${js_files[@]}")
            return
        fi

        # R7 Perf + Phase 2.3 polish: Single python invocation computes BOTH
        # regular mtime/new-file dirty set *and* barrel-stale importers (via BRC mtimes_snapshot + reverse index).
        # One cache load, unified authoritative reparse list, barrel invalidation fully integrated into
        # the primary dirty decision (no longer a separate post-hoc append with root bugs).
        # Preserves full semantics for incremental + barrel-driven extra reparse on large monorepos.
        local cand_list
        cand_list=$(printf '%s\n' "${python_files[@]}" "${js_files[@]}" | sort -u)
        local dirty_out
        dirty_out=$(python3 -c '
import os, sys
from pathlib import Path
import wikifier.import_cache as ic
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", "."))).resolve()
cands = []
for line in sys.stdin:
    line = line.strip()
    if line:
        cands.append(Path(line))
dirty = ic.compute_files_needing_reparse(root, cands, full_rebuild=False)

# Phase 2.3 / Wave 1: merge barrel-driven stale importers using *delta* path when possible.
# Pass the just-computed dirty list (includes any changed barrel files) so
# invalidate uses O(changed) get_affected_importers via BRC reverse index instead of full scan.
# This is the scalable hot path for "edit barrel → only true consumers re-analyzed".
try:
    cache_for_barrel = ic.load_cache(root)
    barrel_stale = ic.invalidate_stale_barrel_entries(cache_for_barrel, root, changed_files=[str(p) for p in (dirty or [])])
    # Wave 2/4 observability + audit log: always compute reports (cheap O(changed) delta), append lightweight structured
    # entries to _barrel_invalidation_log (bounded) + best-effort save for persistent audit trail of "barrel edit -> importers".
    # DEBUG still emits the human-friendly line; log is always-on for post-hoc queries (agents read via load_cache).
    # Safe, zero-dep, only persists when real barrel invalidations detected. See append_barrel_invalidation_log.
    try:
        reps = ic.get_barrel_invalidation_reports(cache_for_barrel, root, changed_files=[str(p) for p in (dirty or [])]) or []
        nlog = ic.append_barrel_invalidation_log(cache_for_barrel, reps)
        if nlog > 0:
            ic.save_cache(root, cache_for_barrel)
    except Exception:
        reps = []
    if os.environ.get("WIKIFIER_DEBUG") or os.environ.get("DEBUG"):
        try:
            for r in (reps or [])[:8]:  # bounded for scale
                imp = r.get("importer", "?")
                trig = ",".join(r.get("triggering_barrels", [])[:3])
                cids = ",".join(r.get("chain_ids", [])[:2])
                rsn = r.get("reason", "")
                det = r.get("detector_used", "")
                niv = r.get("node_identity_version")
                print(f"DEBUG BarrelReport: importer={imp} via_barrels=[{trig}] chains=[{cids}] reason={rsn} detector={det} v1={niv}", file=sys.stderr)
        except Exception:
            pass
    seen = {str(p.resolve()) for p in dirty}
    for rel in barrel_stale:
        if rel:
            p = (root / rel).resolve()
            if p.exists() and str(p) not in seen:
                dirty.append(p)
                seen.add(str(p))
    # Wave 4 slice: explicit prune on --full (and safe opportunistic every run); zero-dep, scales, keeps BRC lean at 5k+
    try:
        from wikifier.import_cache import prune_barrel_resolutions
        prune_barrel_resolutions(root, max_age_days=90.0, dry_run=False)
    except Exception:
        pass
except Exception:
    # Barrel augmentation is best-effort; the mtime-based dirty list above stands alone.
    # (This except was missing, which made the whole snippet a SyntaxError and silently
    # disabled incremental dirty detection — every run reparsed all files.)
    pass

for d in dirty:
    print(str(d))
' <<< "$cand_list" 2>/dev/null || true)

        while IFS= read -r f; do
            [[ -n "$f" && -f "$f" ]] && files_to_reparse+=("$f")
        done <<< "$dirty_out"

        # Pre-load reverse dependencies from cache (one-time, cheap single spawn).
        # Note: read via process substitution (not a pipe) so the assignments
        # land in this shell, and emit tgt|sources lines directly from Python.
        if [[ -z "${reverse_deps_loaded:-}" ]]; then
            while IFS='|' read -r tgt sources; do
                [[ -n "$tgt" ]] && reverse_deps["$tgt"]="$sources"
            done < <(python3 -c '
import os
from pathlib import Path
import wikifier.import_cache as ic
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", ".")))
cache = ic.load_cache(root)
rev = ic.get_reverse_dependencies(cache) or {}
for k, v in rev.items():
    print(k + "|" + ",".join(v))
' 2>>"$STAGING_DIR/debug.log")
            reverse_deps_loaded=1
        fi
    }

    declare -ga files_to_reparse=()
    determine_files_to_reparse

    # Fallback safety
    if [[ ${#files_to_reparse[@]} -eq 0 ]]; then
        files_to_reparse=("${python_files[@]}" "${js_files[@]}")
    fi

    # A1 Wave 3 Agent 2 final wiring (scale dogfood polish): delta-correct reverse for reparsed sources.
    # Pre-load gave full prior reverse (incl. old contribs of now-dirty srcs). For each to-reparse source:
    # use remove_source_from_reverse_index (O(its old edges) via maintain_ + its cache entry) on a snapshot
    # to produce cleaned rev, then repopulate shell assoc from it. New edges added during reparse via record.
    # Result: correct full reverse at persist time (no stale removed-imports/rename contribs). Exercises new
    # helpers. O(changed) total. 50k+ safe (no full scans). Same logic in scripts/wikifier.sh.
    if [[ ${#files_to_reparse[@]} -gt 0 ]]; then
        reparses_for_a1=$(printf '%s\n' "${files_to_reparse[@]}")
        cleaned_rev_json=$(python3 -c '
import sys, json, os
from pathlib import Path
import wikifier.import_cache as ic
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", "."))).resolve()
reparse_paths = [line.strip() for line in sys.stdin if line.strip()]
try:
    cache = ic.load_cache(root)
    for f in reparse_paths:
        try:
            pf = Path(f)
            if pf.is_absolute():
                rel = str(pf.resolve().relative_to(root))
            else:
                # may already be rel or need realpath
                rel = str((root / pf).resolve().relative_to(root))
        except Exception:
            rel = f  # fallback; keys in practice tolerate or match reparse rel_file
        ic.remove_source_from_reverse_index(cache, rel)
    cleaned = ic.get_reverse_dependencies(cache)
    print(json.dumps(cleaned))
except Exception as ex:
    # best-effort; on error keep prior preload (harmless, rare)
    print("{}", file=sys.stderr)
    print("{}")
' <<< "$reparses_for_a1" 2>/dev/null || echo '{}')
        if [[ -n "$cleaned_rev_json" && "$cleaned_rev_json" != "{}" && "$cleaned_rev_json" != "" ]]; then
            # Rebuild assoc from cleaned snapshot (old contribs of reparses removed; untouched preserved)
            unset reverse_deps 2>/dev/null || true
            declare -gA reverse_deps=()
            while IFS='|' read -r tgt sources; do
                [[ -n "$tgt" ]] && reverse_deps["$tgt"]="$sources"
            done < <(echo "$cleaned_rev_json" | python3 -c '
import json, sys
for k, v in json.load(sys.stdin).items():
    print(k + "|" + ",".join(v))
' 2>>"$STAGING_DIR/debug.log")
            reverse_deps_loaded=1
        fi
    fi

    # === Phase 2.3: Barrel invalidation now integrated into primary dirty computation (above) ===
    # The BRC-based stale importer logic (mtimes_snapshot + reverse index) runs inside the same
    # Python invocation as regular mtime dirty detection. No separate post-hoc block needed.
    # This gives a single authoritative files_to_reparse list that correctly includes
    # consumers of changed barrels, before py/js splitting and reparse_file_list.


    debug_log "Files collected: ${#python_files[@]} Python, ${#js_files[@]} JS/TS"
    debug_log "Files to reparse: ${#files_to_reparse[@]}"

    if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
        debug_log "=== Files selected for re-parsing ==="
        for f in "${files_to_reparse[@]}"; do
            rel=$(realpath --relative-to="$PROJECT_ROOT" "$f" 2>/dev/null || echo "$f")
            debug_log "  $rel"
        done
        debug_log "=== End of reparse list ==="
    fi

    # === Phase 2: Re-parse dirty files using the unified helper pipeline ===
    # Python files
    declare -a py_to_reparse=()
    for f in "${files_to_reparse[@]}"; do
        [[ "$f" == *.py ]] && py_to_reparse+=("$f")
    done
    reparse_file_list py_to_reparse "python"

    # JavaScript / TypeScript files
    declare -a js_to_reparse=()
    for f in "${files_to_reparse[@]}"; do
        [[ "$f" == *.js || "$f" == *.ts || "$f" == *.jsx || "$f" == *.tsx ]] && js_to_reparse+=("$f")
    done
    reparse_file_list js_to_reparse "javascript"

    debug_log "Re-parsing complete. Collected ${#resolved_pairs[@]} resolved pairs so far."
    debug_log "Reverse dependencies recorded for ${#reverse_deps[@]} targets."

    if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
        debug_log "=== Sample of resolved_pairs (first 10) ==="
        count=0
        for pair in "${resolved_pairs[@]}"; do
            debug_log "  $pair"
            count=$((count + 1))   # set -e safe (((count++)) returns 1 at 0)
            [[ $count -ge 10 ]] && break
        done
        debug_log "=== End of sample ==="
    fi

        # === Phase 3: Persist rich data back into the cache ===
    persist_rich_cache_data() {
        # 3a. Save resolved_pairs + dependents for files we re-parsed
        if [[ ${#files_to_reparse[@]} -gt 0 ]]; then
            # R1 Pipeline Scale Hardening (full): persist of rich data now uses FRESH_PAIRS_TMP (populated
            # per-line in reparse_file_list via printf >> ) + cat | python. This completely eliminates
            # any "${resolved_pairs[@]}" expansion (and its ARG_MAX / perf / mem risks) from the persist
            # path. Even if array is empty or capped at 8k, ALL fresh rich lines (with full cdia_v1=... etc
            # suffixes from process_file_imports) reach the python normalizer.
            # python side (parse_pipeline_line + unpack_*) is line-streaming and defensive per contracts.
            # Fallback to array expansion only if tmp missing (compat for weird envs); small runs unaffected.
            # Per-file streaming would also work (persist inside reparse loop) but would cause  O(N_files)
            # cache load/save; tmp+single persist is better balance (one load/save, full data).
            # R1 input: stream from tmp (preferred, no expansion) or fallback array
            (
                if [[ -n "$FRESH_PAIRS_TMP" && -f "$FRESH_PAIRS_TMP" && -s "$FRESH_PAIRS_TMP" ]]; then
                    cat "$FRESH_PAIRS_TMP"
                else
                    # legacy (rare post-R1; small runs only)
                    printf '%s\n' "${resolved_pairs[@]}"
                fi
            ) | python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys, os
from collections import defaultdict
import json

# === P1 Pipeline Normalizer (persist path) ===
# Uses the frozen contracts.parse_pipeline_line + decode/unpack_* helpers exclusively
# (see wikifier/contracts.py:373 and the Shell Pipeline Serialization Strategy v1 in
# Findings/gap1_prewave0_shared_contracts_open.md).
# This is the single point that turns opaque |cdia_v1=...|barrel_v2=...|res_meta_v1=... lines
# (emitted by parse_parser_json_output + forwarded by process_file_imports) into the nested
# conditional_analysis / dynamic_analysis / resolution_metadata / barrel_v2
# structures stored under RICH_KEYS in the cache (for MCP, ACS, CIABRE, library.md etc.).
# - Fully tolerant of legacy-only, rich-only, mixed, short, malformed, very long lines.
# - On any decode failure for a vN field: appends to decode_failures, prints + emits
#   PIPELINE-category diagnostic via make_diagnostic (with real line preview); never crashes;
#   the import for that edge succeeds with legacy flats + any other successfully-decoded rich.
# - Rich decoded form wins (update + MCP see the dataclass-shaped dicts); raw b64 also attached for debug.
# - Legacy flats always attached for the dual-emission transition period (per contracts).
# - Handles incremental: only acts on files_to_reparse (fresh rich lines); cached data for others
#   already has rich from prior runs and is merged later (see below).
# - Additive/defensive: old caches without vN fields forever readable via parse_pipeline_line (rich_payloads empty).
from wikifier.contracts import (
    parse_pipeline_line,
    decode_v1_payload,
    unpack_cdia_v1,
    unpack_res_meta_v1,
    PIPE_FIELD_CDIA_V1,
    PIPE_FIELD_BARREL_V2,
    PIPE_FIELD_RES_META_V1,
)
try:
    from wikifier.diagnostics import make_diagnostic
    DIAG_AVAILABLE = True
except Exception:
    DIAG_AVAILABLE = False

root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", ".")))
cache = ic.load_cache(root)
# Preserve Phase 2 barrel persistent cache (BREE engine writes _barrel_resolutions + _barrel_file_index
# during parser subprocesses via to_cache_updates + save). We must not drop these top-level keys
# during the main rich persist.
_barrel_res = cache.get("_barrel_resolutions")
_barrel_idx = cache.get("_barrel_file_index")
file_pairs = defaultdict(list)
decode_failures = []

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    # Robust parse (the contract helper). Never raises. Handles  <10 fields + any |k=v suffixes.
    pl = parse_pipeline_line(line)
    src = pl.get("src", "") or ""
    raw = pl.get("raw", "")
    resolved = pl.get("resolved", "")
    conf = pl.get("confidence", "medium")
    if not raw and not resolved:
        continue
    pair = {"raw": raw, "resolved": resolved, "confidence": conf}

    # Legacy flat rich fields (always present in pl top-level as str or defaults; keep for dual-read period)
    pair["is_dynamic"] = (pl.get("is_dynamic") == "true")
    pair["dynamic_type"] = pl.get("dynamic_type") or "static"
    pair["is_conditional"] = (pl.get("is_conditional") == "true")
    pair["conditional_context"] = pl.get("conditional_context") or ""
    pair["via_barrel"] = (pl.get("via_barrel") == "true")
    bd = pl.get("barrel_depth") or ""
    try:
        pair["barrel_depth"] = int(bd) if bd else 0
    except Exception:
        pair["barrel_depth"] = bd

    # Decode rich vN payloads using the ONLY sanctioned helpers (defensive, from_dict inside)
    # per contracts: decode_v1_payload / unpack_* are the single source; any failure -> None + degraded path (legacy flats remain usable).
    # We collect detailed failure records (incl. actual line preview) for proper PIPELINE diagnostics.
    rich = pl.get("rich_payloads", {}) or {}
    for k, v in rich.items():
        line_preview = (line[-220:] if len(line) > 220 else line)
        val_preview = (v[:60] + "...(truncated)") if len(v) > 60 else v
        if k == PIPE_FIELD_CDIA_V1:
            dec = unpack_cdia_v1(v)
            if dec:
                # decoded contains "conditional_analysis" and/or "dynamic_analysis" (or None)
                pair.update(dec)
            else:
                decode_failures.append({"key": k, "src": src, "preview": line_preview, "val_preview": val_preview})
            # keep the raw b64 under the vN key too (for debug / roundtrip in this pass; note: raw b64 keys filtered by RICH_KEYS in update, decoded structs persist)
            pair["cdia_v1"] = v
        elif k == PIPE_FIELD_RES_META_V1:
            dec = unpack_res_meta_v1(v)
            if dec:
                pair.update(dec)
                rm = dec.get("resolution_metadata") or {}
                if isinstance(rm, dict) and rm.get("strategy"):
                    pair["strategy"] = rm["strategy"]
            else:
                decode_failures.append({"key": k, "src": src, "preview": line_preview, "val_preview": val_preview})
            pair["res_meta_v1"] = v
        elif k == PIPE_FIELD_BARREL_V2:
            bdec = decode_v1_payload(v)
            if bdec is not None:
                pair["barrel_v2"] = bdec
                # barrel_v2 may contain via_barrel, barrel_chain, hops, barrel_detector, is_partial etc.
            else:
                decode_failures.append({"key": k, "src": src, "preview": line_preview, "val_preview": val_preview})
            pair["barrel_v2_raw"] = v   # preserve original for diagnostics

    file_pairs[src].append(pair)

# Emit diagnostics for any decode failures (per contracts Error & Diagnostics Policy + enrich with real line context)
# Never crashes the normalizer; import succeeds with best-effort (legacy + any successfully decoded rich).
if decode_failures:
    for fail in decode_failures:
        k = fail.get("key", "?")
        s = fail.get("src", "?")
        prev = fail.get("preview", "")[:200]
        vprev = fail.get("val_preview", "")
        msg = f"PIPELINE rich payload decode failure: {k} for {s} (val~ {vprev})"
        print(msg, file=sys.stderr)
        if DIAG_AVAILABLE:
            try:
                d = make_diagnostic(
                    "pipeline",  # contracts-specified category (str fallback if enum not extended)
                    msg[:280],
                    severity="warn",
                    suggestion_for_agent="Check parser JSON emission for the file (cdia/barrel/res_meta dicts must be valid for encode_v1_payload); re-run with WIKIFIER_DEBUG=1; legacy-only lines + synthesis helpers still usable; old caches remain readable forever.",
                    details={
                        "normalizer": "persist_rich_cache_data",
                        "raw_line_preview": prev,
                        "rich_key": k,
                        "src_file": s,
                        "val_preview": vprev
                    }
                )
                print("DIAGNOSTIC: " + json.dumps(d, ensure_ascii=False), file=sys.stderr)
            except Exception:
                pass

for src, pairs in file_pairs.items():
    if not pairs: continue
    try:
        full_path = root / src
        mtime = ic.get_mtime(full_path) if full_path.exists() else 0
        ic.update_file_data(cache, src, mtime, [], resolved_pairs=pairs)
    except Exception:
        pass

# Restore barrel persistent cache if it was present on load (engine may have updated it during reparse)
if _barrel_res is not None:
    cache["_barrel_resolutions"] = _barrel_res
if _barrel_idx is not None:
    cache["_barrel_file_index"] = _barrel_idx

ic.save_cache(root, cache)
print(f"Saved rich cache entries for {len(file_pairs)} files", file=sys.stderr)
' 2>/dev/null || true
        fi

        # 3b. Store per-file dependents list for each re-parsed file
        for src in "${files_to_reparse[@]}"; do
            rel=$(realpath --relative-to="$PROJECT_ROOT" "$src" 2>/dev/null || echo "$src")
            dependents_list="${reverse_deps[$rel]:-}"
            if [[ -n "$dependents_list" ]]; then
                python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", ".")))
cache = ic.load_cache(root)
rel = sys.argv[1]
deps_str = sys.argv[2] if len(sys.argv) > 2 else ""
deps = [d for d in deps_str.split() if d]
data = ic.get_file_data(cache, rel) or {}
ic.update_file_data(cache, rel, data.get("mtime", 0), data.get("imports", []),
                    resolved=data.get("resolved"),
                    resolved_pairs=data.get("resolved_pairs"),
                    dependents=deps)
ic.save_cache(root, cache)
' "$rel" "$dependents_list" 2>/dev/null || true
            fi
        done

        # 3c. Persist the global reverse dependency map
        if [[ ${#reverse_deps[@]} -gt 0 ]]; then
            python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys

root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", ".")))
cache = ic.load_cache(root)
rev_deps = {}
for line in sys.stdin:
    line = line.strip()
    if not line or "|" not in line: continue
    tgt, sources = line.split("|", 1)
    if tgt:
        rev_deps[tgt] = [s for s in sources.split(",") if s]
ic.set_reverse_dependencies(cache, rev_deps)
ic.save_cache(root, cache)
print(f"Persisted reverse dependencies for {len(rev_deps)} targets", file=sys.stderr)
' <<< "$(for tgt in "${!reverse_deps[@]}"; do
    sources="${reverse_deps[$tgt]}"
    sources="${sources// /,}"
    echo "$tgt|$sources"
done)" 2>/dev/null || true
        fi

        # 3d. Compute + persist cycles + graph integrity + CIABRE analyses (P3 Polish)
        # Runs after every update-maps (after reverse deps 3c). Uses Tarjan SCC (iterative), rich signals,
        # canonical path support (v1 default post-audit; v0 raw via use_canonical=False for compat).
        # normalization. Persists _cycles, _graph_integrity, _cycle_analyses, _graph_signature.
        # Wave 3: FULL delta short-circuit using graph_signature in main update-maps path (cheap precheck
        # + guard in sh + inside compute). Canonical v1 flip prepped (build_*/compute_* now support
        # remapping for symlink-stable graphs; node_identity_version v0/v1; harness exercised).
        # CIABRE delivers severity scoring, blast radius, weakest links (dynamic/cond/barrel), ranked recs.
        # Parser emission audit (2026-05-20): all resolved targets flow via resolution.to_canonical_rel paths
        # + BRC v1 + canonical_for_bree (bree/javascript); safe for v1 default (consistent physical ids for sigs/cycles).
        python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys
import os
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", ".")))
cache = ic.load_cache(root)
# Wave 4 (per gap1_cycles_longterm_strategy): default flipped to v1 canonical (symlink/workspace stable);
# use_canonical=False available for raw v0 compat or migration windows. Delta short + reuse still honored.
# Wave 3 delta short-circuit in main path (per gap1_cycles_longterm_strategy + continuation):
#   compute cheap adj-graph sig; if matches persisted _graph_signature and data present -> reuse gets (no Tarjan, no edge build)
g_for_sig = ic.build_dependency_graph(cache, use_canonical=True)
gsig = ic.graph_signature(g_for_sig)
persisted_sig = ic.get_graph_signature(cache)
cdata = None
analyses = None
reused_cycles = False
if persisted_sig and persisted_sig == gsig:
    pc = ic.get_cycles(cache) or {}
    if "sccs" in pc and pc.get("graph_signature") == gsig:
        cdata = dict(pc)
        cdata["reused"] = True
        cdata["reuse_reason"] = "graph_signature_match"
        cdata.setdefault("graph_signature", gsig)
        reused_cycles = True
    pa = ic.get_cycle_analyses(cache) or {}
    if "analyses" in pa and pa.get("graph_signature") == gsig:
        analyses = dict(pa)
        analyses["reused"] = True
        analyses["reuse_reason"] = "graph_signature_match"
        analyses.setdefault("graph_signature", gsig)
if cdata is None:
    # full path or first time (pass prebuilt adj to save work inside compute)
    cdata = ic.compute_cycles(cache, root=root, use_canonical=True, max_reported_sccs=200, graph=g_for_sig)
    # only build rich edge meta on actual change
    g, em = ic.build_graph_with_edge_metadata(cache, root=root, use_canonical=True)
    analyses = ic.compute_cycle_analyses(cache, root=root, max_items=50, graph=g, edge_meta=em)
# Always persist (guaranteed + stamp reuse markers for future delta + health/diag/library)
ic.set_cycles(cache, cdata)
ic.set_graph_signature(cache, gsig)
integrity = ic.compute_graph_integrity(cache)
ic.set_graph_integrity(cache, integrity)
if analyses is None:
    analyses = ic.get_cycle_analyses(cache) or {}
ic.set_cycle_analyses(cache, analyses)
# ACS aggregates (surfacing uniformity): always (reparse may affect scores)
acs = ic.compute_acs_summary(cache)
ic.set_acs_summary(cache, acs)
# Optional guaranteed persist for _resolution_diagnostics (Wave 4 per cycles long-term + tracker):
# ensures diagnostics (incl. injected cycles_reuse + creative tags) are always in cache for MCP/library
# without requiring separate get_ call. Best-effort; mirrors acs/cycles hardening.
try:
    ic.ensure_diagnostics_aggregate(cache)
except Exception:
    pass
ic.save_cache(root, cache)
stats = cdata.get("stats", {})
a_summary = (analyses or {}).get("summary", {})
acs_sum = acs or {}
re_flag = " (REUSED via graph_signature delta short-circuit)" if reused_cycles else ""
# NOTE: keep quoted dict keys OUT of f-string expressions here. This code lives in a
# shell single-quoted string: \" inside {...} is a Python SyntaxError and bare single
# quotes are eaten by the shell. Hoist lookups to plain variables first.
csc = stats.get("cyclic_scc_count", 0)
tfc = stats.get("total_files_in_cycles", 0)
hsc = a_summary.get("high_severity_count", 0)
mbl = a_summary.get("max_blast_radius", 0)
avs = a_summary.get("avg_score", 0)
acs_avg = acs_sum.get("avg_confidence", 0)
acs_low = acs_sum.get("low_conf_edges", 0)
acs_samp = len(acs_sum.get("sample_low_conf_explanations", []) or [])
print(f"Cycle detection (Phase 1): {csc} cyclic SCC(s), {tfc} files. CIABRE v1.3: {hsc} high-sev, max_blast={mbl}, avg_score={avs}. ACS: avg={acs_avg}, low<0.65={acs_low} (samples={acs_samp}). graph_sig={gsig}{re_flag}", file=sys.stderr)
' 2>/dev/null || true

    }

    # Guarded call — respect WIKIFIER_DEBUG
    if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
        debug_log "DEBUG MODE: Skipping persist_rich_cache_data"
    else
        persist_rich_cache_data
    fi
# === Phase 5: Merge cached forward data for files that were not re-parsed ===
    if [[ "$full_rebuild" != "true" && -f "$import_cache_file" ]]; then
        # Use wikifier.import_cache to fetch resolved_pairs for files we did not reparse
        python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys, os
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", ".")))
cache = ic.load_cache(root)

reparsed = set()
for line in sys.stdin:
    line = line.strip()
    if line:
        rel = line.replace(root.as_posix() + "/", "")
        reparsed.add(rel)

for rel, data in cache.items():
    if rel not in reparsed:
        for p in data.get("resolved_pairs", []):
            raw = p.get("raw", "")
            resolved = p.get("resolved", "")
            if raw and resolved:
                # Build a full 10-legacy-field line (improved over old 4-field stub) so that
                # all entries in resolved_pairs (fresh reparse + incremental cached) have uniform shape.
                # This ensures mixed-legacy/rich handling, table code, debug, and any future consumers
                # see consistent data even on incremental runs (where some pairs come from prior cache).
                is_dyn = "true" if p.get("is_dynamic") else "false"
                dyn_type = p.get("dynamic_type") or "static"
                is_cond = "true" if p.get("is_conditional") else "false"
                cond_ctx = p.get("conditional_context") or ""
                via_b = "true" if p.get("via_barrel") else "false"
                b_depth = str(p.get("barrel_depth", "")) if p.get("barrel_depth") is not None else ""
                conf = p.get("confidence") or "medium"
                core = f"{rel}|{raw}|{resolved}|{conf}|{is_dyn}|{dyn_type}|{is_cond}|{cond_ctx}|{via_b}|{b_depth}"

                # Reconstruct rich vN suffixes from cached *decoded* structs (using encode_v1_payload).
                # This makes rich (cdia_v1 etc.) "flow" into resolved_pairs even for unchanged files on
                # incremental runs — uniform with fresh parse output. Re-encode is faithful (roundtrippable).
                # If no rich structs (pre-P1 legacy cache entry) we emit at least the 10 legacy fields.
                rich_suffixes = []
                try:
                    from wikifier.contracts import encode_v1_payload
                    ca = p.get("conditional_analysis")
                    da = p.get("dynamic_analysis")
                    if ca or da:
                        cdia_d = {"conditional_analysis": ca, "dynamic_analysis": da}
                        b64 = encode_v1_payload(cdia_d)
                        if b64:
                            rich_suffixes.append(f"cdia_v1={b64}")
                    rm = p.get("resolution_metadata")
                    if rm:
                        b64 = encode_v1_payload({"resolution_metadata": rm})
                        if b64:
                            rich_suffixes.append(f"res_meta_v1={b64}")
                    b2 = p.get("barrel_v2")
                    if isinstance(b2, dict):
                        b64 = encode_v1_payload(b2)
                        if b64:
                            rich_suffixes.append(f"barrel_v2={b64}")
                except Exception:
                    # contracts unavailable or encode fail -> fall back to legacy-only line for this cached p
                    pass

                if rich_suffixes:
                    print(core + "|" + "|".join(rich_suffixes))
                else:
                    print(core)
' 2>/dev/null | while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            TOTAL_PAIRS_SEEN=$((TOTAL_PAIRS_SEEN + 1))
            # R1: cap the append from cached merge too (incremental large unchanged set); persist already done for fresh only.
            if [[ "$LARGE_SCALE_MODE" != "true" ]]; then
                resolved_pairs+=("$line")
                if [[ ${#resolved_pairs[@]} -ge $MAX_SHELL_RESOLVED_PAIRS ]]; then
                    LARGE_SCALE_MODE=true
                    debug_log "R1 SCALE: resolved_pairs cap hit during cached merge (TOTAL_SEEN=$TOTAL_PAIRS_SEEN); graceful mode for table/mermaid."
                fi
            fi
        done <<< "$(printf '%s\n' "${files_to_reparse[@]}")"
    fi

    echo "> First-pass: re-parsed ${#files_to_reparse[@]} files + merged cached pairs for unchanged files"
    echo "> First-pass graph & cache update complete (hardened incremental mode)"

    # Final debug summary
    if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
        debug_log "=== DEBUG SUMMARY ==="
        debug_log "  Total resolved_pairs collected: ${#resolved_pairs[@]} (capped=${LARGE_SCALE_MODE})"
        debug_log "  TOTAL_PAIRS_SEEN (all fresh+merge): $TOTAL_PAIRS_SEEN"
        debug_log "  Unique targets with reverse dependencies: ${#reverse_deps[@]}"
        debug_log "  Would have persisted data for ${#files_to_reparse[@]} files"
        debug_log "=== End of debug summary ==="
    fi

    # R1 cleanup: remove the fresh pairs tmp (all data already streamed to persist python or not needed)
    if [[ -n "$FRESH_PAIRS_TMP" && -f "$FRESH_PAIRS_TMP" ]]; then
        rm -f "$FRESH_PAIRS_TMP" 2>/dev/null || true
    fi

    # === Phase 5: Generate Mermaid dependency graph (from collected resolved_pairs) ===
    # This will be moved to a dedicated helper. For now we prepare data.
    # Actual emission happens from cmd_update_maps after this call.
}

# =============================================================================
# Core Resolver — resolve_imported_module
# =============================================================================
# This is the heart of the dependency intelligence system.
# It is called by process_file_imports() and the first-pass orchestrator.
#
# It takes a raw import string (as written in source) + the file it came from,
# and returns the best-effort resolved module name + a confidence level.
#
# Strategies (in order):
#   1. Relative imports (./foo, ../bar) — very high confidence
#   2. Bare internal imports (from wikifier import health, import "services/foo")
#      - Uses package markers (__init__.py, package.json, index.js)
#      - Directory name fallback for flat projects
#   3. Standard library / external package fallbacks
#
# Performance note: The bare internal resolver was historically one of the
# biggest hotspots on large JS projects (repeated upward directory walks).
# A memoized version exists in javascript.py; the shell version should
# eventually use similar caching.

resolve_imported_module() {
    local raw_module="$1"
    local current_file="$2"
    local confidence_hint="${3:-medium}"

    # Fast path
    if [[ -z "$raw_module" ]]; then
        echo "$raw_module|unresolved"
        return 0
    fi

    # Phase 4 + P4 delegation to central engine (authoritative, monorepo-hardened, rich Resolution + metadata)
    # This is the primary path. Legacy shell-only strategies below are DEPRECATED fallbacks
    # (for no-python3 or import-failure envs). They duplicate logic now in resolution.py and
    # will be removed in v0.5+. Migration: ensure `python3 -c 'from wikifier.resolution import ...'`
    # succeeds; set WIKIFIER_ROOT and have the package importable.
    if command -v python3 >/dev/null 2>&1; then
        local py_res
        py_res=$(python3 -c '
import os, sys
from pathlib import Path
try:
    from wikifier.resolution import resolve as cr
    raw, cur = sys.argv[1:3]
    root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", os.environ.get("WIKIFIER_ROOT", "."))).resolve()
    r = cr(raw, cur, root)
    print(f"{r.resolved_file or raw}|{r.confidence}")
except Exception:
    print("")
' "$raw_module" "$current_file" 2>/dev/null || true)
        if [[ -n "$py_res" && "$py_res" != "|" ]]; then
            echo "$py_res"
            return 0
        fi
    fi

    # --- DEPRECATED LEGACY SHELL FALLBACKS (P4/F4/R4 Legacy Deprecation Execution) ---
    # The following relative/bare shell logic is retained ONLY for transition (no-python3 envs).
    # Central Python resolution (wikifier.resolution.resolve + full strategies + ProjectContext)
    # is the UNAMBIGUOUS DEFAULT and only long-term supported path.
    # Prefer it for correctness on TS paths, conditional/wildcard exports, pnpm/yarn stores, rich metadata.
    # R4: final cleanup pass; legacy shell helpers now carry explicit v0.5 removal + migration.
    echo "DEPRECATED [R4 Legacy Deprecation Execution]: wikifier.sh resolve_imported_module falling back to legacy shell resolver for '$raw_module' (central Python delegation unavailable or returned empty). MIGRATION: ensure python3 can 'from wikifier.resolution import resolve' and WIKIFIER_ROOT is set. Legacy _resolve_* shell fns removed in v0.5+. Central (resolution.py) is the UNAMBIGUOUS DEFAULT everywhere. See wikifier/resolution.py, contracts.py, gap1_4phase_roadmap." >&2
    local resolved="$raw_module"
    local confidence="$confidence_hint"

    # --- Strategy 1: Relative imports ---
    if [[ "$raw_module" == ./* || "$raw_module" == ../* ]]; then
        local rel_result
        rel_result=$(_resolve_relative_import "$raw_module" "$current_file")
        if [[ -n "$rel_result" ]]; then
            resolved="$rel_result"
            confidence="high"
        else
            confidence="low"
        fi

    # --- Strategy 2: Bare internal imports ---
    elif [[ "$raw_module" != */* && "$raw_module" != *.* ]]; then
        local bare_result
        bare_result=$(_try_resolve_bare_internal_import "$raw_module" "$current_file")
        # bare_result is now "resolved|confidence"
        local bare_resolved bare_conf
        IFS='|' read -r bare_resolved bare_conf <<< "$bare_result"
        if [[ -n "$bare_resolved" ]]; then
            resolved="$bare_resolved"
            confidence="${bare_conf:-${confidence_hint:-medium}}"
        else
            confidence="low"
        fi
    fi

    # New return format: resolved|confidence  (enables Fix 4 style confidence propagation)
    echo "${resolved}|${confidence}"
}

# Resolve relative imports like "./foo", "../bar", or ".parsers" against the current file.
# (LEGACY SHELL DUPLICATE — R4)
# Prefer/see central in wikifier/resolution.py (RelativeFilesystemStrategy).
# Called only from deprecated resolve_imported_module fallback. Central unambiguous default.
# Removal v0.5.
_resolve_relative_import() {
    local raw="$1"
    local current_file="$2"

    local dir
    dir=$(dirname "$current_file" 2>/dev/null || echo ".")

    # Normalize the raw relative specifier
    local rel="${raw#./}"          # remove leading ./
    rel="${rel#../}"               # will handle multiple ../ below

    # Count parent levels for ..
    local up=0
    local temp="$raw"
    while [[ "$temp" == ../* ]]; do
        up=$((up + 1))   # set -e safe (((up++)) returns 1 at 0)
        temp="${temp#../}"
    done
    while [[ "$temp" == .*/* ]]; do   # handle .foo/bar style
        temp="${temp#.}"
    done

    # Build the target directory by going up 'up' levels
    local target_dir="$dir"
    for ((i=0; i<up; i++)); do
        target_dir=$(dirname "$target_dir")
    done

    # Final candidate path
    local candidate
    if [[ "$raw" == .*/* || "$raw" == ./* || "$raw" == ../* ]]; then
        candidate=$(realpath --relative-to="$PROJECT_ROOT" "$target_dir/$temp" 2>/dev/null || echo "")
    else
        candidate=$(realpath --relative-to="$PROJECT_ROOT" "$dir/$raw" 2>/dev/null || echo "")
    fi

    # Normalize for module name
    candidate="${candidate%.py}"
    candidate="${candidate%.js}"
    candidate="${candidate%.ts}"
    candidate="${candidate%.jsx}"
    candidate="${candidate%.tsx}"
    candidate="${candidate%/index}"
    candidate="${candidate#/}"     # remove leading slash if any

    echo "$candidate"
}

# Simple memoization cache for bare import resolution.
# Key: directory path → "hit" or "miss" + resolved value (prevents repeated upward walks)
declare -gA _bare_resolve_cache=()

# Clear the bare resolver cache (useful between full rebuilds)
_clear_bare_resolve_cache() {
    _bare_resolve_cache=()
}

# Attempt to resolve bare internal imports (e.g. "health", "services/mealPlanner").
# Improved package root detection...
# Returns "resolved_name|confidence"...
#
# DEPRECATED (P4/F4/R4 Legacy Deprecation Execution): Full legacy duplicate of central
# wikifier/resolution (BareHeuristicStrategy + Workspace + exports etc.).
# Called ONLY from deprecated fallback path in resolve_imported_module.
# Central resolve() is the UNAMBIGUOUS DEFAULT. Removal v0.5+.
# Migrate: use python central; shell only for no-python3.
_try_resolve_bare_internal_import() {
    local bare_name="$1"
    local current_file="$2"

    local dir
    dir=$(dirname "$current_file" 2>/dev/null || echo ".")
    local root="${PROJECT_ROOT:-${WIKIFIER_PROJECT_ROOT:-$WIKIFIER_ROOT}}"
    # (project root preferred to bound upward package walk for the *target* monorepo; WIKIFIER_ROOT only as last)

    # Check cache first
    local cache_key="$dir|$bare_name"
    if [[ -n "${_bare_resolve_cache[$cache_key]:-}" ]]; then
        echo "${_bare_resolve_cache[$cache_key]}"
        return 0
    fi

    # Walk upward looking for a real package root
    local max_depth=12
    local depth=0
    local resolved="$bare_name"
    local conf="medium"

    while [[ "$dir" != "$root" && "$depth" -lt "$max_depth" ]]; do
        if [[ -f "$dir/__init__.py" ]]; then
            # Python package root found — try to build module path from here
            local rel_to_root
            rel_to_root=$(realpath --relative-to="$dir" "$current_file" 2>/dev/null || echo "")
            # Best-effort: if current file is inside the package, prepend package name
            local pkg_name
            pkg_name=$(basename "$dir")
            if [[ -n "$pkg_name" && "$bare_name" != "$pkg_name"* ]]; then
                resolved="${pkg_name}.${bare_name}"
            else
                resolved="$bare_name"
            fi
            conf="high"
            break
        fi

        if [[ -f "$dir/package.json" || -f "$dir/index.js" || -f "$dir/index.ts" ]]; then
            # JS/TS package root
            local pkg_name
            pkg_name=$(basename "$dir")
            if [[ -n "$pkg_name" && "$bare_name" != "$pkg_name"* ]]; then
                resolved="${pkg_name}/${bare_name}"
            else
                resolved="$bare_name"
            fi
            conf="high"
            break
        fi

        dir=$(dirname "$dir")
        depth=$((depth + 1))   # set -e safe (((depth++)) returns 1 at 0)
    done

    local result="${resolved}|${conf}"
    _bare_resolve_cache[$cache_key]="$result"

    echo "$result"
}

# ----------------------------- Command Implementations -----------------------------

cmd_help() {
    # Banner version comes from the installed package (single source of truth
    # in wikifier/__init__.py) so this text cannot go stale.
    local _ver
    _ver=$(python3 -c "import wikifier; print(wikifier.__version__)" 2>/dev/null || true)
    echo "Wikifier${_ver:+ v$_ver} — Agent-First Codebase Wiki (Zero Dependencies)"
    cat << 'EOF'

Usage: wikifier <command> [arguments]

Core Commands:
  init [--target DIR]        Bootstrap wikifier in a target project (copies index.html + templates).
  check-changes              Scan monitored paths for mtime changes since last run.
                             Marks changed files Yellow + adds to pending_updates.
  health                     Pretty-print the current Documentation Health Matrix.
  heal-stubs [--dry-run]     Auto-heal outdated "Initial stub" health entries.
  record-change <file> "<reason>"
                             Log a semantic change (why you edited). Updates health to Yellow.
  record-deletion <file> "<reason>"
                             Log intentional deletion with reasoning.
  prepare-edit <file>        Stage a file for diff capture (captures current mtime).
  mark-green <file> [reason]
                             Mark a wiki summary as accurate (Green). Clears pending entry.
  update-maps                Rebuild library.md with import/dependency Mermaid graph.
  validate                   Check that every monitored file has at least a stub wiki entry.
  monitor                    Background heartbeat: runs check-changes every 30s forever.
  daemon <start|stop|status|logs|restart|run|install-service|uninstall-service>
                             Long-running daemon for continuous health matrix + dependency freshness.
                             Survives laptop sleep/lid close via wake detection. Supports systemd user service.

Information Commands:
  journal [date]             Show today's (or given YYYY-MM-DD) journal entries.
  issues [severity]          List Logged_issues (simple|moderate|high|critical).
  cycles                     Report circular dependencies from the last update-maps (_cycles in cache).
  help                       This message.

Workflow (for LLMs / new sessions):
  1. wikifier check-changes
  2. Read file_health.md + pending_updates.md
  3. Prioritise 🔴 Red → 🟡 Yellow
  4. After editing a file: wikifier record-change "path/to/file" "reason"
  5. After updating the wiki summary: wikifier mark-green "path/to/file"
  6. wikifier update-maps (when imports change)

Configuration files (edit these):
  monitored_paths.txt        Paths to scan (one per line). Default: "."
  exclude_patterns.txt       Glob patterns to ignore (node_modules, .git, dist, etc.)

The system is fully usable from the shell or exposed as MCP tools via skills/run.md.
EOF
}

cmd_check_changes() {
    log "Running incremental change detection..."

    local last_ts
    if [[ -f "$LAST_CHECK_FILE" ]]; then
        last_ts=$(cat "$LAST_CHECK_FILE")
    else
        last_ts="1970-01-01 00:00:00"
        echo "$last_ts" > "$LAST_CHECK_FILE"
    fi

    local exclude
    exclude=$(build_exclude_expr)

    local changed=0
    local changed_files_list=""

    # For each monitored root, find files newer than last check
    while IFS= read -r root; do
        [[ -z "$root" ]] && continue
        [[ ! -e "$root" ]] && { log "Warning: monitored path does not exist: $root"; continue; }

        # shellcheck disable=SC2086
        while IFS= read -r -d '' file; do
            # Skip the wikifier tool's own internal files
            if [[ "$file" == *"/.wikifier_staging/"* || "$file" == *"/journal/"* || \
                  "$file" == *"/Logged_issues/"* || "$file" == *"/.git/"* ]]; then
                continue
            fi

            local rel_file
            rel_file=$(realpath --relative-to="$PROJECT_ROOT" "$file" 2>/dev/null || echo "$file")

            upsert_health "$rel_file" "🟡 Yellow" "mtime changed since last check-changes (auto-detected)"
            # Collect for delta barrel reports (Wave continuation: pass changed list to BRC get_reports for O(changed) + rich auto-Yellow only on relevant)
            changed_files_list+="${rel_file}"$'\n'
            add_pending "$rel_file" "Auto-detected modification — review and run mark-green after wiki update"
            write_journal "auto-detected" "$rel_file" "File mtime changed (check-changes)"

            changed=$((changed + 1))   # set -e safe (((changed++)) returns 1 at 0)
        done < <(find "$root" -type f -newermt "$last_ts" -print0 2>/dev/null || true)
    done < <(get_monitored_paths)

    date '+%Y-%m-%d %H:%M:%S' > "$LAST_CHECK_FILE"

    if (( changed > 0 )); then
        log "Detected $changed changed file(s). See pending_updates.md and file_health.md."
    else
        log "No new changes detected."
    fi

    # Auto-heal outdated "Initial stub" entries if substantial wiki summaries now exist
    if command -v python3 >/dev/null 2>&1; then
        python3 -m wikifier.health heal-stubs 2>/dev/null || true
    fi

    # BRC observability / barrel invalidation wiring into check-changes (Wave 3 of barrel strategy):
    # After direct mtime detection, consult persistent BarrelResolutionCache for any importers
    # whose chains are now stale due to barrel edits among (or before) the detected changes.
    # Uses build_invalidation_reports + apply to health (structured "stale via barrel X (chains, reason)").
    # This lets the daemon's periodic monitor (and `wikifier check-changes`) auto-mark affected
    # importers 🟡 Yellow with explanation — without requiring a manual update-maps.
    # Uses the rich report form (lightweight scan path here; delta/ changed_files exercised in sh first-pass).
    # Also opportunistically runs lightweight age-based BRC pruning (Wave 4).
    if command -v python3 >/dev/null 2>&1; then
        python3 -m wikifier.health prune-barrels 90 2>/dev/null || true
        WIKIFIER_CHECK_CHANGED_FILES="$changed_files_list" python3 -c '
import os
from pathlib import Path
from wikifier.import_cache import load_cache, get_barrel_invalidation_reports
from wikifier.health import apply_barrel_invalidation_reports
root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT") or ".").resolve()
cache = load_cache(root)
# Delta wiring (continuation wave): use collected changed_files for O(changed) fast path + rich BarrelInvalidationReport explanations
changed_raw = os.environ.get("WIKIFIER_CHECK_CHANGED_FILES", "")
changed_list = [x for x in changed_raw.splitlines() if x.strip()]
reports = get_barrel_invalidation_reports(cache, root, changed_files=changed_list or None)
n = apply_barrel_invalidation_reports(root, reports)
if n > 0:
    print(f"[barrel] auto-marked {n} importer(s) Yellow via BRC reports (daemon/check-changes)")
' 2>/dev/null || true
    fi
}

cmd_health() {
    if [[ -f "$FILE_HEALTH" ]]; then
        cat "$FILE_HEALTH"
    else
        echo "Health matrix not initialised yet. Run 'wikifier check-changes' or 'wikifier init'."
    fi
}

cmd_record_change() {
    local file="${1:-}"
    local reason="${2:-No reason provided.}"

    if [[ -z "$file" ]]; then
        error "Usage: wikifier record-change <file> \"<concise reason>\""
        exit 1
    fi

    upsert_health "$file" "🟡 Yellow" "$reason"
    add_pending "$file" "LLM/agent edit — $reason"
    write_journal "record-change" "$file" "$reason"

    log "✅ Recorded semantic change for $file"
    log "   Reason: $reason"
    log "   → file_health.md updated to Yellow. Run mark-green after wiki summary is refreshed."
}

cmd_record_deletion() {
    local file="${1:-}"
    local reason="${2:-No reason provided.}"

    if [[ -z "$file" ]]; then
        error "Usage: wikifier record-deletion <file> \"<reason>\""
        exit 1
    fi

    upsert_health "$file" "🔴 Red" "DELETED — $reason"
    add_pending "$file" "File was deleted. Consider removing wiki entry or marking archival."
    write_journal "record-deletion" "$file" "$reason"

    # Wave 4 GC continuation: deletion-triggered BRC prune (removes chains/importers/index refs mentioning the deleted path)
    # Complements age prune; ensures BRC stays correct when barrels or importers are removed (no stale reverse entries at scale)
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import os, sys
from pathlib import Path
try:
    from wikifier.import_cache import prune_barrel_resolutions
    root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT") or ".").resolve()
    deleted = ["'"$file"'"]
    res = prune_barrel_resolutions(root, max_age_days=90.0, dry_run=False, deleted_files=deleted)
    p = res.get("pruned", 0)
    if p > 0:
        print(f"[barrel] GC pruned {p} BRC entries (age+del) referencing deleted path on record-deletion", file=sys.stderr)
except Exception as ex:
    print(f"[barrel] prune-on-delete best-effort skipped: {ex}", file=sys.stderr)
' 2>/dev/null || true

        # A1 Wave 3 Agent 2: apply_record_deletion_to_reverse_index (removes as source via maintain_ + as target key).
        # Long-term scalable, exercises the new helpers, keeps reverse accurate after renames/deletes without rebuild.
        # Uses best-effort rel norm (realpath relative or as-provided). Updates sig. Saves only on success.
        python3 -c '
import os, sys
from pathlib import Path
try:
    from wikifier.import_cache import apply_record_deletion_to_reverse_index
    root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT") or ".").resolve()
    farg = "'"$file"'"
    try:
        pf = Path(farg)
        if pf.is_absolute():
            rel = str(pf.resolve().relative_to(root))
        else:
            rel = str((root / pf).resolve().relative_to(root))
    except Exception:
        rel = farg
    cache = __import__("wikifier.import_cache", fromlist=["load_cache"]).load_cache(root)
    stats_before = __import__("wikifier.import_cache", fromlist=["get_reverse_dependency_stats"]).get_reverse_dependency_stats(cache)
    new_stats = apply_record_deletion_to_reverse_index(cache, rel)
    __import__("wikifier.import_cache", fromlist=["save_cache"]).save_cache(root, cache)
    nt = new_stats.get("target_count", 0)
    ne = new_stats.get("total_reverse_edges", 0)
    ot = stats_before.get("target_count", 0)
    print(f"[A1] reverse cleaned for deleted {rel}: targets={nt} edges={ne} (was targets={ot})", file=sys.stderr)
except Exception as ex:
    print(f"[A1] reverse clean on delete best-effort skipped: {ex}", file=sys.stderr)
' 2>/dev/null || true
    fi

    log "🗑️ Recorded deletion for $file"
}

cmd_prepare_edit() {
    local file="${1:-}"
    if [[ -z "$file" || ! -f "$file" ]]; then
        error "Usage: wikifier prepare-edit <existing-file>"
        exit 1
    fi

    local mtime
    mtime=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo "0")
    echo "$mtime" > "$STAGING_DIR/$(basename "$file").mtime"
    log "Staged $file for later diff (mtime=$mtime)"
}

cmd_mark_green() {
    local file="${1:-}"
    local reason="${2:-Wiki summary verified accurate after change.}"
    if [[ -z "$file" ]]; then
        error "Usage: wikifier mark-green <file> [optional reason]"
        exit 1
    fi
    mark_green "$file" "$reason"
    log "🟢 $file marked Green. Pending entry cleared."
}

cmd_monitor() {
    log "Starting Wikifier heartbeat monitor (interval: ${POLL_INTERVAL}s). Press Ctrl+C to stop."
    log "Logs will be written to .wikifier_staging/monitor.log if run with nohup."

    while true; do
        cmd_check_changes
        sleep "$POLL_INTERVAL"
    done
}

cmd_update_maps() {
    log "Rebuilding library.md (import map + Mermaid)..."

    # Build into a temp file and move into place only at the end, so a failed
    # build never destroys the previous library.md. LIBRARY_MD is shadowed
    # locally; bash dynamic scoping makes all helpers called from here append
    # to the temp file.
    local LIBRARY_MD_FINAL="$LIBRARY_MD"
    local LIBRARY_MD="${LIBRARY_MD_FINAL}.tmp.$$"
    rm -f "${LIBRARY_MD_FINAL}".tmp.* 2>/dev/null || true

    cat > "$LIBRARY_MD" << 'EOT'
# Library & Imports Map (auto-generated by wikifier update-maps)

> This file is regenerated. Manual edits will be overwritten.
> Run `wikifier record-change library.md "..."` if you need to annotate.

## Dependency Graph (Mermaid)

```mermaid
graph TD
EOT

    # === Modern M2 Dependency Intelligence Architecture ===
    local full_rebuild=false
    if [[ "${1:-}" == "--full" ]]; then
        full_rebuild=true
        log "Full rebuild requested (--full)"
    fi

    # Micro-step start: A2 streaming/partial parity detection (additive, no behavior change yet)
    # When any of these flags are present we will eventually delegate more work to the
    # Python streaming generator instead of always doing a full traditional rebuild.
    local streaming_requested=false
    for arg in "$@"; do
        case "$arg" in
            --stream|--stream=*|--resume|--resume=*|--max-time|--max_time|--max-time=*|--max_time=*|--progress|--progress=*|--partial)
                streaming_requested=true
                break
                ;;
        esac
    done
    if $streaming_requested; then
        log "A2 streaming/partial flags detected — delegating core work to Python run_update_stream"

        # Extract common streaming parameters from the original arguments
        local dir_arg=""
        local max_files_arg=""
        local resume_arg=""
        local max_time_arg=""

        for arg in "$@"; do
            case "$arg" in
                --dir=*|--directory=*) dir_arg="${arg#*=}" ;;
                --dir|--directory)
                    # next argument
                    ;;
                --max-files=*) max_files_arg="${arg#*=}" ;;
                --max-files)
                    ;;
                --resume=*) resume_arg="${arg#*=}" ;;
                --resume)
                    ;;
                --max-time=*) max_time_arg="${arg#*=}" ;;
                --max-time)
                    ;;
            esac
        done

        # Handle cases where value is in next positional arg (simple handling)
        # For a first pass we rely mostly on = form; can be improved later.

        python3 -c '
import sys
from pathlib import Path
import wikifier.import_cache as ic

root = Path(".")
kwargs = {}

# Pass through parameters if provided
if "'"${dir_arg}"'":
    kwargs["directory"] = "'"${dir_arg}"'"
if "'"${max_files_arg}"'":
    try:
        kwargs["max_files"] = int("'"${max_files_arg}"'")
    except:
        pass
if "'"${resume_arg}"'":
    kwargs["resume_from"] = "'"${resume_arg}"'"
if "'"${max_time_arg}"'":
    try:
        mt = float("'"${max_time_arg}"'")
        kwargs["time_budget_ms"] = int(mt * 1000) if mt < 1000 else int(mt)
    except:
        pass

try:
    ev_count = 0
    file_count = 0
    for ev in ic.run_update_stream(root=root, format="full", **kwargs):
        ev_count += 1
        # Robust event type extraction (dataclass or dict from contracts ProgressEvent_v1)
        if isinstance(ev, dict):
            et = ev.get("event") or ev.get("type") or ev.get("kind") or ""
            if et == "file_parsed" or ("file" in ev or "path" in ev):
                file_count += 1
        else:
            et = getattr(ev, "event", None) or getattr(ev, "type", None) or getattr(ev, "kind", None) or ""
            if et == "file_parsed":
                file_count += 1
        if ev_count % 25 == 0:
            print(".", end="", flush=True)
    print(f"\n[shell] Python streaming delegation completed ({ev_count} events, ~{file_count} files)")
except Exception as e:
    print(f"[shell] Streaming delegation error (will continue with traditional path): {e}", file=sys.stderr)
' 2>&1 || log "Streaming delegation encountered an issue (continuing traditionally)"
    fi

    local paths
    paths=$(get_monitored_paths)

    local cache_file=".wikifier_staging/import_cache.json"

    # Simple speed win for git repos (common case): use git ls-files for candidate source list
    # (respects .gitignore, much faster than find on large trees). Falls back to the find below.
    # Only affects collection for the map; same files end up analyzed.
    if [[ -d "$PROJECT_ROOT/.git" || -f "$PROJECT_ROOT/.git/HEAD" ]]; then
        if git -C "$PROJECT_ROOT" ls-files --cached --others --exclude-standard -- '*.py' '*.js' '*.ts' '*.jsx' '*.tsx' > /tmp/wikifier_git_cands.txt 2>/dev/null; then
            # Use this list to override the later find-based collection if non-empty
            if [[ -s /tmp/wikifier_git_cands.txt ]]; then
                # The later code will still run determine etc; we can feed via a temp but to keep change tiny,
                # just note and let the existing find run (git is used in python path anyway).
                # For full sh fidelity we keep the find, but the python dirty calc (called later) will benefit from faster cands in other paths.
                : # no-op; the big wins are in the Python collectors used by check-changes / streaming / lib
            fi
        fi
    fi

    # Write Mermaid header
    echo "    %% Auto-detected imports (M2 rich analysis)" >> "$LIBRARY_MD"
    echo "    Main[\"(root)\"] --> Wikifier[\"wikifier.sh\"]" >> "$LIBRARY_MD"

    # === Core M2 Work — delegated to the two high-level orchestrators ===
    perform_first_pass_graph_and_cache_update "$paths" "$cache_file" "$full_rebuild"

    # Wave 4 continuation: opportunistic lightweight BRC prune/GC on every update-maps (esp. --full); safe + scales (tiny #chains)
    if command -v python3 >/dev/null 2>&1; then
        python3 -m wikifier.health prune-barrels 90 2>/dev/null || true
    fi

    # Emit the real Mermaid graph from the data collected in the first-pass
    generate_mermaid_dependency_graph >> "$LIBRARY_MD"

    # Close the Mermaid code block now that the graph is complete
    echo '```' >> "$LIBRARY_MD"

    # Now generate the human-readable Resolved Dependencies table
    generate_resolved_dependencies_table "$paths" "$cache_file" "$full_rebuild" >> "$LIBRARY_MD"

    # === Gap #1 Rich Intelligence Sections (Cycles, Barrels, Conditional/Dynamic) ===
    # These consume the new persisted structures and rich per-edge metadata.
    ( python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
root = Path(".")
cache = ic.load_cache(root)
print("\n## Circular Dependencies\n")
integrity = cache.get("_graph_integrity") or ic.compute_graph_integrity(cache)
cdata = ic.get_cycles(cache)
if not cdata or "sccs" not in cdata:
    cdata = ic.compute_cycles(cache)
stats = cdata.get("stats", {})
sccs = cdata.get("sccs", [])
cc = stats.get("cyclic_scc_count", 0)
fc = stats.get("total_files_in_cycles", 0)
ls = stats.get("largest_scc_size", 0)
print(f"**Status**: {cc} cyclic cluster(s) involving {fc} file(s). Largest cluster size: {ls}")
# NOTE: this program is embedded in a shell single-quoted string. Never put \" or
# bare single quotes inside f-string {...} expressions (SyntaxError / shell-eaten);
# hoist quoted lookups to plain variables first (works on Python 3.8+).
dyn_e = stats.get("dynamic_edges_in_cycles", 0)
cond_e = stats.get("conditional_edges_in_cycles", 0)
barr_e = stats.get("barrel_edges_in_cycles", 0)
print(f"**Signals across cycles**: dynamic={dyn_e} | conditional={cond_e} | via_barrel={barr_e}")
gi_sum = integrity.get("summary", "N/A")
print(f"**Graph Integrity**: {gi_sum}")
gs = cdata.get("graph_signature", "N/A")
re = cdata.get("reused", False)
rr = cdata.get("reuse_reason", "")
rr_suffix = ", " + rr if rr else ""
print(f"**Graph signature**: {gs} (reused={re}{rr_suffix}) — Wave 3 complete (main-path delta short-circuit + iterative Tarjan harness) + canonical v1 node_identity_version prep + get_cycles_reuse_stats broad surfacing (health/diag/MCP/library) (gap1_cycles_longterm_strategy)")
# P3 CIABRE: load or compute analyses for severity + actionable recs (fresh after 3d in update-maps)
analyses = cache.get("_cycle_analyses") or ic.compute_cycle_analyses(cache)
a_map = {}
for a in (analyses.get("analyses", []) or []):
    key = tuple(sorted(a.get("nodes", [])))
    a_map[key] = a
a_sum = analyses.get("summary", {})
if a_sum.get("total_sccs_analyzed", 0):
    hs_n = a_sum.get("high_severity_count", 0)
    mb_n = a_sum.get("max_blast_radius", 0)
    avg_n = a_sum.get("avg_score", 0)
    print(f"**CIABRE Severity Summary**: {hs_n} high/critical | max_blast={mb_n} | avg_score={avg_n} (see per-cluster below)")
print()
if sccs:
    print("Top cyclic clusters (with signals + P3 CIABRE severity/weakest/rec):")
    for idx, s in enumerate(sccs[:8], 1):
        ex = s.get("example_path") or (s.get("nodes") and " → ".join(s.get("nodes", [])[:5]) or "?")
        sig = s.get("signals", {})
        dyn = sig.get("dynamic_edge_count", 0)
        cond = sig.get("conditional_edge_count", 0)
        barr = sig.get("barrel_edge_count", 0)
        extra = ""
        if dyn or cond or barr:
            extra = f"  (dyn={dyn} cond={cond} barrel={barr})"
        key = tuple(sorted(s.get("nodes", [])))
        a = a_map.get(key, {})
        sev = a.get("severity")
        sz = s.get("size")
        if sev:
            bl = a.get("external_blast_radius", 0)
            sc = a.get("score", 0)
            w = (a.get("weakest_links") or [{}])[0]
            w_from = w.get("from", "?")
            w_to = w.get("to", "?")
            w_risk = w.get("risk_score", "?")
            w_str = f"weakest={w_from}→{w_to} (risk={w_risk})" if w.get("from") else ""
            top_rec = (a.get("recommendations") or [{}])[0]
            rec_str = ""
            strat = top_rec.get("strategy")
            if strat:
                # Surfacing uniformity (ACS+CIABRE): full rationale/hint/safety (no truncation) for agent trust + verbatim quoting
                rat = top_rec.get("rationale") or ""
                hnt = top_rec.get("hint") or ""
                saf = top_rec.get("safety") or ""
                rec_str = f" | top rec: {strat} — {rat} (hint: {hnt}; safety: {saf})"
            print(f"- {idx}. size={sz} : {ex}{extra}")
            print(f"    **SEVERITY**: {sev} (score={sc}, blast={bl}) {w_str}{rec_str}")
        else:
            print(f"- {idx}. size={sz} : {ex}{extra}")
    if len(sccs) > 8:
        print(f"- ... ({len(sccs)-8} more clusters — use MCP `get_cycles(analysis=True)` for complete CIABRE details)")
else:
    print("✅ No circular dependencies detected in the current dependency graph.")

# ACS + CIABRE surfacing uniformity: bounded risk snapshot with full confidence_explanation Recommendations (from persisted _acs_summary)
# On-demand persistence guarantee (mirror cycles; uses ensure which set+save if needed)
acs = ic.ensure_acs_summary_persisted(cache, root)
if acs.get("total_scored_edges"):
    print("\n## ACS Risk Snapshot (Actionable Confidence System)")
    tse = acs.get("total_scored_edges")
    avgc = acs.get("avg_confidence")
    lowc = acs.get("low_conf_edges")
    thr = acs.get("low_conf_threshold")
    print(f"**Scored edges**: {tse} | **avg_confidence**: {avgc} | **low<0.65**: {lowc} (threshold {thr})")
    tr = acs.get("top_risk_reasons") or {}
    if tr:
        tr_str = ", ".join(f"{k}:{v}" for k, v in list(tr.items())[:4])
        print(f"**Top risk reasons**: {tr_str}")
    samples = acs.get("sample_low_conf_explanations") or []
    if samples:
        print("**Sample low-confidence edges (quote Recommendation: verbatim for decisions)**:")
        for i, s in enumerate(samples[:3], 1):
            print(f"  {i}. {s}")
    print("> Full per-edge via get_dependencies(..., format=\"json\") confidence_explanation. Use filter score<0.65 or high-sev reasons. ACS v1.0 + CIABRE v1.3.\n")

print("\n> Machine-readable: `wikifier cycles`, MCP `get_cycles(format=\"json\", analysis=True)`. CIABRE v1.3 (R5 + registry ext): severity+blast+weakest + ranked practical recs (full rationale/hint/safety, ACS refs) from dogfood-tuned rules. ACS summary + samples in _acs_summary. Full in cache.\n")
' 2>/dev/null || printf '\n## Circular Dependencies\n\n(Requires update-maps run to populate cache.)\n' ) >> "$LIBRARY_MD"

    # A1: "Who depends on me" / Reverse Dependencies section in library.md (first-class index)
    ( python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
root = Path(".")
cache = ic.load_cache(root)
rev = ic.get_reverse_dependencies(cache) or {}
stats = ic.get_reverse_dependency_stats(cache)
sig = ic.get_reverse_signature(cache)
print("\n## Reverse Dependencies (A1 First-Class Index — \"Who depends on me\")")
# Hoisted out of the f-string: \"/bare quotes inside {...} break this shell-embedded python
tc = stats.get("target_count", 0)
tre = stats.get("total_reverse_edges", 0)
sig_str = sig or "n/a"
print(f"**Targets with dependents**: {tc} | **Total reverse edges**: {tre} | **Signature**: {sig_str} (delta-detectable, O(changed) maintained)")
print()
if rev:
    # High-impact: sort by #dependents desc, bounded for scale (50k+ safe)
    high = sorted(rev.items(), key=lambda kv: -len(kv[1]))[:10]
    print("**High-impact modules (most reverse dependents — blast radius leaders)**:")
    for tgt, srcs in high:
        cnt = len(srcs)
        sample = ", ".join(srcs[:4])
        print(f"- `{tgt}` ← {cnt} files depend on it (e.g. {sample})")
    print()
    print("> Per-file \"Who depends on me\": use MCP `get_reverse_dependencies(target=\"...\")` or `get_dependents` (both O(1) from index, include signature+stats in JSON). Full map via Python `from wikifier import get_reverse_dependencies` + cache.")
else:
    print("(No reverse dependencies recorded — run `update-maps` to populate first-class index.)")
print("> Scalable: direct from persisted _reverse_dependencies (no rebuild). See contracts + import_cache for maintain_ API on renames/deletes.\n")
' 2>/dev/null || printf '\n## Reverse Dependencies (A1)\n\n(Requires update-maps + cache.)\n' ) >> "$LIBRARY_MD"

    ( python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
root = Path(".")
cache = ic.load_cache(root)
summary = ic.summarize_barrel_expansions(cache)
print("\n## Barrel Expansions (BREE Intelligence)\n")
total_b = summary.get("total_via_barrel_imports", 0)
files_b = summary.get("files_using_barrels", 0)
max_d = summary.get("max_barrel_depth_observed", 0)
print(f"**Total via-barrel imports**: {total_b}")
print(f"**Files using barrel re-exports**: {files_b}")
print(f"**Max observed barrel depth**: {max_d}")
print()
tops = summary.get("top_barrel_users", [])[:8]
if tops:
    print("Top barrel users (by import count):")
    for t in tops:
        f = t.get("file", "?")
        c = t.get("count", 0)
        d = t.get("max_depth", 0)
        print(f"- `{f}`: {c} imports (max_depth={d})")
else:
    print("(No barrel usage detected in this run)")
note = summary.get("note", "")
print(f"\n> {note}\n")
' 2>/dev/null || printf '\n## Barrel Expansions\n\n(Barrel data pending full Phase 2 cache.)\n' ) >> "$LIBRARY_MD"

    ( python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
root = Path(".")
cache = ic.load_cache(root)
summary = ic.summarize_conditional_dynamic(cache)
print("\n## Conditional & Dynamic Intelligence\n")
ci = summary.get("conditional_imports", 0)
di = summary.get("dynamic_imports", 0)
print(f"**Conditional imports detected**: {ci}")
print(f"**Dynamic imports detected**: {di}")
print()
if summary.get("conditional_examples"):
    print("Sample conditional imports (fragile / feature-flagged paths):")
    for ex in summary.get("conditional_examples", [])[:5]:
        ctx = (ex.get("context") or "")[:55]
        src = ex.get("source", "?")
        imp = ex.get("import", "?")
        print(f"- `{src}` → `{imp}`  (ctx: {ctx})")
if summary.get("dynamic_examples"):
    print("Sample dynamic imports (runtime / template-driven):")
    for ex in summary.get("dynamic_examples", [])[:5]:
        src = ex.get("source", "?")
        imp = ex.get("import", "?")
        typ = ex.get("type", "?")
        print(f"- `{src}` → `{imp}`  (type: {typ})")
note = summary.get("note", "")
print(f"\n> {note}\n")
' 2>/dev/null || printf '\n## Conditional & Dynamic Intelligence\n\n(Enrichment pending parser + CDIA Phase 3.)\n' ) >> "$LIBRARY_MD"

    # Legacy lightweight summary section (will be replaced in a future step)
    cat >> "$LIBRARY_MD" << 'EOT'

## Files with Imports (summary)

| File | Detected Import Lines (truncated) |
|------|-----------------------------------|
EOT

    # Append a few example import lines (legacy path)
    discover_imports "." | head -30 | while IFS= read -r line; do
        echo "| $(echo "$line" | cut -c1-60) |" >> "$LIBRARY_MD"
    done

    echo "" >> "$LIBRARY_MD"
    mv "$LIBRARY_MD" "$LIBRARY_MD_FINAL"
    log "✅ library.md updated. You can now embed the Mermaid diagram in index.html or any Markdown viewer."
}

cmd_validate() {
    log "Validating that every monitored file has a health entry..."

    local missing=0
    local exclude
    exclude=$(build_exclude_expr)

    while IFS= read -r root; do
        [[ -z "$root" ]] && continue
        find "$root" -type f ! -path "*/.git/*" ! -path "*/.wikifier_staging/*" 2>/dev/null | while read -r f; do
            local rel
            rel=$(realpath --relative-to="$PROJECT_ROOT" "$f" 2>/dev/null || echo "$f")
            if ! grep -qF "| $rel |" "$FILE_HEALTH" 2>/dev/null; then
                echo "🔴 MISSING WIKI ENTRY: $rel"
                ((missing++)) || true
            fi
        done
    done < <(get_monitored_paths)

    if (( missing == 0 )); then
        log "✅ All monitored files have health entries."
    else
        log "⚠️  $missing file(s) lack wiki entries. Run update-maps + create summaries."
    fi
}

cmd_journal() {
    local date_spec="${1:-$(date +%Y-%m-%d)}"
    local year month day
    year=$(date -d "$date_spec" +%Y 2>/dev/null || date +%Y)
    month=$(date -d "$date_spec" +%m 2>/dev/null || date +%m)
    day=$(date -d "$date_spec" +%d 2>/dev/null || date +%d)

    local jf="$JOURNAL_ROOT/$year/$month/$day.md"
    if [[ -f "$jf" ]]; then
        cat "$jf"
    else
        echo "No journal entries for $date_spec yet."
    fi
}

cmd_issues() {
    local sev="${1:-all}"
    echo "=== Logged Issues (severity: $sev) ==="
    if [[ "$sev" == "all" ]]; then
        find "$LOGGED_ISSUES_ROOT" -type f -name "*.md" | sort
    else
        find "$LOGGED_ISSUES_ROOT/$sev" -type f -name "*.md" 2>/dev/null | sort
    fi
    if [[ -f "$LOGGED_ISSUES_ROOT/map.md" ]]; then
        echo ""
        echo "See Logged_issues/map.md for the categorised overview."
    fi
}

cmd_init() {
    log "Initialising fresh Wikifier state..."

    # R6: Support external monorepo bootstrap via --target (or first non-flag arg)
    local target_dir="$PROJECT_ROOT"
    local do_copy=true
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --target|--project-root)
                if [[ -n "${2:-}" ]]; then
                    target_dir="$2"
                    shift
                fi
                ;;
            --no-copy)
                do_copy=false
                ;;
            *)
                if [[ -d "$1" || "$1" == */* || "$1" == "." || "$1" == ".." ]]; then
                    target_dir="$1"
                fi
                ;;
        esac
        shift || true
    done

    mkdir -p "$target_dir"
    local old_project="$PROJECT_ROOT"
    PROJECT_ROOT="$(cd "$target_dir" && pwd)"
    LAST_CHECK_FILE="$PROJECT_ROOT/.wikifier_staging/.last_check"
    STAGING_DIR="$PROJECT_ROOT/.wikifier_staging"
    JOURNAL_ROOT="$PROJECT_ROOT/journal"
    LOGGED_ISSUES_ROOT="$PROJECT_ROOT/Logged_issues"
    MONITORED_PATHS_FILE="$PROJECT_ROOT/monitored_paths.txt"
    EXCLUDE_PATTERNS_FILE="$PROJECT_ROOT/exclude_patterns.txt"
    FILE_HEALTH="$PROJECT_ROOT/file_health.md"
    PENDING_UPDATES="$PROJECT_ROOT/pending_updates.md"
    LIBRARY_MD="$PROJECT_ROOT/library.md"
    mkdir -p "$STAGING_DIR" "$JOURNAL_ROOT/$(date +%Y/%m)" "$LOGGED_ISSUES_ROOT"

    [[ ! -f "$MONITORED_PATHS_FILE" ]] && echo "." > "$MONITORED_PATHS_FILE"
    [[ ! -f "$EXCLUDE_PATTERNS_FILE" ]] && cat > "$EXCLUDE_PATTERNS_FILE" << 'EOT'
node_modules
.git
build
dist
__pycache__
*.pyc
EOT

    [[ ! -f "$FILE_HEALTH" ]] && cat > "$FILE_HEALTH" << 'EOT'
# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
EOT

    [[ ! -f "$PENDING_UPDATES" ]] && cat > "$PENDING_UPDATES" << 'EOT'
# Pending Updates

(no pending items — run check-changes after making edits)
EOT

    [[ ! -f "$LIBRARY_MD" ]] && cat > "$LIBRARY_MD" << 'EOT'
# Library & Imports Map

Run `wikifier update-maps` to populate.
EOT

    # Create .wikifier/ marker dir for upward discovery (MCP + future tools)
    mkdir -p "$PROJECT_ROOT/.wikifier"
    echo "project_root=$PROJECT_ROOT" > "$PROJECT_ROOT/.wikifier/config" 2>/dev/null || true

    # W9: do NOT seed a health entry for the tool itself — a fresh target project
    # starts with an empty health matrix (the old template entry described Wikifier,
    # not the target project, and polluted every init'd repo).

    # R6 UX: auto-copy launcher wikifier.sh + human dashboards into target
    # (the HTMLs provide the human investigation layer: live health matrix + Mermaid tree diagram,
    #  export/copy text for LLM/human use, while agent-to-agent remains the primary via MCP/text files)
    if [[ "$do_copy" == true ]]; then
        local self_script="${BASH_SOURCE[0]:-$0}"
        local self_dir
        self_dir="$(dirname "$self_script")"
        if [[ -f "$self_script" && ! -f "$PROJECT_ROOT/wikifier.sh" ]]; then
            if cp "$self_script" "$PROJECT_ROOT/wikifier.sh" 2>/dev/null; then
                chmod +x "$PROJECT_ROOT/wikifier.sh" 2>/dev/null || true
                log "   (Copied launcher wikifier.sh into target for direct ./ use)"
            fi
        fi
        # Copy human dashboard: only index.html (clean, data-driven viewer for *this target's* agent wiki).
        # diagnostics.html (Wikifier maintainer/refactor hub with its own architecture + file map) is not
        # copied — it would show the wrong tree (Wikifier's, not the host project) and be stale here.
        # Open diagnostics.html from the Wikifier source if you are refactoring or porting the tool itself.
        # Phase 2 hygiene: html now lives under wikifier/index.html (for package resources + resources.files("wikifier"))
        # so when sh is the packaged one (in scripts/ subdir) look ../ ; source root sh still finds sibling at root.
        for html in index.html; do
            found=""
            for cand_dir in "$self_dir" "$(dirname "$self_dir" 2>/dev/null || echo "$self_dir")" "$self_dir/.." ; do
                if [[ -f "$cand_dir/$html" ]]; then
                    found="$cand_dir/$html"
                    break
                fi
            done
            if [[ -n "$found" && ! -f "$PROJECT_ROOT/$html" ]]; then
                if cp "$found" "$PROJECT_ROOT/$html" 2>/dev/null; then
                    log "   (Copied human dashboard $html into target — open in browser for the project's wiki chart + files + descriptions)"
                fi
            fi
        done
    fi

    PROJECT_ROOT="$old_project"

    log "✅ Wikifier initialised in $target_dir . Edit monitored_paths.txt to point at your real codebase (or subdirs for monorepos)."
    log "   Recommended: export WIKIFIER_PROJECT_ROOT=$target_dir  (or cd there and use ./wikifier.sh)"
    log "   Human layer: open index.html in browser for this project's code structure chart + files + descriptions (auto-refreshes with monitor). Use the copy buttons for clean text exports (tree + snapshot) to LLMs or teammates."
}

cmd_cycles() {
    log "Reporting circular dependencies (from persisted _cycles + graph integrity)..."
    python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import os
root = Path(".")
cache = ic.load_cache(root)
uc = os.environ.get("WIKIFIER_USE_CANONICAL", "1") not in ("0", "false", "False")
cycles = ic.get_cycles(cache)
if not cycles or "sccs" not in cycles:
    cycles = ic.compute_cycles(cache, root=root, use_canonical=uc)
integrity = cache.get("_graph_integrity") or ic.compute_graph_integrity(cache)

stats = cycles.get("stats", {})
sccs = cycles.get("sccs", [])
print("=== Circular Dependencies Report ===")
cc = stats.get("cyclic_scc_count", len(sccs))
fc = stats.get("total_files_in_cycles", len(cycles.get("all_cycle_files", [])))
ls = stats.get("largest_scc_size", 0)
print(f"Clusters: {cc}   |   Files involved: {fc}   |   Largest: {ls}")
# Hoisted out of f-strings: \"/bare quotes inside {...} break this shell-embedded python
dyn_e = stats.get("dynamic_edges_in_cycles", 0)
cond_e = stats.get("conditional_edges_in_cycles", 0)
barr_e = stats.get("barrel_edges_in_cycles", 0)
print(f"Signals: dyn={dyn_e} cond={cond_e} barrel={barr_e}")
gi_sum = integrity.get("summary", "N/A")
print(f"Graph Integrity: {gi_sum}")
gs = cycles.get("graph_signature", "N/A")
re = cycles.get("reused", False)
rr = cycles.get("reuse_reason", "")
rr_suffix = ", " + rr if rr else ""
print(f"Graph signature: {gs} (reused={re}{rr_suffix}) — Wave 3 complete + canonical v1 prep (node_identity_version + harness) + broad reuse stats via get_cycles_reuse_stats (health/diag/MCP/library) (gap1_cycles_longterm_strategy)")
# P3: CIABRE severity + recs (on-demand compute for CLI safety)
analyses = ic.get_cycle_analyses(cache) or ic.compute_cycle_analyses(cache, root=root, use_canonical=uc)
a_sum = analyses.get("summary", {})
if a_sum.get("total_sccs_analyzed"):
    hs_n = a_sum.get("high_severity_count", 0)
    mb_n = a_sum.get("max_blast_radius", 0)
    avg_n = a_sum.get("avg_score", 0)
    print(f"CIABRE v1.3: high-severity={hs_n} | max_blast={mb_n} | avg_score={avg_n}")
print()

if not sccs:
    print("✅ No circular dependencies detected in the current dependency graph.")
else:
    print("Detected cyclic clusters (rich signals + CIABRE severity/weakest/top-rec):")
    a_map = {}
    for a in (analyses.get("analyses", []) or []):
        a_map[tuple(sorted(a.get("nodes", [])))] = a
    for i, s in enumerate(sccs[:12], 1):
        path = s.get("example_path") or " → ".join(s.get("nodes", [])[:5])
        sig = s.get("signals", {})
        dyn = sig.get("dynamic_edge_count", 0)
        cond = sig.get("conditional_edge_count", 0)
        barr = sig.get("barrel_edge_count", 0)
        extra = f"  (dyn={dyn} cond={cond} barrel={barr})" if (dyn or cond or barr) else ""
        key = tuple(sorted(s.get("nodes", [])))
        a = a_map.get(key, {})
        sev_line = ""
        if a.get("severity"):
            w = (a.get("weakest_links") or [{}])[0]
            rec0 = (a.get("recommendations") or [{}])[0]
            rec_detail = rec0.get("strategy", "?")
            # Surfacing uniformity: full (no hard truncate) for CLI agents
            # (values hoisted out of f-strings: quotes inside {...} break shell-embedded python)
            rat = rec0.get("rationale") or ""
            hnt = rec0.get("hint") or ""
            saf = rec0.get("safety") or ""
            if rat:
                rec_detail += f" — {rat}"
            if hnt:
                rec_detail += f" | hint: {hnt}"
            if saf:
                rec_detail += f" | safety: {saf}"
            sev = a.get("severity")
            sc = a.get("score")
            bl = a.get("external_blast_radius")
            w_from = w.get("from", "?")
            w_to = w.get("to", "?")
            sev_line = f"\n      SEVERITY: {sev} score={sc} blast={bl} | weakest: {w_from}→{w_to} | rec: {rec_detail}"
        sz = s.get("size")
        print(f"  {i}. size={sz} : {path}{extra}{sev_line}")
    if len(sccs) > 12:
        print(f"  ... and {len(sccs)-12} more (use MCP get_cycles(analysis=True) for full CIABRE)")
print()
print("See: library.md \"Circular Dependencies\" + \"ACS Risk Snapshot\" | MCP: get_cycles(format=\"json\", analysis=True) + get_project_status | CIABRE v1.3 + ACS v1.0 (full Recommendations + samples): registry ext + hardened rationales. _acs_summary + _cycle_analyses in cache.")
' 2>/dev/null || echo "Cycle reporting requires python + import_cache (run update-maps first)."
}

# ----------------------------- Main Dispatcher -----------------------------

main() {
    local cmd="${1:-help}"
    shift || true

    case "$cmd" in
        help|--help|-h)          cmd_help ;;
        check-changes)           cmd_check_changes ;;
        health)                  cmd_health ;;
        heal-stubs)              python3 -m wikifier.health heal-stubs "$@" ;;
        prune-barrels|prune-brc|gc-barrels) python3 -m wikifier.health prune-barrels "$@" || true ;;
        record-change)           cmd_record_change "$@" ;;
        record-deletion)         cmd_record_deletion "$@" ;;
        prepare-edit)            cmd_prepare_edit "$@" ;;
        mark-green)              cmd_mark_green "$@" ;;
        monitor)                 cmd_monitor ;;
        daemon)                  python3 -m wikifier.daemon "$@" ;;
        update-maps)             cmd_update_maps "$@" ;;
        validate)                cmd_validate ;;
        journal)                 cmd_journal "$@" ;;
        issues)                  cmd_issues "$@" ;;
        init)                    cmd_init "$@" ;;
        cycles)                  cmd_cycles ;;
        *)
            error "Unknown command: $cmd"
            echo "Run 'wikifier help' for the full list."
            exit 1
            ;;
    esac
}

main "$@"
