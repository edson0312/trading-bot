@echo off
echo Building MT5 Trading Bot Desktop Application...

REM Install required packages if not already installed
echo Installing required packages...
pip install -r requirements.txt
pip install pywebview pyinstaller

REM Create a spec file for PyInstaller
echo Creating PyInstaller spec file...

echo from PyInstaller.utils.hooks import collect_data_files, collect_submodules > trading_bot.spec
echo import sys >> trading_bot.spec
echo import os >> trading_bot.spec
echo datas = [] >> trading_bot.spec
echo datas += collect_data_files('flask') >> trading_bot.spec
echo datas += [('templates', 'templates'), ('static', 'static'), ('uploaded_indicators', 'uploaded_indicators'), ('strategies', 'strategies')] >> trading_bot.spec
echo hiddenimports = collect_submodules('flask') + collect_submodules('MetaTrader5') + collect_submodules('pandas') + ['psutil', 'pytz', 'webview'] >> trading_bot.spec
echo a = Analysis(['desktop_app.py'], pathex=['.'], binaries=[], datas=datas, hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[], excludes=[], win_no_prefer_redirects=False, win_private_assemblies=False) >> trading_bot.spec
echo pyz = PYZ(a.pure, a.zipped_data) >> trading_bot.spec
echo exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, name='TradingBot', debug=False, strip=False, upx=True, console=True, icon='static/favicon.ico') >> trading_bot.spec
echo coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True, name='TradingBot') >> trading_bot.spec

REM Build the application
echo Building the application...
pyinstaller --clean trading_bot.spec

REM Copy additional files to the dist folder
echo Copying additional files...
if not exist "dist\TradingBot\uploaded_indicators" mkdir "dist\TradingBot\uploaded_indicators"
if not exist "dist\TradingBot\strategies" mkdir "dist\TradingBot\strategies"
copy "uploaded_indicators\*.*" "dist\TradingBot\uploaded_indicators\"
copy "strategies\*.*" "dist\TradingBot\strategies\"

echo Creating README file...
echo MT5 Trading Bot Desktop Application > "dist\TradingBot\README.txt"
echo ------------------------------------ >> "dist\TradingBot\README.txt"
echo This is a desktop application for the MT5 Trading Bot. >> "dist\TradingBot\README.txt"
echo. >> "dist\TradingBot\README.txt"
echo Instructions: >> "dist\TradingBot\README.txt"
echo 1. Make sure MetaTrader 5 is installed on your computer. >> "dist\TradingBot\README.txt"
echo 2. Run TradingBot.exe to start the application. >> "dist\TradingBot\README.txt"
echo 3. Configure your MT5 instances and connect to start trading. >> "dist\TradingBot\README.txt"

echo Creating launcher script...
echo @echo off > "dist\TradingBot\Start Trading Bot.bat"
echo start TradingBot.exe >> "dist\TradingBot\Start Trading Bot.bat"

echo Build complete! The application is in the dist\TradingBot folder.
echo To run the application, go to dist\TradingBot and run "TradingBot.exe" 