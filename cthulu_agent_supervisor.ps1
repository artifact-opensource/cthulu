param(
    [Parameter(Mandatory = $true)]
    [string]$EnvironmentFile,
    [Parameter(Mandatory = $true)]
    [ValidateSet('config.json', 'config_multi.json')]
    [string]$Config,
    [switch]$OpenDashboard,
    [switch]$HighFrequency
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$killSwitchPath = Join-Path $projectRoot '.cthulu.killswitch'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$environmentPath = [System.IO.Path]::GetFullPath($EnvironmentFile)
$configPath = Join-Path $projectRoot $Config
$logsDirectory = Join-Path $projectRoot 'logs'
$supervisorLog = Join-Path $logsDirectory 'Cthulu_agent_supervisor.log'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtualenv Python not found: $python"
}
if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
    throw "Agent environment file not found: $environmentPath"
}
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Configuration not found: $configPath"
}
if (-not (Test-Path -LiteralPath $logsDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $logsDirectory | Out-Null
}

$delaySeconds = 2
$openOnNextStart = [bool]$OpenDashboard
while (-not (Test-Path -LiteralPath $killSwitchPath)) {
    if ($HighFrequency) {
        $preflightLog = Join-Path $logsDirectory 'Cthulu_hft_preflight_restart.log'
        & $python -m cthulu_agent.hft_preflight *> $preflightLog
        if ($LASTEXITCODE -ne 0) {
            Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) HFT preflight blocked Agent restart; see $preflightLog"
            for ($i = 0; $i -lt $delaySeconds -and -not (Test-Path -LiteralPath $killSwitchPath); $i++) {
                Start-Sleep -Seconds 1
            }
            $delaySeconds = [Math]::Min($delaySeconds * 2, 60)
            continue
        }
    }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $stdout = Join-Path $logsDirectory "Cthulu_agent_$timestamp.out.log"
    $stderr = Join-Path $logsDirectory "Cthulu_agent_$timestamp.err.log"
    $arguments = @('-u', '-m', 'cthulu_agent', '--env', "`"$environmentPath`"", '--config', "`"$configPath`"")
    if ($openOnNextStart) {
        $arguments += '--open'
        $openOnNextStart = $false
    }
    $startedAt = [DateTime]::UtcNow
    try {
        $agent = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot `
            -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) Started dashboard/Agent PID $($agent.Id); logs: $stdout ; $stderr"
        $agent.WaitForExit()
        $agent.Refresh()
        $runtimeSeconds = ([DateTime]::UtcNow - $startedAt).TotalSeconds
        Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) Dashboard/Agent PID $($agent.Id) exited after $([Math]::Round($runtimeSeconds)) seconds with code $($agent.ExitCode)."
        if ($runtimeSeconds -ge 300) {
            $delaySeconds = 2
        } else {
            $delaySeconds = [Math]::Min($delaySeconds * 2, 60)
        }
    } catch {
        Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) Could not start dashboard/Agent: $($_.Exception.Message)"
        $delaySeconds = [Math]::Min($delaySeconds * 2, 60)
    }

    for ($i = 0; $i -lt $delaySeconds -and -not (Test-Path -LiteralPath $killSwitchPath); $i++) {
        Start-Sleep -Seconds 1
    }
}

Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) Kill switch detected; supervisor exiting without restarting Agent."
