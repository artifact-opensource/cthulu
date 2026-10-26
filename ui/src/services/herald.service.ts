import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { GoogleGenAI } from "@google/genai";
import { firstValueFrom } from 'rxjs';
<<<<<<< HEAD
import { io, Socket } from 'socket.io-client';
=======
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a

export interface Trade {
  id: string;
  type: 'BUY' | 'SELL';
  price: number;
  size: number;
  timestamp: number;
  status: 'OPEN' | 'CLOSED';
  pnl?: number;
  origin: 'AUTO' | 'USER';
  reason?: string;
}

export interface LogEntry {
  timestamp: number;
  level: 'INFO' | 'WARN' | 'ERROR' | 'TRADE';
  message: string;
  source: 'SYSTEM' | 'CTHULU_AI';
  real_time_str?: string;
}

export interface SignalEntry {
  signal_id: string;
  symbol: string;
  action: string;
  confidence: number;
  timestamp: string; // ISO DB string
  price: number;
  reason: string;
}

export interface OrderBookEntry {
  price: number;
  size: number;
  total: number;
}

export interface OrderBook {
  asks: OrderBookEntry[];
  bids: OrderBookEntry[];
  spread: number;
  spreadPct: number;
}

// Chart drawings from Chart Manager
export interface ChartZone {
  id: string;
  type: string;
  upper: number;
  lower: number;
  midpoint: number;
  state: string;
  strength: number;
  color: string;
  style: {
    fill_opacity: number;
    border_style: string;
    border_width: number;
  };
}

export interface ChartLevel {
  price: number;
  type: 'support' | 'resistance';
  color: string;
  style: string;
  label: string;
}

export interface ChartDrawings {
  symbol: string;
  timeframe: string;
  timestamp: string;
  zones: ChartZone[];
  levels: ChartLevel[];
  trend_lines: any[];
  channels: any[];
}

@Injectable({
  providedIn: 'root'
})
export class HeraldService {
  private http = inject(HttpClient);
  private API_URL = 'http://localhost:5000/api';
<<<<<<< HEAD
  private WS_URL = 'http://localhost:5000';
  private socket: Socket | null = null;
=======
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a

  // State Signals
  readonly price = signal<number>(0); // 0 indicates unknown
  readonly priceHistory = signal<{ time: number, value: number }[]>([]);
<<<<<<< HEAD
  readonly ohlcHistory = signal<{ time: number, open: number, high: number, low: number, close: number }[]>([]);
=======
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
  readonly trades = signal<Trade[]>([]);
  readonly logs = signal<LogEntry[]>([]);
  readonly signals = signal<SignalEntry[]>([]);
  readonly orderBook = signal<OrderBook>({ asks: [], bids: [], spread: 0, spreadPct: 0 });

<<<<<<< HEAD
  // Chart Drawings from Chart Manager
  readonly chartDrawings = signal<ChartDrawings | null>(null);

=======
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
  // System Status
  readonly isRunning = signal<boolean>(true);
  readonly isConnected = signal<boolean>(false);
  readonly lastHeartbeat = signal<number>(0);

  // Indicators
  readonly currentRSI = signal<number>(0);

  // Metrics
  readonly pnl = computed(() => this.trades().reduce((acc, t) => acc + (t.pnl || 0), 0));
  readonly openPositions = computed(() => this.trades().filter(t => t.status === 'OPEN').length);

  // Gemini Client
  private ai: GoogleGenAI;
  private timer: any;

  constructor() {
<<<<<<< HEAD
    this.ai = new GoogleGenAI({ apiKey: '' });
    this.initWebSocket();
    this.initPolling();
  }

