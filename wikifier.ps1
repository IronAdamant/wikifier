# wikifier.ps1 — thin Windows launcher. Every command is implemented in Python:
#   .\wikifier.ps1 <command> [args]   ==   python -m wikifier <command> [args]
# Set $env:WIKIFIER_PYTHON to choose the interpreter.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($candidate in @($here, (Split-Path -Parent (Split-Path -Parent $here)))) {
    if ($candidate -and (Test-Path (Join-Path $candidate "wikifier\__init__.py"))) {
        $env:PYTHONPATH = if ($env:PYTHONPATH) { "$candidate;$env:PYTHONPATH" } else { $candidate }
        break
    }
}
$python = if ($env:WIKIFIER_PYTHON) { $env:WIKIFIER_PYTHON } else { "python" }
& $python -m wikifier @args
exit $LASTEXITCODE
