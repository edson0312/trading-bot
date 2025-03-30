import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
import pytz
from typing import Tuple, List, Dict, Optional
import config
from strategies.ace_strategy import check_entry_conditions, get_stop_loss, get_take_profit
import traceback

# Import configuration
from config import (
    SYMBOL, TIMEFRAME, LOT_SIZE, LOOKBACK,
    TP_PIPS, SL_PIPS, FIRST_TP_PIPS, SECOND_TP_PIPS,
    POSITIONS_PER_SETUP, ACTIVE_STRATEGY, MAGIC_NUMBER,
    ACE_SETTINGS, ENABLE_DRAWDOWN_LAYERING, MAX_LAYERS,
    DRAWDOWN_LAYER_THRESHOLD, POSITIONS_PER_LAYER, MINIMUM_PROFIT_PER_POSITION
)

# Initialize MT5 connection
def initialize_mt5():
    """Initialize MT5 connection"""
    if not mt5.initialize():
        print("MT5 initialization failed")
        # Print additional details about the error
        error_code = mt5.last_error()
        if error_code:
            print(f"MT5 Error: {error_code}")
            
        print("Checking if MT5 is installed and running...")
        try:
            # Check if terminal.exe or terminal64.exe is running
            import psutil
            mt5_running = False
            for proc in psutil.process_iter(['name']):
                if 'terminal' in proc.info['name'].lower() and ('64' in proc.info['name'] or '32' in proc.info['name']):
                    mt5_running = True
                    print(f"MT5 process found: {proc.info['name']}")
                    break
            
            if not mt5_running:
                print("MT5 is not running. Please start MetaTrader 5 manually.")
                print("Make sure you're logged in to your trading account.")
            else:
                print("MT5 is running but initialization failed. Check if you're logged in to your account.")
                
        except Exception as e:
            print(f"Error checking MT5 process: {e}")
            
        return False
    
    print(f"MT5 version: {mt5.version()}")
    
    # Check if connected to account
    account_info = mt5.account_info()
    if account_info:
        print(f"Connected to account: {account_info.login} on server {account_info.server}")
        print(f"Balance: {account_info.balance}, Equity: {account_info.equity}")
        
        # Check if symbol exists
        symbol_info = mt5.symbol_info(SYMBOL)
        if not symbol_info:
            print(f"Symbol {SYMBOL} not found! Check if it's available in your MT5 terminal.")
            return False
            
        return True
    else:
        print("Not connected to any trading account. Please log in to MT5 manually.")
        return False

# Convert pips to price points based on symbol
def pips_to_price(symbol, pips):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Failed to get symbol info for {symbol}")
        return None
    
    # For 5-digit brokers, 1 pip = 0.0001 for most pairs
    digits = symbol_info.digits
    
    # For XXXJPY pairs usually 1 pip = 0.01
    if digits == 3:
        point_value = 0.01
    else:
        point_value = 0.0001 if digits == 5 else 0.001
    
    return pips * point_value

# Get recent price data
def get_price_data(symbol, timeframe, lookback):
    timezone = pytz.timezone("UTC")
    time_now = datetime.now(timezone)
    
    # Get specified number of bars + extra for calculation
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, lookback + 10)
    if bars is None or len(bars) == 0:
        print(f"Failed to get price data for {symbol}")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# Open a trade
def open_trade(symbol, trade_type, lot, sl, tp, comment=""):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": trade_type,
        "price": mt5.symbol_info_tick(symbol).ask if trade_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Error opening trade: {result.retcode}")
        print(f"Comment: {result.comment}")
        return None
    
    print(f"Trade opened: Type={'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'}, Lot={lot}, Ticket={result.order}")
    return result.order

