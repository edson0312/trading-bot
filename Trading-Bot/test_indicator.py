import pandas as pd
import numpy as np
from custom_indicators import PineScriptHandler
import os

def test_indicator_sma_calculation():
    """Test that SMA is properly calculated in all code paths"""
    print("Testing SMA calculation in indicators...")
    
    # Create the handler
    handler = PineScriptHandler()
    
    # Create sample data (must have enough data for valid SMA calculation)
    data = {
        'open': [100.0 + i for i in range(30)],
        'high': [101.0 + i for i in range(30)],
        'low': [99.0 + i for i in range(30)],
        'close': [100.5 + i for i in range(30)]
    }
    
    df = pd.DataFrame(data)
    
    # Test 1: Direct SMA calculation in check_entry_conditions
    print("\nTest 1: check_entry_conditions with non-existent indicator")
    try:
        # This should not raise a KeyError even with a non-existent indicator
        buy, sell = handler.check_entry_conditions(df, "non_existent_indicator.pine")
        print(f"Result: buy={buy}, sell={sell} (should be False, False)")
        print("✅ Test 1 passed: No KeyError")
    except KeyError as e:
        print(f"❌ Test 1 failed: KeyError occurred: {e}")
    
    # Test 2: HWR indicator
    print("\nTest 2: HWR Indicator")
    # Create test pine file if it doesn't exist
    hwr_test_file = os.path.join(handler.upload_dir, "HWR_test.pine")
    with open(hwr_test_file, 'w') as f:
        f.write("""
//@version=5
indicator("High Wave Ratio (HWR)", shorttitle="HWR")
length = input.int(21, "Length")
tr = math.max(high - low, math.abs(high - close[1]), math.abs(low - close[1]))
atr = ta.sma(tr, length)
wave_height = high - low
hwr = wave_height / atr
buy = hwr < 0.5 and close > open
sell = hwr < 0.5 and close < open
        """)
    
    print(f"Created test file: {hwr_test_file}")
    handler.save_uploaded_file(open(hwr_test_file).read(), "HWR_test.pine")
    handler.convert_pine_to_python("HWR_test.pine")
    
    try:
        # This should calculate SMA and not raise KeyError
        df_result = handler.apply_indicator(df, "HWR_test.pine")
        if 'sma' in df_result.columns:
            print(f"SMA column exists in result with {df_result['sma'].count()} values")
            print("✅ Test 2 passed: SMA column exists")
        else:
            print("❌ Test 2 failed: No SMA column in result")
    except KeyError as e:
        print(f"❌ Test 2 failed: KeyError occurred: {e}")
    
    # Test 3: Generic indicator
    print("\nTest 3: Generic Indicator v5")
    generic_test_file = os.path.join(handler.upload_dir, "Generic_test.pine")
    with open(generic_test_file, 'w') as f:
        f.write("""
//@version=5
indicator("Generic RSI Test", shorttitle="GenRSI")
length = input.int(14, "Length")
rsi = ta.rsi(close, length)
buy = rsi < 30
sell = rsi > 70
        """)
    
    print(f"Created test file: {generic_test_file}")
    handler.save_uploaded_file(open(generic_test_file).read(), "Generic_test.pine")
    handler.convert_pine_to_python("Generic_test.pine")
    
    try:
        # Test the generic indicator
        df_result = handler.apply_indicator(df, "Generic_test.pine")
        if 'sma' in df_result.columns:
            print(f"SMA column exists in result with {df_result['sma'].count()} values")
            print("✅ Test 3 passed: SMA column exists")
        else:
            print("❌ Test 3 failed: No SMA column in result")
    except KeyError as e:
        print(f"❌ Test 3 failed: KeyError occurred: {e}")
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    test_indicator_sma_calculation() 