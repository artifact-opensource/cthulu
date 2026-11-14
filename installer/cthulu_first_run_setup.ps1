$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$script:ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:SetupProcess = $null
$script:SetupLogPath = $null
$script:Settings = $null
$script:OutputQueue = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()

function New-FormLabel {
    param(
        [string]$Text,
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height = 24
    )

    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point($X, $Y)
    $label.Size = New-Object System.Drawing.Size($Width, $Height)
    return $label
}

function New-FormTextBox {
    param(
        [int]$X,
        [int]$Y,
        [int]$Width,
        [switch]$Secret
    )

    $textBox = New-Object System.Windows.Forms.TextBox
    $textBox.Location = New-Object System.Drawing.Point($X, $Y)
    $textBox.Size = New-Object System.Drawing.Size($Width, 25)
    if ($Secret) {
        $textBox.UseSystemPasswordChar = $true
    }
    return $textBox
}

function Set-JsonProperty {
    param(
        [object]$Target,
        [string]$Name,
        [object]$Value
    )

    if ($Target.PSObject.Properties[$Name]) {
        $Target.$Name = $Value
    } else {
        $Target | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    }
}

function Ensure-JsonObject {
    param(
        [object]$Target,
        [string]$Name
    )

    $property = $Target.PSObject.Properties[$Name]
    if (-not $property -or $null -eq $property.Value) {
        Set-JsonProperty -Target $Target -Name $Name -Value ([pscustomobject]@{})
    }
    return $Target.$Name
}

function ConvertTo-EnvValue {
    param([string]$Value)

    if ($null -eq $Value) {
        return ''
    }
    if ($Value -match '[\s#''"\\]') {
        return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
    }
    return $Value
}

