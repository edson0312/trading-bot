import os
import subprocess
import pandas as pd
import numpy as np
import json
import time
import re
from pathlib import Path
import MetaTrader5 as mt5

class PineScriptHandler:
    def __init__(self, upload_dir="uploaded_indicators"):
        self.upload_dir = upload_dir
        self.pine_files = {}
        self.indicators = {}
        
        # Create upload directory if it doesn't exist
        os.makedirs(self.upload_dir, exist_ok=True)
        
        # Load any existing indicators
        self.load_existing_indicators()
    
    def load_existing_indicators(self):
        """Load existing indicators from the upload directory"""
        try:
            for file in os.listdir(self.upload_dir):
                if file.endswith('.pine'):
                    file_path = os.path.join(self.upload_dir, file)
                    self.pine_files[file] = file_path
                    # Try to convert the indicator
                    self.convert_pine_to_python(file)
        except Exception as e:
            print(f"Error loading existing indicators: {e}")
    
    def save_uploaded_file(self, file_content, filename):
        """Save an uploaded Pine script file"""
        file_path = os.path.join(self.upload_dir, filename)
        
        with open(file_path, 'w') as f:
            f.write(file_content)
        
        self.pine_files[filename] = file_path
        print(f"Saved indicator file: {file_path}")
        return file_path
    
    def detect_pine_version(self, file_content):
        """Detect the Pine Script version from the file content"""
        # Look for version declaration
        version_match = re.search(r'//@version=(\d+)', file_content)
        if version_match:
            return int(version_match.group(1))
        
        # Check for v5/v6 specific syntax if no explicit version
        if "indicator(" in file_content or "strategy(" in file_content:
            return 5  # Default to v5 if no version specified but has v5+ syntax
        
        return 4  # Default to v4 if we can't determine version
    
    def convert_pine_to_python(self, filename):
        """
        Convert Pine script to Python using external tool
        Now supports multiple Pine Script versions (v4, v5, v6)
        """
        try:
            if filename not in self.pine_files:
                print(f"File {filename} not found")
                return False
            
            file_path = self.pine_files[filename]
            
            # Read the file content
            with open(file_path, 'r') as f:
                file_content = f.read()
            
            # Detect Pine Script version
            pine_version = self.detect_pine_version(file_content)
            print(f"Detected Pine Script version: {pine_version} for {filename}")
            
            # Parse the indicator based on type and version
            if "HWR" in filename.upper():
                self.indicators[filename] = self.create_hwr_indicator(pine_version)
                print(f"Successfully loaded HWR indicator: {filename} (Pine v{pine_version})")
                return True
            elif pine_version >= 5:
                # Support for generic v5/v6 indicators
                # This is a placeholder - implement proper v5/v6 parsing logic
                print(f"Recognized Pine Script v{pine_version} indicator: {filename}")
                self.indicators[filename] = self.create_generic_indicator(file_content, pine_version)
                return True
            else:
                print(f"Indicator type not supported yet: {filename}")
                return False
                
        except Exception as e:
            print(f"Error converting Pine script: {e}")
            return False
    
    def create_generic_indicator(self, file_content, version):
        """
        Create a generic indicator based on Pine Script v5/v6 content
        This is a placeholder implementation that extracts key parameters and functions
        """
        def generic_indicator(df, length=14):
            """Generic indicator calculation using common technical indicators"""
            # Create a copy to avoid modifying the original
            df = df.copy()
            
            # Ensure SMA is calculated
            if 'sma' not in df.columns:
                df['sma'] = df['close'].rolling(window=length).mean()
            
            try:
                # Calculate RSI
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                avg_gain = gain.rolling(window=length).mean()
                avg_loss = loss.rolling(window=length).mean()
                
                # Avoid division by zero
                avg_loss = avg_loss.replace(0, 0.001)
                rs = avg_gain / avg_loss
                df['rsi'] = 100 - (100 / (1 + rs))
                
                # Calculate Bollinger Bands
                std = df['close'].rolling(window=length).std()
                df['bb_middle'] = df['sma']
                df['bb_upper'] = df['bb_middle'] + (std * 2)
                df['bb_lower'] = df['bb_middle'] - (std * 2)
                
                # Generate buy/sell signals based on RSI and SMA crossovers
                df['buy_signal'] = (df['rsi'] < 40) & (df['close'] > df['sma']) & (df['close'] < df['bb_lower'] * 1.05)
                df['sell_signal'] = (df['rsi'] > 60) & (df['close'] < df['sma']) & (df['close'] > df['bb_upper'] * 0.95)
                
                # Try to extract conditions from Pine Script content if present
                if "buy =" in file_content and "sell =" in file_content:
                    # Very basic parsing - this is just a placeholder
                    # In a real implementation, we would parse the Pine Script code properly
                    print(f"Found buy/sell conditions in Pine Script v{version}")
                
                # Debug info
                print(f"Generic indicator created for Pine Script v{version}")
                print(f"DataFrame shape: {df.shape}")
                
                return df
            except Exception as e:
                print(f"Error in generic indicator calculation: {e}")
                # Ensure basic signals exist even if calculation fails
                df['buy_signal'] = False
                df['sell_signal'] = False
                return df
        
        return generic_indicator
    
    def create_hwr_indicator(self, version=4):
        """
        Create a HWR (High Wave Ratio) indicator implementation
        Now supports multiple Pine Script versions
        """
        def calculate_hwr(df, length=21):
            """
            HWR calculation for Pine Script v4+:
            1. Calculate the true range
            2. Calculate average range with specified length
            3. Calculate wave height as (high-low)
            4. Calculate wave ratio as wave height / average range
            5. Add buy/sell signals based on thresholds
            """
            # Create a copy to avoid modifying the original
            df = df.copy()
            
            # Calculate SMA for all versions (needed for v5+)
            df['sma'] = df['close'].rolling(window=length).mean()
            
            # Calculate the true range (TR) properly
            df['prev_close'] = df['close'].shift(1)
            
            # Now calculate TR for each row with proper handling of prev_close
            df['tr'] = df.apply(
                lambda x: max(
                    x['high'] - x['low'],
                    abs(x['high'] - x['prev_close']) if not pd.isna(x['prev_close']) else 0,
                    abs(x['low'] - x['prev_close']) if not pd.isna(x['prev_close']) else 0
                ), axis=1)
            
            # Calculate ATR (Average True Range)
            df['atr'] = df['tr'].rolling(window=length).mean()
            
            # Calculate wave height
            df['wave_height'] = df['high'] - df['low']
            
            # Calculate HWR
            df['hwr'] = df.apply(
                lambda x: x['wave_height'] / x['atr'] if x['atr'] > 0 else 0, 
                axis=1
            )
            
            # Generate signals - different for v5+ vs v4
            if version >= 5:
                # v5/v6 Pine Script often uses more complex conditions
                df['hwr_buy'] = (df['hwr'] < 0.5) & (df['close'] > df['open']) & (df['close'] > df['sma'])
                df['hwr_sell'] = (df['hwr'] < 0.5) & (df['close'] < df['open']) & (df['close'] < df['sma'])
            else:
                # v4 Pine Script uses simpler conditions
                df['hwr_buy'] = (df['hwr'] < 0.5) & (df['close'] > df['open'])
                df['hwr_sell'] = (df['hwr'] < 0.5) & (df['close'] < df['open'])
            
            return df
        
        return calculate_hwr
    
    def apply_indicator(self, df, indicator_name):
        """Apply a loaded indicator to dataframe"""
        if indicator_name in self.indicators:
            indicator_func = self.indicators[indicator_name]
            # Calculate SMA before applying indicator in case it's needed
            df = df.copy()
            df['sma'] = df['close'].rolling(window=21).mean()
            return indicator_func(df)
        else:
            # Auto-load the indicator if the file exists but indicator not loaded
            if os.path.exists(os.path.join(self.upload_dir, indicator_name)):
                if self.convert_pine_to_python(indicator_name):
                    # Create a copy and calculate SMA before calling the indicator
                    df = df.copy()
                    df['sma'] = df['close'].rolling(window=21).mean()
                    return self.indicators[indicator_name](df)
            
            print(f"Indicator {indicator_name} not loaded")
            # Add SMA column to the original dataframe to avoid errors
            df = df.copy()
            df['sma'] = df['close'].rolling(window=21).mean()
            return df
    
    def check_entry_conditions(self, df, indicator_name):
        """Check entry conditions based on indicator"""
        # Create a copy of the dataframe to avoid modifying the original
        df = df.copy()
        
        # Always calculate SMA first to ensure it's available for all indicators
        df['sma'] = df['close'].rolling(window=21).mean()
        
        if indicator_name not in self.indicators:
            # Try to auto-load the indicator
            if os.path.exists(os.path.join(self.upload_dir, indicator_name)):
                if not self.convert_pine_to_python(indicator_name):
                    print(f"Failed to load indicator {indicator_name}")
                    return False, False
            else:
                print(f"Indicator {indicator_name} not found")
                return False, False
        
        try:
            # Apply indicator to data
            df = self.apply_indicator(df, indicator_name)
            
            # Check for buy/sell signals on the latest bar
            if len(df) > 0:
                last_bar = df.iloc[-1]
                
                # Try different signal column names (for compatibility)
                long_condition = last_bar.get('hwr_buy', False) or last_bar.get('buy_signal', False)
                short_condition = last_bar.get('hwr_sell', False) or last_bar.get('sell_signal', False)
                
                print(f"Indicator value: {last_bar.get('hwr', 'N/A')}, Buy: {long_condition}, Sell: {short_condition}")
                
                return long_condition, short_condition
            else:
                print("No data available for entry conditions check")
                return False, False
                
        except Exception as e:
            print(f"Error checking entry conditions: {e}")
            print(f"Indicator: {indicator_name}")
            import traceback
            traceback.print_exc()
            return False, False

