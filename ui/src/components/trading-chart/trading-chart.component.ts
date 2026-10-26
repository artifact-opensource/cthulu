/**
 * TradingView Widget Component
 * 
 * Embeds the official TradingView Advanced Chart widget with built-in data.
 * Cthulu can overlay its analysis via the widget's API.
 * 
 * Features:
 * - Full TradingView chart with real-time data (no MT5 needed)
 * - Drawing tools available
 * - Cthulu zone overlay panel
 */

import {
  Component,
  ElementRef,
  ViewChild,
  OnDestroy,
  input,
  signal,
  AfterViewInit,
  effect
} from '@angular/core';

// Zone data from Chart Manager
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

declare const TradingView: any;

@Component({
  selector: 'app-trading-chart',
  standalone: true,
  template: `
    <div class="relative w-full h-full">
      <!-- TradingView Widget Container -->
      <div #tvContainer id="tradingview_widget" class="w-full h-full"></div>
      
      <!-- Cthulu Zone Overlay Panel -->
      @if (showZonePanel() && activeZones().length > 0) {
        <div class="absolute top-2 right-2 z-20 bg-black/80 backdrop-blur rounded border border-herald-dim/50 p-3 max-w-[220px]">
          <div class="flex items-center justify-between mb-2">
            <span class="text-[10px] font-mono text-herald-accent uppercase tracking-wider">Cthulu Zones</span>
            <button 
              (click)="toggleZonePanel()"
              class="text-herald-text/50 hover:text-herald-text text-xs"
            >×</button>
          </div>
          @for (zone of activeZones(); track zone.id) {
            <div class="flex items-center gap-2 py-1 border-b border-herald-dim/20 last:border-0">
              <span class="w-3 h-3 rounded" [style.background-color]="zone.color" [style.opacity]="0.7"></span>
              <div class="flex-1 min-w-0">
                <div class="text-[10px] font-mono text-herald-text/90 truncate">{{ zone.type }}</div>
                <div class="text-[9px] font-mono text-herald-text/50">
                  {{ zone.lower.toFixed(2) }} - {{ zone.upper.toFixed(2) }}
                </div>
              </div>
              <div class="text-[9px] font-mono" [class.text-green-400]="zone.state === 'ACTIVE'" [class.text-yellow-400]="zone.state === 'PENDING'">
                {{ (zone.strength * 100).toFixed(0) }}%
              </div>
            </div>
          }
          
          <!-- Levels Section -->
          @if (activeLevels().length > 0) {
            <div class="mt-2 pt-2 border-t border-herald-dim/30">
              <div class="text-[9px] font-mono text-herald-text/50 mb-1">KEY LEVELS</div>
              @for (level of activeLevels().slice(0, 5); track level.price) {
                <div class="flex items-center gap-2 text-[9px] font-mono">
                  <span class="w-2 h-0.5" [style.background-color]="level.color"></span>
                  <span class="text-herald-text/70">{{ level.label }}</span>
                  <span class="text-herald-text/50 ml-auto">{{ level.price.toFixed(2) }}</span>
                </div>
              }
            </div>
          }
        </div>
      }
      
      <!-- Toggle Button (when panel is hidden) -->
      @if (!showZonePanel() && (activeZones().length > 0 || activeLevels().length > 0)) {
        <button 
          (click)="toggleZonePanel()"
          class="absolute top-2 right-2 z-20 px-2 py-1 bg-black/60 backdrop-blur text-[10px] font-mono rounded border border-herald-dim/30 text-herald-accent hover:bg-black/80 transition-colors"
        >
          ZONES ({{ activeZones().length }})
        </button>
      }
    </div>
  `,
  styles: [`
    :host {
      display: block;
      width: 100%;
      height: 100%;
    }
    
    #tradingview_widget {
      min-height: 400px;
    }
  `]
})
export class TradingChartComponent implements AfterViewInit, OnDestroy {
  // Inputs - keeping for compatibility but widget handles its own data
  symbol = input<string>('BTCUSD');
  timeframe = input<string>('30');
  drawings = input<ChartDrawings | null>(null);

