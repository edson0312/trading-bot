import pandas as pd
import numpy as np
from ta.trend import ADXIndicator
from ta.momentum import StochasticOscillator
from ta.trend import MACD
from ta.volatility import AverageTrueRange

def calculate_smi(df, k_period=10, d_period=3, ema_period=3):
    """Calculate Stochastic Momentum Index (SMI)"""
    highest_high = df['high'].rolling(window=k_period).max()
    lowest_low = df['low'].rolling(window=k_period).min()
    
    # Calculate relative range
    relative_range = df['close'] - (highest_high + lowest_low) / 2
    highest_lowest_range = highest_high - lowest_low
    
    # Double EMA calculations
    ema_relative_range = relative_range.ewm(span=d_period, adjust=False).mean()
    ema_ema_relative_range = ema_relative_range.ewm(span=d_period, adjust=False).mean()
    
    ema_highest_lowest_range = highest_lowest_range.ewm(span=d_period, adjust=False).mean()
    ema_ema_highest_lowest_range = ema_highest_lowest_range.ewm(span=d_period, adjust=False).mean()
    
    # Calculate SMI
    smi = 200 * (ema_ema_relative_range / ema_ema_highest_lowest_range)
    
    # Calculate SMI-based EMA
    smi_based_ema = smi.ewm(span=ema_period, adjust=False).mean()
    
    return smi, smi_based_ema

def calculate_macd(df, fast_period=12, slow_period=26, signal_period=9):
    """Calculate MACD indicator"""
    macd = MACD(df['close'], window_fast=fast_period, window_slow=slow_period, window_sign=signal_period)
    macd_line = macd.macd()
    signal_line = macd.macd_signal()
    histogram = macd.macd_diff()
    return macd_line, signal_line, histogram

def calculate_macd_colors(histogram):
    """Calculate MACD histogram color scheme based on ACE strategy"""
    # Define colors as numeric values for easy comparison
    DARK_GREEN = 1
    LIGHT_GREEN = 2
    DARK_RED = 3
    LIGHT_RED = 4
    
    # Initialize colors array
    colors = np.zeros(len(histogram))
    
    # Loop through and assign colors
    for i in range(1, len(histogram)):
        if histogram[i] >= 0:
            if histogram[i-1] < histogram[i]:
                colors[i] = DARK_GREEN
            else:
                colors[i] = LIGHT_GREEN
        else:
            if histogram[i-1] < histogram[i]:
                colors[i] = LIGHT_RED
            else:
                colors[i] = DARK_RED
    
    return colors

def calculate_adx(df, period=14):
    """Calculate ADX indicator"""
    adx = ADXIndicator(df['high'], df['low'], df['close'], period)
    return adx.adx()

