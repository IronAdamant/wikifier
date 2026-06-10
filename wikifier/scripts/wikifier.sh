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

# =============================================================================
# update-maps implementation note (2026-06-10 thin-shell rework)
#
# The in-shell first-pass (per-file parser spawns, pipe-format normalization,
# shell resolvers, Mermaid/table generators — ~1,750 lines) was retired in
# favor of delegating cmd_update_maps to the Python pipeline, which performs
# the same work in-process at ~100-1000x the speed and is covered by the test
# suite. See cmd_update_maps below and git history for the removed code.
# =============================================================================

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
    # Thin delegation (the long-stated "shell becomes thin" goal): the full
    # pipeline — dirty detection, in-process parsing, canonical cache persist,
    # cycles/ACS/reverse deps, atomic library.md — lives in the Python package
    # (wikifier.cli.run_full_update). The old in-shell first-pass spawned one
    # Python interpreter per file (~12s/file on real projects) and its
    # incremental merge block could deadlock on stdin; both are retired
    # (Logged_issues/2026-06-10-brc-scoped-rerun-pathology.md). python3 + the
    # wikifier package were already hard requirements of this command.
    if [[ -n "${WIKIFIER_SH_UPDATE_MAPS_DELEGATED:-}" ]]; then
        error "update-maps delegation loop detected. Run 'python3 -m wikifier update-maps' directly."
        return 1
    fi
    if ! python3 -c "import wikifier" 2>/dev/null; then
        error "update-maps requires the wikifier Python package (pip install wikifier)."
        return 1
    fi
    log "Rebuilding import cache + library.md (delegating to the Python pipeline)..."
    local args=()
    local a
    for a in "$@"; do
        case "$a" in
            --sh|--legacy-sh|--no-python-primary) ;;  # consumed: this IS the shell entry
            *) args+=("$a") ;;
        esac
    done
    WIKIFIER_SH_UPDATE_MAPS_DELEGATED=1 WIKIFIER_PROJECT_ROOT="$PROJECT_ROOT" \
        python3 -m wikifier update-maps ${args[@]+"${args[@]}"}
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
