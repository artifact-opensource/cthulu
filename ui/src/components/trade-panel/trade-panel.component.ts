import { Component, output } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
  selector: 'app-trade-panel',
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <div class="bg-herald-panel p-4 rounded-lg border border-herald-dim/30 h-full flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-herald-text/70 uppercase tracking-widest">Manual Override</h3>
        <span class="px-2 py-0.5 text-[10px] bg-herald-accent/10 text-herald-accent rounded border border-herald-accent/20">ACTIVE</span>
      </div>

      <div class="flex-1 flex flex-col justify-center gap-4">
        <div class="flex flex-col gap-2">
           <label class="text-xs text-herald-text/50 font-mono">SIZE (UNITS)</label>
           <input 
             [formControl]="sizeControl" 
             type="number" 
             step="0.1"
             class="bg-herald-black border border-herald-dim rounded p-2 text-right font-mono text-herald-accent focus:outline-none focus:border-herald-accent transition-colors"
           >
        </div>

        <div class="grid grid-cols-2 gap-3 mt-2">
          <button 
            (click)="placeOrder('BUY')"
            class="group relative overflow-hidden bg-herald-accent/10 hover:bg-herald-accent/20 border border-herald-accent/50 text-herald-accent font-bold py-3 rounded transition-all active:scale-95"
          >
             <span class="relative z-10 flex flex-col items-center">
               <span class="text-lg">BUY</span>
               <span class="text-[10px] opacity-60 font-mono">LONG POSITION</span>
             </span>
             <div class="absolute inset-0 bg-herald-accent/10 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
          </button>

          <button 
             (click)="placeOrder('SELL')"
             class="group relative overflow-hidden bg-herald-danger/10 hover:bg-herald-danger/20 border border-herald-danger/50 text-herald-danger font-bold py-3 rounded transition-all active:scale-95"
          >
             <span class="relative z-10 flex flex-col items-center">
               <span class="text-lg">SELL</span>
               <span class="text-[10px] opacity-60 font-mono">SHORT POSITION</span>
             </span>
             <div class="absolute inset-0 bg-herald-danger/10 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
          </button>
        </div>
      </div>
      
      <div class="text-[10px] text-herald-text/30 text-center font-mono">
        Cthulu will adapt strategy to your manual entries.
      </div>
    </div>
  `
})
export class TradePanelComponent {
  onTrade = output<{type: 'BUY' | 'SELL', size: number}>();
  sizeControl = new FormControl(1.0, { nonNullable: true, validators: [Validators.min(0.01)] });

  placeOrder(type: 'BUY' | 'SELL') {
    if (this.sizeControl.valid) {
      this.onTrade.emit({ type, size: this.sizeControl.value });
    }
  }
}