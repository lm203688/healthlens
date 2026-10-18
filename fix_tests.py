import re, os, glob

test_dir = "/opt/healthlens/tests/api"
fixed = 0

for fpath in sorted(glob.glob(f"{test_dir}/test_*.py")):
    if ".bak-" in fpath:
        continue
    with open(fpath) as f:
        content = f.read()
    
    original = content
    
    # Fix 1: Replace function signatures (client, test_user_data) -> (client, login_token)
    content = content.replace("(client, test_user_data)", "(client, login_token)")
    
    # Fix 2: Remove register block, replace with login_token usage
    # Pattern: register_resp = ... if ... skip ... login_resp = ... token = ...
    content = re.sub(
        r'register_resp = await client\.post\("/api/v1/auth/register", json=test_user_data\)\n\s+if register_resp\.status_code not in \(200, 201\):\n\s+pytest\.skip\("Registration failed"\)\n\s+login_resp = await client\.post\("/api/v1/auth/login", json=test_user_data\)\n\s+token = login_resp\.json\(\)\["data"\]\["access_token"\]\n',
        '',
        content
    )
    
    # Fix 3: Replace token extraction patterns
    content = content.replace(
        'token = login_resp.json()["data"]["access_token"]',
        'token = login_token'
    )
    content = content.replace(
        'token = login_resp.json()["data"].get("access_token")',
        'token = login_token'
    )
    content = content.replace(
        'token = login_resp.json()["data"]  ',
        'token = login_token'
    )
    
    # Fix 4: Remove leftover login_resp lines
    content = content.replace(
        'login_resp = await client.post("/api/v1/auth/login", json=test_user_data)\n',
        ''
    )
    
    # Fix 5: If login_token is used, remove test_user_data from signature if not needed
    if 'login_token' in content and 'test_user_data' not in content:
        pass  # Already fixed in step 1
    
    if content != original:
        with open(fpath, 'w') as f:
            f.write(content)
        fixed += 1
        print(f"Fixed: {os.path.basename(fpath)}")

print(f"\nTotal fixed: {fixed} files")
