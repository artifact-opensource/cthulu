"""
<<<<<<< HEAD
Cthulu Trading Dashboard v5.3.0
=======
Cthulu Trading Dashboard v6.0.0
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a

A comprehensive real-time trading dashboard that displays:
- Live positions from MT5 with real-time P&L
- Complete trade history from database
- All metrics from observability CSVs
- System health and performance indicators
- Manual trade controls

Designed to work with wizard → UI → Sentinel flow.
"""

import sys
import time
import threading
import re
import json
import os
import csv
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    import requests
except Exception:
    print("Tkinter not available; GUI cannot start.")
    sys.exit(2)

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cthulu.persistence.database import Database, TradeRecord

# Try to import MT5 for direct position reading
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

<<<<<<< HEAD
LOG_PATH = PROJECT_ROOT / 'cthulu.log'
=======
LOG_PATH = PROJECT_ROOT / 'Cthulu.log'
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
SUMMARY_PATH = PROJECT_ROOT / 'logs' / 'latest_summary.txt'
STRATEGY_INFO_PATH = PROJECT_ROOT / 'logs' / 'strategy_info.txt'

# CSV paths for metrics
METRICS_DIR = PROJECT_ROOT / 'metrics'
COMPREHENSIVE_CSV = METRICS_DIR / 'comprehensive_metrics.csv'
INDICATOR_CSV = METRICS_DIR / 'indicator_metrics.csv'
SYSTEM_HEALTH_CSV = METRICS_DIR / 'system_health.csv'

REFRESH_INTERVAL = 1500  # ms - faster refresh for real-time feel
TAIL_LINES = 150

RPC_ENDPOINTS = [
    'http://127.0.0.1:8181/trade',
    'http://127.0.0.1:8181/order',
    'http://127.0.0.1:8181/rpc/order',
    'http://127.0.0.1:8181/place_order',
]

# Theme colors - Cthulu dark purple theme
THEME_BG = '#0a0e14'
THEME_BG_SECONDARY = '#0f1720'
THEME_BG_TERTIARY = '#161f2d'
THEME_FG = '#e6eef6'
THEME_FG_DIM = '#8892a0'
ACCENT = '#8b5cf6'  # Purple
ACCENT_LIGHT = '#a78bfa'
SUCCESS = '#4ade80'  # Green
DANGER = '#f87171'   # Red
WARNING = '#fbbf24'  # Yellow
INFO = '#60a5fa'     # Blue


def tail_file(path: Path, lines: int = TAIL_LINES):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            filesize = f.tell()
            blocksize = 1024
            data = b''
            while filesize > 0 and lines >= 0:
                read_size = min(blocksize, filesize)
                f.seek(filesize - read_size)
                chunk = f.read(read_size)
                data = chunk + data
                filesize -= read_size
                if data.count(b'\n') > lines:
                    break
            text = data.decode('utf-8', errors='replace')
            return '\n'.join(text.splitlines()[-lines:])
    except FileNotFoundError:
        return ''
    except Exception as e:
        return f'Error reading log: {e}'


