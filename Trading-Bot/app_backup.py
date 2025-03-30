import os
import sys
import time
import json
import logging
import threading
import traceback
import subprocess
from datetime import datetime, timezone, timedelta
import pytz
import psutil
from flask import Flask, request, render_template, jsonify, flash, redirect, url_for
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash
import config
from strategies.ace_strategy import check_entry_conditions, get_stop_loss, get_take_profit
from custom_indicators import PineScriptHandler
import math
import random
from news_handler import news_handler  # Import the news handler singleton

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

# Create and configure the app
app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trading_bot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions with the app
db.init_app(app)
login_manager.init_app(app)

# Define the User and License models
class User(UserMixin, db.Model):
    """User account model for authentication and license management"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.username}>'

class License(db.Model):
    """License model for managing user access to the trading bot"""
    __tablename__ = 'licenses'
    
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(23), unique=True, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, active, expired
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    activation_date = db.Column(db.DateTime, nullable=True)
    expiration_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('license', uselist=False))
    
    def __repr__(self):
        return f'<License {self.license_key}>'
    
    @property
    def is_active(self):
        """Check if license is active"""
        if self.status != 'active':
            return False
        
        if not self.expiration_date:
            return False
            
        return self.expiration_date > datetime.utcnow()

# User loader callback
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Import blueprints
from auth import auth
from main import main

# Register blueprints
app.register_blueprint(auth)
app.register_blueprint(main)

# Create database tables
with app.app_context():
    db.create_all()
    
    # Create admin user if it doesn't exist
    if User.query.filter_by(username='admin').first() is None:
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
    
    # Create requested users with licenses
    # User 1
    if User.query.filter_by(email='edventure0312@gmail.com').first() is None:
        user1 = User(
            username='edventure',
            email='edventure0312@gmail.com',
            password_hash=generate_password_hash('password123'),
            is_admin=False
        )
        db.session.add(user1)
        db.session.commit()
        
        license1 = License(
            license_key='AB123-CD456-EF789-GH012',
            status='active',
            user_id=user1.id,
            activation_date=datetime.utcnow(),
            expiration_date=datetime.utcnow() + timedelta(days=365)
        )
        db.session.add(license1)
        db.session.commit()
    
    # User 2
    if User.query.filter_by(email='niel.utrillo@gmail.com').first() is None:
        user2 = User(
            username='niel',
            email='niel.utrillo@gmail.com',
            password_hash=generate_password_hash('password123'),
            is_admin=False
        )
        db.session.add(user2)
        db.session.commit()
        
        license2 = License(
            license_key='IJ123-KL456-MN789-OP012',
            status='active',
            user_id=user2.id,
            activation_date=datetime.utcnow(),
            expiration_date=datetime.utcnow() + timedelta(days=365)
        )
        db.session.add(license2)
        db.session.commit()
    
    # User 3 (Admin)
    if User.query.filter_by(email='edsonlazaro0312@gmail.com').first() is None:
        user3 = User(
            username='edson',
            email='edsonlazaro0312@gmail.com',
            password_hash=generate_password_hash('password123'),
            is_admin=True
        )
        db.session.add(user3)
        db.session.commit()
        
        license3 = License(
            license_key='QR123-ST456-UV789-WX012',
            status='active',
            user_id=user3.id,
            activation_date=datetime.utcnow(),
            expiration_date=datetime.utcnow() + timedelta(days=365)
        )
        db.session.add(license3)
        db.session.commit()

# Global variables
bot_running = False
bot_threads = {}  # Dictionary to store multiple bot threads keyed by symbol
bot_instances = {}  # Dictionary to store multiple bot threads by instance number
mt5_instances = {}  # Dictionary to store MT5 instance configurations
mt5_initialized = False
pine_handler = PineScriptHandler()
active_indicator = "HWR.pine"  # Set HWR.pine as the default active indicator

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
        self.symbol = settings.get('symbol', 'EURUSD')
        self.symbols = settings.get('symbols', [self.symbol])
        self.multi_symbol = settings.get('multi_symbol', len(self.symbols) > 1)
        self.timeframe = settings.get('timeframe', mt5.TIMEFRAME_M15)
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
        self.first_tp_points = settings.get('first_tp_points', 20)
        self.second_tp_points = settings.get('second_tp_points', 50)
        self.positive_sl_points = settings.get('positive_sl_points', 20)
        self.breakeven_trigger_points = settings.get('breakeven_trigger_points', 20)
        self.enable_progressive = settings.get('enable_progressive', False)
        
        # Drawdown Layering Strategy settings
        self.enable_drawdown_layering = settings.get('enable_drawdown_layering', False)
        self.drawdown_layer_threshold = settings.get('drawdown_layer_threshold', 20)
        self.positions_per_layer = settings.get('positions_per_layer', 3)
        self.minimum_profit_per_position = settings.get('minimum_profit_per_position', 20)
        self.max_layers = settings.get('max_layers', 5)
        self.max_drawdown_points = settings.get('max_drawdown_points', self.sl_points)
        
        # Trailing Stop Loss Strategy settings
        self.enable_trailing_sl = settings.get('enable_trailing_sl', False)
        self.trailing_breakeven_points = settings.get('trailing_breakeven_points', 30)
        self.trailing_positive_sl_points = settings.get('trailing_positive_sl_points', 30)
        self.trailing_positive_trigger_points = settings.get('trailing_positive_trigger_points', 60)
        self.trailing_tp_points = settings.get('trailing_tp_points', 90)
        self.trailing_sl_points = settings.get('trailing_sl_points', 30)
        self.dynamic_checkpoints = settings.get('dynamic_checkpoints', 5)
        
        # Exit Signal or Max TP settings
        self.reentry_count = settings.get('reentry_count', 5)
        
        # Custom indicator settings
        self.custom_indicator = settings.get('custom_indicator', None)
        self.pine_handler = settings.get('pine_handler')
        
        # Add new settings for Prop Firm Mode
        self.prop_firm_mode = settings.get('prop_firm_mode', False)
        self.trading_start_time = settings.get('trading_start_time', '08:00')
        self.trading_end_time = settings.get('trading_end_time', '17:00')
        self.comment_off = settings.get('comment_off', False)
        self.randomness_level = settings.get('randomness_level', 'medium')
        
        # High Impact News settings
        self.high_impact_news = settings.get('high_impact_news', False)
        self.news_duration = settings.get('news_duration', 5)  # Default 5 minutes before news
        self.news_stop_points = settings.get('news_stop_points', 200)  # Default 200 points for Buy/Sell Stop
        self.news_orders = {}  # Store pending news orders
        
        # Calculate randomness threshold
        self.randomness_threshold = {
            'low': 0.25,
            'medium': 0.50,
            'high': 0.75
        }.get(self.randomness_level, 0.50)
        
        # Add strategy type
        self.strategy_type = settings.get('strategy', 'exit_signal_or_max_tp')
        
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
        
    def should_open_trade(self):
        """Check if we should open a trade based on Prop Firm Mode settings"""
        if not self.prop_firm_mode:
            return True
            
        # Check trading hours
        now = datetime.now(pytz.timezone('Asia/Manila'))
        current_time = now.strftime('%H:%M')
        
        if not (self.trading_start_time <= current_time <= self.trading_end_time):
            print(f"Outside trading hours ({self.trading_start_time} - {self.trading_end_time})")
            return False
            
        # Apply randomness
        if random.random() < self.randomness_threshold:
            print(f"Randomness check failed (threshold: {self.randomness_threshold})")
            return False
            
        return True
        
    def execute_trade_setup(self, is_buy):
        """Execute a complete trade setup with multiple positions"""
        # Check if we should open a trade
        if not self.should_open_trade():
            print("Trade execution skipped based on Prop Firm Mode settings")
            return []
        
        positions = []
        setup_id = int(time.time())
        current_price = mt5.symbol_info_tick(self.symbol).ask if is_buy else mt5.symbol_info_tick(self.symbol).bid
        
        # Calculate SL and TP
        point_value = self.get_point_value()
        
        # Handle different strategies
        if self.strategy_type == 'exit_signal_or_max_tp':
            # For Exit Signal or Max TP strategy
            sl_points = self.sl_points
            tp_points = self.tp_points
            
            # Check existing positions
            existing_positions = mt5.positions_get(symbol=self.symbol)
            if existing_positions:
                # Count positions and check if we're in drawdown
                existing_count = len(existing_positions)
                positions_in_drawdown = [pos for pos in existing_positions if pos.profit < 0]
                
                # Only allow adding positions if we have positions in drawdown and we're under the reentry limit
                if existing_count >= self.reentry_count:
                    print(f"Maximum number of positions ({self.reentry_count}) reached for {self.symbol}")
                    return []
                
                if not positions_in_drawdown:
                    print(f"No positions in drawdown for {self.symbol}, not opening additional positions")
                    return []
                
                print(f"Found {len(positions_in_drawdown)} positions in drawdown, allowing reentry ({existing_count}/{self.reentry_count})")
            
            sl_price = current_price - (sl_points * point_value) if is_buy else current_price + (sl_points * point_value)
            tp_price = current_price + (tp_points * point_value) if is_buy else current_price - (tp_points * point_value)
            
            # Create order request with empty comment if comment_off is True
            comment = "" if self.comment_off else f"EXIT_{setup_id}_1"
            
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
                
        elif self.strategy_type in ['trailing_stop', 'hybrid_trailing_drawdown']:
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
        try:
            symbol_info_tick = mt5.symbol_info_tick(self.symbol)
            if symbol_info_tick is None:
                print(f"Failed to get symbol tick info for {self.symbol}")
                return None
                
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": order_type,
                "price": symbol_info_tick.ask if order_type == mt5.ORDER_TYPE_BUY else symbol_info_tick.bid,
                "sl": sl,
                "tp": tp,
                "deviation": config.DEVIATION,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Order failed: {result.retcode} - {result.comment}")
                return None
                
            return result.order
        except Exception as e:
            print(f"Error opening position: {e}")
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
            "magic": position.magic,
            "comment": f"Close_{position.comment}",
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
        try:
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                return 0.0001  # Default for forex
            return 10 ** -symbol_info.digits
        except Exception as e:
            print(f"Error getting pip value: {e}")
            return 0.0001
    
    def manage_positions(self):
        """Manage existing positions"""
        try:
            positions = mt5.positions_get(symbol=self.symbol)
            if not positions:
                return
            
            for pos in positions:
                # For Exit Signal or Max TP strategy
                if self.strategy_type == 'exit_signal_or_max_tp':
                    # Check for exit signal
                    df = self.get_historical_data(self.timeframe)
                    if df is not None and self.pine_handler:
                        long_condition, short_condition = self.pine_handler.check_entry_conditions(df, self.custom_indicator)
                        
                        # Close position if exit signal is opposite to position direction
                        if (pos.type == 0 and short_condition) or (pos.type == 1 and long_condition):
                            print(f"Exit signal detected for position {pos.ticket}")
                            self.close_position(pos.ticket)
                    continue
                    
                    # Check if TP is hit
                    if pos.profit >= self.tp_points * self.get_point_value():
                        print(f"Take Profit hit for position {pos.ticket}")
                        self.close_position(pos.ticket)
                    continue
                    
                # For Trailing Stop Loss strategy
                elif self.strategy_type in ['trailing_stop', 'hybrid_trailing_drawdown']:
                    self.manage_trailing_sl([pos])
                    
                    # For hybrid strategy, also manage drawdown layers
                    if self.strategy_type == 'hybrid_trailing_drawdown':
                        self.manage_drawdown_layers([pos])
                
                # Handle other strategies as before...
                
        except Exception as e:
            print(f"Error managing positions: {e}")
            traceback.print_exc()
            
    def manage_drawdown_layers(self, positions):
        try:
            print(f"Checking for drawdown conditions on {self.symbol}...")
            # Group positions by setup ID
            position_groups = {}
            for pos in positions:
                if not pos.comment or not pos.comment.startswith("ACE_"):
                    continue
                    
                # Extract setup ID
                parts = pos.comment.split('_')
                if len(parts) < 2:
                    continue
                    
                setup_id = parts[1]
                if setup_id not in position_groups:
                    position_groups[setup_id] = []
                position_groups[setup_id].append(pos)
            
            point_value = self.get_point_value()
            
            # Process each setup
            for setup_id, setup_positions in position_groups.items():
                if not setup_positions:
                    continue
                
                # Calculate current drawdown
                is_buy = setup_positions[0].type == 0
                
                # Calculate weighted average entry price
                total_volume = sum(pos.volume for pos in setup_positions)
                avg_entry_price = sum(pos.price_open * pos.volume for pos in setup_positions) / total_volume
                
                # Get current price
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
                    if len(pos.comment.split('_')) > 3 and pos.comment.split('_')[3].startswith('L'):
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
                    self.add_layer(setup_id, setup_positions[0].type == 0, layer_to_add)
                    
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
        
        # Open positions
        for i in range(self.positions_per_layer):
            position_num = i + 1
            
            # Create a layer-specific comment
            comment = f"ACE_{setup_id}_L{layer_num}_{position_num}"
            
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
                "comment": comment,
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
    
    def check_weekend_closing(self):
        """Check if it's weekend and manage open positions accordingly"""
        # Only check if weekend closing is enabled
        if not self.weekend_closing:
            return

        # Check if we're in weekend trading hours
        if self.is_weekend_trading_hours():
            print(f"{self.symbol}: Weekend closing is enabled and we are in weekend hours")
            
            # Get current open positions for this symbol
            positions = mt5.positions_get(symbol=self.symbol, magic=self.magic_number)
            
            # Check if it's Saturday at midnight (within 10 minutes of midnight)
            now = datetime.now()
            is_saturday_midnight = now.weekday() == 5 and now.hour == 0 and now.minute < 10
            
            if is_saturday_midnight:
                print(f"{self.symbol}: It's Saturday midnight, closing profitable positions and keeping those in drawdown")
                
                # Get all positions for this symbol
                for position in positions:
                    # Close profitable positions, keep those in drawdown
                    if position.profit > 0:
                        print(f"{self.symbol}: Closing profitable position {position.ticket} with profit {position.profit}")
                        self.close_position(position.ticket)
                    else:
                        print(f"{self.symbol}: Keeping position {position.ticket} in drawdown with profit {position.profit}")
            
            return True  # Signal that we're in weekend trading hours
        
        return False  # Not in weekend trading hours
        
    def is_weekend_trading_hours(self):
        """Check if current time is within weekend trading restriction hours (Sat 12 AM to Mon 7:59 AM PHT)"""
        # Convert current time to Philippine Time (UTC+8)
        now_utc = datetime.now(timezone.utc)
        pht_offset = timedelta(hours=8)
        now_pht = now_utc + pht_offset
        
        # Check if it's Saturday or Sunday or Monday before 8 AM
        is_saturday = now_pht.weekday() == 5  # Saturday is 5
        is_sunday = now_pht.weekday() == 6    # Sunday is 6
        is_monday_before_8am = now_pht.weekday() == 0 and now_pht.hour < 8  # Monday before 8 AM
        
        return is_saturday or is_sunday or is_monday_before_8am

    def trading_loop(self):
        """Main trading loop that continuously monitors the market and executes trades"""
        last_check_time = time.time() - 60  # Check immediately on start
        last_news_check_time = time.time() - 300  # Check news less frequently
        
        while self.running:
            try:
                current_time = time.time()
                
                # Only perform actions at the specified interval
                if current_time - last_check_time >= 60:  # Check every minute
                    last_check_time = current_time
                    
                    # Check if weekend closing is enabled and if we're in weekend hours
                    if self.check_weekend_closing():
                        print(f"{self.symbol}: Weekend trading hours - no new trades will be opened")
                        time.sleep(60)  # Check again in a minute
                        continue
                    
                    # Check for high impact news events every 5 minutes
                    if self.high_impact_news and current_time - last_news_check_time >= 300:
                        last_news_check_time = current_time
                        self.check_news_events()
                    
                    # Check custom indicator if available
                    if self.custom_indicator:
                        self.check_custom_indicator()
                    else:
                        # Use default strategy if no custom indicator
                        self.check_default_strategy()
                    
                    # Update existing positions based on strategy
                    self.manage_positions()
                
                # Sleep to prevent high CPU usage
                time.sleep(1)
                
            except Exception as e:
                print(f"Error in trading loop: {e}")
                traceback.print_exc()
                time.sleep(5)  # Sleep longer after an error

    def check_news_events(self):
        """Check for upcoming high impact news events and create pending orders if needed"""
        if not self.high_impact_news:
            return
            
        try:
            # Get currencies from the symbol
            symbol_currencies = self.get_symbol_currencies(self.symbol)
            if not symbol_currencies:
                return
                
            # Check each currency in the symbol
            for currency in symbol_currencies:
                # Check if there's high impact news coming up within our duration
                upcoming_news = news_handler.get_upcoming_news(currency, self.news_duration)
                if not upcoming_news:
                    # No upcoming news for this currency
                    continue
                    
                # We have upcoming news for this currency
                news_item = upcoming_news[0]  # Get the soonest news event
                print(f"🗞️ High Impact News detected for {currency} - {news_item['event']} in ~{self.news_duration} minutes")
                
                # Check if we already have a pending order for this news event
                news_id = f"{news_item['timestamp']}-{news_item['event']}"
                if news_id in self.news_orders:
                    # We already have pending orders for this news event
                    print(f"Already placed news orders for event: {news_item['event']}")
                    continue
                    
                # Set up buy stop and sell stop orders
                self.place_news_pending_orders(news_item)
                
            except Exception as e:
                print(f"Error checking news events: {e}")
                traceback.print_exc()
    
    def get_symbol_currencies(self, symbol):
        """Extract the currencies from a forex symbol"""
        # For regular forex pairs like EURUSD, GBPJPY, etc.
        if len(symbol) == 6:
            return [symbol[:3], symbol[3:]]
        # For special cases like XAUUSD (gold)
        elif len(symbol) > 6 and symbol.startswith('XAU'):
            return ['XAU', symbol[3:]]
        elif len(symbol) > 6 and symbol.startswith('XAG'):
            return ['XAG', symbol[3:]]
        else:
            # Can't determine currencies, assume the whole symbol
            return [symbol]
    
    def place_news_pending_orders(self, news_item):
        """Place Buy Stop and Sell Stop orders for high impact news"""
        try:
            # Get current price
            symbol_info = mt5.symbol_info_tick(self.symbol)
            current_price = (symbol_info.ask + symbol_info.bid) / 2  # Use the middle price
            
            # Calculate stop levels
            point_value = self.get_point_value()
            price_adjustment = self.news_stop_points * point_value
            
            # Calculate buy stop and sell stop prices
            buy_stop_price = current_price + price_adjustment
            sell_stop_price = current_price - price_adjustment
            
            # Set stop loss and take profit levels
            sl_points = self.sl_points
            tp_points = self.tp_points
            
            # Calculate SL and TP prices for buy stop
            buy_sl_price = buy_stop_price - (sl_points * point_value)
            buy_tp_price = buy_stop_price + (tp_points * point_value)
            
            # Calculate SL and TP prices for sell stop
            sell_sl_price = sell_stop_price + (sl_points * point_value)
            sell_tp_price = sell_stop_price - (tp_points * point_value)
            
            # Create news event ID
            news_id = f"{news_item['timestamp']}-{news_item['event']}"
            
            print(f"Placing news pending orders for {self.symbol}:")
            print(f"Current price: {current_price}")
            print(f"Buy Stop @ {buy_stop_price}, SL @ {buy_sl_price}, TP @ {buy_tp_price}")
            print(f"Sell Stop @ {sell_stop_price}, SL @ {sell_sl_price}, TP @ {sell_tp_price}")
            
            # Place Buy Stop order
            buy_request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": mt5.ORDER_TYPE_BUY_STOP,
                "price": buy_stop_price,
                "sl": buy_sl_price,
                "tp": buy_tp_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"NEWS_{news_id}_BUY" if not self.comment_off else "",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            # Place Sell Stop order
            sell_request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": self.symbol,
                "volume": self.lot_size,
                "type": mt5.ORDER_TYPE_SELL_STOP,
                "price": sell_stop_price,
                "sl": sell_sl_price,
                "tp": sell_tp_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"NEWS_{news_id}_SELL" if not self.comment_off else "",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            # Send the orders
            buy_result = mt5.order_send(buy_request)
            sell_result = mt5.order_send(sell_request)
            
            # Store the pending orders for tracking
            if buy_result.retcode == mt5.TRADE_RETCODE_DONE and sell_result.retcode == mt5.TRADE_RETCODE_DONE:
                self.news_orders[news_id] = {
                    'buy_ticket': buy_result.order,
                    'sell_ticket': sell_result.order,
                    'timestamp': news_item['timestamp'],
                    'event': news_item['event'],
                    'currency': news_item['currency']
                }
                print(f"✅ Successfully placed news pending orders for {news_item['event']}")
                return True
            else:
                print(f"❌ Failed to place news pending orders:")
                if buy_result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Buy Stop order failed: {buy_result.retcode}, {buy_result.comment}")
                if sell_result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Sell Stop order failed: {sell_result.retcode}, {sell_result.comment}")
                return False
                
        except Exception as e:
            print(f"Error placing news pending orders: {e}")
            traceback.print_exc()
            return False

    def run(self, initialize_mt5=True):
        """Run the trading bot"""
        try:
            # Initialize MT5 if requested
            if initialize_mt5:
                if not self.initialize_mt5():
                    print(f"Failed to initialize MT5 for {self.symbol}")
                    return False
                    
            print(f"Starting trading bot for {self.symbol}...")
            
            # Start the trading loop
            self.trading_loop()
            
            return True
        except Exception as e:
            print(f"Error running trading bot: {e}")
            traceback.print_exc()
            return False

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
    
    # Base settings to be applied to all symbols
    base_settings = {
        'timeframe': timeframe,
        'lot_size': float(data.get('lot_size', 0.01)),
        'sl_points': float(data.get('sl_points', 100)),
        'tp_points': float(data.get('tp_points', 100)),
        'first_tp_points': float(data.get('first_tp_points', 20)),
        'second_tp_points': float(data.get('second_tp_points', 50)),
        'positions_per_setup': int(data.get('positions_per_setup', 3)),
        'magic_number': int(data.get('magic_number', 234000)),
        'trade_direction': data.get('trade_direction', 'BOTH'),
        'login': login,
        'password': data.get('password', ''),
        'server': data.get('server', ''),
        'enable_progressive': data.get('enable_progressive', True),
        'positive_sl_points': float(data.get('positive_sl_points', 20)),
        'breakeven_trigger_points': float(data.get('breakeven_trigger_points', 20)),
        'enable_drawdown_layering': data.get('enable_drawdown_layering', False),
        'drawdown_layer_threshold': float(data.get('drawdown_layer_threshold', 20)),
        'positions_per_layer': int(data.get('positions_per_layer', 3)),
        'minimum_profit_per_position': float(data.get('minimum_profit_per_position', 20)),
        'max_layers': int(data.get('max_layers', 5)),
        'enable_trailing_sl': data.get('enable_trailing_sl', False),
        'trailing_breakeven_points': float(data.get('trailing_breakeven_points', 30)),
        'trailing_positive_sl_points': float(data.get('trailing_positive_sl_points', 30)),
        'trailing_positive_trigger_points': float(data.get('trailing_positive_trigger_points', 60)),
        'trailing_tp_points': float(data.get('trailing_tp_points', 90)),
        'trailing_sl_points': float(data.get('trailing_sl_points', 30)),
        'dynamic_checkpoints': int(data.get('dynamic_checkpoints', 5)),
        'reentry_count': int(data.get('reentry_count', 5)),
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
                    status["active_layers"] = 0
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
    """Start a new MT5 trading instance"""
    data = request.json
    instance_id = data.get('instance_id')
    
    # In a real application, you would create and start the MT5 instance here
    # For this demo, we'll just return success
    
    mt5_instances[instance_id] = data
    
    return jsonify({
        'status': 'success',
        'message': f'MT5 Instance {instance_id} started successfully'
    })

@app.route('/stop_instance', methods=['POST'])
def stop_instance():
    """Stop an MT5 trading instance"""
    data = request.json
    instance_id = data.get('instance_id')
    
    # In a real application, you would stop the MT5 instance here
    # For this demo, we'll just remove it from our dictionary
    
    if instance_id in mt5_instances:
        del mt5_instances[instance_id]
        return jsonify({
            'success': True,
            'message': f'MT5 Instance {instance_id} stopped successfully'
        })
    else:
        return jsonify({
            'success': False,
            'message': f'MT5 Instance {instance_id} not found'
        })

@app.route('/get_high_impact_news', methods=['GET'])
def get_high_impact_news():
    """Get high impact news events for the provided currency or all currencies"""
    currency = request.args.get('currency', None)
    try:
        # Get all high impact news events
        news_events = news_handler.get_high_impact_news_events(currency)
        
        # Format the news events for display
        formatted_events = []
        for event in news_events:
            formatted_events.append({
                'symbol': event['symbol'],
                'title': event['title'],
                'date': event['date'].strftime('%Y-%m-%d %H:%M:%S'),
                'impact': event['impact'],
                'forecast': event['forecast'],
                'previous': event['previous']
            })
        
        return jsonify({'status': 'success', 'data': formatted_events})
    except Exception as e:
        app.logger.error(f"Error fetching news events: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Error fetching news events: {str(e)}"}), 500

@app.route('/get_news_calendar', methods=['GET'])
def get_news_calendar():
    """Get the economic calendar for the week"""
    try:
        # Get calendar for the week
        calendar = news_handler.get_economic_calendar()
        
        # Format for display
        formatted_calendar = []
        for event in calendar:
            formatted_calendar.append({
                'symbol': event['symbol'],
                'title': event['title'],
                'date': event['date'].strftime('%Y-%m-%d %H:%M:%S'),
                'impact': event['impact'],
                'forecast': event['forecast'],
                'previous': event['previous']
            })
        
        return jsonify({'status': 'success', 'data': formatted_calendar})
    except Exception as e:
        app.logger.error(f"Error fetching economic calendar: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Error fetching economic calendar: {str(e)}"}), 500

@app.route('/update_news_data', methods=['POST'])
def update_news_data():
    """Force update of news data"""
    try:
        news_handler.force_refresh()
        return jsonify({'status': 'success', 'message': 'News data refreshed'})
    except Exception as e:
        app.logger.error(f"Error refreshing news data: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Error refreshing news data: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True) 