import os
import sys
import time
import threading
import traceback
import subprocess
from datetime import datetime
import pytz
import psutil
from flask import Flask, request, render_template, jsonify, flash, redirect, url_for
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from custom_indicators import PineScriptHandler
import math
import random

app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)

# Global variables
bot_running = False
bot_threads = {}  # Dictionary to store multiple bot threads keyed by symbol
bot_instances = {}  # Dictionary to store multiple bot threads by instance number
mt5_initialized = False
pine_handler = PineScriptHandler()
active_indicator = "WMITable.pine"  # Set WMITable.pine as the default active indicator

# Error messages
MT5_ERROR_MESSAGES = {
    -1: "Connection to MetaTrader terminal failed. Make sure MT5 is running.",
    -2: "Authorization failed. Check login, password and server details.",
    -3: "Not enough account balance.",
    -4: "Symbol not found. Check if the symbol is available in your MT5 terminal."
}

# Bot class
class TradingBot:
    def __init__(self, settings):
        # Core trading parameters - essential for operation
        self.symbol = settings['symbol']
        self.symbols = settings.get('symbols', [self.symbol])
        self.multi_symbol = settings.get('multi_symbol', False)
        self.timeframe = settings['timeframe']
        self.lot_size = settings.get('lot_size', 0.01)
        self.sl_points = settings.get('sl_points', 1000)
        self.tp_points = settings.get('tp_points', 1000)
        self.trade_direction = settings.get('trade_direction', 'BOTH')
        
        # Magic number - unique identifier for this instance's trades (important for tracking)
        # This should be a unique number between 0-2147483647
        self.magic_number = settings.get('magic_number', 234000)
        self.instance_id = settings.get('instance_id', 0)
        
        # MT5 connection settings
        self.login = settings.get('login', None)
        self.password = settings.get('password', '')
        self.server = settings.get('server', '')
        self.use_active_account = settings.get('use_active_account', False)
        
        # Status flags
        self.running = True
        self.error_message = None
        
        # Risk management settings
        self.weekend_closing = settings.get('weekend_closing', True)
        self.max_drawdown = settings.get('max_drawdown', 3.5)
        
        # Strategy settings - keep all of these since they're used in strategy functions
        # Progressive Lockin Strategy settings
        self.positions_per_setup = settings.get('positions_per_setup', 3)
        self.positive_sl_points = settings.get('positive_sl_points', 20)
        self.breakeven_trigger_points = settings.get('breakeven_trigger_points', 20)
        self.enable_progressive = settings.get('enable_progressive', False)
        
        # Drawdown Layering Strategy settings
        self.enable_drawdown_layering = settings.get('enable_drawdown_layering', False)
        self.drawdown_layer_threshold = settings.get('drawdown_layer_threshold', self.sl_points / 5)  # Default to SL/5 layers
        self.positions_per_layer = settings.get('positions_per_layer', 3)
        self.minimum_profit_per_position = settings.get('tp_per_position', 200)  # Use configured TP per position
        self.max_layers = settings.get('max_layers', 5)
        self.max_drawdown_points = settings.get('max_drawdown_points', self.sl_points)
        
        # Trailing Stop Loss Strategy settings
        self.enable_trailing_sl = settings.get('enable_trailing_sl', False)
        self.trailing_tp_points = settings.get('trailing_tp_points', 900)
        self.trailing_sl_points = settings.get('trailing_sl_points', 300)
        self.dynamic_checkpoints = settings.get('dynamic_checkpoints', 5)
        
        # Custom indicator settings
        self.custom_indicator = settings.get('custom_indicator', None)
        self.pine_handler = settings.get('pine_handler')
        
        # Add new settings for Prop Firm Mode
        self.prop_firm_mode = settings.get('prop_firm_mode', False)
        self.trading_start_time = settings.get('trading_start_time', '08:00')
        self.trading_end_time = settings.get('trading_end_time', '17:00')
        self.comment_off = settings.get('comment_off', False)
        self.randomness_level = settings.get('randomness_level', 'medium')
        
        # Calculate randomness threshold
        self.randomness_threshold = {
            'low': 0.25,
            'medium': 0.50,
            'high': 0.75
        }.get(self.randomness_level, 0.50)
        
        # Add strategy type
        self.strategy_type = settings.get('strategy', 'exit_signal_or_max_tp')
        
        # Exit Signal or Max TP settings
        self.reentry_count = settings.get('reentry_count', 5)
        self.profit_percentage = settings.get('profit_percentage', 0.02)
        
    def initialize_mt5(self):
        """Initialize MT5 connection with improved auto-start functionality"""
        # First, try terminating any existing MT5 connection
        mt5.shutdown()
        time.sleep(1)
        
        # Check if MT5 terminal is installed and accessible
        mt5_terminal_paths = [
            os.getenv('MT5_PATH'),
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal.exe",
            r"C:\Program Files\MetaQuotes\terminal64.exe",
            r"C:\MT5\terminal64.exe",
            os.path.expanduser("~/AppData/Roaming/MetaTrader 5/terminal64.exe"),
            os.path.expanduser("~/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/terminal64.exe"),
            # Add more potential paths here
        ]
        
        # Find first valid path
        mt5_terminal_path = None
        for path in mt5_terminal_paths:
            if path and os.path.exists(path):
                mt5_terminal_path = path
                print(f"Found MT5 at: {mt5_terminal_path}")
                break
        
        if not mt5_terminal_path:
            self.error_message = "MetaTrader 5 terminal not found. Please install MT5 or set the MT5_PATH environment variable."
            print(self.error_message)
            return False
            
        # Check if MT5 is running
        mt5_process_running = False
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and ('terminal64.exe' in proc.info['name'].lower() or 'terminal.exe' in proc.info['name'].lower()):
                mt5_process_running = True
                break
                
        # If MT5 is not running and this is instance 1 or we're using active account, try to start it
        if not mt5_process_running and (self.instance_id == 1 or self.use_active_account):
            print(f"MetaTrader 5 is not running. Automatically starting it for Instance {self.instance_id}...")
            try:
                # Start MT5 process
                subprocess.Popen([mt5_terminal_path])
                
                # Wait for MT5 to initialize (up to 30 seconds)
                print("Waiting for MT5 to start...")
                start_time = time.time()
                while time.time() - start_time < 30:
                    # Check if MT5 process is now running
                    for proc in psutil.process_iter(['name']):
                        if proc.info['name'] and ('terminal64.exe' in proc.info['name'].lower() or 'terminal.exe' in proc.info['name'].lower()):
                            mt5_process_running = True
                            break
                    
                    if mt5_process_running:
                        print("MT5 process started successfully!")
                        # Give it more time to fully initialize
                        time.sleep(10)
                        break
                        
                    time.sleep(1)
                    
                if not mt5_process_running:
                    self.error_message = "Failed to start MetaTrader 5. Please start it manually."
                    print(self.error_message)
                    return False
            except Exception as e:
                self.error_message = f"Error starting MetaTrader 5: {str(e)}"
                print(self.error_message)
                return False
        elif not mt5_process_running:
            self.error_message = "MetaTrader 5 is not running. Please start it manually or enable Instance 1."
            print(self.error_message)
            return False
        
        print("MetaTrader 5 process is running, attempting to connect...")
        
        # Initialize MT5 connection
        if self.login and self.password and self.server:
            # If credentials are provided, use them
            try:
                login_value = int(self.login)  # Convert login to integer
                print(f"Connecting with credentials: login={login_value}, server={self.server}")
                init_result = mt5.initialize(
                    login=login_value,
                    password=self.password,
                    server=self.server,
                    path=mt5_terminal_path
                )
            except ValueError:
                print(f"Invalid login value: {self.login}. Must be numeric.")
                self.error_message = f"Invalid login format: {self.login}. Login must be a number."
                return False
        else:
            # Otherwise try to connect to already logged in terminal
            print("Connecting to already logged in terminal...")
            init_result = mt5.initialize(path=mt5_terminal_path)
        
        if not init_result:
            error_code = mt5.last_error()
            error_msg = MT5_ERROR_MESSAGES.get(error_code, f"MT5 initialization failed with error code {error_code}")
            self.error_message = error_msg
            print(self.error_message)
            return False
        
        # Check if symbol is available
        for symbol in self.symbols:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.error_message = f"Symbol {symbol} not found. Please check if it's available in your MT5 terminal."
                print(self.error_message)
                return False
            
            # Enable symbol for trading if needed
            if not symbol_info.visible:
                mt5.symbol_select(symbol, True)
            
        print(f"MT5 connected successfully. Version: {mt5.version()}")
        print(f"Trading account: {mt5.account_info().login} - {mt5.account_info().server}")
        return True
        
    def get_historical_data(self, timeframe, num_bars=100):
        """Get historical data for the currently active symbol"""
        try:
            rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, num_bars)
            if rates is None or len(rates) == 0:
                print(f"Failed to get historical data for {self.symbol}")
                return None
                
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            print(f"Error getting historical data for {self.symbol}: {e}")
            return None
            
    def get_historical_data_for_symbol(self, symbol, timeframe, num_bars=100):
        """Get historical data for a specific symbol, regardless of the active symbol"""
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
            if rates is None or len(rates) == 0:
                print(f"Failed to get historical data for {symbol}")
                return None
                
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            print(f"Error getting historical data for {symbol}: {e}")
            return None
        
    def is_weekend_trading_hours(self):
        """Check if current time is within weekend trading restriction hours (Sat 12 AM to Mon 7:59 AM PHT)"""
        # Convert current time to Philippine Time (PHT/UTC+8)
        now = datetime.now(pytz.timezone('Asia/Manila'))
        
        # Check if it's Saturday or Sunday or Monday before 8 AM
        is_saturday = now.weekday() == 5  # Saturday is 5
        is_sunday = now.weekday() == 6    # Sunday is 6
        is_monday_before_8am = now.weekday() == 0 and now.hour < 8  # Monday before 8 AM
        
        return is_saturday or is_sunday or is_monday_before_8am

    def should_open_trade(self):
        """Check if we should open a new trade"""
        try:
            # Get current positions for this symbol
            positions = mt5.positions_get(symbol=self.symbol)
            if positions is None:
                positions = []
            
            # Strict position count check for Exit Signal or Max TP strategy
            if self.strategy_type == 'exit_signal_or_max_tp':
                current_position_count = len(positions)
                if current_position_count >= self.reentry_count:
                    print(f"Maximum positions ({self.reentry_count}) reached for {self.symbol}. Cannot open new position.")
                    return False
                
                # Calculate total profit for drawdown check
                total_profit = 0
                for position in positions:
                    total_profit += position.profit + position.swap
                
                # Only allow new positions if in drawdown
                if current_position_count > 0 and total_profit >= 0:
                    print(f"Positions for {self.symbol} are in profit. Waiting for drawdown before opening new position.")
                    return False
            
            # Weekend trading check
            if self.weekend_closing and self.is_weekend_trading_hours():
                print("Weekend trading hours - no new positions")
                return False
            
            # Prop firm mode check
            if self.prop_firm_mode and not self.is_trading_hours():
                print("Outside prop firm trading hours")
                return False
            
            # Get historical data and calculate WMI signal
            df = self.get_historical_data(self.timeframe)
            if df is None or len(df) < 100:
                print("Insufficient historical data")
                return False
            
            # Check entry conditions using WMI indicator
            long_condition, short_condition = self.pine_handler.check_entry_conditions(
                self.symbol,
                self.timeframe,
                num_bars=100
            )
            
            # Determine if we should open based on trade direction
            can_buy = self.trade_direction in ['BOTH', 'LONG'] and long_condition
            can_sell = self.trade_direction in ['BOTH', 'SHORT'] and short_condition
            
            if can_buy or can_sell:
                print(f"Entry signal detected for {self.symbol} - Buy: {can_buy}, Sell: {can_sell}")
                print(f"Current positions: {current_position_count}/{self.reentry_count}")
                return True
            
            return False
            
        except Exception as e:
            print(f"Error in should_open_trade: {str(e)}")
            traceback.print_exc()
            return False

    def execute_trade_setup(self, is_buy):
        """Execute a complete trade setup with multiple positions"""
        # Check if we should open a trade
        if not self.should_open_trade():
            print(f"Trade execution skipped based on settings for {self.symbol}")
            return []
            
        positions = []
        setup_id = int(time.time())
        current_price = mt5.symbol_info_tick(self.symbol).ask if is_buy else mt5.symbol_info_tick(self.symbol).bid
        
        # Calculate SL and TP
        point_value = self.get_point_value()
        
        # Handle different strategies
        if self.strategy_type == 'exit_signal_or_max_tp':
            # For Exit Signal or Max TP strategy
            # This strategy opens positions one at a time, allowing up to reentry_count (default 5) positions
            # Positions are only added when existing ones are in drawdown
            sl_points = self.sl_points
            tp_points = self.tp_points
            positions_to_open = 1  # Only one position at a time for this strategy
            
            sl_price = current_price - (sl_points * point_value) if is_buy else current_price + (sl_points * point_value)
            tp_price = current_price + (tp_points * point_value) if is_buy else current_price - (tp_points * point_value)
            
            # Create order request with empty comment if comment_off is True
            comment = "" if self.comment_off else f"EXIT_{setup_id}_1"
            
            # Get existing positions for this symbol to determine position number
            existing_positions = mt5.positions_get(symbol=self.symbol)
            position_number = len(existing_positions) + 1 if existing_positions else 1
            
            # Update comment to include position number
            if not self.comment_off:
                comment = f"EXIT_{setup_id}_{position_number}"
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                "price": current_price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to open position for {self.symbol}: {result.retcode}, {result.comment}")
                return []
            else:
                positions.append(result.order)
                print(f"Opened position with ticket {result.order} for {self.symbol} (position {position_number}/{self.reentry_count})")
                
        elif self.enable_progressive:
            # For Progressive Lock-in strategy
            # This strategy opens all positions at once (positions_per_setup, default 3)
            # Each position has a different take profit level
            
            # Calculate TP for each position
            total_tp_points = self.tp_points
            tp_per_position = total_tp_points / self.positions_per_setup
            
            # Set SL for all positions
            sl_price = current_price - (self.sl_points * point_value) if is_buy else current_price + (self.sl_points * point_value)
            
            print(f"Opening Progressive Lock-in setup with {self.positions_per_setup} positions for {self.symbol}")
            print(f"Total TP: {total_tp_points} points, TP per position: {tp_per_position} points")
            
            # Get existing positions with the same setup ID to determine if this is a new setup
            # or continuing an existing one
            existing_positions = mt5.positions_get(symbol=self.symbol)
            existing_setup_ids = set()
            for pos in existing_positions:
                if pos.comment and pos.comment.startswith("PROG_"):
                    parts = pos.comment.split('_')
                    if len(parts) >= 2:
                        existing_setup_ids.add(parts[1])
            
            # Get the latest setup ID or create a new one
            current_setup_positions = []
            latest_setup_id = None
            if existing_setup_ids:
                latest_setup_id = list(existing_setup_ids)[-1]
                # Count positions in the latest setup
                for pos in existing_positions:
                    if pos.comment and pos.comment.startswith(f"PROG_{latest_setup_id}"):
                        current_setup_positions.append(pos)
            
            # Check if we need to continue with an existing setup or create a new one
            if latest_setup_id and len(current_setup_positions) < self.positions_per_setup:
                # Continue with existing setup
                setup_id = latest_setup_id
                positions_to_open = self.positions_per_setup - len(current_setup_positions)
                start_position = len(current_setup_positions) + 1
                print(f"Continuing existing setup PROG_{setup_id} ({len(current_setup_positions)}/{self.positions_per_setup} positions)")
            else:
                # Create a new setup
                positions_to_open = self.positions_per_setup
                start_position = 1
                print(f"Creating new setup PROG_{setup_id}")
            
            # Open the positions
            for i in range(positions_to_open):
                position_num = start_position + i
                
                # Calculate TP for this position
                position_tp = tp_per_position * position_num
                tp_price = current_price + (position_tp * point_value) if is_buy else current_price - (position_tp * point_value)
                
                # Create comment
                comment = "" if self.comment_off else f"PROG_{setup_id}_{position_num}"
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.symbol,
                    "volume": self.lot_size,
                    "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                    "price": current_price,
                    "sl": sl_price,
                    "tp": tp_price,
                    "deviation": 20,
                    "magic": self.magic_number,
                    "comment": comment,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Failed to open position {position_num}/{self.positions_per_setup} for {self.symbol}: {result.retcode}, {result.comment}")
                    # If this position failed, we should continue trying to open others
                    continue
                else:
                    positions.append(result.order)
                    print(f"Opened position {position_num}/{self.positions_per_setup} with ticket {result.order} for {self.symbol}, TP: {position_tp} points")
        
        elif self.enable_progressive and self.enable_drawdown_layering:
            # For Hybrid Progressive + Drawdown strategy
            # This strategy opens all positions at once (positions_per_setup, default 3)
            # like Progressive Lock-in, but also adds layers based on drawdown
            
            # Calculate TP for each position
            total_tp_points = self.tp_points
            tp_per_position = total_tp_points / self.positions_per_setup
            
            # Set SL for all positions
            sl_price = current_price - (self.sl_points * point_value) if is_buy else current_price + (self.sl_points * point_value)
            
            print(f"Opening Hybrid Progressive+Drawdown setup with {self.positions_per_setup} positions for {self.symbol}")
            print(f"Total TP: {total_tp_points} points, TP per position: {tp_per_position} points")
            
            # Get existing positions with the same setup ID to determine if this is a new setup
            # or continuing an existing one
            existing_positions = mt5.positions_get(symbol=self.symbol)
            existing_setup_ids = set()
            for pos in existing_positions:
                if pos.comment and (pos.comment.startswith("PROG_") or pos.comment.startswith("HYBRID_")):
                    parts = pos.comment.split('_')
                    if len(parts) >= 2:
                        existing_setup_ids.add(parts[1])
            
            # Get the latest setup ID or create a new one
            current_setup_positions = []
            latest_setup_id = None
            if existing_setup_ids:
                latest_setup_id = list(existing_setup_ids)[-1]
                # Count positions in the latest setup
                for pos in existing_positions:
                    if pos.comment and (
                        pos.comment.startswith(f"PROG_{latest_setup_id}") or 
                        pos.comment.startswith(f"HYBRID_{latest_setup_id}")
                    ):
                        current_setup_positions.append(pos)
            
            # Check if we need to continue with an existing setup or create a new one
            if latest_setup_id and len(current_setup_positions) < self.positions_per_setup:
                # Continue with existing setup
                setup_id = latest_setup_id
                positions_to_open = self.positions_per_setup - len(current_setup_positions)
                start_position = len(current_setup_positions) + 1
                print(f"Continuing existing setup HYBRID_{setup_id} ({len(current_setup_positions)}/{self.positions_per_setup} positions)")
            else:
                # Create a new setup
                positions_to_open = self.positions_per_setup
                start_position = 1
                print(f"Creating new setup HYBRID_{setup_id}")
            
            # Open the positions
            for i in range(positions_to_open):
                position_num = start_position + i
                
                # Calculate TP for this position
                position_tp = tp_per_position * position_num
                tp_price = current_price + (position_tp * point_value) if is_buy else current_price - (position_tp * point_value)
                
                # Create comment using HYBRID_ prefix to distinguish from pure Progressive
                comment = "" if self.comment_off else f"HYBRID_{setup_id}_{position_num}"
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.symbol,
                    "volume": self.lot_size,
                    "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                    "price": current_price,
                    "sl": sl_price,
                    "tp": tp_price,
                    "deviation": 20,
                    "magic": self.magic_number,
                    "comment": comment,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Failed to open hybrid position {position_num}/{self.positions_per_setup} for {self.symbol}: {result.retcode}, {result.comment}")
                    # If this position failed, we should continue trying to open others
                    continue
                else:
                    positions.append(result.order)
                    print(f"Opened hybrid position {position_num}/{self.positions_per_setup} with ticket {result.order} for {self.symbol}, TP: {position_tp} points")
        
        elif self.enable_drawdown_layering:
            # For Drawdown Layering strategy
            # This strategy opens the first positions normally, then adds layers based on drawdown
            positions_to_open = self.positions_per_layer
            
            # Calculate SL and TP for initial positions
            sl_points = self.sl_points
            tp_points = self.tp_points if hasattr(self, 'tp_points') else self.minimum_profit_per_position
            
            sl_price = current_price - (sl_points * point_value) if is_buy else current_price + (sl_points * point_value)
            tp_price = current_price + (tp_points * point_value) if is_buy else current_price - (tp_points * point_value)
            
            print(f"Opening Drawdown Layering setup with {positions_to_open} positions for {self.symbol}")
            print(f"SL: {sl_points} points, TP: {tp_points} points, Layer threshold: {self.drawdown_layer_threshold} points")
            
            # Open the initial positions (first layer)
            for i in range(positions_to_open):
                position_num = i + 1
                
                # Create comment with DDL_ prefix to distinguish drawdown layering positions
                comment = "" if self.comment_off else f"DDL_{setup_id}_1_{position_num}"
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.symbol,
                    "volume": self.lot_size,
                    "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                    "price": current_price,
                    "sl": sl_price,
                    "tp": tp_price,
                    "deviation": 20,
                    "magic": self.magic_number,
                    "comment": comment,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Failed to open drawdown position {position_num}/{positions_to_open} for {self.symbol}: {result.retcode}, {result.comment}")
                    # If this position failed, we should continue trying to open others
                    continue
                else:
                    positions.append(result.order)
                    print(f"Opened drawdown position {position_num}/{positions_to_open} with ticket {result.order} for {self.symbol}")
        
        elif self.strategy_type == 'trailing_stop' or self.enable_trailing_sl:
            # For Trailing Stop Loss strategy (modified to allow multiple positions)
            sl_points = self.trailing_sl_points
            tp_points = self.trailing_tp_points
            
            # Calculate checkpoint information
            checkpoint_size = tp_points / self.dynamic_checkpoints
            
            sl_price = current_price - (sl_points * point_value) if is_buy else current_price + (sl_points * point_value)
            tp_price = current_price + (tp_points * point_value) if is_buy else current_price - (tp_points * point_value)
            
            # Create order request with empty comment if comment_off is True
            comment = "" if self.comment_off else f"TSL_{setup_id}_{len(positions) + 1}"
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                "price": current_price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to open position: {result.retcode}, {result.comment}")
                return []
            else:
                positions.append(result.order)
                print(f"Opened position with ticket {result.order}")
                
        else:
            # Handle other strategies as before...
            pass
            
        return positions
    
    def open_position(self, order_type, sl, tp, comment):
        """Open a new position with the specified parameters"""
        try:
            # First check if we've reached the maximum number of positions
            if self.strategy_type == 'exit_signal_or_max_tp':
                positions = mt5.positions_get(symbol=self.symbol)
                if positions is None:
                    positions = []
                
                if len(positions) >= self.reentry_count:
                    print(f"Maximum number of positions ({self.reentry_count}) reached for {self.symbol}, cannot open new position")
                    return None
            
            # Prepare the trade request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": order_type,
                "price": mt5.symbol_info_tick(self.symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).bid,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": 234000,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send the trade request
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to open position: {result.comment}")
                return None
            
            print(f"Opened position with ticket {result.order} for {self.symbol} (position {len(positions) + 1}/{self.reentry_count})")
            return result.order
            
        except Exception as e:
            print(f"Error opening position: {str(e)}")
            traceback.print_exc()
            return None
    
    def close_position(self, ticket):
        """Close a position by ticket"""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            print(f"Position {ticket} not found")
            return False
            
        position = position[0]

        # Prepare close request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
            "price": mt5.symbol_info_tick(position.symbol).bid if position.type == 0 else mt5.symbol_info_tick(position.symbol).ask,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        # Send close request
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to close position {ticket}: {result.retcode}, {result.comment}")
            return False
            
        print(f"Closed position {ticket} successfully")
        return True
    
    def modify_position_sl(self, ticket, new_sl):
        """Modify position stop loss"""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            print(f"Position {ticket} not found")
            return False
            
        position = position[0]
        
        # Prepare modify request
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": position.symbol,
            "sl": new_sl,
            "tp": position.tp,
            "magic": position.magic
        }
        
        # Send modify request
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to modify SL for position {ticket}: {result.retcode}, {result.comment}")
            return False
            
        print(f"Modified SL for position {ticket} to {new_sl}")
        return True
    
    def get_point_value(self):
        """Get point value for the symbol"""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            return 0.0001  # Default for forex
        
        # When trading in Forex (standard account), points are usually 0.0001
        # For 5-digit brokers, some scalars may be required
        return symbol_info.point
    
    def manage_positions(self):
        """Manage all open positions for the current symbol"""
        try:
            positions = mt5.positions_get(symbol=self.symbol)
            if not positions:
                return
            
            # Call specific strategy management functions based on the position comment
            # or the configured strategy
            
            # Exit Signal or Max TP strategy
            if self.strategy_type == 'exit_signal_or_max_tp':
                self.manage_exit_signal_positions(positions)
            
            # Progressive Lock-in strategy - handle both PROG_ and HYBRID_ prefixes
            prog_positions = [pos for pos in positions if pos.comment and (pos.comment.startswith("PROG_") or pos.comment.startswith("HYBRID_"))]
            if prog_positions and (self.enable_progressive or (self.enable_progressive and self.enable_drawdown_layering)):
                self.manage_progressive_positions(prog_positions)
            
            # Trailing Stop Loss strategy
            trailing_positions = [pos for pos in positions if not pos.comment or pos.comment.startswith("TSL_")]
            if trailing_positions and self.enable_trailing_sl:
                self.manage_trailing_sl(trailing_positions)
            
            # Drawdown Layering strategy - handle both ACE_, DDL_, and HYBRID_ prefixes
            if self.enable_drawdown_layering:
                # For hybrid strategy, also check for drawdown in the progressive positions
                if self.enable_progressive and self.enable_drawdown_layering:
                    # Include all positions for drawdown layering in hybrid mode
                    self.manage_drawdown_layers(positions)
                else:
                    # Only handle positions with ACE_ or DDL_ prefixes for pure drawdown layering
                    drawdown_positions = [pos for pos in positions if pos.comment and (pos.comment.startswith("ACE_") or pos.comment.startswith("DDL_"))]
                    if drawdown_positions:
                        self.manage_drawdown_layers(drawdown_positions)
            
            # For positions not handled by specific strategies, make sure they have take profit set
            for position in positions:
                if position.tp == 0:
                    # Calculate TP based on strategy
                    point_value = self.get_point_value()
                    is_buy = position.type == 0
                    tp_points = self.tp_points
                    
                    tp_price = position.price_open + (tp_points * point_value) if is_buy else position.price_open - (tp_points * point_value)
                    
                    print(f"Setting TP for position {position.ticket} to {tp_points} points")
                    self.modify_position_tp(position.ticket, tp_price)
                    
        except Exception as e:
            print(f"Error managing positions for {self.symbol}: {e}")
            traceback.print_exc()

    def manage_progressive_positions(self, positions):
        """
        Progressive lock-in strategy:
        1. When first position reaches TP, it's closed and others move to breakeven
        2. When second position reaches TP, it's closed and third position moves to positive SL
        3. Each position has its own take profit level based on its position number
        """
        try:
            # Group positions by setup ID
            position_groups = {}
            for pos in positions:
                if not pos.comment or (not pos.comment.startswith("PROG_") and not pos.comment.startswith("HYBRID_")):
                    continue
                    
                setup_id = pos.comment.split('_')[1]
                if setup_id not in position_groups:
                    position_groups[setup_id] = []
                position_groups[setup_id].append(pos)
            
            point_value = self.get_point_value()
            
            # Process each setup
            for setup_id, group_positions in position_groups.items():
                # Skip if not a progressive setup
                if len(group_positions) < 2:
                    continue
                
                # Sort positions by position number (from comment)
                try:
                    # Extract position numbers from comments
                    for pos in group_positions:
                        pos_parts = pos.comment.split('_')
                        if len(pos_parts) >= 3:
                            try:
                                pos.position_number = int(pos_parts[2])
                            except ValueError:
                                # If position number cannot be parsed, set it to 0 and log the issue
                                print(f"Warning: Invalid position number format in comment: {pos.comment}, ticket: {pos.ticket}")
                                pos.position_number = 0
                        else:
                            pos.position_number = 0
                    
                    # Sort by position number
                    sorted_positions = sorted(group_positions, key=lambda p: getattr(p, 'position_number', 0))
                except Exception as e:
                    print(f"Error sorting positions for {self.symbol}, setup {setup_id}: {e}")
                    # Continue with unsorted positions
                    sorted_positions = group_positions
                
                # Get current profit for each position
                for i, pos in enumerate(sorted_positions):
                    is_buy = pos.type == 0
                    
                    # Calculate profit in points
                    price_diff = pos.price_current - pos.price_open
                    if not is_buy:
                        price_diff = -price_diff
                    
                    profit_points = price_diff / point_value
                    
                    # Calculate TP for this position
                    tp_per_position = self.tp_points / self.positions_per_setup
                    position_tp = tp_per_position * pos.position_number
                    
                    # First position management
                    if i == 0 and profit_points >= position_tp:
                        # Close first position
                        print(f"Closing first position ({pos.ticket}) at {profit_points:.2f} points profit (target: {position_tp})")
                        self.close_position(pos.ticket)
                        
                        # Move others to breakeven
                        for j, other_pos in enumerate(sorted_positions):
                            if j > 0:
                                print(f"Moving position {other_pos.ticket} to breakeven")
                                self.modify_position_sl(other_pos.ticket, other_pos.price_open)
                    
                    # Second position management
                    elif i == 1 and profit_points >= position_tp:
                        # Close second position
                        print(f"Closing second position ({pos.ticket}) at {profit_points:.2f} points profit (target: {position_tp})")
                        self.close_position(pos.ticket)
                        
                        # Move third position to positive_sl_points
                        if len(sorted_positions) > 2:
                            third_pos = sorted_positions[2]
                            is_third_buy = third_pos.type == 0
                            
                            # Calculate new SL
                            new_sl = third_pos.price_open + (self.positive_sl_points * point_value) if is_third_buy else third_pos.price_open - (self.positive_sl_points * point_value)
                            
                            print(f"Moving position {third_pos.ticket} to positive SL at {self.positive_sl_points} points")
                            self.modify_position_sl(third_pos.ticket, new_sl)
                    
                    # For all positions - check if they've hit breakeven trigger
                    if profit_points >= self.breakeven_trigger_points and pos.sl == 0:
                        print(f"Position {pos.ticket} hit breakeven trigger at {profit_points:.2f} points profit (trigger: {self.breakeven_trigger_points})")
                        self.modify_position_sl(pos.ticket, pos.price_open)
        
        except Exception as e:
            print(f"Error in progressive position management: {e}")
            traceback.print_exc()

    def manage_drawdown_layers(self, positions):
        try:
            print(f"Checking for drawdown conditions on {self.symbol}...")
            
            # Skip if no positions
            if not positions:
                print(f"No positions to check for {self.symbol}")
                return
                
            # Group positions by symbol and direction (buy/sell) instead of relying on comments
            buy_positions = [p for p in positions if p.type == 0]
            sell_positions = [p for p in positions if p.type == 1]
            
            # Process buy and sell positions separately
            for positions_list, is_buy in [(buy_positions, True), (sell_positions, False)]:
                if not positions_list:
                    continue
                    
                # Create a default setup ID based on direction
                default_setup_id = f"default_{self.symbol}_{'buy' if is_buy else 'sell'}"
                
                # Try to extract setup ID from position comments if they exist
                # Otherwise, use the default setup ID
                position_groups = {}
                position_groups[default_setup_id] = []
                
                for pos in positions_list:
                    position_groups[default_setup_id].append(pos)
                    
                    # Also try to group by explicit setup IDs if found in comments
                    if pos.comment and len(pos.comment.split('_')) >= 2:
                        comment_parts = pos.comment.split('_')
                        prefix = comment_parts[0]
                        setup_id = comment_parts[1]
                        
                        # Only group by setup ID if it's from a valid strategy
                        if prefix in ['ACE', 'PROG', 'TSL', 'EXIT']:
                            if setup_id not in position_groups:
                                position_groups[setup_id] = []
                            position_groups[setup_id].append(pos)
                            
                            # Remove from default group if added to a specific group
                            if pos in position_groups[default_setup_id]:
                                position_groups[default_setup_id].remove(pos)
                
                # Process each group
                for setup_id, setup_positions in position_groups.items():
                    if not setup_positions:
                        continue
                    
                    # Calculate current drawdown
                    # Calculate weighted average entry price
                    total_volume = sum(pos.volume for pos in setup_positions)
                    avg_entry_price = sum(pos.price_open * pos.volume for pos in setup_positions) / total_volume
                    
                    # Get current price
                    point_value = self.get_point_value()
                    current_price = mt5.symbol_info_tick(self.symbol).bid if is_buy else mt5.symbol_info_tick(self.symbol).ask
                    
                    # Calculate drawdown in points
                    drawdown = (avg_entry_price - current_price) if is_buy else (current_price - avg_entry_price)
                    drawdown_points = drawdown / point_value
                    
                    if drawdown_points <= 0:
                        print(f"{self.symbol} Setup {setup_id} has no drawdown, no layers needed")
                        continue  # No drawdown, no need for additional layers
                    
                    print(f"{self.symbol} Setup {setup_id} drawdown: {drawdown_points:.2f} points")
                    
                    # Check if drawdown exceeds max limit - don't add layers if at max
                    max_drawdown_points = getattr(self, 'max_drawdown_points', self.sl_points)
                    if drawdown_points >= max_drawdown_points:
                        print(f"⚠️ WARNING: {self.symbol} Drawdown {drawdown_points:.2f} points exceeds max limit of {max_drawdown_points} points.")
                        print(f"Not adding more layers for {self.symbol} setup {setup_id} due to max drawdown limit.")
                        continue
                    
                    # Count existing layers
                    existing_layers = set()
                    for pos in setup_positions:
                        if pos.comment and len(pos.comment.split('_')) > 3 and pos.comment.split('_')[3].startswith('L'):
                            existing_layers.add(pos.comment.split('_')[3])
                    
                    # Calculate required layers based on drawdown threshold
                    required_layers = math.ceil(drawdown_points / self.drawdown_layer_threshold)
                    required_layers = min(required_layers, self.max_layers)  # Limit to max_layers
                    
                    # Check if we need to add layers
                    if len(existing_layers) >= required_layers:
                        print(f"{self.symbol} Setup {setup_id} already has {len(existing_layers)} layers (required: {required_layers})")
                        continue
                    
                    # Add missing layers
                    layer_to_add = len(existing_layers) + 1
                    if layer_to_add <= required_layers:
                        print(f"{self.symbol} Setup {setup_id} needs additional layer {layer_to_add} (required: {required_layers})")
                        self.add_layer(setup_id, is_buy, layer_to_add)
                        
                        # Adjust take profits for all positions in this setup
                        self.adjust_take_profits(setup_positions)
                    
        except Exception as e:
            print(f"Error managing drawdown layers for {self.symbol}: {e}")
            traceback.print_exc()
    
    def add_layer(self, setup_id, is_buy, layer_num):
        """Add a new layer of positions for drawdown layering strategy"""
        positions = []
        
        # Get current price
        current_price = mt5.symbol_info_tick(self.symbol).ask if is_buy else mt5.symbol_info_tick(self.symbol).bid
        
        # Calculate SL and TP
        point_value = self.get_point_value()
        sl_points = self.sl_points
        
        # Calculate SL price
        sl_price = current_price - (sl_points * point_value) if is_buy else current_price + (sl_points * point_value)
        
        # For layering, we initially set TP at minimum profit level
        min_profit_points = self.minimum_profit_per_position
        tp_price = current_price + (min_profit_points * point_value) if is_buy else current_price - (min_profit_points * point_value)
        
        print(f"Adding layer {layer_num} for setup {setup_id} on {self.symbol}")
        print(f"Type: {'BUY' if is_buy else 'SELL'}, Price: {current_price}")
        print(f"SL: {sl_price}, TP: {tp_price}")
        
        # Determine position comment prefix based on strategy
        if setup_id.startswith("default_"):
            # This is a hybrid strategy position, use the appropriate prefix
            if self.enable_progressive and self.enable_drawdown_layering:
                comment_prefix = "HYBRID"
            else:
                comment_prefix = "DDL"  # Default drawdown layering
        else:
            # Use the original ACE prefix for traditional drawdown layering
            comment_prefix = "ACE"
        
        # Open positions
        for i in range(self.positions_per_layer):
            position_num = i + 1
            
            # Create a layer-specific comment
            comment = f"{comment_prefix}_{setup_id}_L{layer_num}_{position_num}"
            
            # Make sure the comment isn't too long for MT5 (limited to 31 characters)
            if len(comment) > 31:
                # Truncate the setup_id part to fit
                max_setup_id_len = 31 - len(f"{comment_prefix}_X_L{layer_num}_{position_num}")
                truncated_setup_id = setup_id[:max_setup_id_len]
                comment = f"{comment_prefix}_{truncated_setup_id}_L{layer_num}_{position_num}"
            
            # Create order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                "price": current_price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "" if self.comment_off else comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            # Send order
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to open position for layer {layer_num}: {result.retcode}, {result.comment}")
                
                # Close all opened positions if one fails
                for pos in positions:
                    self.close_position(pos)
                return []
            else:
                positions.append(result.order)
                print(f"Opened position for layer {layer_num} with ticket {result.order}")
        
        return positions
    
    def adjust_take_profits(self, positions):
        """Adjust take profit levels for all positions in a setup"""
        if not positions:
            return
        
        # Group by symbol and type (buy/sell)
        buy_positions = [p for p in positions if p.type == 0]
        sell_positions = [p for p in positions if p.type == 1]
        
        # Handle buy positions
        if buy_positions:
            # Calculate weighted average entry
            total_volume = sum(pos.volume for pos in buy_positions)
            avg_entry = sum(pos.price_open * pos.volume for pos in buy_positions) / total_volume
            
            # Calculate min profit price
            point_value = self.get_point_value()
            min_profit_price = avg_entry + (self.minimum_profit_per_position * point_value)
            
            print(f"Adjusting TPs for {len(buy_positions)} BUY positions on {self.symbol}")
            print(f"Average entry: {avg_entry}, Min profit price: {min_profit_price}")
            
            # Update TP for each position
            for pos in buy_positions:
                self.modify_position_tp(pos.ticket, min_profit_price)
        
        # Handle sell positions
        if sell_positions:
            # Calculate weighted average entry
            total_volume = sum(pos.volume for pos in sell_positions)
            avg_entry = sum(pos.price_open * pos.volume for pos in sell_positions) / total_volume
            
            # Calculate min profit price
            point_value = self.get_point_value()
            min_profit_price = avg_entry - (self.minimum_profit_per_position * point_value)
            
            print(f"Adjusting TPs for {len(sell_positions)} SELL positions on {self.symbol}")
            print(f"Average entry: {avg_entry}, Min profit price: {min_profit_price}")
            
            # Update TP for each position
            for pos in sell_positions:
                self.modify_position_tp(pos.ticket, min_profit_price)
    
    def modify_position_tp(self, ticket, new_tp):
        """Modify position take profit"""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            print(f"Position {ticket} not found")
            return False
            
        position = position[0]
        
        # Prepare modify request
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": position.symbol,
            "sl": position.sl,
            "tp": new_tp,
            "magic": position.magic
        }
        
        # Send modify request
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to modify TP for position {ticket}: {result.retcode}, {result.comment}")
            return False
            
        print(f"Modified TP for position {ticket} to {new_tp}")
        return True
    
    def manage_trailing_sl(self, positions):
        """Manage trailing stop loss with dynamic checkpoints"""
        for pos in positions:
            # Process only positions with TSL_ comment
            if not pos.comment or not pos.comment.startswith("TSL_"):
                continue
                
            # Extract setup ID from comment (TSL_[setup_id]_[position_number])
            parts = pos.comment.split('_')
            if len(parts) < 3:
                continue
                
            is_buy = pos.type == 0
            
            # Calculate current profit in points
            price_diff = pos.price_current - pos.price_open
            if not is_buy:  # Sell position
                price_diff = -price_diff
                
            point_value = self.get_point_value()
            profit_points = price_diff / point_value
            
            # Calculate each checkpoint value
            tp_points = self.trailing_tp_points
            checkpoint_size = tp_points / self.dynamic_checkpoints
            
            # Determine which checkpoint we've reached
            current_checkpoint = 0
            for i in range(1, self.dynamic_checkpoints + 1):
                checkpoint_level = checkpoint_size * i
                if profit_points >= checkpoint_level:
                    current_checkpoint = i
            
            if current_checkpoint == 0:
                # Not reached first checkpoint yet
                continue
                
            # Calculate new SL based on current checkpoint
            new_sl = None
            new_sl_points = 0
            
            if current_checkpoint == 1:
                # First checkpoint - move to breakeven
                new_sl = pos.price_open
                new_sl_points = 0
            else:
                # Lock in a percentage of the profit based on checkpoint
                locked_profit_percentage = 0.8  # Lock in 80% of progress to next checkpoint
                progress_to_next = profit_points - (checkpoint_size * (current_checkpoint - 1))
                percentage_of_current_checkpoint = progress_to_next / checkpoint_size
                
                lock_in_points = (current_checkpoint - 1) * checkpoint_size * locked_profit_percentage
                
                # Add partial lock-in from current checkpoint if significant progress
                if percentage_of_current_checkpoint > 0.3:  # Over 30% to next checkpoint
                    lock_in_points += progress_to_next * locked_profit_percentage * 0.5
                    
                new_sl_points = lock_in_points
                new_sl = pos.price_open + (new_sl_points * point_value) if is_buy else pos.price_open - (new_sl_points * point_value)
            
            # Only update if new SL is better than current SL
            current_sl_diff = abs(pos.sl - pos.price_open) / point_value
            if is_buy and (pos.sl == 0 or new_sl > pos.sl):
                print(f"{self.symbol} Moving SL to lock in {new_sl_points:.2f} points (profit: {profit_points:.2f} points, checkpoint: {current_checkpoint})")
                self.modify_position_sl(pos.ticket, new_sl)
            elif not is_buy and (pos.sl == 0 or new_sl < pos.sl):
                print(f"{self.symbol} Moving SL to lock in {new_sl_points:.2f} points (profit: {profit_points:.2f} points, checkpoint: {current_checkpoint})")
                self.modify_position_sl(pos.ticket, new_sl)
    
    def run(self, initialize_mt5=True):
        if initialize_mt5 and not self.initialize_mt5():
            self.running = False
            return
        elif not initialize_mt5:
            print(f"Skipping MT5 initialization for {self.symbol}. Using existing connection.")
            
        # Print configured symbols
        if self.multi_symbol and len(self.symbols) > 1:
            print(f"Trading bot started in MULTI-SYMBOL mode for: {', '.join(self.symbols)}")
            print(f"Primary symbol: {self.symbol}")
        else:
            print(f"Trading bot started for {self.symbol}")
            
        print(f"Strategy settings:")
        print(f"  - Lot size: {self.lot_size}")
        print(f"  - SL/TP: {self.sl_points}/{self.tp_points} points")
        print(f"  - Trade direction: {self.trade_direction}")
        print(f"  - Strategy type: {self.strategy_type}")
        
        # Debug hybrid strategy configuration
        if self.enable_progressive and self.enable_drawdown_layering:
            print(f"HYBRID STRATEGY ENABLED - Progressive + Drawdown Layering")
            print(f"  - Progressive settings: {self.positions_per_setup} positions, breakeven: {self.breakeven_trigger_points} points")
            print(f"  - Drawdown settings: {self.max_layers} layers, threshold: {self.drawdown_layer_threshold} points")
            print(f"  - Min profit per position: {self.minimum_profit_per_position} points")
        
        # Other strategy prints
        if self.strategy_type == 'exit_signal_or_max_tp':
            print(f"Exit Signal or Max TP Strategy enabled:")
            print(f"  - TP: {self.tp_points} points")
            print(f"  - No. of Reentry: {self.reentry_count}")
            
        if self.enable_progressive:
            print(f"Progressive Lockin Strategy enabled:")
            print(f"  - Positions per setup: {self.positions_per_setup}")
            print(f"  - Positive SL: {self.positive_sl_points} points")
            print(f"  - Breakeven trigger: {self.breakeven_trigger_points} points")
        
        if self.enable_drawdown_layering:
            print(f"Drawdown Layering Strategy enabled:")
            print(f"  - Threshold: {self.drawdown_layer_threshold} points")
            print(f"  - Minimum profit: {self.minimum_profit_per_position} points")
            print(f"  - Maximum layers: {self.max_layers}")
            print(f"  - Max drawdown: {getattr(self, 'max_drawdown_points', self.sl_points)} points")

        if self.enable_trailing_sl:
            print(f"Trailing Stop Loss Strategy enabled:")
            print(f"  - Initial SL: {self.trailing_sl_points} points")
            print(f"  - TP: {self.trailing_tp_points} points")
            print(f"  - Dynamic checkpoints: {self.dynamic_checkpoints}")
            print(f"  - Checkpoint size: {self.trailing_tp_points / self.dynamic_checkpoints} points")

        if self.custom_indicator:
            print(f"Using custom indicator: {self.custom_indicator}")
        
        print(f"End of Week Closing enabled: Profitable positions will be closed on Saturday at midnight Philippine Time")
        
        retry_count = 0
        max_retries = 5
        
        while self.running:
            try:
                # Verify MT5 connection is still valid
                if not mt5.terminal_info():
                    print("MT5 connection lost, attempting to reconnect...")
                    if not self.initialize_mt5():
                        retry_count += 1
                        if retry_count >= max_retries:
                            self.error_message = f"Failed to reconnect to MT5 after {max_retries} attempts. Stopping bot."
                            print(self.error_message)
                            self.running = False
                            break
                        
                        print(f"Reconnection attempt {retry_count}/{max_retries} failed. Waiting 10 seconds...")
                        time.sleep(10)
                        continue
                    else:
                        print("Successfully reconnected to MT5.")
                        retry_count = 0
            
                # Reset retry count on successful operations
                retry_count = 0
                
                # Check if it's Saturday and manage trades accordingly
                self.check_weekend_closing()
                
                # Manage existing positions for all symbols
                symbols_to_process = self.symbols if self.multi_symbol else [self.symbol]
                
                for current_symbol in symbols_to_process:
                    try:
                        # Store the original symbol temporarily
                        original_symbol = self.symbol
                        
                        # Set the current symbol as the active one
                        if current_symbol != self.symbol:
                            self.symbol = current_symbol
                            print(f"\nProcessing symbol: {current_symbol}")
                        
                        # Manage existing positions first
                        self.manage_positions()
                        
                        # Check for new trade setups
                        df = self.get_historical_data(self.timeframe)
                        if df is None:
                            print(f"Failed to get historical data for {current_symbol}. Skipping...")
                            continue
                            
                        # Check for entry conditions - custom indicator or default HWR
                        if self.custom_indicator and self.pine_handler:
                            long_condition, short_condition = self.pine_handler.check_entry_conditions(
                                self.symbol,  # Pass symbol string
                                self.timeframe,  # Pass timeframe
                                num_bars=100  # Pass number of bars
                            )
                            print(f"Custom indicator {self.custom_indicator} signals for {current_symbol} - Long: {long_condition}, Short: {short_condition}")
                        else:
                            # Fallback to HWR strategy
                            if not hasattr(self, 'pine_handler'):
                                from custom_indicators import PineScriptHandler
                                self.pine_handler = PineScriptHandler()
                            
                            # Use WMITable.pine as the default strategy
                            long_condition, short_condition = self.pine_handler.check_entry_conditions(
                                self.symbol,  # Pass symbol string
                                self.timeframe,  # Pass timeframe
                                num_bars=100  # Pass number of bars
                            )
                            print(f"WMITable strategy signals for {current_symbol} - Long: {long_condition}, Short: {short_condition}")
                        
                        # Apply trade direction filter
                        if self.trade_direction == "LONG":
                            short_condition = False
                        elif self.trade_direction == "SHORT":
                            long_condition = False
                        
                        if long_condition:
                            print(f"Long entry signal detected for {current_symbol}")
                        elif short_condition:
                            print(f"Short entry signal detected for {current_symbol}")
                        
                        # Get existing positions for this symbol
                        positions = mt5.positions_get(symbol=current_symbol)
                        positions_count = len(positions) if positions else 0
                        
                        # Check for strategy-specific position handling
                        if self.strategy_type == 'exit_signal_or_max_tp':
                            # For Exit Signal or Max TP strategy
                            # Make sure we set the current symbol correctly for should_open_trade
                            self.symbol = current_symbol
                            
                            # Check for entry signals and execute trade if appropriate
                            # The execute_trade_setup method will check should_open_trade() internally
                            if long_condition:
                                positions = self.execute_trade_setup(True)
                                if positions:
                                    print(f"Opened {len(positions)} long positions for {current_symbol} (new or reentry)")
                            elif short_condition:
                                positions = self.execute_trade_setup(False)
                                if positions:
                                    print(f"Opened {len(positions)} short positions for {current_symbol} (new or reentry)")
                            else:
                                print(f"No entry signals for {current_symbol}")
                        elif self.enable_progressive and self.enable_drawdown_layering:
                            # For Hybrid Progressive + Drawdown strategy
                            # Count how many positions we have with progressive lock-in setup
                            progressive_positions = []
                            setup_ids = set()
                            
                            if positions:
                                for pos in positions:
                                    # Check for both PROG_ and HYBRID_ prefixes to handle all relevant positions
                                    if pos.comment and (pos.comment.startswith("PROG_") or pos.comment.startswith("HYBRID_")):
                                        parts = pos.comment.split('_')
                                        if len(parts) >= 2:
                                            setup_ids.add(parts[1])
                                            progressive_positions.append(pos)
                            
                            # If we don't have a complete setup yet and there's a signal, open positions
                            if not setup_ids or len([p for p in progressive_positions if p.comment.split('_')[1] == list(setup_ids)[-1] if len(p.comment.split('_')) >= 2]) < self.positions_per_setup:
                                if long_condition:
                                    new_positions = self.execute_trade_setup(True)
                                    if new_positions:
                                        print(f"Opened {len(new_positions)} hybrid progressive long positions for {current_symbol}")
                                elif short_condition:
                                    new_positions = self.execute_trade_setup(False)
                                    if new_positions:
                                        print(f"Opened {len(new_positions)} hybrid progressive short positions for {current_symbol}")
                                else:
                                    print(f"No entry signals for {current_symbol}")
                            else:
                                # Even with a complete setup, check positions for drawdown to add layers
                                buy_positions = [p for p in positions if p.type == 0] if positions else []
                                sell_positions = [p for p in positions if p.type == 1] if positions else []
                                
                                is_in_drawdown = False
                                for pos_list in [buy_positions, sell_positions]:
                                    if not pos_list:
                                        continue
                                    
                                    # Calculate drawdown
                                    total_volume = sum(pos.volume for pos in pos_list)
                                    avg_entry = sum(pos.price_open * pos.volume for pos in pos_list) / total_volume
                                    current_price = mt5.symbol_info_tick(current_symbol).bid if pos_list[0].type == 0 else mt5.symbol_info_tick(current_symbol).ask
                                    
                                    # Calculate drawdown in points
                                    point_value = self.get_point_value()
                                    drawdown = (avg_entry - current_price) if pos_list[0].type == 0 else (current_price - avg_entry)
                                    drawdown_points = drawdown / point_value
                                    
                                    if drawdown_points > 0:
                                        is_in_drawdown = True
                                        print(f"{current_symbol} is in drawdown: {drawdown_points:.1f} points")
                                        break
                                
                                if is_in_drawdown:
                                    print(f"Will manage drawdown layers for {current_symbol} in the next cycle")
                                else:
                                    print(f"Already have a complete progressive setup for {current_symbol} without drawdown")
                        elif self.enable_progressive:
                            # For Progressive Lock-in strategy
                            # Count how many positions we have with progressive lock-in setup
                            progressive_positions = []
                            setup_ids = set()
                            
                            if positions:
                                for pos in positions:
                                    if pos.comment and pos.comment.startswith("PROG_"):
                                        parts = pos.comment.split('_')
                                        if len(parts) >= 2:
                                            setup_ids.add(parts[1])
                                            progressive_positions.append(pos)
                            
                            # If we don't have a complete setup yet and there's a signal, open positions
                            if not setup_ids or len([p for p in progressive_positions if p.comment.split('_')[1] == list(setup_ids)[-1]]) < self.positions_per_setup:
                                if long_condition:
                                    new_positions = self.execute_trade_setup(True)
                                    if new_positions:
                                        print(f"Opened {len(new_positions)} progressive long positions for {current_symbol}")
                                elif short_condition:
                                    new_positions = self.execute_trade_setup(False)
                                    if new_positions:
                                        print(f"Opened {len(new_positions)} progressive short positions for {current_symbol}")
                                else:
                                    print(f"No entry signals for {current_symbol}")
                            else:
                                print(f"Already have a complete progressive setup for {current_symbol} with {len(progressive_positions)} positions")
                        elif self.enable_drawdown_layering:
                            # For Drawdown Layering strategy
                            # We don't need to wait for a signal, just check positions for drawdown
                            if positions:
                                # Check for positions in drawdown
                                buy_positions = [p for p in positions if p.type == 0]
                                sell_positions = [p for p in positions if p.type == 1]
                                
                                # Process existing drawdown for immediate layer adding (in case the manage_positions didn't)
                                for pos_list, is_buy in [(buy_positions, True), (sell_positions, False)]:
                                    if not pos_list:
                                        continue
                                    
                                    # Calculate drawdown
                                    point_value = self.get_point_value()
                                    total_volume = sum(pos.volume for pos in pos_list)
                                    avg_entry = sum(pos.price_open * pos.volume for pos in pos_list) / total_volume
                                    current_price = mt5.symbol_info_tick(current_symbol).bid if is_buy else mt5.symbol_info_tick(current_symbol).ask
                                    
                                    # Calculate drawdown in points
                                    drawdown = (avg_entry - current_price) if is_buy else (current_price - avg_entry)
                                    drawdown_points = abs(drawdown / point_value)
                                    
                                    if drawdown_points > 0:
                                        print(f"{current_symbol} positions in {drawdown_points:.1f} points drawdown")
                                        
                                        # Count existing layers
                                        setup_id = f"default_{current_symbol}_{'buy' if is_buy else 'sell'}"
                                        existing_layers = 0
                                        for pos in pos_list:
                                            if pos.comment and len(pos.comment.split('_')) > 2 and pos.comment.split('_')[2].startswith('L'):
                                                existing_layers += 1
                                        
                                        # Calculate required layers based on drawdown threshold
                                        required_layers = math.ceil(drawdown_points / self.drawdown_layer_threshold)
                                        required_layers = min(required_layers, self.max_layers)
                                        
                                        # Check if we need to add a layer
                                        if existing_layers < required_layers:
                                            layer_to_add = existing_layers + 1
                                            print(f"{current_symbol} drawdown: {drawdown_points:.1f} points requires {required_layers} layers, adding layer {layer_to_add}")
                                            self.add_layer(setup_id, is_buy, layer_to_add)
                                        else:
                                            # Log the drawdown situation
                                            print(f"{current_symbol} drawdown: {drawdown_points:.1f} points requires {required_layers} layers, already have {existing_layers}")
                                
                                print(f"Drawdown positions are being managed for {current_symbol}")
                            else:
                                # No positions yet, open initial positions if we have a signal
                                if long_condition:
                                    new_positions = self.execute_trade_setup(True)
                                    if new_positions:
                                        print(f"Opened initial {len(new_positions)} drawdown long positions for {current_symbol}")
                                elif short_condition:
                                    new_positions = self.execute_trade_setup(False)
                                    if new_positions:
                                        print(f"Opened initial {len(new_positions)} drawdown short positions for {current_symbol}")
                                else:
                                    print(f"No entry signals for {current_symbol} to open initial positions")
                        elif self.enable_trailing_sl:
                            # For Trailing Stop Loss strategy
                            # Check for existing positions with TSL comment
                            tsl_positions = []
                            if positions:
                                for pos in positions:
                                    if pos.comment and pos.comment.startswith("TSL_"):
                                        tsl_positions.append(pos)
                            
                            # If no positions yet, open a new one on signal
                            if not tsl_positions:
                                if long_condition:
                                    new_positions = self.execute_trade_setup(True)
                                    if new_positions:
                                        print(f"Opened trailing stop loss long position for {current_symbol}")
                                elif short_condition:
                                    new_positions = self.execute_trade_setup(False)
                                    if new_positions:
                                        print(f"Opened trailing stop loss short position for {current_symbol}")
                                else:
                                    print(f"No entry signals for {current_symbol} to open trailing stop loss position")
                            else:
                                print(f"Already have a trailing stop loss position for {current_symbol}, managing with checkpoints")
                                # Check for positions that have reached checkpoints
                                for pos in tsl_positions:
                                    is_buy = pos.type == 0
                                    current_price = mt5.symbol_info_tick(current_symbol).bid if is_buy else mt5.symbol_info_tick(current_symbol).ask
                                    point_value = self.get_point_value()
                                    
                                    # Calculate profit in points
                                    profit_distance = (current_price - pos.price_open) if is_buy else (pos.price_open - current_price)
                                    profit_points = profit_distance / point_value
                                    
                                    print(f"TSL position {pos.ticket} is at {profit_points:.1f} points profit")
                        else:
                            # For other strategies, use the original logic
                            if positions_count == 0:
                                if long_condition:
                                    positions = self.execute_trade_setup(True)
                                    if positions:
                                        print(f"Opened {len(positions)} long positions for {current_symbol}")
                                elif short_condition:
                                    positions = self.execute_trade_setup(False)
                                    if positions:
                                        print(f"Opened {len(positions)} short positions for {current_symbol}")
                            else:
                                print(f"Already have {positions_count} active positions for {current_symbol}, not opening new ones")
                    except Exception as e:
                        print(f"Error processing symbol {current_symbol}: {e}")
                        traceback.print_exc()
                    finally:
                        # Restore the original symbol
                        self.symbol = original_symbol
                
                # Wait between checks
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                print(f"Error in trading loop: {e}")
                traceback.print_exc()
                time.sleep(5)
        
        print("Trading bot stopped")
    
    def check_weekend_closing(self):
        """
        Check if it's Saturday 12:00 AM (midnight) Philippine time and manage positions accordingly:
        - Close all positions that are in profit
        - Leave positions in drawdown to hit their TP/SL
        """
        # Get current time in Philippine time (PHT/UTC+8)
        now = datetime.now(pytz.timezone('Asia/Manila'))
        
        # Check if it's Saturday (weekday=5) at midnight (12:00 AM) Philippine time
        # Using a small window (12:00 AM to 12:05 AM) to ensure we don't miss it
        if now.weekday() == 5 and now.hour == 0 and now.minute < 5:
            print(f"End of week closing check - Saturday 12:00 AM (midnight) Philippine Time")
            
            # Process all symbols in multi-symbol mode
            symbols_to_check = self.symbols if self.multi_symbol else [self.symbol]
            
            total_closed = 0
            total_kept = 0
            
            for current_symbol in symbols_to_check:
                # Get all open positions for this symbol
                positions = mt5.positions_get(symbol=current_symbol)
                if not positions:
                    print(f"No open positions to manage for weekend closing for {current_symbol}")
                    continue
                
                closed_count = 0
                kept_count = 0
                
                print(f"Weekend closing check for {current_symbol}:")
                
                for position in positions:
                    # Calculate if position is in profit
                    is_profit = position.profit > 0
                    
                    if is_profit:
                        # Close profitable positions
                        if self.close_position(position.ticket):
                            closed_count += 1
                            print(f"  - Closed profitable position #{position.ticket} with profit {position.profit}")
                    else:
                        # Log positions in drawdown that we're keeping
                        kept_count += 1
                        print(f"  - Keeping position #{position.ticket} in drawdown ({position.profit}). Will hit TP/SL.")
                
                # Log the weekend closing action for this symbol
                print(f"Weekend closing for {current_symbol}: Closed {closed_count} profitable positions, kept {kept_count} positions in drawdown.")
                
                total_closed += closed_count
                total_kept += kept_count
            
            # Log the overall weekend closing action
            print(f"Weekend closing completed for all symbols: Closed {total_closed} profitable positions, kept {total_kept} positions in drawdown.")

    def manage_exit_signal_positions(self, positions):
        """Manage positions based on exit signals or Max TP"""
        try:
            if not positions:
                return
            
            # Group positions by symbol
            positions_by_symbol = {}
            for pos in positions:
                if pos.symbol not in positions_by_symbol:
                    positions_by_symbol[pos.symbol] = []
                positions_by_symbol[pos.symbol].append(pos)
                
            for symbol, symbol_positions in positions_by_symbol.items():
                # Check if any position has hit Max TP
                max_tp_hit = False
                for pos in symbol_positions:
                    point_value = self.get_point_value()
                    profit_points = (pos.price_current - pos.price_open) / point_value if pos.type == 0 else (pos.price_open - pos.price_current) / point_value
                    if profit_points >= self.tp_points:
                        max_tp_hit = True
                        break
                
                if max_tp_hit:
                    print(f"Max TP hit for {symbol}, closing all positions")
                    for pos in symbol_positions:
                        self.close_position(pos.ticket)
                    continue
                    
                # Get current WMI signal values
                df = self.get_historical_data_for_symbol(symbol, self.timeframe, 2)
                if len(df) < 2:
                    continue
                    
                # Calculate WMI components
                a = 20  # Percent K Length
                b = 3   # Percent D Length
                
                # Calculate WMI signal
                ll = df['low'].rolling(window=a).min()
                hh = df['high'].rolling(window=a).max()
                diff = hh - ll
                rdiff = df['close'] - (hh + ll) / 2
                avgrel = rdiff.ewm(span=b).mean().ewm(span=b).mean()
                avgdiff = diff.ewm(span=b).mean().ewm(span=b).mean()
                smi_signal = (avgrel / (avgdiff / 2) * 100).fillna(0)
                smi_signal_ema = smi_signal.ewm(span=10).mean()
                
                # Get the last values
                current_smi_signal = smi_signal.iloc[-1]
                current_smi_ema = smi_signal_ema.iloc[-1]
                prev_smi_ema = smi_signal_ema.iloc[-2]
                
                # Check if EMA has crossed midline (0)
                ema_crossed_midline = (prev_smi_ema > 0 and current_smi_ema <= 0) or (prev_smi_ema < 0 and current_smi_ema >= 0)
                
                if ema_crossed_midline:
                    for pos in symbol_positions:
                        # Calculate profit percentage
                        profit_points = (pos.price_current - pos.price_open) / point_value if pos.type == 0 else (pos.price_open - pos.price_current) / point_value
                        profit_percentage = (profit_points * point_value) / pos.price_open * 100
                        
                        # Only close if profit is at least 0.02%
                        if profit_percentage >= 0.02:
                            print(f"Closing {symbol} position {pos.ticket} at {profit_percentage:.2f}% profit due to WMI EMA crossing midline")
                            self.close_position(pos.ticket)
                        else:
                            print(f"Keeping {symbol} position {pos.ticket} open (profit: {profit_percentage:.2f}%) despite WMI EMA crossing midline")
            
        except Exception as e:
            print(f"Error managing exit signal positions: {str(e)}")
            traceback.print_exc()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_indicator', methods=['POST'])
