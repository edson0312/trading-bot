import MetaTrader5 as mt5

# Trading Symbol Configuration
SYMBOL = "XAUUSD"  # Change to your preferred trading symbol

# Timeframe Configuration
TIMEFRAME = mt5.TIMEFRAME_M15  # Default timeframe (15-minute)
# Other options:
# TIMEFRAME = mt5.TIMEFRAME_M1     # 1-minute
# TIMEFRAME = mt5.TIMEFRAME_M5     # 5-minute
# TIMEFRAME = mt5.TIMEFRAME_M30    # 30-minute
# TIMEFRAME = mt5.TIMEFRAME_H1     # 1-hour
# TIMEFRAME = mt5.TIMEFRAME_H4     # 4-hour
# TIMEFRAME = mt5.TIMEFRAME_D1     # 1-day

# Position Sizing
LOT_SIZE = 0.01  # Fixed lot size for all positions

# Strategy Selection
ACTIVE_STRATEGY = "ACE"  # Options: "FVG", "WaveBF", "ACE"

# Trade Management Parameters
POSITIONS_PER_SETUP = 3  # Number of positions per trade setup
TP_PIPS = 100  # Maximum take profit in pips
SL_PIPS = 100  # Maximum stop loss in pips
FIRST_TP_PIPS = 20  # First position closes at 20 pips profit
SECOND_TP_PIPS = 50  # Second position closes at 50 pips profit
BREAKEVEN_TRIGGER_PIPS = 20  # Move to breakeven after 20 pips
TRAILING_STOP_PIPS = 20  # Trailing stop distance

# Drawdown Layering Strategy Parameters
ENABLE_DRAWDOWN_LAYERING = False  # Enable or disable drawdown layering
DRAWDOWN_LAYER_THRESHOLD = 20    # Add new layer every 20 pips of drawdown
POSITIONS_PER_LAYER = 3          # Each layer must have exactly 3 positions
MINIMUM_PROFIT_PER_POSITION = 20 # Each position must achieve at least 20 pips profit
MAX_LAYERS = 5                   # Maximum number of layers allowed (to limit risk)

# FVG Strategy Parameters
LOOKBACK = 100  # Lookback period for indicator calculation

# Trade Execution Settings
MAGIC_NUMBER = 234000  # Magic number to identify bot trades
DEVIATION = 10  # Maximum price deviation in points

# Backtesting Configuration
INITIAL_BALANCE = 100000  # Initial balance for backtesting

# Logging Configuration
ENABLE_LOGGING = True  # Enable or disable detailed logging
LOG_LEVEL = "INFO"  # Options: "DEBUG", "INFO", "WARNING", "ERROR"

# Trading Rules
TRADE_DIRECTION = "BOTH"  # Options: "LONG", "SHORT", "BOTH"

# Trading Schedule
TRADING_HOURS = {
    "Monday": [(0, 23)],     # [(start_hour, end_hour)]
    "Tuesday": [(0, 23)],
    "Wednesday": [(0, 23)],
    "Thursday": [(0, 23)],
    "Friday": [(0, 20)],    # Stop trading at 8 PM on Friday
    "Saturday": [],         # No trading on Saturday
    "Sunday": [(22, 23)]    # Start trading at 10 PM on Sunday
}

# MT5 Account Configuration
def get_account_config():
    return {
        "login": 91137210,
        "password": "*1ZwLoRq",
        "server": "MetaQuotes-Demo",
        "timeout": 60000
    }
    
    # OPTION 2: If you don't want to store credentials in the code,
    # make sure you're logged in to MT5 terminal before starting the bot
    # The bot will use the active MT5 session if no credentials are provided above

# ACE Strategy Settings
ACE_SETTINGS = {
    'adx_period': 14,
    'adx_threshold': 25,
    'rsi_period': 14,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'smi_k_period': 10,
    'smi_d_period': 3,
    'smi_overbought': 40,
    'smi_oversold': -40,
} 