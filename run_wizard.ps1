# Run the interactive setup wizard then start Cthulu (manual selection)
# Double-click this file in Explorer (it will keep the window open at the end)

Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $scriptDir

Write-Host "[cthulu] Running interactive wizard --> scripts/run_wizard_manual.py" -ForegroundColor Cyan
# Run the interactive wizard (operator will be prompted)
& python .\scripts\run_wizard_manual.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Wizard exited with code $LASTEXITCODE" -ForegroundColor Yellow
    Pop-Location
    exit $LASTEXITCODE
}

# Ensure PYTHONPATH includes the cthulu package directory
$env:PYTHONPATH = (Join-Path $scriptDir 'cthulu') + ';' + ($env:PYTHONPATH)

Write-Host "[cthulu] Starting Cthulu (skip setup, live mode)" -ForegroundColor Cyan
& python -m cthulu --config config.json --skip-setup
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cthulu process exited with code $LASTEXITCODE" -ForegroundColor Yellow
} else {
    Write-Host "Cthulu process finished normally." -ForegroundColor Green
}

Write-Host "`nPress Enter to close this window..." -ForegroundColor Cyan
Read-Host

Pop-Location
