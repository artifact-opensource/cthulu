# Cthulu Visualization Toolkit

Comprehensive visualization system adapted from proprietary system for Cthulu system analysis.

## Overview

This toolkit generates 6 types of professional visualizations to analyze the Cthulu codebase from multiple perspectives:

1. **Star Future Readiness** - Radar chart showing system health across 6 dimensions
2. **Module Comparison** - Radar charts comparing top 5 modules
3. **Improvement Distribution** - Analysis of 176 code improvements by severity, category, and effort
4. **ML/RL Analysis Dashboard** - Comprehensive ML component analysis
5. **Complexity Heatmap** - Module complexity vs size visualization
6. **Summary Dashboard** - Executive overview of system health

## Quick Start

### Option 1: Use the Shell Script (Recommended)

```bash
cd /home/runner/work/cthulu/cthulu/tools
./run_analyzer.sh
```

This will:
1. Run the code analyzer
2. Generate all visualizations
3. Save everything to `visualizations/` directory

### Option 2: Manual Execution

```bash
# Step 1: Run analyzer
python analyze_cthulu.py --output codebase_analysis.json

# Step 2: Generate visualizations
python cthulu_visualizer.py --input codebase_analysis.json --output visualizations/
```

## Usage Options

```bash
# Full analysis and visualization
./run_analyzer.sh

# Analyze only (no visualizations)
./run_analyzer.sh --analyze-only

# Visualize only (requires existing analysis)
./run_analyzer.sh --visualize-only

# Custom output directory
./run_analyzer.sh --output /path/to/output

# Verbose output
./run_analyzer.sh --verbose

# Help
./run_analyzer.sh --help
```

## Visualizations Explained

### 1. Star Future Readiness

**File:** `star_future_readiness.png`

**Purpose:** Radar chart showing system readiness across 6 key dimensions

**Metrics:**
- **Extensibility** (10/10): Base classes, factories, plugin architecture
- **Scalability** (0/10): Async/await usage, caching, connection pooling
- **ML/RL Maturity** (10/10): Model versioning, monitoring, training infrastructure
- **Documentation Quality** (10/10): README files, docstrings, guides
- **Test Coverage** (7/10): Unit, integration, and E2E tests
- **Overall Health** (7.4/10): Combined system assessment

**Interpretation:**
- Scores 8-10: Excellent (Green)
- Scores 6-7: Good (Light Green)
- Scores 4-5: Needs Improvement (Yellow)
- Scores 0-3: Critical (Red)

### 2. Module Comparison Radar

**File:** `module_comparison_radar.png`

**Purpose:** Compare top 5 modules across multiple dimensions

**Metrics:**
- Lines (scaled to 0-10)
- Functions (scaled)
- Classes (scaled)
- Dependencies
- Complexity

**Use Case:** Identify which modules need refactoring or optimization

### 3. Improvement Distribution

**File:** `improvement_distribution.png`

**Purpose:** Visual breakdown of 176 code improvement suggestions

**Charts:**
- By Severity: Critical (4), High (47), Medium (64), Low (61)
- By Category: Security (7), Performance (20), Maintainability (79), ML Best Practices (70)
- By Effort: Low, Medium, High
- Summary Statistics

**Use Case:** Prioritize technical debt and improvement work

### 4. ML/RL Analysis Dashboard

**File:** `ml_analysis_dashboard.png`

**Purpose:** Deep dive into ML/RL system health

**Components:**
- Implementation Status (Implemented/Partial/Stub)
- Components by Type (models, pipelines, training, etc.)
- ML Metrics Summary
- ML Code Coverage (56% of codebase)

**Use Case:** Track ML/RL system maturity and coverage

### 5. Complexity Heatmap

**File:** `complexity_heatmap.png`

**Purpose:** Visualize module complexity vs size

**Features:**
- Bubble size = lines of code
- Y-axis = complexity (Low/Medium/High/Very High)
- Color coding by complexity level
- Annotations with exact line counts

**Use Case:** Identify complexity hotspots that need refactoring

### 6. Summary Dashboard

**File:** `summary_dashboard.png`

**Purpose:** Executive overview of entire system

**Sections:**
- Overall Metrics (files, lines, functions, classes, modules)
- Issues Detected (critical and warnings)
- ML Components Count
- Future Readiness Radar
- Code Improvements Summary

