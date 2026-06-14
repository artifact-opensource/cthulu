# Cthulu System Map - User Guide

![](https://img.shields.io/badge/Version-1.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
![](https://img.shields.io/badge/Interactive-Yes-00FF00?style=for-the-badge&labelColor=0D1117)

---

## Overview

The **Cthulu System Map** is an interactive visualization tool that provides a comprehensive, real-time view of the entire Cthulu trading system architecture. It allows developers, auditors, and stakeholders to explore the system's components, dependencies, data flows, and potential issues through an intuitive, interactive interface.

## Features

### 🎯 Core Features

1. **Interactive Force-Directed Graph**
   - Drag and drop nodes to reorganize the view
   - Zoom in/out with mouse wheel or pinch gestures
   - Pan by clicking and dragging the background

2. **Detailed Component Information**
   - Hover over any node to see detailed metrics
   - View lines of code, function count, complexity
   - See dependencies and relationships
   - Identify issues and bottlenecks

3. **Smart Issue Detection**
   - Visual indicators (red badges) for components with issues
   - Automatic suggestions based on code analysis
   - Severity classification (Critical, High, Medium)

4. **Color-Coded Architecture**
   - Different colors for different component types
   - Visual distinction between critical and non-critical paths
   - Flow intensity visualization (high/medium/low)

5. **Search and Filter**
   - Quick search to find specific components
   - Auto-dim non-matching components
   - Highlight related connections

6. **Multiple View Modes**
   - Force-directed layout (default)
   - Tree layout
   - Radial layout

7. **Export Capabilities**
   - Export as SVG for documentation
   - High-quality vector graphics
   - Print-ready format

## Quick Start

### Opening the Map

1. **Local File:** Simply open `system_map.html` in a modern web browser (Chrome, Firefox, Edge, Safari)
2. **Web Server:** Host on any web server for team access
3. **Live Server:** Use VS Code Live Server extension for development

### Navigation

- **Zoom:** Mouse wheel or pinch gesture
- **Pan:** Click and drag background
- **Move Nodes:** Click and drag individual nodes
- **Reset View:** Click "Reset View" button
- **Expand:** Click "Expand All" to spread out the graph

## Component Types & Color Legend

| Color | Component Type | Examples |
|-------|---------------|----------|
| 🟢 Green (#00ff88) | Core Engine | Bootstrap, Trading Loop, Shutdown |
| 🔵 Blue (#00aaff) | Strategy/Indicators | EMA, RSI, Strategy Engine |
| 🔴 Red (#ff6b6b) | Risk/Position | Risk Evaluator, Position Manager |
| 🟠 Orange (#ffaa00) | Execution/Exit | Execution Engine, Exit Coordinator |
| 🟣 Purple (#9b59b6) | AI/ML (Cognition) | Cognition Engine, Regime Classifier |
| 🔷 Light Blue (#3498db) | Data/Persistence | Data Layer, Database |
| 🟢 Lime (#2ecc71) | Monitoring/UI | GUI, RPC Server, Metrics |
| 🔴 Bright Red (#e74c3c) | External/MT5 | MT5 Connector, News Feed |

## Understanding Node Sizes

Nodes are sized based on importance:
- **Largest (25px):** Critical path components
- **Large (22px):** Files > 1000 lines
- **Medium (18px):** Files > 500 lines
- **Small (15px):** Standard components

## Flow Types & Colors

Data flow connections are color-coded by intensity:

| Color | Flow Type | Description |
|-------|-----------|-------------|
| 🔴 Red (#ff0055) | High | Critical data paths, executed every loop |
| 🟠 Orange (#ffaa00) | Medium | Regular operations, frequent usage |
| 🔵 Blue (#00aaff) | Low | Occasional operations, non-critical |

High-flow connections use animated dashes to show active data movement.

## Interactive Features

### Hovering Over Nodes

When you hover over a node, a detailed tooltip appears showing:

1. **Component Name** - Full name of the module
2. **Description** - Purpose and functionality
3. **Metrics:**
   - Lines of code
   - Number of functions
   - Complexity rating (Low/Medium/High/Very High)
   - Critical path indicator (Yes/No)
4. **Dependencies** - List of components it depends on
5. **Issues** - Any detected problems (if applicable)

### Issue Indicators

Components with detected issues show:
- Red circular badge with issue count
- Detailed issue description in tooltip
- Listed in Smart Suggestions panel

### Search Functionality

The search box at the top allows you to:
1. Type component name (partial match supported)
2. Matching nodes remain at full opacity
3. Non-matching nodes dim to 20% opacity
4. Connected links also highlight/dim accordingly

### View Modes

**Force Layout (Default):**
- Natural organization based on relationships
- Nodes repel each other for clarity
- Optimal for exploring connections

**Tree Layout:**
- Hierarchical view from core to periphery
- Good for understanding dependency chains
- Tighter spacing

**Radial Layout:**
- Circular arrangement
- Core components in center
- Peripheral components on outside

## System Statistics Panel

Located in the top-right corner, shows:

- **Total Components:** Number of modules visualized (40)
- **Total Connections:** Number of data flow links (70+)
- **Lines of Code:** Total codebase size (69,512)
- **Functions:** Total function count (2,118)
- **Critical Issues:** Number of high-priority problems (3)

## Smart Suggestions Panel

Located in the bottom-right, automatically detects and displays:

1. **CRITICAL Issues:**
   - trading_loop.py refactoring needed (2,214 lines)
   - File too large and complex

2. **HIGH Priority:**
   - MT5 Connector circuit breaker missing
   - Single point of failure risk

3. **MEDIUM Priority:**
   - Test coverage expansion needed
   - Target: 85%+ for critical paths

## Component Details

### Core Components

**Bootstrap** - System initialization
- Initializes MT5 connection
- Loads configuration
- Sets up database
- Launches trading loop

**Trading Loop** - Main orchestration (⚠️ CRITICAL: Needs refactoring)
- 2,214 lines - too complex
- Coordinates all trading phases
- Executes every poll interval
- Critical path component

**Execution Engine** - Order management
- Submits orders to MT5
- Handles reconciliation
- Logs all trades
- High complexity

### AI/ML Components

**Cognition Engine** - Central AI orchestrator
- Coordinates all AI modules
- Provides intelligent signals
- Enhances trading decisions

**Entry Confluence** - Entry quality assessment (⚠️ WARNING: Large file)
- 1,466 lines - needs splitting
- Evaluates entry timing
- Multi-factor analysis
- Critical for trade quality

**Chart Manager** - Visual reasoning (⚠️ WARNING: Large file)
- 1,500 lines - needs splitting
- Pattern recognition
- Support/resistance detection

### Risk Components

**Risk Evaluator** - Pre-trade approval
- Position sizing
- Risk limit checks
- Approval/rejection decisions
- High complexity

**Account Manager** - Adaptive sizing
- Phase-based sizing
- Account growth tracking
- Dynamic adjustments

### Strategy Components

**Strategy Engine** - Dynamic selection
- Monitors multiple strategies
- Performance-based switching
- Regime adaptation

**Individual Strategies:**
- EMA Crossover (246 lines)
- RSI Reversal (165 lines)
- Scalping (243 lines)
- Plus 4 more...

## Use Cases

### 1. System Audit

**Goal:** Identify bottlenecks and issues

**Steps:**
1. Open the map
2. Look for red issue badges
3. Check Smart Suggestions panel
4. Hover over flagged components
5. Review complexity ratings
6. Identify oversized modules (>1000 lines)

**Key Indicators:**
- Components with "Very High" complexity
- Large file sizes (>1000 lines)
- High number of dependencies
- Critical path components with issues

### 2. Understanding Data Flow

**Goal:** Trace how data moves through the system

**Steps:**
1. Start at MT5 Connector (external data source)
2. Follow connections to Data Layer
3. Trace to Indicators
4. See how it flows to Strategies
5. Follow through Risk → Execution → Position
6. End at Database persistence

**Color Key:**
- Red lines = high-frequency data (every loop)
- Orange lines = regular operations
- Blue lines = occasional operations

### 3. Dependency Analysis

**Goal:** Understand component relationships

**Steps:**
1. Search for a component
2. Observe its connections
3. Hover to see listed dependencies
4. Click and drag to isolate it
5. Examine upstream and downstream components

### 4. Refactoring Planning

**Goal:** Identify what to refactor first

**Priority Order:**
1. Look for "Very High" complexity components
2. Find files > 1500 lines
3. Identify high-dependency components
4. Check critical path components with issues

**Current Refactoring Targets:**
- trading_loop.py (2,214 lines) - CRITICAL
- entry_confluence.py (1,466 lines) - HIGH
- chart_manager.py (1,500 lines) - HIGH

### 5. New Developer Onboarding

**Goal:** Quickly understand system architecture

**Exploration Path:**
1. Start with Core Engine components (green)
2. Understand trading loop flow
3. Explore Strategy system (blue)
4. Learn about Risk management (red)
5. Understand AI/ML layer (purple)
6. Review monitoring and UI (lime green)

### 6. Performance Optimization

**Goal:** Find performance bottlenecks

**Focus Areas:**
1. Components with high complexity
2. High-frequency data flows (red lines)
3. Critical path components
4. Large file sizes (potential for optimization)

**Current Bottlenecks:**
- Indicator recalculation (every loop)
- Database writes (synchronous)
- Configuration loading (startup)

### 7. Security Review

**Goal:** Identify security-sensitive components

**Key Components:**
1. MT5 Connector (credentials, API)
2. RPC Server (authentication, validation)
3. Database (SQL injection risk)
4. Execution Engine (order validation)

### 8. Testing Strategy

**Goal:** Prioritize test coverage

**Test Priority:**
1. Critical path components (marked as critical)
2. High complexity components
3. Components with high dependencies
4. External interfaces (MT5, Database)
5. Risk and execution layers

## Advanced Tips

### 1. Isolating Subsystems

To focus on a specific subsystem:
1. Use search to filter components
2. Drag related nodes together
3. Click "Expand All" to spread them out
4. Zoom in on the area of interest

### 2. Comparing Component Complexity

Hover over multiple components and compare:
- Lines of code
- Number of functions
- Complexity rating
- Critical path status

### 3. Tracing Critical Paths

Critical path components have:
- Larger node size (25px radius)
- Bold text labels
- High-flow connections (red lines)
- "Critical: Yes" in tooltip

Follow these to understand the most important execution paths.

### 4. Finding Related Components

When hovering over a node:
1. Note the dependencies list
2. Search for each dependency
3. Trace the connections
4. Build a mental model of the subsystem

### 5. Export for Documentation

To export the map:
1. Arrange nodes as desired
2. Zoom to appropriate level
3. Click "Export" button
4. Save SVG file
5. Use in documentation or presentations

## Technical Details

### Technology Stack

- **D3.js v7** - Data visualization and force simulation
- **HTML5 Canvas/SVG** - High-performance rendering
- **Vanilla JavaScript** - No framework dependencies
- **CSS3** - Modern styling and animations

### Performance

- Optimized for 50+ nodes and 100+ links
- Smooth 60 FPS force simulation
- Efficient DOM updates
- Minimal memory footprint

### Browser Compatibility

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

### Customization

The system data is embedded in JavaScript at the bottom of the HTML file. To update:

1. Open `system_map.html` in a text editor
2. Find the `systemData` object
3. Modify nodes or links as needed
4. Save and refresh in browser

**Node Structure:**
```javascript
{
    id: "component_id",
    name: "Display Name",
    group: "component_group",
    type: "Component Type",
    lines: 1234,
    functions: 56,
    issues: 0,
    description: "Detailed description",
    dependencies: ["dep1", "dep2"],
    complexity: "Medium",
    criticalPath: true
}
```

**Link Structure:**
```javascript
{
    source: "source_id",
    target: "target_id",
    type: "connection_type",
    flow: "high|medium|low"
}
```

## Troubleshooting

### Map Not Loading

**Issue:** Blank page or errors
**Solution:**
- Check browser console for errors
- Ensure D3.js CDN is accessible
- Try a different browser
- Check file permissions

### Performance Issues

**Issue:** Slow or choppy animation
**Solution:**
- Close other browser tabs
- Disable browser extensions
- Use a more powerful device
- Reduce number of visible nodes (use search)

### Tooltip Not Appearing

**Issue:** Hover doesn't show information
**Solution:**
- Ensure JavaScript is enabled
- Check browser console for errors
- Try refreshing the page
- Hover directly over node circle

### Export Not Working

**Issue:** Export button doesn't download
**Solution:**
- Check browser download settings
- Allow pop-ups for the page
- Try right-click → "Save As" on SVG
- Use browser developer tools to debug

## Best Practices

### 1. Regular Updates

Update the map when:
- New components are added
- Dependencies change
- Complexity metrics change
- Issues are resolved or new ones found

### 2. Share with Team

Make the map accessible:
- Host on internal web server
- Include in onboarding documentation
- Reference in code review discussions
- Use in architecture meetings

### 3. Use in Meetings

The map is excellent for:
- Architecture discussions
- Sprint planning (identifying work areas)
- Technical debt prioritization
- New feature planning (impact analysis)

### 4. Document Changes

When making architectural changes:
1. Screenshot the before state
2. Update the system data
3. Screenshot the after state
4. Document the changes in commits

### 5. Combine with Other Tools

Use alongside:
- SYSTEM_AUDIT.md for detailed analysis
- Code coverage reports
- Performance profiling data
- Security scan results

## Future Enhancements

Potential improvements for future versions:

1. **Real-time Metrics**
   - Live data from running system
   - CPU/memory usage per component
   - Request/response times

2. **3D Visualization**
   - Three.js integration
   - Z-axis for hierarchy levels
   - Immersive exploration

3. **Historical View**
   - Time-travel through architecture changes
   - Compare different versions
   - Evolution visualization

4. **Integration Testing**
   - Show test coverage per component
   - Highlight untested paths
   - Test failure indicators

5. **Performance Profiling**
   - Hot path highlighting
   - Execution time per component
   - Bottleneck detection

6. **AI-Powered Suggestions**
   - Machine learning for issue prediction
   - Automatic refactoring suggestions
   - Risk scoring

7. **Collaborative Features**
   - Multi-user annotations
   - Comments and discussions
   - Change proposals

## Support

For issues, questions, or contributions:

- **GitHub Issues:** Report bugs or request features
- **Documentation:** See SYSTEM_AUDIT.md for detailed analysis
- **Code:** system_map.html source is well-commented

---

## Quick Reference Card

| Action | Method |
|--------|--------|
| Zoom In/Out | Mouse wheel or pinch |
| Pan View | Drag background |
| Move Node | Drag node |
| View Details | Hover over node |
| Search | Type in search box |
| Reset View | Click "Reset View" |
| Expand Graph | Click "Expand All" |
| Export | Click "Export" |
| Change Layout | Click view toggle buttons |

| Color | Meaning |
|-------|---------|
| 🟢 Green | Core Engine |
| 🔵 Blue | Strategies/Indicators |
| 🔴 Red | Risk/Position |
| 🟠 Orange | Execution/Exit |
| 🟣 Purple | AI/ML |

| Badge | Meaning |
|-------|---------|
| 🔴 Red Circle | Issues detected |
| Large Node | Critical path |
| Animated Line | High data flow |

---

**Version:** 1.0  
**Last Updated:** 2026-01-12  
**Status:** Production Ready
