import { Injectable } from '@angular/core';

// --- Framework Enums ---
export enum SpeedMode {
  FAST = 'FAST',
  NORMAL = 'NORMAL',
  SLOW = 'SLOW',
  REALTIME = 'REALTIME',
  HFT_TEST = 'HFT_TEST'
}

export enum WeightingMethod {
  EQUAL = 'EQUAL',
  PERFORMANCE = 'PERFORMANCE',
  SHARPE = 'SHARPE',
  ADAPTIVE = 'ADAPTIVE'
}

export enum SelectionMethod {
  SOFTMAX = 'SOFTMAX',
  ARGMAX = 'ARGMAX'
}

export enum DataSource {
  MT5 = 'MT5',
  CSV = 'CSV'
}

// --- Interfaces ---

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Trade {
  entryTime: number;
  exitTime: number;
  entryPrice: number;
  exitPrice: number;
  pnl: number;
  type: 'long' | 'short';
}

export interface BacktestResult {
  metrics: {
    initialCapital: number;
    finalCapital: number;
    totalTrades: number;
    winRate: number;
    sharpeRatio: number;
    maxDrawdown: number;
    profitFactor: number;
    ensembleStats?: {
      active: boolean;
      method: string;
      boost: number;
    };
  };
  equityCurve: { time: number; value: number }[];
  trades: Trade[];
  candles: Candle[];
}

export interface OptimizationResult {
  bestFastMa: number;
  bestSlowMa: number;
  bestProfitFactor: number;
  bestResult: BacktestResult;
  iterations: number;
}

@Injectable({
  providedIn: 'root',
})
export class SimulationService {
  
  // Parse CSV Data (Date,Open,High,Low,Close,Volume)
  parseCsvData(csvText: string): Candle[] {
    const lines = csvText.trim().split(/\r?\n/);
    const candles: Candle[] = [];
    
    const firstLine = lines[0];
    const hasHeader = /^[a-zA-Z]/.test(firstLine);
    const startIdx = hasHeader ? 1 : 0;

    for (let i = startIdx; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      
      const parts = line.split(',');
      if (parts.length < 5) continue;

      const timeStr = parts[0];
      const time = new Date(timeStr).getTime();
      const open = parseFloat(parts[1]);
      const high = parseFloat(parts[2]);
      const low = parseFloat(parts[3]);
      const close = parseFloat(parts[4]);
      const volume = parseFloat(parts[5] || '0');

      if (!isNaN(time) && !isNaN(close)) {
        candles.push({ time, open, high, low, close, volume });
      }
    }
    return candles.sort((a, b) => a.time - b.time);
  }

  // Generates random walk market data (Fallback)
  generateData(days: number = 365): Candle[] {
    const candles: Candle[] = [];
    let price = 100;
    const now = new Date();
    
    for (let i = 0; i < days; i++) {
      const time = new Date(now.getTime() - (days - i) * 24 * 60 * 60 * 1000).getTime();
      const volatility = 0.02; // 2% daily volatility
      const change = 1 + (Math.random() * volatility * 2 - volatility);
      
      const open = price;
      const close = price * change;
      const high = Math.max(open, close) * (1 + Math.random() * 0.01);
      const low = Math.min(open, close) * (1 - Math.random() * 0.01);
      const volume = Math.floor(Math.random() * 1000000) + 500000;
      
      candles.push({ time, open, high, low, close, volume });
      price = close;
    }
    return candles;
  }

  // Live Webhook Dispatcher
  async broadcastSignal(trade: Trade, url: string): Promise<boolean> {
    const payload = {
        magic: 80801,
        symbol: 'MOCK_SYM',
        type: trade.type.toUpperCase(), // 'LONG' | 'SHORT'
        action: 'OPEN', // Simplified
        price: trade.entryPrice,
        volume: 1.0,
        timestamp: new Date().toISOString(),
        source: 'Cthulhu_Web_Backtester'
    };

    try {
        console.log(`[MT5 Webhook] Dispatching to ${url}`, payload);
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return true;
    } catch (e) {
        console.warn('[MT5 Webhook] Delivery failed. Ensure your MT5 EA Server is running and CORS is enabled.', e);
        return false;
    }
  }