def read_summary(path: Path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return 'No summary available yet.'
    except Exception as e:
        return f'Error reading summary: {e}'


def read_latest_csv_row(csv_path: Path) -> dict:
    """Read the last row of a CSV file and return as dict."""
    try:
        if not csv_path.exists():
            return {}
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                return rows[-1]
        return {}
    except Exception:
        return {}


def get_mt5_positions():
    """Get live positions directly from MT5."""
    if not MT5_AVAILABLE:
        return []
    try:
        if not mt5.initialize():
            return []
        positions = mt5.positions_get()
        if positions is None:
            return []
        return list(positions)
    except Exception:
        return []


def get_mt5_account_info():
    """Get account info directly from MT5."""
    if not MT5_AVAILABLE:
        return None
    try:
        if not mt5.initialize():
            return None
        return mt5.account_info()
    except Exception:
        return None


def format_currency(value, symbol='$'):
    """Format currency value with color coding."""
    try:
        val = float(value)
        if val > 0:
            return f"+{symbol}{val:.2f}"
        elif val < 0:
            return f"-{symbol}{abs(val):.2f}"
        return f"{symbol}0.00"
    except (ValueError, TypeError):
        return f"{symbol}0.00"


def format_percent(value):
    """Format percentage value."""
    try:
        val = float(value)
        return f"{val:.2f}%"
    except (ValueError, TypeError):
        return "0.00%"


class CthuluGUI:
    """
<<<<<<< HEAD
    Comprehensive Cthulu Trading Dashboard v5.3.0
=======
    Comprehensive Cthulu Trading Dashboard v6.0.0
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
    
    Features:
    - Live MT5 positions with real-time P&L
    - Complete trade history from database
    - All metrics from observability CSVs
    - System health monitoring
    - Manual trade controls
    - Strategy and regime display
    """
    
    def __init__(self, root):
        self.root = root
<<<<<<< HEAD
        root.title('Cthulu — Trading Dashboard v5.3.0')
=======
        root.title('Cthulu — Trading Dashboard v6.0.0')
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
        root.geometry('1400x900')
        root.minsize(1200, 700)
        root.configure(bg=THEME_BG)

        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        # Fonts
        UI_FONT = ('Segoe UI', 10)
        HEADER_FONT = ('Segoe UI Semibold', 12)
        METRIC_FONT = ('Consolas', 11, 'bold')
        TREE_FONT = ('Segoe UI', 9)
        
        # Configure all ttk widgets for dark mode
        # Frame styling (critical for dark mode)
        style.configure('TFrame', background=THEME_BG)
        
        # Notebook styling for tabs
        style.configure('TNotebook', background=THEME_BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=THEME_BG_SECONDARY, foreground=THEME_FG,
                       padding=[15, 8], font=UI_FONT)
        style.map('TNotebook.Tab',
                  background=[('selected', ACCENT), ('active', THEME_BG_TERTIARY)],
                  foreground=[('selected', '#ffffff'), ('active', THEME_FG)])
        
        # Label styles
        style.configure('TLabel', background=THEME_BG, foreground=THEME_FG, font=UI_FONT)
        style.configure('Header.TLabel', font=HEADER_FONT, foreground=ACCENT, background=THEME_BG)
        style.configure('Metric.TLabel', font=METRIC_FONT, foreground=THEME_FG, background=THEME_BG)
        style.configure('Success.TLabel', foreground=SUCCESS, background=THEME_BG)
        style.configure('Danger.TLabel', foreground=DANGER, background=THEME_BG)
        
        # Entry styling
        style.configure('TEntry', fieldbackground=THEME_BG_TERTIARY, foreground=THEME_FG, insertcolor=THEME_FG)
        style.map('TEntry', 
                  fieldbackground=[('readonly', THEME_BG_TERTIARY), ('disabled', THEME_BG)],
                  foreground=[('readonly', THEME_FG_DIM), ('disabled', THEME_FG_DIM)])
        
        # Combobox styling
        style.configure('TCombobox', fieldbackground=THEME_BG_TERTIARY, foreground=THEME_FG, 
                       background=THEME_BG_TERTIARY, selectbackground=ACCENT, selectforeground='#ffffff')
        style.map('TCombobox',
                  fieldbackground=[('readonly', THEME_BG_TERTIARY), ('disabled', THEME_BG)],
                  selectbackground=[('readonly', ACCENT)],
                  selectforeground=[('readonly', '#ffffff')])
        
        # Button styling
        style.configure('TButton', background=THEME_BG_TERTIARY, foreground=THEME_FG, borderwidth=1, 
                       focuscolor='none', relief='flat', padding=[10, 5])
        style.configure('Accent.TButton', background=ACCENT, foreground='#ffffff', borderwidth=0,
                       focuscolor='none', relief='flat', padding=[12, 6])
        style.configure('Danger.TButton', background=DANGER, foreground='#ffffff', borderwidth=0,
                       focuscolor='none', relief='flat', padding=[10, 5])
        style.map('TButton',
                  background=[('active', THEME_BG_SECONDARY), ('pressed', THEME_BG)],
                  foreground=[('active', THEME_FG), ('pressed', THEME_FG)])
        style.map('Accent.TButton',
                  background=[('active', ACCENT_LIGHT), ('pressed', ACCENT)],
                  foreground=[('active', '#ffffff'), ('pressed', '#ffffff')])
        
        # Treeview styling
        style.configure('Treeview', background=THEME_BG_TERTIARY, fieldbackground=THEME_BG_TERTIARY, 
                   foreground=THEME_FG, rowheight=26, borderwidth=0, font=TREE_FONT)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), 
                   foreground=ACCENT, background=THEME_BG_SECONDARY, borderwidth=0, relief='flat')
        style.map('Treeview', 
                  background=[('selected', ACCENT)], 
                  foreground=[('selected', '#ffffff')])
        style.map('Treeview.Heading',
                  background=[('active', THEME_BG_TERTIARY)],
                  foreground=[('active', ACCENT_LIGHT)])
        
        # LabelFrame styling
        style.configure('TLabelframe', background=THEME_BG_SECONDARY, borderwidth=1)
        style.configure('TLabelframe.Label', background=THEME_BG_SECONDARY, foreground=ACCENT, font=HEADER_FONT)

        # Create notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Tab 1: Main Dashboard
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text=' Dashboard ')
        
        # Tab 2: Trades
        trades_frame = ttk.Frame(self.notebook)
        self.notebook.add(trades_frame, text=' Trades ')
        
        # Tab 3: Log
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text=' Log ')
        
        # === BUILD MAIN DASHBOARD TAB ===
        # Account Summary Row
        account_row = ttk.Frame(main_frame)
        account_row.pack(fill='x', padx=10, pady=10)
        
        self.account_labels = {}
        account_items = [
            ('Balance', '$0.00'),
            ('Equity', '$0.00'),
            ('Floating P/L', '$0.00'),
            ('Positions', '0'),
            ('Daily P/L', '$0.00'),
            ('Win Rate', '0%'),
        ]
        
        for i, (label, default) in enumerate(account_items):
            frame = tk.Frame(account_row, bg=THEME_BG_SECONDARY, padx=15, pady=10)
            frame.grid(row=0, column=i, padx=5, sticky='nsew')
            account_row.columnconfigure(i, weight=1)
            
            tk.Label(frame, text=label, font=('Segoe UI', 9), fg=THEME_FG_DIM, bg=THEME_BG_SECONDARY).pack(anchor='w')
            val_label = tk.Label(frame, text=default, font=('Consolas', 14, 'bold'), fg=SUCCESS, bg=THEME_BG_SECONDARY)
            val_label.pack(anchor='w')
            self.account_labels[label] = val_label
        
        # Strategy & Performance Row
        info_row = ttk.Frame(main_frame)
        info_row.pack(fill='x', padx=10, pady=5)
        
        # Strategy Panel
        strategy_panel = ttk.LabelFrame(info_row, text='Strategy Info')
        strategy_panel.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        self.strategy_info = {}
        for i, (label, default) in enumerate([
            ('Strategy:', '—'), ('Regime:', '—'), ('RSI:', '—'), ('ADX:', '—')
        ]):
            ttk.Label(strategy_panel, text=label).grid(row=i, column=0, sticky='e', padx=5, pady=2)
            val = ttk.Label(strategy_panel, text=default, style='Metric.TLabel')
            val.grid(row=i, column=1, sticky='w', padx=5, pady=2)
            self.strategy_info[label.replace(':', '')] = val
        
        # Performance Panel
        perf_panel = ttk.LabelFrame(info_row, text='Performance')
        perf_panel.pack(side='left', fill='both', expand=True, padx=(5, 0))
        
        self.perf_info = {}
        for i, (label, default) in enumerate([
            ('Total Trades:', '0'), ('Profit Factor:', '0.00'), ('Sharpe:', '0.00'), ('Max DD:', '0%')
        ]):
            ttk.Label(perf_panel, text=label).grid(row=i, column=0, sticky='e', padx=5, pady=2)
            val = ttk.Label(perf_panel, text=default, style='Metric.TLabel')
            val.grid(row=i, column=1, sticky='w', padx=5, pady=2)
            self.perf_info[label.replace(':', '')] = val
        
        # Open Positions Table
        pos_frame = ttk.LabelFrame(main_frame, text='Open Positions')
        pos_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        cols = ('ticket', 'symbol', 'type', 'volume', 'entry', 'current', 'pnl')
        self.positions_tree = ttk.Treeview(pos_frame, columns=cols, show='headings', height=8)
        
        for col, width in [('ticket', 100), ('symbol', 90), ('type', 60), ('volume', 70), ('entry', 100), ('current', 100), ('pnl', 90)]:
            self.positions_tree.heading(col, text=col.upper())
            self.positions_tree.column(col, width=width, anchor='center')
        
        self.positions_tree.tag_configure('profit', foreground=SUCCESS)
        self.positions_tree.tag_configure('loss', foreground=DANGER)
        self.positions_tree.tag_configure('even', background=THEME_BG_SECONDARY)
        self.positions_tree.tag_configure('odd', background=THEME_BG_TERTIARY)
        
        pos_scroll = ttk.Scrollbar(pos_frame, orient='vertical', command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=pos_scroll.set)
        self.positions_tree.pack(side='left', fill='both', expand=True)
        pos_scroll.pack(side='right', fill='y')
        
        # === BUILD TRADES TAB ===
        # Trade History
        history_label = ttk.Label(trades_frame, text='Trade History', style='Header.TLabel')
        history_label.pack(anchor='w', padx=10, pady=(10, 5))
        
        cols = ('time', 'symbol', 'side', 'volume', 'entry', 'exit', 'pnl', 'status')
        self.history_tree = ttk.Treeview(trades_frame, columns=cols, show='headings', height=15)
        
        for col, width in [('time', 140), ('symbol', 80), ('side', 60), ('volume', 60), ('entry', 100), ('exit', 100), ('pnl', 80), ('status', 80)]:
            self.history_tree.heading(col, text=col.upper())
            self.history_tree.column(col, width=width, anchor='center')
        
        self.history_tree.tag_configure('profit', foreground=SUCCESS)
        self.history_tree.tag_configure('loss', foreground=DANGER)
        self.history_tree.tag_configure('even', background=THEME_BG_SECONDARY)
        self.history_tree.tag_configure('odd', background=THEME_BG_TERTIARY)
        
        hist_scroll = ttk.Scrollbar(trades_frame, orient='vertical', command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=hist_scroll.set)
        self.history_tree.pack(side='left', fill='both', expand=True, padx=10, pady=5)
        hist_scroll.pack(side='right', fill='y', pady=5)
        
        # Manual Trade Panel
        trade_panel = ttk.LabelFrame(trades_frame, text='Manual Trade')
        trade_panel.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(trade_panel, text='Symbol:').grid(row=0, column=0, padx=5, pady=5)
        self.symbol_var = tk.StringVar(value='BTCUSD#')
        ttk.Entry(trade_panel, textvariable=self.symbol_var, width=12).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(trade_panel, text='Side:').grid(row=0, column=2, padx=5, pady=5)
        self.side_var = tk.StringVar(value='BUY')
        ttk.Combobox(trade_panel, textvariable=self.side_var, values=['BUY', 'SELL'], width=8).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(trade_panel, text='Volume:').grid(row=0, column=4, padx=5, pady=5)
        self.volume_var = tk.StringVar(value='0.01')
        ttk.Entry(trade_panel, textvariable=self.volume_var, width=8).grid(row=0, column=5, padx=5, pady=5)
        
        ttk.Label(trade_panel, text='SL:').grid(row=0, column=6, padx=5, pady=5)
        self.sl_var = tk.StringVar()
        ttk.Entry(trade_panel, textvariable=self.sl_var, width=10).grid(row=0, column=7, padx=5, pady=5)
        
        ttk.Label(trade_panel, text='TP:').grid(row=0, column=8, padx=5, pady=5)
        self.tp_var = tk.StringVar()
        ttk.Entry(trade_panel, textvariable=self.tp_var, width=10).grid(row=0, column=9, padx=5, pady=5)
        
        ttk.Button(trade_panel, text='Place Trade', style='Accent.TButton', command=self.place_manual_trade).grid(row=0, column=10, padx=10, pady=5)
        
        # === BUILD LOG TAB ===
        # Log controls
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(log_controls, text='Filter:').pack(side='left', padx=5)
        self.log_filter = tk.StringVar()
        ttk.Entry(log_controls, textvariable=self.log_filter, width=20).pack(side='left', padx=5)
        
        ttk.Button(log_controls, text='Clear', command=self._clear_log).pack(side='right', padx=5)
        ttk.Button(log_controls, text='Refresh', command=self._refresh_log).pack(side='right', padx=5)
        
        # Log text area
        self.log_text = ScrolledText(log_frame, height=30, bg=THEME_BG_TERTIARY, fg=THEME_FG, 
                                     insertbackground=THEME_FG, wrap='none', font=('Consolas', 9))
        xscroll = tk.Scrollbar(log_frame, orient='horizontal', command=self.log_text.xview)
        self.log_text.configure(xscrollcommand=xscroll.set)
        self.log_text.pack(fill='both', expand=True, padx=10, pady=5)
        xscroll.pack(fill='x', padx=10)
        
        self.log_text.tag_configure('ERROR', foreground=DANGER)
        self.log_text.tag_configure('WARNING', foreground=WARNING)
        self.log_text.tag_configure('SIGNAL', foreground=SUCCESS)

        # Close behavior
        root.protocol('WM_DELETE_WINDOW', self.on_close)

        # Database connection
        self.db = None
        try:
