# HealthLens「裸 /health 健康检查」缺口 — 根因定位与修复方案

> 日期：2026-09-01（自动化每日闭环后续「continue」）｜结论：**根因已定位，缺口由 Cloudflare 边缘规则造成，worker/nginx/后端均正常**

## 1. 现象
- `https://healthlens.cc/health` 外部回读 → **404**（空 body，`Server: cloudflare`，`cf-cache-status: DYNAMIC`）。
- 已知正常：`/api/**` 经 worker 代理 → 200（真实后端数据）。
- 后端源站经 SSH 直连 `localhost:8000/health` → `{"status":"ok","version":"0.18.1"}`（健康）。

## 2. 根因（已逐层排除）
调用链：`healthlens.cc`(CF Worker) → `api.healthlens.cc`(CF 边缘 → 源站 nginx) → `127.0.0.1:8000`(FastAPI)。

| 层 | 验证 | 结论 |
|----|------|------|
| Worker `/health` 路由 | `auto-pipeline/dist/_worker.js` L174 已含 `if (path==="/health") return proxy(...)`；source 与 `deploy_out` 两份已同步防止小时级部署回退 | ✅ 正确 |
| nginx `api.healthlens.cc` | `location / { proxy_pass http://127.0.0.1:8000 }`；ECS 上 `--resolve api.healthlens.cc:443:150.158.119.19` 模拟 worker 路径，`/health` 与 `/api` **均 200** | ✅ 全量反代、无路径限制 |
| 后端 FastAPI | `127.0.0.1:8000/health` 对任意 Host 均返回 ok；主应用 `@app.get("/health")` 无鉴权、无 Host 限制 | ✅ 健康 |
| **Cloudflare 边缘（api.healthlens.cc）** | 沙箱直连 `api.healthlens.cc` **任意路径（含 /api）均 404**；经 worker `resolveOverride` 时 **仅 /api→200、/health→404** | ❌ **路径级放行规则拦截非 /api 路径** |

**结论**：`api.healthlens.cc` 的 Cloudflare 边缘规则（WAF / Firewall 或 Origin Rule）仅放行 `/api/**` 到源站，对 `/health`、`/metrics` 等其它路径在边缘直接 404。404 由 Cloudflare 生成，非本栈任何组件。

## 3. 为什么之前误判为「worker 未代理」
早期 `healthlens.cc/health` 返回的是 SPA 首页 HTML（worker 无 `/health` 规则，落入静态回退）。worker 打补丁后变为 404，进一步排查发现：`deploy_out/_worker.js` 是旧版（小时级部署会回退），已同步修正；但即使 worker 正确代理，Cloudflare 边缘仍 404 —— 故真实瓶颈在 Cloudflare 边缘规则。

## 4. 修复方案（需用户执行 / 二选一）

### 方案 A（推荐，最小、零停机）：放宽 Cloudflare 边缘规则
- **位置**：Cloudflare 控制台 → 站点 `api.healthlens.cc`（账户 `8162aa3b…`）→ **Security → WAF → Firewall Rules**（或 **Rules → Origin Rules**）。
- **动作**：找到「仅放行 `/api/**`、其余返回 404」的规则，增加例外放行 `/health` 与 `/metrics`（或将该规则的目标路径改为 `/api`、`/health`、`/metrics`）。
- **生效**：保存即边缘生效，**无需重新部署** worker。
- **为何不自行动**：部署用 CF 令牌为 Pages-only（无 Zone/Firewall 写权）；属账户级变更，需用户手动确认。

### 方案 B（不碰 Cloudflare，需后端变更）：加无鉴权 `/api/v1/health` 路由
- 后端 `app/__init__.py` 增加 `@app.get("/api/v1/health")` 返回 `{"status":"ok","version":...}`（无鉴权）。
- worker 将 `path==="/health"` 代理目标改为 `api.healthlens.cc/api/v1/health`（命中已放行的 `/api/**`）。
- **代价**：需改后端代码并在 ECS 重启后端服务（生产变更，需用户批准）。

## 5. 本次已落地动作
- ✅ `_worker.js` 增加 `/health` 代理分支（source + `deploy_out` 两份同步，防小时级回退）。
- ✅ 重新构建并部署到 Cloudflare Pages（production 子域 + 自定义域名均已更新；wrangler `Deployment complete` + `Compiled Worker successfully`）。
- ✅ 告警 `auto-pipeline/alerts/2026-08-31_health_route_gap.json` 更新为 `root_caused_pending_user_action`，附根因证据与修复步骤。

## 6. 待办（用户侧）
- [ ] 执行方案 A（或在确认后执行方案 B），使 `https://healthlens.cc/health` 返回 `{"status":"ok","version":"0.18.1"}`。
- [ ] 修复后回读校验：`curl -s https://healthlens.cc/health` → 200 + `{"status":"ok",...}`。
