#!/usr/bin/env bash
#
# Cthulu Trading Bot - Automated Setup Script (Linux/macOS)
# 
# Automated installation and configuration for Cthulu MT5 trading bot.
# Sets up Python environment, installs dependencies, validates configuration.

set -e

PYTHON_MIN_VERSION="3.10"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_step() { echo -e "${CYAN}► $1${NC}"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Cthulu Trading Bot - Automated Setup${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Parse arguments
SKIP_VENV=false
FORCE=false
DEV=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-venv) SKIP_VENV=true; shift ;;
        --force) FORCE=true; shift ;;
        --dev) DEV=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check Python
print_step "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    print_fail "Python not found. Please install Python $PYTHON_MIN_VERSION or higher"
fi

VERSION=$($PYTHON_CMD --version | grep -oP '\d+\.\d+')
if [ "$(printf '%s\n' "$PYTHON_MIN_VERSION" "$VERSION" | sort -V | head -n1)" = "$PYTHON_MIN_VERSION" ]; then
    print_success "Python $VERSION detected"
else
    print_fail "Python $VERSION is below minimum required version $PYTHON_MIN_VERSION"
fi

# Create virtual environment
if [ "$SKIP_VENV" = false ]; then
    print_step "Setting up virtual environment..."
    VENV_PATH="$PROJECT_ROOT/venv"
    
    if [ -d "$VENV_PATH" ]; then
        if [ "$FORCE" = true ]; then
            print_warn "Removing existing virtual environment..."
            rm -rf "$VENV_PATH"
        else
            print_success "Virtual environment already exists (use --force to recreate)"
            SKIP_VENV=true
        fi
    fi
    
    if [ "$SKIP_VENV" = false ]; then
        $PYTHON_CMD -m venv "$VENV_PATH"
        print_success "Virtual environment created"
    fi
    
    # Activate venv
    print_step "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
    print_success "Virtual environment activated"
fi

# Upgrade pip
print_step "Upgrading pip..."
$PYTHON_CMD -m pip install --upgrade pip --quiet
print_success "pip upgraded"

# Install dependencies
print_step "Installing dependencies..."
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
    print_success "Dependencies installed"
else
    print_fail "requirements.txt not found"
fi

# Install dev dependencies
if [ "$DEV" = true ]; then
    print_step "Installing development dependencies..."
    if [ -f "$PROJECT_ROOT/requirements-dev.txt" ]; then
        pip install -r "$PROJECT_ROOT/requirements-dev.txt" --quiet
        print_success "Development dependencies installed"
    fi
fi

# Check MT5 installation
print_step "Checking MetaTrader 5 installation..."
if $PYTHON_CMD -c "import MetaTrader5" 2>/dev/null; then
    MT5_VERSION=$($PYTHON_CMD -c "import MetaTrader5 as mt5; print(mt5.version())")
    print_success "MetaTrader5 Python package installed: $MT5_VERSION"
else
    print_warn "MetaTrader5 package check failed"
fi

# Create config
print_step "Checking configuration..."
CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"
CONFIG_EXAMPLE="$PROJECT_ROOT/config/config.example.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$CONFIG_EXAMPLE" ]; then
        cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
        print_warn "config.yaml created from template - PLEASE CONFIGURE IT"
        echo -e "${YELLOW}  Edit: config/config.yaml${NC}"
    else
        print_warn "config.example.yaml not found"
    fi
else
    print_success "config.yaml exists"
fi

# Create required directories
print_step "Creating required directories..."
for dir in logs data output; do
    DIR_PATH="$PROJECT_ROOT/$dir"
    if [ ! -d "$DIR_PATH" ]; then
        mkdir -p "$DIR_PATH"
        print_success "Created $dir/"
    fi
done

# Initialize database
print_step "Initializing database..."
DB_SCRIPT="$PROJECT_ROOT/scripts/init_db.py"
if [ -f "$DB_SCRIPT" ]; then
    $PYTHON_CMD "$DB_SCRIPT"
    print_success "Database initialized"
fi

# Run installation tests
print_step "Running installation tests..."
TEST_SCRIPT="$PROJECT_ROOT/tests/test_installation.py"
if [ -f "$TEST_SCRIPT" ]; then
    $PYTHON_CMD "$TEST_SCRIPT" && print_success "Installation tests passed" || print_warn "Some installation tests failed"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  1. Configure your MT5 credentials in config/config.yaml"
echo "  2. Run tests: python -m pytest tests/"
echo "  3. Start Cthulu: python -m cthulu"
echo ""
echo -e "${CYAN}Documentation: docs/README.md${NC}"
echo ""




