#!/bin/bash
# wikifier.sh — Wikifier v0.3 Core CLI (Zero-Dependency)
# Agent-first shell tool for codebase documentation health & semantic change tracking.
#
# Usage:
#   ./wikifier.sh <command> [args]
#   (Optionally symlink or alias as 'wikifier' in your PATH)
#
# Commands implemented:
#   help, check-changes, health, record-change, record-deletion,
#   prepare-edit, mark-green, monitor, update-maps, validate,
#   journal, issues, init

set -euo pipefail

# ----------------------------- Configuration -----------------------------
WIKIFIER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAST_CHECK_FILE="$WIKIFIER_ROOT/.wikifier_staging/.last_check"
STAGING_DIR="$WIKIFIER_ROOT/.wikifier_staging"
JOURNAL_ROOT="$WIKIFIER_ROOT/journal"
LOGGED_ISSUES_ROOT="$WIKIFIER_ROOT/Logged_issues"
MONITORED_PATHS_FILE="$WIKIFIER_ROOT/monitored_paths.txt"
EXCLUDE_PATTERNS_FILE="$WIKIFIER_ROOT/exclude_patterns.txt"
FILE_HEALTH="$WIKIFIER_ROOT/file_health.md"
PENDING_UPDATES="$WIKIFIER_ROOT/pending_updates.md"
LIBRARY_MD="$WIKIFIER_ROOT/library.md"
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
    if [[ -f "$MONITORED_PATHS_FILE" ]]; then
        grep -vE '^\s*(#|$)' "$MONITORED_PATHS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
    else
        echo "."
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
# and emits one "raw|module|confidence" line per import.
# This replaces all previous crude grep hacks for Python and makes JS handling consistent.
parse_parser_json_output() {
    local json_file="$1"
    local lang="$2"   # python | javascript  (for future differences)

    # Use python3 -c for robust JSON handling (no fragile grep)
    python3 -c '
import json, sys
data = json.load(sys.stdin)
for item in data:
    raw = item.get("raw_module") or item.get("module") or ""
    mod = item.get("module") or ""
    conf = item.get("resolution_confidence") or "medium"
    if raw or mod:
        print(f"{raw}|{mod}|{conf}")
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
    local normalized_input="$2"   # raw|mod|conf lines (can be heredoc or variable)
    local lang="$3"               # python | javascript (informational for now)

    # Output: one "raw|resolved|conf" line per import (for caller to collect)
    # Side effects: updates reverse dependency state and modules_str (via caller globals for now)

    while IFS='|' read -r raw mod conf; do
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

        # Emit the rich pair line including source file for better table quality:
        # src_file|raw|resolved|confidence
        printf '%s|%s|%s|%s\n' "$src_file" "$raw" "$resolved" "$actual_conf"

        # Note: reverse dependency recording and modules_str accumulation
        # will be driven by the caller (the high-level first-pass helper)
        # once we introduce the node maps and cache structures.
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
    local current_mtime_map="$2"   # optional: for staleness checks

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
    if declare -p resolved_pairs 2>/dev/null | grep -q 'declare -a'; then
        # Sort for nicer output (by source file, then raw import)
        local sorted_pairs
        sorted_pairs=$(printf '%s\n' "${resolved_pairs[@]}" | sort)

        while IFS= read -r pair; do
            [[ -z "$pair" ]] && continue
            IFS='|' read -r src_file raw resolved conf <<< "$pair"
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

    # Load cache data once (for dependents / reverse impact styling)
    local cache_json=""
    local root="${WIKIFIER_ROOT:-.}"
    if [[ -f "$root/.wikifier_staging/import_cache.json" ]]; then
        cache_json=$(python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import json
root = Path(sys.argv[1])
cache = ic.load_cache(root)
out = {"dependents": {}, "reverse": ic.get_reverse_dependencies(cache)}
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
    for pair in "${resolved_pairs[@]}"; do
        IFS='|' read -r src_file raw resolved conf <<< "$pair"
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
            ((edge_count++))
        fi
    done

    if (( ${#mermaid_edges[@]} > max_edges )); then
        echo "    %% (Graph truncated — ${#mermaid_edges[@]} total edges)"
    fi

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
                    ((styled++))
                fi
            done
        fi
    done

    # Simple legend
    echo ""
    echo "    %% === Legend ==="
    echo "    %% -->     high confidence forward"
    echo "    %% -.->    medium / reverse dependency"
    echo "    %% -..->   low or cached"
    echo "    %% highImpact = many files depend on this module"
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
    declare -ga resolved_pairs=()   # src|raw|resolved|confidence lines from this run

    # Helper to record reverse dependencies (target → list of sources that import it)
    record_reverse_dep() {
        local source_file="$1"
        local resolved_target="$2"
        [[ -z "$resolved_target" || -z "$source_file" ]] && return
        if [[ " ${reverse_deps[$resolved_target]} " != *" $source_file "* ]]; then
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
            rel_file=$(realpath --relative-to="$WIKIFIER_ROOT" "$file" 2>/dev/null || echo "$file")

            local parser_cmd
            if [[ "$lang" == "python" ]]; then
                parser_cmd="python3 wikifier/parsers/python.py"
            else
                parser_cmd="python3 wikifier/parsers/javascript.py"
            fi

            local json_output
            json_output=$($parser_cmd "$file" 2>/dev/null || echo "[]")

            local normalized
            normalized=$(parse_parser_json_output <(echo "$json_output") "$lang")

            local pairs
            pairs=$(process_file_imports "$rel_file" "$normalized" "$lang")

            while IFS='|' read -r src raw resolved conf; do
                [[ -n "$resolved" ]] && resolved_pairs+=("$src|$raw|$resolved|$conf")
                record_reverse_dep "$src" "$resolved"
            done <<< "$pairs"
        done
    }

    # === Phase 1: Collect source files and determine what needs re-parsing ===
    # Find all relevant source files
    while IFS= read -r f; do
        case "$f" in
            *.py) python_files+=("$f") ;;
            *.js|*.ts|*.jsx|*.tsx) js_files+=("$f") ;;
        esac
    done < <(find $paths -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" \) \
        ! -path "*/.git/*" ! -path "*/node_modules/*" 2>/dev/null | sort)

    # Determine which files actually need re-parsing this run.
    # This helper encapsulates the mtime-based dirty detection and
    # reverse dependency pre-loading from the cache.
    determine_files_to_reparse() {
        declare -gA files_to_reparse=()

        if [[ "$full_rebuild" == "true" || ! -f "$import_cache_file" ]]; then
            files_to_reparse=("${python_files[@]}" "${js_files[@]}")
            return
        fi

        # Load cache using the official module
        while IFS= read -r rel; do
            [[ -z "$rel" ]] && continue
            full_path="$WIKIFIER_ROOT/$rel"

            # Get cached mtime
            cached_mtime=$(python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
root = Path(os.environ.get("WIKIFIER_ROOT", "."))
cache = ic.load_cache(root)
data = ic.get_file_data(cache, sys.argv[1])
print(data.get("mtime", 0) if data else 0)
' "$rel" 2>/dev/null || echo 0)

            # Pre-load reverse dependencies from cache (one-time)
            if [[ -z "${reverse_deps_loaded:-}" ]]; then
                python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import json, sys
root = Path(os.environ.get("WIKIFIER_ROOT", "."))
cache = ic.load_cache(root)
rev = ic.get_reverse_dependencies(cache)
print(json.dumps(rev))
' 2>/dev/null | while IFS= read -r jsonline; do
                    if [[ -n "$jsonline" && "$jsonline" != "{}" ]]; then
                        echo "$jsonline" | python3 -c '
import json,sys
for k, v in json.load(sys.stdin).items():
    print(f"{k}|{",".join(v)}")
' | while IFS='|' read -r tgt sources; do
                            [[ -n "$tgt" ]] && reverse_deps["$tgt"]="$sources"
                        done
                    fi
                done
                reverse_deps_loaded=1
            fi

            current_mtime=0
            if [[ -f "$full_path" ]]; then
                current_mtime=$(stat -c %Y "$full_path" 2>/dev/null || echo 0)
            fi

            if [[ "$current_mtime" -gt "$cached_mtime" ]]; then
                files_to_reparse+=("$full_path")
            fi
        done < <(python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
root = Path(os.environ.get("WIKIFIER_ROOT", "."))
cache = ic.load_cache(root)
for rel in cache.keys():
    print(rel)
' 2>/dev/null)

        # New files not yet in the cache must be re-parsed
        for f in "${python_files[@]}" "${js_files[@]}"; do
            rel=$(realpath --relative-to="$WIKIFIER_ROOT" "$f" 2>/dev/null || echo "")
            if [[ -n "$rel" ]]; then
                has_cache=$(python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys
root = Path(os.environ.get("WIKIFIER_ROOT", "."))
cache = ic.load_cache(root)
print("yes" if sys.argv[1] in cache else "no")
' "$rel" 2>/dev/null || echo "no")
                if [[ "$has_cache" != "yes" ]]; then
                    files_to_reparse+=("$f")
                fi
            fi
        done
    }

    declare -ga files_to_reparse=()
    determine_files_to_reparse

    # Fallback safety
    if [[ ${#files_to_reparse[@]} -eq 0 ]]; then
        files_to_reparse=("${python_files[@]}" "${js_files[@]}")
    fi

    debug_log "Files collected: ${#python_files[@]} Python, ${#js_files[@]} JS/TS"
    debug_log "Files to reparse: ${#files_to_reparse[@]}"

    if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
        debug_log "=== Files selected for re-parsing ==="
        for f in "${files_to_reparse[@]}"; do
            rel=$(realpath --relative-to="$WIKIFIER_ROOT" "$f" 2>/dev/null || echo "$f")
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
            ((count++))
            [[ $count -ge 10 ]] && break
        done
        debug_log "=== End of sample ==="
    fi

        # === Phase 3: Persist rich data back into the cache ===
    persist_rich_cache_data() {
        # 3a. Save resolved_pairs + dependents for files we re-parsed
        if [[ ${#files_to_reparse[@]} -gt 0 ]]; then
            python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys, os
from collections import defaultdict

root = Path(os.environ.get("WIKIFIER_ROOT", "."))
cache = ic.load_cache(root)
file_pairs = defaultdict(list)

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    parts = line.split("|", 3)
    if len(parts) == 4:
        src, raw, resolved, conf = parts
        file_pairs[src].append({"raw": raw, "resolved": resolved, "confidence": conf})

for src, pairs in file_pairs.items():
    if not pairs: continue
    try:
        full_path = root / src
        mtime = ic.get_mtime(full_path) if full_path.exists() else 0
        ic.update_file_data(cache, src, mtime, [], resolved_pairs=pairs)
    except Exception:
        pass

ic.save_cache(root, cache)
print(f"Saved rich cache entries for {len(file_pairs)} files", file=sys.stderr)
' <<< "$(printf '%s\n' "${resolved_pairs[@]}")" 2>/dev/null || true
        fi

        # 3b. Store per-file dependents list for each re-parsed file
        for src in "${files_to_reparse[@]}"; do
            rel=$(realpath --relative-to="$WIKIFIER_ROOT" "$src" 2>/dev/null || echo "$src")
            dependents_list="${reverse_deps[$rel]:-}"
            if [[ -n "$dependents_list" ]]; then
                python3 -c '
from pathlib import Path
import wikifier.import_cache as ic
import sys
root = Path(os.environ.get("WIKIFIER_ROOT", "."))
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

root = Path(os.environ.get("WIKIFIER_ROOT", "."))
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
root = Path(os.environ.get("WIKIFIER_ROOT", "."))
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
                # Old cache entries do not store confidence (added later).
                # Map to "medium" for clean table output. Future cache writes
                # will store richer confidence when we update update_file_data calls.
                print(f"{rel}|{raw}|{resolved}|medium")
' 2>/dev/null | while IFS= read -r line; do
            [[ -n "$line" ]] && resolved_pairs+=("$line")
        done <<< "$(printf '%s\n' "${files_to_reparse[@]}")"
    fi

    echo "> First-pass: re-parsed ${#files_to_reparse[@]} files + merged cached pairs for unchanged files"
    echo "> First-pass graph & cache update complete (hardened incremental mode)"

    # Final debug summary
    if [[ "${WIKIFIER_DEBUG:-0}" == "1" || "${WIKIFIER_DEBUG:-0}" == "true" ]]; then
        debug_log "=== DEBUG SUMMARY ==="
        debug_log "  Total resolved_pairs collected: ${#resolved_pairs[@]}"
        debug_log "  Unique targets with reverse dependencies: ${#reverse_deps[@]}"
        debug_log "  Would have persisted data for ${#files_to_reparse[@]} files"
        debug_log "=== End of debug summary ==="
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
# Handles common patterns: from . import X, from ..parsers import python, import "./utils".
# Returns a normalized module path relative to project root when possible.
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
        ((up++))
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
        candidate=$(realpath --relative-to="$WIKIFIER_ROOT" "$target_dir/$temp" 2>/dev/null || echo "")
    else
        candidate=$(realpath --relative-to="$WIKIFIER_ROOT" "$dir/$raw" 2>/dev/null || echo "")
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
# Improved package root detection: when we hit __init__.py or package.json,
# we try to construct a better module path relative to that package root.
# Returns "resolved_name|confidence" where confidence can be "high" if marker found.
_try_resolve_bare_internal_import() {
    local bare_name="$1"
    local current_file="$2"

    local dir
    dir=$(dirname "$current_file" 2>/dev/null || echo ".")
    local root="$WIKIFIER_ROOT"

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
        ((depth++))
    done

    local result="${resolved}|${conf}"
    _bare_resolve_cache[$cache_key]="$result"

    echo "$result"
}

# ----------------------------- Command Implementations -----------------------------

cmd_help() {
    cat << 'EOF'
Wikifier v0.3 — Agent-First Codebase Wiki (Zero Dependencies)

Usage: wikifier <command> [arguments]

Core Commands:
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

Information Commands:
  journal [date]             Show today's (or given YYYY-MM-DD) journal entries.
  issues [severity]          List Logged_issues (simple|moderate|high|critical).
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
            rel_file=$(realpath --relative-to="$WIKIFIER_ROOT" "$file" 2>/dev/null || echo "$file")

            upsert_health "$rel_file" "🟡 Yellow" "mtime changed since last check-changes (auto-detected)"
            add_pending "$rel_file" "Auto-detected modification — review and run mark-green after wiki update"
            write_journal "auto-detected" "$rel_file" "File mtime changed (check-changes)"

            ((changed++))
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

    local paths
    paths=$(get_monitored_paths)

    local cache_file=".wikifier_staging/import_cache.json"

    # Write Mermaid header
    echo "    %% Auto-detected imports (M2 rich analysis)" >> "$LIBRARY_MD"
    echo "    Main[\"(root)\"] --> Wikifier[\"wikifier.sh\"]" >> "$LIBRARY_MD"

    # === Core M2 Work — delegated to the two high-level orchestrators ===
    perform_first_pass_graph_and_cache_update "$paths" "$cache_file" "$full_rebuild"

    # Emit the real Mermaid graph from the data collected in the first-pass
    generate_mermaid_dependency_graph >> "$LIBRARY_MD"

    # Close the Mermaid code block now that the graph is complete
    echo '```' >> "$LIBRARY_MD"

    # Now generate the human-readable Resolved Dependencies table
    generate_resolved_dependencies_table "$paths" "$cache_file" "$full_rebuild" >> "$LIBRARY_MD"

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
            rel=$(realpath --relative-to="$WIKIFIER_ROOT" "$f" 2>/dev/null || echo "$f")
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
    echo ""
    echo "See Logged_issues/map.md for the categorised overview."
}

cmd_init() {
    log "Initialising fresh Wikifier state..."

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

    # Seed a first health entry for the tool itself
    upsert_health "wikifier.sh" "🟢 Green" "Core CLI implemented and documented."

    log "✅ Wikifier initialised. Edit monitored_paths.txt to point at your real codebase."
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
        record-change)           cmd_record_change "$@" ;;
        record-deletion)         cmd_record_deletion "$@" ;;
        prepare-edit)            cmd_prepare_edit "$@" ;;
        mark-green)              cmd_mark_green "$@" ;;
        monitor)                 cmd_monitor ;;
        update-maps)             cmd_update_maps ;;
        validate)                cmd_validate ;;
        journal)                 cmd_journal "$@" ;;
        issues)                  cmd_issues "$@" ;;
        init)                    cmd_init ;;
        *)
            error "Unknown command: $cmd"
            echo "Run 'wikifier help' for the full list."
            exit 1
            ;;
    esac
}

main "$@"