  private initWebSocket() {
    this.socket = io(this.WS_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000
    });
=======
    this.ai = new GoogleGenAI({ apiKey: process.env['API_KEY'] || '' });
    this.initPolling();
  }

  private initPolling() {
    // Poll faster for status, slower for heavy data
    setInterval(() => this.checkStatus(), 2000);
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a

    this.socket.on('connect', () => {
      console.log('WebSocket connected');
      this.isConnected.set(true);
      this.localLog('INFO', 'Live price feed connected', 'SYSTEM');
    });

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected');
      this.isConnected.set(false);
    });

    this.socket.on('price', (data: { value: number, time: number, symbol: string }) => {
      if (data && data.value) {
        this.updatePrice(data.value);
      }
    });

    this.socket.on('trade', (trade: Trade) => {
      // Real-time trade notification
      this.trades.update(t => [trade, ...t].slice(0, 100));
      this.localLog('TRADE', `${trade.type} ${trade.size} @ ${trade.price}`, 'SYSTEM');
    });

    // Listen for chart drawings updates
    this.socket.on('drawings', (data: ChartDrawings) => {
      if (data) {
        this.chartDrawings.set(data);
      }
    });
  }

  private initPolling() {
    // Poll for status and heavy data (slower)
    setInterval(() => this.checkStatus(), 5000);
    this.timer = setInterval(() => {
      if (!this.isConnected()) return;
<<<<<<< HEAD
      this.fetchTrades();
      this.fetchLogs();
      this.fetchSignals();
      this.fetchDrawings();
      this.fetchOrderBook();
    }, 3000); // 3s for non-price data

    // Initial Load
    this.fetchHistory();
    this.fetchDrawings();
    this.fetchOrderBook();
  }

  private async checkStatus() {
    try {
      await firstValueFrom(this.http.get(`${this.API_URL}/status`));
      this.isConnected.set(true);
      this.lastHeartbeat.set(Date.now());
    } catch (e) {
      this.isConnected.set(false);
      const lastLog = this.logs()[0];
      if (!lastLog || lastLog.message !== 'Backend Offline - Waiting for Cthulu...') {
        this.localLog('ERROR', 'Backend Offline - Waiting for Cthulu...', 'SYSTEM');
      }
    }
  }

  private fetchHistory() {
    // Get price history from trades
    this.http.get<any[]>(`${this.API_URL}/history`).subscribe({
      next: (data) => {
        if (data && data.length > 0) {
          const history = data.map(d => ({ time: d.time, value: d.close }));
          this.priceHistory.set(history);
          
          // Set OHLC data for TradingView chart
          const ohlc = data.map(d => ({
            time: d.time,
            open: d.open || d.close,
            high: d.high || d.close,
            low: d.low || d.close,
            close: d.close
          }));
          this.ohlcHistory.set(ohlc);
          
          const closes = history.map(h => h.value);
          this.currentRSI.set(this.calculateRSI(closes));
        }
      }
    });
=======
      this.tick();
    }, 1000); // 1s data refresh when online
  }

  private async checkStatus() {
    try {
      await firstValueFrom(this.http.get(`${this.API_URL}/status`));
      this.isConnected.set(true);
      this.lastHeartbeat.set(Date.now());
    } catch (e) {
      this.isConnected.set(false);
      // If offline, add a system log once (debounced) if we haven't already recently
      const lastLog = this.logs()[0];
      if (!lastLog || lastLog.message !== 'Backend Offline - Waiting for Cthulu...') {
        this.localLog('ERROR', 'Backend Offline - Waiting for Cthulu...', 'SYSTEM');
      }
    }
  }

  private tick() {
    this.fetchTrades();
    this.fetchLogs();
    this.fetchSignals();
    this.fetchMetrics();
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
  }

  private fetchTrades() {
    this.http.get<Trade[]>(`${this.API_URL}/trades`).subscribe({
<<<<<<< HEAD
      next: (data) => { if (data) this.trades.set(data); },
      error: () => { }
=======
      next: (data) => {
        if (data) {
          this.trades.set(data);
          // Update current price from latest trade if available for some realism
          if (data.length > 0) {
            const lastTrade = data[0];
            // Only update if looks like a valid price
            if (lastTrade.price > 0) {
              // this.updatePrice(lastTrade.price); // Optional: drive price from trade data
            }
          }
        }
      },
      error: () => { } // Handled by status check
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
    });
  }

  private fetchLogs() {
    this.http.get<LogEntry[]>(`${this.API_URL}/logs`).subscribe({
<<<<<<< HEAD
      next: (data) => { if (data && data.length > 0) this.logs.set(data); }
=======
      next: (data) => {
        // Merge, but keep our local connection logs if possible.
        // For now, simpler to just prepend backend logs.
        // We rely on backend providing sorted logs.
        if (data && data.length > 0) {
          this.logs.set(data);
        }
      }
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
    });
  }

  private fetchSignals() {
    this.http.get<any[]>(`${this.API_URL}/signals`).subscribe({
<<<<<<< HEAD
      next: (data) => { if (data) this.signals.set(data); }
    });
  }

  private fetchDrawings() {
    this.http.get<ChartDrawings>(`${this.API_URL}/drawings`).subscribe({
      next: (data) => { if (data && data.zones) this.chartDrawings.set(data); }
    });
  }

  private fetchOrderBook() {
    this.http.get<OrderBook>(`${this.API_URL}/orderbook`).subscribe({
      next: (data) => { if (data) this.orderBook.set(data); },
      error: () => { }
    });
  }

  private fetchMetrics() { }