**Use Case:** High-level system health check for stakeholders

## Integration with Analyzer

The visualizer automatically reads the JSON output from `analyze_cthulu.py`:

```python
{
  "summary": { ... },
  "modules": { ... },
  "ml_analysis": { ... },
  "code_improvements": {
    "total_suggestions": 176,
    "by_severity": { "critical": 4, "high": 47, ... },
    "by_category": { "security": 7, "performance": 20, ... },
    "details": [ ... ]
  },
  "future_readiness": {
    "overall_score": 7.4,
    "metrics": [ ... ]
  }
}
```

## Technical Details

### Dependencies

```bash
pip install matplotlib seaborn numpy
```

### File Structure

```
tools/
├── analyze_cthulu.py           # Core analyzer
├── cthulu_visualizer.py        # Visualization generator
├── run_analyzer.sh             # Convenience script
├── visualizations/             # Output directory
│   ├── star_future_readiness.png
│   ├── module_comparison_radar.png
│   ├── improvement_distribution.png
│   ├── ml_analysis_dashboard.png
│   ├── complexity_heatmap.png
│   └── summary_dashboard.png
└── VISUALIZATION_TOOLKIT_README.md
```

### Customization

You can customize the visualizer by modifying `cthulu_visualizer.py`:

```python
# Color schemes
self.colors = {
    'critical': '#d32f2f',
    'high': '#f57c00',
    'medium': '#fbc02d',
    'low': '#7cb342',
    ...
}

# DPI settings
plt.rcParams['figure.dpi'] = 100
plt.rcParams['savefig.dpi'] = 300
```

## Comparison with Cthulu


| Feature | Cthulu | Cthulu Visualizer |
|---------|-------------|-------------------|
| Star | Trading performance metrics | System readiness metrics |
| Radar Charts | Algorithm comparison | Module comparison |
| Dashboards | Trading statistics | Code quality metrics |
| Focus | RL trading evaluation | Code health analysis |

## Example Workflow

### Weekly System Health Check

```bash
# 1. Run full analysis
./run_analyzer.sh

# 2. Review visualizations
open visualizations/summary_dashboard.png

# 3. Check critical issues
open visualizations/improvement_distribution.png

# 4. Assess ML system
open visualizations/ml_analysis_dashboard.png
```

### Before Major Release

```bash
# 1. Generate latest analysis
./run_analyzer.sh --verbose

# 2. Export all visualizations for documentation
cp visualizations/*.png ../docs/latest_analysis/

# 3. Review future readiness
# Target: All metrics > 8/10 before release
```

### Continuous Integration

```bash
# In CI/CD pipeline
./run_analyzer.sh --analyze-only
python -c "
import json
report = json.load(open('codebase_analysis.json'))
critical = report['code_improvements']['by_severity']['critical']
if critical > 0:
    print(f'❌ {critical} critical issues found!')
    exit(1)
"
```

## Troubleshooting

### Issue: Font warnings

```
findfont: Generic family 'sans-serif' not found
```

**Solution:** This is cosmetic. Visualizations still generate correctly. To fix:
```bash
sudo apt-get install fonts-dejavu-core
```

### Issue: Module not found

```
ModuleNotFoundError: No module named 'matplotlib'
```

**Solution:**
```bash
pip install matplotlib seaborn numpy
```

### Issue: Permission denied

```
./run_analyzer.sh: Permission denied
```

**Solution:**
```bash
chmod +x run_analyzer.sh
```

## Performance

- **Analyzer Runtime:** ~15 seconds for 288 files
- **Visualization Generation:** ~5 seconds for 6 charts
- **Total Time:** ~20 seconds end-to-end
- **Output Size:** ~2.9MB for all visualizations

## Future Enhancements

Planned additions:
- [ ] Time-series tracking (track metrics over time)
- [ ] Comparison mode (compare different branches/commits)
- [ ] Interactive HTML dashboards
- [ ] PDF report generation
- [ ] Custom metric definitions
- [ ] Email notifications for critical issues

## Credits

- **Adapted from:** proprietary system
- **Adapted for:** Cthulu system-centric code analysis

## License

Follows the same license as the Cthulu project.

---

**Version:** 1.0  
**Last Updated:** 2026-01-17  
**Maintainer:** Cthulu Development Team
