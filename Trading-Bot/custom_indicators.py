import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import os

class PineScriptHandler:
    def __init__(self, indicator_name=None):
        self.indicator_name = indicator_name
        self.default_indicator = "WMITable.pine"
        self.indicators = {
            "WMITable.pine": "Wave Momentum Index with MTF Table"
        }
        
    def check_entry_conditions(self, symbol, timeframe, num_bars=100):
        """
        Check entry conditions based on the selected indicator
        Returns: tuple (should_buy, should_sell)
        """
        if not self.indicator_name:
            self.indicator_name = self.default_indicator
            
        # Get historical data
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
        if rates is None or len(rates) == 0:
            print(f"Failed to get rates for {symbol}")
            return False, False
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Handle WMI indicator
        if "WMITable" in self.indicator_name:
            return self._check_wmi_conditions(df)
            
        # Add other indicator handlers here
        return False, False
        
    def _check_wmi_conditions(self, df):
        """
        Check WMI indicator conditions - Fixed to match TradingView interpretation
        Returns: tuple (should_buy, should_sell)
        """
        # Calculate WMI components
        a = 20  # Percent K Length
        b = 3   # Percent D Length
        ob = 40  # Overbought level
        os = -40  # Oversold level
        
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
        last_signal = smi_signal.iloc[-1]
        last_signal_ema = smi_signal_ema.iloc[-1]
        prev_signal = smi_signal.iloc[-2]
        prev_signal_ema = smi_signal_ema.iloc[-2]
        
        # Check buy condition: WMI Signal crosses above EMA Signal in oversold region
        buy_condition = (
            last_signal > last_signal_ema and  # Current crossover
            prev_signal <= prev_signal_ema and  # Confirms the crossover
            last_signal < os  # In oversold region
        )
        
        # Check sell condition: WMI Signal crosses below EMA Signal in overbought region
        sell_condition = (
            last_signal < last_signal_ema and  # Current crossunder
            prev_signal >= prev_signal_ema and  # Confirms the crossunder
            last_signal > ob  # In overbought region
        )
        
        print(f"WMI Signal Analysis:")
        print(f"  - Current WMI: {last_signal:.2f}, Current EMA: {last_signal_ema:.2f}")
        print(f"  - Previous WMI: {prev_signal:.2f}, Previous EMA: {prev_signal_ema:.2f}")
        print(f"  - Oversold level: {os}, Overbought level: {ob}")
        print(f"  - Buy Condition: {buy_condition} (Needs: crossover + oversold)")
        print(f"  - Sell Condition: {sell_condition} (Needs: crossunder + overbought)")
        
        return buy_condition, sell_condition
        
    def check_exit_conditions(self, symbol, timeframe, num_bars=100):
        """
        Check exit conditions based on the selected indicator
        Returns: bool (should_exit)
        """
        if not self.indicator_name:
            self.indicator_name = self.default_indicator
            
        # Get historical data
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
        if rates is None or len(rates) == 0:
            print(f"Failed to get rates for {symbol}")
            return False
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Handle WMI indicator
        if "WMITable" in self.indicator_name:
            return self._check_wmi_exit_conditions(df)
            
        # Add other indicator handlers here
        return False
        
    def _check_wmi_exit_conditions(self, df):
        """
        Check WMI exit conditions
        Returns: bool (should_exit)
        """
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
        
        # Get the last value
        last_signal_ema = smi_signal_ema.iloc[-1]
        
        # Check exit condition: EMA touches midline (0)
        exit_condition = abs(last_signal_ema) < 0.1  # Small threshold to account for floating point precision
        
        print(f"WMI Exit Check - EMA: {last_signal_ema:.2f}, Should Exit: {exit_condition}")
        
        return exit_condition
