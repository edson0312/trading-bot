import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import traceback
import sys

# Import strategy functions from the updated ACE strategy
from strategies.ace_strategy import check_entry_conditions, get_stop_loss, get_take_profit
from config import SYMBOL, TIMEFRAME, TP_PIPS, SL_PIPS, FIRST_TP_PIPS, SECOND_TP_PIPS, POSITIONS_PER_SETUP, LOT_SIZE, INITIAL_BALANCE, ACE_SETTINGS

# Constants for backtesting
START_DATE = datetime(2023, 11, 1, tzinfo=pytz.UTC)  # Start date for backtesting
END_DATE = datetime(2023, 12, 31, tzinfo=pytz.UTC)  # End date for backtesting

def get_pip_value(symbol: str) -> float:
    """Get pip value for a symbol in backtesting"""
    # For most forex pairs, 1 pip = 0.0001
    # For JPY pairs, 1 pip = 0.01
    if symbol.endswith('JPY'):
        return 0.01
    return 0.0001

def pips_to_price_backtest(symbol: str, pips: float) -> float:
    """Convert pips to price points for backtesting"""
    pip_value = get_pip_value(symbol)
    return pips * pip_value

def simulate_trade_management(df: pd.DataFrame, start_idx: int, is_long: bool, entry_price: float, setup_id: int) -> tuple:
    """Simulate trade management for a setup"""
    positions = []
    total_profit = 0
    
    # Calculate TP/SL levels
    pip_value = get_pip_value(SYMBOL)
    
    for i in range(1, POSITIONS_PER_SETUP + 1):
        position = {
            'entry_price': entry_price,
            'entry_time': df.iloc[start_idx]['time'],
            'type': 'long' if is_long else 'short',
            'lot_size': LOT_SIZE,
            'status': 'open',
            'exit_price': None,
            'exit_time': None,
            'profit': 0,
            'sl': entry_price + (-pip_value * SL_PIPS if is_long else pip_value * SL_PIPS),
            'tp': entry_price + (pip_value * TP_PIPS if is_long else -pip_value * TP_PIPS)
        }
        
        positions.append(position)
    
    # Simulate forward
    for i in range(start_idx + 1, len(df)):
        current_bar = df.iloc[i]
        high, low = current_bar['high'], current_bar['low']
        
        # Check each open position
        for pos in positions:
            if pos['status'] != 'open':
                continue
            
            # Calculate current profit in pips
            price_diff = (current_bar['close'] - pos['entry_price']) * (1 if pos['type'] == 'long' else -1)
            profit_pips = price_diff / pip_value
            
            # Check stop loss
            if (pos['type'] == 'long' and low <= pos['sl']) or \
               (pos['type'] == 'short' and high >= pos['sl']):
                pos['status'] = 'closed'
                pos['exit_price'] = pos['sl']
                pos['exit_time'] = current_bar['time']
                pos['profit'] = (pos['exit_price'] - pos['entry_price']) * (1 if pos['type'] == 'long' else -1) * (pos['lot_size'] * 100000)
                total_profit += pos['profit']
                continue
            
            # Check take profit
            if (pos['type'] == 'long' and high >= pos['tp']) or \
               (pos['type'] == 'short' and low <= pos['tp']):
                pos['status'] = 'closed'
                pos['exit_price'] = pos['tp']
                pos['exit_time'] = current_bar['time']
                pos['profit'] = (pos['exit_price'] - pos['entry_price']) * (1 if pos['type'] == 'long' else -1) * (pos['lot_size'] * 100000)
                total_profit += pos['profit']
                continue
            
            # Position-specific management
            position_index = positions.index(pos) + 1
            
            # First position: Close at FIRST_TP_PIPS and move others to breakeven
            if position_index == 1 and profit_pips >= FIRST_TP_PIPS:
                pos['status'] = 'closed'
                pos['exit_price'] = current_bar['close']
                pos['exit_time'] = current_bar['time']
                pos['profit'] = price_diff * (pos['lot_size'] * 100000)
                total_profit += pos['profit']
                
                # Move other positions to breakeven
                for other_pos in positions[1:]:
                    if other_pos['status'] == 'open':
                        other_pos['sl'] = other_pos['entry_price']
            
            # Second position: Close at SECOND_TP_PIPS and move third to +20 pips
            elif position_index == 2 and profit_pips >= SECOND_TP_PIPS:
                pos['status'] = 'closed'
                pos['exit_price'] = current_bar['close']
                pos['exit_time'] = current_bar['time']
                pos['profit'] = price_diff * (pos['lot_size'] * 100000)
                total_profit += pos['profit']
                
                # Move third position's stop loss to +20 pips
                if positions[2]['status'] == 'open':
                    positions[2]['sl'] = positions[2]['entry_price'] + (pip_value * 20 if is_long else -pip_value * 20)
    
    return positions, total_profit

