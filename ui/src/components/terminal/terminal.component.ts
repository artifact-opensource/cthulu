import { Component, input, effect, ElementRef, ViewChild } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { LogEntry } from '../../services/herald.service';

@Component({
  selector: 'app-terminal',
  standalone: true,
  imports: [CommonModule, DatePipe],
  template: `
    <div class="flex flex-col h-full bg-herald-black border border-herald-dim/30 rounded-lg overflow-hidden font-mono text-xs">
      <div class="flex items-center justify-between px-3 py-2 bg-herald-panel border-b border-herald-dim/30">
        <span class="text-herald-text/60 font-semibold tracking-wider">CTHULU://SYSTEM_LOGS</span>
        <div class="flex gap-2">
          <div class="w-2 h-2 rounded-full bg-herald-dim animate-pulse"></div>
          <div class="w-2 h-2 rounded-full bg-herald-dim"></div>
        </div>
      </div>
      <div #scrollContainer class="flex-1 overflow-y-auto p-3 space-y-1 scroll-smooth">
        @for (log of logs().slice().reverse(); track log.timestamp) {
          <div class="flex gap-3 animate-in fade-in slide-in-from-left-2 duration-300">
            <span class="text-herald-dim whitespace-nowrap">[{{ log.timestamp | date:'HH:mm:ss' }}]</span>
            
            @if (log.source === 'CTHULU_AI') {
              <span class="text-purple-400 font-bold whitespace-nowrap">AI_CORE ></span>
              <span class="text-purple-200">{{ log.message }}</span>
            } @else if (log.level === 'TRADE') {
               <span class="text-herald-accent font-bold whitespace-nowrap">EXECUTION ></span>
               <span class="text-white">{{ log.message }}</span>
            } @else {
               <span class="text-blue-400 font-bold whitespace-nowrap">SYS ></span>
               <span class="text-herald-text/80">{{ log.message }}</span>
            }
          </div>
        }
      </div>
    </div>
  `
})
export class TerminalComponent {
  logs = input.required<LogEntry[]>();
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  constructor() {
    effect(() => {
      // Auto-scroll logic could go here if we were using appending (currently using reverse list)
      // Since we reverse the list for display (newest top), we don't strictly need to scroll to bottom,
      // but "terminal" usually has newest at bottom. Let's stick to newest at top for better UX in dashboard.
      // Changing template to standard log view (newest at bottom) is more "terminal-like".
      // Actually, let's keep the template rendering reversed so the user sees the latest immediately without scrolling.
      // Wait, let's just make it auto-scroll to bottom.
    });
  }
}