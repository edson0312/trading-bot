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
        Check WMI indicator conditions
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
        
        # Check buy condition: crossover and below oversold
        buy_condition = (last_signal > last_signal_ema and 
                        prev_signal <= prev_signal_ema and 
                        last_signal < os)
        
        # Check sell condition: crossunder and above overbought
        sell_condition = (last_signal < last_signal_ema and 
                         prev_signal >= prev_signal_ema and 
                         last_signal > ob)
        
        print(f"WMI Signal: {last_signal:.2f}, EMA: {last_signal_ema:.2f}")
        print(f"Buy Condition: {buy_condition}, Sell Condition: {sell_condition}")
        
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