def run_backtest():
    print(f"Starting backtest of {SYMBOL} from {START_DATE} to {END_DATE} with timeframe: {TIMEFRAME}")
    
    # Initialize MT5 connection for historical data
    try:
        if not mt5.initialize():
            print("MT5 initialization failed. Please make sure MetaTrader 5 is running.")
            return None, [], 0
    except Exception as e:
        print(f"MT5 initialization error: {e}")
        print(traceback.format_exc())
        return None, [], 0
    
    try:
        # Get historical data
        rates = mt5.copy_rates_range(SYMBOL, TIMEFRAME, START_DATE, END_DATE)
        if rates is None or len(rates) == 0:
            print(f"Failed to get historical data for {SYMBOL} from {START_DATE} to {END_DATE}")
            print(f"Last MT5 error: {mt5.last_error()}")
            return None, [], 0
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"Loaded {len(df)} bars for backtesting")
        
        # Initialize variables
        balance = INITIAL_BALANCE
        trades = []
        setup_id = 0
        active_setup = False
        active_until = 0
        
        # Required lookback for indicators (minimum to calculate all indicators)
        lookback = max(30, ACE_SETTINGS["SMI_K_PERIOD"] + 10)
        
        # Run through the data
        for i in range(lookback, len(df) - 2):  # Need enough bars for indicators, -2 to avoid index errors at the end
            if active_setup and i < active_until:
                continue
            
            # Get data window for analysis
            window = df.iloc[i-lookback:i+1].copy()
            
            # Check entry conditions
            long_condition, short_condition = check_entry_conditions(window, ACE_SETTINGS)
            
            if long_condition or short_condition:
                setup_id += 1
                current_bar = df.iloc[i]
                price = current_bar['close']
                
                print(f"Setup {setup_id}: {'LONG' if long_condition else 'SHORT'} at {price} on {current_bar['time']}")
                
                # Get dynamic SL/TP based on the ACE strategy (optional)
                is_long = long_condition
                
                # Uncomment these lines to use dynamic SL/TP based on ATR instead of fixed pips
                # window_for_sl_tp = window.copy()
                # sl_price = get_stop_loss(window_for_sl_tp, is_long)
                # tp_price = get_take_profit(window_for_sl_tp, is_long)
                
                # Simulate trade management
                positions, setup_profit = simulate_trade_management(
                    df, i, is_long, price, setup_id
                )
                
                # Update balance
                balance += setup_profit
                
                # Store trade results
                trades.append({
                    'setup_id': setup_id,
                    'entry_time': current_bar['time'],
                    'type': 'long' if long_condition else 'short',
                    'positions': positions,
                    'profit': setup_profit
                })
                
                # Prevent new setups for a while
                active_setup = True
                active_until = i + 10
            
            # Check if active setup period has ended
            if active_setup and i >= active_until:
                active_setup = False
        
        # Print backtest results
        print("\n=== BACKTEST RESULTS ===")
        print(f"Initial Balance: ${INITIAL_BALANCE}")
        print(f"Final Balance: ${balance:.2f}")
        print(f"Total Profit/Loss: ${balance - INITIAL_BALANCE:.2f}")
        print(f"Total Setups: {len(trades)}")
        
        profitable_trades = sum(1 for trade in trades if trade['profit'] > 0)
        losing_trades = sum(1 for trade in trades if trade['profit'] <= 0)
        
        if trades:
            win_rate = (profitable_trades / len(trades)) * 100
            print(f"Win Rate: {win_rate:.2f}%")
            print(f"Profitable Trades: {profitable_trades}")
            print(f"Losing Trades: {losing_trades}")
            
            # Calculate average profit and loss
            profits = [trade['profit'] for trade in trades if trade['profit'] > 0]
            losses = [trade['profit'] for trade in trades if trade['profit'] <= 0]
            
            if profits:
                avg_profit = sum(profits) / len(profits)
                print(f"Average Profit: ${avg_profit:.2f}")
            
            if losses:
                avg_loss = sum(losses) / len(losses)
                print(f"Average Loss: ${avg_loss:.2f}")
        
        return df, trades, balance
    
    except Exception as e:
        print(f"Error during backtest: {e}")
        print(traceback.format_exc())
        return None, [], 0
    
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    run_backtest() 