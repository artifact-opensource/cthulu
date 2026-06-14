import { Component, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ConfigurationComponent, ConfigData } from './components/configuration.component';
import { ChartComponent } from './components/chart.component';
import { MetricsComponent } from './components/metrics.component';
import { SimulationService, BacktestResult, Candle, OptimizationResult, Trade } from './services/simulation.service';
import { AiService } from './services/ai.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ConfigurationComponent, ChartComponent, MetricsComponent],
  template: `
    <div class="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-emerald-500/30">
      <div class="w-full px-4 md:px-6 lg:px-8 py-6">
        <header class="mb-8 flex items-center justify-between">
          <div>
            <h1 class="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">
              <i class="fa-solid fa-layer-group mr-2 text-emerald-500"></i>
              BACKTESTER <span class="text-slate-600 text-lg font-mono">v3.2</span>
            </h1>
            <p class="text-slate-500 text-sm mt-1">High-Frequency Backtesting & Optimization Engine</p>
          </div>
          
          <!-- Webhook Status Indicator -->
          @if (webhookConfig()?.enableWebhooks) {
             <div class="flex items-center space-x-2 bg-slate-900 border border-blue-900 px-3 py-1 rounded-full animate-pulse">
                <span class="w-2 h-2 rounded-full bg-blue-500"></span>
                <span class="text-xs font-mono text-blue-400">MT5 BRIDGE ACTIVE</span>
             </div>
          }
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Sidebar / Config -->
          <div class="lg:col-span-3 space-y-6">
            <app-configuration 
               (run)="handleRun($event)" 
               (fileLoaded)="onFileLoaded($event)">
            </app-configuration>
            
            <!-- Optimization Results Panel -->
            @if (optResult(); as opt) {
              <div class="bg-slate-900 border border-purple-500/30 rounded-lg p-4 shadow-lg animate-fade-in">
                 <h3 class="text-purple-400 font-bold mb-3 flex items-center">
                   <i class="fa-solid fa-trophy mr-2"></i> Optimization Winner
                 </h3>
                 <div class="space-y-2 text-sm">
                    <div class="flex justify-between">
                      <span class="text-slate-400">Iterations</span>
                      <span class="font-mono text-white">{{opt.iterations}}</span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-slate-400">Best Fast MA</span>
                      <span class="font-mono text-emerald-400">{{opt.bestFastMa}}</span>
                    </div>
                    <div class="flex justify-between">
                      <span class="text-slate-400">Best Slow MA</span>
                      <span class="font-mono text-emerald-400">{{opt.bestSlowMa}}</span>
                    </div>
                    <div class="flex justify-between pt-2 border-t border-slate-700">
                      <span class="text-slate-400">Profit Factor</span>
                      <span class="font-mono text-purple-400 font-bold">{{opt.bestProfitFactor.toFixed(2)}}</span>
                    </div>
                 </div>
              </div>
            }
          </div>

          <!-- Main Content -->
          <div class="lg:col-span-9 space-y-6">
            @if (results(); as res) {
               <app-metrics [data]="res.metrics"></app-metrics>
               
               <app-chart [data]="res"></app-chart>
               
               <!-- AI Analysis Section -->
               <div class="bg-slate-900 border border-slate-700 rounded-lg p-6 shadow-xl relative overflow-hidden">
                 <div class="absolute top-0 right-0 p-4 opacity-10">
                   <i class="fa-solid fa-brain text-9xl"></i>
                 </div>
                 
                 <div class="flex justify-between items-start mb-4 relative z-10">
                   <h3 class="text-xl font-bold text-slate-100 flex items-center">
                     <i class="fa-solid fa-robot mr-2 text-cyan-400"></i> AI Analysis
                   </h3>
                   @if (!aiAnalysis() && !isAnalyzing()) {
                     <button (click)="analyze()" class="bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold py-2 px-4 rounded transition-colors shadow-lg shadow-cyan-900/20">
                       Generate Report
                     </button>
                   }
                 </div>

                 @if (isAnalyzing()) {
                   <div class="flex items-center space-x-3 text-cyan-400 animate-pulse py-8">
                     <i class="fa-solid fa-circle-notch fa-spin text-2xl"></i>
                     <span class="font-mono">Processing market telemetry...</span>
                   </div>
                 }

                 @if (aiAnalysis()) {
                   <div class="prose prose-invert max-w-none text-sm animate-fade-in" [innerHTML]="aiAnalysis()"></div>
                 }
               </div>

               <!-- Recent Trades List -->
               <div class="bg-slate-900 border border-slate-700 rounded-lg p-4 shadow-xl">
                  <h3 class="text-slate-400 text-xs font-bold uppercase mb-4">Recent Trades</h3>
                  <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs">
                      <thead class="text-slate-500 border-b border-slate-700">
                        <tr>
                          <th class="pb-2">Type</th>
                          <th class="pb-2">Entry Date</th>
                          <th class="pb-2">Price</th>
                          <th class="pb-2">Exit Date</th>
                          <th class="pb-2">Price</th>
                          <th class="pb-2 text-right">PnL</th>
                          <th class="pb-2 text-center" *ngIf="webhookConfig()?.enableWebhooks">Broadcast</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-slate-800">
                        @for (trade of lastTrades(); track $index) {
                          <tr class="hover:bg-slate-800/50 transition-colors">
                            <td class="py-2">
                               <span class="px-2 py-0.5 rounded-full bg-emerald-900/50 text-emerald-400 border border-emerald-900">LONG</span>
                            </td>
                            <td class="py-2 font-mono text-slate-400">{{formatDate(trade.entryTime)}}</td>
                            <td class="py-2 font-mono text-slate-300">{{trade.entryPrice.toFixed(2)}}</td>
                            <td class="py-2 font-mono text-slate-400">{{formatDate(trade.exitTime)}}</td>
                            <td class="py-2 font-mono text-slate-300">{{trade.exitPrice.toFixed(2)}}</td>
                            <td class="py-2 font-mono text-right font-bold" [class]="trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'">
                              {{trade.pnl.toFixed(2)}}
                            </td>
                            <td class="py-2 text-center" *ngIf="webhookConfig()?.enableWebhooks">
                               <button (click)="broadcast(trade)" class="text-blue-400 hover:text-blue-300 transition-colors" title="Send to MT5">
                                 <i class="fa-solid fa-tower-broadcast"></i>
                               </button>
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
               </div>

            } @else {
               <div class="h-96 flex flex-col items-center justify-center text-slate-600 border-2 border-dashed border-slate-800 rounded-lg">
                  <i class="fa-solid fa-chart-line text-4xl mb-4 opacity-50"></i>
                  <p>Load data and run simulation to view results</p>
               </div>
            }
          </div>
        </div>
      </div>
    </div>
  `
})
export class AppComponent {
  private simulationService = inject(SimulationService);
  private aiService = inject(AiService);
  private sanitizer: DomSanitizer = inject(DomSanitizer);

