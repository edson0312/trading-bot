#!/usr/bin/env python
import os
import shutil
import sys

# Required core files
REQUIRED_FILES = [
    "app.py",
    "custom_indicators.py",
    "requirements.txt",
    "run.bat",
    "verify_setup.py",
    "cleanup.py",
    "config.py",
    "README.md",
    "VERSION.txt"
]

# Required directories with their essential files
REQUIRED_DIRS = {
    "strategies": ["ace_strategy.py", "wavebf_strategy.py", "__init__.py"],
    "templates": ["index.html"],
    "static": [],
    "static/js": ["main.js"],
    "uploaded_indicators": ["README.md"]
}

def print_header(message):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(message)
    print("=" * 60)

def print_status(message, success=True):
    """Print a status message with an icon"""
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

def confirm_action(message="Do you want to continue?"):
    """Ask for user confirmation"""
    response = input(f"{message} (y/n): ").strip().lower()
    return response == 'y' or response == 'yes'

def create_backup():
    """Create a backup of the current project"""
    import datetime
    import zipfile
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"trading_bot_backup_{timestamp}.zip"
    
    print_status(f"Creating backup: {backup_filename}", True)
    
    with zipfile.ZipFile(backup_filename, 'w') as zipf:
        for root, dirs, files in os.walk('.'):
            # Skip __pycache__ directories and the backup itself
            if '__pycache__' in root or backup_filename in root:
                continue
            
            for file in files:
                if file != backup_filename:
                    file_path = os.path.join(root, file)
                    arcname = file_path[2:]  # Remove './' from the beginning
                    zipf.write(file_path, arcname)
    
    print_status(f"Backup created successfully: {os.path.abspath(backup_filename)}", True)
    return backup_filename

def cleanup_files():
    """Remove unnecessary files and keep only the essential ones"""
    removed_files = []
    kept_files = []
    
    # Walk through all files and directories
    for root, dirs, files in os.walk('.'):
        # Skip root level items in required list
        if root == '.':
            for file in files:
                if file in REQUIRED_FILES:
                    kept_files.append(file)
                elif not file.endswith('.zip') and not file.startswith('.'):  # Skip backups and hidden files
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    removed_files.append(file_path)
            continue
        
        # Process subdirectories
        rel_path = root[2:]  # Remove './' from the beginning
        
        # If this is a required directory
        if rel_path in REQUIRED_DIRS or any(rel_path.startswith(d + os.sep) for d in REQUIRED_DIRS):
            # Get parent directory if it's a subdirectory
            parent_dir = rel_path.split(os.sep)[0]
            
            # Keep required files, delete others
            for file in files:
                file_path = os.path.join(root, file)
                
                # Special case for uploaded_indicators - keep all .pine files
                if parent_dir == "uploaded_indicators" and file.endswith('.pine'):
                    kept_files.append(file_path)
                    continue
                
                # If it's a directly specified required file
                if parent_dir in REQUIRED_DIRS and file in REQUIRED_DIRS[parent_dir]:
                    kept_files.append(file_path)
                else:
                    os.remove(file_path)
                    removed_files.append(file_path)
        else:
            # Not a required directory, remove all files
            for file in files:
                file_path = os.path.join(root, file)
                if not file_path.endswith('.zip'):  # Skip backup files
                    os.remove(file_path)
                    removed_files.append(file_path)
    
    # Now remove empty directories that aren't required
    for root, dirs, files in os.walk('.', topdown=False):  # Use topdown=False to process child dirs first
        rel_path = root[2:]  # Remove './' from the beginning
        
        # Skip the root and required directories
        if rel_path and rel_path not in REQUIRED_DIRS and not any(rel_path.startswith(d + os.sep) for d in REQUIRED_DIRS):
            if not os.listdir(root):  # If directory is empty
                os.rmdir(root)
                removed_files.append(root + '/')
    
    # Check if any required directory is missing, create it
    for dir_name in REQUIRED_DIRS:
        dir_path = dir_name
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            print_status(f"Created missing directory: {dir_path}")
    
    # Create __init__.py files in Python directories if missing
    for dir_name in ["strategies"]:
        init_file = os.path.join(dir_name, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                f.write("# This file marks this directory as a Python package\n")
            print_status(f"Created missing file: {init_file}")
    
    # Report
    print_header("Cleanup Results")
    print(f"Kept {len(kept_files)} essential files")
    print(f"Removed {len(removed_files)} unnecessary files and directories")
    
    return removed_files, kept_files

def remove_pycache():
    """Remove all __pycache__ directories"""
    removed = []
    
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            shutil.rmtree(pycache_path)
            removed.append(pycache_path)
    
    if removed:
        print_status(f"Removed {len(removed)} __pycache__ directories")
    else:
        print_status("No __pycache__ directories found")
    
    return removed

def main():
    print_header("MT5 Multi-Instance Trading Bot - Cleanup Tool")
    print("This tool will remove unnecessary files and keep only the essential ones.")
    print("A backup will be created before any changes are made.")
    
    if not confirm_action():
        print("Cleanup cancelled.")
        return
    
    # Create backup
    backup_file = create_backup()
    
    # Remove __pycache__ directories
    remove_pycache()
    
    # Confirm before proceeding with main cleanup
    print("\nReady to remove unnecessary files.")
    if not confirm_action():
        print("Cleanup cancelled.")
        return
    
    # Cleanup files
    removed_files, kept_files = cleanup_files()
    
    print_header("Cleanup Complete")
    print(f"Backup file: {backup_file}")
    print("The project now contains only the essential files needed to run.")

if __name__ == "__main__":
    main() 