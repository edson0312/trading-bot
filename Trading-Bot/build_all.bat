@echo off
echo MT5 Trading Bot - Master Build Script
echo ====================================
echo.

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python not found. Please install Python 3.8 or later.
    exit /b 1
)

REM Get Python version
for /f "tokens=2" %%I in ('python --version 2^>^&1') do set PYTHON_VERSION=%%I
echo Using Python version: %PYTHON_VERSION%
echo.

REM Create a virtual environment
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

REM Create an icon file if it doesn't exist
if not exist "static\favicon.ico" (
    echo Creating icon file...
    mkdir static 2>nul
    echo Create favicon.ico manually and place it in the static folder for better appearance.
)

REM Build desktop application
echo.
echo Building desktop application...
call build_desktop_app.bat

REM Create installer
echo.
echo Creating installer...
call create_installer.bat

REM Deactivate virtual environment
call venv\Scripts\deactivate

echo.
echo ====================================
echo Build process complete!
echo.
echo The installer is available at: TradingBot_Setup.exe
echo.
echo To run the application without installing:
echo 1. Navigate to dist\TradingBot
echo 2. Run TradingBot.exe
echo.
echo To distribute the application:
echo 1. Share the TradingBot_Setup.exe file with your users
echo 2. They can install it by running the setup file
echo ==================================== 