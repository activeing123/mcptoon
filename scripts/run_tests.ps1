<#
run_tests.ps1 — run the test suite so a wedged test can never take the machine
down with it.

Why this exists (measured 2026-10-09)
-------------------------------------
`python -m pytest tests/` normally finishes in ~150s here. One run did not
finish at all: it was killed at 600s, and by then it had accumulated child
processes (each of ~65 tests can spawn `npx`/`uvx`/an MCP server over stdio).
The killed parent left the grandchildren orphaned, which is what a neighbour
agent saw as "hundreds of processes".

Two defences, and this script is the second one:
  1. `pyproject.toml` sets `timeout = 120` per test, so a wedged test fails and
     names itself instead of hanging forever.
  2. This wrapper puts a wall-clock ceiling on the *whole run* and, on expiry,
     kills the entire process tree — no orphans.

Usage
-----
    pwsh -File scripts/run_tests.ps1                 # whole suite
    pwsh -File scripts/run_tests.ps1 tests/test_doctor_errors.py
    pwsh -File scripts/run_tests.ps1 -TimeoutSec 900

Exit codes: the pytest exit code (0 = pass). 124 = the run hit the ceiling.
#>
param(
    [string[]]$Paths = @("tests/"),
    [int]$TimeoutSec = 900,
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo

$argv = @("-m", "pytest") + $Paths + @("-q", "--timeout=120", "--timeout-method=thread") + $ExtraArgs
Write-Host "==> python $($argv -join ' ')   (wall clock ceiling: ${TimeoutSec}s)"

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath "python" -ArgumentList $argv -PassThru -NoNewWindow
$exited = $p.WaitForExit($TimeoutSec * 1000)
$sw.Stop()

if (-not $exited) {
    Write-Host ""
    Write-Warning "pytest exceeded ${TimeoutSec}s - killing the whole process tree (PID $($p.Id))"
    # /T kills the tree: the point is the grandchildren, not pytest itself.
    & taskkill /PID $p.Id /T /F 2>&1 | Out-String | Write-Host
    Pop-Location
    exit 124
}

Write-Host ("==> finished in {0:N1}s (exit {1})" -f $sw.Elapsed.TotalSeconds, $p.ExitCode)
Pop-Location
exit $p.ExitCode