def modify_position(ticket: int, sl: float = None, tp: float = None) -> bool:
    """Modify position's SL and/or TP"""
    position = mt5.positions_get(ticket=ticket)
    if not position:
        print(f"Position {ticket} not found")
        return False
    
    position = position[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": ticket,
        "sl": sl if sl is not None else position.sl,
        "tp": tp if tp is not None else position.tp,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to modify position {ticket}: {result.comment}")
        return False
    
    print(f"Modified position {ticket}: SL={sl}, TP={tp}")
    return True

# Check and manage existing positions
def manage_positions(symbol):
    """Manage open positions according to the trade progression rules"""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return
    
    # Group positions by setup ID
    position_groups = {}
    for pos in positions:
        setup_id = pos.comment.split('_')[0] if pos.comment else 'unknown'
        if setup_id not in position_groups:
            position_groups[setup_id] = []
        position_groups[setup_id].append(pos)
    
    pip_value = pips_to_price(symbol, 1)
    
    # Process each setup's positions
    for setup_id, setup_positions in position_groups.items():
        if len(setup_positions) != 3:
            continue  # Skip if not exactly 3 positions
        
        # Sort positions by their order (using comment suffix)
        setup_positions.sort(key=lambda p: int(p.comment.split('_')[1]) if p.comment else 0)
        
        # Calculate profits in pips for each position
        for pos in setup_positions:
            price_diff = pos.price_current - pos.price_open
            if pos.type == 1:  # Sell position
                price_diff = -price_diff
            profit_pips = price_diff / pip_value
            
            # Position index (1-based)
            pos_index = int(pos.comment.split('_')[1])
            
            # First position management (20 pips TP)
            if pos_index == 1 and profit_pips >= FIRST_TP_PIPS:
                # Close first position
                if close_position(pos.ticket):
                    print(f"Closed first position of setup {setup_id} at {FIRST_TP_PIPS} pips profit")
                    # Move others to breakeven
                    for other_pos in setup_positions[1:]:
                        modify_position(other_pos.ticket, sl=other_pos.price_open)
            
            # Second position management (50 pips TP)
            elif pos_index == 2 and profit_pips >= SECOND_TP_PIPS:
                # Close second position
                if close_position(pos.ticket):
                    print(f"Closed second position of setup {setup_id} at {SECOND_TP_PIPS} pips profit")
                    # Move third position SL to +20 pips
                    third_pos = setup_positions[2]
                    new_sl = third_pos.price_open + (20 * pip_value if third_pos.type == 0 else -20 * pip_value)
                    modify_position(third_pos.ticket, sl=new_sl)

# Close a position
def close_position(ticket):
    position = mt5.positions_get(ticket=ticket)
    if position:
        position = position[0]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": mt5.symbol_info_tick(position.symbol).bid if position.type == 0 else mt5.symbol_info_tick(position.symbol).ask,
            "deviation": 10,
            "magic": MAGIC_NUMBER,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Error closing position {ticket}: {result.retcode}")
            print(f"Comment: {result.comment}")
            return False
        
        print(f"Position {ticket} closed successfully")
        return True
    
    print(f"Position {ticket} not found")
    return False

# Check if we already have a trade setup in progress
def check_existing_setup(symbol):
    positions = mt5.positions_get(symbol=symbol)
    
    if positions is None or len(positions) == 0:
        return False, ""
    
    try:
        positions_df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
        
        if positions_df.empty:
            return False, ""
            
        for comment in positions_df['comment'].unique():
            if comment and isinstance(comment, str) and comment.startswith("ACE_"):
                parts = comment.split('_')
                if len(parts) > 1:
                    return True, parts[1]
        
        return False, ""
    except Exception as e:
        print(f"Error checking existing setup: {e}")
        return False, ""

def execute_trade_setup(symbol: str, trade_type: str, setup_id: int) -> List[int]:
    """Execute a complete trade setup with 3 positions"""
    positions = []
    
    # Get current price
    price = mt5.symbol_info_tick(symbol).ask if trade_type == "BUY" else mt5.symbol_info_tick(symbol).bid
    
    # Get price data for calculating SL/TP
    df = get_price_data(symbol, TIMEFRAME, LOOKBACK)
    if df is None:
        return []
    
    # Calculate SL and TP based on ACE strategy
    is_long = trade_type == "BUY"
    sl = get_stop_loss(df, is_long)
    tp = get_take_profit(df, is_long)
    
    # Open 3 positions
    for i in range(1, 4):
        ticket = open_trade(
            symbol=symbol,
            trade_type=mt5.ORDER_TYPE_BUY if trade_type == "BUY" else mt5.ORDER_TYPE_SELL,
            lot=LOT_SIZE,
            sl=sl,
            tp=tp,
            comment=f"ACE_{setup_id}_{i}"
        )
        
        if ticket:
            positions.append(ticket)
        else:
            # Close any opened positions if we can't open all 3
            for pos_ticket in positions:
                close_position(pos_ticket)
            return []
    
    return positions

# Main trading logic
def run_trading_bot():
    """Main trading bot function"""
    if not initialize_mt5():
        print("Failed to initialize MT5. Exiting.")
        return
    
    print("Trading bot started")
    
    try:
        while True:
            try:
                # Manage existing positions
                manage_positions(SYMBOL)
                
                # Get latest price data
                df = get_price_data(SYMBOL, TIMEFRAME, LOOKBACK)
                if df is None:
                    print("Failed to get price data. Retrying...")
                    time.sleep(60)
                    continue
                
                # Check entry conditions using ACE strategy
                long_condition, short_condition = check_entry_conditions(df, ACE_SETTINGS)
                
                # Execute new trade setup if conditions are met
                if long_condition or short_condition:
                    setup_id = int(time.time())
                    trade_type = "BUY" if long_condition else "SELL"
                    
                    print(f"New trade setup: {trade_type}")
                    positions = execute_trade_setup(SYMBOL, trade_type, setup_id)
                    
                    if positions:
                        print(f"Successfully opened trade setup {setup_id} with {len(positions)} positions")
                    else:
                        print(f"Failed to open complete trade setup {setup_id}")
                
                # Sleep before next check
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                print(f"Error in main trading loop: {e}")
                time.sleep(60)  # Wait before retrying
                
    except KeyboardInterrupt:
        print("Bot stopped by user")
    finally:
        mt5.shutdown()
        print("MT5 connection closed")

class DrawdownLayerManager:
    """
    Manages drawdown layering strategy:
    1. Adds 3 positions when trade reaches 20 pips drawdown
    2. Adds more layers at 40, 60, 80 pips drawdown, etc.
    3. Averages TP across all positions to ensure minimum 20 pips profit
    """
    def __init__(self, symbol, lot_size=0.01):
        self.symbol = symbol
        self.lot_size = lot_size
        self.layers = {}  # Dictionary to track layers by their setup ID
        self.pip_value = self.get_pip_value()
        # Import configuration settings
        self.threshold = config.DRAWDOWN_LAYER_THRESHOLD
        self.positions_per_layer = config.POSITIONS_PER_LAYER
        self.min_profit_pips = config.MINIMUM_PROFIT_PER_POSITION
        self.max_layers = config.MAX_LAYERS
        
    def get_pip_value(self):
        """Get pip value for the symbol"""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            return 0.0001  # Default for forex
        return 10 ** -symbol_info.digits
        
    def get_current_drawdown(self, positions):
        """Calculate current drawdown in pips for a set of positions"""
        if not positions:
            return 0
            
        # Calculate weighted average entry price
        total_volume = sum(pos.volume for pos in positions)
        avg_entry_price = sum(pos.price_open * pos.volume for pos in positions) / total_volume
        
        # Get current price
        current_price = mt5.symbol_info_tick(self.symbol).bid if positions[0].type == 0 else mt5.symbol_info_tick(self.symbol).ask
        
        # Calculate drawdown
        if positions[0].type == 0:  # Buy positions
            drawdown_points = avg_entry_price - current_price
        else:  # Sell positions
            drawdown_points = current_price - avg_entry_price
            
        # Convert to pips
        drawdown_pips = drawdown_points / self.pip_value
        
        return drawdown_pips if drawdown_pips > 0 else 0
        
    def check_and_add_layers(self):
        """Check for drawdown and add layers if needed"""
        # Get all position groups by setup ID
        position_groups = self.group_positions_by_setup()
        
        for setup_id, positions in position_groups.items():
            # Skip if this is not a valid set of positions
            if not positions:
                continue
                
            # Calculate current drawdown
            current_drawdown = self.get_current_drawdown(positions)
            print(f"Setup {setup_id} current drawdown: {current_drawdown:.2f} pips")
            
            # Get the current number of layers for this setup
            current_layers = len(positions) // self.positions_per_layer
            
            # Check if we've reached max layers
            if current_layers >= self.max_layers:
                print(f"Maximum number of layers ({self.max_layers}) reached for setup {setup_id}")
                continue
                
            # Calculate required layers based on drawdown
            required_layers = 1 + int(current_drawdown / self.threshold)
            
            # Cap at max layers
            required_layers = min(required_layers, self.max_layers)
            
            # Calculate how many new layers to add
            layers_to_add = max(0, required_layers - current_layers)
            
            if layers_to_add > 0:
                print(f"Adding {layers_to_add} new layer(s) for setup {setup_id}. Drawdown: {current_drawdown:.2f} pips")
                
                # Add each layer
                for i in range(layers_to_add):
                    layer_number = current_layers + i + 1
                    self.add_layer(setup_id, layer_number, positions[0].type == 0)
                    
                # Adjust take profit on all positions of this setup
                self.adjust_take_profit(setup_id)
        
    def add_layer(self, setup_id, layer_number, is_buy):
        """Add a new layer of positions"""
        positions = []
        
        # Get current price
        current_price = mt5.symbol_info_tick(self.symbol).ask if is_buy else mt5.symbol_info_tick(self.symbol).bid
        
        # Calculate SL and TP
        # For layering strategy, we'll calculate these dynamically
        timeframe = TIMEFRAME
        lookback = LOOKBACK
        df = self.get_price_data(self.symbol, timeframe, lookback)
        if df is None:
            print("Failed to get price data for layering")
            return []
            
        sl_price = get_stop_loss(df, is_buy)
        tp_price = self.calculate_tp_for_layer(setup_id, is_buy, current_price)
        
        # Open positions for this layer
        for i in range(self.positions_per_layer):
            position_id = i + 1 + ((layer_number - 1) * self.positions_per_layer)
            
            # Open position
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            comment = f"ACE_{setup_id}_{position_id}_L{layer_number}"
            
            ticket = self.open_position(order_type, sl_price, tp_price, comment)
            if ticket:
                positions.append(ticket)
            else:
                # If we can't open all positions in this layer, close the ones we opened
                for pos_ticket in positions:
                    self.close_position(pos_ticket)
                return []
                
        print(f"Added layer {layer_number} for setup {setup_id} with {len(positions)} positions")
        return positions
        
    def calculate_tp_for_layer(self, setup_id, is_buy, current_price):
        """Calculate take profit price that ensures minimum profit across all positions"""
        # Get all existing positions for this setup
        positions = []
        all_positions = mt5.positions_get(symbol=self.symbol)
        
        if all_positions:
            for pos in all_positions:
                # Parse setup ID from comment
                if not pos.comment or len(pos.comment.split('_')) < 2:
                    continue
                if pos.comment.split('_')[1] == str(setup_id):
                    positions.append(pos)
        
        # If no existing positions, use standard TP calculation
        if not positions:
            # Get price data for TP calculation
            df = self.get_price_data(self.symbol, TIMEFRAME, LOOKBACK)
            if df is None:
                # Fallback to fixed TP
                return current_price + (self.min_profit_pips * self.pip_value * (1 if is_buy else -1))
            return get_take_profit(df, is_buy)
            
        # Calculate weighted average entry price
        total_volume = sum(pos.volume for pos in positions) + (self.positions_per_layer * self.lot_size)
        total_position_value = sum(pos.price_open * pos.volume for pos in positions)
        total_position_value += current_price * (self.positions_per_layer * self.lot_size)
        
        avg_entry_price = total_position_value / total_volume
        
        # Calculate TP that ensures minimum profit
        tp_price = avg_entry_price + (self.min_profit_pips * self.pip_value * (1 if is_buy else -1))
        
        return tp_price
        
    def adjust_take_profit(self, setup_id):
        """Adjust take profit on all positions of a setup after adding new layers"""
        # Get all positions for this setup
        positions = []
        all_positions = mt5.positions_get(symbol=self.symbol)
        
        if all_positions:
            for pos in all_positions:
                # Parse setup ID from comment
                if not pos.comment or len(pos.comment.split('_')) < 2:
                    continue
                if pos.comment.split('_')[1] == str(setup_id):
                    positions.append(pos)
        
        if not positions:
            return
            
        # Determine if these are buy or sell positions
        is_buy = positions[0].type == 0
        
        # Calculate weighted average entry price
        total_volume = sum(pos.volume for pos in positions)
        avg_entry_price = sum(pos.price_open * pos.volume for pos in positions) / total_volume
        
        # Calculate new TP price
        new_tp = avg_entry_price + (self.min_profit_pips * self.pip_value * (1 if is_buy else -1))
        
        # Update TP on all positions
        for pos in positions:
            self.modify_position_tp(pos.ticket, new_tp)
            
        print(f"Adjusted TP for all {len(positions)} positions in setup {setup_id} to ensure {self.min_profit_pips} pips profit")
    
    def group_positions_by_setup(self):
        """Group positions by their setup ID"""
        position_groups = {}
        positions = mt5.positions_get(symbol=self.symbol)
        
        if not positions:
            return position_groups
            
        # Group positions by setup ID
        for pos in positions:
            if not pos.comment or len(pos.comment.split('_')) < 2:
                continue
                
            setup_id = pos.comment.split('_')[1]
            if setup_id not in position_groups:
                position_groups[setup_id] = []
            position_groups[setup_id].append(pos)
            
        return position_groups
    
    def get_price_data(self, symbol, timeframe, lookback):
        """Get historical price data"""
        bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, lookback + 10)
        if bars is None or len(bars) == 0:
            return None
        
        df = pd.DataFrame(bars)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    def open_position(self, order_type, sl_price, tp_price, comment="HWR Strategy"):
        """Open a single position"""
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self.lot_size,
            "type": order_type,
            "price": mt5.symbol_info_tick(self.symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).bid,
            "sl": sl_price,
            "tp": tp_price,
            "magic": MAGIC_NUMBER,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Order failed: {result.comment}")
            return None
        
        print(f"Position opened: {self.symbol}, Type={'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}, Ticket={result.order}, Comment={comment}")
        return result.order
    
    def close_position(self, ticket):
        """Close a position"""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            print(f"Position {ticket} not found")
            return False
            
        position = positions[0]
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": mt5.symbol_info_tick(self.symbol).bid if position.type == 0 else mt5.symbol_info_tick(self.symbol).ask,
            "magic": MAGIC_NUMBER,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to close position {ticket}: {result.comment}")
            return False
            
        print(f"Position {ticket} closed successfully")
        return True
    
    def modify_position_tp(self, ticket, new_tp):
        """Modify take profit of a position"""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            print(f"Position {ticket} not found")
            return False
            
        position = positions[0]
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "position": ticket,
            "sl": position.sl,  # Keep the same SL
            "tp": new_tp
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to modify TP for position {ticket}: {result.comment}")
            return False
            
        print(f"Modified TP for position {ticket} to {new_tp}")
        return True

