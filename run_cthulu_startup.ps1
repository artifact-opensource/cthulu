param(
    [switch]$Preview
)

$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$lockPath = Join-Path $projectRoot 'cthulu.lock'
$venvPython = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot '.venv\Scripts\python.exe')
)
$modulePattern = '(?i)(?:^|\s)-m\s+cthulu(?:\s|$)'

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Project virtualenv Python not found: $venvPython"
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
            if ($parent.CommandLine -notmatch $modulePattern) {
                break
            }
            [void]$targetIds.Add($parentId)
            $parentId = [int]$parent.ParentProcessId
        }
    }
}

if ($targetIds.Count -eq 0) {
    foreach ($process in $processes) {
        if ($process.CommandLine -notmatch $modulePattern) {
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

if ($Preview) {
    if ($targetIds.Count -eq 0) {
        Write-Output 'No previous Cthulu processes found; no changes made.'
    } else {
        Write-Output ('Would stop Cthulu process IDs: ' + (($targetIds | Sort-Object) -join ', '))
    }
    exit 0
}

foreach ($processId in $targetIds) {
    $currentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if (-not $currentProcess) {
        continue
    }
    if ($currentProcess.CommandLine -notmatch $modulePattern) {
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
