import pandas as pd
import numpy as np
from typing import Tuple, List, Dict
import MetaTrader5 as mt5

def calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Average True Range"""
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr

def calculate_trailing_stop(df: pd.DataFrame, settings: Dict) -> Tuple[pd.Series, pd.Series]:
    """Calculate the trailing stop levels based on WaveBF logic"""
    
    # Get settings
    key_value = settings['key_value']
    atr_period = settings['atr_period']
    use_heikin_ashi = settings['use_heikin_ashi']
    
    # Calculate ATR
    atr = calculate_atr(df, atr_period)
    n_loss = key_value * atr
    
    # Use either regular close or Heikin Ashi close
    if use_heikin_ashi:
        ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        src = ha_close
    else:
        src = df['close']
    
    # Initialize trailing stop series
    trailing_stop = pd.Series(index=df.index, dtype=float)
    position = pd.Series(index=df.index, dtype=float)
    
    # Calculate trailing stop and position
    for i in range(1, len(df)):
        prev_stop = trailing_stop.iloc[i-1] if not pd.isna(trailing_stop.iloc[i-1]) else 0
        curr_src = src.iloc[i]
        prev_src = src.iloc[i-1]
        
        # Calculate new trailing stop
        if curr_src > prev_stop and prev_src > prev_stop:
            trailing_stop.iloc[i] = max(prev_stop, curr_src - n_loss.iloc[i])
        elif curr_src < prev_stop and prev_src < prev_stop:
            trailing_stop.iloc[i] = min(prev_stop, curr_src + n_loss.iloc[i])
        elif curr_src > prev_stop:
            trailing_stop.iloc[i] = curr_src - n_loss.iloc[i]
        else:
            trailing_stop.iloc[i] = curr_src + n_loss.iloc[i]
        
        # Calculate position
        if prev_src < prev_stop and curr_src > trailing_stop.iloc[i]:
            position.iloc[i] = 1  # Long
        elif prev_src > prev_stop and curr_src < trailing_stop.iloc[i]:
            position.iloc[i] = -1  # Short
        else:
            position.iloc[i] = position.iloc[i-1] if i > 0 else 0
    
    return trailing_stop, position

def check_entry_conditions(df: pd.DataFrame, settings: Dict) -> Tuple[bool, bool]:
    """Check entry conditions for WaveBF strategy
    Returns: (long_condition, short_condition)
    """
    if len(df) < 2:
        return False, False
        
    # Calculate trailing stop and position
    trailing_stop, position = calculate_trailing_stop(df, settings)
    
    # Calculate EMA
    ema = df['close'].ewm(span=settings['ema_period'], adjust=False).mean()
    
    # Check for crossovers
    above_cross = (ema.shift(1) <= trailing_stop.shift(1)) & (ema > trailing_stop)
    below_cross = (ema.shift(1) >= trailing_stop.shift(1)) & (ema < trailing_stop)
    
    # Entry conditions
    long_condition = (df['close'].iloc[-1] > trailing_stop.iloc[-1]) & above_cross.iloc[-1]
    short_condition = (df['close'].iloc[-1] < trailing_stop.iloc[-1]) & below_cross.iloc[-1]
    
    return long_condition, short_condition

def get_stop_loss(df: pd.DataFrame, settings: Dict, is_long: bool) -> float:
    """Calculate stop loss level based on WaveBF logic"""
    trailing_stop, _ = calculate_trailing_stop(df, settings)
    return trailing_stop.iloc[-1]

def get_take_profit(df: pd.DataFrame, settings: Dict, is_long: bool, entry_price: float) -> float:
    """Calculate take profit level based on ATR"""
    atr = calculate_atr(df, settings['atr_period']).iloc[-1]
    tp_distance = settings['key_value'] * 2 * atr  # Using 2x the key value for TP
    
    if is_long:
        return entry_price + tp_distance
    else:
        return entry_price - tp_distance 