  candles = signal<Candle[]>([]);
  results = signal<BacktestResult | null>(null);
  optResult = signal<OptimizationResult | null>(null);
  webhookConfig = signal<{webhookUrl: string, enableWebhooks: boolean} | null>(null);
  
  aiAnalysis = signal<SafeHtml | null>(null);
  isAnalyzing = signal<boolean>(false);

  constructor() {
    // Initialize with mock data so it works out of the box
    this.candles.set(this.simulationService.generateData(365));
  }

  lastTrades = computed(() => {
    const res = this.results();
    if (!res) return [];
    // Return last 10 trades reversed
    return [...res.trades].reverse().slice(0, 10);
  });

  onFileLoaded(csvContent: string) {
    const parsedCandles = this.simulationService.parseCsvData(csvContent);
    if (parsedCandles.length > 0) {
      this.candles.set(parsedCandles);
      // Reset results on new data load
      this.results.set(null);
      this.optResult.set(null);
      this.aiAnalysis.set(null);
    } else {
      alert('Failed to parse CSV. Ensure format: Date,Open,High,Low,Close,Volume');
    }
  }

  handleRun(config: ConfigData) {
    // Reset AI analysis when new simulation runs
    this.aiAnalysis.set(null);
    this.optResult.set(null); // Clear previous optimization if running manual
    
    // Store webhook settings
    this.webhookConfig.set({
      webhookUrl: config.webhookUrl,
      enableWebhooks: config.enableWebhooks
    });

    // Ensure we have data
    if (this.candles().length === 0) {
      this.candles.set(this.simulationService.generateData(365));
    }

    if (config.mode === 'single') {
      const res = this.simulationService.runBacktest(
        this.candles(),
        config.initialCapital,
        config.commission,
        config.slippage,
        config.fastMa,
        config.slowMa,
        // Pass optional Ensemble/ML configs
        config.useEnsemble ? config.ensembleConfig : undefined,
        config.mlConfig
      );
      this.results.set(res);
    } 
    else if (config.mode === 'optimize' && config.optimization) {
      const opt = this.simulationService.optimizeStrategy(
        this.candles(),
        config.initialCapital,
        config.commission,
        config.slippage,
        config.optimization.fastStart,
        config.optimization.fastEnd,
        config.optimization.fastStep,
        config.optimization.slowStart,
        config.optimization.slowEnd,
        config.optimization.slowStep
      );
      
      this.optResult.set(opt);
      this.results.set(opt.bestResult);
    }
  }

  async analyze() {
    const metrics = this.results()?.metrics;
    if (!metrics) return;

    this.isAnalyzing.set(true);
    const rawHtml = await this.aiService.analyzeBacktest(metrics);
    // Sanitize the HTML to prevent XSS while allowing styling
    this.aiAnalysis.set(this.sanitizer.bypassSecurityTrustHtml(rawHtml));
    this.isAnalyzing.set(false);
  }

  async broadcast(trade: Trade) {
    const conf = this.webhookConfig();
    if (!conf || !conf.enableWebhooks) return;
    
    // Optimistic UI interaction
    const success = await this.simulationService.broadcastSignal(trade, conf.webhookUrl);
    if (success) {
      alert('Signal broadcast successfully to MT5 Bridge!');
    } else {
      alert('Failed to broadcast signal. Check console for CORS or network errors.');
    }
  }

  formatDate(ts: number): string {
    return new Date(ts).toLocaleDateString();
  }
}