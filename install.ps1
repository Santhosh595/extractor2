# One-line installer: checks Git + Python, clones extractor2, runs setup.
$ErrorActionPreference = 'Stop'
Write-Host "=== Extractor2 setup ===" -ForegroundColor Cyan

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Host "Git not found. Installing via winget..."
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { Write-Host "Git install failed. Install from https://git-scm.com and re-run." -ForegroundColor Red; exit 1 }
} else { Write-Host "Git found: $($git.Source)" }

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python not found. Installing via winget..."
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { Write-Host "Python install failed. Install from https://python.org and re-run." -ForegroundColor Red; exit 1 }
} else { Write-Host "Python found: $($py.Source)" }

$dest = "$env:USERPROFILE\extractor2"
if (Test-Path $dest) {
    Write-Host "Already cloned at $dest — updating..."
    Set-Location $dest; git pull
} else {
    git clone https://github.com/Santhosh595/extractor2.git $dest
    if ($LASTEXITCODE -ne 0) { Write-Host "Clone failed (network?). Check connection and re-run." -ForegroundColor Red; exit 1 }
    Set-Location $dest
}

Write-Host "`nNext: enter your Telegram bot token and chat id (saved encrypted, password-protected)." -ForegroundColor Yellow
python extractor2.py setup

Write-Host "`nDone. Preview:  python extractor2.py run --once --dry-run" -ForegroundColor Cyan
Write-Host "Schedule daily (Task Scheduler): see README."