def upload_indicator():
    """Upload and register a custom Pine Script indicator"""
    if 'indicator_file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"})
        
    file = request.files['indicator_file']
    
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"})
        
    if file:
        try:
            # Read file content
            file_content = file.read().decode('utf-8')
            
            # Save the file
            file_path = pine_handler.save_uploaded_file(file_content, file.filename)
            
            # Try to convert Pine script to Python
            if pine_handler.convert_pine_to_python(file.filename):
                global active_indicator
                active_indicator = file.filename
                return jsonify({
                    "status": "success", 
                    "message": f"Indicator {file.filename} uploaded and registered successfully",
                    "indicator_name": file.filename
                })
            else:
                return jsonify({
                    "status": "error", 
                    "message": f"Uploaded file is not a supported indicator format"
                })
                
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error processing indicator: {str(e)}"})
    
    return jsonify({"status": "error", "message": "Unknown error"})

@app.route('/indicators', methods=['GET'])
def list_indicators():
    """List all available indicators"""
    indicators = list(pine_handler.indicators.keys())
    return jsonify({"indicators": indicators})

@app.route('/start', methods=['POST'])
def start_bot():
    global bot_threads, bot_instances, active_indicator, pine_handler
    
    # Get settings from request
    data = request.json
    
    # Handle login credentials
    login = data.get('login', '')
    try:
        login = int(login) if login and login.strip() else None
    except (ValueError, AttributeError):
        login = None
        
    # Handle symbols selection (now can be a list)
    symbols = data.get('symbols', [])
    if not symbols:
        # Backward compatibility for single symbol
        symbol = data.get('symbol', 'EURUSD')
        symbols = [symbol]
    
    # Get timeframe selection
    timeframe = getattr(mt5, data.get('timeframe', 'TIMEFRAME_M5'))
    
    # Helper function to get parameter with backward compatibility
    def get_param(new_name, old_name, default_value, convert_func=float):
        # Check for new name first, then fall back to old name
        value = data.get(new_name)
        if value is None:
            value = data.get(old_name, default_value)
        return convert_func(value)
    
    # Base settings to be applied to all symbols
    base_settings = {
        'timeframe': timeframe,
        'lot_size': float(data.get('lot_size', 0.01)),
        'sl_points': get_param('sl_points', 'sl_pips', 1000),
        'tp_points': get_param('tp_points', 'tp_pips', 1000),
        'positions_per_setup': int(data.get('positions_per_setup', 3)),
        'magic_number': int(data.get('magic_number', 234000)),
        'trade_direction': data.get('trade_direction', 'BOTH'),
        'login': login,
        'password': data.get('password', ''),
        'server': data.get('server', ''),
        'enable_progressive': data.get('enable_progressive', True),
        'positive_sl_points': get_param('positive_sl_points', 'positive_sl_pips', 20),
        'breakeven_trigger_points': get_param('breakeven_trigger_points', 'breakeven_trigger_pips', 20),
        'enable_drawdown_layering': data.get('enable_drawdown_layering', False),
        'drawdown_layer_threshold': float(data.get('drawdown_layer_threshold', 20)),
        'positions_per_layer': int(data.get('positions_per_layer', 3)),
        'minimum_profit_per_position': float(data.get('minimum_profit_per_position', 20)),
        'max_layers': int(data.get('max_layers', 5)),
        'enable_trailing_sl': data.get('enable_trailing_sl', False),
        'trailing_breakeven_points': get_param('trailing_breakeven_points', 'trailing_breakeven_pips', 30),
        'trailing_positive_sl_points': get_param('trailing_positive_sl_points', 'trailing_positive_sl_pips', 30),
        'trailing_positive_trigger_points': get_param('trailing_positive_trigger_points', 'trailing_positive_trigger_pips', 60),
        'trailing_tp_points': get_param('trailing_tp_points', 'trailing_tp_pips', 90),
        'trailing_sl_points': get_param('trailing_sl_points', 'trailing_sl_pips', 30),
        'dynamic_checkpoints': int(data.get('dynamic_checkpoints', 5)),
        'weekend_closing': data.get('weekend_closing', True),
        # Exit Signal or Max TP strategy settings
        'reentry_count': int(data.get('reentry_count', 5)),  # Number of reentries for drawdown positions
        'strategy': data.get('strategy', 'exit_signal_or_max_tp'),  # Default strategy
        'symbols': symbols,  # Add all symbols to the settings
        'multi_symbol': data.get('multi_symbol', len(symbols) > 1)  # Set multi_symbol based on number of symbols or explicit setting
    }
    
    # Add custom indicator if selected
    custom_indicator = data.get('custom_indicator', None)
    if custom_indicator:
        base_settings['custom_indicator'] = custom_indicator
    elif active_indicator:
        base_settings['custom_indicator'] = active_indicator
    
    # Add pine script handler
    base_settings['pine_handler'] = pine_handler
    
    # Initialize MT5 once for all symbols
    mt5_initialized = False
    for symbol in symbols:
        # Create settings for this symbol
        symbol_settings = base_settings.copy()
        symbol_settings['symbol'] = symbol
        
        # Check if a bot is already running for this symbol
        if symbol in bot_instances and bot_instances[symbol].running:
            print(f"Bot for {symbol} is already running. Skipping.")
            continue
        
        # Create and start bot thread for this symbol
        bot_instances[symbol] = TradingBot(symbol_settings)
        
        # Initialize MT5 once
        if not mt5_initialized:
            if not bot_instances[symbol].initialize_mt5():
                # If MT5 initialization fails, return error
                return jsonify({"status": "error", "message": bot_instances[symbol].error_message})
            mt5_initialized = True
        
        # Start thread for this symbol
        bot_threads[symbol] = threading.Thread(target=bot_instances[symbol].run, args=(False,))  # False means don't initialize MT5 again
        bot_threads[symbol].daemon = True
        bot_threads[symbol].start()
        
        print(f"Started bot for {symbol}")
    
    # Wait a bit to check for initialization errors
    time.sleep(2)
    
    # Check if any bots have errors
    errors = {}
    for symbol, bot in bot_instances.items():
        if bot.error_message:
            errors[symbol] = bot.error_message
    
    if errors:
        return jsonify({"status": "error", "message": "Error starting bots", "errors": errors})
    
    bot_running = len(bot_instances) > 0
    return jsonify({
        "status": "success", 
        "message": f"Successfully started trading bots for {len(bot_threads)} symbols",
        "active_symbols": list(bot_threads.keys())
    })

