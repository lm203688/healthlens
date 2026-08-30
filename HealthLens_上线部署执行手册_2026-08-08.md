# HealthLens 上线部署执行手册（2026-08-08）

> 目标：让 **https://healthlens.cc** 真正跑通「前端 SPA + Cloudflare 代理 + 后端 API + 1251 个 SEO 页 + 支付（国内虎皮椒 / 国际 Creem）+ 手机验证码」。
>
> 图例：**【你】**= 需要你登录对应后台点 **【我】**= 我可以在代码/命令层替你做 **【共同】**= 一起核对
>
> 当前已确认：代码侧 `frontend/functions/`（含 `_proxy.js`、`knowledge/`、`health-tools/`、`api/[[path]].js`）、`/send-sms-code`、`/phone-login` 端点、3 个 seed 脚本均已就位。线上仍部署的是旧产物 `auto-pipeline/dist/`（仅 3 个支付 function + 39 页静态 sitemap），导致 `/api`、`/knowledge`、真实工具页全部 soft-404。

---

## 总览（先后顺序）

| 步骤 | 内容 | 谁做 | 阻塞级别 |
|---|---|---|---|
| 0 | 前置决策：后端源站域名 | 【你】 | 必须先定 |
| 1 | 修复 Cloudflare Pages 构建产物错配 | 【你】后台点 +【我】核对 | **P0 最高** |
| 2 | 配置后端源站 + `BACKEND_URL` 环境变量 | 【你】+【我】 | P0 |
| 3 | 生产库灌入 1251 个 SEO 页 | 【共同】 | P0 |
| 4 | 支付上线（虎皮椒已就绪 / Creem 独立店） | 【你】后台 +【我】填变量 | P1 |
| 5 | 手机验证码真实短信网关（可选） | 【你】后台 +【我】改配置 | P2 |
| 6 | 吊销 GitHub 泄露的 PAT（安全） | 【你】后台点 | **安全必做** |
| 7 | 提供 `AGNES_API_KEY`（让诊断 LLM 生效，可选） | 【你】提供 | P2 |

---

## 步骤 0 ｜ 前置决策：后端源站用哪个域名（必须先定）

Cloudflare Pages 上的 `_proxy.js` 会把 `/api`、`/knowledge`、`/health`、`/health-tools` 转发到环境变量 `BACKEND_URL` 指向的后端源站。**关键约束：`BACKEND_URL` 不能是 `healthlens.cc` 本身**（否则无限回环，代码里已防住会直接 503）。

请二选一，并在后续步骤填对应值：

- **方案 A（推荐）**：后端放在子域 `https://api.healthlens.cc`
  - 在 DNS 里给 `api.healthlens.cc` 指向你的后端服务器（docker-compose + nginx，已在 `.env.production` 规划好）。
  - 则 `BACKEND_URL = https://api.healthlens.cc`
- **方案 B**：后端放在别的已备案域名（如 `https://api.你的其他域名.com`），`BACKEND_URL` 填它。

> 把你的选择（域名）告诉我，步骤 2 的变量值就以它为准。

---

## 步骤 1 ｜ 修复 Cloudflare Pages 构建产物错配【P0 最高】

**链接**：https://dash.cloudflare.com/ → 选你的账户 → 左侧 **Workers & Pages** → 点 **healthlens** 项目 → **Settings** → **Builds & deployments** → **Build configuration**

点击动作：
1. 确认 **Root directory**（根目录）设置。本仓库 git 根目录是 `healthlens/`（内含 `frontend/`、`app/`、`scripts/`、`docker-compose.prod.yml`）。
2. 把 **Build output directory（构建输出目录）** 从当前的 `auto-pipeline/dist` 改成 **`frontend`**（即包含 `index.html` 和 `functions/` 的那个目录）。
   - 若你的 Pages「Root directory」设为 git 仓库根，则输出目录填 `frontend`。
   - 若「Root directory」设为 `healthlens`，输出目录也填 `frontend`。
   - 一句话：输出目录 = 同时含有 `index.html` 与 `functions/` 的文件夹，本仓库即 `frontend/`。
3. **Build command（构建命令）**：本前端是纯静态（无需 npm build），可填 `echo "static"` 或留空（Pages 会直接发布输出目录）。
4. 点 **Save**。
5. 回到 **Deployments** → 点 **Retry deployment**（或重新触发一次部署），等构建变绿。