function Write-EnvironmentFile {
    param(
        [string]$Path,
        [System.Collections.IDictionary]$Updates
    )

    $lines = @()
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $lines = @(Get-Content -LiteralPath $Path -ErrorAction Stop)
    }

    $pending = [ordered]@{}
    foreach ($key in $Updates.Keys) {
        $pending[$key] = $Updates[$key]
    }

    $output = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in $lines) {
        $match = [regex]::Match($line, '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=')
        if ($match.Success -and $pending.Contains($match.Groups[1].Value)) {
            $key = $match.Groups[1].Value
            $value = $pending[$key]
            if ($null -ne $value) {
                $output.Add("$key=$(ConvertTo-EnvValue ([string]$value))")
            }
            $pending.Remove($key)
        } else {
            $output.Add($line)
        }
    }

    foreach ($key in $pending.Keys) {
        if ($null -ne $pending[$key]) {
            $output.Add("$key=$(ConvertTo-EnvValue ([string]$pending[$key]))")
        }
    }

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $temporaryPath = Join-Path $parent ('.' + [System.IO.Path]::GetFileName($Path) + '.' + [guid]::NewGuid().ToString('N') + '.tmp')
    $contents = ($output -join [Environment]::NewLine).TrimEnd() + [Environment]::NewLine
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($temporaryPath, $contents, $encoding)
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            [System.IO.File]::Replace($temporaryPath, $Path, $null)
        } else {
            Move-Item -LiteralPath $temporaryPath -Destination $Path
        }
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Protect-SecretFile {
    param([string]$Path)

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $systemSid = New-Object System.Security.Principal.SecurityIdentifier(
        [System.Security.Principal.WellKnownSidType]::LocalSystemSid,
        $null
    )
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleSpecific($rule)
    }
    $acl.SetOwner($identity.User)
    $userRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity.User,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $systemRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $systemSid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.SetAccessRule($userRule)
    $acl.AddAccessRule($systemRule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Write-JsonFile {
    param(
        [string]$Path,
        [object]$Value
    )

    $json = $Value | ConvertTo-Json -Depth 100
    $temporaryPath = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($temporaryPath, $json + [Environment]::NewLine, $encoding)
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            [System.IO.File]::Replace($temporaryPath, $Path, $null)
        } else {
            Move-Item -LiteralPath $temporaryPath -Destination $Path
        }
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Get-SetupValues {
    $login = 0
    if (-not [int]::TryParse($script:LoginTextBox.Text.Trim(), [ref]$login) -or $login -le 0) {
        throw 'Enter a valid positive MT5 account number.'
    }

    $password = $script:PasswordTextBox.Text
    if ([string]::IsNullOrWhiteSpace($password) -or $password.Contains("`n") -or $password.Contains("`r")) {
        throw 'Enter an MT5 password without line breaks.'
    }

    $server = $script:ServerTextBox.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($server) -or $server.Contains("`n") -or $server.Contains("`r")) {
        throw 'Enter the MT5 broker server name.'
    }

    $terminalPath = $script:TerminalPathTextBox.Text.Trim()
    if ($terminalPath -and -not (Test-Path -LiteralPath $terminalPath -PathType Leaf)) {
        throw 'The MT5 terminal path does not point to an existing file.'
    }

    $culture = [System.Globalization.CultureInfo]::InvariantCulture
    $riskPerTrade = 0.0
    $dailyLoss = 0.0
    $drawdown = 0.0
    $maxPositions = 0
    if (-not [double]::TryParse($script:RiskPerTradeTextBox.Text.Trim(), [System.Globalization.NumberStyles]::Float, $culture, [ref]$riskPerTrade) -or $riskPerTrade -lt 0.05 -or $riskPerTrade -gt 5) {
        throw 'Risk per trade must be between 0.05% and 5%.'
    }
    if (-not [double]::TryParse($script:DailyLossTextBox.Text.Trim(), [System.Globalization.NumberStyles]::Float, $culture, [ref]$dailyLoss) -or $dailyLoss -lt 0 -or $dailyLoss -gt 20) {
        throw 'Daily loss stop must be between 0% and 20%.'
    }
    if (-not [double]::TryParse($script:DrawdownTextBox.Text.Trim(), [System.Globalization.NumberStyles]::Float, $culture, [ref]$drawdown) -or $drawdown -lt 0 -or $drawdown -gt 60) {
        throw 'Drawdown halt must be between 0% and 60%.'
    }
    if (-not [int]::TryParse($script:MaxPositionsTextBox.Text.Trim(), [ref]$maxPositions) -or $maxPositions -lt 1 -or $maxPositions -gt 10) {
        throw 'Maximum positions must be a whole number between 1 and 10.'
    }

    $llm = $null
    if ($script:ConfigureLlmCheckBox.Checked) {
        $accountId = $script:CloudflareAccountIdTextBox.Text.Trim()
        if ($accountId -notmatch '^[A-Za-z0-9_-]{1,128}$') {
            throw 'Enter a valid Cloudflare account ID.'
        }

        $gatewayId = $script:CloudflareGatewayIdTextBox.Text.Trim()
        if ($gatewayId -notmatch '^[A-Za-z0-9_-]{1,128}$') {
            throw 'Enter a valid Cloudflare AI Gateway ID.'
        }

        $baseUrl = $script:LlmBaseUrlTextBox.Text.Trim()
        if ($baseUrl) {
            $uri = $null
            if (-not [uri]::TryCreate($baseUrl, [System.UriKind]::Absolute, [ref]$uri) -or
                $uri.Scheme -notin @('http', 'https') -or
                [string]::IsNullOrWhiteSpace($uri.Host) -or
                $uri.UserInfo -or
                $uri.Query -or
                $uri.Fragment) {
                throw 'Enter a valid Cloudflare-compatible base URL (HTTP or HTTPS, without a query or fragment).'
            }
        }

        $apiKey = $script:LlmApiKeyTextBox.Text
        $model = $script:LlmModelTextBox.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Contains("`n") -or $apiKey.Contains("`r")) {
            throw 'Enter a Cloudflare API token without line breaks.'
        }
        if ([string]::IsNullOrWhiteSpace($model) -or $model.Contains("`n") -or $model.Contains("`r")) {
            throw 'Enter a model name without line breaks.'
        }
        $llm = [pscustomobject]@{
            AccountId = $accountId
            GatewayId = $gatewayId
            BaseUrl = if ($baseUrl) { $baseUrl } else { $null }
            ApiKey = $apiKey
            Model = $model
        }
    }

    return [pscustomobject]@{
        Login = $login
        Password = $password
        Server = $server
        TerminalPath = $terminalPath
        RiskPerTrade = $riskPerTrade
        DailyLoss = $dailyLoss
        Drawdown = $drawdown
        MaxPositions = $maxPositions
        Llm = $llm
    }
}

