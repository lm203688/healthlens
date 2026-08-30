#!/usr/bin/env python3
"""HealthLens Creem支付完整部署脚本
在服务器WebShell中执行: python3 deploy_creem_full.py
功能: 部署4个后端文件 + 配置API Key + 重启容器
"""
import os, sys, subprocess, json, base64, zipfile, io, time

API_KEY = "creem_4yM8aDDK17QiHjWdiWgQEA"

# base64编码的zip文件，包含4个后端文件
B64_ZIP = "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"

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def find_project():
    for d in ["/root/healthlens", "/opt/healthlens", "/home/healthlens"]:
        if os.path.exists(os.path.join(d, "docker-compose.yml")):
            return d
    out, _, _ = run("find / -maxdepth 4 -name 'docker-compose.yml' -path '*/healthlens/*' 2>/dev/null | head -1")
    if out:
        return os.path.dirname(out.strip())
    print("[ERROR] 未找到项目目录"); sys.exit(1)

def main():
    print("=" * 50)
    print("  HealthLens Creem 支付完整部署")
    print("=" * 50)

    project = find_project()
    print(f"\n[1/5] 项目目录: {project}")

    # 2. 解码并写入后端文件
    print("\n[2/5] 部署后端文件...")
    zip_bytes = base64.b64decode(B64_ZIP)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

    file_map = {
        "creem_pay_service.py": "app/services/creem_pay_service.py",
        "payment.py": "app/api/payment.py",
        "tiered_growth.py": "app/api/tiered_growth.py",
        "config.py": "app/config.py",
    }

    for name in zf.namelist():
        if name in file_map:
            dest = os.path.join(project, file_map[name])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(zf.read(name))
            print(f"  -> {file_map[name]}")

    # 3. 更新 .env
    print("\n[3/5] 配置 API Key...")
    env_file = os.path.join(project, ".env")
    if not os.path.exists(env_file):
        env_file = os.path.join(project, ".env.production")
    if not os.path.exists(env_file):
        env_file = os.path.join(project, ".env")
        open(env_file, "a").close()

    with open(env_file, "r") as f:
        content = f.read()

    creem_config = f"\n# Creem支付\nCREEM_API_KEY={API_KEY}\nCREEM_WEBHOOK_SECRET=\nCREEM_API_BASE=https://api.creem.io/v1\nCREEM_SUCCESS_URL=https://healthlens.cc/#buy-success\nCREEM_WEBHOOK_URL=https://healthlens.cc/api/v1/payment/creem/webhook\n"

    if "CREEM_API_KEY" in content:
        lines = content.split("\n")
        new_lines = []
        for line in lines:
            if line.startswith("CREEM_API_KEY="):
                new_lines.append(f"CREEM_API_KEY={API_KEY}")
            else:
                new_lines.append(line)
        if "CREEM_API_BASE" not in "\n".join(new_lines):
            new_lines.append(creem_config.strip())
        with open(env_file, "w") as f:
            f.write("\n".join(new_lines))
    else:
        with open(env_file, "a") as f:
            f.write(creem_config)
    print(f"  -> .env 已更新")

    # 4. 重启Docker
    print("\n[4/5] 重启容器...")
    os.chdir(project)
    dc = None
    if subprocess.run("docker-compose version", shell=True, capture_output=True).returncode == 0:
        dc = "docker-compose"
    elif subprocess.run("docker compose version", shell=True, capture_output=True).returncode == 0:
        dc = "docker compose"

    if dc:
        run(f"{dc} restart web")
        print(f"  -> {dc} restart web")
    else:
        out, _, _ = run('docker ps --format "{{.Names}}" | grep -i health | grep -i web | head -1')
        if out:
            run(f"docker restart {out}")
            print(f"  -> docker restart {out}")

    print("  -> 等待启动...")
    time.sleep(8)

    # 5. 验证
    print("\n[5/5] 验证...")
    out, _, _ = run('curl -s "https://healthlens.cc/api/v1/growth/points/packages"')
    if out:
        try:
            data = json.loads(out)
            pkgs = data.get("data", [])
            print(f"  -> 套餐API: {len(pkgs)}个套餐")
        except:
            print(f"  -> API: {out[:80]}")

    out, _, _ = run('docker ps --format "{{.Names}}" | grep -i health | grep -i web | head -1')
    if out:
        container = out.strip()
        check, err, _ = run(f'''docker exec {container} python3 -c "
from app.services.creem_pay_service import CREEM_API_KEY, CREEM_PRODUCT_MAP
print(f'API: {{CREEM_API_KEY[:20]}}...' if CREEM_API_KEY else 'API: NOT SET')
print(f'Products: {{len(CREEM_PRODUCT_MAP)}}')
for k,v in CREEM_PRODUCT_MAP.items(): print(f'  {{k}}: {{v}}')
"''')
        if check:
            for line in check.strip().split("\n"):
                print(f"  -> {line}")

    print("\n" + "=" * 50)
    print("  部署完成!")
    print()
    print("  产品映射:")
    for p in [("starter","$1.99","100"),("basic","$5.99","550"),("pro","$17.99","2300"),("ultimate","$39.99","6000")]:
        print(f"    {p[0]:10s} -> {p[1]:7s} ({p[2]}积分)")
    print()
    print("  待完成:")
    print("    1. Creem Dashboard > Developers > Webhook:")
    print("       https://healthlens.cc/api/v1/payment/creem/webhook")
    print("    2. 获取Webhook Secret添加到.env:")
    print("       CREEM_WEBHOOK_SECRET=whsec_xxx")
    print("=" * 50)

if __name__ == "__main__":
    main()