=======
      next: (data) => {
        if (data) {
          this.signals.set(data);
          // Try to find a recent price in signals to update UI
          const recent = data[0];
          if (recent && recent.price) {
            this.updatePrice(recent.price);
          }
        }
      }
    });
  }

  private fetchMetrics() {
    // TODO: Bind backend metrics to UI if we adds charts
  }

>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
  private updatePrice(newPrice: number) {
    if (newPrice === this.price()) return;

    this.price.set(newPrice);
    this.priceHistory.update(h => {
      const newHistory = [...h, { time: Date.now(), value: newPrice }];
      if (newHistory.length > 500) newHistory.shift(); // Keep more history
      return newHistory;
    });

<<<<<<< HEAD
    // Update OHLC for real-time candle building
    const now = Date.now();
    const candleInterval = 60000; // 1 minute candles
    this.ohlcHistory.update(ohlc => {
      if (ohlc.length === 0) {
        return [{ time: now, open: newPrice, high: newPrice, low: newPrice, close: newPrice }];
      }
      
      const lastCandle = ohlc[ohlc.length - 1];
      const candleStart = Math.floor(lastCandle.time / candleInterval) * candleInterval;
      const currentCandleStart = Math.floor(now / candleInterval) * candleInterval;
      
      if (currentCandleStart === candleStart) {
        // Update current candle
        const updated = [...ohlc];
        updated[updated.length - 1] = {
          ...lastCandle,
          high: Math.max(lastCandle.high, newPrice),
          low: Math.min(lastCandle.low, newPrice),
          close: newPrice
        };
        return updated;
      } else {
        // New candle
        const newCandle = { time: currentCandleStart, open: newPrice, high: newPrice, low: newPrice, close: newPrice };
        const newOhlc = [...ohlc, newCandle];
        if (newOhlc.length > 500) newOhlc.shift();
        return newOhlc;
      }
    });

    // Update RSI on every tick (simplified)
    const history = this.priceHistory().map(h => h.value);
    this.currentRSI.set(this.calculateRSI(history));
  }

  // --- Indicators ---

  private calculateRSI(prices: number[], period: number = 14): number {
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    // Calculate initial RS
    for (let i = prices.length - period; i < prices.length; i++) {
      const diff = prices[i] - prices[i - 1];
      if (diff >= 0) gains += diff;
      else losses -= diff;
    }

    if (losses === 0) return 100;

    const avgGain = gains / period;
    const avgLoss = losses / period;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  // --- Actions ---
=======
    // We can't really generate an order book without real L2 data.
    // Leaving it empty or minimal to avoid "fake" misleading info.
    this.orderBook.set({ asks: [], bids: [], spread: 0, spreadPct: 0 });
  }

  // --- Helpers ---
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a

  public placeManualTrade(type: 'BUY' | 'SELL', size: number) {
    if (!this.isConnected()) {
      this.localLog('ERROR', 'Cannot trade: System Offline', 'SYSTEM');
      return;
    }
<<<<<<< HEAD

    const payload = {
      symbol: "BTCUSD#", // Match config.json
      side: type,
      volume: size
    };

    this.localLog('INFO', `Sending ${type} order to Cthulu RPC...`, 'SYSTEM');
    this.http.post(`${this.API_URL}/trade`, payload).subscribe({
      next: (res: any) => {
        if (res.error) {
          this.localLog('ERROR', `Trade Failed: ${res.error}`, 'SYSTEM');
        } else {
          this.localLog('INFO', `Trade Accepted: #${res.order_id}`, 'SYSTEM');
        }
      },
      error: (err) => {
        this.localLog('ERROR', `RPC Error: ${err.message}`, 'SYSTEM');
      }
    });
=======
    this.localLog('WARN', 'Manual trading via UI not yet connected to Cthulu core.', 'SYSTEM');
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
  }

  public toggleSystem() {
    this.isRunning.update(v => !v);
  }

  public closeTrade(id: string) {
    this.localLog('WARN', 'Remote close not yet implemented.', 'SYSTEM');
  }

  private localLog(level: 'INFO' | 'WARN' | 'ERROR' | 'TRADE', message: string, source: 'SYSTEM' | 'CTHULU_AI') {
    this.logs.update(l => [{
      timestamp: Date.now(),
      level,
      message,
      source
    }, ...l].slice(0, 100));
  }
}