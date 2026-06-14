# Run the interactive/auto wizard then start Cthulu (skip setup, live mode)
# Double-click this file in Explorer (it will keep the window open at the end)

Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $scriptDir

Write-Host "[cthulu] Running wizard (auto defaults) --> scripts/run_wizard_auto.py" -ForegroundColor Cyan
# Run the non-interactive wizard that auto-accepts defaults
& python .\scripts\run_wizard_auto.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Wizard exited with code $LASTEXITCODE" -ForegroundColor Yellow
}

Write-Host "[cthulu] Starting Cthulu (skip setup, live mode)" -ForegroundColor Cyan
# Ensure PYTHONPATH includes the cthulu package directory
$env:PYTHONPATH = (Join-Path $scriptDir 'cthulu') + ';' + ($env:PYTHONPATH)

# Run Cthulu using the generated config.json and --skip-setup (live mode by default)
& python -m cthulu --config config.json --skip-setup
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cthulu process exited with code $LASTEXITCODE" -ForegroundColor Yellow
} else {
    Write-Host "Cthulu process finished normally." -ForegroundColor Green
}

Write-Host "\nPress Enter to close this window..." -ForegroundColor Cyan
Read-Host

Pop-Location
