param(
    [switch]$Preview,
    [switch]$Stop,
    [switch]$Resume,
    [string]$Mode,
    [string]$Config
)

$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$killSwitchPath = Join-Path $projectRoot '.cthulu.killswitch'
$lockPath = Join-Path $projectRoot 'cthulu.lock'
$venvPython = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot '.venv\Scripts\python.exe')
)
$modulePattern = '(?i)(?:^|\s)-m\s+cthulu(?:\s|$)'
$managedModulePattern = '(?i)(?:^|\s)-m\s+(?:cthulu|cthulu_agent)(?:\s|$)'

if ($Stop) {
    & (Join-Path $projectRoot 'cthulu_killswitch.ps1') -Preview:$Preview
    exit $LASTEXITCODE
}
if ($Resume -and $Preview) {
    throw 'Resume cannot be combined with Preview.'
}
if ((Test-Path -LiteralPath $killSwitchPath) -and -not $Resume) {
    throw "Cthulu kill switch is active at '$killSwitchPath'. Use the launcher to explicitly resume."
}

if ($Mode -and $Mode -notin @('legacy', 'agentic')) {
    throw 'Mode must be legacy or agentic.'
}
if ($Config -and $Config -notin @('config.json', 'config_multi.json')) {
    throw 'Config must be config.json or config_multi.json.'
}
if (($Mode -and -not $Config) -or (-not $Mode -and $Config)) {
    throw 'Mode and Config must be provided together.'
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Project virtualenv Python not found: $venvPython"
}

if ($Mode) {
    $configPath = Join-Path $projectRoot $Config
    $agentEnvPath = Join-Path $projectRoot 'cthulu_agent\.env.agent'
    $rootEnvPath = Join-Path $projectRoot '.env'
    $logsDirectory = Join-Path $projectRoot 'logs'

    foreach ($requiredPath in @($configPath, $agentEnvPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Required startup file not found: $requiredPath"
        }
    }

    & $venvPython -c "import pandas, numpy; print('Dependencies ready: pandas ' + pandas.__version__ + ', numpy ' + numpy.__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Project dependencies could not be imported by '$venvPython'."
    }
}

if ($Mode -and -not $Preview) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $powershell = Join-Path $PSHOME 'powershell.exe'
        if (-not (Test-Path -LiteralPath $logsDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $logsDirectory | Out-Null
        }
        $startupLog = Join-Path $logsDirectory ("Cthulu_launcher_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
        $scriptLiteral = "'" + $PSCommandPath.Replace("'", "''") + "'"
        $logLiteral = "'" + $startupLog.Replace("'", "''") + "'"
        $resumeArgument = if ($Resume) { ' -Resume' } else { '' }
        $command = "`$ErrorActionPreference = 'Stop'; Start-Transcript -LiteralPath $logLiteral -Append; try { & $scriptLiteral -Mode $Mode -Config $Config$resumeArgument } catch { Write-Error `$_; exit 1 } finally { Stop-Transcript | Out-Null }"
        $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
        $arguments = "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encodedCommand"
        try {
            $elevatedProcess = Start-Process `
                -FilePath $powershell `
                -ArgumentList $arguments `
                -WorkingDirectory $projectRoot `
                -Verb RunAs `
                -WindowStyle Hidden `
                -Wait `
                -PassThru `
                -ErrorAction Stop
        } catch {
            throw "Elevated Cthulu startup was cancelled or failed. See '$startupLog' if available. $($_.Exception.Message)"
        }
        if ($elevatedProcess.ExitCode -ne 0) {
            throw "Elevated Cthulu startup failed with exit code $($elevatedProcess.ExitCode). See '$startupLog'."
        }
        Write-Output "Elevated startup completed. Details: '$startupLog'."
        exit 0
    }
}

$processes = @(Get-CimInstance Win32_Process)
$processById = @{}
foreach ($process in $processes) {
    $processById[[int]$process.ProcessId] = $process
}

$targetIds = [System.Collections.Generic.HashSet[int]]::new()
$lockOwnerId = $null

if (Test-Path -LiteralPath $lockPath) {
    $lockContents = (Get-Content -LiteralPath $lockPath -Raw).Trim()
    $parsedPid = 0
    if (-not [int]::TryParse($lockContents, [ref]$parsedPid) -or $parsedPid -le 0) {
        throw 'Cthulu lock file is invalid; refusing to remove it automatically.'
    }

    $lockOwnerId = $parsedPid
    if ($processById.ContainsKey($lockOwnerId)) {
        $owner = $processById[$lockOwnerId]
        if ($owner.CommandLine -notmatch $modulePattern) {
            throw "Cthulu lock PID $lockOwnerId belongs to a process that is not running the Cthulu module."
        }
        [void]$targetIds.Add($lockOwnerId)

        $parentId = [int]$owner.ParentProcessId
        while ($parentId -gt 0 -and $processById.ContainsKey($parentId)) {
            $parent = $processById[$parentId]
            if ($parent.CommandLine -notmatch $managedModulePattern) {
                break
            }
            [void]$targetIds.Add($parentId)
            $parentId = [int]$parent.ParentProcessId
        }
    }
}

