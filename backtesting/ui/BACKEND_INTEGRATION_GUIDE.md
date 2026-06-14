# Cthulu Backtesting UI - 
> 🔗 Backend Integration Guide

**Date**: 2026-01-06

---

## Overview

The Cthulu Backtesting UI is fully integrated with a Flask backend, supporting both **client-side** and **backend** execution modes with seamless switching.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Angular Frontend (UI)                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  app.component.ts                                      │ │
│  │  - Mode Toggle (Client/Backend)                        │ │
│  │  - Connection Status Indicator                         │ │
│  │  - Dual Execution Paths                                │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  backend.service.ts                                    │ │
│  │  - REST API Communication                              │ │
│  │  - Job Polling                                         │ │
│  │  - Data Conversion                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  simulation.service.ts                                 │ │
│  │  - Client-Side Backtesting                             │ │
│  │  - Local Optimization                                  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP REST API
                            │ (http://127.0.0.1:5000/api)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Flask Backend (Python)                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  ui_server.py                                          │ │
│  │  - REST API Endpoints                                  │ │
│  │  - Job Management                                      │ │
│  │  - WebSocket Support                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  engine.py                                             │ │
│  │  - Backtest Execution                                  │ │
│  │  - Strategy Simulation                                 │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  auto_optimizer.py                                     │ │
│  │  - Grid Search                                         │ │
│  │  - Bayesian Optimization                               │ │
│  │  - Multi-Objective Optimization                        │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  hektor_backtest.py                                    │ │
│  │  - Semantic Storage                                    │ │
│  │  - Pattern Matching                                    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Start the Backend

```bash
# Terminal 1 - Start Flask backend
cd C:\workspace\cthulu
python backtesting/ui_server.py

# Server will start on http://127.0.0.1:5000
```

### 2. Open the UI

```bash
# Open in browser
start backtesting/ui/index.html

# Or use a local server
cd backtesting/ui
python -m http.server 8080
# Then open http://localhost:8080
```

### 3. Verify Connection

- Look for the **green "Backend Connected"** indicator in the top-right
- If red, the UI will fall back to client-side mode
- Click the **mode toggle** to switch between Client/Backend modes

---

## API Integration

### Backend Service (`backend.service.ts`)

**Key Features**:
- REST API communication
- Job submission and polling
- Progress tracking
- Data format conversion
- Connection health checks

**Main Methods**:

```typescript
// Check backend availability
await backendService.checkConnection();

// Run backtest
backendService.runBacktest(config).subscribe(job => {
  // Poll for completion
  backendService.pollJobUntilComplete(job.job_id).subscribe(result => {
    console.log('Backtest complete:', result);
  });
});

// Run optimization
backendService.runOptimization(config, optConfig).subscribe(job => {
  // Handle optimization job
});

// List saved configurations
backendService.listConfigs().subscribe(configs => {
  console.log('Saved configs:', configs);
});
```

### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/backtest/run` | POST | Submit backtest |
| `/api/backtest/status/{id}` | GET | Get job status |
| `/api/backtest/results/{id}` | GET | Get results |
| `/api/backtest/jobs` | GET | List all jobs |
| `/api/configs` | GET | List configurations |
| `/api/configs` | POST | Save configuration |
| `/api/configs/{name}` | DELETE | Delete configuration |
| `/api/optimize` | POST | Run optimization |

---

## Execution Modes

### Client Mode (Default Fallback)

- Runs entirely in browser
- No backend required
- Fast for small datasets
- Limited by browser resources
- ⚠️ No Hektor integration
- ⚠️ No advanced optimization

**Use When**:
- Backend is unavailable
- Testing/development
- Small datasets (<1000 bars)
- Quick parameter testing

### Backend Mode (Recommended)

- Full Python backtesting engine
- Hektor vector database integration
- Advanced optimization algorithms
- Unlimited dataset size
- Parallel execution
- Pattern recognition
- ML training data export

**Use When**:
- Backend is running
- Large datasets (>1000 bars)
- Production optimization
- Hektor features needed
- Advanced analytics required

---

## Component Integration

### App Component (`app.component.integrated.ts`)

**New Features**:

1. **Connection Status Indicator**
   ```html
   <div class="flex items-center space-x-2">
     <i class="fa-solid fa-circle" 
        [class]="backendService.connectionStatus() === 'connected' ? 
                 'text-emerald-400' : 'text-red-400'"></i>
     <span>{{backendService.connectionStatus() === 'connected' ? 
            'Backend Connected' : 'Local Mode'}}</span>
   </div>
   ```

2. **Mode Toggle Button**
   ```html
   <button (click)="toggleMode()">
     <i class="fa-solid fa-server"></i>
     {{useBackend() ? 'Backend Mode' : 'Client Mode'}}
   </button>
   ```

3. **Job Status Display**
   ```html
   @if (isRunning()) {
     <div class="animate-pulse">
       <i class="fa-solid fa-spinner fa-spin"></i> Running...
       <p>Job ID: {{currentJobId()}}</p>
     </div>
   }
   ```

4. **Dual Execution Paths**
   ```typescript
   handleRun(config: ConfigData) {
     if (this.useBackend() && this.backendService.connectionStatus() === 'connected') {
       this.runOnBackend(config);
     } else {
       this.runLocally(config);
     }
   }
   ```

---

## Data Flow

### Client Mode Flow

```
User Input → Configuration Component
    ↓
App Component (handleRun)
    ↓
SimulationService.runBacktest()
    ↓
Results → Display Components
```

### Backend Mode Flow

```
User Input → Configuration Component
    ↓
App Component (handleRun)
    ↓
BackendService.runBacktest()
    ↓
Flask Backend (ui_server.py)
    ↓
BacktestEngine.run()
    ↓
Results → BackendService.pollJobUntilComplete()
    ↓
Convert Results → Display Components
```

---

## Configuration

### Backend Configuration

Edit `backtesting/ui_server.py`:

```python
class BacktestServer:
    def __init__(self, host: str = '127.0.0.1', port: int = 5000):
        self.host = host
        self.port = port
```

### CORS Configuration

The backend automatically enables CORS for the Angular frontend:

```python
from flask_cors import CORS
CORS(self.app)  # Enable CORS for all routes
```

### API Base URL

Edit `backtesting/ui/src/services/backend.service.ts`:

```typescript
const API_BASE_URL = 'http://127.0.0.1:5000/api';
```

---

## Testing

### Test Backend Connection

```bash
# Check health endpoint
curl http://127.0.0.1:5000/api/health

# Expected response:
# {"status": "healthy", "timestamp": "2026-01-06T..."}
```

### Test Backtest Submission

```bash
# Submit a test backtest
curl -X POST http://127.0.0.1:5000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "initial_capital": 10000,
    "commission": 0.0001,
    "slippage_pct": 0.0002,
    "speed_mode": "fast",
    "strategies": [{"type": "ema_crossover", "params": {"fast_period": 12, "slow_period": 26}}]
  }'

# Expected response:
# {"job_id": "...", "status": "QUEUED", "message": "Backtest queued successfully"}
```

### Test Job Status

```bash
# Check job status
curl http://127.0.0.1:5000/api/backtest/status/{job_id}
```

---

## Troubleshooting

### Backend Not Connecting

**Symptoms**: Red "Local Mode" indicator

**Solutions**:
1. Check if backend is running: `netstat -ano | findstr :5000`
2. Start backend: `python backtesting/ui_server.py`
3. Check firewall settings
4. Verify CORS is enabled

### CORS Errors

**Symptoms**: Console errors about CORS policy

**Solutions**:
1. Ensure `flask-cors` is installed: `pip install flask-cors`
2. Verify CORS is enabled in `ui_server.py`
3. Check browser console for specific errors

### Job Stuck in QUEUED

**Symptoms**: Job never progresses

**Solutions**:
1. Check backend logs
2. Verify data is being sent correctly
3. Check for errors in Flask console
4. Restart backend server

### Results Not Displaying

**Symptoms**: Backtest completes but no results shown

**Solutions**:
1. Check browser console for errors
2. Verify data conversion in `convertFromBackendResults()`
3. Check network tab for API responses
4. Ensure result format matches expected structure

---

## Performance

### Client Mode
- **Speed**: 1,000-5,000 bars/second
- **Memory**: Limited by browser (~2GB)
- **Optimization**: Basic grid search only

### Backend Mode
- **Speed**: 10,000+ bars/second
- **Memory**: System RAM available
- **Optimization**: Grid, Bayesian, Multi-objective
- **Parallel**: Multiple cores utilized

---

## Security

### API Security

Currently the API is **open** for local development. For production:

1. **Add Authentication**:
   ```python
   from flask_httpauth import HTTPBasicAuth
   auth = HTTPBasicAuth()
   
   @app.route('/api/backtest/run', methods=['POST'])
   @auth.login_required
   def run_backtest():
       # ...
   ```

2. **Enable HTTPS**:
   ```python
   app.run(ssl_context='adhoc')
   ```

3. **Rate Limiting**:
   ```python
   from flask_limiter import Limiter
   limiter = Limiter(app, default_limits=["100 per hour"])
   ```

---

## Deployment

### Development

```bash
# Backend
python backtesting/ui_server.py

# Frontend
# Open index.html in browser
```

### Production

```bash
# Backend with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 backtesting.ui_server:app

# Frontend with Nginx
# Serve static files from backtesting/ui/
```

---

## Next Steps

1. **WebSocket Integration**: Replace polling with real-time WebSocket updates
2. **Authentication**: Add user authentication for multi-user support
3. **Result Caching**: Cache results in backend for faster retrieval
4. **Advanced Charts**: Add more interactive D3.js visualizations
5. **Configuration Presets**: Save and load configuration presets
6. **Export Results**: Add CSV/JSON export functionality

---

## Integration Checklist

- [x] Backend service created (`backend.service.ts`)
- [x] App component updated with backend integration
- [x] Connection status indicator added
- [x] Mode toggle implemented
- [x] Dual execution paths (client/backend)
- [x] Job polling mechanism
- [x] Data format conversion
- [x] Error handling
- [x] Progress tracking
- [x] Configuration management API
- [x] Optimization support
- [x] Documentation complete

---

**To Use the Integrated Version**:
1. Rename `app.component.integrated.ts` to `app.component.ts`
2. Start backend: `python backtesting/ui_server.py`
3. Open UI: `backtesting/ui/index.html`
4. Toggle between Client/Backend modes as needed
