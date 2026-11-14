<# 
.SYNOPSIS
    Cthulu Trading Bot - Automated Setup Script

.DESCRIPTION
    Automated installation and configuration for Cthulu MT5 trading bot.
    Sets up Python environment, installs dependencies, validates configuration.

.NOTES
    Author: Cthulu Project
    Version: 1.0.0
    Requires: Python 3.10+, MetaTrader 5 Terminal
#>

param(
    [switch]$SkipVenv,
    [switch]$Force,
    [switch]$Dev,
    [switch]$ForLauncher,
    [switch]$BootstrapPython
)

$ErrorActionPreference = "Stop"
$PYTHON_MIN_VERSION = "3.10"
$SCRIPT_DIR = $PSScriptRoot
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR

# Colors for output
function Write-Step { param($msg) Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "-------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  Cthulu Trading Bot - Automated Setup" -ForegroundColor Cyan
Write-Host "-------------------------------------------------------" -ForegroundColor Cyan
Write-Host ""

function Find-PythonCommand {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($candidate in @('-3.12', '-3.11', '-3.10', '-3.13', '-3')) {
            $versionOutput = & $launcher.Source $candidate --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $versionOutput -match 'Python (\d+\.\d+(?:\.\d+)?)') {
                return [pscustomobject]@{
                    Executable = $launcher.Source
                    Arguments = @($candidate)
                    Version = [version]$matches[1]
                }
            }
        }
    }

    foreach ($candidatePath in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
    )) {
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
            $versionOutput = & $candidatePath --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $versionOutput -match 'Python (\d+\.\d+(?:\.\d+)?)') {
                return [pscustomobject]@{
                    Executable = $candidatePath
                    Arguments = @()
                    Version = [version]$matches[1]
                }
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $versionOutput = & $python.Source --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $versionOutput -match 'Python (\d+\.\d+(?:\.\d+)?)') {
            return [pscustomobject]@{
                Executable = $python.Source
                Arguments = @()
                Version = [version]$matches[1]
            }
        }
    }

    return $null
}

function Get-PythonCommand {
    $pythonCommand = Find-PythonCommand
    if ($pythonCommand -or -not $BootstrapPython) {
        return $pythonCommand
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Fail "Python $PYTHON_MIN_VERSION or higher was not found and winget is unavailable. Install Python 3.12, then run setup again."
        exit 1
    }

    Write-Step "Installing Python 3.12 for the current Windows user..."
    & $winget.Source install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Python could not be installed through winget (exit code $LASTEXITCODE). Install Python 3.12 and run setup again."
        exit 1
    }

    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
    $pythonCommand = Find-PythonCommand
    if (-not $pythonCommand) {
        Write-Fail "Python was installed but could not be found. Restart Windows, then run setup again."
        exit 1
    }

    return $pythonCommand
}

$venvPath = Join-Path $PROJECT_ROOT ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$createdVenv = $false

if ($SkipVenv) {
    $pythonCommand = Get-PythonCommand
    if (-not $pythonCommand) {
        Write-Fail "Python $PYTHON_MIN_VERSION or higher was not found."
        exit 1
    }
    $pythonExecutable = $pythonCommand.Executable
    $pythonArguments = $pythonCommand.Arguments
    $pythonVersion = $pythonCommand.Version
} else {
    Write-Step "Setting up virtual environment..."
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or $Force) {
        $pythonCommand = Get-PythonCommand
        if (-not $pythonCommand) {
            Write-Fail "Python $PYTHON_MIN_VERSION or higher was not found. Install Python and enable the Windows launcher, then try again."
            exit 1
        }
        if ($pythonCommand.Version -lt [version]$PYTHON_MIN_VERSION) {
            Write-Fail "Python $($pythonCommand.Version) is below the minimum required version $PYTHON_MIN_VERSION."
            exit 1
        }

        if ((Test-Path -LiteralPath $venvPath) -and $Force) {
            Write-Warn "Removing existing virtual environment..."
            Remove-Item -LiteralPath $venvPath -Recurse -Force
        }

        Write-Step "Creating .venv with Python $($pythonCommand.Version)..."
        $venvArguments = @($pythonCommand.Arguments) + @('-m', 'venv', $venvPath)
        & $pythonCommand.Executable @venvArguments
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            Write-Fail "Failed to create the project virtual environment."
            exit 1
        }
        $createdVenv = $true
    }

    $pythonExecutable = $venvPython
    $pythonArguments = @()
    $versionOutput = & $pythonExecutable --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch 'Python (\d+\.\d+(?:\.\d+)?)') {
        Write-Fail "Could not determine the version of the project virtual environment Python."
        exit 1
    }
    $pythonVersion = [version]$matches[1]
}

