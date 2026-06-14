import { Component, input, computed } from '@angular/core';

@Component({
  selector: 'app-metrics',
  standalone: true,
  template: `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <!-- Net Profit -->
      <div class="bg-slate-800 p-4 rounded-lg border-l-4" 
           [class]="netProfitClass()">
        <div class="text-slate-400 text-xs uppercase tracking-wide">Net Profit</div>
        <div class="text-2xl font-mono font-bold">{{ netProfitFormatted() }}</div>
      </div>

      <!-- Win Rate -->
      <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-blue-500">
        <div class="text-slate-400 text-xs uppercase tracking-wide">Win Rate</div>
        <div class="text-2xl font-mono font-bold text-blue-400">
          {{ (data().winRate * 100).toFixed(1) }}%
        </div>
      </div>

      <!-- Sharpe -->
      <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-purple-500">
        <div class="text-slate-400 text-xs uppercase tracking-wide">Sharpe Ratio</div>
        <div class="text-2xl font-mono font-bold text-purple-400">
          {{ data().sharpeRatio.toFixed(2) }}
        </div>
      </div>

      <!-- Drawdown -->
      <div class="bg-slate-800 p-4 rounded-lg border-l-4 border-red-500">
        <div class="text-slate-400 text-xs uppercase tracking-wide">Max Drawdown</div>
        <div class="text-2xl font-mono font-bold text-red-400">
          -{{ (data().maxDrawdown * 100).toFixed(1) }}%
        </div>
      </div>
    </div>
    
    <div class="grid grid-cols-2 gap-4">
       <div class="bg-slate-800 p-3 rounded flex justify-between">
          <span class="text-slate-400">Total Trades</span>
          <span class="font-mono text-white">{{ data().totalTrades }}</span>
       </div>
       <div class="bg-slate-800 p-3 rounded flex justify-between">
          <span class="text-slate-400">Profit Factor</span>
          <span class="font-mono text-white">{{ data().profitFactor.toFixed(2) }}</span>
       </div>
    </div>
  `
})
export class MetricsComponent {
  data = input.required<any>();

  netProfit = computed(() => this.data().finalCapital - this.data().initialCapital);
  
  netProfitFormatted = computed(() => {
    const val = this.netProfit();
    return (val >= 0 ? '+' : '') + '$' + val.toFixed(2);
  });

  netProfitClass = computed(() => {
    return this.netProfit() >= 0 ? 'border-emerald-500 text-emerald-400' : 'border-red-500 text-red-400';
  });
}