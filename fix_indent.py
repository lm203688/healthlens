"""Fix test files: correct indentation and variable names after login_token migration"""
import re, os, glob

test_dir = "/opt/healthlens/tests/api"
fixed = 0

for fpath in sorted(glob.glob(f"{test_dir}/test_*.py")):
    if ".bak-" in fpath:
        continue
    with open(fpath) as f:
        lines = f.readlines()
    
    new_lines = []
    changed = False
    
    for line in lines:
        # Fix 1: Indentation - 8 spaces -> 4 spaces for headers line
        if line.startswith('        headers = {"Authorization":'):
            # Replace 8 spaces with 4, and token -> login_token
            indent = '    '
            rest = line.strip()
            rest = rest.replace('Bearer {token}', 'Bearer {login_token}')
            new_lines.append(indent + rest + '\n')
            changed = True
            continue
        
        # Fix 2: Any remaining Bearer {token} -> Bearer {login_token}
        if 'Bearer {token}' in line and 'Bearer {login_token}' not in line:
            line = line.replace('Bearer {token}', 'Bearer {login_token}')
            changed = True
        
        new_lines.append(line)
    
    if changed:
        with open(fpath, 'w') as f:
            f.writelines(new_lines)
        fixed += 1
        print(f"Fixed: {os.path.basename(fpath)}")

print(f"\nTotal fixed: {fixed} files")
