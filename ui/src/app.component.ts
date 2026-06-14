import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HeraldService } from './services/herald.service';
import { MarketChartComponent } from './components/market-chart/market-chart.component';
import { TerminalComponent } from './components/terminal/terminal.component';
import { StatsTickerComponent } from './components/stats-ticker/stats-ticker.component';
import { OrderBookComponent } from './components/order-book/order-book.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule, 
    MarketChartComponent, 
    TerminalComponent, 
    StatsTickerComponent,
    OrderBookComponent
  ],
  templateUrl: './app.component.html'
})
export class AppComponent {
  private herald = inject(HeraldService);

  // UI State
  showOrderBook = signal(false);

  // Expose signals to template
  priceHistory = this.herald.priceHistory;
  currentPrice = this.herald.price;
  currentRSI = this.herald.currentRSI;
  logs = this.herald.logs;
  trades = this.herald.trades;
  pnl = this.herald.pnl;
  openPositions = this.herald.openPositions;
  isRunning = this.herald.isRunning;
  orderBook = this.herald.orderBook;

  toggleSystem() {
    this.herald.toggleSystem();
  }

  toggleOrderBook() {
    this.showOrderBook.update(v => !v);
  }

  closePosition(id: string) {
    this.herald.closeTrade(id);
  }
}