def check_entry_conditions(df, settings=None):
    """Check entry conditions based on ACE indicator logic"""
    if len(df) < 30:  # Need enough data for indicators
        print("Not enough data points for indicator calculation")
        return False, False
    
    # Use settings if provided or default values
    if settings is None:
        settings = {
            "ADX_PERIOD": 14,
            "ADX_THRESHOLD": 20,
            "SMI_K_PERIOD": 10,
            "SMI_D_PERIOD": 7,
            "SMI_EMA_PERIOD": 3
        }
    
    # Get parameters from settings
    adx_period = settings.get("ADX_PERIOD", 14)
    adx_threshold = settings.get("ADX_THRESHOLD", 12)
    smi_k_period = settings.get("SMI_K_PERIOD", 10)
    smi_d_period = settings.get("SMI_D_PERIOD", 7)
    smi_ema_period = settings.get("SMI_EMA_PERIOD", 3)
    
    # Calculate SMI
    smi, smi_based_ema = calculate_smi(df, 
                                      k_period=smi_k_period, 
                                      d_period=smi_d_period, 
                                      ema_period=smi_ema_period)
    
    # Calculate MACD
    macd, signal, histogram = calculate_macd(df)
    
    # Calculate MACD colors
    macd_colors = calculate_macd_colors(histogram.values)
    
    # Calculate ADX
    adx = calculate_adx(df, period=adx_period)
    
    # Check if candles are green or red
    is_candle_green = df['close'] > df['open']
    is_candle_red = df['close'] < df['open']
    
    # Get the latest values
    current_smi = smi.iloc[-1]
    current_smi_ema = smi_based_ema.iloc[-1]
    current_macd = macd.iloc[-1]
    current_signal = signal.iloc[-1]
    current_hist = histogram.iloc[-1]
    current_adx = adx.iloc[-1]
    
    # Define conditions
    smi_ob = 40  # Overbought threshold
    smi_os = -40  # Oversold threshold
    
    # SMI conditions
    is_smi_rising = smi.diff().iloc[-1] > 0
    is_smi_falling = smi.diff().iloc[-1] < 0
    is_overbought = current_smi > smi_ob and current_smi_ema > smi_ob
    is_oversold = current_smi < smi_os and current_smi_ema < smi_os
    
    # MACD conditions
    is_macd_above_mid = current_macd > 0 and current_signal > 0
    is_macd_below_mid = current_macd < 0 and current_signal < 0
    
    # Check for crossovers
    smi_cross_up = smi.iloc[-2] < smi_based_ema.iloc[-2] and smi.iloc[-1] > smi_based_ema.iloc[-1]
    smi_cross_down = smi.iloc[-2] > smi_based_ema.iloc[-2] and smi.iloc[-1] < smi_based_ema.iloc[-1]
    macd_cross_up = macd.iloc[-2] < signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]
    macd_cross_down = macd.iloc[-2] > signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]
    
    # Check for MACD color shifts (key for entries)
    is_hist_dark_green = macd_colors[-1] == 1
    is_hist_light_green = macd_colors[-1] == 2
    is_hist_dark_red = macd_colors[-1] == 3
    is_hist_light_red = macd_colors[-1] == 4
    
    # Check for color reversals
    is_green_to_red = is_candle_green.iloc[-2] and is_candle_red.iloc[-1]
    is_red_to_green = is_candle_red.iloc[-2] and is_candle_green.iloc[-1]
    
    # ADX condition
    is_valid_adx = current_adx > adx_threshold  # Valid trend strength
    
    # Print debugging information
    print("\n--- ACE Strategy Indicator Values ---")
    print(f"SMI: {current_smi:.2f}, SMI EMA: {current_smi_ema:.2f}")
    print(f"SMI rising: {is_smi_rising}, SMI falling: {is_smi_falling}")
    print(f"SMI overbought: {is_overbought}, SMI oversold: {is_oversold}")
    print(f"SMI cross up: {smi_cross_up}, SMI cross down: {smi_cross_down}")
    
    print(f"MACD: {current_macd:.6f}, Signal: {current_signal:.6f}, Histogram: {current_hist:.6f}")
    print(f"MACD above mid: {is_macd_above_mid}, MACD below mid: {is_macd_below_mid}")
    print(f"MACD cross up: {macd_cross_up}, MACD cross down: {macd_cross_down}")
    print(f"MACD colors - Dark green: {is_hist_dark_green}, Light green: {is_hist_light_green}")
    print(f"MACD colors - Dark red: {is_hist_dark_red}, Light red: {is_hist_light_red}")
    
    print(f"ADX: {current_adx:.2f}, Valid trend strength: {is_valid_adx}")
    print(f"Candle color change - Green to red: {is_green_to_red}, Red to green: {is_red_to_green}")
    
    # Entry conditions
    # Buy conditions
    buy_condition = (
        # SMI conditions
        ((is_oversold and is_smi_rising) or smi_cross_up or macd_cross_up) and
        # MACD confirmation
        (is_hist_light_green or (is_hist_dark_green and is_red_to_green)) and
        # ADX confirmation
        is_valid_adx
    )
    
    # Sell conditions
    sell_condition = (
        # SMI conditions
        ((is_overbought and is_smi_falling) or smi_cross_down or macd_cross_down) and
        # MACD confirmation
        (is_hist_light_red or (is_hist_dark_red and is_green_to_red)) and
        # ADX confirmation
        is_valid_adx
    )
    
    # Print detailed entry condition results
    if not buy_condition:
        print("\nBuy condition not met because:")
        if not ((is_oversold and is_smi_rising) or smi_cross_up or macd_cross_up):
            print("- SMI conditions not met (need oversold + rising OR SMI crossover OR MACD crossover)")
        if not (is_hist_light_green or (is_hist_dark_green and is_red_to_green)):
            print("- MACD color conditions not met (need light green OR dark green with candle color change)")
        if not is_valid_adx:
            print(f"- ADX not above threshold ({current_adx:.2f} vs {adx_threshold})")
    
    if not sell_condition:
        print("\nSell condition not met because:")
        if not ((is_overbought and is_smi_falling) or smi_cross_down or macd_cross_down):
            print("- SMI conditions not met (need overbought + falling OR SMI crossdown OR MACD crossdown)")
        if not (is_hist_light_red or (is_hist_dark_red and is_green_to_red)):
            print("- MACD color conditions not met (need light red OR dark red with candle color change)")
        if not is_valid_adx:
            print(f"- ADX not above threshold ({current_adx:.2f} vs {adx_threshold})")
    
    return buy_condition, sell_condition

def get_stop_loss(df, is_long):
    """Calculate stop loss level based on ATR"""
    atr_indicator = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    atr_value = atr_indicator.average_true_range().iloc[-1]
    current_price = df['close'].iloc[-1]
    
    # More conservative SL setting based on updated ACE strategy
    if is_long:
        recent_low = df['low'].tail(5).min()
        return min(current_price - (atr_value * 2), recent_low - (atr_value * 0.5))
    else:
        recent_high = df['high'].tail(5).max()
        return max(current_price + (atr_value * 2), recent_high + (atr_value * 0.5))

def get_take_profit(df, is_long):
    """Calculate take profit level based on ATR and fibonacci extensions"""
    atr_indicator = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    atr_value = atr_indicator.average_true_range().iloc[-1]
    current_price = df['close'].iloc[-1]
    
    # More dynamic TP setting based on updated ACE strategy
    if is_long:
        return current_price + (atr_value * 3)  # 3 ATR for take profit
    else:
        return current_price - (atr_value * 3) 