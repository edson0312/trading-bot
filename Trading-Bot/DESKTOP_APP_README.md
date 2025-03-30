# MT5 Trading Bot Desktop Application

This is a desktop application for the MT5 Trading Bot. It provides the same functionality as the web application but in a convenient desktop format.

## Requirements

- Windows 10 or later
- Python 3.8 or later
- MetaTrader 5 installed on your computer

## Building the Desktop Application

There are two ways to build the desktop application:

### Option 1: Using the master build script (Recommended)

1. Open a Command Prompt or PowerShell window
2. Navigate to the trading bot directory
3. Run the master build script:
   ```
   build_all.bat
   ```
4. The script will:
   - Create a virtual environment
   - Install all required packages
   - Build the desktop application
   - Create an installer

### Option 2: Manual build process

1. Install the required packages:
   ```
   pip install -r requirements.txt
   pip install pywebview pyinstaller
   ```

2. Build the desktop application:
   ```
   build_desktop_app.bat
   ```

3. (Optional) Create an installer:
   ```
   create_installer.bat
   ```

## Running the Application

### From the build directory

1. Navigate to `dist\TradingBot`
2. Run `TradingBot.exe`

### From the installer

1. Run the installer (`TradingBot_Setup.exe`)
2. Follow the installation instructions
3. Launch the application from the Start Menu or desktop shortcut

## Features

- Multi-instance MT5 trading support
- Custom indicator support
- Advanced risk management strategies
- Modern, user-friendly interface
- Automatic MetaTrader 5 launching
- Custom indicators (Pine Script v4, v5, and v6 support)

## Default Settings

- Default server: MetaQuotes-Demo
- Default indicator: HWR.pine
- Stop Loss: Uses the value you set in "Max Stop Loss (points)"

## Notes

- Make sure MetaTrader 5 is installed and can be found in one of the standard installation locations
- For best results, log in to your MT5 account before starting the application
- The first instance (Instance 1) will automatically attempt to launch MT5 if it's not already running 