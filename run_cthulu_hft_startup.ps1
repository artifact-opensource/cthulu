param(
    [switch]$Preview,
    [switch]$Resume,
    [ValidateSet('legacy', 'agentic')]
    [string]$Mode = 'agentic'
)

$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$killSwitchPath = Join-Path $projectRoot '.cthulu.killswitch'
$venvPython = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot '.venv\Scripts\python.exe')
)
$configPath = Join-Path $projectRoot 'config.json'
$envPath = Join-Path $projectRoot '.env'
$logsDirectory = Join-Path $projectRoot 'logs'
$launcherLog = Join-Path $logsDirectory 'Cthulu_hft_launcher.log'
$legacyPattern = '(?i)(?:^|\s)-m\s+cthulu(?:\s|$)'
$agentPattern = '(?i)(?:^|\s)-m\s+cthulu_agent(?:\s|$)'

if ((Test-Path -LiteralPath $killSwitchPath) -and -not $Resume) {
    throw "Cthulu kill switch is active at '$killSwitchPath'. Use the launcher to explicitly resume."
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Project virtualenv Python not found: $venvPython"
}
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Configuration not found: $configPath"
}
if (-not (Test-Path -LiteralPath $logsDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $logsDirectory | Out-Null
}

& $venvPython -c "import sys; sys.path.insert(0, sys.argv[3]); from pathlib import Path; from cthulu_agent.envfile import set_env; set_env({'CTHULU_EXECUTION_MODE': sys.argv[1], 'CTHULU_TRADING_MODE': 'hft', 'CTHULU_CONFIG_NAME': 'config.json'}, Path(sys.argv[2]))" $Mode $envPath $projectRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Could not save the selected execution mode in the project .env.'
}

$pythonProcesses = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ExecutablePath -and
            [System.IO.Path]::GetFullPath($_.ExecutablePath) -ieq $venvPython
        }
)
$unverifiablePythonProcesses = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match '(?i)^pythonw?\.exe$' -and
            (-not $_.ExecutablePath -or -not $_.CommandLine)
        }
)
if ($unverifiablePythonProcesses.Count -gt 0) {
    $pids = ($unverifiablePythonProcesses | ForEach-Object { $_.ProcessId }) -join ', '
    throw "Cannot verify Python process identity for PID(s) $pids. No HFT services were started."
}

$existingLegacy = @($pythonProcesses | Where-Object { $_.CommandLine -match $legacyPattern })
$existingAgent = @($pythonProcesses | Where-Object { $_.CommandLine -match $agentPattern })

if ($existingLegacy.Count -gt 0 -or $existingAgent.Count -gt 0) {
    $running = @($existingLegacy + $existingAgent | ForEach-Object {
        "$($_.Name) PID $($_.ProcessId)"
    }) -join ', '
    throw "Existing Cthulu service process(es) detected ($running). Verify and stop them before starting HFT; no duplicate was launched."
}

if ($Preview) {
    Write-Output 'No Cthulu service processes found; preview only, no processes started.'
    exit 0
}

$overrides = [ordered]@{
    BROKER = 'mt5'
    CTHULU_ENV_FILE = $envPath
    CTHULU_EXECUTION_MODE_FILE = $envPath
    CTHULU_EXECUTION_MODE = $Mode
    AGENT_AUTONOMY = 'autonomous'
    AGENT_SYMBOLS = '*'
    AGENT_SYMBOL_MAX_SPREAD_PCT = '0.0025'
    AGENT_SYMBOL_SCAN_LIMIT = '25'
    AGENT_TIMEFRAME = 'M1'
    AGENT_PROFILE = 'hft'
    AGENT_OBJECTIVE = 'Build risk-adjusted growth through confirmed M1 momentum; favor frequent, strictly protected opportunities and scale only validated winners.'
    AGENT_STRATEGY_PROFILE = 'scalping'
    AGENT_ENTRY_MODE = 'adaptive'
    AGENT_CYCLE_SECONDS = '5'
    AGENT_MANAGE_INTERVAL = '20'
    AGENT_IDLE_THINK_MINUTES = '1'
    AGENT_MAX_THINKS_PER_HOUR = '120'
    AGENT_PLAN_EVERY = '8'
    AGENT_MANAGE_FOREIGN = 'true'
    AGENT_EMERGENCY_SL = 'true'
    RISK_MAX_SPREAD_ATR = '0.25'
    LIVE_RUN_CONFIRM = '1'
}

$previousEnvironment = @{}
foreach ($key in $overrides.Keys) {
    $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, $overrides[$key], 'Process')
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$legacyStdout = Join-Path $logsDirectory "Cthulu_hft_$timestamp.log"
$legacyStderr = Join-Path $logsDirectory "Cthulu_hft_$timestamp.error.log"
$agentSupervisor = Join-Path $projectRoot 'cthulu_agent_supervisor.ps1'

try {
    & $venvPython -m cthulu_agent.hft_preflight
    if ($LASTEXITCODE -ne 0) {
        throw 'HFT preflight failed; no trading services were started.'
    }

    if ($Resume -and (Test-Path -LiteralPath $killSwitchPath)) {
        Remove-Item -LiteralPath $killSwitchPath -Force -ErrorAction Stop
    }

    $legacy = Start-Process `
        -FilePath $venvPython `
        -ArgumentList @(
            '-u',
            '-m',
            'cthulu',
            '--config',
            "`"$configPath`"",
            '--skip-setup',
            '--mindset',
            'high_frequency'
        ) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $legacyStdout `
        -RedirectStandardError $legacyStderr `
        -PassThru

    $agent = Start-Process `
        -FilePath (Join-Path $PSHOME 'powershell.exe') `
        -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$agentSupervisor`"",
            '-EnvironmentFile', "`"$(Join-Path $projectRoot 'cthulu_agent\.env.agent')`"",
            '-Config', 'config.json', '-OpenDashboard', '-HighFrequency'
        ) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
} finally {
    foreach ($key in $overrides.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], 'Process')
    }
}

Start-Sleep -Seconds 3
$legacyAlive = Get-Process -Id $legacy.Id -ErrorAction SilentlyContinue
$agentAlive = Get-Process -Id $agent.Id -ErrorAction SilentlyContinue
if (-not $legacyAlive -or -not $agentAlive) {
    $message = "HFT startup incomplete. Legacy PID $($legacy.Id) alive=$([bool]$legacyAlive); dashboard supervisor PID $($agent.Id) alive=$([bool]$agentAlive). Logs: $legacyStdout ; $legacyStderr ; logs\Cthulu_agent_supervisor.log"
    Add-Content -LiteralPath $launcherLog -Value "$(Get-Date -Format o) $message"
    throw $message
}

$message = "Started $Mode HFT (Legacy PID $($legacy.Id), dashboard supervisor PID $($agent.Id)); both use config.json, MT5, M1, 1% max entry risk, 5% aggregate risk, and 10 combined active orders. Logs: $legacyStdout ; $legacyStderr ; logs\Cthulu_agent_supervisor.log"
Add-Content -LiteralPath $launcherLog -Value "$(Get-Date -Format o) $message"
Write-Output $message
