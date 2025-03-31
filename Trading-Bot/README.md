# ACE Trading Bot

## Version 1.0.0

A powerful MT5 trading bot with advanced position management strategies.

## Features

- **ACE Trading Strategy**: Use ADX, Stochastic Momentum Index (SMI), and other indicators for precise entry and exit signals
- **Progressive Lockin Strategy**: Intelligent take-profit and stop-loss management system for position pyramiding
- **Drawdown Layering Strategy**: Automatically adds positions during drawdowns to improve average entry price
- **Trailing Stop Loss Strategy**: Manages a single position with automatic stop-loss adjustments as profit increases
- **Web-based UI**: Control the bot through an easy-to-use browser interface
- **Real-time Status Monitoring**: Track your account balance, open positions, and trading activity
- **Custom Indicator Support**: Upload and use your own TradingView Pine Script indicators (e.g., HWR.pine)
- **Multi-Symbol Trading**: Trade multiple currency pairs simultaneously
- **End of Week Closing**: Automatically closes profitable positions before the weekend (Saturday 12:00 AM Philippine Time) while letting positions in drawdown hit their set TP/SL

## Requirements

- Windows with MetaTrader 5 installed and configured
- Python 3.8 or higher
- Required Python packages (listed in requirements.txt)

## Installation

1. Clone or download this repository
2. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Make sure MetaTrader 5 is installed and running on your system

## Usage

1. Start the web interface:
   ```
   python app.py
   ```
2. Open your browser and navigate to `http://localhost:5000`
3. Configure your trading settings in the user interface
4. Click "Connect & Start Trading" to begin

## Strategy Settings

### Basic Settings
- **Symbol**: The currency pair or instrument to trade
- **Timeframe**: Trading timeframe (M1, M5, M15, H1, etc.)
- **Lot Size**: Size of each position
- **Stop Loss**: Maximum stop loss in pips
- **Take Profit**: Maximum take profit in pips
- **Trade Direction**: Choose between LONG, SHORT, or BOTH trading directions

### Progressive Lockin Strategy
This strategy manages a set of positions with progressive take profits:
- First position closes at a smaller profit (default: 20 pips)
- When first position closes, moves others to breakeven
- Second position closes at medium profit (default: 50 pips)
- When second position closes, third position stop loss moves to profit

### Drawdown Layering Strategy
This strategy helps manage drawdowns by adding positions:
- Automatically adds new positions at specified drawdown thresholds
- Adjusts take profit levels to ensure minimum profit for all positions
- Limits maximum number of layers to control risk

### End of Week Closing

The bot includes weekend risk management with the following behavior:

- **Profit Closing**: At Saturday 12:00 AM (midnight) Philippine Time, all positions in profit will be automatically closed to protect weekend gains
- **Drawdown Handling**: Positions in drawdown will be kept open to allow recovery and will hit their predetermined TP/SL levels

This feature helps protect your profits before weekend market gaps while giving underwater positions a chance to recover.

## Trailing Stop Loss Strategy

The Trailing Stop Loss Strategy is designed for traders who prefer a more conservative approach with just one position at a time. This strategy focuses on protecting profits by automatically adjusting stop loss levels as the trade moves in your favor.

### Key Features:

1. **Single Position Trading**: Only allows one active trade position at a time.
2. **Initial Parameters**:
   - Sets initial Stop Loss at 30 pips
   - Sets Take Profit at 90 pips
3. **Automated Stop Loss Adjustments**:
   - When profit reaches 30 pips: Moves SL to breakeven (entry price)
   - When profit reaches 60 pips: Moves SL to lock in 30 pips profit
4. **Precise Execution**: All SL movements are calculated and executed automatically with detailed logs for review.

This strategy is ideal for traders who want to minimize risk while still capturing significant market moves. When enabled, the Trailing Stop Loss Strategy takes precedence over other strategies and restricts the bot to opening only a single position regardless of the "Positions Per Setup" setting.

## Disclaimer

Trading forex and other financial instruments carries significant risk. This software is provided for educational and informational purposes only. Use at your own risk.

## License

This project is private and not licensed for redistribution. 