@app.route('/stop', methods=['POST'])
def stop_bot():
    global bot_threads, bot_instances, bot_running
    
    if not bot_instances:
        return jsonify({"status": "error", "message": "No bots are running"})
    
    data = request.json or {}
    symbol = data.get('symbol', None)
    
    if symbol:
        # Stop a specific bot
        if symbol in bot_instances:
            bot_instances[symbol].running = False
            if symbol in bot_threads:
                del bot_threads[symbol]
            print(f"Stopped bot for {symbol}")
            
            if not bot_threads:
                bot_running = False
                # Shutdown MT5 only if no bots are running
                mt5.shutdown()
            
            return jsonify({"status": "success", "message": f"Bot stopped for {symbol}"})
        else:
            return jsonify({"status": "error", "message": f"No bot running for {symbol}"})
    else:
        # Stop all bots
        for sym, bot in bot_instances.items():
            bot.running = False
            print(f"Stopped bot for {sym}")
        
        bot_threads.clear()
    bot_running = False
    
    # Shutdown MT5
    mt5.shutdown()
    
    return jsonify({"status": "success", "message": "All bots stopped successfully"})

@app.route('/status', methods=['GET'])
def get_status():
    global bot_instances
    
    symbol = request.args.get('symbol', None)
    
    if symbol:
        # Get status for a specific symbol
        if symbol in bot_instances:
            return get_bot_status(symbol, bot_instances[symbol])
        else:
            return jsonify({"status": "error", "message": f"No bot running for {symbol}"})
    
    # Get status for all symbols
    all_status = {
        "running": len(bot_instances) > 0,
        "bots": {}
    }
    
    # Add account info if any bots are running
    if bot_instances:
        try:
            # Check MT5 connection
            if not mt5.initialize():
                all_status["mt5_connected"] = False
                all_status["warning"] = "MT5 connection lost. Attempting to reconnect..."
            else:
                all_status["mt5_connected"] = True
                
                # Get account info
                account_info = mt5.account_info()
                if account_info:
                    all_status["account"] = {
                        "balance": account_info.balance,
                        "equity": account_info.equity,
                        "margin": account_info.margin,
                        "free_margin": account_info.margin_free,
                        "server": account_info.server
                    }
                    
                # Get individual bot statuses
                for sym, bot in bot_instances.items():
                    bot_status = get_individual_bot_status(sym, bot)
                    all_status["bots"][sym] = bot_status
                
                # Clean up
                mt5.shutdown()
        except Exception as e:
            all_status["warning"] = f"Error checking MT5 status: {str(e)}"
    
    return jsonify(all_status)