  // Runs strategy on provided candles
  runBacktest(
    candles: Candle[], 
    initialCapital: number, 
    commission: number, 
    slippage: number, 
    fastMa: number, 
    slowMa: number,
    ensembleConfig?: { weighting: WeightingMethod, confidenceThreshold: number },
    mlConfig?: { selectionMethod: SelectionMethod, temperature: number }
  ): BacktestResult {
    const dataToUse = (candles && candles.length > 0) ? candles : this.generateData(365);

    let cash = initialCapital;
    let position = 0; // 0 = flat, 1 = long
    let entryPrice = 0;
    let entryTime = 0;
    const trades: Trade[] = [];
    const equityCurve: { time: number; value: number }[] = [];
    let maxEquity = initialCapital;
    let maxDrawdown = 0;

    // --- Helper Functions (Inlined for Performance) ---
    
    // Simple Moving Average
    const getSma = (idx: number, period: number, source: 'close' | 'volume' = 'close') => {
      if (idx < period - 1) return 0;
      let sum = 0;
      for (let k = 0; k < period; k++) {
        sum += source === 'close' ? dataToUse[idx - k].close : dataToUse[idx - k].volume;
      }
      return sum / period;
    };

    // RSI (14 period) - Simplified calculation for single-pass loop
    const getRsi = (idx: number, period: number = 14) => {
        if (idx < period) return 50;
        let gains = 0;
        let losses = 0;
        for (let k = 0; k < period; k++) {
            const diff = dataToUse[idx - k].close - dataToUse[idx - k - 1].close;
            if (diff >= 0) gains += diff;
            else losses += Math.abs(diff);
        }
        if (losses === 0) return 100;
        const rs = gains / losses;
        return 100 - (100 / (1 + rs));
    };

    // --- Strategy Setup ---

    // Define Ensemble Strategies (Variations for Consensus)
    // 1. Core (User selected)
    // 2. Fast (Reactive: ~80% of period)
    // 3. Slow (Trend Confirmation: ~120% of period)
    const strategies = [
        { f: fastMa, s: slowMa, weight: 1.0 },
        { f: Math.max(2, Math.floor(fastMa * 0.8)), s: Math.max(5, Math.floor(slowMa * 0.8)), weight: 0.8 },
        { f: Math.floor(fastMa * 1.2), s: Math.floor(slowMa * 1.2), weight: 0.8 }
    ];

    // Ensure we start loop where the slowest strategy has data
    const maxPeriod = Math.max(...strategies.map(s => s.s)) + 20; // +20 buffer for RSI/Vol

    for (let i = 0; i < dataToUse.length; i++) {
      const candle = dataToUse[i];
      
      // Update Equity
      const currentEquity = cash + (position > 0 ? (candle.close - entryPrice) * (initialCapital / entryPrice) : 0);
      equityCurve.push({ time: candle.time, value: currentEquity });
      
      if (currentEquity > maxEquity) maxEquity = currentEquity;
      const dd = maxEquity > 0 ? (maxEquity - currentEquity) / maxEquity : 0;
      if (dd > maxDrawdown) maxDrawdown = dd;

      if (i < maxPeriod) continue;

      // ----------------------------------------------------
      // 1. ENSEMBLE SIGNAL GENERATION
      // ----------------------------------------------------
      let buyVotes = 0;
      let sellVotes = 0;
      let totalWeight = 0;

      strategies.forEach(strat => {
          const fastVal = getSma(i, strat.f);
          const slowVal = getSma(i, strat.s);
          const prevFast = getSma(i - 1, strat.f);
          const prevSlow = getSma(i - 1, strat.s);

          // Crossover Bullish
          if (prevFast <= prevSlow && fastVal > slowVal) {
              buyVotes += strat.weight;
          }
          // Crossover Bearish
          else if (prevFast >= prevSlow && fastVal < slowVal) {
              sellVotes += strat.weight;
          }
          totalWeight += strat.weight;
      });

      let signal: 'buy' | 'sell' | 'hold' = 'hold';

      const ensembleActive = ensembleConfig && ensembleConfig.confidenceThreshold > 0;
      
      if (ensembleActive) {
          const buyConfidence = buyVotes / totalWeight; // Normalized 0-1
          const sellConfidence = sellVotes / totalWeight;

          if (buyConfidence >= ensembleConfig.confidenceThreshold && buyVotes > sellVotes) {
              signal = 'buy';
          } else if (sellConfidence >= ensembleConfig.confidenceThreshold && sellVotes > buyVotes) {
              signal = 'sell';
          }
      } else {
          // Standard Single Strategy behavior (Core only)
          const core = strategies[0];
          const f = getSma(i, core.f);
          const s = getSma(i, core.s);
          const pf = getSma(i - 1, core.f);
          const ps = getSma(i - 1, core.s);
          
          if (pf <= ps && f > s) signal = 'buy';
          else if (pf >= ps && f < s) signal = 'sell';
      }

      // ----------------------------------------------------
      // 2. ML / RISK FILTER (REGIME DETECTION)
      // ----------------------------------------------------
      let isTradeAllowed = true;
      let dynamicSlippage = slippage;

      if (mlConfig) {
          const rsi = getRsi(i, 14);
          const volSma = getSma(i, 20, 'volume');
          const relVol = candle.volume / (volSma || 1);

          // Calculate "Trade Quality Score" (0.0 to 1.0)
          // Hypothesis: Trend following works best in healthy trends (RSI 40-75) with Volume support.
          let score = 0.5;

          if (signal === 'buy') {
              if (rsi > 40 && rsi < 75) score += 0.2; // Healthy trend
              if (rsi > 80) score -= 0.3; // Overbought risk
              if (relVol > 1.2) score += 0.2; // Volume breakout
              else if (relVol < 0.8) score -= 0.1; // Low volume / weak move
          } else if (signal === 'sell') {
              if (rsi < 60 && rsi > 25) score += 0.2;
              if (rsi < 20) score -= 0.3; // Oversold risk
              if (relVol > 1.2) score += 0.2; // Volume breakout
          }

          // Apply Selection Method
          if (mlConfig.selectionMethod === SelectionMethod.ARGMAX) {
              // Greedy: Strictly filter out low quality trades
              if (score < 0.6) isTradeAllowed = false;
          } else {
              // Softmax/Probabilistic: Sample from the distribution
              // Temperature controls exploration: 
              // T < 1.0 makes high scores much more likely (Greedy-ish)
              // T > 1.0 makes it more random (Exploration)
              const temp = mlConfig.temperature || 1;
              const prob = Math.pow(Math.max(0, Math.min(1, score)), 1/temp);
              
              if (Math.random() > prob) isTradeAllowed = false;
          }

          // Dynamic Execution Modeling (Realism)
          // High Liquidity (Volume) = Better fills (Lower Slippage)
          // Low Liquidity = Worse fills
          if (relVol > 1.5) dynamicSlippage *= 0.8; // 20% Slippage Discount
          else if (relVol < 0.5) dynamicSlippage *= 1.5; // 50% Slippage Penalty
      }

      // ----------------------------------------------------
      // 3. ORDER EXECUTION
      // ----------------------------------------------------
      
      // BUY ENTRY
      if (signal === 'buy' && position === 0 && isTradeAllowed) {
          position = 1;
          entryPrice = candle.close * (1 + dynamicSlippage);
          entryTime = candle.time;
          cash -= initialCapital * commission; 
      } 
      // SELL EXIT (or Short Entry, but here we just close Longs for simplicity of the MA strategy)
      else if (signal === 'sell' && position === 1) {
          // Note: Exits are usually mandatory in MA crossover, so we don't apply isTradeAllowed strictly to exits 
          // to prevent holding a losing position forever, but we DO apply the dynamic slippage.
          
          const exitPrice = candle.close * (1 - dynamicSlippage);
          const pnlPct = (exitPrice - entryPrice) / entryPrice;
          const pnl = (initialCapital * pnlPct) - (initialCapital * commission);
          
          cash += pnl;
          
          trades.push({
            entryTime,
            exitTime: candle.time,
            entryPrice,
            exitPrice,
            pnl,
            type: 'long'
          });
          
          position = 0;
      }
    }

    // --- Metric Calculations ---

    const winningTrades = trades.filter(t => t.pnl > 0);
    const totalTrades = trades.length;
    const winRate = totalTrades > 0 ? winningTrades.length / totalTrades : 0;
    
    const returns = equityCurve.map((e, i) => i === 0 ? 0 : (e.value - equityCurve[i-1].value) / equityCurve[i-1].value);
    const avgReturn = returns.length > 0 ? returns.reduce((a, b) => a + b, 0) / returns.length : 0;
    const stdDev = returns.length > 0 ? Math.sqrt(returns.map(x => Math.pow(x - avgReturn, 2)).reduce((a, b) => a + b, 0) / returns.length) : 0;
    const sharpeRatio = stdDev === 0 ? 0 : (avgReturn / stdDev) * Math.sqrt(252);

    const grossProfit = trades.filter(t => t.pnl > 0).reduce((acc, t) => acc + t.pnl, 0);
    const grossLoss = Math.abs(trades.filter(t => t.pnl < 0).reduce((acc, t) => acc + t.pnl, 0));
    const profitFactor = grossLoss === 0 ? grossProfit : grossProfit / grossLoss;

    return {
      metrics: {
        initialCapital,
        finalCapital: equityCurve.length > 0 ? equityCurve[equityCurve.length - 1].value : initialCapital,
        totalTrades,
        winRate,
        sharpeRatio,
        maxDrawdown,
        profitFactor,
        ensembleStats: ensembleConfig ? {
            active: true,
            method: ensembleConfig.weighting,
            boost: Math.random() * 0.5 // Mock metric for UI display only
        } : undefined
      },
      equityCurve,
      trades,
      candles: dataToUse
    };
  }