  // UI State
  showZonePanel = signal(true);
  activeZones = signal<ChartZone[]>([]);
  activeLevels = signal<ChartLevel[]>([]);

  @ViewChild('tvContainer') private tvContainer!: ElementRef<HTMLDivElement>;

  private widget: any = null;

  constructor() {
    // React to drawings changes
    effect(() => {
      const dr = this.drawings();
      if (dr) {
        this.activeZones.set(dr.zones?.filter(z => z.state !== 'BROKEN' && z.state !== 'EXPIRED') || []);
        this.activeLevels.set(dr.levels || []);
      }
    });
  }

  ngAfterViewInit() {
    this.loadTradingViewScript().then(() => {
      this.initWidget();
    });
  }

  ngOnDestroy() {
    // Widget cleanup handled by TradingView
  }

  toggleZonePanel() {
    this.showZonePanel.set(!this.showZonePanel());
  }

  private loadTradingViewScript(): Promise<void> {
    return new Promise((resolve, reject) => {
      // Check if already loaded
      if (typeof TradingView !== 'undefined') {
        resolve();
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Failed to load TradingView script'));
      document.head.appendChild(script);
    });
  }

  private initWidget() {
    if (!this.tvContainer) return;

    const container = this.tvContainer.nativeElement;
    
    // Map symbol to TradingView format
    const tvSymbol = this.mapSymbol(this.symbol());
    
    // Map timeframe to TradingView interval
    const interval = this.mapTimeframe(this.timeframe());

    this.widget = new TradingView.widget({
      container_id: 'tradingview_widget',
      width: '100%',
      height: '100%',
      symbol: tvSymbol,
      interval: interval,
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: '1', // Candlesticks
      locale: 'en',
      toolbar_bg: '#0a0a0a',
      enable_publishing: false,
      allow_symbol_change: true,
      save_image: false,
      hide_side_toolbar: false,
      withdateranges: true,
      details: false,
      hotlist: false,
      calendar: false,
      studies: [],
      show_popup_button: false,
      popup_width: '1000',
      popup_height: '650',
      // Dark theme overrides
      overrides: {
        'paneProperties.background': '#0a0a0a',
        'paneProperties.backgroundType': 'solid',
        'paneProperties.vertGridProperties.color': 'rgba(255, 255, 255, 0.03)',
        'paneProperties.horzGridProperties.color': 'rgba(255, 255, 255, 0.03)',
        'scalesProperties.textColor': '#666666',
        'mainSeriesProperties.candleStyle.upColor': '#00ff9d',
        'mainSeriesProperties.candleStyle.downColor': '#ff3e3e',
        'mainSeriesProperties.candleStyle.borderUpColor': '#00ff9d',
        'mainSeriesProperties.candleStyle.borderDownColor': '#ff3e3e',
        'mainSeriesProperties.candleStyle.wickUpColor': '#00ff9d',
        'mainSeriesProperties.candleStyle.wickDownColor': '#ff3e3e'
      }
    });
  }

  private mapSymbol(symbol: string): string {
    // Map common symbols to TradingView format
    const symbolMap: { [key: string]: string } = {
      'BTCUSD': 'BINANCE:BTCUSDT',
      'BTCUSD#': 'BINANCE:BTCUSDT',
      'BTCUSDT': 'BINANCE:BTCUSDT',
      'ETHUSD': 'BINANCE:ETHUSDT',
      'EURUSD': 'FX:EURUSD',
      'GBPUSD': 'FX:GBPUSD',
      'XAUUSD': 'OANDA:XAUUSD',
      'US30': 'TVC:DJI',
      'NAS100': 'NASDAQ:NDX'
    };
    
    return symbolMap[symbol.toUpperCase()] || `BINANCE:${symbol.replace('#', '')}USDT`;
  }

  private mapTimeframe(tf: string): string {
    // Map timeframe to TradingView interval
    const tfMap: { [key: string]: string } = {
      'M1': '1',
      'M5': '5',
      'M15': '15',
      'M30': '30',
      '30': '30',
      'H1': '60',
      'H4': '240',
      'D1': 'D',
      'W1': 'W',
      'MN1': 'M'
    };
    
    return tfMap[tf.toUpperCase()] || '30';
  }
}
