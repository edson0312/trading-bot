import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from backtest import run_backtest
import os
from strategies.ace_strategy import calculate_smi, calculate_macd, calculate_macd_colors, calculate_adx

def visualize_backtest_results():
    # Run the backtest
    df, trades, final_balance = run_backtest()
    
    if df is None or not trades:
        print("No trades or data to visualize.")
        return
    
    # Create results directory if it doesn't exist
    os.makedirs('results', exist_ok=True)
    
    # Extract trade data
    trade_times = [trade['entry_time'] for trade in trades]
    trade_profits = [trade['profit'] for trade in trades]
    trade_types = [trade['type'] for trade in trades]
    
    # Calculate cumulative profit
    cumulative_profit = np.cumsum(trade_profits)
    
    # Create a DataFrame for easier plotting
    results_df = pd.DataFrame({
        'Time': trade_times,
        'Profit': trade_profits,
        'Type': trade_types,
        'Cumulative Profit': cumulative_profit
    })
    
    # Save results to CSV
    results_df.to_csv('results/backtest_results.csv', index=False)
    
    # Plot 1: Equity Curve
    plt.figure(figsize=(12, 6))
    plt.plot(results_df['Time'], results_df['Cumulative Profit'], 'b-', linewidth=2)
    plt.title('Equity Curve')
    plt.xlabel('Date')
    plt.ylabel('Cumulative Profit ($)')
    plt.grid(True)
    plt.savefig('results/equity_curve.png')
    plt.close()
    
    # Plot 2: Individual Trade Profits
    plt.figure(figsize=(12, 6))
    colors = ['green' if p > 0 else 'red' for p in results_df['Profit']]
    plt.bar(range(len(results_df)), results_df['Profit'], color=colors)
    plt.title('Individual Trade Profits')
    plt.xlabel('Trade Number')
    plt.ylabel('Profit ($)')
    plt.grid(True)
    plt.savefig('results/trade_profits.png')
    plt.close()
    
    # Plot 3: Win/Loss Distribution
    plt.figure(figsize=(10, 6))
    plt.hist(results_df['Profit'], bins=20, color='skyblue', edgecolor='black')
    plt.title('Profit/Loss Distribution')
    plt.xlabel('Profit ($)')
    plt.ylabel('Frequency')
    plt.grid(True)
    plt.savefig('results/profit_distribution.png')
    plt.close()
    
    # Plot 4: Monthly Returns
    results_df['Month'] = results_df['Time'].dt.to_period('M')
    monthly_profit = results_df.groupby('Month')['Profit'].sum()
    
    plt.figure(figsize=(12, 6))
    colors = ['green' if p > 0 else 'red' for p in monthly_profit]
    monthly_profit.plot(kind='bar', color=colors)
    plt.title('Monthly Returns')
    plt.xlabel('Month')
    plt.ylabel('Profit ($)')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig('results/monthly_returns.png')
    plt.close()
    
    # Plot 5: Win rate by trade type
    long_trades = results_df[results_df['Type'] == 'long']
    short_trades = results_df[results_df['Type'] == 'short']
    
    long_win_rate = (long_trades['Profit'] > 0).mean() * 100 if len(long_trades) > 0 else 0
    short_win_rate = (short_trades['Profit'] > 0).mean() * 100 if len(short_trades) > 0 else 0
    overall_win_rate = (results_df['Profit'] > 0).mean() * 100
    
    plt.figure(figsize=(8, 6))
    plt.bar(['Long', 'Short', 'Overall'], [long_win_rate, short_win_rate, overall_win_rate], color=['blue', 'orange', 'green'])
    plt.title('Win Rate by Trade Type')
    plt.ylabel('Win Rate (%)')
    plt.grid(True)
    plt.savefig('results/win_rate.png')
    plt.close()
    
    # Plot 6: ACE Strategy Indicators for a selected trading period
    visualize_ace_indicators(df, trades)
    
    # Generate summary statistics
    total_trades = len(results_df)
    profitable_trades = sum(1 for p in results_df['Profit'] if p > 0)
    losing_trades = total_trades - profitable_trades
    win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0
    
    avg_profit = results_df[results_df['Profit'] > 0]['Profit'].mean() if profitable_trades > 0 else 0
    avg_loss = results_df[results_df['Profit'] <= 0]['Profit'].mean() if losing_trades > 0 else 0
    
    profit_factor = abs(results_df[results_df['Profit'] > 0]['Profit'].sum() / 
                       results_df[results_df['Profit'] <= 0]['Profit'].sum()) if losing_trades > 0 else float('inf')
    
    max_drawdown = calculate_max_drawdown(cumulative_profit)
    
    # Write summary to text file
    with open('results/summary.txt', 'w') as f:
        f.write("=== BACKTEST SUMMARY ===\n\n")
        f.write(f"Total Trades: {total_trades}\n")
        f.write(f"Profitable Trades: {profitable_trades}\n")
        f.write(f"Losing Trades: {losing_trades}\n")
        f.write(f"Win Rate: {win_rate:.2f}%\n\n")
        
        f.write(f"Initial Balance: ${10000}\n")  # From backtest.py constants
        f.write(f"Final Balance: ${final_balance:.2f}\n")
        f.write(f"Total Profit/Loss: ${final_balance - 10000:.2f}\n")
        f.write(f"Return on Investment: {((final_balance - 10000) / 10000 * 100):.2f}%\n\n")
        
        f.write(f"Average Profit: ${avg_profit:.2f}\n")
        f.write(f"Average Loss: ${avg_loss:.2f}\n")
        f.write(f"Profit Factor: {profit_factor:.2f}\n")
        f.write(f"Maximum Drawdown: ${max_drawdown:.2f}\n\n")
        
        f.write("Long Trades Summary:\n")
        f.write(f"  Count: {len(long_trades)}\n")
        f.write(f"  Win Rate: {long_win_rate:.2f}%\n")
        f.write(f"  Total Profit: ${long_trades['Profit'].sum():.2f}\n\n")
        
        f.write("Short Trades Summary:\n")
        f.write(f"  Count: {len(short_trades)}\n")
        f.write(f"  Win Rate: {short_win_rate:.2f}%\n")
        f.write(f"  Total Profit: ${short_trades['Profit'].sum():.2f}\n")
    
    print("Visualization complete. Results saved to 'results' directory.")

