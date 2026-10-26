import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, Subject, interval } from 'rxjs';
import { map, catchError, switchMap, takeWhile } from 'rxjs/operators';

// Backend API configuration
const API_BASE_URL = 'http://127.0.0.1:5000/api';

export interface BacktestConfig {
  initial_capital: number;
  commission: number;
  slippage_pct: number;
  speed_mode: string;
  strategies: StrategyConfig[];
  data_source?: {
    csv_path?: string;
    csv_data?: string;
  };
}

export interface StrategyConfig {
  type: string;
  params: Record<string, any>;
}

export interface BacktestJob {
  job_id: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  config: BacktestConfig;
  progress: number;
  result?: any;
  error?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface OptimizationConfig {
  method: 'grid_search' | 'bayesian' | 'multi_objective';
  param_grid?: Record<string, any[]>;
  param_bounds?: Record<string, [number, number]>;
  objectives?: string[];
  objective?: string;
  max_iterations?: number;
  n_iterations?: number;
}

export interface SavedConfig {
  name: string;
  config: BacktestConfig;
  modified_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class BackendService {
  private http = inject(HttpClient);
  
  // WebSocket connection (we'll use polling for now, can upgrade to Socket.IO later)
  private progressSubject = new Subject<{job_id: string, progress: number, message: string}>();
  public progress$ = this.progressSubject.asObservable();
  
  // Connection status
  connectionStatus = signal<'connected' | 'disconnected' | 'error'>('disconnected');
  
  constructor() {
    this.checkConnection();
  }
  
  /**
   * Check if backend is available
   */
  async checkConnection(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      const healthy = response.ok;
      this.connectionStatus.set(healthy ? 'connected' : 'error');
      return healthy;
    } catch (error) {
      this.connectionStatus.set('error');
      return false;
    }
  }
  
  /**
   * Run a backtest on the backend
   */
  runBacktest(config: BacktestConfig): Observable<BacktestJob> {
    return this.http.post<{job_id: string, status: string, message: string}>(
      `${API_BASE_URL}/backtest/run`,
      config
    ).pipe(
      map(response => ({
        job_id: response.job_id,
        status: response.status as any,
        config: config,
        progress: 0
      })),
      catchError(error => {
        console.error('Backtest submission failed:', error);
        throw error;
      })
    );
  }
  
  /**
   * Get backtest job status
   */
  getJobStatus(jobId: string): Observable<BacktestJob> {
    return this.http.get<BacktestJob>(`${API_BASE_URL}/backtest/status/${jobId}`);
  }
  
  /**
   * Get backtest results
   */
  getJobResults(jobId: string): Observable<any> {
    return this.http.get<any>(`${API_BASE_URL}/backtest/results/${jobId}`);
  }
  
  /**
   * Poll job status until completion
   */
  pollJobUntilComplete(jobId: string): Observable<BacktestJob> {
    return interval(1000).pipe(
      switchMap(() => this.getJobStatus(jobId)),
      takeWhile(job => job.status === 'QUEUED' || job.status === 'RUNNING', true),
      map(job => {
        // Emit progress updates
        if (job.progress > 0) {
          this.progressSubject.next({
            job_id: jobId,
            progress: job.progress,
            message: `Progress: ${(job.progress * 100).toFixed(1)}%`
          });
        }
        return job;
      })
    );
  }
  
  /**
   * Run optimization
   */
  runOptimization(config: BacktestConfig, optConfig: OptimizationConfig): Observable<BacktestJob> {
    const payload = {
      ...config,
      optimization: optConfig
    };
    
    return this.http.post<{job_id: string, status: string, message: string}>(
      `${API_BASE_URL}/optimize`,
      payload
    ).pipe(
      map(response => ({
        job_id: response.job_id,
        status: response.status as any,
        config: config,
        progress: 0
      }))
    );
  }
  
  /**
   * List all backtest jobs
   */
  listJobs(): Observable<BacktestJob[]> {
    return this.http.get<BacktestJob[]>(`${API_BASE_URL}/backtest/jobs`);
  }
  
  /**
   * List saved configurations
   */
  listConfigs(): Observable<SavedConfig[]> {
    return this.http.get<SavedConfig[]>(`${API_BASE_URL}/configs`);
  }
  
  /**
   * Save a configuration
   */
  saveConfig(name: string, config: BacktestConfig): Observable<{message: string, name: string, path: string}> {
    return this.http.post<{message: string, name: string, path: string}>(
      `${API_BASE_URL}/configs`,
      { name, config }
    );
  }
  
  /**
   * Delete a configuration
   */
  deleteConfig(name: string): Observable<{message: string}> {
    return this.http.delete<{message: string}>(`${API_BASE_URL}/configs/${name}`);
  }
  
  /**
   * Upload CSV data for backtesting
   */
  uploadCsvData(csvContent: string): BacktestConfig {
    // Return a config with CSV data embedded
    return {
      initial_capital: 10000,
      commission: 0.0001,
      slippage_pct: 0.0002,
      speed_mode: 'fast',
      strategies: [],
      data_source: {
        csv_data: csvContent
      }
    };
  }
  
  /**
   * Convert local config to backend format
   */
  convertToBackendConfig(
    initialCapital: number,
    commission: number,
    slippage: number,
    fastMa: number,
    slowMa: number,
    csvData?: string
  ): BacktestConfig {
    return {
      initial_capital: initialCapital,
      commission: commission,
      slippage_pct: slippage,
      speed_mode: 'fast',
      strategies: [
        {
          type: 'ema_crossover',
          params: {
            fast_period: fastMa,
            slow_period: slowMa
          }
        }
      ],
      data_source: csvData ? { csv_data: csvData } : undefined
    };
  }
  
  /**
   * Convert backend results to local format
   */
  convertFromBackendResults(backendResults: any): any {
    // Transform backend results to match the UI's expected format
    return {
      metrics: {
        totalReturn: backendResults.total_return || 0,
        sharpeRatio: backendResults.sharpe_ratio || 0,
        maxDrawdown: backendResults.max_drawdown || 0,
        winRate: backendResults.win_rate || 0,
        profitFactor: backendResults.profit_factor || 0,
        totalTrades: backendResults.total_trades || 0,
        winningTrades: backendResults.winning_trades || 0,
        losingTrades: backendResults.losing_trades || 0,
        avgWin: backendResults.avg_win || 0,
        avgLoss: backendResults.avg_loss || 0,
        largestWin: backendResults.largest_win || 0,
        largestLoss: backendResults.largest_loss || 0
      },
      trades: backendResults.trades || [],
      equity: backendResults.equity_curve || [],
      drawdown: backendResults.drawdown_curve || []
    };
  }
}
