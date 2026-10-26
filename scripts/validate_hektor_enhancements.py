#!/usr/bin/env python
"""
Quick validation script for Hektor enhancements.
Tests that all new modules can be imported and basic functionality works.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all new modules can be imported"""
    print("Testing imports...")
    
    try:
        from cognition.pattern_recognition import PatternRecognizer, PatternType
        print("✅ Pattern Recognition module")
    except Exception as e:
        print(f"❌ Pattern Recognition: {e}")
        return False
        
    try:
        from integrations.ml_exporter import MLDataExporter
        print("✅ ML Data Exporter module")
    except Exception as e:
        print(f"❌ ML Data Exporter: {e}")
        return False
        
    try:
        from integrations.performance_analyzer import PerformanceAnalyzer
        print("✅ Performance Analyzer module")
    except Exception as e:
        print(f"❌ Performance Analyzer: {e}")
        return False
        
    try:
        from backtesting.ui_server import BacktestServer
        print("✅ UI Server module")
    except Exception as e:
        print(f"❌ UI Server: {e}")
        return False
        
    try:
        from backtesting.hektor_backtest import HektorBacktest
        print("✅ Hektor Backtest module")
    except Exception as e:
        print(f"❌ Hektor Backtest: {e}")
        return False
        
    try:
        from backtesting.auto_optimizer import AutoOptimizer
        print("✅ Auto Optimizer module")
    except Exception as e:
        print(f"❌ Auto Optimizer: {e}")
        return False
        
    return True


def test_pattern_recognition():
    """Test pattern recognition basic functionality"""
    print("\nTesting Pattern Recognition...")
    
    try:
        from cognition.pattern_recognition import PatternRecognizer, PatternType
        import pandas as pd
        import numpy as np
        
        # Create dummy data
        dates = pd.date_range('2024-01-01', periods=100, freq='15min')
        data = pd.DataFrame({
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 101,
            'low': np.random.randn(100).cumsum() + 99,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        recognizer = PatternRecognizer()
        patterns = recognizer.detect_patterns(data, lookback_bars=50)
        
        print(f"✅ Detected {len(patterns)} patterns")
        return True
        
    except Exception as e:
        print(f"❌ Pattern Recognition test failed: {e}")
        return False


def test_ml_exporter():
    """Test ML data exporter"""
    print("\nTesting ML Data Exporter...")
    
    try:
        from integrations.ml_exporter import MLDataExporter, TrainingExample
        from datetime import datetime
        
        exporter = MLDataExporter(output_dir="./test_output")
        
        # Create dummy example
        example = TrainingExample(
            features={'rsi': 50.0, 'macd': 0.5},
            outcome='WIN',
            pnl=100.0,
            pnl_pct=1.5,
            duration_bars=10,
            profit_tier=2,
            timestamp=datetime.now(),
            symbol='EURUSD',
            strategy='ema_crossover'
        )
        
        print(f"✅ Created training example: {example.to_dict()}")
        return True
        
    except Exception as e:
        print(f"❌ ML Exporter test failed: {e}")
        return False


def test_performance_analyzer():
    """Test performance analyzer"""
    print("\nTesting Performance Analyzer...")
    
    try:
        from integrations.performance_analyzer import PerformanceAnalyzer, PerformanceInsight
        
        analyzer = PerformanceAnalyzer()
        
        # Create dummy insight
        insight = PerformanceInsight(
            condition="Regime: TRENDING_BULLISH",
            metric="win_rate",
            value=0.65,
            sample_size=50,
            confidence=0.8,
            recommendation="FAVORABLE - Trade actively"
        )
        
        print(f"✅ Created performance insight: {insight.to_dict()}")
        return True
        
    except Exception as e:
        print(f"❌ Performance Analyzer test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("="*80)
    print("HEKTOR ENHANCEMENT VALIDATION")
    print("="*80)
    
    results = []
    
    # Test imports
    results.append(("Imports", test_imports()))
    
    # Test modules
    results.append(("Pattern Recognition", test_pattern_recognition()))
    results.append(("ML Exporter", test_ml_exporter()))
    results.append(("Performance Analyzer", test_performance_analyzer()))
    
    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll tests passed! Ready to use Hektor enhancements.")
        return 0
    else:
        print("\nSome tests failed. Check errors above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
