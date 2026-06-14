#!/usr/bin/env python3
"""
Cthulu Visualization Toolkit
Professional visualization system for system-centric code analysis

This toolkit provides comprehensive visualizations for:
1. Star: Radar charts for key system metrics
2. Performance Profile: Score distributions across components
3. Rank Distribution: Relative rankings of modules
4. Component Analysis: Module-level visualizations
5. Future Readiness Dashboard: System health indicators

Usage:
    python cthulu_visualizer.py --input codebase_analysis.json --output visualizations/
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Circle, RegularPolygon
from matplotlib.path import Path
from matplotlib.projections.polar import PolarAxes
from matplotlib.projections import register_projection
from matplotlib.spines import Spine
from matplotlib.transforms import Affine2D
import seaborn as sns
import argparse
from pathlib import Path as PathLib
from typing import Dict, List, Tuple
import warnings
# Filter only matplotlib font warnings which are cosmetic
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.dpi'] = 100
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial']


class RadarChart:
    """
    Create radar/star charts for multi-dimensional metrics.
    Adapted from Cthulu Star for Cthulu system metrics.
    """
    
    def __init__(self, fig, variables, rect=None):
        """
        Initialize radar chart.
        
        Args:
            fig: matplotlib figure
            variables: list of variable names
            rect: position [left, bottom, width, height]
        """
        if rect is None:
            rect = [0.1, 0.1, 0.8, 0.8]
        
        self.n = len(variables)
        self.variables = variables
        self.angles = np.linspace(0, 2 * np.pi, self.n, endpoint=False).tolist()
        self.angles += self.angles[:1]  # close the plot
        
        self.ax = fig.add_subplot(111, polar=True)
        self.ax.set_theta_offset(np.pi / 2)
        self.ax.set_theta_direction(-1)
        
        self.ax.set_xticks(self.angles[:-1])
        self.ax.set_xticklabels(self.variables, size=10)
        self.ax.set_ylim(0, 10)
        self.ax.set_yticks(range(1, 11, 2))
        self.ax.set_yticklabels(range(1, 11, 2), size=8, alpha=0.7)
        self.ax.grid(True, linestyle='--', alpha=0.7)
    
    def plot(self, data, label='', color='blue', alpha=0.4):
        """
        Plot data on radar chart.
        
        Args:
            data: list of values for each variable
            label: label for the data series
            color: color for the plot
            alpha: transparency
        """
        values = data + data[:1]  # close the plot
        self.ax.plot(self.angles, values, 'o-', linewidth=2, 
                    label=label, color=color)
        self.ax.fill(self.angles, values, alpha=alpha, color=color)
    
    def set_title(self, title):
        """Set chart title."""
        self.ax.set_title(title, size=14, weight='bold', pad=20)
    
    def add_legend(self):
        """Add legend to chart."""
        self.ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))


class CthuluVisualizer:
    """Main visualization class for Cthulu analyzer output."""
    
    def __init__(self, analysis_data: Dict, output_dir: str = 'visualizations'):
        """
        Initialize visualizer with analysis data.
        
        Args:
            analysis_data: Parsed JSON from analyzer
            output_dir: Directory to save visualizations
        """
        self.data = analysis_data
        self.output_dir = PathLib(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Color schemes
        self.colors = {
            'critical': '#d32f2f',
            'high': '#f57c00',
            'medium': '#fbc02d',
            'low': '#7cb342',
            'excellent': '#4caf50',
            'good': '#8bc34a',
            'warning': '#ff9800',
            'poor': '#e53935'
        }
        
        self.module_colors = sns.color_palette("husl", 32)
    
    def create_star(self):
        """
        Create Star radar chart for future readiness metrics.
        Shows: Extensibility, Scalability, ML Maturity, Documentation, Test Coverage, Overall Health
        """
        print("Creating Star radar chart...")
        
        if 'future_readiness' not in self.data:
            print("  No future readiness data available")
            return
        
        readiness = self.data['future_readiness']
        metrics = readiness['metrics']
        
        # Extract data
        categories = [m['aspect'] for m in metrics]
        scores = [m['score'] for m in metrics]
        
        # Add overall score
        categories.append('Overall\nHealth')
        scores.append(readiness['overall_score'])
        
        # Create figure
        fig = plt.figure(figsize=(10, 10))
        radar = RadarChart(fig, categories)
        
        # Determine color based on scores
        avg_score = np.mean(scores)
        if avg_score >= 8:
            color = self.colors['excellent']
            assessment = 'Excellent'
        elif avg_score >= 6:
            color = self.colors['good']
            assessment = 'Good'
        elif avg_score >= 4:
            color = self.colors['warning']
            assessment = 'Needs Improvement'
        else:
            color = self.colors['poor']
            assessment = 'Critical'
        
        radar.plot(scores, label=f'Cthulu System ({assessment})', 
                  color=color, alpha=0.3)
        radar.set_title('Cthulu System Star\nFuture Readiness Assessment')
        radar.add_legend()
        
        # Save
        output_path = self.output_dir / 'star_future_readiness.png'
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved to {output_path}")
    
    def create_module_comparison(self):
        """Create radar charts comparing top modules."""
        print("Creating module comparison radar charts...")
        
        if 'modules' not in self.data:
            print("  No module data available")
            return
        
        modules = self.data['modules']
        
        # Select top 5 modules by lines of code
        module_list = [(name, data) for name, data in modules.items()]
        module_list.sort(key=lambda x: x[1]['total_lines'], reverse=True)
        top_modules = module_list[:5]
        
        # Metrics to compare
        categories = ['Lines\n(scaled)', 'Functions\n(scaled)', 'Classes\n(scaled)', 
                     'Dependencies', 'Complexity']
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12), subplot_kw=dict(projection='polar'))
        axes = axes.flatten()
        
        for idx, (name, module_data) in enumerate(top_modules):
            ax = axes[idx]
            
            # Normalize metrics to 0-10 scale
            scores = [
                min(module_data['total_lines'] / 1000, 10),  # Scale lines
                min(module_data['total_functions'] / 50, 10),  # Scale functions
                min(module_data['total_classes'] / 20, 10),  # Scale classes
                min(len(module_data.get('dependencies', [])) / 5, 10),  # Dependencies
                self._complexity_to_score(module_data['complexity'])
            ]
            
            angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
            angles += angles[:1]
            values = scores + scores[:1]
            
            ax.set_theta_offset(np.pi / 2)
            ax.set_theta_direction(-1)
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(categories, size=8)
            ax.set_ylim(0, 10)
            ax.set_yticks(range(2, 11, 2))
            ax.set_yticklabels(range(2, 11, 2), size=7, alpha=0.7)
            ax.grid(True, linestyle='--', alpha=0.5)
            
            color = self.module_colors[idx % len(self.module_colors)]
            ax.plot(angles, values, 'o-', linewidth=2, color=color)
            ax.fill(angles, values, alpha=0.25, color=color)
            ax.set_title(f'{name}\n({module_data["total_lines"]} lines)', 
                        size=10, weight='bold', pad=15)
        
        # Remove extra subplot
        fig.delaxes(axes[5])
        
        plt.suptitle('Top 5 Modules Comparison', size=16, weight='bold', y=0.98)
        plt.tight_layout()
        
        output_path = self.output_dir / 'module_comparison_radar.png'
        plt.savefig(output_path, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved to {output_path}")
    
    def _complexity_to_score(self, complexity_str: str) -> float:
        """Convert complexity string to numeric score."""
        mapping = {
            'Low': 9,
            'Medium': 6,
            'High': 3,
            'Very High': 1
        }
        return mapping.get(complexity_str, 5)
    
    def create_improvement_distribution(self):
        """Create distribution plots for code improvements."""
        print("Creating improvement distribution plots...")
        
        if 'code_improvements' not in self.data:
            print("  No code improvements data available")
            return
        
        improvements = self.data['code_improvements']
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. By Severity
        ax = axes[0, 0]
        severities = ['critical', 'high', 'medium', 'low']
        counts = [improvements['by_severity'].get(s, 0) for s in severities]
        colors_severity = [self.colors[s] for s in severities]
        
        bars = ax.barh(severities, counts, color=colors_severity, alpha=0.8)
        ax.set_xlabel('Number of Issues', fontsize=11)
        ax.set_title('Improvements by Severity', fontsize=12, weight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        for i, (bar, count) in enumerate(zip(bars, counts)):
            if count > 0:
                ax.text(count + 1, i, str(count), va='center', fontsize=10, weight='bold')
        
        # 2. By Category
        ax = axes[0, 1]
        categories = list(improvements['by_category'].keys())
        counts = [improvements['by_category'][c] for c in categories]
        colors_cat = sns.color_palette("Set2", len(categories))
        
        bars = ax.barh(categories, counts, color=colors_cat, alpha=0.8)
        ax.set_xlabel('Number of Issues', fontsize=11)
        ax.set_title('Improvements by Category', fontsize=12, weight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        for i, (bar, count) in enumerate(zip(bars, counts)):
            if count > 0:
                ax.text(count + 1, i, str(count), va='center', fontsize=10, weight='bold')
        
        # 3. By Effort
        ax = axes[1, 0]
        if 'by_effort' in improvements and improvements['by_effort']:
            efforts = list(improvements['by_effort'].keys())
            counts = [improvements['by_effort'][e] for e in efforts]
            colors_effort = ['#4caf50', '#ff9800', '#f44336'][:len(efforts)]
            
            wedges, texts, autotexts = ax.pie(counts, labels=efforts, autopct='%1.1f%%',
                                               colors=colors_effort, startangle=90)
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_weight('bold')
            ax.set_title('Improvements by Effort', fontsize=12, weight='bold')
        
        # 4. Total Summary
        ax = axes[1, 1]
        ax.axis('off')
        
        total = improvements['total_suggestions']
        critical = improvements['by_severity'].get('critical', 0)
        high = improvements['by_severity'].get('high', 0)
        
        summary_text = f"""
        Code Improvement Summary
        
        Total Suggestions: {total}
        
        Critical Issues: {critical}
        High Priority: {high}
        Medium Priority: {improvements['by_severity'].get('medium', 0)}
        Low Priority: {improvements['by_severity'].get('low', 0)}
        
        Security: {improvements['by_category'].get('security', 0)}
        Performance: {improvements['by_category'].get('performance', 0)}
        Maintainability: {improvements['by_category'].get('maintainability', 0)}
        ML Best Practices: {improvements['by_category'].get('ml_best_practice', 0)}
        """
        
        ax.text(0.5, 0.5, summary_text, transform=ax.transAxes,
               fontsize=11, verticalalignment='center', horizontalalignment='center',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
        
        plt.suptitle('Code Improvement Analysis', size=16, weight='bold')
        plt.tight_layout()
        
        output_path = self.output_dir / 'improvement_distribution.png'
        plt.savefig(output_path, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved to {output_path}")
    
    def create_ml_analysis_dashboard(self):
        """Create ML/RL component analysis dashboard."""
        print("Creating ML/RL analysis dashboard...")
        
        if 'ml_analysis' not in self.data:
            print("  No ML analysis data available")
            return
        
        ml = self.data['ml_analysis']
        summary = ml['summary']
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. Implementation Status
        ax = axes[0, 0]
        status = ml['implementation_status']
        labels = ['Implemented', 'Partial', 'Stub']
        sizes = [status['implemented'], status['partial'], status['stub']]
        colors_status = ['#4caf50', '#ff9800', '#e0e0e0']
        explode = (0.1, 0, 0)
        
        wedges, texts, autotexts = ax.pie(sizes, explode=explode, labels=labels,
                                           autopct='%1.1f%%', colors=colors_status,
                                           startangle=90, textprops={'weight': 'bold'})
        for autotext in autotexts:
            autotext.set_color('white')
        ax.set_title('ML Component Implementation Status', fontsize=12, weight='bold')
        
        # 2. Components by Type
        ax = axes[0, 1]
        components_by_type = ml['components_by_type']
        types = list(components_by_type.keys())[:7]  # Top 7
        counts = [len(components_by_type[t]) for t in types]
        
        colors_types = sns.color_palette("Set3", len(types))
        bars = ax.barh(types, counts, color=colors_types, alpha=0.8)
        ax.set_xlabel('Number of Components', fontsize=11)
        ax.set_title('ML Components by Type', fontsize=12, weight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        for i, (bar, count) in enumerate(zip(bars, counts)):
            ax.text(count + 0.5, i, str(count), va='center', fontsize=10, weight='bold')
        
        # 3. ML Metrics Summary
        ax = axes[1, 0]
        ax.axis('off')
        
        ml_summary = f"""
        ML/RL System Metrics
        
        Total ML Files: {summary['total_ml_files']}
        Total ML Lines: {summary['total_ml_lines']:,}
        Total ML Functions: {summary['total_ml_functions']:,}
        
        Architectures Detected:
        {chr(10).join(f'  • {arch}' for arch in summary.get('ml_architectures', []))}
        
        Training Capabilities:
        {chr(10).join(f'  • {cap}' for cap in summary.get('training_capabilities', []))}
        """
        
        ax.text(0.5, 0.5, ml_summary, transform=ax.transAxes,
               fontsize=10, verticalalignment='center', horizontalalignment='center',
               bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))
        
        # 4. ML Code Coverage
        ax = axes[1, 1]
        total_lines = self.data['summary']['total_lines']
        ml_lines = summary['total_ml_lines']
        non_ml_lines = total_lines - ml_lines
        
        sizes = [ml_lines, non_ml_lines]
        labels = [f'ML/RL Code\n({ml_lines:,} lines)', 
                 f'Other Code\n({non_ml_lines:,} lines)']
        colors_coverage = ['#9c27b0', '#e0e0e0']
        
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%',
                                           colors=colors_coverage, startangle=90)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_weight('bold')
        ax.set_title('ML Code Coverage', fontsize=12, weight='bold')
        
        plt.suptitle('ML/RL Component Analysis', size=16, weight='bold')
        plt.tight_layout()
        
        output_path = self.output_dir / 'ml_analysis_dashboard.png'
        plt.savefig(output_path, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved to {output_path}")
    
    def create_complexity_heatmap(self):
        """Create heatmap of module complexity vs size."""
        print("Creating complexity heatmap...")
        
        if 'modules' not in self.data:
            print("  No module data available")
            return
        
        modules = self.data['modules']
        
        # Prepare data
        module_names = []
        lines_data = []
        complexity_data = []
        
        complexity_mapping = {'Low': 1, 'Medium': 2, 'High': 3, 'Very High': 4}
        
        for name, data in sorted(modules.items(), key=lambda x: x[1]['total_lines'], reverse=True)[:15]:
            module_names.append(name)
            lines_data.append(data['total_lines'])
            complexity_data.append(complexity_mapping.get(data['complexity'], 2))
        
        # Create figure
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Create scatter plot with size and color
        sizes = np.array(lines_data) / 10  # Scale down for visualization
        colors_heat = [self.colors['low'] if c == 1 else 
                      self.colors['medium'] if c == 2 else
                      self.colors['high'] if c == 3 else 
                      self.colors['critical'] for c in complexity_data]
        
        scatter = ax.scatter(range(len(module_names)), complexity_data, 
                           s=sizes, c=colors_heat, alpha=0.6, edgecolors='black')
        
        ax.set_yticks([1, 2, 3, 4])
        ax.set_yticklabels(['Low', 'Medium', 'High', 'Very High'])
        ax.set_xticks(range(len(module_names)))
        ax.set_xticklabels(module_names, rotation=45, ha='right')
        ax.set_ylabel('Complexity', fontsize=12, weight='bold')
        ax.set_title('Module Complexity vs Size\n(bubble size = lines of code)', 
                    fontsize=14, weight='bold')
        ax.grid(True, alpha=0.3)
        
        # Add legend
        for i, name in enumerate(module_names):
            ax.annotate(f'{lines_data[i]:,}', 
                       xy=(i, complexity_data[i]),
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=8, alpha=0.7)
        
        plt.tight_layout()
        
        output_path = self.output_dir / 'complexity_heatmap.png'
        plt.savefig(output_path, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved to {output_path}")
    
    def create_summary_dashboard(self):
        """Create overall summary dashboard."""
        print("Creating summary dashboard...")
        
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        summary = self.data['summary']
        
        # Title
        fig.suptitle('Cthulu System Analysis Dashboard', 
                    fontsize=20, weight='bold', y=0.98)
        
        # 1. Overall Metrics (top left)
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.axis('off')
        metrics_text = f"""
        Overall System Metrics
        
        Total Files: {summary['total_files']}
        Total Lines: {summary['total_lines']:,}
        Total Functions: {summary['total_functions']:,}
        Total Classes: {summary['total_classes']:,}
        Total Modules: {summary['total_modules']}
        """
        ax1.text(0.5, 0.5, metrics_text, transform=ax1.transAxes,
                fontsize=11, verticalalignment='center', horizontalalignment='center',
                bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.3))
        
        # 2. Issues Overview (top center)
        ax2 = fig.add_subplot(gs[0, 1])
        issues = [summary['critical_issues'], summary['warning_issues']]
        labels = ['Critical', 'Warnings']
        colors_issues = [self.colors['critical'], self.colors['warning']]
        bars = ax2.bar(labels, issues, color=colors_issues, alpha=0.8)
        ax2.set_ylabel('Count', fontsize=10)
        ax2.set_title('Issues Detected', fontsize=12, weight='bold')
        ax2.grid(axis='y', alpha=0.3)
        for bar, issue in zip(bars, issues):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{issue}', ha='center', va='bottom', fontsize=11, weight='bold')
        
        # 3. ML Components (top right)
        if 'ml_analysis' in self.data:
            ax3 = fig.add_subplot(gs[0, 2])
            ml_summary = self.data['ml_analysis']['summary']
            ml_metrics = [
                ml_summary['total_ml_files'],
                ml_summary['total_ml_functions'],
                summary['ml_components']
            ]
            ml_labels = ['Files', 'Functions', 'Components']
            bars = ax3.bar(ml_labels, ml_metrics, color='#9c27b0', alpha=0.6)
            ax3.set_ylabel('Count', fontsize=10)
            ax3.set_title('ML/RL System', fontsize=12, weight='bold')
            ax3.grid(axis='y', alpha=0.3)
            for bar, metric in zip(bars, ml_metrics):
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2., height,
                        f'{metric}', ha='center', va='bottom', fontsize=10)
        
        # 4. Future Readiness Radar (middle, spans 2 columns)
        if 'future_readiness' in self.data:
            ax4 = fig.add_subplot(gs[1:, :2], projection='polar')
            readiness = self.data['future_readiness']
            metrics = readiness['metrics']
            
            categories = [m['aspect'] for m in metrics]
            scores = [m['score'] for m in metrics]
            
            angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
            angles += angles[:1]
            values = scores + scores[:1]
            
            ax4.set_theta_offset(np.pi / 2)
            ax4.set_theta_direction(-1)
            ax4.set_xticks(angles[:-1])
            ax4.set_xticklabels(categories, size=10)
            ax4.set_ylim(0, 10)
            ax4.set_yticks(range(2, 11, 2))
            ax4.set_yticklabels(range(2, 11, 2), size=8, alpha=0.7)
            ax4.grid(True, linestyle='--', alpha=0.7)
            
            ax4.plot(angles, values, 'o-', linewidth=2, color='#2196f3')
            ax4.fill(angles, values, alpha=0.25, color='#2196f3')
            ax4.set_title('Future Readiness\n(Overall: {:.1f}/10)'.format(readiness['overall_score']),
                         size=12, weight='bold', pad=20)
        
        # 5. Top Issues (right column)
        ax5 = fig.add_subplot(gs[1:, 2])
        ax5.axis('off')
        
        if 'code_improvements' in self.data:
            improvements = self.data['code_improvements']
            top_issues_text = f"""
            Code Improvements
            
            Total: {improvements['total_suggestions']}
            
            By Severity:
              Critical: {improvements['by_severity'].get('critical', 0)}
              High: {improvements['by_severity'].get('high', 0)}
              Medium: {improvements['by_severity'].get('medium', 0)}
              Low: {improvements['by_severity'].get('low', 0)}
            
            By Category:
              Security: {improvements['by_category'].get('security', 0)}
              Performance: {improvements['by_category'].get('performance', 0)}
              Maintainability: {improvements['by_category'].get('maintainability', 0)}
              ML Practices: {improvements['by_category'].get('ml_best_practice', 0)}
            """
            ax5.text(0.5, 0.5, top_issues_text, transform=ax5.transAxes,
                    fontsize=10, verticalalignment='center', horizontalalignment='center',
                    bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.5))
        
        plt.tight_layout()
        
        output_path = self.output_dir / 'summary_dashboard.png'
        plt.savefig(output_path, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved to {output_path}")
    
    def generate_all(self):
        """Generate all visualizations."""
        print("\n" + "="*70)
        print("CTHULU VISUALIZATION TOOLKIT")
        print("Generating comprehensive system visualizations...")
        print("="*70 + "\n")
        
        self.create_star()
        self.create_module_comparison()
        self.create_improvement_distribution()
        self.create_ml_analysis_dashboard()
        self.create_complexity_heatmap()
        self.create_summary_dashboard()
        
        print("\n" + "="*70)
        print("✅ All visualizations generated successfully!")
        print(f"📁 Output directory: {self.output_dir}")
        print("="*70 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Cthulu Visualization Toolkit - Generate comprehensive system visualizations'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='codebase_analysis.json',
        help='Input JSON file from analyzer'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='visualizations',
        help='Output directory for visualizations'
    )
    
    args = parser.parse_args()
    
    # Load analysis data
    try:
        with open(args.input, 'r') as f:
            analysis_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Input file '{args.input}' not found")
        print("   Please run the analyzer first: python analyze_cthulu.py")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in '{args.input}': {e}")
        return 1
    
    # Create visualizations
    visualizer = CthuluVisualizer(analysis_data, args.output)
    visualizer.generate_all()
    
    return 0


if __name__ == '__main__':
    exit(main())
