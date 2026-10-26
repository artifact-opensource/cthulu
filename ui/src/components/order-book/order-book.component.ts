import { Component, input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { OrderBook } from '../../services/herald.service';

@Component({
  selector: 'app-order-book',
  standalone: true,
  imports: [CommonModule, DecimalPipe],
  template: `
    <div class="h-full flex flex-col bg-herald-panel border border-herald-dim/30 rounded-lg overflow-hidden font-mono text-xs">
      <div class="flex items-center justify-between px-3 py-2 border-b border-herald-dim/30 bg-herald-black/20">
        <span class="text-herald-text/60 font-semibold tracking-wider">ORDER BOOK</span>
        <div class="flex gap-2 text-[10px]">
          <span class="text-herald-text/40">SIZE</span>
          <span class="text-herald-text/40">PRICE</span>
        </div>
      </div>
      
      <div class="flex-1 overflow-y-auto flex flex-col relative">
        <!-- Asks (Red) -->
        <div class="flex flex-col justify-end pb-1">
          @for (ask of book().asks; track ask.price) {
            <div class="relative flex justify-between items-center px-2 py-0.5 group">
              <!-- Depth Bar -->
              <div class="absolute right-0 top-0 bottom-0 bg-herald-danger/10 transition-all duration-300" [style.width.%]="(ask.size / 3) * 100"></div>
              
              <span class="relative z-10 text-herald-text/50">{{ ask.size | number:'1.2-2' }}</span>
              <span class="relative z-10 text-herald-danger group-hover:text-white transition-colors">{{ ask.price | number:'1.2-2' }}</span>
            </div>
          }
        </div>

        <!-- Spread -->
        <div class="py-1 my-1 border-y border-herald-dim/20 bg-herald-black text-center flex justify-center items-center gap-2">
           <span class="text-herald-text/40 text-[10px]">SPREAD</span>
           <span class="text-herald-text font-bold">{{ book().spread | number:'1.2-2' }}</span>
           <span class="text-[9px] text-herald-text/30">({{ book().spreadPct | number:'1.3-3' }}%)</span>
        </div>

        <!-- Bids (Green) -->
        <div class="flex flex-col pt-1">
          @for (bid of book().bids; track bid.price) {
            <div class="relative flex justify-between items-center px-2 py-0.5 group">
              <!-- Depth Bar -->
              <div class="absolute right-0 top-0 bottom-0 bg-herald-accent/10 transition-all duration-300" [style.width.%]="(bid.size / 3) * 100"></div>
              
              <span class="relative z-10 text-herald-text/50">{{ bid.size | number:'1.2-2' }}</span>
              <span class="relative z-10 text-herald-accent group-hover:text-white transition-colors">{{ bid.price | number:'1.2-2' }}</span>
            </div>
          }
        </div>
      </div>
    </div>
  `
})
export class OrderBookComponent {
  book = input.required<OrderBook>();
}