def get_individual_bot_status(symbol, bot):
    status = {
        "running": bot.running,
        "error": bot.error_message if hasattr(bot, 'error_message') else None,
        "symbol": symbol
    }
    
    # Add position info if running
    if bot.running:
        try:
            # Get positions for this symbol
            positions = mt5.positions_get(symbol=symbol)
            if positions:
                status["positions"] = len(positions)
            
                # Count active layers if drawdown layering is enabled
                if hasattr(bot, 'enable_drawdown_layering') and bot.enable_drawdown_layering:
                    layers = set()
                    for pos in positions:
                        if pos.comment and len(pos.comment.split('_')) > 3:
                            if pos.comment.split('_')[3].startswith('L'):
                                layers.add(pos.comment.split('_')[3])
                    status["active_layers"] = len(layers)
            else:
                status["positions"] = 0
                status["active_layers"] = 0
        except Exception as e:
            status["warning"] = f"Error checking positions: {str(e)}"
    
    return status

def get_bot_status(symbol, bot):
    status = get_individual_bot_status(symbol, bot)
    
    # Add account info if the bot is running
    if bot.running:
        try:
            # Check MT5 connection
            if not mt5.initialize():
                status["mt5_connected"] = False
                status["warning"] = "MT5 connection lost. Attempting to reconnect..."
            else:
                status["mt5_connected"] = True
                
                # Get account info
                account_info = mt5.account_info()
                if account_info:
                    status["account"] = {
                        "balance": account_info.balance,
                        "equity": account_info.equity,
                        "margin": account_info.margin,
                        "free_margin": account_info.margin_free,
                        "server": account_info.server
                    }
                    
                # Clean up
                mt5.shutdown()
        except Exception as e:
            status["warning"] = f"Error checking MT5 status: {str(e)}"
    
    return jsonify(status)