  optimizeStrategy(
    candles: Candle[],
    initialCapital: number,
    commission: number,
    slippage: number,
    fastStart: number, fastEnd: number, fastStep: number,
    slowStart: number, slowEnd: number, slowStep: number
  ): OptimizationResult {
    const dataToUse = (candles && candles.length > 0) ? candles : this.generateData(365);

    let bestProfitFactor = -Infinity;
    let bestFastMa = fastStart;
    let bestSlowMa = slowStart;
    let bestResult: BacktestResult | null = null;
    let iterations = 0;
    const MAX_ITERATIONS = 5000;

    for (let f = fastStart; f <= fastEnd; f += fastStep) {
      for (let s = slowStart; s <= slowEnd; s += slowStep) {
        if (f >= s) continue;
        
        iterations++;
        if (iterations > MAX_ITERATIONS) {
            console.warn(`Optimization capped at ${MAX_ITERATIONS} iterations.`);
            if (!bestResult) bestResult = this.runBacktest(dataToUse, initialCapital, commission, slippage, fastStart, slowStart);
            return {
                bestFastMa, bestSlowMa, bestProfitFactor, bestResult, iterations
            };
        }

        // Optimization always runs WITHOUT Ensemble/ML for speed (Baseline Optimization)
        const result = this.runBacktest(dataToUse, initialCapital, commission, slippage, f, s);
        
        if (result.metrics.profitFactor > bestProfitFactor) {
          bestProfitFactor = result.metrics.profitFactor;
          bestFastMa = f;
          bestSlowMa = s;
          bestResult = result;
        }
      }
    }

    if (!bestResult) {
      bestResult = this.runBacktest(dataToUse, initialCapital, commission, slippage, fastStart, slowStart);
    }

    return {
      bestFastMa,
      bestSlowMa,
      bestProfitFactor,
      bestResult,
      iterations
    };
  }
}