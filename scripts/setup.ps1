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
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$PYTHON_MIN_VERSION = "3.10"
$SCRIPT_DIR = $PSScriptRoot
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR

# Colors for output
function Write-Step { param($msg) Write-Host "► $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "✗ $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Cthulu Trading Bot - Automated Setup" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Check Python installation
Write-Step "Checking Python installation..."
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+\.\d+)") {
        $version = [version]$matches[1]
        $minVersion = [version]$PYTHON_MIN_VERSION
        
        if ($version -ge $minVersion) {
            Write-Success "Python $version detected"
        } else {
            Write-Fail "Python $version is below minimum required version $PYTHON_MIN_VERSION"
            exit 1
        }
    }
} catch {
    Write-Fail "Python not found. Please install Python $PYTHON_MIN_VERSION or higher"
    exit 1
}

# Create virtual environment
if (-not $SkipVenv) {
    Write-Step "Setting up virtual environment..."
    $venvPath = Join-Path $PROJECT_ROOT "venv"
    
    if (Test-Path $venvPath) {
        if ($Force) {
            Write-Warn "Removing existing virtual environment..."
            Remove-Item -Recurse -Force $venvPath
        } else {
            Write-Success "Virtual environment already exists (use -Force to recreate)"
            $SkipVenv = $true
        }
    }
    
    if (-not $SkipVenv) {
        python -m venv $venvPath
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Virtual environment created"
        } else {
            Write-Fail "Failed to create virtual environment"
            exit 1
        }
    }
    
    # Activate venv
    Write-Step "Activating virtual environment..."
    $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
    & $activateScript
    Write-Success "Virtual environment activated"
}

# Upgrade pip
Write-Step "Upgrading pip..."
python -m pip install --upgrade pip --quiet
Write-Success "pip upgraded"

# Install dependencies
Write-Step "Installing dependencies..."
$requirementsFile = Join-Path $PROJECT_ROOT "requirements.txt"
if (Test-Path $requirementsFile) {
    pip install -r $requirementsFile --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Dependencies installed"
    } else {
        Write-Fail "Failed to install dependencies"
        exit 1
    }
} else {
    Write-Fail "requirements.txt not found"
    exit 1
}

# Install dev dependencies if requested
if ($Dev) {
    Write-Step "Installing development dependencies..."
    $devRequirementsFile = Join-Path $PROJECT_ROOT "requirements-dev.txt"
    if (Test-Path $devRequirementsFile) {
        pip install -r $devRequirementsFile --quiet
        Write-Success "Development dependencies installed"
    }
}

# Check MT5 installation
Write-Step "Checking MetaTrader 5 installation..."
try {
    $mt5Check = python -c "import MetaTrader5 as mt5; print(mt5.version())" 2>&1
    if ($mt5Check) {
        Write-Success "MetaTrader5 Python package installed: $mt5Check"
    }
} catch {
    Write-Warn "MetaTrader5 package check failed"
}

# Create config if needed
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

# Initialize database
Write-Step "Initializing database..."
$dbScript = Join-Path $PROJECT_ROOT "scripts" "init_db.py"
if (Test-Path $dbScript) {
    python $dbScript
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Database initialized"
    } else {
        Write-Warn "Database initialization had issues"
    }
}

# Run installation tests
Write-Step "Running installation tests..."
$testScript = Join-Path $PROJECT_ROOT "tests" "test_installation.py"
if (Test-Path $testScript) {
    python $testScript
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Installation tests passed"
    } else {
        Write-Warn "Some installation tests failed"
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Configure your MT5 credentials in config\config.yaml"
Write-Host "  2. Run tests: python -m pytest tests/"
Write-Host "  3. Start Cthulu: python -m cthulu"
Write-Host ""
Write-Host "Documentation: docs\README.md" -ForegroundColor Cyan
Write-Host ""




