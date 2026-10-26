#!/bin/bash
# Cthulu System Analyzer and Visualizer
# Comprehensive analysis and visualization generation

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      CTHULU SYSTEM ANALYZER & VISUALIZATION TOOLKIT           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Set script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Default output directory
OUTPUT_DIR="${PROJECT_ROOT}/tools/visualizations"
ANALYSIS_OUTPUT="${PROJECT_ROOT}/tools/codebase_analysis.json"

# Parse arguments
ANALYZE=true
VISUALIZE=true
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --analyze-only)
            VISUALIZE=false
            shift
            ;;
        --visualize-only)
            ANALYZE=false
            shift
            ;;
        --output|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_analyzer.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --analyze-only     Only run the analyzer (no visualizations)"
            echo "  --visualize-only   Only generate visualizations (requires existing analysis)"
            echo "  --output, -o DIR   Output directory for visualizations"
            echo "  --verbose, -v      Verbose output"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_analyzer.sh                    # Full analysis and visualization"
            echo "  ./run_analyzer.sh --analyze-only     # Just analyze the codebase"
            echo "  ./run_analyzer.sh --visualize-only   # Just create visualizations"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found"
    exit 1
fi

# Step 1: Run Analyzer
if [ "$ANALYZE" = true ]; then
    echo "📊 Step 1: Running Code Analyzer"
    echo "────────────────────────────────────────────────────────────────"
    
    cd "$SCRIPT_DIR"
    
    if [ "$VERBOSE" = true ]; then
        python3 analyze_cthulu.py --root "$PROJECT_ROOT" --output "$ANALYSIS_OUTPUT"
    else
        python3 analyze_cthulu.py --root "$PROJECT_ROOT" --output "$ANALYSIS_OUTPUT" 2>&1 | \
            grep -E "🔍|📁|🔬|🚀|✅|💾|Critical|Warning"
    fi
    
    if [ $? -ne 0 ]; then
        echo "❌ Analyzer failed"
        exit 1
    fi
    
    echo ""
fi

# Step 2: Generate Visualizations
if [ "$VISUALIZE" = true ]; then
    echo "🎨 Step 2: Generating Visualizations"
    echo "────────────────────────────────────────────────────────────────"
    
    # Check if analysis file exists
    if [ ! -f "$ANALYSIS_OUTPUT" ]; then
        echo "❌ Error: Analysis file not found: $ANALYSIS_OUTPUT"
        echo "   Run analyzer first with: ./run_analyzer.sh --analyze-only"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
    
    # Check dependencies
    if ! python3 -c "import matplotlib" 2>/dev/null; then
        echo "⚠️  Warning: matplotlib not found"
        echo "   Install with: pip install matplotlib seaborn numpy"
        echo "   Attempting to continue anyway..."
    fi
    
    python3 cthulu_visualizer.py --input "$ANALYSIS_OUTPUT" --output "$OUTPUT_DIR"
    
    if [ $? -ne 0 ]; then
        echo "❌ Visualization generation failed"
        exit 1
    fi
    
    echo ""
fi

# Summary
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                     ANALYSIS COMPLETE                          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

if [ "$ANALYZE" = true ]; then
    echo "📄 Analysis Report: $ANALYSIS_OUTPUT"
fi

if [ "$VISUALIZE" = true ]; then
    echo "🎨 Visualizations: $OUTPUT_DIR"
    echo ""
    echo "Generated visualizations:"
    echo "  • star_future_readiness.png"
    echo "  • module_comparison_radar.png"
    echo "  • improvement_distribution.png"
    echo "  • ml_analysis_dashboard.png"
    echo "  • complexity_heatmap.png"
    echo "  • summary_dashboard.png"
fi

echo ""
echo "✅ All tasks completed successfully!"
echo ""