**验证（部署后你或我来测）**：
```bash
# 应返回 JSON（不再是首页 HTML）
curl -s https://healthlens.cc/api/v1/health
# 应返回 200 且是知识页正文
curl -s -o /dev/null -w "%{http_code}\n" https://healthlens.cc/knowledge/<某个slug>
```

> 这一步是 SEO 与 API 能用的前提，没有它后面全不可见。

---

## 步骤 2 ｜ 配置后端源站 + `BACKEND_URL`【P0】

**链接**：https://dash.cloudflare.com/ → healthlens 项目 → **Settings** → **Environment variables**

点击动作：
1. 点 **Add variable**（作用域选 **Production**）。
2. 变量名 `BACKEND_URL`，值填步骤 0 定的域名，例如 `https://api.healthlens.cc`。
3. 保存后**重新部署一次**（步骤 1 的 Deployments → Retry）。

**后端源站本身（你这边服务器）**：
- 用仓库里的 `docker-compose.prod.yml` 起服务（FastAPI + nginx + Postgres + Redis + MinIO）。
- 确认 `api.healthlens.cc` 的 nginx 已把 `/api` 反代到 FastAPI（`.env.production` 里 `DOMAIN=healthlens.cc`、虎皮椒回调 `https://healthlens.cc/api/v1/payment/notify` 已规划）。
- 如用方案 A，把 compose 里的 `DOMAIN` 改为 `api.healthlens.cc` 或单独给子域配 nginx server block。

**我可替你做的**：核对 `frontend/functions/_proxy.js` / `api/[[path]].js` 转发逻辑（已正确保留 method/headers/body）；如需要我可补一份 `wrangler.toml` 或部署检查清单。

---

## 步骤 3 ｜ 生产库灌入 1251 个 SEO 页【P0】

准备：拿到生产库的连接串（Postgres，格式 `postgresql+asyncpg://用户:密码@host:5432/healthlens`）。

**【我】可以替你跑**（只要你把生产 `DATABASE_URL` 给我，或确认我连得到）：
```bash
cd healthlens
export DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/healthlens"

python scripts/seed_seo_content.py     # 613 古籍主页
python scripts/seed_seo_longtail.py    # 613 FAQ 页（FAQPage 结构化数据）
python scripts/seed_seo_topics.py       # 21 体质/症状页
```

**【你】若想自己跑**（在后端服务器或能连生产库的环境）：
1. 进后端容器 / venv：`pip install -r requirements.txt`
2. 执行上面三条命令。

**验证**：
```bash
# sitemap 应含 ~1251 条 URL
curl -s https://healthlens.cc/sitemap.xml | grep -c "<loc>"
# 抽查一个古籍页
curl -s -o /dev/null -w "%{http_code}\n" https://healthlens.cc/knowledge/<slug>
```

> 注意：只灌库、不先做步骤 1/2，线上依然看不见（soft-404）。三者顺序：① 步骤1/2 改构建+后端 → ② 步骤3 灌库。

---

## 步骤 4 ｜ 支付上线【P1】

### 4.1 国内 · 虎皮椒 XunhuPay（已基本就绪）
- 凭据已在 `.env.production`：`XUNHU_APPID=201906181178`、`XUNHU_SECRET=...`、网关 `https://api.xunhupay.com`、回调 `https://healthlens.cc/api/v1/payment/notify`。
- **你确认**：虎皮椒后台（https://www.xunhupay.com/ ）商户状态为「已激活/可收款」，回调地址可达。
- 前端 `index.html` 已含 `#pay-method-xunhu`，无需改动。

### 4.2 国际 · Creem 独立专店（需你开店铺 + 填变量）
**链接**：https://www.creem.io/dashboard
点击动作：
1. 登录 Creem → 新建一个**独立店铺**（不要和别的店混，代码里 `assert_store()` 会硬校验 `store_id`）。
2. 记下该店的 **API Key / Store ID / Product ID**（starter/basic/pro/ultimate 四个套餐各建一个产品）。
3. 把以下变量加到后端环境变量（`.env` / 生产环境）：
   - `CREEM_API_KEY=...`
   - `CREEM_STORE_ID=...`（独立店 ID）
   - `CREEM_WEBHOOK_SECRET=...`（如用 webhook）
   - `CREEM_API_BASE=https://api.creem.io`（沙箱用 https://test-api.creem.io）
