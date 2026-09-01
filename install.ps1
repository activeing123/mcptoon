# mcptoon one-line installer (Windows PowerShell 5.1+ / pwsh)
#   irm https://raw.githubusercontent.com/activeing123/mcptoon/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

function Write-Info { param($m) Write-Host "  $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "  $m" -ForegroundColor Green }
function Write-Err  { param($m) Write-Host "  $m" -ForegroundColor Red }

Write-Host ""
Write-Host "  mcptoon installer - zero-dependency MCP gateway"
Write-Host "  ------------------------------------------------"

# 1. Find Python 3.10+ (py launcher first, then python)
$py = $null
foreach ($cand in @("py", "python", "python3")) {
    try {
        $v = & $cand -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ($v -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 10) { $py = $cand; break }
    } catch { }
}
if (-not $py) {
    Write-Err "Python 3.10+ not found. Install it first: https://www.python.org/downloads/"
    Write-Err "Or: winget install Python.Python.3.12   <- then re-run this script"
    exit 1
}
Write-Info "Found Python $(& $py -c "import sys;print('%d.%d'%sys.version_info[:2])")"

# 2. Install mcptoon (pip --user; handles PEP 668 style blocks via --user too)
& $py -m pip install --user --quiet mcptoon 2>&1 | ForEach-Object { }
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed. Try manually: $py -m pip install --user mcptoon"
    exit 1
}
Write-Ok "Installed via pip --user"

# 3. Make sure the user Scripts dir is on PATH for THIS session and persist it
$userScripts = & $py -c "import site;print(site.USER_SITE.replace('Lib\\site-packages','Scripts').replace('lib/site-packages','Scripts'))"
if (-not $userScripts) {
    $userScripts = Join-Path $env:APPDATA "Python\Scripts"
}
if (Test-Path $userScripts) {
    if ($env:PATH -notlike "*$userScripts*") {
        $env:PATH = "$userScripts;$env:PATH"
        try {
            $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if ($userPath -notlike "*$userScripts*") {
                [Environment]::SetEnvironmentVariable("Path", "$userPath;$userScripts", "User")
                Write-Info "Added $userScripts to your PATH (new terminals only)"
            }
        } catch { }
    }
}

# 4. Verify + hand off to quickstart
$bin = Get-Command mcptoon -ErrorAction SilentlyContinue
if (-not $bin) {
    Write-Err "mcptoon not on PATH yet. Open a NEW terminal and run: mcptoon quickstart"
    exit 1
}
Write-Ok "mcptoon ready: $($bin.Source)"
Write-Host ""
& mcptoon quickstart