<<<<<<< HEAD
            db_paths = [PROJECT_ROOT / 'cthulu.db', PROJECT_ROOT / 'cthulu_ultra_aggressive.db']
=======
            db_paths = [PROJECT_ROOT / 'Cthulu.db', PROJECT_ROOT / 'Cthulu_ultra_aggressive.db']
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
            for p in db_paths:
                if p.exists():
                    self.db = Database(str(p))
                    break
        except Exception as e:
            print(f"Warning: Could not connect to database: {e}")

        # Start periodic update
        self.update()

    def update(self):
        """Main update loop."""
        try:
            self._update_account()
            self._update_positions()
            self._update_history()
            self._update_metrics()
            self._update_log_content()
        except Exception as e:
            print(f"Update error: {e}")
        
        self.root.after(REFRESH_INTERVAL, self.update)

    def _update_account(self):
        """Update account info from MT5 or CSV."""
        account = get_mt5_account_info()
        if account:
            self.account_labels['Balance'].configure(text=f'${account.balance:.2f}', fg=SUCCESS)
            self.account_labels['Equity'].configure(text=f'${account.equity:.2f}', fg=INFO)
            floating = account.equity - account.balance
            color = SUCCESS if floating >= 0 else DANGER
            self.account_labels['Floating P/L'].configure(text=format_currency(floating), fg=color)
        else:
            metrics = read_latest_csv_row(COMPREHENSIVE_CSV)
            if metrics:
                self.account_labels['Balance'].configure(text=f'${float(metrics.get("account_balance", 0)):.2f}')
                self.account_labels['Equity'].configure(text=f'${float(metrics.get("account_equity", 0)):.2f}')
        
        positions = get_mt5_positions()
        self.account_labels['Positions'].configure(text=str(len(positions)), fg=ACCENT)
        
        metrics = read_latest_csv_row(COMPREHENSIVE_CSV)
        if metrics:
            daily = float(metrics.get('daily_pnl', 0))
            color = SUCCESS if daily >= 0 else DANGER
            self.account_labels['Daily P/L'].configure(text=format_currency(daily), fg=color)
            win_rate = float(metrics.get('win_rate', 0))
            self.account_labels['Win Rate'].configure(text=f'{win_rate:.1f}%')

    def _update_positions(self):
        """Update positions from MT5."""
        positions = get_mt5_positions()
        
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        
        for idx, pos in enumerate(positions):
            try:
                pnl = pos.profit
                pnl_tag = 'profit' if pnl >= 0 else 'loss'
                row_tag = 'even' if idx % 2 == 0 else 'odd'
                pos_type = 'BUY' if pos.type == 0 else 'SELL'
                
                self.positions_tree.insert('', 'end', values=(
                    pos.ticket, pos.symbol, pos_type,
                    f'{pos.volume:.2f}', f'{pos.price_open:.5f}',
                    f'{pos.price_current:.5f}', f'{pnl:+.2f}'
                ), tags=(pnl_tag, row_tag))
            except Exception:
                pass

    def _update_history(self):
        """Update trade history from database."""
        if not self.db:
            return
        try:
            self.db.close()
