import { Component, ElementRef, effect, input, ViewChild, OnDestroy, AfterViewInit } from '@angular/core';
import * as d3 from 'd3';
import { Trade } from '../../services/herald.service';

@Component({
  selector: 'app-market-chart',
  standalone: true,
  template: `<div #chartContainer class="w-full h-full min-h-[300px] bg-herald-panel/50 rounded-lg overflow-hidden relative"></div>`
})
export class MarketChartComponent implements AfterViewInit, OnDestroy {
  data = input.required<{time: number, value: number}[]>();
  trades = input<Trade[]>([]);
  
  @ViewChild('chartContainer') private chartContainer!: ElementRef<HTMLDivElement>;
  
  private svg: any;
  private width = 0;
  private height = 0;
  private resizeObserver: ResizeObserver | undefined;
  
  // Track the ID of the most recent trade to detect new ones
  private lastTradeId: string | null = null;

  constructor() {
    effect(() => {
      const d = this.data();
      const t = this.trades();
      if (this.svg && d.length > 1) {
        this.updateChart(d, t);
      }
    });
  }

  ngAfterViewInit() {
    this.initChart();
    this.resizeObserver = new ResizeObserver(() => {
      this.resize();
    });
    this.resizeObserver.observe(this.chartContainer.nativeElement);
  }

  ngOnDestroy() {
    this.resizeObserver?.disconnect();
  }

  private resize() {
    if(!this.chartContainer) return;
    d3.select(this.chartContainer.nativeElement).selectAll('*').remove();
    this.initChart();
    // Keep lastTradeId to avoid re-flashing on resize
    this.updateChart(this.data(), this.trades());
  }

