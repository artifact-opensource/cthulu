#!/usr/bin/env python3
"""
Cthulu Code Analyzer - Automated System Analysis Tool (Enhanced v2.0)

This tool scans the Cthulu codebase and generates:
- Code metrics (LOC, complexity, function counts)
- Dependency graphs
- Issue detection (oversized files, complexity warnings)
- JSON output for system map updates
- Performance bottleneck identification
- Deep ML/RL component analysis with architecture insights
- Code improvement suggestions (security, performance, maintainability)
- Future-readiness assessment (extensibility, scalability)
- Technical debt identification with severity levels
- Best practices compliance checking

Usage:
    python analyze_cthulu.py [--output report.json] [--verbose]
"""

import ast
import os
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import sys


@dataclass
class FileMetrics:
    """Metrics for a single Python file."""
    path: str
    name: str
    lines: int
    functions: int
    classes: int
    imports: List[str]
    complexity_score: int
    issues: List[str]
    dependencies: List[str]
    is_ml_component: bool = False
    ml_features: List[str] = field(default_factory=list)


@dataclass
class ModuleMetrics:
    """Metrics for a module/directory."""
    name: str
    path: str
    total_lines: int
    total_functions: int
    total_classes: int
    files: List[str]
    dependencies: Set[str]
    issues: List[str]
    complexity: str
    is_ml_module: bool = False


@dataclass
class MLComponentMetrics:
    """Metrics specifically for ML/RL components."""
    component_name: str
    component_type: str  # 'feature_pipeline', 'model', 'training', 'mlops'
    file_path: str
    features_count: int
    model_architecture: Optional[str]
    training_capabilities: List[str]
    dependencies: List[str]
    status: str  # 'implemented', 'partial', 'stub'


@dataclass
class CodeImprovement:
    """Suggested code improvement."""
    file_path: str
    severity: str  # 'critical', 'high', 'medium', 'low', 'info'
    category: str  # 'security', 'performance', 'maintainability', 'extensibility', 'ml_best_practice'
    issue: str
    suggestion: str
    impact: str
    effort: str  # 'low', 'medium', 'high'
    line_range: Optional[Tuple[int, int]] = None


@dataclass
class FutureReadinessMetric:
    """Future-readiness assessment metric."""
    aspect: str
    score: int  # 0-10
    assessment: str
    recommendations: List[str]


