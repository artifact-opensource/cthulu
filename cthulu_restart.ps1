$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$environmentFile = Join-Path $projectRoot '.env'
$killScript = Join-Path $projectRoot 'cthulu_killswitch.ps1'
$agentSupervisorPattern = '(?i)cthulu_agent_supervisor\.ps1'

if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) {
    throw "Project environment file not found: $environmentFile"
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $environmentFile) {
    if ($line -match '^\s*(CTHULU_EXECUTION_MODE|CTHULU_TRADING_MODE|CTHULU_CONFIG_NAME)\s*=\s*(.*?)\s*$') {
        $settings[$matches[1]] = $matches[2].Trim('"', "'")
    }
}

$mode = $settings['CTHULU_EXECUTION_MODE']
$tradingMode = $settings['CTHULU_TRADING_MODE']
$config = $settings['CTHULU_CONFIG_NAME']
if ($mode -notin @('legacy', 'agentic')) {
    throw 'Saved execution mode is invalid; select a mode in the launcher before restarting.'
}
if ($tradingMode -notin @('single', 'multi', 'hft')) {
    throw 'Saved trading mode is invalid; select Single, Multi, or HFT in the launcher before restarting.'
}
if ($config -notin @('config.json', 'config_multi.json') -or
    ($tradingMode -eq 'multi' -and $config -ne 'config_multi.json') -or
    ($tradingMode -ne 'multi' -and $config -ne 'config.json')) {
    throw 'Saved trading configuration does not match the saved trading mode.'
}

& $killScript
if ($LASTEXITCODE -ne 0) {
    throw 'Could not stop the existing Cthulu services; restart aborted.'
}

$deadline = [DateTime]::UtcNow.AddSeconds(20)
do {
    $supervisors = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -match $agentSupervisorPattern -and
                $_.CommandLine.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            }
    )
    if ($supervisors.Count -eq 0) { break }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)
if ($supervisors.Count -gt 0) {
    throw 'The dashboard supervisor did not stop; restart aborted to avoid duplicate runtimes.'
}

if ($tradingMode -eq 'hft') {
    & (Join-Path $projectRoot 'run_cthulu_hft_startup.ps1') -Mode $mode -Resume
} else {
    & (Join-Path $projectRoot 'run_cthulu_startup.ps1') -Mode $mode -Config $config -Resume
}
if ($LASTEXITCODE -ne 0) {
    throw "Cthulu restart failed with exit code $LASTEXITCODE."
}