@app.route('/start_instance', methods=['POST'])
def start_instance():
    """
    Start a trading bot instance with customized settings
    This endpoint is used by the Advanced Settings modal where users can customize
    specific aspects of the trading strategy.
    """
    global bot_threads, bot_instances, active_indicator
    data = request.json
    
    # Get the bot ID - this is also the symbol most of the time
    instance_id = data.get('instance_id', 1)
    
    # Handle multi-symbol mode
    symbols = data.get('symbols', [])
    if not symbols:
        # Backward compatibility for single symbol
        symbol = data.get('symbol', 'EURUSD')
        symbols = [symbol]
    else:
        # Ensure symbols is a list
        if isinstance(symbols, str):
            symbols = [symbols]
    
    # Use the first symbol as the primary symbol
    symbol = symbols[0] if symbols else 'EURUSD'
    
    # Helper function to get parameter with backward compatibility
    def get_param(new_name, old_name, default_value, convert_func=float):
        # Check for new name first, then fall back to old name
        value = data.get(new_name)
        if value is None:
            value = data.get(old_name, default_value)
        return convert_func(value)
    
    # Create base settings
    instance_settings = {
        'symbol': symbol,
        'symbols': symbols,
        'multi_symbol': data.get('multi_symbol', len(symbols) > 1),
        'timeframe': getattr(mt5, data.get('timeframe', 'TIMEFRAME_M15')),
        'lot_size': float(data.get('lot_size', 0.01)),
        'sl_points': get_param('sl_points', 'sl_pips', 1000),
        'tp_points': get_param('tp_points', 'tp_pips', 1000),
        'trade_direction': data.get('trade_direction', 'BOTH'),
        'login': data.get('login'),
        'password': data.get('password', ''),
        'server': data.get('server', ''),
        'weekend_closing': data.get('weekend_closing', True),
        'custom_indicator': data.get('custom_indicator', active_indicator),
        'instance_id': instance_id,
        'pine_handler': pine_handler,
        'enable_progressive': False,
        'enable_drawdown_layering': False,
        'enable_trailing_sl': False,
        'trailing_breakeven_points': 300,
        'trailing_tp_points': 900,
        'trailing_sl_points': 300,
        'dynamic_checkpoints': int(data.get('dynamic_checkpoints', 5)),
        'prop_firm_mode': data.get('prop_firm_mode', False),
        'trading_start_time': data.get('trading_start_time', '08:00'),
        'trading_end_time': data.get('trading_end_time', '17:00'),
        'comment_off': data.get('comment_off', False),
        'randomness_level': data.get('randomness_level', 'medium'),
        'strategy': data.get('strategy', 'progressive')
    }
    
    # Set strategy-specific settings based on selected strategy
    strategy = data.get('strategy', 'progressive')
    instance_settings['enable_progressive'] = False
    instance_settings['enable_drawdown_layering'] = False
    instance_settings['enable_trailing_sl'] = False
    
    if strategy == 'exit_signal_or_max_tp':
        # Set exit signal or max TP specific settings
        instance_settings['reentry_count'] = int(data.get('reentry_count', 5))
    elif strategy == 'progressive':
        # Rest of the code remains the same
        instance_settings['enable_progressive'] = True
        instance_settings['positions_per_setup'] = int(data.get('positions_per_setup', 3))
        
        # Calculate take profit levels based on Max TP divided by positions
        total_tp = int(data.get('tp_points', 1000))
        positions_count = int(data.get('positions_per_setup', 3))
        
        # Divide the Max TP by number of positions to get TP per position
        tp_per_position = total_tp / positions_count
        
        # Set progressive TP values - these are now calculated in the execute_trade_setup method
        instance_settings['tp_points'] = total_tp  # Keep the overall TP value
        
        # Standard settings
        instance_settings['positive_sl_points'] = int(tp_per_position)  # Positive SL equal to first TP
        instance_settings['breakeven_trigger_points'] = int(tp_per_position)  # Breakeven at first TP
    elif strategy == 'drawdown':
        instance_settings['enable_drawdown_layering'] = True
        
        # Get user configured values
        max_sl = int(data.get('sl_points', 1000))
        num_layers = int(data.get('max_layers', 5))
        tp_per_position = int(data.get('tp_per_position', 200))
        
        # Calculate layer threshold (distance between layers)
        layer_threshold = max_sl / num_layers
        
        # Set drawdown layering parameters
        instance_settings['drawdown_layer_threshold'] = int(layer_threshold)
        instance_settings['positions_per_layer'] = 3
        instance_settings['tp_per_position'] = tp_per_position  # Store the configured TP per position
        instance_settings['minimum_profit_per_position'] = tp_per_position  # Use the same value for minimum profit
        instance_settings['max_layers'] = num_layers
        instance_settings['max_drawdown_points'] = max_sl  # Store max SL as the limit for layering
        
        print(f"Initializing Drawdown Layering with: Layer Threshold={layer_threshold}, TP per position={tp_per_position}, Max Layers={num_layers}")
    
    elif strategy == 'trailing_stop':
        instance_settings['enable_trailing_sl'] = True
        # Get dynamic checkpoint value
        checkpoint_count = int(data.get('dynamic_checkpoints', 5))
        instance_settings['dynamic_checkpoints'] = checkpoint_count
        
        # Set the Take Profit value based on user input
        tp_value = int(data.get('tp_points', 1000))
        instance_settings['trailing_tp_points'] = tp_value
        
        # Calculate checkpoint size for trailing stops
        checkpoint_size = tp_value / checkpoint_count
        
        # Calculate trailing parameters based on checkpoints
        instance_settings['trailing_sl_points'] = int(data.get('sl_points', 1000))  # Use the exact SL value provided by user
        instance_settings['trailing_breakeven_points'] = int(checkpoint_size)  # First checkpoint
        instance_settings['trailing_positive_sl_points'] = int(checkpoint_size * 0.5)  # Half of a checkpoint
        instance_settings['trailing_positive_trigger_points'] = int(checkpoint_size * 2)  # At second checkpoint
    
    elif strategy == 'hybrid_progressive_drawdown':
        # Enable both strategies
        instance_settings['enable_progressive'] = True
        instance_settings['enable_drawdown_layering'] = True
        
        # Get position and layer counts
        positions_count = int(data.get('positions_per_setup', 3))
        num_layers = int(data.get('max_layers', 5))
        instance_settings['positions_per_setup'] = positions_count
        instance_settings['max_layers'] = num_layers
        
        # Calculate progressive parameters
        total_tp = int(data.get('tp_points', 1000))
        tp_per_position = total_tp / positions_count
        
        # Progressive part
        instance_settings['tp_points'] = total_tp
        instance_settings['positive_sl_points'] = int(tp_per_position)
        instance_settings['breakeven_trigger_points'] = int(tp_per_position)
        
        # Calculate drawdown parameters
        max_sl = int(data.get('sl_points', 1000))
        layer_threshold = max_sl / num_layers
        
        # Drawdown part
        instance_settings['drawdown_layer_threshold'] = int(layer_threshold)
        instance_settings['positions_per_layer'] = 3
        instance_settings['minimum_profit_per_position'] = int(data.get('tp_per_position', 200))
        instance_settings['max_drawdown_points'] = max_sl
    
    elif strategy == 'hybrid_trailing_drawdown':
        # Enable both strategies
        instance_settings['enable_trailing_sl'] = True
        instance_settings['enable_drawdown_layering'] = True
        
        # Get checkpoint and layer counts
        checkpoint_count = int(data.get('dynamic_checkpoints', 5))
        num_layers = int(data.get('max_layers', 5))
        
        # Store in settings
        instance_settings['dynamic_checkpoints'] = checkpoint_count
        instance_settings['max_layers'] = num_layers
        
        # Trailing SL part
        # Set the Take Profit value based on user input
        tp_value = int(data.get('tp_points', 1000))
        instance_settings['trailing_tp_points'] = tp_value
        
        # Calculate checkpoint size for trailing stops
        checkpoint_size = tp_value / checkpoint_count
        
        # Calculate trailing parameters based on checkpoints
        max_sl = int(data.get('sl_points', 1000))
        instance_settings['trailing_sl_points'] = max_sl  # Initial SL
        instance_settings['trailing_breakeven_points'] = int(checkpoint_size * 0.5)  # Move to breakeven earlier
        instance_settings['trailing_positive_sl_points'] = int(checkpoint_size * 0.3)  # Tighter trailing
        instance_settings['trailing_positive_trigger_points'] = int(checkpoint_size)  # Start trailing at first checkpoint
        
        # Drawdown layering part
        layer_threshold = max_sl / num_layers
        
        # Adjust drawdown parameters for better protection
        instance_settings['drawdown_layer_threshold'] = int(layer_threshold * 0.8)  # Add layers more frequently
        instance_settings['positions_per_layer'] = 3
        instance_settings['minimum_profit_per_position'] = int(checkpoint_size)  # Set minimum profit to checkpoint size
        instance_settings['max_drawdown_points'] = max_sl
    
    # Add selected indicator if provided
    selected_indicator = data.get('selected_indicator')
    if selected_indicator:
        instance_settings['custom_indicator'] = selected_indicator
    
    # Create the bot instance
    bot_instances[f"instance_{instance_id}"] = TradingBot(instance_settings)
    
    # Initialize MT5 and start the bot
    if not bot_instances[f"instance_{instance_id}"].initialize_mt5():
        error_msg = bot_instances[f"instance_{instance_id}"].error_message
        return jsonify({"status": "error", "message": error_msg or "Failed to initialize MT5"})
    
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=bot_instances[f"instance_{instance_id}"].run, args=(False,))
    bot_thread.daemon = True
    bot_thread.start()
    
    print(f"Started MT5 instance {instance_id} for {symbols}")
    
    # Return success
    return jsonify({
        "status": "success",
        "message": f"MT5 Instance {instance_id} started successfully",
        "instance_id": instance_id
    })

