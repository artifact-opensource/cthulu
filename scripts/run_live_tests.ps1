Param(
    [switch]$Yes,
    [int]$TimeoutSeconds = 30
)

if (-not $Yes) {
    Write-Host "This script will run integration tests that may call live APIs. Provide -Yes to proceed." -ForegroundColor Yellow
    exit 1
}

# Run pytest for integration tests only
python -m pytest tests/integration -q -k "providers_live" --maxfail=1 -q




