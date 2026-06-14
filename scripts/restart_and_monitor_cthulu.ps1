# Restart Cthulu safely and monitor logs for errors
$log = Join-Path $PSScriptRoot '..\logs\Cthulu.log'
$monitorOut = Join-Path $PSScriptRoot '..\logs\monitor_matches.log'

Write-Output "Checking for existing Cthulu-related processes..."
# Match processes that are likely running the Cthulu runtime (avoid matching this script)
$pattern = '(?i)run_cthulu_startup\.bat|cthulu[\\/].*__main__|cthulu[\\/]__main__|Cthulu\.py'
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match $pattern) -and ($_.ProcessId -ne $PID) }
if ($procs) {
    foreach ($p in $procs) {
        Write-Output "Stopping PID $($p.ProcessId): $($p.CommandLine)"
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { Write-Output "Failed to stop PID $($p.ProcessId): $_" }
    }
} else {
    Write-Output "No running cthulu processes found"
}

Write-Output "Starting Cthulu via run_cthulu_startup.bat..."
Start-Process -FilePath .\run_cthulu_startup.bat -WorkingDirectory (Resolve-Path .).ProviderPath
Start-Sleep -Seconds 5

Write-Output "Monitoring logs for 120 seconds (pattern: Traceback|ERROR|CRITICAL)."
if (Test-Path $monitorOut) { Remove-Item $monitorOut -ErrorAction SilentlyContinue }
$end = (Get-Date).AddSeconds(120)
$seen = @{}
while ((Get-Date) -lt $end) {
    try {
        $matches = Select-String -Path $log -Pattern 'Traceback|ERROR|CRITICAL' -AllMatches | ForEach-Object { $_.Line }
        foreach ($m in $matches) {
            if (-not $seen.ContainsKey($m)) {
                $seen[$m] = $true
                $m | Out-File -FilePath $monitorOut -Append -Encoding utf8
                Write-Output "[MATCH] $m"
            }
        }
    } catch {
        Write-Output "Error reading log: $_"
    }
    Start-Sleep -Seconds 5
}

if (Test-Path $monitorOut) {
    Write-Output "Monitoring complete. Matches logged to $monitorOut"
    Get-Content $monitorOut -Tail 200
} else {
    Write-Output "Monitoring complete. No matching errors found in log during the period."
}
