param(
    [switch]$AutoApply,
    [switch]$NoAI,
    [string[]]$Symbols = @("GOLDm#","BTCUSD#"),
    [string[]]$Timeframes = @("M15","H1"),
    [int]$Days = 30
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir '..')
Set-Location $RepoRoot

# Try to activate a virtualenv if available (venv312 or .venv)
$venv_candidates = @('venv312', '.venv')
foreach ($v in $venv_candidates) {
    $act = Join-Path $RepoRoot (Join-Path $v 'Scripts\Activate.ps1')
    if (Test-Path $act) {
        Write-Output "Activating virtualenv: $v"
        & $act
        break
    }
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$OutDir = Join-Path $RepoRoot ("backtesting\reports\auto_tune_runs\$ts")
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$Log = Join-Path $OutDir 'run.log'

$symbolsArg = $Symbols -join ' '
$timeframesArg = $Timeframes -join ' '
$autoFlag = ''
$noAiFlag = ''
if ($AutoApply) { $autoFlag = '--auto-apply' }
if ($NoAI) { $noAiFlag = '--no-ai' }

Write-Output "Running entry with redirected output to $Log"

$python = 'python'
$argsList = @('-m', 'cthulu.backtesting.scripts.auto_tune_runner', '--symbols') + $Symbols + @('--timeframes') + $Timeframes + @('--days', $Days)
if ($AutoApply) { $argsList += '--auto-apply' }
if ($NoAI) { $argsList += '--no-ai' }

# Choose a python command: prefer 'py -3' launcher on Windows, otherwise 'python'
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $pythonCmd = 'py'
    $pythonArgsPrefix = @('-3')
} else {
    $pythonCmd = 'python'
    $pythonArgsPrefix = @()
}

# Run python command; temporarily set ErrorActionPreference to avoid native command output being treated as termination
$prevErr = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $pythonCmd @pythonArgsPrefix @argsList 2>&1 | Tee-Object -FilePath $Log
$ErrorActionPreference = $prevErr
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Python exited with code $LASTEXITCODE. Check $Log for details."
}

# Read final JSON line from log safely
$lastJsonLine = $null
try {
    $lastJsonLine = (Get-Content $Log | Where-Object { $_ -match '^{\s*"smoke_out_dir' } | Select-Object -Last 1)
} catch {
    Write-Warning "Failed to read log file: $_"
}

if ($lastJsonLine) {
    try {
        $result = $lastJsonLine | ConvertFrom-Json
        Write-Output "Run completed. Summary JSON: $($result.summary_json)"
        if (Test-Path $result.summary_json) {
            Write-Output "Opening summary in notepad..."
            notepad $result.summary_json
        }
    } catch {
        Write-Warning "Failed to parse result JSON: $_"
    }
} else {
    Write-Warning "No final JSON line found in log. Check $Log for details."
}

Write-Output "Full run finished. Logs: $Log"
