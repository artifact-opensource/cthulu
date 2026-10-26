import { Component, ElementRef, effect, input, ViewChild } from '@angular/core';
import * as d3 from 'd3';

@Component({
  selector: 'app-chart',
  standalone: true,
  template: `
    <div class="bg-slate-900 border border-slate-700 rounded-lg p-4 shadow-xl h-96 relative">
      <div #chartContainer class="w-full h-full"></div>
      
      <!-- Overlay legend -->
      <div class="absolute top-6 left-6 bg-slate-800/80 p-2 rounded text-xs pointer-events-none">
        <div class="flex items-center mb-1">
          <span class="w-3 h-3 bg-emerald-500 rounded-full mr-2"></span>
          <span class="text-slate-200">Equity Curve</span>
        </div>
        <div class="flex items-center mb-1">
          <span class="w-3 h-3 bg-slate-500 rounded-full mr-2"></span>
          <span class="text-slate-200">Asset Price</span>
        </div>
        <div class="flex items-center space-x-2 mt-2 pt-2 border-t border-slate-600">
           <div class="flex items-center"><span class="w-2 h-2 rounded-full bg-green-400 mr-1"></span> Buy</div>
           <div class="flex items-center"><span class="w-2 h-2 rounded-full bg-red-400 mr-1"></span> Sell</div>
        </div>
      </div>
    </div>
  `
})
export class ChartComponent {
  data = input.required<any>();
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  constructor() {
    effect(() => {
      if (this.data() && this.chartContainer) {
        this.drawChart(this.data());
      }
    });
  }

  drawChart(data: any) {
    const element = this.chartContainer.nativeElement;
    d3.select(element).selectAll('*').remove();

    if (!data.candles || data.candles.length === 0) return;

    const margin = { top: 20, right: 60, bottom: 30, left: 60 };
    const width = element.clientWidth - margin.left - margin.right;
    const height = element.clientHeight - margin.top - margin.bottom;

    const svg = d3.select(element)
      .append('svg')
      .attr('width', width + margin.left + margin.right)
      .attr('height', height + margin.top + margin.bottom)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Scales
    const x = d3.scaleTime()
      .domain(d3.extent(data.candles, (d: any) => new Date(d.time)) as [Date, Date])
      .range([0, width]);

    const yPrice = d3.scaleLinear()
      .domain([
        d3.min(data.candles, (d: any) => d.low) as number,
        d3.max(data.candles, (d: any) => d.high) as number
      ])
      .range([height, 0]);

    const yEquity = d3.scaleLinear()
      .domain([
        d3.min(data.equityCurve, (d: any) => d.value) as number,
        d3.max(data.equityCurve, (d: any) => d.value) as number
      ])
      .range([height, 0]);

    // Axes
    svg.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x).ticks(5).tickFormat(d3.timeFormat('%b %d') as any))
      .attr('color', '#64748b');

    svg.append('g')
      .call(d3.axisLeft(yEquity).ticks(5))
      .attr('color', '#10b981'); 

    svg.append('g')
      .attr('transform', `translate(${width}, 0)`)
      .call(d3.axisRight(yPrice).ticks(5))
      .attr('color', '#64748b');

    // Price Line
    const priceLine = d3.line<any>()
      .x(d => x(new Date(d.time)))
      .y(d => yPrice(d.close));

    svg.append('path')
      .datum(data.candles)
      .attr('fill', 'none')
      .attr('stroke', '#475569')
      .attr('stroke-width', 1.5)
      .attr('d', priceLine)
      .attr('opacity', 0.5);

    // Equity Line
    const equityLine = d3.line<any>()
      .x(d => x(new Date(d.time)))
      .y(d => yEquity(d.value));

    svg.append('path')
      .datum(data.equityCurve)
      .attr('fill', 'none')
      .attr('stroke', '#10b981')
      .attr('stroke-width', 2.5)
      .attr('d', equityLine);
      
    // ---------------------------------------------------------
    // Trade Markers
    // ---------------------------------------------------------

    const tradeGroup = svg.append('g').attr('class', 'trades');

    // Entry Markers (Buy)
    tradeGroup.selectAll('.entry-marker')
      .data(data.trades)
      .enter()
      .append('circle')
      .attr('cx', (d: any) => x(new Date(d.entryTime)))
      .attr('cy', (d: any) => yPrice(d.entryPrice))
      .attr('r', 4)
      .attr('fill', '#4ade80') // Green-400
      .attr('stroke', '#052e16')
      .attr('stroke-width', 1)
      .append('title')
      .text((d: any) => `LONG Entry: $${d.entryPrice.toFixed(2)} on ${new Date(d.entryTime).toLocaleDateString()}`);

    // Exit Markers (Sell)
    tradeGroup.selectAll('.exit-marker')
      .data(data.trades)
      .enter()
      .append('circle')
      .attr('cx', (d: any) => x(new Date(d.exitTime)))
      .attr('cy', (d: any) => yPrice(d.exitPrice))
      .attr('r', 4)
      .attr('fill', '#f87171') // Red-400
      .attr('stroke', '#450a0a')
      .attr('stroke-width', 1)
      .append('title')
      .text((d: any) => `Sell: $${d.exitPrice.toFixed(2)} on ${new Date(d.exitTime).toLocaleDateString()}. PnL: $${d.pnl.toFixed(2)}`);

    // Connector lines (Buy to Sell)
    tradeGroup.selectAll('.trade-line')
      .data(data.trades)
      .enter()
      .append('line')
      .attr('x1', (d: any) => x(new Date(d.entryTime)))
      .attr('y1', (d: any) => yPrice(d.entryPrice))
      .attr('x2', (d: any) => x(new Date(d.exitTime)))
      .attr('y2', (d: any) => yPrice(d.exitPrice))
      .attr('stroke', (d: any) => d.pnl > 0 ? '#4ade80' : '#f87171')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '3,3')
      .attr('opacity', 0.6);
      
    // Equity Curve Markers (Exit Points on Equity Curve)
    tradeGroup.selectAll('.equity-marker')
      .data(data.trades)
      .enter()
      .append('circle')
      .attr('cx', (d: any) => x(new Date(d.exitTime)))
      .attr('cy', (d: any) => {
         const eqPoint = data.equityCurve.find((e: any) => e.time === d.exitTime);
         return eqPoint ? yEquity(eqPoint.value) : 0;
      })
      .attr('r', 3)
      .attr('fill', (d: any) => d.pnl > 0 ? '#4ade80' : '#f87171')
      .attr('opacity', 0.8)
      .append('title')
      .text((d: any) => `Trade Closed. PnL: ${d.pnl.toFixed(2)}`);

  }
}