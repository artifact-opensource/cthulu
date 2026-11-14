param(
    [switch]$Preview
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$killSwitchPath = Join-Path $projectRoot '.cthulu.killswitch'
$lockPath = Join-Path $projectRoot 'cthulu.lock'
$venvPython = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '.venv\Scripts\python.exe'))
$legacyPattern = '(?i)(?:^|\s)-m\s+cthulu(?:\s|$)'
$agentPattern = '(?i)(?:^|\s)-m\s+cthulu_agent(?:\s|$)'

function Get-ProcessOwner([object]$Process) {
    $owner = Invoke-CimMethod -InputObject $Process -MethodName GetOwner -ErrorAction SilentlyContinue
    if ($owner -and $owner.ReturnValue -eq 0) {
        return "$($owner.Domain)\$($owner.User)"
    }
    return ''
}

function Get-CthuluTargets {
    $processes = @(Get-CimInstance Win32_Process)
    $byId = @{}
    foreach ($process in $processes) {
        $byId[[int]$process.ProcessId] = $process
    }

    $targetIds = [System.Collections.Generic.HashSet[int]]::new()
    $lockOwnerId = $null
    if (Test-Path -LiteralPath $lockPath) {
        $rawLock = (Get-Content -LiteralPath $lockPath -Raw).Trim()
        $parsedPid = 0
        if (-not [int]::TryParse($rawLock, [ref]$parsedPid) -or $parsedPid -le 0) {
            throw 'Cthulu lock file is invalid; refusing broad process termination.'
        }
        $lockOwnerId = $parsedPid
        $script:lockOwnerId = $parsedPid
        if ($byId.ContainsKey($lockOwnerId)) {
            $lockProcess = $byId[$lockOwnerId]
            if ($lockProcess.Name -notmatch '(?i)^pythonw?\.exe$' -and
                $lockProcess.CommandLine -notmatch $legacyPattern) {
                throw "Cthulu lock PID $lockOwnerId is not a verifiable Cthulu process."
            }
            [void]$targetIds.Add($lockOwnerId)

            $root = $lockProcess
            while ($root.ParentProcessId -gt 0 -and $byId.ContainsKey([int]$root.ParentProcessId)) {
                $parent = $byId[[int]$root.ParentProcessId]
                if ($parent.Name -notmatch '(?i)^pythonw?\.exe$') {
                    break
                }
                [void]$targetIds.Add([int]$parent.ProcessId)
                $root = $parent
            }

            $ownerName = Get-ProcessOwner $lockProcess
            if ($root.ParentProcessId -gt 0) {
                $siblings = @($processes | Where-Object {
                    $_.Name -match '(?i)^pythonw?\.exe$' -and
                    [int]$_.ParentProcessId -eq [int]$root.ParentProcessId -and
                    $_.ProcessId -ne $root.ProcessId
                })
                foreach ($sibling in $siblings) {
                    $sameOwner = $ownerName -and (Get-ProcessOwner $sibling) -eq $ownerName
                    $sameLaunch = $sibling.CreationDate -and $root.CreationDate -and
                        [Math]::Abs((([datetime]$sibling.CreationDate) - ([datetime]$root.CreationDate)).TotalSeconds) -le 5
                    if ($sameOwner -and $sameLaunch) {
                        [void]$targetIds.Add([int]$sibling.ProcessId)
                    }
                }
            }
        }
    }

    foreach ($process in $processes) {
        if ($process.Name -match '(?i)^pythonw?\.exe$' -and $process.ExecutablePath -and
            [System.IO.Path]::GetFullPath($process.ExecutablePath) -ieq $venvPython -and
            $process.CommandLine -and
            ($process.CommandLine -match $legacyPattern -or $process.CommandLine -match $agentPattern) -and
            $process.CommandLine.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            [void]$targetIds.Add([int]$process.ProcessId)
        }
        if ($process.Name -match '(?i)^Cthulu.*\.exe$' -and $process.ExecutablePath -and
            [System.IO.Path]::GetFullPath($process.ExecutablePath).StartsWith(
                $projectRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            [void]$targetIds.Add([int]$process.ProcessId)
        }
    }

    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $processes) {
            if ($process.Name -match '(?i)^pythonw?\.exe$' -and
                $targetIds.Contains([int]$process.ParentProcessId) -and
                $targetIds.Add([int]$process.ProcessId)) {
                $changed = $true
            }
        }
    }

    return @($targetIds | ForEach-Object { $byId[$_] })
}

if (-not $Preview) {
    Set-Content -LiteralPath $killSwitchPath -Value "Trading disabled at $(Get-Date -Format o)" -Encoding Ascii
}

$targets = @(Get-CthuluTargets)
if ($Preview) {
    if ($targets.Count -eq 0) {
        Write-Output 'No Cthulu processes identified; no changes made.'
    } else {
        $targets | Select-Object ProcessId,ParentProcessId,Name | Format-Table -AutoSize
    }
    exit 0
}

$targetIds = [System.Collections.Generic.HashSet[int]]::new()
foreach ($target in $targets) {
    [void]$targetIds.Add([int]$target.ProcessId)
}

foreach ($target in @($targets | Sort-Object { $_.ProcessId })) {
    $processId = [int]$target.ProcessId
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if (-not $current) {
        continue
    }
    if (-not $targetIds.Contains($processId)) {
        continue
    }
    Write-Output "Stopping Cthulu service process $processId ($($target.Name))."
    Stop-Process -Id $processId -Force -ErrorAction Stop
}

$deadline = [DateTime]::UtcNow.AddSeconds(15)
foreach ($processId in $targetIds) {
    while (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Timed out waiting for Cthulu process $processId to exit. Kill switch remains active."
        }
        Start-Sleep -Milliseconds 250
    }
}

for ($attempt = 0; $attempt -lt 10; $attempt++) {
    Start-Sleep -Seconds 1
    $restarted = @(Get-CthuluTargets)
    if ($restarted.Count -eq 0) {
        if (Test-Path -LiteralPath $lockPath) {
            $remainingLock = (Get-Content -LiteralPath $lockPath -Raw).Trim()
            if ($remainingLock -eq [string]$lockOwnerId) {
                Remove-Item -LiteralPath $lockPath -Force
            }
        }
        Write-Output "Cthulu and Cthulu Agent are stopped. Persistent kill switch active: $killSwitchPath"
        exit 0
    }
    foreach ($process in $restarted) {
        if (-not $targetIds.Contains([int]$process.ProcessId)) {
            [void]$targetIds.Add([int]$process.ProcessId)
            Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction Stop
        }
    }
}
throw "Cthulu processes kept restarting. The persistent kill switch is active at '$killSwitchPath', but one or more external restart mechanisms remain."
