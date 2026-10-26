<#
Monitor script with automatic restart policy.

Behavior:
- Tails `logs/cthulu.log` in real time.
- On detecting an ERROR or Traceback, appends context to `SYSTEM_REPORT.md`, attempts a safe restart of the running Cthulu process, and records the action.
- Continues until `RequiredSteadyMinutes` of uninterrupted runtime (no ERROR/Traceback) have elapsed.

Usage: (defaults suffice)
PowerShell -File .\monitor_cthulu.ps1 -RequiredSteadyMinutes 60 -MaxTotalMinutes 240
#>

param(
    [int]$RequiredSteadyMinutes = 60,
    [int]$MaxTotalMinutes = 240,
    [string]$PythonExe = "C:\\Users\\alish\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
    [string]$CthuluWorkingDir = "C:\\workspace\\cthulu"
)

$log = Join-Path $CthuluWorkingDir "logs\cthulu.log"
$report = Join-Path $CthuluWorkingDir "SYSTEM_REPORT.md"
$startTime = Get-Date
$endTime = $startTime.AddMinutes($MaxTotalMinutes)
$lastErrorTime = $null
$restartCount = 0

function Write-Report([string]$title, [string[]]$lines) {
    Add-Content $report "\n## $(Get-Date -Format o) - $title"
    foreach ($l in $lines) { Add-Content $report $l }
}

if (-not (Test-Path $log)) { Write-Host "Log not found: $log"; exit 1 }

Write-Host "Starting advanced monitor for $log"

# Helper: find and stop running cthulu processes (python processes with '-m cthulu')
function Stop-CthuluProcesses() {
    $killed = @()
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match '\-m\s+cthulu') }
    foreach ($p in $procs) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; $killed += $p.ProcessId } catch { Add-Content $report "Failed to kill process $($p.ProcessId): $_" }
    }
    return $killed
}

function Start-CthuluInstance() {
    Write-Report "Action" @("Starting Cthulu instance (auto-restart)")
    $psi = Start-Process -FilePath $PythonExe -ArgumentList "-m cthulu --config config.json" -WorkingDirectory $CthuluWorkingDir -WindowStyle Minimized -PassThru
    Add-Content $report "Started new Cthulu PID: $($psi.Id)"
    return $psi
}

# Begin monitoring
Get-Content $log -Tail 0 -Wait | ForEach-Object {
    $line = $_.ToString()
    # Basic detection
    if ($line -match 'ERROR' -or $line -match 'Traceback') {
        $lastErrorTime = Get-Date
        $restartCount++

        # Append immediate line and context to report
        Write-Report "Error detected" @($line)
        $context = Get-Content $log -Tail 200
        Write-Report "Context (last 200 lines)" $context

        # Attempt controlled restart
        Write-Report "Action" @("Attempting controlled restart (#$restartCount)")
        $killed = Stop-CthuluProcesses
        if ($killed.Count -gt 0) { Write-Report "Action" @("Killed PIDs: $($killed -join ', ')") }
        Start-Sleep -Seconds 3
        $newproc = Start-CthuluInstance
        Start-Sleep -Seconds 5
        Write-Report "Action" @("Restarted (PID $($newproc.Id)) - monitor will continue")
    }

    # Check steady-run condition
    if ($lastErrorTime -eq $null) {
        # No errors seen yet; require full steady interval from start
        if ((Get-Date) - $startTime -ge (New-TimeSpan -Minutes $RequiredSteadyMinutes)) {
            Write-Report "Success" @("No errors observed for $RequiredSteadyMinutes minutes. Monitoring complete.")
            exit 0
        }
    }
    else {
        if ((Get-Date) - $lastErrorTime -ge (New-TimeSpan -Minutes $RequiredSteadyMinutes)) {
            Write-Report "Success" @("No errors observed for $RequiredSteadyMinutes minutes since last incident. Monitoring complete.")
            exit 0
        }
    }

    if (Get-Date -ge $endTime) {
        Write-Report "Timeout" @("Reached max monitoring time ($MaxTotalMinutes minutes). Exiting. Last error time: $lastErrorTime")
        exit 2
    }
}