function Read-OrCreateLegacyConfig {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop)
    }

    $templatePath = Join-Path $script:ProjectRoot 'config.example.json'
    if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
        throw "The legacy configuration template is missing: $templatePath"
    }
    return (Get-Content -LiteralPath $templatePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop)
}

function Update-LegacyConfig {
    param(
        [object]$Config,
        [object]$Settings
    )

    $mt5 = Ensure-JsonObject -Target $Config -Name 'mt5'
    Set-JsonProperty -Target $mt5 -Name 'login' -Value '${MT5_LOGIN}'
    Set-JsonProperty -Target $mt5 -Name 'password' -Value '${MT5_PASSWORD}'
    Set-JsonProperty -Target $mt5 -Name 'server' -Value '${MT5_SERVER}'
    Set-JsonProperty -Target $mt5 -Name 'path' -Value $(if ($Settings.TerminalPath) { $Settings.TerminalPath } else { $null })

    $risk = Ensure-JsonObject -Target $Config -Name 'risk'
    $perTradeFraction = $Settings.RiskPerTrade / 100.0
    $dailyLossFraction = $Settings.DailyLoss / 100.0
    Set-JsonProperty -Target $risk -Name 'max_position_size_pct' -Value $perTradeFraction
    Set-JsonProperty -Target $risk -Name 'position_size_pct' -Value $Settings.RiskPerTrade
    Set-JsonProperty -Target $risk -Name 'max_daily_loss_pct' -Value $dailyLossFraction
    Set-JsonProperty -Target $risk -Name 'max_daily_loss' -Value 0.0
    Set-JsonProperty -Target $risk -Name 'drawdown_halt_percent' -Value $Settings.Drawdown
    Set-JsonProperty -Target $risk -Name 'max_total_positions' -Value $Settings.MaxPositions
    Set-JsonProperty -Target $risk -Name 'max_positions_per_symbol' -Value $Settings.MaxPositions
}

