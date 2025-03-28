import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
import threading
from datetime import datetime, timedelta
import pytz

# Local imports
from trading_bot import initialize_mt5, get_price_data, detect_fvg, check_entry_conditions
from config import SYMBOL, TIMEFRAME

class TradingBotDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Trading Bot Dashboard")
        self.root.geometry("1200x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Initialize variables
        self.is_running = False
        self.mt5_connected = False
        self.trading_data = []
        self.current_positions = []
        
        # Set up the dashboard structure
        self.setup_ui()
        
        # Initialize MT5 connection
        self.connect_to_mt5()
        
        # Start data collection thread
        self.data_thread = threading.Thread(target=self.collect_data_loop)
        self.data_thread.daemon = True
        
        # Initial data load
        self.update_status("Ready to start...")
    
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top control panel
        control_frame = ttk.LabelFrame(main_frame, text="Control Panel", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Control buttons
        self.start_button = ttk.Button(control_frame, text="Start Monitoring", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=5, pady=5)
        
        self.stop_button = ttk.Button(control_frame, text="Stop Monitoring", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5, pady=5)
        
        self.status_label = ttk.Label(control_frame, text="Status: Not connected")
        self.status_label.grid(row=0, column=2, padx=20, pady=5, sticky=tk.W)
        
        # Middle content with tabs
        tab_control = ttk.Notebook(main_frame)
        tab_control.pack(fill=tk.BOTH, expand=True)
        
        # Chart tab
        chart_tab = ttk.Frame(tab_control)
        tab_control.add(chart_tab, text="Price Chart")
        
        # Create chart figure
        self.fig = plt.Figure(figsize=(12, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, chart_tab)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Trade history tab
        history_tab = ttk.Frame(tab_control)
        tab_control.add(history_tab, text="Trade History")
        
        # Create trade history table
        columns = ('time', 'type', 'price', 'sl', 'tp', 'profit', 'status')
        self.trade_tree = ttk.Treeview(history_tab, columns=columns, show='headings')
        
        # Define headings
        self.trade_tree.heading('time', text='Time')
        self.trade_tree.heading('type', text='Type')
        self.trade_tree.heading('price', text='Price')
        self.trade_tree.heading('sl', text='Stop Loss')
        self.trade_tree.heading('tp', text='Take Profit')
        self.trade_tree.heading('profit', text='Profit')
        self.trade_tree.heading('status', text='Status')
        
        # Column width
        for col in columns:
            self.trade_tree.column(col, width=100)
        
        self.trade_tree.pack(fill=tk.BOTH, expand=True)
        
        # Active positions tab
        positions_tab = ttk.Frame(tab_control)
        tab_control.add(positions_tab, text="Active Positions")
        
        # Create positions table
        pos_columns = ('ticket', 'type', 'price', 'sl', 'tp', 'profit', 'time')
        self.positions_tree = ttk.Treeview(positions_tab, columns=pos_columns, show='headings')
        
        # Define headings
        self.positions_tree.heading('ticket', text='Ticket')
        self.positions_tree.heading('type', text='Type')
        self.positions_tree.heading('price', text='Entry Price')
        self.positions_tree.heading('sl', text='Stop Loss')
        self.positions_tree.heading('tp', text='Take Profit')
        self.positions_tree.heading('profit', text='Current Profit')
        self.positions_tree.heading('time', text='Open Time')
        
        # Column width
        for col in pos_columns:
            self.positions_tree.column(col, width=100)
        
        self.positions_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bottom status panel
        status_frame = ttk.LabelFrame(main_frame, text="Bot Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Status indicators
        self.balance_var = tk.StringVar(value="Balance: --")
        self.equity_var = tk.StringVar(value="Equity: --")
        self.active_positions_var = tk.StringVar(value="Active Positions: 0")
        self.fvg_status_var = tk.StringVar(value="FVG Detected: None")
        
        ttk.Label(status_frame, textvariable=self.balance_var).grid(row=0, column=0, padx=20, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.equity_var).grid(row=0, column=1, padx=20, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.active_positions_var).grid(row=0, column=2, padx=20, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.fvg_status_var).grid(row=0, column=3, padx=20, pady=5, sticky=tk.W)
    
    def connect_to_mt5(self):
        self.update_status("Connecting to MetaTrader 5...")
        
        try:
            if initialize_mt5():
                self.mt5_connected = True
                account_info = mt5.account_info()
                if account_info:
                    self.update_status(f"Connected to account: {account_info.login}")
                    self.balance_var.set(f"Balance: {account_info.balance:.2f}")
                    self.equity_var.set(f"Equity: {account_info.equity:.2f}")
                    
                    # Verify symbol exists
                    symbol_info = mt5.symbol_info(SYMBOL)
                    if symbol_info is None:
                        messagebox.showerror("Error", f"Symbol {SYMBOL} not found in MT5")
                        self.root.quit()
                        return
                else:
                    self.update_status("Connected to MT5 but couldn't get account info")
            else:
                messagebox.showerror("Error", "Failed to connect to MetaTrader 5")
                self.root.quit()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to MT5: {str(e)}")
            self.root.quit()
    
    def start_monitoring(self):
        if not self.mt5_connected:
            self.connect_to_mt5()
            if not self.mt5_connected:
                return
        
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.update_status("Monitoring started")
        
        # Start data collection
        self.data_thread.start()
        
        # Start updating the chart
        self.update_chart()
        
        # Update positions table
        self.update_positions_table()
    
    def stop_monitoring(self):
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_status("Monitoring stopped")
    
    def collect_data_loop(self):
        while self.is_running:
            try:
                # Get the latest price data for the configured symbol
                df = get_price_data(SYMBOL, TIMEFRAME, 100)
                
                if df is not None:
                    # Detect FVGs
                    df = detect_fvg(df)
                    
                    # Store the data for charting
                    self.trading_data = df
                    
                    # Check for FVGs in the most recent data
                    last_few_rows = df.tail(5)
                    has_bull_fvg = last_few_rows['bull_fvg'].any()
                    has_bear_fvg = last_few_rows['bear_fvg'].any()
                    
                    if has_bull_fvg:
                        self.fvg_status_var.set("FVG Detected: Bullish")
                    elif has_bear_fvg:
                        self.fvg_status_var.set("FVG Detected: Bearish")
                    else:
                        self.fvg_status_var.set("FVG Detected: None")
                    
                    # Update account info
                    account_info = mt5.account_info()
                    if account_info:
                        self.balance_var.set(f"Balance: {account_info.balance:.2f}")
                        self.equity_var.set(f"Equity: {account_info.equity:.2f}")
                    
                    # Get position info
                    positions = mt5.positions_get(symbol=SYMBOL)
                    if positions:
                        self.current_positions = list(positions)
                        self.active_positions_var.set(f"Active Positions: {len(positions)}")
                    else:
                        self.current_positions = []
                        self.active_positions_var.set("Active Positions: 0")
                else:
                    self.update_status(f"Failed to get price data for {SYMBOL}")
            
            except Exception as e:
                self.update_status(f"Error: {str(e)}")
            
            # Sleep before next update
            time.sleep(5)
    
    def update_chart(self):
        if self.is_running and len(self.trading_data) > 0:
            self.ax.clear()
            
            # Plot candlestick chart
            df = self.trading_data.tail(50)  # Last 50 candles
            
            # Calculate candlestick positions
            width = 0.6
            up = df[df.close >= df.open]
            down = df[df.close < df.open]
            
            # Plot up candles
            self.ax.bar(up.index, up.close - up.open, width, bottom=up.open, color='green')
            self.ax.bar(up.index, up.high - up.close, width/5, bottom=up.close, color='green')
            self.ax.bar(up.index, up.low - up.open, width/5, bottom=up.open, color='green')
            
            # Plot down candles
            self.ax.bar(down.index, down.close - down.open, width, bottom=down.open, color='red')
            self.ax.bar(down.index, down.high - down.open, width/5, bottom=down.open, color='red')
            self.ax.bar(down.index, down.low - down.close, width/5, bottom=down.close, color='red')
            
            # Plot FVG levels
            for i, row in df.iterrows():
                if not np.isnan(row['bull_fvg_level']):
                    self.ax.axhline(y=row['bull_fvg_level'], color='green', linestyle='--', alpha=0.5)
                if not np.isnan(row['bear_fvg_level']):
                    self.ax.axhline(y=row['bear_fvg_level'], color='red', linestyle='--', alpha=0.5)
            
            # Mark FVG points
            bull_fvg_points = df[df['bull_fvg']]
            bear_fvg_points = df[df['bear_fvg']]
            
            self.ax.scatter(bull_fvg_points.index, bull_fvg_points['high'], marker='^', color='green', s=100)
            self.ax.scatter(bear_fvg_points.index, bear_fvg_points['low'], marker='v', color='red', s=100)
            
            # Plot active positions if any
            for position in self.current_positions:
                pos_price = position.price_open
                pos_type = "BUY" if position.type == 0 else "SELL"
                pos_color = "blue" if position.type == 0 else "purple"
                
                self.ax.axhline(y=pos_price, color=pos_color, linestyle='-', linewidth=2, alpha=0.7)
                self.ax.text(df.index[-1], pos_price, f"{pos_type} @ {pos_price}", 
                             color=pos_color, ha='right', va='bottom')
                
                # Plot SL and TP levels
                if position.sl != 0:
                    self.ax.axhline(y=position.sl, color='red', linestyle=':', linewidth=1.5, alpha=0.7)
                    self.ax.text(df.index[-1], position.sl, f"SL: {position.sl}", 
                                 color='red', ha='right', va='bottom')
                
                if position.tp != 0:
                    self.ax.axhline(y=position.tp, color='green', linestyle=':', linewidth=1.5, alpha=0.7)
                    self.ax.text(df.index[-1], position.tp, f"TP: {position.tp}", 
                                 color='green', ha='right', va='bottom')
            
            # Format chart
            self.ax.set_xlabel('Candle Index')
            self.ax.set_ylabel('Price')
            self.ax.set_title(f'{SYMBOL} - {self.get_timeframe_name(TIMEFRAME)}')
            self.ax.grid(True, alpha=0.3)
            
            # Set x-axis ticks
            x_ticks = np.linspace(0, len(df) - 1, 10, dtype=int)
            self.ax.set_xticks(x_ticks)
            
            # Format dates for x-axis labels if time data available
            if 'time' in df.columns:
                x_labels = [df.iloc[i]['time'].strftime('%H:%M\n%m-%d') for i in x_ticks if i < len(df)]
                self.ax.set_xticklabels(x_labels)
            
            self.fig.tight_layout()
            self.canvas.draw()
        
        # Schedule next update if still running
        if self.is_running:
            self.root.after(5000, self.update_chart)  # Update every 5 seconds
    
    def update_positions_table(self):
        if self.is_running:
            # Clear existing items
            for item in self.positions_tree.get_children():
                self.positions_tree.delete(item)
            
            # Add current positions
            for position in self.current_positions:
                pos_type = "BUY" if position.type == 0 else "SELL"
                open_time = datetime.fromtimestamp(position.time).strftime('%Y-%m-%d %H:%M:%S')
                
                self.positions_tree.insert('', tk.END, values=(
                    position.ticket,
                    pos_type,
                    f"{position.price_open:.5f}",
                    f"{position.sl:.5f}" if position.sl != 0 else "None",
                    f"{position.tp:.5f}" if position.tp != 0 else "None",
                    f"{position.profit:.2f}",
                    open_time
                ))
            
            # Schedule next update if still running
            self.root.after(5000, self.update_positions_table)  # Update every 5 seconds
    
    def update_status(self, message):
        self.status_label.config(text=f"Status: {message}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    
    def get_timeframe_name(self, timeframe):
        timeframe_names = {
            mt5.TIMEFRAME_M1: "1 Minute",
            mt5.TIMEFRAME_M5: "5 Minutes",
            mt5.TIMEFRAME_M15: "15 Minutes",
            mt5.TIMEFRAME_M30: "30 Minutes",
            mt5.TIMEFRAME_H1: "1 Hour",
            mt5.TIMEFRAME_H4: "4 Hours",
            mt5.TIMEFRAME_D1: "Daily",
        }
        return timeframe_names.get(timeframe, str(timeframe))
    
    def on_close(self):
        self.is_running = False
        if self.mt5_connected:
            mt5.shutdown()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TradingBotDashboard(root)
    root.mainloop() 