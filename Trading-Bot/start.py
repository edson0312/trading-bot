import argparse
import sys
import os

def check_mt5_installed():
    """Check if MetaTrader5 package is installed and available"""
    try:
        import MetaTrader5
        return True
    except ImportError:
        return False

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_packages = [
        'MetaTrader5', 'pandas', 'numpy', 'pytz',
        'matplotlib', 'tkinter'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    return missing_packages

def install_dependencies():
    """Install required dependencies"""
    import subprocess
    
    print("Installing required dependencies...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError:
        print("Failed to install dependencies.")
        return False

def main():
    """Main function to start the bot in different modes"""
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='FVG Trading Bot')
    parser.add_argument('--mode', choices=['bot', 'backtest', 'dashboard', 'visualize'], 
                        default='bot', help='Mode to run: bot, backtest, dashboard, or visualize')
    parser.add_argument('--install-deps', action='store_true', 
                        help='Install dependencies before running')
    parser.add_argument('--symbol', type=str, default='EURUSD',
                        help='Symbol to trade (default: EURUSD)')
    parser.add_argument('--timeframe', type=str, default='M15',
                        help='Timeframe to use: M1, M5, M15, M30, H1, H4, D1 (default: M15)')
    parser.add_argument('--lot-size', type=float, default=0.01,
                        help='Lot size for trading (default: 0.01)')
    
    args = parser.parse_args()
    
    # Check for dependencies
    if args.install_deps:
        install_dependencies()
    
    missing_packages = check_dependencies()
    
    if missing_packages:
        print(f"Missing required packages: {', '.join(missing_packages)}")
        install = input("Would you like to install them now? (y/n): ")
        
        if install.lower() == 'y':
            if install_dependencies():
                print("Restarting application...")
                # Restart the script to use newly installed packages
                os.execv(sys.executable, ['python'] + sys.argv)
            else:
                print("Exiting due to missing dependencies.")
                sys.exit(1)
        else:
            print("Exiting due to missing dependencies.")
            sys.exit(1)
    
    # Import here to ensure dependencies are installed
    from config import SYMBOL, TIMEFRAME
    import MetaTrader5 as mt5
    
    # Update configuration based on command-line arguments
    if args.symbol:
        from trading_bot import SYMBOL as bot_symbol
        globals()['SYMBOL'] = args.symbol
        bot_symbol = args.symbol
    
    if args.timeframe:
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1
        }
        
        if args.timeframe in timeframe_map:
            from trading_bot import TIMEFRAME as bot_timeframe
            globals()['TIMEFRAME'] = timeframe_map[args.timeframe]
            bot_timeframe = timeframe_map[args.timeframe]
        else:
            print(f"Invalid timeframe: {args.timeframe}")
            print(f"Valid options are: {', '.join(timeframe_map.keys())}")
            sys.exit(1)
    
    if args.lot_size:
        from trading_bot import LOT_SIZE as bot_lot_size
        bot_lot_size = args.lot_size
    
    # Run in selected mode
    if args.mode == 'bot':
        print(f"Starting trading bot for {SYMBOL} on {args.timeframe} timeframe...")
        from trading_bot import run_trading_bot
        run_trading_bot()
    
    elif args.mode == 'backtest':
        print(f"Running backtest for {SYMBOL} on {args.timeframe} timeframe...")
        from backtest import run_backtest
        run_backtest()
    
    elif args.mode == 'dashboard':
        print(f"Starting dashboard for {SYMBOL} on {args.timeframe} timeframe...")
        import tkinter as tk
        from dashboard import TradingBotDashboard
        root = tk.Tk()
        app = TradingBotDashboard(root)
        root.mainloop()
    
    elif args.mode == 'visualize':
        print(f"Visualizing backtest results for {SYMBOL} on {args.timeframe} timeframe...")
        from visualize_results import visualize_backtest_results
        visualize_backtest_results()

if __name__ == "__main__":
    main() 