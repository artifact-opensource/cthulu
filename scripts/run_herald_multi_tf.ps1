param(
    [string]$Mindset = "aggressive",
    [string[]]$Symbols = @("GOLD#m"),
    [string[]]$Timeframes = @("TIMEFRAME_H1", "TIMEFRAME_M15"),
    [switch]$DryRun
)

# Helper to start Cthulu for multiple timeframes using configs stored under configs/mindsets/<mindset>/
$python = "python"

# Normalize timeframes input (allow comma-separated string)
if ($Timeframes -is [string]) { $Timeframes = $Timeframes -split ',' }
# Handle single-element arrays with comma-separated string
if (($Timeframes -is [object[]]) -and $Timeframes.Count -eq 1 -and ($Timeframes[0] -like '*,*')) { $Timeframes = $Timeframes[0] -split ',' }
$Timeframes = $Timeframes | ForEach-Object { $_.Trim() }

$startedCount = 0
# Normalize Symbols input (allow comma-separated string)
if ($Symbols -is [string]) { $Symbols = $Symbols -split ',' }
if (($Symbols -is [object[]]) -and $Symbols.Count -eq 1 -and ($Symbols[0] -like '*,*')) { $Symbols = $Symbols[0] -split ',' }
$Symbols = $Symbols | ForEach-Object { $_.Trim() }

foreach ($raw in $Timeframes) {
    $parts = @()
    if ($raw -like '*,*') { $parts = $raw -split ',' } else { $parts = @($raw) }
    foreach ($tf in $parts) {
        # Normalize suffix: accept either TIMEFRAME_H1 or h1/m15 etc.
        $suffix = $tf.Trim()
        if ($suffix -like 'TIMEFRAME_*') { $suffix = $suffix -replace '^TIMEFRAME_','' }
        $suffix = $suffix.ToLower()

        # Build config path relative to repo root
        $cfgDir = Join-Path -Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) -ChildPath "..\configs\mindsets\$Mindset"
        $fileName = "config_{0}_{1}.json" -f $Mindset, $suffix
        $cfgPath = Join-Path -Path $cfgDir -ChildPath $fileName

        if (-not (Test-Path $cfgPath)) {
            Write-Host "  [WARN] Config not found for timeframe '$tf' (expected: $cfgPath). Skipping." -ForegroundColor Yellow
            continue
        }

        foreach ($sym in $Symbols) {
            $argList = @('-m', 'cthulu', '--config', "$cfgPath", '--mindset', $Mindset, '--skip-setup', '--symbol', $sym)
            if ($DryRun) { $argList += '--dry-run' }

            Write-Host "Starting Cthulu for $sym on $tf using $cfgPath"
            $proc = Start-Process -FilePath $python -ArgumentList $argList -NoNewWindow -PassThru
            Write-Host "  -> Started PID: $($proc.Id)" -ForegroundColor Cyan
            $startedCount++
        }
    }
}

Write-Host "Started $startedCount Cthulu process(es)."




