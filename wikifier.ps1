# Launch the Rust wikifier binary.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($env:WIKIFIER_BIN) { & $env:WIKIFIER_BIN @args; exit $LASTEXITCODE }
foreach ($rel in @("target\release\wikifier.exe", "target\debug\wikifier.exe")) {
    $cand = Join-Path $here $rel
    if (Test-Path $cand) { & $cand @args; exit $LASTEXITCODE }
}
cargo run --quiet --manifest-path (Join-Path $here "Cargo.toml") -- @args
exit $LASTEXITCODE
