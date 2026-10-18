# HealthLens 后端上线 · 腾讯云 ECS 部署指南（实测修订版）

> 目标：把后端跑在 `150.158.119.19` 的 `/home/ubuntu/atex/healthlens`，通过子域 `api.healthlens.cc` 暴露，填进 Cloudflare `BACKEND_URL`，让 `healthlens.cc` 的 `/api`、`/knowledge`、`/sitemap.xml` 从 503 变 200。
> **实测关键事实（2026-08-09）**：这台 ECS 当前已在 443 上跑着 **AIShield**（另一个项目）。所以 HealthLens 必须**作为子域共存**，复用宿主 nginx 反代，绝不碰 AIShield 的配置。

---

## ⚠️ 实测结论（决定下面所有步骤）

1. **这台机器跑的是 AIShield，不是 HealthLens**。`https://150.158.119.19/` 返回 AIShield 首页，`/home/ubuntu/atex/` 是其部署目录。
2. **SSH 密码登录已禁用**：`atex_deploy_2026` 当密码对 `ubuntu/root/deploy/atex` 全部 `Authentication failed`；常见部署 webhook 路径（`/deploy`、`/webhook`、`/api/deploy`…）全部 404。**意味着只能走 SSH 密钥登录**。
3. **Flexible SSL 架构**：宿主 nginx 在 80/443，CF 终止 HTTPS → 源站走 HTTP:80。所以 HealthLens 容器只需监听 `127.0.0.1:8000`，由宿主 nginx 加一个 `api.healthlens.cc` 的 vhost 反代过去，**不需要 HealthLens 自己的 nginx 容器**（避免占用 80/443 与 AIShield 冲突）。
4. **`deploy.yml` 用不了**：那条 GitHub Action 目标是 `/opt/healthlens`（另一台机器），且 `REGISTRY` 是空占位符，流水线本身没配好。

---

## 架构（共存版）

```
浏览器 → healthlens.cc (Cloudflare Pages 前端)
                └─ Worker 代理 /api/* → https://api.healthlens.cc
                                        └─ Cloudflare 橙云 (Flexible: 边缘HTTPS→源站HTTP:80)
                                           └─ ECS 150.158.119.19:80 (宿主 nginx, AIShield 同台)
                                              └─ 新增 vhost api.healthlens.cc → 127.0.0.1:8000
                                                 └─ HealthLens web 容器 :8000 (db/redis/minio 仅内网)
```

---

## 第 0 步（必须）：拿到 SSH 登录方式

当前 `atex_deploy_2026` 既不是密码也不是 webhook。需要 **`ubuntu@150.158.119.19` 的 SSH 私钥**（你平时登这台机器用的那把）。三选一给我：

- **A. 直接把私钥贴给我**（若带密码短语，连密码一起给）。我存进 gitignored 缓存，用 paramiko 登录后跑部署脚本，用完可删。
- **B. 你自己在腾讯云控制台 VNC 登录**，生成一把新密钥并把公钥写进 `~/.ssh/authorized_keys`，再把私钥给我。
- **C. 你自己 SSH 上去跑脚本**（见第 1 步），我把脚本和配置都准备好了。

> 凭 `atex_deploy_2026` 我无法登录，也不会去暴力猜密码（会触发 fail2ban 锁账号）。

---

## 第 1 步：在 ECS 上部署（脚本已备好）

已写好 `scripts/ecs_deploy.sh`，自动完成：克隆/拉代码 → 生成 `.env` 强随机密钥 → 起 `web worker beat db redis minio`（不含 nginx）→ 等 `/health` → `alembic upgrade head` → 灌 1247 页 → 安装 `api.healthlens.cc` 宿主 nginx vhost → 重载 nginx → 验收。

登录后执行：
```bash
cd /home/ubuntu/atex/healthlens
bash scripts/ecs_deploy.sh
# 只重新灌 SEO 页: bash scripts/ecs_deploy.sh --seed
```
相关文件（已提交到仓库）：
- `docker-compose.ecs.yml` —— 共存覆盖：web 监听 `127.0.0.1:8000`，禁用自带 nginx
- `nginx/api.healthlens.cc.conf` —— 宿主 nginx 子域反代配置（仅 :80，Flexible 无需证书）
- `scripts/ecs_deploy.sh` —— 一键部署脚本

> 若代码尚未 clone 到 `/home/ubuntu/atex/healthlens`，先在脚本里填 `REPO_URL` 或手动 `git clone`。

---

## 第 2 步：Cloudflare DNS 加 `api` 记录（你在后台做，我的令牌无 DNS 写权限）

1. 打开 **https://dash.cloudflare.com/8162aa3b2241c132e43a81f526d7f758/healthlens.cc/dns/records**
2. **Add record**：
   - Type: **A**
   - Name: **api**
   - IPv4 address: **150.158.119.19**
   - Proxy status: **Proxied（橙色云 ☁️）** ← 必须橙云，走 Flexible SSL
3. 保存

---

## 第 3 步：确认 Cloudflare SSL 模式 = Flexible

1. **SSL/TLS** → **Overview**
2. 加密模式选 **Flexible**（否则 CF 连源站 525）

---

## 第 4 步：Cloudflare Pages 填 `BACKEND_URL`（你已进到该页）

- 加 `BACKEND_URL` = `https://api.healthlens.cc`
- 作用域 Production → Save（即时生效）

---

## 第 5 步：验收

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://healthlens.cc/api/v1/health        # 期望 200
curl -s -o /dev/null -w "%{http_code}\n" https://healthlens.cc/sitemap.xml          # 期望 200
curl -s -o /dev/null -w "%{http_code}\n" https://healthlens.cc/knowledge/shen-nong-ben-cao-jing  # 期望 200
```

---

## 排错

| 现象 | 原因 | 解决 |
|---|---|---|
| 登录被拒 | 用的是密码而非密钥 | 改用 SSH 私钥（第 0 步） |
| `/api` 仍 503 | BACKEND_URL 没填，或 ECS 没起 | 第4步 + ECS 上 `curl 127.0.0.1:8000/health` |
| 525 错误 | SSL 模式不是 Flexible | 第3步改 Flexible |
| AIShield 挂了 | 误改了宿主 nginx 主配置 | 只新增 conf.d 文件，别动 AIShield 原配置；`nginx -t` 通过再 reload |
| 部署后一直重启 | JWT/MINIO 默认值 | 脚本已自动填强随机值；若手动改过 `.env` 需确保非默认 |
| 表不存在 | 没跑 alembic | 脚本已包含，或手动 `exec web alembic upgrade head` |

---

## 分工

- **AI（拿到 SSH 密钥后）**：ECS 上跑 `ecs_deploy.sh` 部署 + 灌页；最终验收 curl。
- **你（Cloudflare 后台）**：加 `api` A 记录（橙云）、SSL=Flexible、Pages `BACKEND_URL=https://api.healthlens.cc`。
- **安全必做**：https://github.com/settings/tokens 吊销之前泄露的 GitHub PAT。
