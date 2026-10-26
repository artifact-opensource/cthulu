# CTHULU APEX v5.1 - SINGLE SETUP SCRIPT
# Run as Administrator in PowerShell on the GCP VM

$ErrorActionPreference = "Stop"

Write-Host "`n  CTHULU APEX v5.1 INSTALLER`n" -ForegroundColor Cyan

# 1. Chocolatey
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "[1/6] Installing Chocolatey..." -ForegroundColor Yellow
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = 3072
    iex ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    $env:Path += ";$env:ALLUSERSPROFILE\chocolatey\bin"
}
else { Write-Host "[1/6] Chocolatey OK" -ForegroundColor Green }

# 2. Python & Git
Write-Host "[2/6] Installing Python 3.10 & Git..." -ForegroundColor Yellow
choco install python310 git -y 2>$null
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

# 3. Clone Cthulu
Write-Host "[3/6] Cloning Cthulu..." -ForegroundColor Yellow
if (!(Test-Path "C:\workspace")) { mkdir C:\workspace | Out-Null }
Set-Location C:\workspace
if (Test-Path "cthulu") { 
    Set-Location cthulu; git pull 2>$null 
}
else { 
    git clone https://github.com/amuzetnoM/cthulu.git; Set-Location cthulu 
}

# 4. Virtual environment
Write-Host "[4/6] Setting up Python environment..." -ForegroundColor Yellow
if (!(Test-Path "venv")) { python -m venv venv }
.\venv\Scripts\Activate.ps1
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 5. MT5
Write-Host "[5/6] Downloading MetaTrader 5..." -ForegroundColor Yellow
$mt5 = "C:\mt5setup.exe"
if (!(Test-Path "C:\Program Files\MetaTrader 5\terminal64.exe")) {
    Invoke-WebRequest "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -OutFile $mt5
    Start-Process $mt5 -ArgumentList "/auto" -Wait
    Remove-Item $mt5 -ErrorAction SilentlyContinue
}

# 6. Desktop shortcut
Write-Host "[6/6] Creating launcher..." -ForegroundColor Yellow
$desktop = [Environment]::GetFolderPath("Desktop")
@"
@echo off
cd /d C:\workspace\cthulu
call venv\Scripts\activate.bat
python __main__.py --wizard
pause
"@ | Out-File "$desktop\Cthulu.bat" -Encoding ASCII

Write-Host "`n DONE! Double-click 'Cthulu.bat' on Desktop to start.`n" -ForegroundColor Green
Write-Host "IMPORTANT: Open MT5, login, enable Algo Trading in Tools > Options > Expert Advisors`n" -ForegroundColor Yellow