def visualize_ace_indicators(df, trades):
    """Visualize ACE Strategy indicators for specific trades"""
    if not trades:
        return
    
    # Select a few trades to visualize (up to 5)
    sample_trades = trades[:min(5, len(trades))]
    
    for i, trade in enumerate(sample_trades):
        # Get 50 bars around the trade entry
        entry_time = trade['entry_time']
        entry_idx = df[df['time'] == entry_time].index[0]
        
        # Get 30 bars before and 20 bars after entry
        start_idx = max(0, entry_idx - 30)
        end_idx = min(len(df) - 1, entry_idx + 20)
        
        trade_window = df.iloc[start_idx:end_idx+1]
        
        # Calculate indicators
        smi, smi_ema = calculate_smi(trade_window)
        macd_line, signal_line, histogram = calculate_macd(trade_window)
        macd_colors = calculate_macd_colors(histogram.values)
        adx = calculate_adx(trade_window)
        
        # Create figure with 4 subplots
        fig, axs = plt.subplots(4, 1, figsize=(14, 12), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1, 1]})
        
        # Plot 1: Price and entry
        axs[0].set_title(f"Trade {i+1}: {trade['type'].upper()} at {entry_time}")
        
        # Candlestick chart
        up = trade_window.loc[trade_window['close'] >= trade_window['open']]
        down = trade_window.loc[trade_window['close'] < trade_window['open']]
        
        # Plot up candles
        width = 0.6
        axs[0].bar(up.index, up['close'] - up['open'], width, bottom=up['open'], color='green', alpha=0.5)
        axs[0].bar(up.index, up['high'] - up['close'], width/5, bottom=up['close'], color='green', alpha=0.5)
        axs[0].bar(up.index, up['low'] - up['open'], width/5, bottom=up['open'], color='green', alpha=0.5)
        
        # Plot down candles
        axs[0].bar(down.index, down['close'] - down['open'], width, bottom=down['open'], color='red', alpha=0.5)
        axs[0].bar(down.index, down['high'] - down['open'], width/5, bottom=down['open'], color='red', alpha=0.5)
        axs[0].bar(down.index, down['low'] - down['close'], width/5, bottom=down['close'], color='red', alpha=0.5)
        
        # Mark entry point
        entry_idx_local = trade_window[trade_window['time'] == entry_time].index[0]
        entry_price = trade_window.iloc[entry_idx_local]['close']
        axs[0].scatter(entry_idx_local, entry_price, marker='^' if trade['type'] == 'long' else 'v', 
                     color='blue', s=200, zorder=10)
        
        axs[0].set_ylabel('Price')
        axs[0].grid(True)
        
        # Plot 2: SMI and SMI EMA
        axs[1].plot(smi.index, smi, label='SMI', color='blue')
        axs[1].plot(smi_ema.index, smi_ema, label='SMI EMA', color='red')
        axs[1].axhline(y=40, color='green', linestyle='--', alpha=0.5, label='Overbought')
        axs[1].axhline(y=-40, color='red', linestyle='--', alpha=0.5, label='Oversold')
        axs[1].axhline(y=0, color='black', linestyle='-', alpha=0.2)
        axs[1].set_ylabel('SMI')
        axs[1].legend(loc='upper right')
        axs[1].grid(True)
        
        # Plot 3: MACD
        axs[2].plot(macd_line.index, macd_line, label='MACD', color='blue')
        axs[2].plot(signal_line.index, signal_line, label='Signal', color='red')
        
        # Plot histogram with color coding
        for j in range(1, len(histogram)):
            color = 'green'
            if macd_colors[j] == 1:  # Dark green
                color = 'darkgreen'
            elif macd_colors[j] == 2:  # Light green
                color = 'lightgreen'
            elif macd_colors[j] == 3:  # Dark red
                color = 'darkred'
            elif macd_colors[j] == 4:  # Light red
                color = 'salmon'
                
            axs[2].bar(histogram.index[j], histogram.iloc[j], color=color, alpha=0.6)
            
        axs[2].axhline(y=0, color='black', linestyle='-', alpha=0.2)
        axs[2].set_ylabel('MACD')
        axs[2].legend(loc='upper right')
        axs[2].grid(True)
        
        # Plot 4: ADX
        axs[3].plot(adx.index, adx, label='ADX', color='purple')
        axs[3].axhline(y=12, color='red', linestyle='--', alpha=0.5, label='Trend Threshold')
        axs[3].set_ylabel('ADX')
        axs[3].legend(loc='upper right')
        axs[3].grid(True)
        
        # X-axis formatting
        axs[3].set_xlabel('Bar Index')
        
        plt.tight_layout()
        plt.savefig(f'results/trade_{i+1}_indicators.png')
        plt.close(fig)

def calculate_max_drawdown(equity_curve):
    """Calculate the maximum drawdown from peak to trough."""
    max_so_far = equity_curve[0]
    drawdowns = []
    
    for value in equity_curve:
        if value > max_so_far:
            max_so_far = value
        drawdown = max_so_far - value
        drawdowns.append(drawdown)
    
    return max(drawdowns) if drawdowns else 0

if __name__ == "__main__":
    visualize_backtest_results() 