<<<<<<< HEAD
            db_paths = [PROJECT_ROOT / 'cthulu.db', PROJECT_ROOT / 'cthulu_ultra_aggressive.db']
=======
            db_paths = [PROJECT_ROOT / 'Cthulu.db', PROJECT_ROOT / 'Cthulu_ultra_aggressive.db']
>>>>>>> 9435fea82335d1a7c54d2da9eee90b6620f2309a
            for p in db_paths:
                if p.exists():
                    self.db = Database(str(p))
                    break
            if not self.db:
                return
            
            trades = self.db.get_all_trades(limit=50)
            
            for item in self.history_tree.get_children():
                self.history_tree.delete(item)
            
            for idx, trade in enumerate(trades):
                pnl = trade.profit if trade.profit else 0
                pnl_tag = 'profit' if pnl >= 0 else 'loss'
                row_tag = 'even' if idx % 2 == 0 else 'odd'
                entry_time = str(trade.entry_time)[:16] if trade.entry_time else '—'
                
                self.history_tree.insert('', 'end', values=(
                    entry_time, trade.symbol, trade.side,
                    f'{trade.volume:.2f}',
                    f'{trade.entry_price:.5f}' if trade.entry_price else '—',
                    f'{trade.exit_price:.5f}' if trade.exit_price else '—',
                    f'{pnl:+.2f}', trade.status or '—'
                ), tags=(pnl_tag, row_tag))
        except Exception:
            pass

    def _update_metrics(self):
        """Update strategy info and performance metrics."""
        # Strategy info from file
        try:
            info = read_summary(STRATEGY_INFO_PATH)
            for line in info.splitlines():
                if 'Current Strategy:' in line:
                    self.strategy_info['Strategy'].configure(text=line.split(':', 1)[1].strip())
                elif 'Current Regime:' in line:
                    val = line.split(':', 1)[1].strip()
                    color = SUCCESS if 'up' in val.lower() else DANGER if 'down' in val.lower() else INFO
                    self.strategy_info['Regime'].configure(text=val, foreground=color)
        except Exception:
            pass
        
        # Metrics from CSV
        metrics = read_latest_csv_row(COMPREHENSIVE_CSV)
        if metrics:
            try:
                self.perf_info['Total Trades'].configure(text=str(metrics.get('total_trades', 0)))
                self.perf_info['Profit Factor'].configure(text=f'{float(metrics.get("profit_factor", 0)):.2f}')
                self.perf_info['Sharpe'].configure(text=f'{float(metrics.get("sharpe_ratio", 0)):.2f}')
                self.perf_info['Max DD'].configure(text=f'{float(metrics.get("max_drawdown_pct", 0)):.1f}%')
            except Exception:
                pass
        
        # Indicators from CSV
        ind = read_latest_csv_row(INDICATOR_CSV)
        if ind:
            try:
                self.strategy_info['RSI'].configure(text=f'{float(ind.get("rsi", 0)):.1f}')
                self.strategy_info['ADX'].configure(text=f'{float(ind.get("adx", 0)):.1f}')
            except Exception:
                pass

    def _update_log_content(self):
        """Update log viewer."""
        log_text = tail_file(LOG_PATH, TAIL_LINES)
        filter_text = self.log_filter.get().strip().lower()
        
        if filter_text:
            lines = [l for l in log_text.splitlines() if filter_text in l.lower()]
            log_text = '\n'.join(lines)
        
        try:
            self.log_text.configure(state='normal')
            self.log_text.delete('1.0', tk.END)
            for line in log_text.splitlines():
                if '[ERROR]' in line:
                    self.log_text.insert(tk.END, line + '\n', 'ERROR')
                elif '[WARNING]' in line:
                    self.log_text.insert(tk.END, line + '\n', 'WARNING')
                elif 'signal' in line.lower():
                    self.log_text.insert(tk.END, line + '\n', 'SIGNAL')
                else:
                    self.log_text.insert(tk.END, line + '\n')
            self.log_text.see(tk.END)
            self.log_text.configure(state='disabled')
        except Exception:
            pass

    def place_manual_trade(self):
        """Place a manual trade via RPC."""
        symbol = self.symbol_var.get().strip()
        side = self.side_var.get().strip().upper()
        volume = self.volume_var.get().strip()
        sl = self.sl_var.get().strip() or None
        tp = self.tp_var.get().strip() or None

        if not symbol or not volume:
            self._show_status('Symbol and volume required', 'error')
            return

        payload = {
            'symbol': symbol, 'side': side, 'volume': float(volume),
            'sl': float(sl) if sl else None, 'tp': float(tp) if tp else None,
            'order_type': 'market'
        }

        for ep in RPC_ENDPOINTS:
            try:
                r = requests.post(ep, json=payload, timeout=3)
                if r.status_code in (200, 201):
                    self._show_status('Order placed!', 'success')
                    return
            except Exception:
                pass
        self._show_status('Failed to place order', 'error')

    def _show_status(self, msg, level='info'):
        """Show status popup."""
        popup = tk.Toplevel(self.root)
        popup.title('Status')
        popup.geometry('250x70')
        popup.configure(bg=THEME_BG_SECONDARY)
        color = SUCCESS if level == 'success' else DANGER if level == 'error' else INFO
        tk.Label(popup, text=msg, font=('Segoe UI', 11), fg=color, bg=THEME_BG_SECONDARY).pack(pady=20)
        self.root.after(2500, popup.destroy)

    def _clear_log(self):
        """Clear log display."""
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')

    def _refresh_log(self):
        """Force refresh log."""
        self._update_log_content()

    def on_close(self):
        """Handle window close."""
        try:
            if self.db:
                self.db.close()
            if MT5_AVAILABLE:
                mt5.shutdown()
            self.root.destroy()
        finally:
            sys.exit(0)