  private initChart() {
    const element = this.chartContainer.nativeElement;
    this.width = element.clientWidth;
    this.height = element.clientHeight;
    
    // Margins
    const margin = { top: 20, right: 60, bottom: 30, left: 10 };
    
    this.svg = d3.select(element)
      .append('svg')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `0 0 ${this.width} ${this.height}`)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);
      
    // Gradient definition
    const defs = this.svg.append("defs");
    const gradient = defs.append("linearGradient")
      .attr("id", "area-gradient")
      .attr("x1", "0%").attr("y1", "0%")
      .attr("x2", "0%").attr("y2", "100%");
      
    gradient.append("stop").attr("offset", "0%").attr("stop-color", "#00ff9d").attr("stop-opacity", 0.1);
    gradient.append("stop").attr("offset", "100%").attr("stop-color", "#00ff9d").attr("stop-opacity", 0);
  }

  private updateChart(data: {time: number, value: number}[], trades: Trade[]) {
    if (!this.svg) return;
    
    const margin = { top: 20, right: 60, bottom: 30, left: 10 };
    const innerWidth = this.width - margin.left - margin.right;
    const innerHeight = this.height - margin.top - margin.bottom;

    // --- Technical Indicator Calculations ---
    const windowSize = 20;
    const augmentedData = data.map((d, i, arr) => {
        if (i < windowSize - 1) return { ...d, sma: d.value, upper: d.value, lower: d.value };
        const slice = arr.slice(i - windowSize + 1, i + 1);
        const mean = d3.mean(slice, x => x.value) || d.value;
        const deviation = d3.deviation(slice, x => x.value) || 0;
        return {
            ...d,
            sma: mean,
            upper: mean + 2 * deviation,
            lower: mean - 2 * deviation
        };
    });

    // Scales
    const x = d3.scaleTime()
      .domain(d3.extent(data, d => new Date(d.time)) as [Date, Date])
      .range([0, innerWidth]);

    const yMin = d3.min(augmentedData, d => d.lower) || 0;
    const yMax = d3.max(augmentedData, d => d.upper) || 100;
    const padding = (yMax - yMin) * 0.1;

    const y = d3.scaleLinear()
      .domain([yMin - padding, yMax + padding])
      .range([innerHeight, 0]);

    // Cleanup Layers
    this.svg.selectAll('.axis').remove();
    this.svg.selectAll('.line-path').remove();
    this.svg.selectAll('.area-path').remove();
    this.svg.selectAll('.bollinger-area').remove();
    this.svg.selectAll('.sma-line').remove();
    this.svg.selectAll('.trade-marker-group').remove();
    this.svg.selectAll('.current-price-group').remove();
    // Note: We do NOT remove .flash-overlay here to allow the animation to persist across chart updates

    // --- 1. Flash Effect Logic (On Trade Execution) ---
    if (trades.length > 0) {
        const latestTrade = trades[0];
        
        // Only flash if we have tracked a previous trade and the ID has changed (new trade)
        if (this.lastTradeId !== null && this.lastTradeId !== latestTrade.id) {
            const isBuy = latestTrade.type === 'BUY';
            const solidColor = isBuy ? '#00ff9d' : '#ff3e3e';
            
            // Create flash overlay
            const flash = this.svg.append('rect')
              .attr('class', 'flash-overlay')
              .attr('x', -margin.left)
              .attr('y', -margin.top)
              .attr('width', this.width)
              .attr('height', this.height)
              .attr('fill', solidColor)
              .attr('opacity', 0.2)
              .style('pointer-events', 'none');

            flash.transition()
              .duration(500)
              .ease(d3.easeQuadOut)
              .attr('opacity', 0)
              .remove();
        }
        
        // Update tracker
        this.lastTradeId = latestTrade.id;
    } else {
        this.lastTradeId = null;
    }

    // --- Axes ---
    const xAxis = d3.axisBottom(x).ticks(5).tickSize(0).tickPadding(10);
    const yAxis = d3.axisRight(y).ticks(5).tickSize(innerWidth).tickPadding(10);

    // Custom Y Axis Grid
    this.svg.append('g')
      .attr('class', 'axis y-axis')
      .call(yAxis)
      .call((g: any) => g.select(".domain").remove())
      .call((g: any) => g.selectAll(".tick line")
        .attr("stroke-opacity", 0.05)
        .attr("stroke", "#ffffff")
        .attr("stroke-dasharray", "2,2"))
      .call((g: any) => g.selectAll(".tick text")
        .attr("x", innerWidth + 10)
        .attr("dy", -4)
        .style("fill", "#666")
        .style("font-family", "monospace"));

    // --- Chart Paths ---
    const line = d3.line<any>()
      .x(d => x(new Date(d.time)))
      .y(d => y(d.value))
      .curve(d3.curveMonotoneX);

    const area = d3.area<any>()
      .x(d => x(new Date(d.time)))
      .y0(innerHeight)
      .y1(d => y(d.value))
      .curve(d3.curveMonotoneX);

    const smaLine = d3.line<any>()
      .x(d => x(new Date(d.time)))
      .y(d => y(d.sma))
      .curve(d3.curveMonotoneX);

    const bollingerArea = d3.area<any>()
      .x(d => x(new Date(d.time)))
      .y0(d => y(d.lower))
      .y1(d => y(d.upper))
      .curve(d3.curveMonotoneX);

    // Draw Bollinger
    this.svg.append("path")
      .datum(augmentedData)
      .attr("class", "bollinger-area")
      .attr("fill", "rgba(255, 255, 255, 0.05)")
      .attr("stroke", "none")
      .attr("d", bollingerArea);
      
    // Draw Area
    this.svg.append("path")
      .datum(data)
      .attr("class", "area-path")
      .attr("fill", "url(#area-gradient)")
      .attr("d", area);

    // Draw Line
    this.svg.append("path")
      .datum(data)
      .attr("class", "line-path")
      .attr("fill", "none")
      .attr("stroke", "#00ff9d")
      .attr("stroke-width", 2)
      .attr("d", line);

    // Draw SMA
    this.svg.append("path")
       .datum(augmentedData)
       .attr("class", "sma-line")
       .attr("fill", "none")
       .attr("stroke", "#ffbf00")
       .attr("stroke-width", 1.5)
       .attr("stroke-dasharray", "4,4")
       .attr("d", smaLine);

    // --- 2. Live Price Indicator ---
    const cpGroup = this.svg.append('g').attr('class', 'current-price-group');
    const lastPoint = data[data.length - 1];
    const currentPrice = lastPoint.value;
    const cx = x(new Date(lastPoint.time));
    const cy = y(lastPoint.value);
    const tickColor = currentPrice >= (data[data.length-2]?.value || 0) ? '#00ff9d' : '#ff3e3e';

    // Horizontal Guideline
    cpGroup.append('line')
      .attr('x1', 0)
      .attr('x2', innerWidth + 60) // Extend to axis label
      .attr('y1', cy)
      .attr('y2', cy)
      .attr('stroke', tickColor)
      .attr('stroke-width', 0.5)
      .attr('stroke-dasharray', '2,2')
      .attr('opacity', 0.6);

    // Pulsating Dot Background
    const pulseCircle = cpGroup.append('circle')
      .attr('cx', cx)
      .attr('cy', cy)
      .attr('r', 4)
      .attr('fill', 'none')
      .attr('stroke', tickColor)
      .attr('stroke-width', 1);

    // Recursive function for pulsing animation since .repeat() is not available
    function repeat() {
      pulseCircle
        .attr('r', 4)
        .attr('opacity', 1)
        .transition()
        .duration(1000)
        .ease(d3.easeLinear)
        .attr('r', 12)
        .attr('opacity', 0)
        .on('end', repeat);
    }
    repeat();

    // Solid Dot
    cpGroup.append('circle')
      .attr('cx', cx)
      .attr('cy', cy)
      .attr('r', 3)
      .attr('fill', tickColor)
      .attr('stroke', '#000')
      .attr('stroke-width', 1);

    // Y-Axis Price Label Background
    cpGroup.append('rect')
      .attr('x', innerWidth)
      .attr('y', cy - 9)
      .attr('width', 60)
      .attr('height', 18)
      .attr('fill', tickColor)
      .attr('rx', 2);

    // Y-Axis Price Label Text
    cpGroup.append('text')
       .attr('x', innerWidth + 5)
       .attr('y', cy)
       .attr('dy', '0.32em')
       .attr('fill', '#000') // Black text on bright background
       .attr('font-family', 'monospace')
       .attr('font-size', '10px')
       .attr('font-weight', 'bold')
       .text(lastPoint.value.toFixed(2));


    // --- 3. Trades Visualization ---
    // Filter visible trades based on chart time domain
    const startTime = data[0].time;
    const visibleTrades = trades.filter(t => t.timestamp >= startTime);
    
    const tradeGroup = this.svg.append('g').attr('class', 'trade-marker-group');

    // Create groups for each trade
    const tradeNodes = tradeGroup.selectAll('g')
      .data(visibleTrades)
      .enter()
      .append('g')
      .attr('transform', (d: Trade) => {
         const tx = x(new Date(d.timestamp));
         const ty = y(d.price);
         return `translate(${tx},${ty})`;
      });

    // Draw Triangles
    tradeNodes.append('path')
      .attr('d', d3.symbol().type(d3.symbolTriangle).size(50))
      .attr('transform', (d: Trade) => d.type === 'SELL' ? 'rotate(180)' : 'rotate(0)')
      .attr('fill', (d: Trade) => d.type === 'BUY' ? '#00ff9d' : '#ff3e3e')
      .attr('stroke', '#000')
      .attr('stroke-width', 1);

    // Draw PnL Label for significant trades or all trades
    tradeNodes.append('text')
      .attr('x', 8)
      .attr('y', 3)
      .attr('font-family', 'monospace')
      .attr('font-size', '9px')
      .attr('fill', (d: Trade) => {
          if (!d.pnl) return '#888';
          return d.pnl >= 0 ? '#00ff9d' : '#ff3e3e';
      })
      .style('text-shadow', '0px 1px 2px rgba(0,0,0,0.8)')
      .text((d: Trade) => {
          const val = d.pnl || 0;
          return val === 0 ? '' : (val > 0 ? '+' : '') + val.toFixed(1);
      });
  }
}