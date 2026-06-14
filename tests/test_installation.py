"""
Herald Trading Bot - Simple test script to verify installation
Run this before starting the main bot
"""

import sys
import pytest
from pathlib import Path

print("=" * 60)
print("Cthulu Trading Bot - Installation Test")
print("=" * 60)
print()

# Test 1: Python version
print("✓ Testing Python version...")
python_version = sys.version_info
if python_version >= (3, 10):
    print(f"  ✅ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
else:
    print(f"  ❌ Python {python_version.major}.{python_version.minor} (requires 3.10+)")
    sys.exit(1)

# Test 2: Required imports
print("\n✓ Testing required packages...")
required_packages = [
    ("MetaTrader5", "MetaTrader 5"),
    ("pandas", "Pandas"),
    ("numpy", "NumPy"),
    ("yaml", "PyYAML"),
]

missing_packages = []
for module_name, display_name in required_packages:
    try:
        __import__(module_name)
        print(f"  ✅ {display_name}")
    except ImportError:
        print(f"  ❌ {display_name} - NOT INSTALLED")
        missing_packages.append(display_name)

if missing_packages:
    print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
    print("   Install with: pip install -r requirements.txt")
    # Skip installation test if optional packages are not installed (e.g. MetaTrader5)
    pytest.skip(f"Missing packages: {', '.join(missing_packages)}", allow_module_level=True)

# Test 3: Project structure
print("\n✓ Testing project structure...")
required_dirs = [
    "connector",
    "strategy",
    "indicators",
    "execution",
    "position",
    "logs"
]

for dir_name in required_dirs:
    dir_path = Path(dir_name)
    if dir_path.exists():
        print(f"  ✅ {dir_name}/")
    else:
        print(f"  ❌ {dir_name}/ - MISSING")

# Test 4: Configuration file
print("\n✓ Testing configuration...")
config_path = Path("config.yaml")
if config_path.exists():
    print(f"  ✅ config.yaml exists")
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check critical fields
        critical_fields = [
            "mt5.login",
            "mt5.password",
            "mt5.server",
            "trading.symbol",
        ]
        
        missing_fields = []
        for field in critical_fields:
            keys = field.split('.')
            value = config
            for key in keys:
                value = value.get(key) if isinstance(value, dict) else None
            
            if value is None or value == "your_password_here" or value == 123456789:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"  ⚠️  Please configure: {', '.join(missing_fields)}")
        else:
            print(f"  ✅ Configuration appears complete")
            
    except Exception as e:
        print(f"  ⚠️  Error reading config: {e}")
else:
    print(f"  ❌ config.yaml NOT FOUND")
    print(f"     Copy config.example.yaml to config.yaml and configure it")

# Test 5: MT5 connection
print("\n✓ Testing MT5 connection...")
try:
    import MetaTrader5 as mt5
    
    if mt5.initialize():
        version = mt5.version()
        terminal_info = mt5.terminal_info()
        
        print(f"  ✅ MT5 version: {version}")
        print(f"  ✅ Terminal build: {terminal_info.build}")
        print(f"  ✅ Terminal path: {terminal_info.path}")
        
        mt5.shutdown()
    else:
        error = mt5.last_error()
        print(f"  ⚠️  Cannot initialize MT5: {error}")
        print(f"     Make sure MetaTrader 5 terminal is installed")
        
except Exception as e:
    print(f"  ❌ MT5 test failed: {e}")

# Test 6: Core modules
print("\n✓ Testing Cthulu modules...")
try:
    from utils.logger import setup_logger
    from utils.config import Config
    from core.connection import MT5Connection
    from core.risk_manager import RiskManager
    from core.trade_manager import TradeManager
    from strategies.base_strategy import BaseStrategy
    from strategies.simple_ma_cross import SimpleMovingAverageCross
    
    print(f"  ✅ All Cthulu modules import successfully")
except Exception as e:
    print(f"  ❌ Module import failed: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)

if missing_packages:
    print("❌ Installation INCOMPLETE - missing packages")
    print("   Run: pip install -r requirements.txt")
elif not config_path.exists():
    print("⚠️  Installation OK, but config.yaml needs to be created")
    print("   Run: cp config.example.yaml config.yaml")
    print("   Then edit config.yaml with your MT5 credentials")
else:
    print("✅ Cthulu is ready!")
    print("\nNext steps:")
    print("1. Ensure config.yaml has your MT5 credentials")
    print("2. Make sure you're using a DEMO account")
    print("3. Run: python main.py")
    print("\nMonitor logs: Get-Content .\\logs\\cthulu.log -Wait -Tail 50")

print("=" * 60)




