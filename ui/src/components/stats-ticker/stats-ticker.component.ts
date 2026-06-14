import { Component, input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';

@Component({
  selector: 'app-stats-ticker',
  standalone: true,
  imports: [CommonModule, DecimalPipe],
  template: `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
      <!-- Current Price -->
      <div class="bg-herald-panel border border-herald-dim/30 p-3 rounded flex flex-col">
        <span class="text-[10px] text-herald-text/50 font-mono uppercase">Market Price</span>
        <span class="text-xl font-mono text-white">{{ price() | number:'1.2-2' }} <span class="text-xs text-herald-dim">USD</span></span>
      </div>

      <!-- PnL -->
      <div class="bg-herald-panel border border-herald-dim/30 p-3 rounded flex flex-col">
        <span class="text-[10px] text-herald-text/50 font-mono uppercase">Unrealized PnL</span>
        <span class="text-xl font-mono" [class.text-herald-accent]="pnl() >= 0" [class.text-herald-danger]="pnl() < 0">
           {{ pnl() > 0 ? '+' : '' }}{{ pnl() | number:'1.2-2' }}
        </span>
      </div>

      <!-- Open Positions -->
      <div class="bg-herald-panel border border-herald-dim/30 p-3 rounded flex flex-col">
        <span class="text-[10px] text-herald-text/50 font-mono uppercase">Open Positions</span>
        <span class="text-xl font-mono text-white">{{ openPositions() }}</span>
      </div>

      <!-- Status -->
      <div class="bg-herald-panel border border-herald-dim/30 p-3 rounded flex flex-col justify-center items-start">
         <div class="flex items-center gap-2">
            <span class="relative flex h-3 w-3">
              @if (running()) {
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-herald-accent opacity-75"></span>
                <span class="relative inline-flex rounded-full h-3 w-3 bg-herald-accent"></span>
              } @else {
                <span class="relative inline-flex rounded-full h-3 w-3 bg-herald-danger"></span>
              }
            </span>
            <span class="font-mono text-sm font-bold tracking-widest" [class.text-herald-accent]="running()" [class.text-herald-danger]="!running()">
              {{ running() ? 'SYSTEM ONLINE' : 'SYSTEM PAUSED' }}
            </span>
         </div>
      </div>
    </div>
  `
})
export class StatsTickerComponent {
  price = input.required<number>();
  pnl = input.required<number>();
  openPositions = input.required<number>();
  running = input.required<boolean>();
}