# wikifier.ps1 — Wikifier v0.3 PowerShell implementation (Windows)
# Zero-dependency. Mirrors the most important commands from wikifier.sh

param(
    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$WikifierRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Staging = Join-Path $WikifierRoot ".wikifier_staging"
$JournalRoot = Join-Path $WikifierRoot "journal"
$HealthFile = Join-Path $WikifierRoot "file_health.md"
$PendingFile = Join-Path $WikifierRoot "pending_updates.md"
$LastCheck = Join-Path $Staging ".last_check"
$Monitored = Join-Path $WikifierRoot "monitored_paths.txt"
$Excludes = Join-Path $WikifierRoot "exclude_patterns.txt"

New-Item -ItemType Directory -Path $Staging -Force | Out-Null

function Write-Log { param([string]$m) Write-Host "[wikifier] $m" }
function Write-Err { param([string]$m) Write-Host "[wikifier ERROR] $m" -ForegroundColor Red }

function Get-Timestamp { Get-Date -Format "yyyy-MM-dd HH:mm:ss" }

function Upsert-Health {
    param([string]$file, [string]$status, [string]$reason = "")
    $now = Get-Timestamp

    if (-not (Test-Path $HealthFile)) {
        @"
# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
"@ | Set-Content $HealthFile
    }

    $content = Get-Content $HealthFile -Raw
    $pattern = [regex]::Escape("| $file |")

    if ($content -match $pattern) {
        $newLine = "| $file | $status | $now | $reason |"
        $content = [regex]::Replace($content, "\| $file \| .*? \| .*? \| .*? \|", $newLine, 1)
        Set-Content $HealthFile $content
    } else {
        Add-Content $HealthFile "| $file | $status | $now | $reason |"
    }
}

function Add-Pending {
    param([string]$file, [string]$msg)
    if (-not (Test-Path $PendingFile)) { " # Pending Updates" | Set-Content $PendingFile }
    Add-Content $PendingFile "- $file`: $msg"
}

function Write-Journal {
    param([string]$action, [string]$file, [string]$reason)
    $datePath = Join-Path $JournalRoot (Get-Date -Format "yyyy/MM")
    New-Item -ItemType Directory -Path $datePath -Force | Out-Null
    $dayFile = Join-Path $datePath ("{0:dd}.md" -f (Get-Date))
    @"

## [$(Get-Timestamp)] $action
**File:** $file
**Reason:** $reason

"@ | Add-Content $dayFile
}

# ---------------- Commands ----------------

switch ($Command.ToLower()) {
    "help" {
        Write-Host @"
Wikifier v0.3 (PowerShell/Windows)

Core:
  check-changes
  record-change <file> "<reason>"
  mark-green <file>
  health
  monitor
  update-maps
  init

See wikifier.sh for the full Unix implementation (recommended on WSL/macOS/Linux).
"@
    }
    "init" {
        if (-not (Test-Path $Monitored)) { "." | Set-Content $Monitored }
        if (-not (Test-Path $Excludes)) {
            @"
node_modules
.git
build
dist
"@ | Set-Content $Excludes
        }
        if (-not (Test-Path $HealthFile)) {
            @"
# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
"@ | Set-Content $HealthFile
        }
        Upsert-Health "wikifier.ps1" "🟢 Green" "Windows PowerShell CLI initialised."
        Write-Log "Wikifier Windows state initialised."
    }
    "check-changes" {
        Write-Log "Running change detection (PowerShell)..."
        $last = if (Test-Path $LastCheck) { Get-Content $LastCheck } else { "1970-01-01" }
        $roots = if (Test-Path $Monitored) { Get-Content $Monitored | Where-Object { $_ -notmatch '^\s*#' } } else { @(".") }

        $changed = 0
        foreach ($root in $roots) {
            if (-not (Test-Path $root)) { continue }
            Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -gt [datetime]$last } |
                ForEach-Object {
                    $rel = $_.FullName.Replace($WikifierRoot, "").TrimStart('\','/')
                    if ($rel -match '(\.git|node_modules|Logged_issues|journal|\.wikifier)') { return }
                    Upsert-Health $rel "🟡 Yellow" "mtime changed (PowerShell auto-detect)"
                    Add-Pending $rel "Auto-detected change on Windows"
                    $changed++
                }
        }
        Get-Date -Format "yyyy-MM-dd HH:mm:ss" | Set-Content $LastCheck
        Write-Log "Detected $changed file(s) changed."
    }
    "record-change" {
        $file = $Arguments[0]
        $reason = if ($Arguments.Count -gt 1) { $Arguments[1] } else { "No reason" }
        if (-not $file) { Write-Err "Usage: wikifier record-change <file> <reason>"; exit 1 }
        Upsert-Health $file "🟡 Yellow" $reason
        Add-Pending $file "record-change: $reason"
        Write-Journal "record-change" $file $reason
        Write-Log "Recorded change for $file"
    }
    "mark-green" {
        $file = $Arguments[0]
        if (-not $file) { Write-Err "Usage: wikifier mark-green <file>"; exit 1 }
        Upsert-Health $file "🟢 Green" "Verified on Windows."
        if (Test-Path $PendingFile) {
            (Get-Content $PendingFile) | Where-Object { $_ -notmatch [regex]::Escape($file) } | Set-Content $PendingFile
        }
        Write-Log "🟢 $file marked Green."
    }
    "health" {
        if (Test-Path $HealthFile) { Get-Content $HealthFile } else { Write-Host "Run init or check-changes first." }
    }
    "monitor" {
        Write-Log "Starting heartbeat monitor (Windows PowerShell)..."
        while ($true) {
            & $PSCommandPath check-changes
            Start-Sleep -Seconds 30
        }
    }
    default {
        Write-Err "Unknown command '$Command'. Try 'wikifier help'."
    }
}
