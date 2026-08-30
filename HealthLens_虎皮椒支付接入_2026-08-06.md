# HealthLens 虎皮椒（XunhuPay）国内支付接入 · 交接文档

> 日期：2026-08-06
> 渠道：虎皮椒 XunhuPay（api.xunhupay.com，国内微信/支付宝收款）
> 凭证：AppID `201906181178` / App Secret `d856af3cab45ce0b0ae5d491a2ac94b0`（已实测网关接受）

## 一、我已完成（代码侧，零风险）

1. **后端凭证已就位**：`.env`（已被 gitignore，不会进仓库）第 29–33 行已有 `XUNHU_APPID` / `XUNHU_SECRET` 等变量。后端 `app/config.py` 用 `BaseSettings(env_file=".env")` 加载，启动即生效。
2. **修正死 IP 默认值**：`app/config.py` 中 `XUNHU_NOTIFY_URL` / `XUNHU_RETURN_URL` 原指向已失效的 `http://150.158.119.19`，已改为 `https://healthlens.cc/...`（与 nginx、其余服务默认一致）。
3. **修复前端入口断点**：`frontend/functions/api/v1/growth/points/buy.js` 之前对 `payment_method=xunhu/wechat/alipay` 直接返回"通道即将上线"并拒绝——而前端默认支付方式恰好是 `xunhu`，等于国内支付在前端入口被卡死。现已改为：**把请求转发到后端 `BACKEND_URL`**，由后端 `tiered_growth.buy_points` 创建虎皮椒订单并返回 `pay_url`/`qrcode_url`。
4. **回归测试**：`tests/core/test_xunhu_pay.py`（7 项，全过），锁定签名生成/校验、回调验证、订单创建逻辑。全量套件 **192 passed / 0 failed**。

## 二、你需要配合的部署步骤（浏览器/服务器操作）

### 步骤 A：Cloudflare Pages 环境变量（dash.cloudflare.com → 项目 → Settings → Environment variables）
新增一个变量：
- **`BACKEND_URL`** = 后端 FastAPI 源站地址（必填）
  - 示例：`https://api.healthlens.cc` 或 `http://<你的服务器IP>:8000`
  - ⚠️ **切勿填 Cloudflare Pages 域名**（如 `https://healthlens.cc`）。`buy.js` 会把请求转发到 `BACKEND_URL`，若指回 Pages 会无限回环调用自身。
  - 该地址必须：① 从 Cloudflare 边缘网络可达；② 真实提供 FastAPI 后端（即 `/api/v1/growth/points/buy` 能创建订单）。

### 步骤 B：确认后端回调地址外网可达（关键）
虎皮椒在用户支付成功后会向 `XUNHU_NOTIFY_URL`（当前 `https://healthlens.cc/api/v1/payment/notify`）**主动发 POST 回调**来发积分。必须保证该 URL 从公网能触达后端，否则用户付了钱积分不到账。
- 若生产是 **nginx/docker 部署在 `healthlens.cc`**（nginx.conf 已 proxy `/` → 后端）：✅ 已满足，无需额外操作。
- 若 `healthlens.cc` 实际是 **Cloudflare Pages**，且 `/api/v1/payment/*` 没有代理规则：需补一条到后端的代理（Cloudflare 路由规则 / 一个 catch-all Pages Function 转发到 `BACKEND_URL`）。**这一步决定国内支付能否真正发积分。**
- 同样需保证 `/api/v1/payment/status/{order_no}` 可达（前端轮询支付状态用）。

### 步骤 C：确认生产域名
- 通知/回跳地址当前用 `healthlens.cc`。若你的生产域名是 `healthlens.cc`，请改 `.env` 的 `XUNHU_NOTIFY_URL` / `XUNHU_RETURN_URL`（及 config.py 默认值）为对应域名。

### 步骤 D：确认后端服务器环境变量
- 后端 `.env`（本机 `healthlens/healthlens/.env`）已含虎皮椒凭证。若后端部署在另一台服务器（docker/nginx 主机），请确保那台机器的 `.env` 或容器环境变量也包含 `XUNHU_APPID` / `XUNHU_SECRET`，否则运行时读取为空、创建订单会失败。

## 三、端到端验证方法
1. **先冒烟**：登录后调用 `POST /api/v1/growth/points/buy?package_code=hl_starter&payment_method=mock` → 应立即返回"积分已到账"（不接真实支付）。
2. **真实链路**：选「微信/支付宝」→ 前端应拿到 `pay_url`/`qrcode_url` 并展示二维码 → 扫码支付 → 虎皮椒回调 `notify` → 积分到账。
3. **查单兜底**：前端轮询 `/api/v1/payment/status/{order_no}`；即使回调丢失，后端也会主动 `query_order` 补发积分（`payment.py` 已实现）。

## 四、与 Creem 的对比提醒
- 虎皮椒是 **CNY 原生**，与前端展示的 ¥9.9/39/128/299 一致 → **无币种错位问题**（Creem 是 USD，之前提示过需对齐）。
- 虎皮椒回调是 **form 表单 POST**，后端 `payment.py` 已用 `request.form()` + `verify_callback` 验签，逻辑完整。
- Creem 的 webhook 走边缘函数 `webhook.js`（只验签不发分），虎皮椒的 notify 走**后端** `payment.py`（直接发分），两条链路独立、互不干扰。

## 五、改动文件清单
- `app/config.py` — notify/return 默认域名修正
- `frontend/functions/api/v1/growth/points/buy.js` — 国内支付转发后端（新增 `BACKEND_URL` 依赖）
- `tests/core/test_xunhu_pay.py` — 新增回归测试
- `healthlens/healthlens/.env` — 凭证已存在（无需改动）