class CodeAnalyzer:
    """Analyzes Python codebase for metrics and issues."""
    
    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self.file_metrics: Dict[str, FileMetrics] = {}
        self.module_metrics: Dict[str, ModuleMetrics] = {}
        self.ml_components: Dict[str, MLComponentMetrics] = {}
        self.global_imports: Set[str] = set()
        self.code_improvements: List[CodeImprovement] = []
        self.future_readiness: List[FutureReadinessMetric] = []
        
        # Complexity thresholds
        self.LARGE_FILE_LINES = 1000
        self.VERY_LARGE_FILE_LINES = 1500
        self.MAX_FUNCTIONS_PER_FILE = 50
        self.HIGH_COMPLEXITY_THRESHOLD = 15
        self.CYCLOMATIC_COMPLEXITY_HIGH = 10
        
        # Directories to skip
        self.SKIP_DIRS = {
            '.git', '.venv', 'venv', 'venv312', '__pycache__', 'node_modules',
            '.archive', 'build', 'dist', '.pytest_cache', 'site-packages',
            '.worktrees', 'worktrees', 'cthulu.worktrees'
        }
        
        # Enhanced ML-related patterns for detection
        self.ML_PATTERNS = {
            'neural_network': ['forward', 'backward', 'relu', 'softmax', 'sigmoid', 'Q-Network', 'QNetwork', 
                             'PolicyNetwork', 'ValueNetwork', 'DQN', 'PPO', 'ActorCritic'],
            'training': ['train', 'fit', 'epoch', 'batch', 'learning_rate', 'optimizer', 'adam', 'sgd',
                        'backprop', 'gradient', 'loss_function', 'train_step', 'validation'],
            'feature_engineering': ['extract_features', 'FeaturePipeline', 'normalize', 'standardize',
                                  'feature_extraction', 'preprocessing', 'transform', 'feature_names'],
            'reinforcement_learning': ['Q-learning', 'PPO', 'epsilon', 'replay_buffer', 'reward', 'action_space',
                                     'state_space', 'policy', 'value_function', 'experience', 'exploration'],
            'model_ops': ['registry', 'drift', 'retrain', 'versioning', 'MLOps', 'model_version',
                        'drift_detection', 'monitoring', 'deployment'],
            'inference': ['predict', 'inference', 'forward_pass', 'get_action', 'evaluate'],
            'data_pipeline': ['DataLoader', 'Dataset', 'batch_processing', 'data_augmentation'],
        }
        
        # Known ML modules
        self.ML_MODULES = {'ML_RL', 'training', 'cognition'}
        
        # Security patterns to detect
        self.SECURITY_PATTERNS = {
            'sql_injection': [r'execute\s*\(.*%.*\)', r'\.format\s*\(.*sql', r'\+.*sql'],
            'command_injection': [r'os\.system\s*\(', r'subprocess\.call\s*\(.*shell=True'],
            'hardcoded_secrets': [r'password\s*=\s*["\']', r'api_key\s*=\s*["\']', r'secret\s*=\s*["\']'],
            'unsafe_deserialization': [r'pickle\.loads', r'yaml\.load\(', r'eval\s*\('],
        }
        
        # Performance anti-patterns
        self.PERFORMANCE_ANTIPATTERNS = {
            'loop_in_loop': r'for\s+.*:\s*\n\s+for\s+.*:',
            'repeated_computation': r'for\s+.*:\s*.*\.calculate\(',
            'inefficient_string_concat': r'\+\s*=\s*["\']',
        }
    
    def analyze(self) -> Dict:
        """Run full analysis on codebase."""
        print("🔍 Starting Cthulu codebase analysis...")
        
        # Scan all Python files
        python_files = self._find_python_files()
        print(f"📁 Found {len(python_files)} Python files")
        
        # Analyze each file
        for file_path in python_files:
            self._analyze_file(file_path)
        
        # Aggregate module metrics
        self._aggregate_modules()
        
        # Analyze ML components specifically
        self._analyze_ml_components()
        
        # NEW: Perform deep code analysis for improvements
        print("🔬 Performing deep code analysis...")
        self._analyze_code_quality()
        
        # NEW: Assess future-readiness
        print("🚀 Assessing future-readiness...")
        self._assess_future_readiness()
        
        # Generate report
        report = self._generate_report()
        
        print("✅ Analysis complete!")
        return report
    
    def _analyze_ml_components(self):
        """Analyze ML/RL specific components."""
        ml_files = [
            f for f in self.file_metrics.values() 
            if f.is_ml_component or any(m in f.path for m in self.ML_MODULES)
        ]
        
        for metrics in ml_files:
            component = self._classify_ml_component(metrics)
            if component:
                self.ml_components[metrics.path] = component
    
    def _classify_ml_component(self, metrics: FileMetrics) -> Optional[MLComponentMetrics]:
        """Classify a file as an ML component."""
        path = metrics.path.lower()
        name = metrics.name.lower()
        
        # Determine component type
        if 'feature' in name or 'pipeline' in name:
            comp_type = 'feature_pipeline'
        elif 'rl' in name or 'position_sizer' in name or 'q_' in name:
            comp_type = 'reinforcement_learning'
        elif 'train' in name:
            comp_type = 'training'
        elif 'mlops' in name or 'registry' in name or 'drift' in name:
            comp_type = 'mlops'
        elif 'predict' in name or 'model' in name:
            comp_type = 'model'
        elif 'llm' in name or 'analysis' in name:
            comp_type = 'llm_analysis'
        else:
            comp_type = 'other'
        
        # Count features (heuristic based on class attributes)
        features_count = len(metrics.ml_features)
        
        # Determine model architecture
        architecture = None
        for feature in metrics.ml_features:
            if 'QNetwork' in feature or 'Q-Network' in feature:
                architecture = 'Q-Learning Network'
            elif 'PolicyNetwork' in feature:
                architecture = 'Policy Network (PPO)'
            elif 'Softmax' in feature:
                architecture = 'Softmax Classifier'
        
        # Determine training capabilities
        training_caps = []
        if any('train' in f.lower() for f in metrics.ml_features):
            training_caps.append('supervised_training')
        if any('replay' in f.lower() for f in metrics.ml_features):
            training_caps.append('experience_replay')
        if any('batch' in f.lower() for f in metrics.ml_features):
            training_caps.append('batch_training')
        
        # Determine status
        if metrics.functions > 5 and metrics.lines > 100:
            status = 'implemented'
        elif metrics.functions > 2:
            status = 'partial'
        else:
            status = 'stub'
        
        return MLComponentMetrics(
            component_name=metrics.name.replace('.py', ''),
            component_type=comp_type,
            file_path=metrics.path,
            features_count=features_count,
            model_architecture=architecture,
            training_capabilities=training_caps,
            dependencies=metrics.dependencies,
            status=status
        )
    
    def _find_python_files(self) -> List[Path]:
        """Find all Python files in the repository."""
        python_files = []
        for root, dirs, files in os.walk(self.root):
            # Remove skip directories from dirs in-place
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            
            for file in files:
                if file.endswith('.py'):
                    python_files.append(Path(root) / file)
        
        return python_files
    
    def _analyze_file(self, file_path: Path):
        """Analyze a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Count lines
            lines = len(content.splitlines())
            
            # Parse AST
            try:
                tree = ast.parse(content)
            except SyntaxError:
                # Skip files with syntax errors
                return
            
            # Count functions and classes
            functions = []
            classes = []
            imports = []
            ml_features = []
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                    # Check for ML-related functions
                    if any(p in node.name.lower() for p in ['train', 'predict', 'forward', 'backward', 'extract']):
                        ml_features.append(f"function:{node.name}")
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                    # Check for ML-related classes
                    for pattern_name, patterns in self.ML_PATTERNS.items():
                        if any(p.lower() in node.name.lower() for p in patterns):
                            ml_features.append(f"class:{node.name}")
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    else:
                        if node.module:
                            imports.append(node.module)
            
            # Detect ML content in file
            is_ml = self._detect_ml_content(content, file_path, imports)
            
            # Calculate complexity score (simple heuristic)
            complexity_score = self._calculate_complexity(tree, lines, len(functions))
            
            # Detect issues
            issues = self._detect_file_issues(file_path, lines, len(functions), complexity_score)
            
            # Extract internal dependencies
            dependencies = self._extract_dependencies(imports)
            
            # Store metrics
            relative_path = str(file_path.relative_to(self.root))
            self.file_metrics[relative_path] = FileMetrics(
                path=relative_path,
                name=file_path.name,
                lines=lines,
                functions=len(functions),
                classes=len(classes),
                imports=imports,
                complexity_score=complexity_score,
                issues=issues,
                dependencies=dependencies,
                is_ml_component=is_ml,
                ml_features=ml_features
            )
            
            # Track global imports
            self.global_imports.update(imports)
            
        except Exception as e:
            print(f"⚠️  Error analyzing {file_path}: {e}")
    
    def _detect_ml_content(self, content: str, file_path: Path, imports: List[str]) -> bool:
        """Detect if file contains ML-related code."""
        # Check file path
        if any(m in str(file_path) for m in self.ML_MODULES):
            return True
        
        # Check imports
        ml_imports = ['numpy', 'sklearn', 'tensorflow', 'torch', 'pandas']
        if any(imp in imports for imp in ml_imports):
            return True
        
        # Check content patterns
        content_lower = content.lower()
        ml_keywords = ['neural', 'network', 'gradient', 'softmax', 'q-learning', 
                      'reinforcement', 'prediction', 'feature extraction',
                      'model training', 'epoch', 'batch_size']
        if any(kw in content_lower for kw in ml_keywords):
            return True
        
        return False
    
    def _calculate_complexity(self, tree: ast.AST, lines: int, functions: int) -> int:
        """Calculate complexity score for a file."""
        # Count control flow statements
        control_flow = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                control_flow += 1
        
        # Simple scoring: lines/100 + functions/10 + control_flow/10
        score = (lines // 100) + (functions // 10) + (control_flow // 10)
        return score
    
    def _detect_file_issues(self, file_path: Path, lines: int, functions: int, complexity: int) -> List[str]:
        """Detect issues in a file."""
        issues = []
        
        if lines > self.VERY_LARGE_FILE_LINES:
            issues.append(f"CRITICAL: Very large file ({lines} lines) - needs refactoring")
        elif lines > self.LARGE_FILE_LINES:
            issues.append(f"WARNING: Large file ({lines} lines) - consider splitting")
        
        if functions > self.MAX_FUNCTIONS_PER_FILE:
            issues.append(f"WARNING: Many functions ({functions}) - consider modularization")
        
        if complexity > self.HIGH_COMPLEXITY_THRESHOLD:
            issues.append(f"WARNING: High complexity score ({complexity}) - needs simplification")
        
        # Check for TODO/FIXME
        try:
            with open(self.root / file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if 'TODO' in content or 'FIXME' in content:
                    issues.append("INFO: Contains TODO/FIXME markers")
        except:
            pass
        
        return issues
    
    def _extract_dependencies(self, imports: List[str]) -> List[str]:
        """Extract internal dependencies from imports."""
        internal_deps = []
        for imp in imports:
            # Extract top-level module name
            parts = imp.split('.')
            if parts:
                module = parts[0]
                # Check if it's an internal module (not stdlib or external)
                if module not in ['os', 'sys', 'ast', 'json', 're', 'pathlib', 'typing', 
                                  'collections', 'dataclasses', 'argparse', 'datetime',
                                  'pandas', 'numpy', 'MetaTrader5', 'd3', 'flask']:
                    internal_deps.append(module)
        
        return list(set(internal_deps))
    
    def _aggregate_modules(self):
        """Aggregate file metrics into module metrics."""
        modules = defaultdict(lambda: {
            'files': [],
            'total_lines': 0,
            'total_functions': 0,
            'total_classes': 0,
            'dependencies': set(),
            'issues': []
        })
        
        for file_path, metrics in self.file_metrics.items():
            # Determine module name (top-level directory)
            parts = Path(file_path).parts
            if len(parts) > 1:
                module_name = parts[0]
            else:
                module_name = 'root'
            
            modules[module_name]['files'].append(file_path)
            modules[module_name]['total_lines'] += metrics.lines
            modules[module_name]['total_functions'] += metrics.functions
            modules[module_name]['total_classes'] += metrics.classes
            modules[module_name]['dependencies'].update(metrics.dependencies)
            modules[module_name]['issues'].extend(metrics.issues)
        
        # Convert to ModuleMetrics
        for module_name, data in modules.items():
            # Determine complexity
            avg_lines_per_file = data['total_lines'] / len(data['files']) if data['files'] else 0
            if avg_lines_per_file > 1000:
                complexity = "Very High"
            elif avg_lines_per_file > 500:
                complexity = "High"
            elif avg_lines_per_file > 200:
                complexity = "Medium"
            else:
                complexity = "Low"
            
            self.module_metrics[module_name] = ModuleMetrics(
                name=module_name,
                path=module_name,
                total_lines=data['total_lines'],
                total_functions=data['total_functions'],
                total_classes=data['total_classes'],
                files=data['files'],
                dependencies=data['dependencies'],
                issues=data['issues'][:5],  # Top 5 issues
                complexity=complexity
            )
    
    def _generate_report(self) -> Dict:
        """Generate comprehensive report."""
        # Count total metrics
        total_lines = sum(m.lines for m in self.file_metrics.values())
        total_functions = sum(m.functions for m in self.file_metrics.values())
        total_classes = sum(m.classes for m in self.file_metrics.values())
        
        # Find top issues
        all_issues = []
        for metrics in self.file_metrics.values():
            for issue in metrics.issues:
                all_issues.append({
                    'file': metrics.path,
                    'issue': issue,
                    'lines': metrics.lines,
                    'complexity': metrics.complexity_score
                })
        
        # Sort by severity
        critical_issues = [i for i in all_issues if 'CRITICAL' in i['issue']]
        warning_issues = [i for i in all_issues if 'WARNING' in i['issue']]
        
        # Find largest files
        largest_files = sorted(
            self.file_metrics.values(),
            key=lambda x: x.lines,
            reverse=True
        )[:10]
        
        # Find most complex files
        most_complex = sorted(
            self.file_metrics.values(),
            key=lambda x: x.complexity_score,
            reverse=True
        )[:10]
        
        # Generate dependency graph
        dependency_graph = self._build_dependency_graph()
        
        # Generate ML analysis
        ml_analysis = self._generate_ml_analysis()
        
        report = {
            'summary': {
                'total_files': len(self.file_metrics),
                'total_lines': total_lines,
                'total_functions': total_functions,
                'total_classes': total_classes,
                'total_modules': len(self.module_metrics),
                'critical_issues': len(critical_issues),
                'warning_issues': len(warning_issues),
                'ml_components': len(self.ml_components)
            },
            'modules': {
                name: asdict(metrics) 
                for name, metrics in self.module_metrics.items()
            },
            'ml_analysis': ml_analysis,
            'top_issues': {
                'critical': critical_issues,
                'warnings': warning_issues[:10]
            },
            'largest_files': [
                {
                    'path': m.path,
                    'lines': m.lines,
                    'functions': m.functions,
                    'complexity': m.complexity_score
                }
                for m in largest_files
            ],
            'most_complex_files': [
                {
                    'path': m.path,
                    'lines': m.lines,
                    'functions': m.functions,
                    'complexity': m.complexity_score
                }
                for m in most_complex
            ],
            'dependency_graph': dependency_graph,
            'recommendations': self._generate_recommendations(critical_issues, warning_issues),
            'code_improvements': self._format_code_improvements(),
            'future_readiness': self._format_future_readiness()
        }
        
        return report
    
    def _generate_ml_analysis(self) -> Dict:
        """Generate detailed ML/RL analysis."""
        # Group by component type
        by_type = defaultdict(list)
        for path, comp in self.ml_components.items():
            by_type[comp.component_type].append(asdict(comp))
        
        # Count ML metrics
        ml_files = [f for f in self.file_metrics.values() if f.is_ml_component]
        total_ml_lines = sum(f.lines for f in ml_files)
        total_ml_functions = sum(f.functions for f in ml_files)
        
        # Identify architectures
        architectures = set()
        for comp in self.ml_components.values():
            if comp.model_architecture:
                architectures.add(comp.model_architecture)
        
        # Identify capabilities
        all_capabilities = set()
        for comp in self.ml_components.values():
            all_capabilities.update(comp.training_capabilities)
        
        return {
            'summary': {
                'total_ml_files': len(ml_files),
                'total_ml_lines': total_ml_lines,
                'total_ml_functions': total_ml_functions,
                'ml_architectures': list(architectures),
                'training_capabilities': list(all_capabilities)
            },
            'components_by_type': dict(by_type),
            'implementation_status': {
                'implemented': len([c for c in self.ml_components.values() if c.status == 'implemented']),
                'partial': len([c for c in self.ml_components.values() if c.status == 'partial']),
                'stub': len([c for c in self.ml_components.values() if c.status == 'stub'])
            }
        }
    
    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        """Build module dependency graph."""
        graph = {}
        for module_name, metrics in self.module_metrics.items():
            graph[module_name] = list(metrics.dependencies)
        return graph
    
    def _generate_recommendations(self, critical_issues: List, warning_issues: List) -> List[str]:
        """Generate recommendations based on findings."""
        recommendations = []
        
        if critical_issues:
            recommendations.append(
                f"URGENT: Address {len(critical_issues)} critical issues immediately. "
                "These files are too large and need refactoring."
            )
        
        if len(warning_issues) > 20:
            recommendations.append(
                f"HIGH PRIORITY: {len(warning_issues)} warnings detected. "
                "Consider technical debt cleanup sprint."
            )
        
        # Check for large modules
        large_modules = [m for m in self.module_metrics.values() if m.total_lines > 5000]
        if large_modules:
            recommendations.append(
                f"Consider splitting {len(large_modules)} large modules into smaller, "
                "more focused components."
            )
        
        return recommendations
    
    def _analyze_code_quality(self):
        """Perform deep code quality analysis and generate improvement suggestions."""
        for file_path, metrics in self.file_metrics.items():
            try:
                full_path = self.root / file_path
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Security checks
                self._check_security_issues(file_path, content)
                
                # Performance checks
                self._check_performance_issues(file_path, content, metrics)
                
                # Maintainability checks
                self._check_maintainability_issues(file_path, content, metrics)
                
                # ML/RL specific checks
                if metrics.is_ml_component:
                    self._check_ml_best_practices(file_path, content, metrics)
                
            except Exception as e:
                pass  # Continue with other files
    
    def _check_security_issues(self, file_path: str, content: str):
        """Check for security vulnerabilities."""
        # Check for SQL injection risks
        if re.search(r'execute\s*\([^)]*%[^)]*\)', content) or re.search(r'\.format\s*\([^)]*sql', content, re.IGNORECASE):
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='critical',
                category='security',
                issue='Potential SQL injection vulnerability detected',
                suggestion='Use parameterized queries instead of string formatting for SQL. Replace .format() or % with query parameters.',
                impact='Prevents SQL injection attacks that could compromise database',
                effort='low'
            ))
        
        # Check for command injection
        if 'os.system(' in content or re.search(r'subprocess\.call\s*\([^)]*shell\s*=\s*True', content):
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='high',
                category='security',
                issue='Command injection risk with shell=True or os.system()',
                suggestion='Use subprocess with shell=False and pass arguments as list. Validate and sanitize all inputs.',
                impact='Prevents command injection attacks',
                effort='medium'
            ))
        
        # Check for hardcoded secrets
        if re.search(r'(password|api_key|secret|token)\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE):
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='critical',
                category='security',
                issue='Hardcoded credentials detected',
                suggestion='Move credentials to environment variables or secure vault. Use os.getenv() or config management.',
                impact='Prevents credential exposure in version control',
                effort='low'
            ))
        
        # Check for eval() usage
        if 'eval(' in content:
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='high',
                category='security',
                issue='Unsafe eval() usage detected',
                suggestion='Replace eval() with safer alternatives like ast.literal_eval() or json.loads()',
                impact='Prevents arbitrary code execution',
                effort='low'
            ))
    
    def _check_performance_issues(self, file_path: str, content: str, metrics: FileMetrics):
        """Check for performance anti-patterns."""
        # Check for inefficient nested loops
        nested_loop_count = len(re.findall(r'for\s+\w+\s+in\s+.*:\s*\n\s+for\s+\w+\s+in', content))
        if nested_loop_count > 2:
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='medium',
                category='performance',
                issue=f'{nested_loop_count} nested loops detected - O(n²) or worse complexity',
                suggestion='Consider vectorization with NumPy, use list comprehensions, or optimize algorithm. Profile to confirm bottleneck.',
                impact='Reduces time complexity and improves execution speed',
                effort='medium'
            ))
        
        # Check for repeated DB/API calls in loops
        if re.search(r'for\s+.*:\s*\n\s+.*\.(query|fetch|get|post|request)\s*\(', content):
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='high',
                category='performance',
                issue='Database/API calls inside loops detected',
                suggestion='Batch queries/requests outside loop. Use bulk operations or caching.',
                impact='Significantly reduces I/O overhead and latency',
                effort='medium'
            ))
        
        # Check for string concatenation in loops
        if re.search(r'for\s+.*:\s*\n\s+.*\+=\s*["\']', content):
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='low',
                category='performance',
                issue='String concatenation in loop (inefficient memory usage)',
                suggestion='Use list.append() and join() instead: parts = []; parts.append(x); result = "".join(parts)',
                impact='Reduces memory allocations and improves performance',
                effort='low'
            ))
    
    def _check_maintainability_issues(self, file_path: str, content: str, metrics: FileMetrics):
        """Check for maintainability issues."""
        # Check for missing docstrings
        if metrics.classes > 0 or metrics.functions > 5:
            lines = content.split('\n')
            has_docstrings = sum(1 for line in lines if '"""' in line or "'''" in line)
            if has_docstrings < metrics.classes + max(1, metrics.functions // 2):
                self.code_improvements.append(CodeImprovement(
                    file_path=file_path,
                    severity='low',
                    category='maintainability',
                    issue='Insufficient docstrings for classes/functions',
                    suggestion='Add docstrings following Google or NumPy style. Document parameters, returns, and raises.',
                    impact='Improves code understandability and maintainability',
                    effort='low'
                ))
        
        # Check for magic numbers
        magic_numbers = re.findall(r'(?<![a-zA-Z_])\d{4,}(?![a-zA-Z_])', content)
        if len(magic_numbers) > 5:
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='low',
                category='maintainability',
                issue=f'{len(magic_numbers)} magic numbers found',
                suggestion='Extract magic numbers to named constants at module level with descriptive names',
                impact='Improves code readability and maintainability',
                effort='low'
            ))
        
        # Check for excessive complexity
        if metrics.complexity_score > self.HIGH_COMPLEXITY_THRESHOLD:
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='medium',
                category='maintainability',
                issue=f'High complexity score ({metrics.complexity_score})',
                suggestion='Refactor into smaller functions using Extract Method pattern. Apply Single Responsibility Principle.',
                impact='Reduces cognitive load and improves testability',
                effort='high'
            ))
        
        # Check for long files
        if metrics.lines > self.VERY_LARGE_FILE_LINES:
            self.code_improvements.append(CodeImprovement(
                file_path=file_path,
                severity='high',
                category='maintainability',
                issue=f'Very large file ({metrics.lines} lines)',
                suggestion='Split into multiple focused modules. Group related functionality and extract to separate files.',
                impact='Improves code organization and navigability',
                effort='high'
            ))
    
    def _check_ml_best_practices(self, file_path: str, content: str, metrics: FileMetrics):
        """Check ML/RL specific best practices."""
        # Check for model versioning
        if any(term in content.lower() for term in ['train', 'fit', 'model']):
            if 'version' not in content.lower() and 'versioning' not in content.lower():
                self.code_improvements.append(CodeImprovement(
                    file_path=file_path,
                    severity='medium',
                    category='ml_best_practice',
                    issue='ML model lacks versioning',
                    suggestion='Implement model versioning with semantic versioning. Track model metadata, hyperparameters, and training data version.',
                    impact='Enables model reproducibility and rollback capability',
                    effort='medium'
                ))
        
        # Check for data validation in feature pipeline
        if 'feature' in file_path.lower() or 'pipeline' in file_path.lower():
            if 'validate' not in content.lower() and 'check' not in content.lower():
                self.code_improvements.append(CodeImprovement(
                    file_path=file_path,
                    severity='medium',
                    category='ml_best_practice',
                    issue='Missing data validation in feature pipeline',
                    suggestion='Add input validation: check for NaN, inf, data types, value ranges. Use assertions or dedicated validation functions.',
                    impact='Prevents model failures from bad input data',
                    effort='medium'
                ))
        
        # Check for model monitoring
        if any(term in content.lower() for term in ['predict', 'inference']):
            if 'monitor' not in content.lower() and 'metric' not in content.lower():
                self.code_improvements.append(CodeImprovement(
                    file_path=file_path,
                    severity='medium',
                    category='ml_best_practice',
                    issue='Missing prediction monitoring',
                    suggestion='Add monitoring for prediction latency, confidence distributions, and data drift. Log predictions for analysis.',
                    impact='Enables detection of model degradation and drift',
                    effort='medium'
                ))
        
        # Check for RL safety mechanisms
        if 'rl' in file_path.lower() or any(term in content.lower() for term in ['q-learning', 'policy', 'reward']):
            if 'constraint' not in content.lower() and 'safety' not in content.lower() and 'clip' not in content.lower():
                self.code_improvements.append(CodeImprovement(
                    file_path=file_path,
                    severity='high',
                    category='ml_best_practice',
                    issue='RL agent lacks safety constraints',
                    suggestion='Implement safety constraints: action space clipping, reward normalization, exploration limits, and fail-safe mechanisms.',
                    impact='Prevents dangerous actions in production trading',
                    effort='high'
                ))
    
    def _assess_future_readiness(self):
        """Assess system's readiness for future expansion."""
        # Extensibility assessment
        extensibility_score = self._assess_extensibility()
        
        # Scalability assessment  
        scalability_score = self._assess_scalability()
        
        # ML/RL maturity assessment
        ml_maturity_score = self._assess_ml_maturity()
        
        # Documentation quality
        doc_quality_score = self._assess_documentation()
        
        # Test coverage estimate
        test_coverage_score = self._assess_test_coverage()
        
        self.future_readiness = [
            extensibility_score,
            scalability_score,
            ml_maturity_score,
            doc_quality_score,
            test_coverage_score
        ]
    
    def _assess_extensibility(self) -> FutureReadinessMetric:
        """Assess code extensibility."""
        # Count base classes and interfaces
        base_classes = sum(1 for m in self.file_metrics.values() 
                          if any('base' in imp.lower() or 'abc' in imp.lower() for imp in m.imports))
        
        # Check for factory patterns
        factories = sum(1 for m in self.file_metrics.values() if 'factory' in m.path.lower())
        
        # Check for plugin architecture
        plugin_files = sum(1 for m in self.file_metrics.values() 
                          if 'plugin' in m.path.lower() or 'loader' in m.path.lower())
        
        total_modules = len(self.module_metrics)
        score = min(10, int(
            (base_classes / max(1, total_modules) * 5) +
            (factories / max(1, total_modules) * 10) +
            (plugin_files / max(1, total_modules) * 10)
        ))
        
        recommendations = []
        if score < 5:
            recommendations.append("Implement more base classes and abstract interfaces")
            recommendations.append("Add factory patterns for component creation")
            recommendations.append("Consider plugin architecture for strategy/indicator extensibility")
        elif score < 8:
            recommendations.append("Enhance existing patterns with better documentation")
            recommendations.append("Add more extension points for future features")
        
        return FutureReadinessMetric(
            aspect='Extensibility',
            score=score,
            assessment=f"{'Excellent' if score >= 8 else 'Good' if score >= 6 else 'Needs Improvement'}",
            recommendations=recommendations
        )
    
    def _assess_scalability(self) -> FutureReadinessMetric:
        """Assess system scalability."""
        # Check for async/await usage
        async_files = sum(1 for m in self.file_metrics.values() 
                         if any('async' in imp or 'asyncio' in imp for imp in m.imports))
        
        # Check for caching
        cache_files = sum(1 for m in self.file_metrics.values() 
                         if 'cache' in m.path.lower() or any('cache' in imp.lower() for imp in m.imports))
        
        # Check for connection pooling
        pooling_files = sum(1 for m in self.file_metrics.values() 
                           if 'pool' in m.path.lower())
        
        total_files = len(self.file_metrics)
        score = min(10, int(
            (async_files / max(1, total_files) * 30) +
            (cache_files / max(1, total_files) * 20) +
            (pooling_files / max(1, total_files) * 15)
        ))
        
        recommendations = []
        if score < 5:
            recommendations.append("Implement async/await for I/O bound operations")
            recommendations.append("Add caching layer for expensive computations")
            recommendations.append("Consider connection pooling for database/API access")
        elif score < 8:
            recommendations.append("Optimize existing async patterns")
            recommendations.append("Expand caching to more components")
            recommendations.append("Profile and optimize bottlenecks")
        
        return FutureReadinessMetric(
            aspect='Scalability',
            score=score,
            assessment=f"{'Excellent' if score >= 8 else 'Good' if score >= 6 else 'Needs Improvement'}",
            recommendations=recommendations
        )
    
    def _assess_ml_maturity(self) -> FutureReadinessMetric:
        """Assess ML/RL system maturity."""
        ml_files_count = len([f for f in self.file_metrics.values() if f.is_ml_component])
        
        # Check for MLOps components
        has_versioning = any('version' in m.path.lower() or 'registry' in m.path.lower() 
                            for m in self.file_metrics.values())
        has_monitoring = any('drift' in m.path.lower() or 'monitor' in m.path.lower() 
                            for m in self.file_metrics.values())
        has_training = any('train' in m.path.lower() for m in self.file_metrics.values())
        has_validation = any('valid' in m.path.lower() or 'test' in m.path.lower() 
                            for m in self.file_metrics.values())
        
        score = min(10, int(
            (ml_files_count / max(1, len(self.file_metrics)) * 20) +
            (2 if has_versioning else 0) +
            (2 if has_monitoring else 0) +
            (2 if has_training else 0) +
            (2 if has_validation else 0)
        ))
        
        recommendations = []
        if not has_versioning:
            recommendations.append("Implement model versioning and registry")
        if not has_monitoring:
            recommendations.append("Add model monitoring and drift detection")
        if not has_training:
            recommendations.append("Set up automated retraining pipelines")
        if not has_validation:
            recommendations.append("Add comprehensive model validation")
        if score >= 8:
            recommendations.append("Consider A/B testing framework for model comparison")
            recommendations.append("Implement feature store for consistent feature engineering")
        
        return FutureReadinessMetric(
            aspect='ML/RL Maturity',
            score=score,
            assessment=f"{'Excellent' if score >= 8 else 'Good' if score >= 6 else 'Developing'}",
            recommendations=recommendations
        )
    
    def _assess_documentation(self) -> FutureReadinessMetric:
        """Assess documentation quality."""
        # Count documentation files
        doc_patterns = ['.md', 'README', 'GUIDE', 'MANUAL']
        doc_files = []
        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for file in files:
                if any(pattern in file.upper() for pattern in doc_patterns):
                    doc_files.append(file)
        
        # Count docstrings in code
        total_docstrings = 0
        for metrics in self.file_metrics.values():
            try:
                with open(self.root / metrics.path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    total_docstrings += content.count('"""') + content.count("'''")
            except:
                pass
        
        avg_docstrings_per_file = total_docstrings / max(1, len(self.file_metrics))
        
        score = min(10, int(
            (len(doc_files) / 10 * 5) +
            (min(avg_docstrings_per_file, 10) / 10 * 5)
        ))
        
        recommendations = []
        if score < 5:
            recommendations.append("Add comprehensive README files for each major module")
            recommendations.append("Document all public APIs with docstrings")
            recommendations.append("Create architecture documentation")
        elif score < 8:
            recommendations.append("Add examples and tutorials")
            recommendations.append("Document design decisions and patterns")
            recommendations.append("Create troubleshooting guides")
        
        return FutureReadinessMetric(
            aspect='Documentation Quality',
            score=score,
            assessment=f"{'Excellent' if score >= 8 else 'Good' if score >= 6 else 'Needs Improvement'}",
            recommendations=recommendations
        )
    
    def _assess_test_coverage(self) -> FutureReadinessMetric:
        """Assess test coverage."""
        test_files = [f for f in self.file_metrics.values() if 'test' in f.path.lower()]
        test_lines = sum(f.lines for f in test_files)
        code_lines = sum(f.lines for f in self.file_metrics.values() if 'test' not in f.path.lower())
        
        # Estimate coverage based on test-to-code ratio
        coverage_ratio = test_lines / max(1, code_lines)
        score = min(10, int(coverage_ratio * 30))  # Rough heuristic
        
        recommendations = []
        if score < 5:
            recommendations.append("Add unit tests for critical components")
            recommendations.append("Implement integration tests for main workflows")
            recommendations.append("Set up CI/CD with automated testing")
        elif score < 8:
            recommendations.append("Expand test coverage to 80%+")
            recommendations.append("Add property-based testing for complex logic")
            recommendations.append("Implement end-to-end tests")
        
        return FutureReadinessMetric(
            aspect='Test Coverage',
            score=score,
            assessment=f"{'Excellent' if score >= 8 else 'Good' if score >= 6 else 'Insufficient'}",
            recommendations=recommendations
        )
    
    def _format_code_improvements(self) -> Dict:
        """Format code improvements for report."""
        # Group by severity
        by_severity = defaultdict(list)
        for imp in self.code_improvements:
            by_severity[imp.severity].append(asdict(imp))
        
        # Group by category
        by_category = defaultdict(list)
        for imp in self.code_improvements:
            by_category[imp.category].append(asdict(imp))
        
        # Count by effort
        effort_counts = defaultdict(int)
        for imp in self.code_improvements:
            effort_counts[imp.effort] += 1
        
        return {
            'total_suggestions': len(self.code_improvements),
            'by_severity': {
                'critical': len(by_severity['critical']),
                'high': len(by_severity['high']),
                'medium': len(by_severity['medium']),
                'low': len(by_severity['low']),
                'info': len(by_severity['info'])
            },
            'by_category': {
                'security': len(by_category['security']),
                'performance': len(by_category['performance']),
                'maintainability': len(by_category['maintainability']),
                'extensibility': len(by_category['extensibility']),
                'ml_best_practice': len(by_category['ml_best_practice'])
            },
            'by_effort': dict(effort_counts),
            'details': {
                'critical': by_severity['critical'][:10],  # Top 10 critical
                'high': by_severity['high'][:10],  # Top 10 high
                'medium': by_severity['medium'][:5],  # Top 5 medium
                'all': list(by_severity.values())  # All grouped
            }
        }
    
    def _format_future_readiness(self) -> Dict:
        """Format future readiness assessment for report."""
        return {
            'overall_score': sum(m.score for m in self.future_readiness) / max(1, len(self.future_readiness)),
            'metrics': [asdict(m) for m in self.future_readiness],
            'summary': self._generate_readiness_summary()
        }
    
    def _generate_readiness_summary(self) -> str:
        """Generate overall readiness summary."""
        avg_score = sum(m.score for m in self.future_readiness) / max(1, len(self.future_readiness))
        
        if avg_score >= 8:
            return "System is EXCELLENT for future expansion with strong foundations"
        elif avg_score >= 6:
            return "System is GOOD for future expansion with some areas needing attention"
        elif avg_score >= 4:
            return "System is ADEQUATE but requires improvements for robust expansion"
        else:
            return "System needs SIGNIFICANT improvements before major expansion"
    
    def print_summary(self, report: Dict):
        """Print analysis summary to console."""
        print("\n" + "="*70)
        print("📊 CTHULU CODEBASE ANALYSIS SUMMARY")
        print("="*70)
        
        summary = report['summary']
        print(f"\n📈 Overall Metrics:")
        print(f"   Total Files: {summary['total_files']}")
        print(f"   Total Lines: {summary['total_lines']:,}")
        print(f"   Total Functions: {summary['total_functions']:,}")
        print(f"   Total Classes: {summary['total_classes']:,}")
        print(f"   Total Modules: {summary['total_modules']}")
        
        print(f"\n⚠️  Issues Detected:")
        print(f"   Critical: {summary['critical_issues']}")
        print(f"   Warnings: {summary['warning_issues']}")
        
        # ML/RL Analysis
        if 'ml_analysis' in report:
            ml = report['ml_analysis']
            print(f"\n🤖 ML/RL Components:")
            print(f"   ML Files: {ml['summary']['total_ml_files']}")
            print(f"   ML Lines: {ml['summary']['total_ml_lines']:,}")
            print(f"   ML Functions: {ml['summary']['total_ml_functions']:,}")
            if ml['summary']['ml_architectures']:
                print(f"   Architectures: {', '.join(ml['summary']['ml_architectures'])}")
            if ml['summary']['training_capabilities']:
                print(f"   Capabilities: {', '.join(ml['summary']['training_capabilities'])}")
            print(f"\n   Implementation Status:")
            print(f"     ✅ Implemented: {ml['implementation_status']['implemented']}")
            print(f"     🔶 Partial: {ml['implementation_status']['partial']}")
            print(f"     ⬜ Stub: {ml['implementation_status']['stub']}")
            
            # List components by type
            if ml['components_by_type']:
                print(f"\n   Components by Type:")
                for comp_type, components in ml['components_by_type'].items():
                    print(f"     {comp_type}: {len(components)} files")
        
        if report['top_issues']['critical']:
            print(f"\n🔴 Top Critical Issues:")
            for issue in report['top_issues']['critical'][:5]:
                print(f"   • {issue['file']}")
                print(f"     {issue['issue']}")
        
        print(f"\n📏 Largest Files:")
        for f in report['largest_files'][:5]:
            print(f"   • {f['path']}: {f['lines']:,} lines, {f['functions']} functions")
        
        print(f"\n🧠 Most Complex Files:")
        for f in report['most_complex_files'][:5]:
            print(f"   • {f['path']}: complexity {f['complexity']}")
        
        if report['recommendations']:
            print(f"\n💡 Recommendations:")
            for i, rec in enumerate(report['recommendations'], 1):
                print(f"   {i}. {rec}")
        
        # NEW: Code Improvements Summary
        if 'code_improvements' in report and report['code_improvements']['total_suggestions'] > 0:
            improvements = report['code_improvements']
            print(f"\n🔧 Code Improvement Suggestions:")
            print(f"   Total Suggestions: {improvements['total_suggestions']}")
            print(f"   By Severity:")
            print(f"     🔴 Critical: {improvements['by_severity']['critical']}")
            print(f"     🟠 High: {improvements['by_severity']['high']}")
            print(f"     🟡 Medium: {improvements['by_severity']['medium']}")
            print(f"     🟢 Low: {improvements['by_severity']['low']}")
            print(f"   By Category:")
            print(f"     🔒 Security: {improvements['by_category']['security']}")
            print(f"     ⚡ Performance: {improvements['by_category']['performance']}")
            print(f"     🛠️  Maintainability: {improvements['by_category']['maintainability']}")
            print(f"     🤖 ML Best Practices: {improvements['by_category']['ml_best_practice']}")
            
            # Show top critical improvements
            if improvements['details']['critical']:
                print(f"\n   Top Critical Improvements:")
                for imp in improvements['details']['critical'][:3]:
                    print(f"     • {imp['file_path']}")
                    print(f"       Issue: {imp['issue']}")
                    print(f"       Fix: {imp['suggestion'][:100]}...")
        
        # NEW: Future Readiness Assessment
        if 'future_readiness' in report:
            readiness = report['future_readiness']
            print(f"\n🚀 Future Readiness Assessment:")
            print(f"   Overall Score: {readiness['overall_score']:.1f}/10")
            print(f"   Summary: {readiness['summary']}")
            print(f"\n   Detailed Scores:")
            for metric in readiness['metrics']:
                score = metric['score']
                emoji = '🟢' if score >= 8 else '🟡' if score >= 6 else '🔴'
                print(f"     {emoji} {metric['aspect']}: {score}/10 - {metric['assessment']}")
                if metric['recommendations']:
                    print(f"        • {metric['recommendations'][0]}")
        
        print("\n" + "="*70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze Cthulu codebase for metrics and issues'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='codebase_analysis.json',
        help='Output JSON file path'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--root',
        type=str,
        default='.',
        help='Root directory to analyze'
    )
    
    args = parser.parse_args()
    
    # Run analysis
    analyzer = CodeAnalyzer(args.root)
    report = analyzer.analyze()
    
    # Print summary
    analyzer.print_summary(report)
    
    # Save to JSON
    with open(args.output, 'w') as f:
        # Convert sets to lists for JSON serialization
        def convert_sets(obj):
            if isinstance(obj, set):
                return list(obj)
            return obj
        
        json.dump(report, f, indent=2, default=convert_sets)
    
    print(f"\n💾 Full report saved to: {args.output}")
    print(f"📊 Use this data to update system_map.html with latest metrics")


if __name__ == '__main__':
    main()