function Save-SetupConfiguration {
    param([object]$Settings)

    $singlePath = Join-Path $script:ProjectRoot 'config.json'
    $multiPath = Join-Path $script:ProjectRoot 'config_multi.json'
    $singleConfig = Read-OrCreateLegacyConfig -Path $singlePath
    $multiConfig = Read-OrCreateLegacyConfig -Path $multiPath
    Update-LegacyConfig -Config $singleConfig -Settings $Settings
    Update-LegacyConfig -Config $multiConfig -Settings $Settings

    $culture = [System.Globalization.CultureInfo]::InvariantCulture
    $riskFraction = ($Settings.RiskPerTrade / 100.0).ToString('0.################', $culture)
    $dailyFraction = ($Settings.DailyLoss / 100.0).ToString('0.################', $culture)
    $riskPerTrade = $Settings.RiskPerTrade.ToString('0.################', $culture)
    $dailyLoss = $Settings.DailyLoss.ToString('0.################', $culture)
    $drawdown = $Settings.Drawdown.ToString('0.################', $culture)
    $maxPositions = [string]$Settings.MaxPositions
    $openRisk = [Math]::Min(20.0, $Settings.RiskPerTrade * $Settings.MaxPositions).ToString('0.################', $culture)

    $rootEnvPath = Join-Path $script:ProjectRoot '.env'
    $agentEnvPath = Join-Path $script:ProjectRoot 'cthulu_agent\.env.agent'
    $rootUpdates = [ordered]@{
        MT5_LOGIN = [string]$Settings.Login
        MT5_PASSWORD = $Settings.Password
        MT5_SERVER = $Settings.Server
        MT5_PATH = if ($Settings.TerminalPath) { $Settings.TerminalPath } else { $null }
        CTHULU_LEGACY_MAX_POSITION_SIZE_PCT = $riskFraction
        CTHULU_LEGACY_MAX_DAILY_LOSS_PCT = $dailyFraction
        CTHULU_LEGACY_DRAWDOWN_HALT_PERCENT = $drawdown
        CTHULU_LEGACY_MAX_POSITIONS_PER_SYMBOL = $maxPositions
        CTHULU_LEGACY_MAX_TOTAL_POSITIONS = $maxPositions
    }
    $agentUpdates = [ordered]@{
        BROKER = 'mt5'
        MT5_LOGIN = [string]$Settings.Login
        MT5_PASSWORD = $Settings.Password
        MT5_SERVER = $Settings.Server
        MT5_PATH = if ($Settings.TerminalPath) { $Settings.TerminalPath } else { $null }
        LIVE_RUN_CONFIRM = '1'
        RISK_MAX_PER_TRADE_PCT = $riskPerTrade
        RISK_DAILY_LOSS_PCT = $dailyLoss
        RISK_DRAWDOWN_HALT_PCT = $drawdown
        RISK_MAX_POSITIONS = $maxPositions
        RISK_MAX_POSITIONS_PER_SYMBOL = $maxPositions
        RISK_MAX_PENDING = $maxPositions
        RISK_MAX_ACTIVE_ORDERS = $maxPositions
        RISK_MAX_OPEN_RISK_PCT = $openRisk
    }
    $agentUpdates['LLM_PROVIDER'] = if ($Settings.Llm) { 'cloudflare' } else { $null }
    $agentUpdates['CLOUDFLARE_ACCOUNT_ID'] = if ($Settings.Llm) { $Settings.Llm.AccountId } else { $null }
    $agentUpdates['CLOUDFLARE_AI_GATEWAY_ID'] = if ($Settings.Llm) { $Settings.Llm.GatewayId } else { $null }
    $agentUpdates['CLOUDFLARE_BASE_URL'] = if ($Settings.Llm) { $Settings.Llm.BaseUrl } else { $null }
    $agentUpdates['CLOUDFLARE_API_KEY'] = if ($Settings.Llm) { $Settings.Llm.ApiKey } else { $null }
    $agentUpdates['CLOUDFLARE_MODEL'] = if ($Settings.Llm) { $Settings.Llm.Model } else { $null }
    $agentUpdates['OPENAI_BASE_URL'] = $null
    $agentUpdates['OPENAI_API_KEY'] = $null
    $agentUpdates['OPENAI_MODEL'] = $null

    Write-EnvironmentFile -Path $rootEnvPath -Updates $rootUpdates
    Write-EnvironmentFile -Path $agentEnvPath -Updates $agentUpdates
    Protect-SecretFile -Path $rootEnvPath
    Protect-SecretFile -Path $agentEnvPath
    Write-JsonFile -Path $singlePath -Value $singleConfig
    Write-JsonFile -Path $multiPath -Value $multiConfig
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Cthulu first-run setup'
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.ClientSize = New-Object System.Drawing.Size(800, 735)
$form.Font = New-Object System.Drawing.Font('Segoe UI', 9)

$title = New-FormLabel -Text 'Set up Cthulu' -X 16 -Y 12 -Width 400 -Height 30
$title.Font = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($title)
$subtitle = New-FormLabel -Text 'Configure MT5, risk limits, and the optional Agent LLM overlay. Setup installs dependencies but does not start Cthulu.' -X 18 -Y 43 -Width 760 -Height 24
$form.Controls.Add($subtitle)

$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Location = New-Object System.Drawing.Point(12, 72)
$tabs.Size = New-Object System.Drawing.Size(776, 320)
$form.Controls.Add($tabs)

$mt5Tab = New-Object System.Windows.Forms.TabPage
$mt5Tab.Text = 'MT5 account'
$tabs.TabPages.Add($mt5Tab)
$mt5Info = New-FormLabel -Text 'Entering an MT5 account enables its real account connection when you later choose Legacy, Agentic, or HFT. Use a demo account first. No trading mode starts automatically.' -X 14 -Y 12 -Width 730 -Height 48
$mt5Tab.Controls.Add($mt5Info)
$mt5Tab.Controls.Add((New-FormLabel -Text 'Account number *' -X 16 -Y 73 -Width 250))
$script:LoginTextBox = New-FormTextBox -X 16 -Y 96 -Width 330
$mt5Tab.Controls.Add($script:LoginTextBox)
$mt5Tab.Controls.Add((New-FormLabel -Text 'Password *' -X 16 -Y 130 -Width 250))
$script:PasswordTextBox = New-FormTextBox -X 16 -Y 153 -Width 330 -Secret
$mt5Tab.Controls.Add($script:PasswordTextBox)
$mt5Tab.Controls.Add((New-FormLabel -Text 'Broker server *' -X 16 -Y 187 -Width 250))
$script:ServerTextBox = New-FormTextBox -X 16 -Y 210 -Width 330
$mt5Tab.Controls.Add($script:ServerTextBox)
$mt5Tab.Controls.Add((New-FormLabel -Text 'MT5 terminal path (optional)' -X 16 -Y 244 -Width 330))
$script:TerminalPathTextBox = New-FormTextBox -X 16 -Y 267 -Width 610
$mt5Tab.Controls.Add($script:TerminalPathTextBox)
$browseButton = New-Object System.Windows.Forms.Button
$browseButton.Text = 'Browse...'
$browseButton.Location = New-Object System.Drawing.Point(635, 266)
$browseButton.Size = New-Object System.Drawing.Size(100, 27)
$browseButton.Add_Click({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Select the MetaTrader 5 terminal'
    $dialog.Filter = 'MetaTrader terminal (terminal64.exe)|terminal64.exe|Executables (*.exe)|*.exe'
    if ($dialog.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {
        $script:TerminalPathTextBox.Text = $dialog.FileName
    }
    $dialog.Dispose()
})
$mt5Tab.Controls.Add($browseButton)

$riskTab = New-Object System.Windows.Forms.TabPage
$riskTab.Text = 'Risk limits'
$tabs.TabPages.Add($riskTab)
$riskInfo = New-FormLabel -Text 'These limits are saved for Legacy and Agentic. Mode presets cannot raise the Legacy limits selected here.' -X 14 -Y 14 -Width 730 -Height 30
$riskTab.Controls.Add($riskInfo)
$riskTab.Controls.Add((New-FormLabel -Text 'Maximum risk per trade (%)' -X 16 -Y 62 -Width 300))
$script:RiskPerTradeTextBox = New-FormTextBox -X 16 -Y 86 -Width 230
$script:RiskPerTradeTextBox.Text = '0.5'
$riskTab.Controls.Add($script:RiskPerTradeTextBox)
$riskTab.Controls.Add((New-FormLabel -Text 'Daily loss stop (%)' -X 16 -Y 122 -Width 300))
$script:DailyLossTextBox = New-FormTextBox -X 16 -Y 146 -Width 230
$script:DailyLossTextBox.Text = '2'
$riskTab.Controls.Add($script:DailyLossTextBox)
$riskTab.Controls.Add((New-FormLabel -Text 'Drawdown halt (%)' -X 16 -Y 182 -Width 300))
$script:DrawdownTextBox = New-FormTextBox -X 16 -Y 206 -Width 230
$script:DrawdownTextBox.Text = '10'
$riskTab.Controls.Add($script:DrawdownTextBox)
$riskTab.Controls.Add((New-FormLabel -Text 'Maximum simultaneous positions (1-10)' -X 16 -Y 242 -Width 350))
$script:MaxPositionsTextBox = New-FormTextBox -X 16 -Y 266 -Width 230
$script:MaxPositionsTextBox.Text = '3'
$riskTab.Controls.Add($script:MaxPositionsTextBox)
$riskNote = New-FormLabel -Text 'Daily loss and drawdown values of 0 disable those stops. Risk values are percentages of account equity.' -X 290 -Y 89 -Width 430 -Height 54
$riskTab.Controls.Add($riskNote)

$agentTab = New-Object System.Windows.Forms.TabPage
$agentTab.Text = 'Agent LLM'
$tabs.TabPages.Add($agentTab)
$script:ConfigureLlmCheckBox = New-Object System.Windows.Forms.CheckBox
$script:ConfigureLlmCheckBox.Text = 'Enable Cloudflare AI Gateway Agent LLM'
$script:ConfigureLlmCheckBox.Location = New-Object System.Drawing.Point(16, 16)
$script:ConfigureLlmCheckBox.Size = New-Object System.Drawing.Size(600, 24)
$agentTab.Controls.Add($script:ConfigureLlmCheckBox)
$agentInfo = New-FormLabel -Text 'Optional. Enter your Cloudflare account and AI Gateway IDs plus API token. Leave Base URL blank to use the account default. Settings are stored in .env.agent.' -X 16 -Y 44 -Width 730 -Height 42
$agentTab.Controls.Add($agentInfo)
$agentTab.Controls.Add((New-FormLabel -Text 'Cloudflare account ID *' -X 16 -Y 86 -Width 330))
$script:CloudflareAccountIdTextBox = New-FormTextBox -X 16 -Y 108 -Width 330
$agentTab.Controls.Add($script:CloudflareAccountIdTextBox)
$agentTab.Controls.Add((New-FormLabel -Text 'AI Gateway ID *' -X 390 -Y 86 -Width 330))
$script:CloudflareGatewayIdTextBox = New-FormTextBox -X 390 -Y 108 -Width 330
$agentTab.Controls.Add($script:CloudflareGatewayIdTextBox)
$agentTab.Controls.Add((New-FormLabel -Text 'Cloudflare API token *' -X 16 -Y 142 -Width 330))
$script:LlmApiKeyTextBox = New-FormTextBox -X 16 -Y 164 -Width 700 -Secret
$agentTab.Controls.Add($script:LlmApiKeyTextBox)
$agentTab.Controls.Add((New-FormLabel -Text 'Base URL override (optional)' -X 16 -Y 198 -Width 700))
$script:LlmBaseUrlTextBox = New-FormTextBox -X 16 -Y 220 -Width 700
$agentTab.Controls.Add($script:LlmBaseUrlTextBox)
$agentTab.Controls.Add((New-FormLabel -Text 'Model *' -X 16 -Y 254 -Width 700))
$script:LlmModelTextBox = New-FormTextBox -X 16 -Y 276 -Width 700
$script:LlmModelTextBox.Text = '@cf/qwen/qwen3-30b-a3b-fp8'
$agentTab.Controls.Add($script:LlmModelTextBox)

$script:ConfigureLlmCheckBox.Add_CheckedChanged({
    $enabled = $script:ConfigureLlmCheckBox.Checked
    $script:CloudflareAccountIdTextBox.Enabled = $enabled
    $script:CloudflareGatewayIdTextBox.Enabled = $enabled
    $script:LlmBaseUrlTextBox.Enabled = $enabled
    $script:LlmApiKeyTextBox.Enabled = $enabled
    $script:LlmModelTextBox.Enabled = $enabled
})
$script:CloudflareAccountIdTextBox.Enabled = $false
$script:CloudflareGatewayIdTextBox.Enabled = $false
$script:LlmBaseUrlTextBox.Enabled = $false
$script:LlmApiKeyTextBox.Enabled = $false
$script:LlmModelTextBox.Enabled = $false

$outputLabel = New-FormLabel -Text 'Setup output' -X 14 -Y 399 -Width 200 -Height 22
$form.Controls.Add($outputLabel)
$script:OutputTextBox = New-Object System.Windows.Forms.TextBox
$script:OutputTextBox.Location = New-Object System.Drawing.Point(14, 422)
$script:OutputTextBox.Size = New-Object System.Drawing.Size(772, 174)
$script:OutputTextBox.Multiline = $true
$script:OutputTextBox.ReadOnly = $true
$script:OutputTextBox.ScrollBars = 'Vertical'
$script:OutputTextBox.Font = New-Object System.Drawing.Font('Consolas', 9)
$form.Controls.Add($script:OutputTextBox)

$script:StatusLabel = New-FormLabel -Text 'Complete the required fields, then install dependencies and save setup.' -X 14 -Y 602 -Width 770 -Height 22
$form.Controls.Add($script:StatusLabel)
$script:ProgressBar = New-Object System.Windows.Forms.ProgressBar
$script:ProgressBar.Location = New-Object System.Drawing.Point(14, 627)
$script:ProgressBar.Size = New-Object System.Drawing.Size(772, 14)
$script:ProgressBar.Style = 'Blocks'
$form.Controls.Add($script:ProgressBar)

$script:CloseButton = New-Object System.Windows.Forms.Button
$script:CloseButton.Text = 'Close'
$script:CloseButton.Location = New-Object System.Drawing.Point(14, 670)
$script:CloseButton.Size = New-Object System.Drawing.Size(105, 34)
$script:CloseButton.Add_Click({ $form.Close() })
$form.Controls.Add($script:CloseButton)

$script:SaveButton = New-Object System.Windows.Forms.Button
$script:SaveButton.Text = 'Install & save setup'
$script:SaveButton.Location = New-Object System.Drawing.Point(442, 670)
$script:SaveButton.Size = New-Object System.Drawing.Size(170, 34)
$script:SaveButton.Add_Click({
    try {
        $script:Settings = Get-SetupValues
        $setupScript = Join-Path $script:ProjectRoot 'scripts\setup.ps1'
        if (-not (Test-Path -LiteralPath $setupScript -PathType Leaf)) {
            throw "The dependency setup script is missing: $setupScript"
        }

        $logsDirectory = Join-Path $script:ProjectRoot 'logs'
        if (-not (Test-Path -LiteralPath $logsDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $logsDirectory -Force | Out-Null
        }
        $script:SetupLogPath = Join-Path $logsDirectory ("Cthulu_setup_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = Join-Path $PSHOME 'powershell.exe'
        $startInfo.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $setupScript + '" -ForLauncher -BootstrapPython'
        $startInfo.WorkingDirectory = $script:ProjectRoot
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true

        $script:OutputTextBox.Clear()
        $script:OutputQueue = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()
        $script:SetupProcess = New-Object System.Diagnostics.Process
        $script:SetupProcess.StartInfo = $startInfo
        $outputHandler = [System.Diagnostics.DataReceivedEventHandler]{
            param($sender, $eventArgs)
            if ($eventArgs.Data) {
                [void]$script:OutputQueue.Enqueue($eventArgs.Data)
            }
        }
        $script:SetupProcess.add_OutputDataReceived($outputHandler)
        $script:SetupProcess.add_ErrorDataReceived($outputHandler)
        if (-not $script:SetupProcess.Start()) {
            throw 'Could not start the dependency installer.'
        }
        $script:SetupProcess.BeginOutputReadLine()
        $script:SetupProcess.BeginErrorReadLine()
        $script:SaveButton.Enabled = $false
        $script:CloseButton.Enabled = $false
        $tabs.Enabled = $false
        $script:StatusLabel.Text = 'Installing Python if needed and preparing Cthulu dependencies...'
        $script:ProgressBar.Style = 'Marquee'
        $script:SetupTimer.Start()
    } catch {
        [System.Windows.Forms.MessageBox]::Show(
            $_.Exception.Message,
            'Cthulu setup error',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
})
$form.Controls.Add($script:SaveButton)

$script:LaunchButton = New-Object System.Windows.Forms.Button
$script:LaunchButton.Text = 'Open launcher'
$script:LaunchButton.Location = New-Object System.Drawing.Point(622, 670)
$script:LaunchButton.Size = New-Object System.Drawing.Size(164, 34)
$script:LaunchButton.Enabled = $false
$script:LaunchButton.Add_Click({
    $launcher = Join-Path $script:ProjectRoot 'Cthulu Launcher.bat'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        [System.Windows.Forms.MessageBox]::Show(
            "The launcher batch file is missing: $launcher",
            'Cthulu setup error',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return
    }
    $arguments = '/d /c ""' + $launcher + '""'
    Start-Process -FilePath $env:ComSpec -ArgumentList $arguments -WorkingDirectory $script:ProjectRoot
})
$form.Controls.Add($script:LaunchButton)

$script:SetupTimer = New-Object System.Windows.Forms.Timer
$script:SetupTimer.Interval = 250
$script:SetupTimer.Add_Tick({
    $line = $null
    while ($script:OutputQueue.TryDequeue([ref]$line)) {
        $script:OutputTextBox.AppendText($line + [Environment]::NewLine)
        $script:OutputTextBox.SelectionStart = $script:OutputTextBox.TextLength
        $script:OutputTextBox.ScrollToCaret()
        $line = $null
    }

    if (-not $script:SetupProcess -or -not $script:SetupProcess.HasExited) {
        return
    }

    $script:SetupTimer.Stop()
    $script:SetupProcess.WaitForExit()
    $line = $null
    while ($script:OutputQueue.TryDequeue([ref]$line)) {
        $script:OutputTextBox.AppendText($line + [Environment]::NewLine)
        $line = $null
    }
    $exitCode = $script:SetupProcess.ExitCode
    $script:ProgressBar.Style = 'Blocks'
    $tabs.Enabled = $true
    $script:CloseButton.Enabled = $true
    if ($exitCode -ne 0) {
        $script:SaveButton.Enabled = $true
        $script:StatusLabel.Text = "Dependency setup failed (exit code $exitCode). Fix the error above and try again."
        return
    }

    try {
        Save-SetupConfiguration -Settings $script:Settings
        $script:LaunchButton.Enabled = $true
        $script:SaveButton.Enabled = $false
        $script:StatusLabel.Text = 'Setup saved. MT5 credentials are stored per-user; choose a mode from the launcher when ready.'
        [System.Windows.Forms.MessageBox]::Show(
            'Setup is complete. Cthulu has not been started. Use Open launcher when you are ready to choose a mode.',
            'Cthulu setup complete',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    } catch {
        $script:SaveButton.Enabled = $true
        $script:StatusLabel.Text = 'Setup could not save configuration. Review the error and retry.'
        [System.Windows.Forms.MessageBox]::Show(
            $_.Exception.Message,
            'Cthulu configuration error',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
})

[void]$form.ShowDialog()
$script:SetupTimer.Dispose()
if ($script:SetupProcess) {
    $script:SetupProcess.Dispose()
}
$form.Dispose()
