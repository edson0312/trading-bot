import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
import pytz
import traceback
import config
from trading_bot import DrawdownLayerManager, TradingBot
from strategies.ace_strategy import check_entry_conditions

def test_drawdown_layering():
    """Test the drawdown layering strategy functionality"""
    print("Testing Drawdown Layering Strategy Implementation")
    print("=" * 50)
    
    # Initialize MT5
    if not mt5.initialize():
        print("Failed to initialize MT5. Please ensure MT5 is running and logged in.")
        return
    
    try:
        # Display configuration settings
        print(f"Symbol: {config.SYMBOL}")
        print(f"Drawdown Layer Threshold: {config.DRAWDOWN_LAYER_THRESHOLD} pips")
        print(f"Positions Per Layer: {config.POSITIONS_PER_LAYER}")
        print(f"Minimum Profit Per Position: {config.MINIMUM_PROFIT_PER_POSITION} pips")
        print(f"Maximum Layers: {config.MAX_LAYERS}")
        print("=" * 50)
        
        # Create a drawdown layer manager instance
        layer_manager = DrawdownLayerManager(config.SYMBOL, config.LOT_SIZE)
        
        # Check for current positions
        positions = mt5.positions_get(symbol=config.SYMBOL)
        if positions:
            print(f"Found {len(positions)} existing positions for {config.SYMBOL}")
            
            # Group positions by setup ID
            position_groups = layer_manager.group_positions_by_setup()
            
            for setup_id, setup_positions in position_groups.items():
                print(f"\nSetup ID: {setup_id}, Positions: {len(setup_positions)}")
                
                # Calculate current drawdown
                current_drawdown = layer_manager.get_current_drawdown(setup_positions)
                print(f"Current drawdown: {current_drawdown:.2f} pips")
                
                # Calculate current layers
                current_layers = len(setup_positions) // config.POSITIONS_PER_LAYER
                print(f"Current layers: {current_layers}")
                
                # Calculate required layers
                required_layers = 1 + int(current_drawdown / config.DRAWDOWN_LAYER_THRESHOLD)
                required_layers = min(required_layers, config.MAX_LAYERS)
                print(f"Required layers: {required_layers}")
                
                # Calculate layers to add
                layers_to_add = max(0, required_layers - current_layers)
                print(f"Layers to add: {layers_to_add}")
                
                # Get TP calculation
                if len(setup_positions) > 0:
                    is_buy = setup_positions[0].type == 0
                    current_price = mt5.symbol_info_tick(config.SYMBOL).ask if is_buy else mt5.symbol_info_tick(config.SYMBOL).bid
                    tp_price = layer_manager.calculate_tp_for_layer(setup_id, is_buy, current_price)
                    
                    # Calculate weighted average entry price
                    total_volume = sum(pos.volume for pos in setup_positions)
                    avg_entry_price = sum(pos.price_open * pos.volume for pos in setup_positions) / total_volume
                    
                    # Calculate profit in pips
                    pip_value = layer_manager.get_pip_value()
                    profit_pips = (tp_price - avg_entry_price) / pip_value * (1 if is_buy else -1)
                    
                    print(f"Average entry price: {avg_entry_price}")
                    print(f"Calculated TP price: {tp_price}")
                    print(f"Profit in pips: {profit_pips:.2f}")
                    
                    # Verify profit is at least minimum
                    if profit_pips >= config.MINIMUM_PROFIT_PER_POSITION:
                        print("✅ TP ensures minimum profit requirement")
                    else:
                        print("❌ TP does not ensure minimum profit requirement")
        else:
            print("No existing positions found. Cannot test drawdown calculation.")
            
            # Create a trading bot to test signal detection
            bot = TradingBot()
            if bot.initialize_mt5():
                print("\nTesting entry signal detection...")
                df = bot.get_historical_data()
                long_signal, short_signal = check_entry_conditions(df, config.ACE_SETTINGS)
                
                print(f"Current entry signals - Long: {long_signal}, Short: {short_signal}")
                
                if long_signal or short_signal:
                    print("Signal detected. You can run the trading bot to open positions and then test layering.")
                else:
                    print("No entry signals detected at this time.")
            
    except Exception as e:
        print(f"Error testing drawdown layering: {e}")
        traceback.print_exc()
    finally:
        # Clean up
        mt5.shutdown()
        print("\nTest completed.")

if __name__ == "__main__":
    test_drawdown_layering() 