Write-Step "Checking Python installation..."
if ($pythonVersion -lt [version]$PYTHON_MIN_VERSION) {
    Write-Fail "Python $pythonVersion is below the minimum required version $PYTHON_MIN_VERSION."
    exit 1
}
Write-Success "Python $pythonVersion detected"

$requirementsFile = Join-Path $PROJECT_ROOT "requirements.txt"
if (-not (Test-Path -LiteralPath $requirementsFile -PathType Leaf)) {
    Write-Fail "requirements.txt not found"
    exit 1
}

if ($createdVenv -or (-not $ForLauncher -and -not $SkipVenv)) {
    Write-Step "Upgrading pip..."
    & $pythonExecutable @pythonArguments -m pip install --upgrade pip --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Could not upgrade pip."
        exit 1
    }
    Write-Success "pip ready"
}

Write-Step "Installing dependencies..."
& $pythonExecutable @pythonArguments -m pip install -r $requirementsFile --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Success "Dependencies installed"
} else {
    Write-Fail "Failed to install dependencies"
    exit 1
}

# Install dev dependencies if requested
if ($Dev) {
    Write-Step "Installing development dependencies..."
    $devRequirementsFile = Join-Path $PROJECT_ROOT "requirements-dev.txt"
    if (Test-Path $devRequirementsFile) {
        & $pythonExecutable @pythonArguments -m pip install -r $devRequirementsFile --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Failed to install development dependencies"
            exit 1
        }
        Write-Success "Development dependencies installed"
    }
}

# Check MT5 installation
Write-Step "Checking MetaTrader 5 installation..."
$mt5Check = & $pythonExecutable @pythonArguments -c 'import MetaTrader5 as mt5; print(mt5.version())' 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "MetaTrader5 Python package installed: $mt5Check"
} else {
    Write-Warn "MetaTrader5 package check failed"
}

# Create config if needed
if (-not $ForLauncher) {
    Write-Step "Checking configuration..."
    $configFile = Join-Path $PROJECT_ROOT "config" "config.yaml"
    $configExample = Join-Path $PROJECT_ROOT "config" "config.example.yaml"

    if (-not (Test-Path $configFile)) {
        if (Test-Path $configExample) {
            Copy-Item $configExample $configFile
            Write-Warn "config.yaml created from template - PLEASE CONFIGURE IT"
            Write-Host "  Edit: config\config.yaml" -ForegroundColor Yellow
        } else {
            Write-Warn "config.example.yaml not found"
        }
    } else {
        Write-Success "config.yaml exists"
    }
}

# Create required directories
Write-Step "Creating required directories..."
$directories = @("logs", "data", "output")
foreach ($dir in $directories) {
    $dirPath = Join-Path $PROJECT_ROOT $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath | Out-Null
        Write-Success "Created $dir/"
    }
}

# Initialize database and run the legacy install checks only for manual setup.
if (-not $ForLauncher) {
    Write-Step "Initializing database..."
    $dbScript = Join-Path $PROJECT_ROOT "scripts" "init_db.py"
    if (Test-Path $dbScript) {
        & $pythonExecutable @pythonArguments $dbScript
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Database initialized"
        } else {
            Write-Warn "Database initialization had issues"
        }
    }

    Write-Step "Running installation tests..."
    $testScript = Join-Path $PROJECT_ROOT "tests" "test_installation.py"
    if (Test-Path $testScript) {
        & $pythonExecutable @pythonArguments $testScript
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Installation tests passed"
        } else {
            Write-Warn "Some installation tests failed"
        }
    }
}

Write-Host ""
Write-Host "-------------------------------------------------------" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "-------------------------------------------------------" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
if ($ForLauncher) {
    Write-Host "  Dependencies are ready. The launcher will now ask which mode to start."
} else {
    Write-Host "  1. Configure your MT5 credentials in config\config.yaml"
    Write-Host "  2. Run tests: python -m pytest tests/"
    Write-Host "  3. Start Cthulu: python -m cthulu"
}
Write-Host ""
Write-Host "Documentation: docs\README.md" -ForegroundColor Cyan
Write-Host ""