if ($targetIds.Count -eq 0) {
    foreach ($process in $processes) {
        if ($process.CommandLine -notmatch $managedModulePattern) {
            continue
        }

        $current = $process
        $seen = [System.Collections.Generic.HashSet[int]]::new()
        while ($current -and $seen.Add([int]$current.ProcessId)) {
            if ($current.ExecutablePath -and
                [System.IO.Path]::GetFullPath($current.ExecutablePath) -ieq $venvPython) {
                [void]$targetIds.Add([int]$process.ProcessId)
                [void]$targetIds.Add([int]$current.ProcessId)
                break
            }
            $parentId = [int]$current.ParentProcessId
            if (-not $processById.ContainsKey($parentId)) {
                break
            }
            $current = $processById[$parentId]
        }
    }
}

foreach ($process in $processes) {
    if ($process.CommandLine -notmatch '(?i)(?:^|\s)-m\s+cthulu_agent(?:\s|$)') {
        continue
    }

    $current = $process
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    while ($current -and $seen.Add([int]$current.ProcessId)) {
        if ($current.ExecutablePath -and
            [System.IO.Path]::GetFullPath($current.ExecutablePath) -ieq $venvPython) {
            [void]$targetIds.Add([int]$process.ProcessId)
            [void]$targetIds.Add([int]$current.ProcessId)
            break
        }
        $parentId = [int]$current.ParentProcessId
        if (-not $processById.ContainsKey($parentId)) {
            break
        }
        $current = $processById[$parentId]
    }
}

if ($Preview) {
    if ($targetIds.Count -eq 0) {
        Write-Output 'No previous Cthulu processes found; no changes made.'
    } else {
        Write-Output ('Would stop Cthulu process IDs: ' + (($targetIds | Sort-Object) -join ', '))
    }
    if ($Mode) {
        Write-Output "Would set execution mode to '$Mode' and start both services using '$Config'."
    }
    exit 0
}

foreach ($processId in $targetIds) {
    $currentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if (-not $currentProcess) {
        continue
    }
    if ($currentProcess.CommandLine -notmatch $managedModulePattern) {
        throw "Process $processId changed identity during cleanup; refusing to stop it."
    }
    Write-Output "Stopping previous Cthulu process $processId."
    Stop-Process -Id $processId -Force -ErrorAction Stop
}

$deadline = [DateTime]::UtcNow.AddSeconds(15)
foreach ($processId in $targetIds) {
    while (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Timed out waiting for previous Cthulu process $processId to exit."
        }
        Start-Sleep -Milliseconds 250
    }
}

if (Test-Path -LiteralPath $lockPath) {
    $remainingContents = (Get-Content -LiteralPath $lockPath -Raw).Trim()
    if ($remainingContents -eq [string]$lockOwnerId) {
        Remove-Item -LiteralPath $lockPath -Force
    } elseif ($remainingContents) {
        throw 'Cthulu lock changed during cleanup; refusing to remove a different owner lock.'
    }
}

if ($targetIds.Count -gt 0) {
    Write-Output 'Previous Cthulu process cleanup complete. Existing positions, if any, are not closed by this launcher.'
}

if ($Mode) {
    if (-not (Test-Path -LiteralPath $logsDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $logsDirectory | Out-Null
    }

    $tradingMode = if ($Config -eq 'config_multi.json') { 'multi' } else { 'single' }
    & $venvPython -c "from pathlib import Path; import sys; sys.path.insert(0, sys.argv[5]); from cthulu_agent.envfile import set_env; set_env({'CTHULU_EXECUTION_MODE': sys.argv[1], 'CTHULU_TRADING_MODE': sys.argv[2], 'CTHULU_CONFIG_NAME': sys.argv[3]}, Path(sys.argv[4]))" $Mode $tradingMode $Config $rootEnvPath $projectRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not save the selected execution mode in the project .env.'
    }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $engineOut = Join-Path $logsDirectory "Cthulu_$timestamp.out.log"
    $engineErr = Join-Path $logsDirectory "Cthulu_$timestamp.err.log"
    $supervisor = Join-Path $projectRoot 'cthulu_agent_supervisor.ps1'

    $engineArguments = @('-u', '-m', 'cthulu', '--config', "`"$configPath`"", '--skip-setup')
    if ($Config -eq 'config_multi.json') {
        $engineArguments += @('--mindset', 'ultra_aggressive')
    }
    $previousExecutionModeFile = [Environment]::GetEnvironmentVariable('CTHULU_EXECUTION_MODE_FILE', 'Process')
    [Environment]::SetEnvironmentVariable('CTHULU_EXECUTION_MODE_FILE', $rootEnvPath, 'Process')
    try {
        if ($Resume -and (Test-Path -LiteralPath $killSwitchPath)) {
            Remove-Item -LiteralPath $killSwitchPath -Force -ErrorAction Stop
        }
        $engine = Start-Process `
            -FilePath $venvPython `
            -ArgumentList $engineArguments `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $engineOut `
            -RedirectStandardError $engineErr `
            -PassThru

        $supervisorArguments = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$supervisor`"",
            '-EnvironmentFile', "`"$agentEnvPath`"", '-Config', $Config, '-OpenDashboard'
        )
        $agent = Start-Process `
            -FilePath (Join-Path $PSHOME 'powershell.exe') `
            -ArgumentList $supervisorArguments `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        [Environment]::SetEnvironmentVariable('CTHULU_EXECUTION_MODE_FILE', $previousExecutionModeFile, 'Process')
    }

    Write-Output "Started $Mode/$tradingMode mode with $Config; Cthulu PID $($engine.Id), dashboard supervisor PID $($agent.Id)."
    Write-Output "Logs: $engineOut ; $engineErr ; logs\Cthulu_agent_supervisor.log"
}
