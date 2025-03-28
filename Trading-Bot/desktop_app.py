"""
Trading Bot Desktop Application
This script creates a desktop application wrapper around the web-based trading bot.
"""

import os
import sys
import threading
import webview
import subprocess
import psutil
from app import app

def run_flask():
    """Run the Flask application in a separate thread"""
    app.run(host='127.0.0.1', port=5000, debug=False)

def find_port_process(port):
    """Find if a process is using the specified port"""
    for proc in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            for conn in proc.connections():
                if conn.laddr.port == port:
                    return proc
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return None

def main():
    """Main entry point for the application"""
    print("Starting Trading Bot Desktop Application...")
    
    # Check if port 5000 is already in use
    process = find_port_process(5000)
    if process:
        print(f"Port 5000 is already in use by process {process.name()} (PID: {process.pid})")
        print("Attempting to terminate the process...")
        try:
            process.terminate()
            process.wait(5)
            print("Process terminated successfully")
        except Exception as e:
            print(f"Error terminating process: {e}")
            print("Please close any applications using port 5000 and try again.")
            return
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Create the window title
    window_title = "MT5 Multi-Instance Trading Bot"
    
    # Set window size based on screen resolution
    window = webview.create_window(
        window_title, 
        'http://127.0.0.1:5000',
        width=1200, 
        height=900,
        min_size=(800, 600),
        resizable=True,
        text_select=True,
        confirm_close=True
    )
    
    # Start the WebView application
    webview.start(debug=False)

if __name__ == "__main__":
    main() 