class TradingBot:
    def __init__(self):
        self.symbol = config.SYMBOL
        self.timeframe = config.TIMEFRAME
        self.positions_per_setup = config.POSITIONS_PER_SETUP
        self.active_positions = []
        self.ace_settings = config.ACE_SETTINGS
        self.initialize_mt5()
        # Initialize the drawdown layer manager
        self.drawdown_manager = DrawdownLayerManager(self.symbol, config.LOT_SIZE)
        # Import drawdown layering configuration
        self.enable_drawdown_layering = config.ENABLE_DRAWDOWN_LAYERING
        self.max_layers = config.MAX_LAYERS

    def initialize_mt5(self):
        if not mt5.initialize():
            print("MT5 initialization failed")
            # Print additional details about the error
            error_code = mt5.last_error()
            if error_code:
                print(f"MT5 Error: {error_code}")
            
            print("Checking if MT5 is installed and running...")
            try:
                # Check if terminal.exe or terminal64.exe is running
                import psutil
                mt5_running = False
                for proc in psutil.process_iter(['name']):
                    if 'terminal' in proc.info['name'].lower() and ('64' in proc.info['name'] or '32' in proc.info['name']):
                        mt5_running = True
                        print(f"MT5 process found: {proc.info['name']}")
                        break
            
                if not mt5_running:
                    print("MT5 is not running. Please start MetaTrader 5 manually.")
                    print("Make sure you're logged in to your trading account.")
                else:
                    print("MT5 is running but initialization failed. Check if you're logged in to your account.")
                
            except Exception as e:
                print(f"Error checking MT5 process: {e}")
            
            return False
        
        print(f"MT5 version: {mt5.version()}")
        
        # Check if connected to account
        account_info = mt5.account_info()
        if account_info:
            print(f"Connected to account: {account_info.login} on server {account_info.server}")
            print(f"Balance: {account_info.balance}, Equity: {account_info.equity}")
            
            # Check if symbol exists
            symbol_info = mt5.symbol_info(self.symbol)
            if not symbol_info:
                print(f"Symbol {self.symbol} not found! Check if it's available in your MT5 terminal.")
                return False
            
            return True
        else:
            print("Not connected to any trading account. Please log in to MT5 manually.")
            return False

    def get_historical_data(self, timeframe=None, num_bars=100):
        if timeframe is None:
            timeframe = self.timeframe
        
        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, num_bars)
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def execute_trade_setup(self, is_buy):
        """Execute a complete trade setup with 3 positions"""
        positions = []
        current_price = mt5.symbol_info_tick(self.symbol).ask if is_buy else mt5.symbol_info_tick(self.symbol).bid
        
        # Calculate initial SL and TP levels
        df = self.get_historical_data()
        sl_price = get_stop_loss(df, is_buy)
        tp_price = get_take_profit(df, is_buy)
        
        setup_id = int(time.time())
        
        # Open positions
        for i in range(self.positions_per_setup):
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            position = self.open_position(order_type, sl_price, tp_price, f"ACE_{setup_id}_{i+1}")
            
            if position is None:
                # If position opening fails, close any opened positions
                for pos in positions:
                    self.close_position(pos)
                return None
            
            positions.append(position)
        
        return positions

    def open_position(self, order_type, sl_price, tp_price, comment="HWR Strategy"):
        """Open a single position"""
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": config.LOT_SIZE,
            "type": order_type,
            "price": mt5.symbol_info_tick(self.symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).bid,
            "sl": sl_price,
            "tp": tp_price,
            "magic": config.MAGIC_NUMBER,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Order failed: {result.comment}")
            return None
        
        print(f"Position opened: {self.symbol}, Type={'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}, Ticket={result.order}")
        return result.order

    def manage_positions(self):
        """Manage open positions according to the strategy rules"""
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return
        
        # First, check if we need to add layers due to drawdown
        if self.enable_drawdown_layering:
            self.drawdown_manager.check_and_add_layers()
        
        pip_value = self.get_pip_value()
        
        # Group positions by setup ID
        position_groups = {}
        for pos in positions:
            if not pos.comment or len(pos.comment.split('_')) < 2:
                continue
                
            setup_id = pos.comment.split('_')[1]
            if setup_id not in position_groups:
                position_groups[setup_id] = []
            position_groups[setup_id].append(pos)
        
        # Process each setup
        for setup_id, setup_positions in position_groups.items():
            # Get all layers in this setup
            layer_info = {}
            for pos in setup_positions:
                # Parse position info from comment
                comment_parts = pos.comment.split('_')
                if len(comment_parts) < 3:
                    continue
                
                # Extract layer number if available
                layer_num = 1  # Default to layer 1
                if len(comment_parts) > 3 and comment_parts[3].startswith('L'):
                    try:
                        layer_num = int(comment_parts[3][1:])
                    except:
                        pass
                
                # Add to layer info
                if layer_num not in layer_info:
                    layer_info[layer_num] = []
                layer_info[layer_num].append(pos)
            
            # Manage positions in the first layer (original positions)
            if 1 in layer_info and len(layer_info[1]) >= 3:
                first_layer = sorted(layer_info[1], key=lambda p: int(p.comment.split('_')[2]))
                
                # Calculate profit in pips for positions in first layer
                for pos in first_layer:
                    price_diff = pos.price_current - pos.price_open
                    if pos.type == 1:  # Sell position
                        price_diff = -price_diff
                    profit_pips = price_diff / pip_value
                    
                    # Get position index (1-based)
                    pos_index = int(pos.comment.split('_')[2]) 
                    
                    # First position management
                    if pos_index == 1 and profit_pips >= config.FIRST_TP_PIPS:
                        self.close_position(pos.ticket)
                        print(f"Closed first position at {config.FIRST_TP_PIPS} pips profit")
                        # Move others to breakeven
                        for other_pos in [p for p in first_layer if p.ticket != pos.ticket]:
                            self.modify_position_sl(other_pos.ticket, other_pos.price_open)
                    
                    # Second position management
                    elif pos_index == 2 and profit_pips >= config.SECOND_TP_PIPS:
                        self.close_position(pos.ticket)
                        print(f"Closed second position at {config.SECOND_TP_PIPS} pips profit")
                        # Move third position SL to +20 pips
                        for other_pos in [p for p in first_layer if p.ticket != pos.ticket and int(p.comment.split('_')[2]) == 3]:
                            new_sl = other_pos.price_open + (20 * pip_value if other_pos.type == 0 else -20 * pip_value)
                            self.modify_position_sl(other_pos.ticket, new_sl)

    def close_position(self, ticket):
        """Close a specific position"""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            print(f"Position {ticket} not found")
            return False
            
        position = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": mt5.symbol_info_tick(self.symbol).bid if position.type == 0 else mt5.symbol_info_tick(self.symbol).ask,
            "magic": config.MAGIC_NUMBER,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to close position {ticket}: {result.comment}")
            return False
            
        print(f"Position {ticket} closed successfully")
        return True

    def modify_position_sl(self, ticket, new_sl):
        """Modify stop loss of a position"""
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "sl": new_sl,
            "position": ticket,
            "magic": config.MAGIC_NUMBER
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE

    def get_pip_value(self):
        """Get pip value for the symbol"""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            return 0.0001  # Default for forex
        return 10 ** -symbol_info.digits

    def run_trading_bot(self):
        """Main bot loop"""
        print(f"Starting trading bot for {self.symbol}")
        print(f"Using ACE settings: {self.ace_settings}")
        print(f"Timeframe: {self.timeframe}")
        if self.enable_drawdown_layering:
            print(f"Drawdown Layering enabled: Adding {config.POSITIONS_PER_LAYER} positions every {config.DRAWDOWN_LAYER_THRESHOLD} pips of drawdown")
            print(f"Maximum layers: {self.max_layers}, Minimum profit per position: {config.MINIMUM_PROFIT_PER_POSITION} pips")
        else:
            print("Drawdown Layering disabled")
        
        while True:
            try:
                # Get current market data
                df = self.get_historical_data()
                
                # Print current market data summary for debugging
                print(f"\n--- Market Data at {datetime.now()} ---")
                print(f"Last price: {df['close'].iloc[-1]}")
                
                # Check for entry conditions using ACE strategy
                long_condition, short_condition = check_entry_conditions(df, self.ace_settings)
                
                # Print entry condition results
                print(f"Entry conditions - Long: {long_condition}, Short: {short_condition}")
                
                # Manage existing positions
                self.manage_positions()
                
                # Check for new trade setups
                positions = mt5.positions_get(symbol=self.symbol)
                positions_count = len(positions) if positions else 0
                print(f"Current open positions: {positions_count}")
                
                if not positions:  # Only enter new trades if no positions are open
                    if long_condition:
                        print("Opening LONG positions...")
                        new_positions = self.execute_trade_setup(True)
                        if new_positions:
                            print(f"Successfully opened {len(new_positions)} LONG positions")
                        else:
                            print("Failed to open LONG positions")
                    elif short_condition:
                        print("Opening SHORT positions...")
                        new_positions = self.execute_trade_setup(False)
                        if new_positions:
                            print(f"Successfully opened {len(new_positions)} SHORT positions")
                        else:
                            print("Failed to open SHORT positions")
                else:
                    print(f"Already have {positions_count} open positions, not entering new trades")
                
                time.sleep(1)  # Avoid excessive CPU usage
                
            except Exception as e:
                print(f"Error in main loop: {e}")
                traceback.print_exc()  # Add detailed traceback
                time.sleep(5)

if __name__ == "__main__":
    bot = TradingBot()
    bot.run_trading_bot()
