import re
import os

def fix_indentation():
    # Read the original file
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Create fixed lines
    fixed_lines = []
    in_class = False
    in_function = False
    current_indent = 0
    base_indent = 4  # Standard 4 spaces indentation
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines, keep as-is
        if not stripped:
            fixed_lines.append(line)
            continue
        
        # Handle class definition
        if line.lstrip().startswith('class ') and ':' in line:
            in_class = True
            current_indent = 0
            fixed_lines.append(line)
            continue
        
        # Handle function definition inside class
        if in_class and line.lstrip().startswith('def ') and ':' in line:
            in_function = True
            current_indent = base_indent
            fixed_line = ' ' * current_indent + line.lstrip()
            fixed_lines.append(fixed_line)
            continue
        
        # Handle function definition outside class
        if not in_class and line.lstrip().startswith('def ') and ':' in line:
            in_function = True
            current_indent = 0
            fixed_lines.append(line)
            continue
        
        # Handle route decorators
        if line.lstrip().startswith('@app.route'):
            in_class = False
            in_function = False
            current_indent = 0
            fixed_lines.append(line)
            continue
        
        # Check indentation for lines in functions inside class
        if in_class and in_function:
            # Special handling for try/except/finally blocks
            if stripped.startswith(('try:', 'except', 'finally:')):
                fixed_line = ' ' * (current_indent) + line.lstrip()
                fixed_lines.append(fixed_line)
                continue
                
            # Increase indentation for blocks inside functions
            if stripped.endswith(':'):
                fixed_line = ' ' * (current_indent) + line.lstrip()
                fixed_lines.append(fixed_line)
                continue
                
            # Regular line in function
            fixed_line = ' ' * (current_indent + base_indent) + line.lstrip()
            fixed_lines.append(fixed_line)
            continue
        
        # Keep other lines as-is
        fixed_lines.append(line)
    
    # Write the fixed file
    with open('app_fixed.py', 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print("Created fixed file: app_fixed.py")
    print("Please review it before replacing the original.")

if __name__ == "__main__":
    # Make sure we're in the right directory
    if not os.path.exists('app.py'):
        print("Error: app.py not found in current directory")
        print("Please run this script from the Trading-Bot directory")
        exit(1)
        
    fix_indentation()
    print("Done! Please check app_fixed.py and if it looks good, you can replace app.py with it.") 