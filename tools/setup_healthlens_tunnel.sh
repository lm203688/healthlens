#!/bin/bash
# =============================================================================
# HealthLens 独立 Cloudflare Tunnel 部署脚本（与 AIShield 完全隔离）
# -----------------------------------------------------------------------------
# 背景：ECS 上曾有两个项目共用一份 /root/.cloudflared/config.yml。
#       cloudflared 启动时会把本地 config 的 ingress 推送到 Cloudflare 远端
#       （remote config 的 "source": "local"），因此任何一方重启都会用自己的
#       配置覆盖远端路由，导致另一方的 hostname 全部落到兜底 404。
#       本脚本为 HealthLens 建立【独立隧道 + 独立配置 + 独立 systemd 服务】，
#       从根本上消除共享配置的耦合。
#
# 用法（在 ECS 上以 root 执行）：
#   bash setup_healthlens_tunnel.sh
# 可覆盖的变量：
#   TUNNEL_NAME / API_HOSTNAME / ORIGIN / CONFIG_DIR / SERVICE_NAME
#
# 幂等：重复执行只会确保状态正确，不会重复创建隧道或破坏已有路由。
# =============================================================================

set -euo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-healthlens-tunnel}"
API_HOSTNAME="${API_HOSTNAME:-api.healthlens.cc}"
ORIGIN="${ORIGIN:-http://127.0.0.1:8000}"
CONFIG_DIR="${CONFIG_DIR:-/etc/cloudflared-healthlens}"
SERVICE_NAME="${SERVICE_NAME:-cloudflared-healthlens}"
CRED_DIR="${CRED_DIR:-/root/.cloudflared}"
CF_BIN="${CF_BIN:-/usr/local/bin/cloudflared}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "请以 root 运行（sudo bash $0）"; exit 1
fi

command -v cloudflared >/dev/null 2>&1 || { echo "未找到 cloudflared"; exit 1; }

# -----------------------------------------------------------------------------
# STEP 1: 确保隧道存在（复用已有 ID，避免重复创建）
# -----------------------------------------------------------------------------
log "STEP 1: 准备隧道 ${TUNNEL_NAME}"

TUNNEL_ID=""
if [ -f "${CONFIG_DIR}/config.yml" ]; then
    TUNNEL_ID=$(awk '/^tunnel:/{print $2; exit}' "${CONFIG_DIR}/config.yml")
    log "复用已配置的隧道 ID: ${TUNNEL_ID}"
fi