@app.route('/stop_instance', methods=['POST'])
def stop_instance():
    """Stop a specific MT5 instance"""
    data = request.json
    instance_id = data.get('instance_id')
    
    if instance_id is None:
        return jsonify({"success": False, "message": "Instance ID is required"})
    
    instance_key = f"instance_{instance_id}"
    
    if instance_key not in bot_instances:
        return jsonify({"success": False, "message": f"MT5 Instance {instance_id} is not running"})
    
    # Stop the bot
    bot_instances[instance_key].running = False
    
    # Remove from instances
    bot = bot_instances.pop(instance_key)
    
    # Check if all instances are stopped
    if not bot_instances:
        # Shutdown MT5 if all instances are stopped
        mt5.shutdown()
    
    return jsonify({
        "success": True,
        "message": f"MT5 Instance {instance_id} stopped successfully"
    })

@app.route('/get_high_impact_news', methods=['GET'])
def get_high_impact_news():
    """Fetch high impact news data for the next 7 days"""
    try:
        from news_handler import NewsHandler
        handler = NewsHandler()
        news = handler.fetch_high_impact_news()
        
        # Format the news for easier display in the UI
        formatted_news = []
        for item in news:
            formatted_news.append({
                'timestamp': item['timestamp'].isoformat(),
                'currency': item['currency'],
                'event': item['event'],
                'impact': item['impact']
            })
            
        return jsonify({'status': 'success', 'news': formatted_news})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True) 