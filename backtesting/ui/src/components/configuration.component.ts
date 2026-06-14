import { Component, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SpeedMode, WeightingMethod, SelectionMethod, DataSource } from '../services/simulation.service';

export interface ConfigData {
  initialCapital: number;
  commission: number;
  slippage: number;
  fastMa: number;
  slowMa: number;
  
  // Framework specific
  speedMode: SpeedMode;
  dataSource: DataSource;
  
  // Webhook / Live
  webhookUrl: string;
  enableWebhooks: boolean;

  // Ensemble
  useEnsemble: boolean;
  ensembleConfig: {
    weighting: WeightingMethod;
    confidenceThreshold: number;
  };

  // ML
  mlConfig: {
    selectionMethod: SelectionMethod;
    temperature: number;
  };

  mode: 'single' | 'optimize';
  optimization?: {
    fastStart: number;
    fastEnd: number;
    fastStep: number;
    slowStart: number;
    slowEnd: number;
    slowStep: number;
  };
}

@Component({
  selector: 'app-configuration',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="bg-slate-900 border border-slate-700 rounded-lg p-6 shadow-xl text-sm">
      <h2 class="text-xl font-bold text-emerald-400 mb-6 flex items-center">
        <i class="fa-solid fa-sliders mr-2"></i> Engine Config
      </h2>

      <!-- Mode Switch -->
      <div class="flex flex-col mb-6">
        <label class="text-slate-400 text-xs font-bold uppercase mb-2">Operation Mode</label>
        <div class="bg-slate-950 p-1 rounded-lg flex border border-slate-800">
          <button (click)="mode.set('single')" 
              class="flex-1 py-2 text-xs font-bold rounded-md transition-all duration-300 flex items-center justify-center gap-2"
              [class]="mode() === 'single' ? 'bg-slate-800 text-emerald-400 shadow ring-1 ring-emerald-500/50' : 'text-slate-500 hover:text-slate-300'">
              <i class="fa-solid fa-play"></i> Single Run
          </button>
          <button (click)="mode.set('optimize')" 
              class="flex-1 py-2 text-xs font-bold rounded-md transition-all duration-300 flex items-center justify-center gap-2"
              [class]="mode() === 'optimize' ? 'bg-slate-800 text-purple-400 shadow ring-1 ring-purple-500/50' : 'text-slate-500 hover:text-slate-300'">
              <i class="fa-solid fa-microchip"></i> Optimization
          </button>
        </div>
      </div>

      <!-- Tabs for Framework Settings -->
      <div class="flex space-x-4 mb-4 border-b border-slate-700 overflow-x-auto">
        <button (click)="activeTab.set('general')" class="pb-2 border-b-2 transition-colors whitespace-nowrap"
          [class]="activeTab() === 'general' ? 'border-emerald-500 text-emerald-400 font-bold' : 'border-transparent text-slate-500'">
          Execution
        </button>
        <button (click)="activeTab.set('strategy')" class="pb-2 border-b-2 transition-colors whitespace-nowrap"
          [class]="activeTab() === 'strategy' ? 'border-emerald-500 text-emerald-400 font-bold' : 'border-transparent text-slate-500'">
          Strategy
        </button>
        <button (click)="activeTab.set('ensemble')" class="pb-2 border-b-2 transition-colors whitespace-nowrap"
           [class]="activeTab() === 'ensemble' ? 'border-emerald-500 text-emerald-400 font-bold' : 'border-transparent text-slate-500'">
           Ensemble
        </button>
        <button (click)="activeTab.set('ml')" class="pb-2 border-b-2 transition-colors whitespace-nowrap"
           [class]="activeTab() === 'ml' ? 'border-emerald-500 text-emerald-400 font-bold' : 'border-transparent text-slate-500'">
           ML / Risk
        </button>
      </div>

      <!-- Execution Tab -->
      @if (activeTab() === 'general') {
        <div class="animate-fade-in space-y-4">
           <!-- Data Source -->
           <div class="p-3 bg-slate-950 rounded border border-slate-800">
            <label class="block text-slate-400 text-xs mb-2 font-bold uppercase">Data Source</label>
            <div class="flex gap-2 mb-2">
               <select [(ngModel)]="dataSource" class="bg-slate-800 border border-slate-600 rounded p-1 text-white text-xs w-full focus:border-emerald-500 outline-none">
                  <option [value]="DataSource.CSV">CSV File</option>
                  <option [value]="DataSource.MT5">MT5 Webhook Relay</option>
               </select>
            </div>
            
            @if(dataSource === DataSource.CSV) {
              <div class="relative">
                <input type="file" (change)="onFileSelected($event)" accept=".csv"
                  class="block w-full text-xs text-slate-400
                  file:mr-2 file:py-2 file:px-4
                  file:rounded file:border-0
                  file:text-xs file:font-semibold
                  file:bg-slate-700 file:text-white
                  hover:file:bg-slate-600 cursor-pointer"/>
              </div>
              <p class="text-[10px] text-slate-600 mt-1">Accepts .csv with OHLCV data.</p>
            }

            @if(dataSource === DataSource.MT5) {
               <div class="space-y-2 animate-fade-in">
                  <div class="flex items-center space-x-2">
                     <input type="checkbox" [(ngModel)]="enableWebhooks" id="webhook-en" class="rounded bg-slate-700 border-slate-600 text-blue-500">
                     <label for="webhook-en" class="text-blue-400 font-bold text-xs">Enable Outbound Signals</label>
                  </div>
                  @if(enableWebhooks) {
                     <div>
                       <label class="text-slate-500 text-[10px] mb-1 block">MT5 Webhook URL</label>
                       <input type="text" [(ngModel)]="webhookUrl" placeholder="http://localhost:8080/signal" 
                         class="w-full bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-blue-500 outline-none font-mono" />
                     </div>
                  }
               </div>
            }
          </div>

          <div class="grid grid-cols-2 gap-3">
             <div class="flex flex-col">
               <label class="text-slate-500 text-xs mb-1">Capital ($)</label>
               <input type="number" [(ngModel)]="capital" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-emerald-500 outline-none" />
             </div>
             <div class="flex flex-col">
               <label class="text-slate-500 text-xs mb-1">Speed Mode</label>
               <select [(ngModel)]="speedMode" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-emerald-500 outline-none">
                 <option [value]="SpeedMode.FAST">FAST (Vectorized)</option>
                 <option [value]="SpeedMode.NORMAL">NORMAL</option>
                 <option [value]="SpeedMode.SLOW">SLOW (Debug)</option>
                 <option [value]="SpeedMode.REALTIME">REALTIME</option>
               </select>
             </div>
             <div class="flex flex-col">
               <label class="text-slate-500 text-xs mb-1">Comm (%)</label>
               <input type="number" [(ngModel)]="commission" step="0.01" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-emerald-500 outline-none" />
             </div>
             <div class="flex flex-col">
               <label class="text-slate-500 text-xs mb-1">Slippage (%)</label>
               <input type="number" [(ngModel)]="slippage" step="0.01" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-emerald-500 outline-none" />
             </div>
          </div>
        </div>
      }

      <!-- Strategy Tab -->
      @if (activeTab() === 'strategy') {
        <div class="animate-fade-in space-y-4">
           
           @if (mode() === 'single') {
            <div class="p-3 bg-slate-950 rounded border border-slate-800">
               <h4 class="text-emerald-400 font-bold text-xs uppercase mb-3">Parameters (Single)</h4>
               <div class="grid grid-cols-2 gap-4">
                <div class="flex flex-col">
                  <label class="text-slate-400 text-xs mb-1">Fast MA Period</label>
                  <input type="number" [(ngModel)]="fastMa" 
                    class="bg-slate-800 border border-slate-600 rounded p-2 text-white focus:border-emerald-500 outline-none text-xs" />
                </div>
                <div class="flex flex-col">
                  <label class="text-slate-400 text-xs mb-1">Slow MA Period</label>
                  <input type="number" [(ngModel)]="slowMa" 
                    class="bg-slate-800 border border-slate-600 rounded p-2 text-white focus:border-emerald-500 outline-none text-xs" />
                </div>
              </div>
            </div>
           }

           @if (mode() === 'optimize') {
            <div class="flex flex-col space-y-3">
              <div class="p-3 bg-slate-950 rounded border border-purple-900/50">
                <label class="text-slate-400 text-[10px] uppercase font-bold tracking-wider text-purple-400 block mb-2">Fast MA Range</label>
                <div class="grid grid-cols-3 gap-2">
                  <div class="flex flex-col">
                     <span class="text-[9px] text-slate-500 mb-0.5">Start</span>
                     <input type="number" [(ngModel)]="optFastStart" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-purple-500 outline-none" />
                  </div>
                  <div class="flex flex-col">
                     <span class="text-[9px] text-slate-500 mb-0.5">End</span>
                     <input type="number" [(ngModel)]="optFastEnd" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-purple-500 outline-none" />
                  </div>
                  <div class="flex flex-col">
                     <span class="text-[9px] text-slate-500 mb-0.5">Step</span>
                     <input type="number" [(ngModel)]="optFastStep" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-purple-500 outline-none" />
                  </div>
                </div>
              </div>

              <div class="p-3 bg-slate-950 rounded border border-purple-900/50">
                 <label class="text-slate-400 text-[10px] uppercase font-bold tracking-wider text-purple-400 block mb-2">Slow MA Range</label>
                 <div class="grid grid-cols-3 gap-2">
                   <div class="flex flex-col">
                     <span class="text-[9px] text-slate-500 mb-0.5">Start</span>
                     <input type="number" [(ngModel)]="optSlowStart" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-purple-500 outline-none" />
                  </div>
                  <div class="flex flex-col">
                     <span class="text-[9px] text-slate-500 mb-0.5">End</span>
                     <input type="number" [(ngModel)]="optSlowEnd" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-purple-500 outline-none" />
                  </div>
                  <div class="flex flex-col">
                     <span class="text-[9px] text-slate-500 mb-0.5">Step</span>
                     <input type="number" [(ngModel)]="optSlowStep" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs focus:border-purple-500 outline-none" />
                  </div>
                 </div>
               </div>
            </div>
           }
        </div>
      }

      <!-- Ensemble Tab -->
      @if (activeTab() === 'ensemble') {
        <div class="animate-fade-in space-y-4">
           <div class="flex items-center space-x-2 mb-4">
             <input type="checkbox" [(ngModel)]="useEnsemble" id="ens" class="w-4 h-4 rounded bg-slate-700 border-slate-500 text-emerald-500 focus:ring-emerald-500">
             <label for="ens" class="text-slate-300 font-bold">Enable Ensemble Strategy</label>
           </div>
           
           <div class="p-3 bg-slate-950 rounded border border-slate-800" [class.opacity-50]="!useEnsemble">
             <div class="flex flex-col mb-3">
               <label class="text-slate-500 text-xs mb-1">Weighting Method</label>
               <select [(ngModel)]="weightingMethod" [disabled]="!useEnsemble" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs">
                 <option [value]="WeightingMethod.EQUAL">EQUAL</option>
                 <option [value]="WeightingMethod.PERFORMANCE">PERFORMANCE</option>
                 <option [value]="WeightingMethod.SHARPE">SHARPE</option>
                 <option [value]="WeightingMethod.ADAPTIVE">ADAPTIVE</option>
               </select>
             </div>
             <div class="flex flex-col">
                <label class="text-slate-500 text-xs mb-1">Confidence Threshold</label>
                <div class="flex items-center space-x-2">
                  <input type="range" [(ngModel)]="confidence" min="0" max="1" step="0.1" [disabled]="!useEnsemble" class="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer">
                  <span class="text-xs text-white w-8">{{ confidence }}</span>
                </div>
             </div>
           </div>
        </div>
      }

      <!-- ML / Risk Tab -->
      @if (activeTab() === 'ml') {
        <div class="animate-fade-in space-y-4">
           <div class="p-3 bg-slate-950 rounded border border-slate-800">
             <h4 class="text-purple-400 font-bold text-xs uppercase mb-3">Signal Selection (ML)</h4>
             
             <div class="flex flex-col mb-3">
               <label class="text-slate-500 text-xs mb-1">Method</label>
               <select [(ngModel)]="selectionMethod" class="bg-slate-800 border border-slate-600 rounded p-2 text-white text-xs">
                 <option [value]="SelectionMethod.SOFTMAX">SOFTMAX (Probabilistic)</option>
                 <option [value]="SelectionMethod.ARGMAX">ARGMAX (Greedy)</option>
               </select>
             </div>
             
             @if (selectionMethod === SelectionMethod.SOFTMAX) {
              <div class="flex flex-col">
                  <label class="text-slate-500 text-xs mb-1">Temperature (Exploration)</label>
                  <div class="flex items-center space-x-2">
                    <input type="range" [(ngModel)]="temperature" min="0.1" max="2.0" step="0.1" class="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer">
                    <span class="text-xs text-white w-8">{{ temperature }}</span>
                  </div>
               </div>
             }
           </div>
        </div>
      }

      <!-- Footer Actions -->
      <div class="mt-6 pt-4 border-t border-slate-700">
        <button (click)="onRun()" 
          [class]="mode() === 'optimize' ? 'bg-purple-600 hover:bg-purple-500 shadow-purple-900/50' : 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/50'"
          class="w-full text-white font-bold py-3 px-4 rounded transition-all transform hover:scale-[1.02] shadow-lg flex justify-center items-center">
          @if (mode() === 'optimize') {
            <i class="fa-solid fa-microchip mr-2"></i> Run Optimization
          } @else {
            <i class="fa-solid fa-play mr-2"></i> Run Simulation
          }
        </button>
      </div>
    </div>
  `
})
export class ConfigurationComponent {
  // Imports for Template Access
  SpeedMode = SpeedMode;
  WeightingMethod = WeightingMethod;
  SelectionMethod = SelectionMethod;
  DataSource = DataSource;

  run = output<ConfigData>();
  fileLoaded = output<string>();

  mode = signal<'single'|'optimize'>('single');
  activeTab = signal<'general'|'strategy'|'ensemble'|'ml'>('general');

  // Execution Defaults
  capital = 10000;
  commission = 0.1;
  slippage = 0.05;
  speedMode = SpeedMode.FAST;
  dataSource = DataSource.CSV;

  // Webhook
  webhookUrl = 'http://localhost:8080/webhook';
  enableWebhooks = false;

  // Strategy Defaults
  fastMa = 10;
  slowMa = 50;

  // Ensemble Defaults
  useEnsemble = false;
  weightingMethod = WeightingMethod.ADAPTIVE;
  confidence = 0.6;

  // ML Defaults
  selectionMethod = SelectionMethod.SOFTMAX;
  temperature = 0.5;

  // Optimization Defaults
  optFastStart = 5;
  optFastEnd = 20;
  optFastStep = 5;
  optSlowStart = 20;
  optSlowEnd = 100;
  optSlowStep = 10;

  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e: any) => {
        this.fileLoaded.emit(e.target.result);
      };
      reader.readAsText(file);
    }
  }

  onRun() {
    this.run.emit({
      initialCapital: this.capital,
      commission: this.commission / 100,
      slippage: this.slippage / 100,
      fastMa: this.fastMa,
      slowMa: this.slowMa,
      speedMode: this.speedMode,
      dataSource: this.dataSource,
      webhookUrl: this.webhookUrl,
      enableWebhooks: this.enableWebhooks,
      useEnsemble: this.useEnsemble,
      ensembleConfig: {
        weighting: this.weightingMethod,
        confidenceThreshold: this.confidence
      },
      mlConfig: {
        selectionMethod: this.selectionMethod,
        temperature: this.temperature
      },
      mode: this.mode(),
      optimization: this.mode() === 'optimize' ? {
        fastStart: this.optFastStart,
        fastEnd: this.optFastEnd,
        fastStep: this.optFastStep,
        slowStart: this.optSlowStart,
        slowEnd: this.optSlowEnd,
        slowStep: this.optSlowStep
      } : undefined
    });
  }
}