4. 前端 `index.html` 已含 `#pay-method-creem` + `app.v2.js` 双轨逻辑，无需改动。

**验证**：前端选 Creem → 跳新窗口 USD 结账 → 完成后 webhook 回调 `/api/v1/payment/creem/webhook` 入账。

---

## 步骤 5 ｜ 手机验证码真实短信网关（可选）【P2】

当前 `SMS_PROVIDER=mock`（开发期回传 `dev_code`）。上线真实发送：

**链接（阿里云）**：https://dysms.console.aliyun.com/
点击动作：
1. 开通「短信服务」→ 申请签名 + 模板（如「验证码 ${code}，5 分钟内有效」）。
2. 创建 AccessKey，拿到 `AccessKeyId` / `AccessKeySecret`。
3. **【我】改 `app/config.py` + `app/services/sms_service.py`**：把 `SMS_PROVIDER` 默认值改 `aliyun`，并接入阿里云 SDK 发送分支（代码里已留 `aliyun` 分支骨架）。
4. 在 `.env` 填：
   - `SMS_PROVIDER=aliyun`
   - `ALIYUN_SMS_ACCESS_KEY_ID=...`
   - `ALIYUN_SMS_ACCESS_KEY_SECRET=...`
   - `SMS_DEV_RETURN_CODE=false`（关闭回传 dev_code）
   - `SMS_SIGN_NAME=...`、`SMS_TEMPLATE_CODE=...`

> 不填也能跑（mock 模式），但用户收不到真实短信，只能你用 dev_code 自测。

---

## 步骤 6 ｜ 吊销 GitHub 泄露的 PAT（安全必做）【最高优先·安全】

之前 inner 仓库 git remote 曾含明文 GitHub PAT（本地 `origin` 已改为无令牌 `https://github.com/lm203688/healthlens.git`，**但线上令牌本身未吊销**）。

**链接**：https://github.com/settings/tokens
点击动作：
1. 登录 GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**（也看 **Fine-grained**）。
2. 找到那个泄露的 token → 右侧 **⋯** → **Revoke**（撤销）。
3. 如不确定是哪个，直接**全部 Revoke 并重建**一个新 token（最小权限），勿再写入任何仓库 URL。

> 仅改本地 remote URL 不会让令牌失效，必须来这里吊销。

---

## 步骤 7 ｜ 提供 `AGNES_API_KEY`（让诊断 LLM 生效，可选）【P2】

当前 `AGNES_API_KEY` 默认空 → 诊断 Agent 走「诚实 demo 降级」（只回显本人提交数据骨架，不返回他人基因）。要真实 AI 分析：
- **你**提供 `AGNES_API_KEY`（或任意兼容 LLM 的 API Key）。
- 加到后端 `.env`：`AGNES_API_KEY=...`。
- 重启后端即生效；前端无需改动（降级横幅会自动消失）。

---

## 一键验证清单（全部完成后）

```bash
# 1) API 健康检查（应 JSON）
curl -s https://healthlens.cc/api/v1/health
# 2) SEO 页数量（应 ~1251）
curl -s https://healthlens.cc/sitemap.xml | grep -c "<loc>"
# 3) 知识页 200
curl -s -o /dev/null -w "%{http_code}\n" https://healthlens.cc/knowledge/<slug>
# 4) 手机验证码发送（mock 返回 dev_code）
curl -s -X POST https://healthlens.cc/api/v1/auth/send-sms-code \
  -H "Content-Type: application/json" -d '{"phone":"13900000000"}'
# 5) 支付套餐列表
curl -s https://healthlens.cc/api/v1/payment/packages
```

---

## 我现在能立刻替你做的
1. 核对/补 `frontend/functions/` 全部代理函数（已正确）。
2. 只要你给**生产 `DATABASE_URL`**，立刻跑步骤 3 的 3 条 seed 脚本并回报条数。
3. 改 `app/config.py` + `sms_service.py` 的阿里云分支（步骤 5），等你给密钥即可联调。
4. 写一份 `wrangler.toml` / 部署检查清单，便于你在 Cloudflare 后台对照勾选。

**请回复**：
- 步骤 0 你选方案 A 还是 B（后端域名）？
- 步骤 3 是否把生产 `DATABASE_URL` 给我跑 seed？
- 步骤 6 的 PAT 你这边去吊销（链接已给），还是需我再做别的？
