"""Comprehensive fix for test files after login_token migration"""
import re, os, glob

test_dir = "/opt/healthlens/tests/api"
fixed = 0

for fpath in sorted(glob.glob(f"{test_dir}/test_*.py")):
    if ".bak-" in fpath:
        continue
    with open(fpath) as f:
        content = f.read()
    
    original = content
    
    # Pattern 1: Remove incomplete register+login remnants
    # Match: register_resp = ... if ... {if login_resp... token = login_token else...} else...
    content = re.sub(
        r'register_resp = await client\.post\("/api/v1/auth/register", json=test_user_data\)\n'
        r'\s+if register_resp\.status_code(?: in| not in) \(200, 201\):\n'
        r'(?:\s+if login_resp\.status_code == 200:\n)?\s+'
        r'(?:token = login_token\n)?\s+'
        r'(?:else:\n\s+pytest\.skip\("Login failed"\)\n)?\s*'
        r'(?:else:\n\s+pytest\.skip\("Registration failed"\)\n)?',
        '',
        content
    )
    
    # Pattern 2: Remove simpler register+login blocks
    content = re.sub(
        r'register_resp = await client\.post\("/api/v1/auth/register", json=test_user_data\)\n'
        r'\s+if register_resp\.status_code not in \(200, 201\):\n'
        r'\s+pytest\.skip\("Registration failed"\)\n'
        r'\s+login_resp = await client\.post\("/api/v1/auth/login", json=test_user_data\)\n'
        r'\s+token = login_resp\.json\(\)\["data"\]\["access_token"\]\n',
        '',
        content
    )
    
    # Pattern 3: Remove orphaned token = login_token lines with wrong indent
    content = re.sub(
        r'\n\s+token = login_token\n',
        '\n',
        content
    )
    
    # Pattern 4: Remove orphaned login_resp lines
    content = re.sub(
        r'\n\s+login_resp = await client\.post\("/api/v1/auth/login".*\n',
        '\n',
        content
    )
    
    # Pattern 5: Remove orphaned register_resp lines
    content = re.sub(
        r'\n\s+register_resp = await client\.post\("/api/v1/auth/register".*\n',
        '\n',
        content
    )
    
    # Pattern 6: Remove orphaned pytest.skip("Registration failed") lines
    content = re.sub(
        r'\n\s+pytest\.skip\("Registration failed"\)\n',
        '\n',
        content
    )
    
    # Pattern 7: Remove orphaned pytest.skip("Login failed") lines
    content = re.sub(
        r'\n\s+pytest\.skip\("Login failed"\)\n',
        '\n',
        content
    )
    
    # Pattern 8: Remove orphaned if/else blocks
    content = re.sub(
        r'\n\s+if register_resp\.status_code[^\n]*\n',
        '\n',
        content
    )
    content = re.sub(
        r'\n\s+if login_resp\.status_code[^\n]*\n',
        '\n',
        content
    )
    content = re.sub(
        r'\n\s+else:\n',
        '\n',
        content
    )
    
    # Fix: Clean up multiple blank lines
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    # Fix: Ensure proper indentation for remaining code
    # Lines that should have 4-space indent but have 8
    content = re.sub(
        r'\n        (headers = .*?)(?=\n)',
        r'\n    \1',
        content
    )
    
    if content != original:
        with open(fpath, 'w') as f:
            f.write(content)
        fixed += 1
        print(f"Fixed: {os.path.basename(fpath)}")

print(f"\nTotal fixed: {fixed} files")
