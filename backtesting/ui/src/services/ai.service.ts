import { Injectable } from '@angular/core';
import { GoogleGenAI } from "@google/genai";

@Injectable({
  providedIn: 'root'
})
export class AiService {
  private ai: GoogleGenAI;

  constructor() {
    // API Key is strictly sourced from environment variables
    this.ai = new GoogleGenAI({ apiKey: process.env['API_KEY'] });
  }

  async analyzeBacktest(metrics: any): Promise<string> {
    const prompt = `
      You are 'Cthulhu AI', a senior quantitative trading analyst for an elite hedge fund.
      Analyze the following backtest results for an algorithmic strategy.

      METRICS:
      - Initial Capital: $${metrics.initialCapital}
      - Final Capital: $${metrics.finalCapital.toFixed(2)}
      - Total Trades: ${metrics.totalTrades}
      - Win Rate: ${(metrics.winRate * 100).toFixed(1)}%
      - Sharpe Ratio: ${metrics.sharpeRatio.toFixed(2)}
      - Max Drawdown: ${(metrics.maxDrawdown * 100).toFixed(1)}%
      - Profit Factor: ${metrics.profitFactor.toFixed(2)}

      TASK:
      Generate a comprehensive, "decorated", and well-structured HTML report.
      Do NOT use Markdown. Return raw HTML suitable for injection into a div.
      Use Tailwind CSS classes for styling. The background context is slate-900 (#0f172a).
      
      REPORT STRUCTURE & STYLING RULES:
      
      1. **Header & Grade**:
         - Create a flex container with a "Strategy Grade" (A+, A, B, C, D, F).
         - Grade logic: A (>2.0 Sharpe), B (>1.0 Sharpe), C (>0.5 Sharpe), else D/F.
         - Style the grade as a large, bold badge (e.g., text-4xl font-black). Color code it (Emerald for A/B, Yellow for C, Rose for D/F).
         - Include a short, punchy headline summarizing the performance next to the grade.

      2. **Executive Summary**:
         - A professional paragraph analyzing the core viability of the strategy.
         - Use <p class="text-slate-300 text-sm leading-relaxed mb-4">.

      3. **Key Insights Grid**:
         - A 2-column grid (<div class="grid grid-cols-2 gap-4 mb-4">).
         - Each item should be a small card (<div class="bg-slate-800 p-3 rounded border border-slate-700">).
         - Highlight Strengths (Green text) and Weaknesses (Red text).

      4. **Risk Assessment**:
         - Dedicated section for Drawdown and Exposure analysis.
         - If Max Drawdown > 20%, add a high visibility warning.

      5. **Tactical Recommendations**:
         - 3 bullet points on how to improve parameters or execution.
         - Use <ul class="list-none space-y-2"> with custom list markers.

      GENERAL STYLING:
      - Section Headers: <h4 class="text-emerald-500 font-bold uppercase text-xs tracking-widest mb-3 border-b border-slate-700 pb-1">
      - Text: text-slate-300, text-sm.
      - Bold/Numbers: font-mono text-white.
      
      Do not include <html>, <head>, or <body> tags. Start directly with the content container.
    `;

    try {
      const response = await this.ai.models.generateContent({
        model: 'gemini-2.5-flash',
        contents: prompt,
      });
      return response.text;
    } catch (error) {
      console.error('AI Error:', error);
      return `<div class="p-4 bg-red-900/20 border border-red-500 rounded text-red-200">
        <i class="fa-solid fa-triangle-exclamation mr-2"></i>
        <strong>System Error:</strong> Unable to connect to Cthulhu AI mainframe. Please check API configuration.
      </div>`;
    }
  }
}