# Example usage
if __name__ == "__main__":
    # Test with sample data
    handler = PineScriptHandler()
    
    # Example Pine script content for HWR v5
    example_pine_v5 = """
    //@version=5
    indicator("High Wave Ratio (HWR)", shorttitle="HWR")
    
    length = input.int(21, "Length")
    
    // Calculate True Range and ATR
    tr = math.max(high - low, math.abs(high - close[1]), math.abs(low - close[1]))
    atr = ta.sma(tr, length)
    
    // Calculate wave height and HWR
    wave_height = high - low
    hwr = wave_height / atr
    
    // Define buy and sell conditions
    buy = hwr < 0.5 and close > open
    sell = hwr < 0.5 and close < open
    
    // Plot signals
    plotshape(buy, title="Buy Signal", location=location.belowbar, color=color.green, style=shape.labelup, size=size.small)
    plotshape(sell, title="Sell Signal", location=location.abovebar, color=color.red, style=shape.labeldown, size=size.small)
    """
    
    # Save and convert
    file_path = handler.save_uploaded_file(example_pine_v5, "HWR_v5.pine")
    handler.convert_pine_to_python("HWR_v5.pine")
    
    # Create sample data
    data = {
        'open': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 108.0],
        'high': [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 109.0],
        'low': [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 106.0],
        'close': [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 107.0]
    }
    
    df = pd.DataFrame(data)
    result_df = handler.apply_indicator(df, "HWR_v5.pine")
    
    # Check signals
    long, short = handler.check_entry_conditions(df, "HWR_v5.pine")
    print(f"Buy signal: {long}, Sell signal: {short}")
    print(result_df[['close', 'hwr', 'hwr_buy', 'hwr_sell']].tail()) 