if [ -z "${TUNNEL_ID}" ]; then
    EXISTING=$($CF_BIN tunnel list 2>/dev/null | awk -v n="${TUNNEL_NAME}" '$2==n{print $1}')
    if [ -n "${EXISTING}" ]; then
        TUNNEL_ID="${EXISTING}"
        log "复用已存在的同名隧道: ${TUNNEL_ID}"
    else
        log "创建新隧道 ${TUNNEL_NAME} ..."
        $CF_BIN tunnel create "${TUNNEL_NAME}" 2>&1 | tee /tmp/hl_tunnel_create.log
        TUNNEL_ID=$(grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' /tmp/hl_tunnel_create.log | head -1)
        [ -n "${TUNNEL_ID}" ] || { echo "无法解析隧道 ID"; exit 1; }
        log "新隧道 ID: ${TUNNEL_ID}"
    fi
fi

# -----------------------------------------------------------------------------
# STEP 2: 独立配置目录 + 独立凭证副本（与 /root/.cloudflared 解耦）
# -----------------------------------------------------------------------------
log "STEP 2: 写入独立配置 ${CONFIG_DIR}/config.yml"
mkdir -p "${CONFIG_DIR}"

if [ ! -f "${CONFIG_DIR}/${TUNNEL_ID}.json" ]; then
    if [ -f "${CRED_DIR}/${TUNNEL_ID}.json" ]; then
        cp "${CRED_DIR}/${TUNNEL_ID}.json" "${CONFIG_DIR}/${TUNNEL_ID}.json"
    else
        echo "找不到凭证文件 ${CRED_DIR}/${TUNNEL_ID}.json"; exit 1
    fi
fi
chmod 600 "${CONFIG_DIR}/${TUNNEL_ID}.json"

cat > "${CONFIG_DIR}/config.yml" << EOF
# HealthLens 专用隧道配置（与 AIShield 完全隔离）
# 本文件不引用 /root/.cloudflared/config.yml，也不被任何其他项目的脚本触碰
tunnel: ${TUNNEL_ID}
credentials-file: ${CONFIG_DIR}/${TUNNEL_ID}.json

originRequest:
  connectTimeout: 30s
  noHappyEyeballs: true

ingress:
  - hostname: ${API_HOSTNAME}
    service: ${ORIGIN}
  - service: http_status:404
EOF

$CF_BIN --config "${CONFIG_DIR}/config.yml" tunnel ingress validate || { echo "ingress 校验失败"; exit 1; }

# -----------------------------------------------------------------------------
# STEP 3: 独立 systemd 服务
# -----------------------------------------------------------------------------
log "STEP 3: 配置 systemd 服务 ${SERVICE_NAME}"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Cloudflare Named Tunnel for HealthLens (isolated)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=${CF_BIN} --config ${CONFIG_DIR}/config.yml tunnel --metrics 127.0.0.1:8099 run
Restart=always
RestartSec=5
KillMode=process
TimeoutStartSec=120
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1
systemctl restart "${SERVICE_NAME}"
sleep 10
systemctl is-active --quiet "${SERVICE_NAME}" && log "服务状态: active" || { echo "服务启动失败"; exit 1; }

# -----------------------------------------------------------------------------
# STEP 4: 把 DNS CNAME 指向本隧道（cloudflared CLI 无法跨隧道覆盖，改用 API）
# -----------------------------------------------------------------------------
log "STEP 4: 校正 ${API_HOSTNAME} 的 CNAME 指向本隧道"
python3 - "${API_HOSTNAME}" "${TUNNEL_ID}" << 'PYEOF'
import json, base64, sys, urllib.request, urllib.error

hostname, tunnel_id = sys.argv[1], sys.argv[2]
pem = open('/root/.cloudflared/cert.pem').read()
d = json.loads(base64.b64decode(''.join(l for l in pem.splitlines() if not l.startswith('-----'))))
token, zone = d['apiToken'], d['zoneID']
target = '%s.cfargotunnel.com' % tunnel_id
H = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

def call(method, url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, method=method, headers=H)
    try:
        with urllib.request.urlopen(req, body, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'http_error': e.code, 'body': e.read()[:300].decode('utf-8', 'ignore')}

listed = call('GET', 'https://api.cloudflare.com/client/v4/zones/%s/dns_records?per_page=200' % zone)
records = [r for r in listed.get('result', []) if r['name'] == hostname and r['type'] == 'CNAME']
if not records:
    print('  未找到 %s 的 CNAME 记录，跳过（请检查 DNS 配置）' % hostname)
for rec in records:
    print('  当前:', rec['content'][:60])
    if target in rec['content']:
        print('  已指向本隧道，无需变更'); continue
    res = call('PUT', 'https://api.cloudflare.com/client/v4/zones/%s/dns_records/%s' % (zone, rec['id']),
               {'type': 'CNAME', 'name': rec['name'], 'content': target, 'ttl': 1, 'proxied': True})
    print('  更新结果:', res.get('success'), '->', (res.get('result') or {}).get('content', res.get('body', ''))[:60])
PYEOF

# -----------------------------------------------------------------------------
# STEP 5: 看门狗（防止服务被外部 pkill 后长时间未恢复）
# -----------------------------------------------------------------------------
log "STEP 5: 安装看门狗 cron"
CRON_LINE="*/5 * * * * systemctl is-active --quiet ${SERVICE_NAME} || systemctl restart ${SERVICE_NAME}"
( crontab -l 2>/dev/null | grep -v "${SERVICE_NAME}"; echo "${CRON_LINE}" ) | crontab -

# -----------------------------------------------------------------------------
# STEP 6: 验证
# -----------------------------------------------------------------------------
log "STEP 6: 验证"
sleep 5
echo "  ${API_HOSTNAME}/health -> $(curl -s -m 20 -o /dev/null -w '%{http_code}' https://${API_HOSTNAME}/health)"
echo "  隧道连接:"
$CF_BIN tunnel info "${TUNNEL_ID}" 2>/dev/null | sed -n '5,8p' | sed 's/^/    /'

log "完成。HealthLens 现由独立隧道 ${TUNNEL_NAME} (${TUNNEL_ID}) 承载，与 AIShield 无共享配置。"
