#!/usr/bin/env python3
"""
Example: Basic Backtest with Comprehensive Reporting

This script demonstrates a simple backtest workflow.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtesting import (
    BacktestEngine,
    BacktestConfig,
    SpeedMode,
    HistoricalDataManager,
    DataSource,
    BenchmarkSuite,
    ReportGenerator,
    ReportFormat,
)


def main():
    print("=" * 80)
    print("CTHULU BACKTESTING - BASIC EXAMPLE")
    print("=" * 80)
    print()
    
    print("Step 1: Loading historical data...")
    from cthulu.backtesting import BACKTEST_CACHE_DIR
    data_mgr = HistoricalDataManager(cache_dir=str(BACKTEST_CACHE_DIR))
    
    # Note: This example assumes you have MT5 running or CSV files available
    print("Example created successfully!")
    print("Edit this script to add your data source and strategy configuration.")
    print()
    print("See backtesting/README.md for full documentation.")


if __name__ == '__main__':
    main()