def main():
    # Prevent multiple instances using a lock file
    lock_file = Path(__file__).parent.parent / 'logs' / '.gui_lock'
    debug_file = Path(__file__).parent.parent / 'logs' / 'gui_debug.log'
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Helper to write debug events
    def dbg(msg: str):
        try:
            with open(debug_file, 'a', encoding='utf-8') as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
        except Exception:
            pass

    dbg(f"GUI main() start (pid={os.getpid()})")

    # Check if another instance is running
    if lock_file.exists():
        try:
            # Check if the PID in lock file is still running
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Try to check if process exists
            if sys.platform == 'win32':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_INFORMATION = 0x0400
                handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, 0, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    print(f"Cthulu GUI is already running (PID: {pid})")
                    sys.exit(0)
            else:
                # Unix-like systems
                try:
                    os.kill(pid, 0)
                    print(f"Cthulu GUI is already running (PID: {pid})")
                    sys.exit(0)
                except OSError:
                    # Process doesn't exist, remove stale lock
                    lock_file.unlink()
        except Exception:
            # If we can't read/check the lock, remove it and continue
            try:
                lock_file.unlink()
            except Exception:
                pass
    
    # Write our PID to lock file
    try:
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    
    # Ensure lock is removed on exit
    def cleanup_lock(exit_msg: str = None):
        try:
            if exit_msg:
                dbg(f"cleanup_lock: {exit_msg}")
            lock_file.unlink()
        except Exception as e:
            dbg(f"cleanup_lock exception: {e}")
    
    import atexit
    atexit.register(cleanup_lock)
    
    # Install a global exception hook to log unexpected errors
    def gui_excepthook(exc_type, exc, tb):
        try:
            import traceback
            dbg("Unhandled exception in GUI: " + ''.join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass
        # Fall back to default handler
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = gui_excepthook

    root = tk.Tk()
    app = CthuluGUI(root)
    try:
        dbg("Entering mainloop")
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass
    finally:
        dbg("Exiting main()")
        cleanup_lock('normal exit')


if __name__ == '__main__':
    main()




