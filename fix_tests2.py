import re, os, glob

test_dir = "/opt/healthlens/tests/api"
fixed = 0

for fpath in sorted(glob.glob(f"{test_dir}/test_*.py")):
    if ".bak-" in fpath:
        continue
    with open(fpath) as f:
        lines = f.readlines()
    
    new_lines = []
    i = 0
    changed = False
    
    while i < len(lines):
        line = lines[i]
        
        # Fix: extra indentation on headers line (8 spaces -> 4 spaces)
        if line.startswith('        headers = {"Authorization": f"Bearer {token}"}'):
            new_lines.append('    headers = {"Authorization": f"Bearer {login_token}"}\n')
            changed = True
            i += 1
            continue
        
        # Fix: extra indentation on headers line with different quote style
        if line.startswith('        headers = {"Authorization": f"Bearer {token}"'):
            new_lines.append('    headers = {"Authorization": f"Bearer {login_token}"}\n')
            changed = True
            i += 1
            continue
        
        # Fix: any remaining Bearer {token} references
        if 'Bearer {token}' in line:
            line = line.replace('Bearer {token}', 'Bearer {login_token}')
            changed = True
        
        new_lines.append(line)
        i += 1
    
    if changed:
        with open(fpath, 'w') as f:
            f.writelines(new_lines)
        fixed += 1
        print(f"Fixed: {os.path.basename(fpath)}")

print(f"\nTotal fixed: {fixed} files")
