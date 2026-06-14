"""
SENTINEL DASHBOARD GUI
======================
Real-time Tkinter GUI for monitoring Cthulu trading system.
Displays system health, process states, and provides control buttons.

NOTE: Sentinel does NOT start Cthulu. It only:
- Monitors health
- Recovers from crashes (Force Recovery)
- Emergency stops (Emergency Stop)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
import sys
import os

if TYPE_CHECKING:
    from sentinel.core.guardian import SentinelGuardian


class SentinelDashboard:
    """
    Real-time Sentinel Monitoring Dashboard
    
    Features:
    - Live system state display with color-coded indicators
    - Process monitoring (Cthulu, MT5)
    - CPU/Memory metrics
    - Crash history and recovery status
    - Force Recovery button (restarts with last known config)
    - Emergency Stop button
    - Auto-restart toggle
    - Auto-refresh every 2 seconds
    """
    
    # Color scheme
    COLORS = {
        'bg_dark': '#1a1a2e',
        'bg_panel': '#16213e',
        'bg_card': '#0f3460',
        'accent': '#e94560',
        'accent_green': '#00d9ff',
        'text': '#ffffff',
        'text_dim': '#8892b0',
        'healthy': '#00ff88',
        'warning': '#ffaa00',
        'critical': '#ff4444',
        'offline': '#666666',
        'recovering': '#aa88ff'
    }
    
    STATE_COLORS = {
        'HEALTHY': 'healthy',
        'DEGRADED': 'warning', 
        'CRITICAL': 'critical',
        'RECOVERING': 'recovering',
        'OFFLINE': 'offline',
        'RUNNING': 'healthy',
        'STARTING': 'warning',
        'STOPPED': 'offline',
        'CRASHED': 'critical',
        'UNRESPONSIVE': 'critical',
        'CONNECTED': 'healthy',
        'DISCONNECTED': 'critical',
        'ALGO_ENABLED': 'healthy',
        'ALGO_DISABLED': 'warning',
        'NOT_RUNNING': 'offline'
    }
    
    def __init__(self, guardian: Optional['SentinelGuardian'] = None):
        self.guardian = guardian
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        
        # Create main window
        self.root = tk.Tk()
        
        # Auto-restart enabled by default (must be after Tk() is created)
        self.auto_restart_enabled = tk.BooleanVar(value=True)
        self.root.title("🛡️ SENTINEL - Cthulu Guardian")
        self.root.geometry("900x700")
        self.root.configure(bg=self.COLORS['bg_dark'])
        self.root.resizable(True, True)
        
        # Set minimum size
        self.root.minsize(800, 600)
        
        # Configure grid weights
        self.root.grid_rowconfigure(0, weight=0)  # Header
        self.root.grid_rowconfigure(1, weight=1)  # Main content
        self.root.grid_rowconfigure(2, weight=0)  # Status bar
        self.root.grid_columnconfigure(0, weight=1)
        
        # Create UI components
        self._create_header()
        self._create_main_content()
        self._create_status_bar()
        
        # Initialize with default values
        self._update_display({
            'system_state': 'OFFLINE',
            'cthulu_state': 'STOPPED',
            'mt5_state': 'NOT_RUNNING',
            'cthulu_pid': None,
            'mt5_pid': None,
            'cpu_percent': 0,
            'memory_percent': 0,
            'uptime_seconds': 0,
            'crash_count': 0,
            'last_crash': None,
            'recovery_attempts': 0,
            'error_log': [],
            'last_known_config': 'config.json',
            'auto_restart_enabled': True
        })
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_header(self):
        """Create header section"""
        header_frame = tk.Frame(self.root, bg=self.COLORS['bg_panel'], height=80)
        header_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=10)
        header_frame.grid_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="🛡️ SENTINEL GUARDIAN",
            font=('Segoe UI', 24, 'bold'),
            fg=self.COLORS['accent'],
            bg=self.COLORS['bg_panel']
        )
        title_label.pack(side='left', padx=20, pady=15)
        
        # System state indicator (large)
        self.state_frame = tk.Frame(header_frame, bg=self.COLORS['bg_panel'])
        self.state_frame.pack(side='right', padx=20)
        
        self.state_label = tk.Label(
            self.state_frame,
            text="OFFLINE",
            font=('Segoe UI', 18, 'bold'),
            fg=self.COLORS['offline'],
            bg=self.COLORS['bg_panel']
        )
        self.state_label.pack()
        
        self.state_indicator = tk.Label(
            self.state_frame,
            text="●",
            font=('Segoe UI', 32),
            fg=self.COLORS['offline'],
            bg=self.COLORS['bg_panel']
        )
        self.state_indicator.pack()
    
    def _create_main_content(self):
        """Create main content area"""
        main_frame = tk.Frame(self.root, bg=self.COLORS['bg_dark'])
        main_frame.grid(row=1, column=0, sticky='nsew', padx=10, pady=5)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # Process status panel (top-left)
        self._create_process_panel(main_frame)
        
        # Metrics panel (top-right)
        self._create_metrics_panel(main_frame)
        
        # Recovery panel (bottom-left)
        self._create_recovery_panel(main_frame)
        
        # Control panel (bottom-right)
        self._create_control_panel(main_frame)
    
    def _create_card(self, parent, title, row, col):
        """Create a styled card frame"""
        card = tk.Frame(parent, bg=self.COLORS['bg_card'], relief='flat', bd=2)
        card.grid(row=row, column=col, sticky='nsew', padx=5, pady=5)
        card.grid_columnconfigure(0, weight=1)
        
        # Card title
        title_label = tk.Label(
            card,
            text=title,
            font=('Segoe UI', 12, 'bold'),
            fg=self.COLORS['accent_green'],
            bg=self.COLORS['bg_card']
        )
        title_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        # Content frame
        content = tk.Frame(card, bg=self.COLORS['bg_card'])
        content.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        
        return content
    
    def _create_process_panel(self, parent):
        """Create process status panel"""
        content = self._create_card(parent, "PROCESS STATUS", 0, 0)
        
        # Cthulu status
        cthulu_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        cthulu_frame.pack(fill='x', pady=5)
        
        tk.Label(
            cthulu_frame,
            text="Cthulu:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.cthulu_status = tk.Label(
            cthulu_frame,
            text="STOPPED",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['offline'],
            bg=self.COLORS['bg_card']
        )
        self.cthulu_status.pack(side='left', padx=10)
        
        self.cthulu_pid_label = tk.Label(
            cthulu_frame,
            text="PID: --",
            font=('Segoe UI', 10),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_card']
        )
        self.cthulu_pid_label.pack(side='right')
        
        # MT5 status
        mt5_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        mt5_frame.pack(fill='x', pady=5)
        
        tk.Label(
            mt5_frame,
            text="MetaTrader 5:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.mt5_status = tk.Label(
            mt5_frame,
            text="NOT RUNNING",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['offline'],
            bg=self.COLORS['bg_card']
        )
        self.mt5_status.pack(side='left', padx=10)
        
        self.mt5_pid_label = tk.Label(
            mt5_frame,
            text="PID: --",
            font=('Segoe UI', 10),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_card']
        )
        self.mt5_pid_label.pack(side='right')
        
        # Algo status
        algo_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        algo_frame.pack(fill='x', pady=5)
        
        tk.Label(
            algo_frame,
            text="Algo Trading:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.algo_status = tk.Label(
            algo_frame,
            text="UNKNOWN",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_card']
        )
        self.algo_status.pack(side='left', padx=10)
        
        # Last known config
        config_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        config_frame.pack(fill='x', pady=5)
        
        tk.Label(
            config_frame,
            text="📄 Config:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.config_label = tk.Label(
            config_frame,
            text="config.json",
            font=('Segoe UI', 10),
            fg=self.COLORS['accent_green'],
            bg=self.COLORS['bg_card']
        )
        self.config_label.pack(side='right')
    
    def _create_metrics_panel(self, parent):
        """Create system metrics panel"""
        content = self._create_card(parent, "SYSTEM METRICS", 0, 1)
        
        # CPU
        cpu_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        cpu_frame.pack(fill='x', pady=5)
        
        tk.Label(
            cpu_frame,
            text="CPU Usage:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.cpu_label = tk.Label(
            cpu_frame,
            text="0%",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['healthy'],
            bg=self.COLORS['bg_card']
        )
        self.cpu_label.pack(side='right')
        
        # Memory
        mem_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        mem_frame.pack(fill='x', pady=5)
        
        tk.Label(
            mem_frame,
            text="Memory Usage:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.mem_label = tk.Label(
            mem_frame,
            text="0%",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['healthy'],
            bg=self.COLORS['bg_card']
        )
        self.mem_label.pack(side='right')
        
        # Uptime
        uptime_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        uptime_frame.pack(fill='x', pady=5)
        
        tk.Label(
            uptime_frame,
            text="Guardian Uptime:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.uptime_label = tk.Label(
            uptime_frame,
            text="--:--:--",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['accent_green'],
            bg=self.COLORS['bg_card']
        )
        self.uptime_label.pack(side='right')
    
    def _create_recovery_panel(self, parent):
        """Create recovery status panel"""
        content = self._create_card(parent, "RECOVERY STATUS", 1, 0)
        
        # Crash count
        crash_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        crash_frame.pack(fill='x', pady=5)
        
        tk.Label(
            crash_frame,
            text="Total Crashes:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.crash_count_label = tk.Label(
            crash_frame,
            text="0",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['healthy'],
            bg=self.COLORS['bg_card']
        )
        self.crash_count_label.pack(side='right')
        
        # Recovery attempts
        recovery_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        recovery_frame.pack(fill='x', pady=5)
        
        tk.Label(
            recovery_frame,
            text="Recovery Attempts:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.recovery_label = tk.Label(
            recovery_frame,
            text="0",
            font=('Segoe UI', 11, 'bold'),
            fg=self.COLORS['healthy'],
            bg=self.COLORS['bg_card']
        )
        self.recovery_label.pack(side='right')
        
        # Last crash
        last_crash_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        last_crash_frame.pack(fill='x', pady=5)
        
        tk.Label(
            last_crash_frame,
            text="Last Crash:",
            font=('Segoe UI', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg_card']
        ).pack(side='left')
        
        self.last_crash_label = tk.Label(
            last_crash_frame,
            text="Never",
            font=('Segoe UI', 10),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_card']
        )
        self.last_crash_label.pack(side='right')
        
        # Error log (scrollable)
        log_label = tk.Label(
            content,
            text="Recent Errors:",
            font=('Segoe UI', 10),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_card']
        )
        log_label.pack(anchor='w', pady=(10, 5))
        
        self.error_log = tk.Text(
            content,
            height=4,
            font=('Consolas', 9),
            bg=self.COLORS['bg_dark'],
            fg=self.COLORS['critical'],
            wrap='word',
            state='disabled'
        )
        self.error_log.pack(fill='both', expand=True)
    
    def _create_control_panel(self, parent):
        """Create control buttons panel - NO START BUTTON, only recovery controls"""
        content = self._create_card(parent, "CONTROLS", 1, 1)
        
        # Info label
        info_label = tk.Label(
            content,
            text="Sentinel monitors and recovers.\nStart Cthulu manually.",
            font=('Segoe UI', 9),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_card'],
            justify='center'
        )
        info_label.pack(pady=(0, 10))
        
        # Button style
        btn_style = {
            'font': ('Segoe UI', 10, 'bold'),
            'width': 20,
            'height': 2,
            'cursor': 'hand2',
            'relief': 'flat',
            'bd': 0
        }
        
        # Auto-restart checkbox (default ON)
        auto_restart_frame = tk.Frame(content, bg=self.COLORS['bg_card'])
        auto_restart_frame.pack(pady=(0, 15))
        
        self.auto_restart_checkbox = tk.Checkbutton(
            auto_restart_frame,
            text="Auto-Restart on Crash",
            variable=self.auto_restart_enabled,
            font=('Segoe UI', 10, 'bold'),
            fg=self.COLORS['accent_green'],
            bg=self.COLORS['bg_card'],
            activebackground=self.COLORS['bg_card'],
            activeforeground=self.COLORS['healthy'],
            selectcolor=self.COLORS['bg_dark'],
            cursor='hand2',
            command=self._toggle_auto_restart
        )
        self.auto_restart_checkbox.pack()
        
        # Auto-restart status label
        self.auto_restart_status = tk.Label(
            auto_restart_frame,
            text="Auto-restart ENABLED",
            font=('Segoe UI', 9),
            fg=self.COLORS['healthy'],
            bg=self.COLORS['bg_card']
        )
        self.auto_restart_status.pack()
        
        # Force Recovery - MAIN ACTION BUTTON
        self.recover_btn = tk.Button(
            content,
            text="Force Recovery",
            bg=self.COLORS['warning'],
            fg=self.COLORS['bg_dark'],
            command=self._force_recovery,
            **btn_style
        )
        self.recover_btn.pack(pady=8)
        
        # Emergency Stop - RED BUTTON
        self.stop_btn = tk.Button(
            content,
            text="Emergency Stop",
            bg=self.COLORS['critical'],
            fg=self.COLORS['text'],
            command=self._emergency_stop,
            **btn_style
        )
        self.stop_btn.pack(pady=8)
        
        # Enable Algo (helper)
        self.algo_btn = tk.Button(
            content,
            text="Enable Algo Trading",
            bg=self.COLORS['accent_green'],
            fg=self.COLORS['bg_dark'],
            command=self._enable_algo,
            **btn_style
        )
        self.algo_btn.pack(pady=8)
    
    def _toggle_auto_restart(self):
        """Handle auto-restart checkbox toggle"""
        enabled = self.auto_restart_enabled.get()
        if enabled:
            self.auto_restart_status.config(
                text="✅ Auto-restart ENABLED",
                fg=self.COLORS['healthy']
            )
            if self.guardian:
                self.guardian.auto_restart = True
            self.status_text.config(text="🔄 Auto-restart enabled - Cthulu will auto-recover from crashes")
        else:
            self.auto_restart_status.config(
                text="⚠️ Auto-restart DISABLED",
                fg=self.COLORS['warning']
            )
            if self.guardian:
                self.guardian.auto_restart = False
            self.status_text.config(text="⚠️ Auto-restart disabled - manual intervention required on crash")
    
    def _create_status_bar(self):
        """Create status bar at bottom"""
        status_frame = tk.Frame(self.root, bg=self.COLORS['bg_panel'], height=30)
        status_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)
        
        self.status_text = tk.Label(
            status_frame,
            text="⏳ Initializing...",
            font=('Segoe UI', 9),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_panel']
        )
        self.status_text.pack(side='left', padx=10, pady=5)
        
        self.time_label = tk.Label(
            status_frame,
            text="",
            font=('Segoe UI', 9),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_panel']
        )
        self.time_label.pack(side='right', padx=10, pady=5)
    
    def _update_display(self, data: dict):
        """Update all display elements with new data"""
        try:
            # System state
            system_state = data.get('system_state', 'OFFLINE')
            state_color = self.COLORS.get(self.STATE_COLORS.get(system_state, 'offline'), self.COLORS['offline'])
            self.state_label.config(text=system_state, fg=state_color)
            self.state_indicator.config(fg=state_color)
            
            # Cthulu status
            cthulu_state = data.get('cthulu_state', 'STOPPED')
            cthulu_color = self.COLORS.get(self.STATE_COLORS.get(cthulu_state, 'offline'), self.COLORS['offline'])
            self.cthulu_status.config(text=cthulu_state, fg=cthulu_color)
            
            cthulu_pid = data.get('cthulu_pid')
            self.cthulu_pid_label.config(text=f"PID: {cthulu_pid or '--'}")
            
            # MT5 status
            mt5_state = data.get('mt5_state', 'NOT_RUNNING')
            mt5_color = self.COLORS.get(self.STATE_COLORS.get(mt5_state, 'offline'), self.COLORS['offline'])
            self.mt5_status.config(text=mt5_state.replace('_', ' '), fg=mt5_color)
            
            mt5_pid = data.get('mt5_pid')
            self.mt5_pid_label.config(text=f"PID: {mt5_pid or '--'}")
            
            # Algo status
            if mt5_state == 'ALGO_ENABLED':
                self.algo_status.config(text="ENABLED", fg=self.COLORS['healthy'])
            elif mt5_state == 'ALGO_DISABLED':
                self.algo_status.config(text="DISABLED", fg=self.COLORS['warning'])
            else:
                self.algo_status.config(text="UNKNOWN", fg=self.COLORS['text_dim'])
            
            # Last known config
            last_config = data.get('last_known_config', 'config.json')
            self.config_label.config(text=last_config)
            
            # Metrics
            cpu = data.get('cpu_percent', 0)
            cpu_color = self.COLORS['healthy'] if cpu < 70 else (self.COLORS['warning'] if cpu < 90 else self.COLORS['critical'])
            self.cpu_label.config(text=f"{cpu:.1f}%", fg=cpu_color)
            
            mem = data.get('memory_percent', 0)
            mem_color = self.COLORS['healthy'] if mem < 70 else (self.COLORS['warning'] if mem < 90 else self.COLORS['critical'])
            self.mem_label.config(text=f"{mem:.1f}%", fg=mem_color)
            
            # Uptime
            uptime_secs = data.get('uptime_seconds', 0)
            hours, remainder = divmod(int(uptime_secs), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.uptime_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Recovery info
            crash_count = data.get('crash_count', 0)
            crash_color = self.COLORS['healthy'] if crash_count == 0 else (self.COLORS['warning'] if crash_count < 3 else self.COLORS['critical'])
            self.crash_count_label.config(text=str(crash_count), fg=crash_color)
            
            recovery = data.get('recovery_attempts', 0)
            recovery_color = self.COLORS['healthy'] if recovery == 0 else self.COLORS['warning']
            self.recovery_label.config(text=str(recovery), fg=recovery_color)
            
            last_crash = data.get('last_crash')
            if last_crash:
                self.last_crash_label.config(text=last_crash[:19] if isinstance(last_crash, str) else "Recent")
            else:
                self.last_crash_label.config(text="Never")
            
            # Error log
            error_log = data.get('error_log', [])
            self.error_log.config(state='normal')
            self.error_log.delete('1.0', tk.END)
            if error_log:
                self.error_log.insert('1.0', '\n'.join(error_log[-5:]))
            else:
                self.error_log.insert('1.0', "No errors")
            self.error_log.config(state='disabled')
            
            # Status bar
            self.status_text.config(text=f"✅ Monitoring active | System: {system_state}")
            self.time_label.config(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
        except Exception as e:
            self.status_text.config(text=f"⚠️ Display error: {e}")
    
    def _update_loop(self):
        """Background thread to update display"""
        error_count = 0
        max_errors = 10
        
        while self.running:
            try:
                if self.guardian:
                    try:
                        data = self.guardian.get_status_dict()
                        error_count = 0  # Reset on success
                    except Exception as e:
                        error_count += 1
                        # Guardian error - show degraded state
                        data = {
                            'system_state': 'DEGRADED',
                            'cthulu_state': 'STOPPED',
                            'mt5_state': 'NOT_RUNNING',
                            'cthulu_pid': None,
                            'mt5_pid': None,
                            'cpu_percent': 0,
                            'memory_percent': 0,
                            'uptime_seconds': 0,
                            'crash_count': 0,
                            'last_crash': None,
                            'recovery_attempts': 0,
                            'error_log': [f"Guardian error: {str(e)[:100]}"],
                            'last_known_config': 'unknown',
                            'auto_restart_enabled': True
                        }
                else:
                    # Demo/standalone mode - show system metrics
                    try:
                        import psutil
                        cpu = psutil.cpu_percent()
                        mem = psutil.virtual_memory().percent
                    except Exception:
                        cpu = 0
                        mem = 0
                    
                    data = {
                        'system_state': 'OFFLINE',
                        'cthulu_state': 'STOPPED',
                        'mt5_state': 'NOT_RUNNING',
                        'cthulu_pid': None,
                        'mt5_pid': None,
                        'cpu_percent': cpu,
                        'memory_percent': mem,
                        'uptime_seconds': 0,
                        'crash_count': 0,
                        'last_crash': None,
                        'recovery_attempts': 0,
                        'error_log': [],
                        'last_known_config': 'config.json',
                        'auto_restart_enabled': True
                    }
                
                # Schedule UI update on main thread
                if self.running:
                    try:
                        self.root.after(0, lambda d=data: self._safe_update_display(d))
                    except tk.TclError:
                        self.running = False
                        break
                
            except tk.TclError:
                # Window was closed
                self.running = False
                break
            except Exception as e:
                error_count += 1
                if error_count >= max_errors:
                    self.running = False
                    break
            
            time.sleep(2)  # Update every 2 seconds
    
    def _safe_update_display(self, data: dict):
        """Safely update display, catching any Tcl errors"""
        try:
            self._update_display(data)
        except tk.TclError:
            # Window is closing or closed
            self.running = False
        except Exception as e:
            # Log but don't crash
            try:
                self.status_text.config(text=f"⚠️ Update error: {str(e)[:40]}")
            except Exception:
                pass
    
    def _force_recovery(self):
        """Force recovery button handler - restarts Cthulu with last known config"""
        if self.guardian:
            if messagebox.askyesno("Force Recovery", 
                "This will restart Cthulu with the last known config.\n\n"
                "Continue?"):
                def recover_with_feedback():
                    try:
                        self.root.after(0, lambda: self.status_text.config(text="🔄 Force recovery in progress..."))
                        self.root.after(0, lambda: self.recover_btn.config(state='disabled'))
                        result = self.guardian.force_recovery()
                        if result:
                            self.root.after(0, lambda: self.status_text.config(text="✅ Recovery completed - Cthulu restarted"))
                        else:
                            self.root.after(0, lambda: self.status_text.config(text="⚠️ Recovery failed - check logs"))
                    except tk.TclError:
                        pass  # Window closed
                    except Exception as e:
                        try:
                            self.root.after(0, lambda: self.status_text.config(text=f"❌ Error: {str(e)[:50]}"))
                        except tk.TclError:
                            pass
                    finally:
                        try:
                            self.root.after(0, lambda: self.recover_btn.config(state='normal'))
                        except tk.TclError:
                            pass
                threading.Thread(target=recover_with_feedback, daemon=True).start()
        else:
            messagebox.showinfo("Info", "Guardian not connected - standalone mode")
    
    def _emergency_stop(self):
        """Emergency stop button handler - immediately stops Cthulu"""
        if self.guardian:
            if messagebox.askyesno("⚠️ EMERGENCY STOP", 
                "This will IMMEDIATELY stop Cthulu!\n\n"
                "All open positions will remain as-is.\n"
                "Are you sure?",
                icon='warning'):
                def stop_with_feedback():
                    try:
                        self.root.after(0, lambda: self.status_text.config(text="🛑 Emergency stop..."))
                        self.root.after(0, lambda: self.stop_btn.config(state='disabled'))
                        result = self.guardian.stop_cthulu()
                        if result:
                            self.root.after(0, lambda: self.status_text.config(text="✅ Cthulu stopped"))
                        else:
                            self.root.after(0, lambda: self.status_text.config(text="⚠️ Stop failed"))
                    except tk.TclError:
                        pass  # Window closed
                    except Exception as e:
                        try:
                            self.root.after(0, lambda: self.status_text.config(text=f"❌ Error: {str(e)[:50]}"))
                        except tk.TclError:
                            pass
                    finally:
                        try:
                            self.root.after(0, lambda: self.stop_btn.config(state='normal'))
                        except tk.TclError:
                            pass
                threading.Thread(target=stop_with_feedback, daemon=True).start()
        else:
            messagebox.showinfo("Info", "Guardian not connected - standalone mode")
    
    def _enable_algo(self):
        """Enable algo trading button handler"""
        if self.guardian:
            def algo_with_feedback():
                try:
                    self.root.after(0, lambda: self.status_text.config(text="Enabling algo trading..."))
                    self.root.after(0, lambda: self.algo_btn.config(state='disabled'))
                    result = self.guardian.enable_algo_trading()
                    if result:
                        self.root.after(0, lambda: self.status_text.config(text="Algo trading enabled"))
                    else:
                        self.root.after(0, lambda: self.status_text.config(text="Algo enable failed - try manually in MT5"))
                except tk.TclError:
                    pass  # Window closed
                except Exception as e:
                    try:
                        self.root.after(0, lambda: self.status_text.config(text=f"❌ Error: {str(e)[:50]}"))
                    except tk.TclError:
                        pass
                finally:
                    try:
                        self.root.after(0, lambda: self.algo_btn.config(state='normal'))
                    except tk.TclError:
                        pass
            threading.Thread(target=algo_with_feedback, daemon=True).start()
        else:
            messagebox.showinfo("Info", "Guardian not connected - standalone mode")
    
    def _on_close(self):
        """Handle window close gracefully"""
        self.running = False
        
        # Give update thread time to finish
        try:
            if self.update_thread and self.update_thread.is_alive():
                self.update_thread.join(timeout=2)
        except Exception:
            pass
        
        # Destroy window
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
    
    def run(self):
        """Start the dashboard"""
        self.running = True
        
        # Start update thread
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        
        # Run main loop
        self.root.mainloop()


def main():
    """Standalone entry point - connects Guardian automatically"""
    import threading
    import sys
    import os
    
    # Add sentinel parent dir to path for imports
    sentinel_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sentinel_dir not in sys.path:
        sys.path.insert(0, sentinel_dir)
    workspace_dir = os.path.dirname(sentinel_dir)
    if workspace_dir not in sys.path:
        sys.path.insert(0, workspace_dir)
        
    try:
        from core.guardian import SentinelGuardian, RecoveryConfig
        
        # Create Guardian with default config
        config = RecoveryConfig(
            auto_restart_cthulu=True,
            auto_enable_algo=True
        )
        guardian = SentinelGuardian(config)
        
        # Start guardian monitoring in background thread
        guardian_thread = threading.Thread(
            target=guardian.run,
            kwargs={'poll_interval': 5.0, 'setup_signals': False},
            daemon=True
        )
        guardian_thread.start()
        
        # Create and run dashboard with guardian connected
        dashboard = SentinelDashboard(guardian)
        dashboard.run()
        
        # Stop guardian when GUI closes
        guardian.running = False
    except ImportError:
        # Fallback - standalone mode without guardian
        dashboard = SentinelDashboard()
        dashboard.run()


if __name__ == "__main__":
    main()
