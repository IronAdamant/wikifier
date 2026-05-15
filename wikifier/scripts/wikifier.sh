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

# ----------------------------- Command Implementations -----------------------------

cmd_help() {
    cat << 'EOF'
Wikifier v0.3 — Agent-First Codebase Wiki (Zero Dependencies)

Usage: wikifier <command> [arguments]

Core Commands:
  check-changes              Scan monitored paths for mtime changes since last run.
                             Marks changed files Yellow + adds to pending_updates.
  health                     Pretty-print the current Documentation Health Matrix.
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

    # Very basic discovery — can be greatly improved per language
    local paths
    paths=$(get_monitored_paths)

    echo "    %% Auto-detected imports (lightweight scan)" >> "$LIBRARY_MD"

    # Placeholder nodes for now; real impl would parse and connect
    echo "    Main[\"(root)\"] --> Wikifier[\"wikifier.sh\"]" >> "$LIBRARY_MD"

    # Add a few real files if they exist in the tree
    find $paths -type f \( -name "*.py" -o -name "*.sh" -o -name "*.js" -o -name "*.ts" -o -name "*.md" \) \
        ! -path "*/.git/*" ! -path "*/node_modules/*" 2>/dev/null | head -30 | while read -r f; do
        local base
        base=$(basename "$f")
        echo "    $base[\"$base\"]" >> "$LIBRARY_MD"
    done

    cat >> "$LIBRARY_MD" << 'EOT'

```

## Files with Imports (summary)

| File | Detected Import Lines (truncated) |
|------|-----------------------------------|
EOT

    # Append a few example import lines
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
