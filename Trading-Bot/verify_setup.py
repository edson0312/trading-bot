import os
import sys
import subprocess
import time
import importlib.util
import platform

def check_requirements():
    """Check if required packages are installed"""
    missing_packages = []
    required_packages = [
        "flask", "pandas", "numpy", "MetaTrader5", "psutil", "pytz", "websockets"
    ]
    
    print("\n🔍 Checking required Python packages...")
    
    for package in required_packages:
        if importlib.util.find_spec(package) is None:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        return False
    else:
        print("✅ All required packages are installed")
        return True

def install_requirements():
    """Install required packages"""
    try:
        print("\n📦 Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Successfully installed required packages")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install required packages")
        return False

def check_mt5():
    """Check if MetaTrader 5 is installed and accessible"""
    print("\n🔍 Checking MetaTrader 5 installation...")
    
    # First try importing MT5
    try:
        import MetaTrader5 as mt5
        print(f"✅ MetaTrader5 module found (version: {mt5.__version__})")
    except ImportError:
        print("❌ MetaTrader5 module not found. Please install it using 'pip install MetaTrader5'")
        return False
    
    # Check if MT5 is installed
    mt5_terminal_paths = [
        os.getenv('MT5_PATH'),
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal.exe",
        r"C:\Program Files\MetaQuotes\terminal64.exe",
        r"C:\MT5\terminal64.exe"
    ]
    
    mt5_found = False
    valid_path = None
    
    for path in mt5_terminal_paths:
        if path and os.path.exists(path):
            mt5_found = True
            valid_path = path
            break
    
    if mt5_found:
        print(f"✅ MetaTrader 5 terminal found at: {valid_path}")
    else:
        print("❌ MetaTrader 5 terminal not found. Please install MT5 or set the MT5_PATH environment variable.")
        return False
    
    # Check if MT5 can be initialized
    try:
        if mt5.initialize():
            print("✅ Successfully connected to MetaTrader 5")
            account_info = mt5.account_info()
            if account_info:
                print(f"   Account: {account_info.login} ({account_info.server})")
                print(f"   Balance: {account_info.balance}")
                print(f"   Leverage: 1:{account_info.leverage}")
            
            # Check a common symbol
            symbols = ["EURUSD", "GBPUSD", "XAUUSD"]
            symbol_found = False
            
            for symbol in symbols:
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info and symbol_info.visible:
                    print(f"✅ Symbol {symbol} is available for trading")
                    symbol_found = True
                    break
            
            if not symbol_found:
                print("⚠️ No common trading symbols found. Make sure to enable symbols in MT5.")
            
            mt5.shutdown()
            return True
        else:
            print("❌ Failed to initialize MetaTrader 5. Error code:", mt5.last_error())
            return False
    except Exception as e:
        print(f"❌ Error connecting to MetaTrader 5: {e}")
        return False

def check_files():
    """Check if important files exist"""
    print("\n🔍 Checking required files...")
    
    required_files = [
        "app.py",
        "custom_indicators.py",
        "requirements.txt",
        "run.bat"
    ]
    
    optional_files = [
        "strategies/ace_strategy.py",
        "strategies/wavebf_strategy.py",
        "templates/index.html",
        "static/js/main.js",
        "uploaded_indicators/HWR.pine"
    ]
    
    # Check required files
    missing_required = []
    for file in required_files:
        if not os.path.exists(file):
            missing_required.append(file)
    
    # Check optional files
    missing_optional = []
    for file in optional_files:
        if not os.path.exists(file):
            missing_optional.append(file)
    
    if missing_required:
        print(f"❌ Missing required files: {', '.join(missing_required)}")
        return False
    else:
        print("✅ All required files are present")
        
    if missing_optional:
        print(f"⚠️ Missing some optional files: {', '.join(missing_optional)}")
    else:
        print("✅ All optional files are present")
    
    return len(missing_required) == 0

def check_folders():
    """Check if important folders exist and create them if needed"""
    print("\n🔍 Checking required folders...")
    
    folders = [
        "strategies",
        "templates",
        "static",
        "static/js",
        "uploaded_indicators",
    ]
    
    for folder in folders:
        if not os.path.exists(folder):
            print(f"📁 Creating folder: {folder}")
            os.makedirs(folder, exist_ok=True)
    
    print("✅ All required folders are present")
    return True

def check_system():
    """Check system information"""
    print("\n🔍 System Information:")
    print(f"   OS: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"   Python: {platform.python_version()}")
    print(f"   Architecture: {platform.architecture()[0]}")
    
    # Check if running on Windows
    if platform.system() != "Windows":
        print("⚠️ Warning: This application is designed for Windows. Some features may not work on other platforms.")
    
    # Check Python version
    python_version = tuple(map(int, platform.python_version_tuple()))
    if python_version < (3, 7, 0):
        print("⚠️ Warning: Python 3.7 or higher is recommended. You're running Python {}.{}.{}".format(*python_version))
    else:
        print("✅ Python version is compatible")

def run_verification():
    """Run all verification checks"""
    print("=" * 60)
    print("MT5 Multi-Instance Trading Bot - System Verification")
    print("=" * 60)
    
    # Check system
    check_system()
    
    # Check folders
    check_folders()
    
    # Check files
    files_ok = check_files()
    if not files_ok:
        print("\n⚠️ Some required files are missing. The application may not work correctly.")
    
    # Check requirements
    requirements_ok = check_requirements()
    if not requirements_ok:
        print("\nInstalling missing requirements...")
        install_requirements()
        # Check again after installation
        requirements_ok = check_requirements()
    
    # Check MT5
    mt5_ok = check_mt5()
    
    print("\n" + "=" * 60)
    if files_ok and requirements_ok and mt5_ok:
        print("✅ All checks passed! The system is ready to run.")
        print("   You can start the application by running 'run.bat' or 'python app.py'")
    else:
        print("⚠️ Some checks failed. Please resolve the issues before running the application.")
    print("=" * 60)

if __name__ == "__main__":
    run_verification() 