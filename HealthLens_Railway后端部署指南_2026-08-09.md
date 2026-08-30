# HealthLens 后端上线 · Railway 部署指南

> 目标：把 FastAPI 后端（含 PostgreSQL）部署到 Railway，拿到一个公网 URL，填进 Cloudflare 的 `BACKEND_URL`，让 `healthlens.cc` 的 `/api`、`/knowledge`、`/sitemap.xml` 全部从 503 变 200。

---

## 0. 一个重要前提

前端已在 Cloudflare Pages 跑通（我已部署）。后端**必须自己有一台服务器**。Railway 是最省事的方案（连 GitHub 自动构建，自带 PostgreSQL）。

> 💡 省钱提示：你项目里已有 `.github/workflows/deploy.yml`，会把后端部署到**阿里云 ECS**（`/opt/healthlens`，打 `v*` tag 触发）。如果那台 ECS 还在运行，用它比 Railway 更便宜。本指南按你选的 Railway 写；想换 ECS 随时说。

---

## 1. 注册 / 登录 Railway

打开 **https://railway.app/** → 右上角 **Login** → 选 **GitHub** 登录（用你存代码那个 GitHub 账号）。

---

## 2. 新建项目并连 GitHub 仓库

1. 登录后点 **New Project**（或 **https://railway.app/new**）
2. 选 **Deploy from GitHub repo**
3. 首次会请求授权 GitHub → 点 **Authorize Railway**
4. 仓库列表里选 **healthlens**（你的后端仓库）
5. Railway 检测到根目录 `Dockerfile` → 自动开始构建 web 服务

构建约 3–6 分钟（Dockerfile 装了不少依赖）。等状态变 **Active / Success**。

---

## 3. 加 PostgreSQL 数据库

1. 项目页点 **New** → **Database** → **Add PostgreSQL**
2. 等它变成 **Active**
3. 点进这个 Postgres 实例 → 顶部 **Variables** 标签页 → 复制 `DATABASE_URL` 的值
   - 形如：`postgresql://user:password@host:port/railway?sslmode=require`

---

## 4. 加 Redis（推荐，缓存/限流用）

1. 项目页点 **New** → **Database** → **Add Redis**
2. 等它 **Active**
3. 复制它的 `REDIS_URL`（形如 `redis://default:password@host:port`）

---

## 5. 配置环境变量（最关键一步）

点进你的 **web 服务**（不是数据库）→ **Variables** 标签页 → **New Variable**，逐个添加：

| 变量名 | 值 | 说明 |
|---|---|---|
| `DEBUG` | `false` | 生产模式 |
| `DATABASE_URL` | 见下方说明 | **必须改 asyncpg 前缀** |
| `JWT_SECRET_KEY` | 强随机串 | **绝不能留默认**，否则启动即崩溃 |
| `MINIO_SECRET_KEY` | 强随机串 | **绝不能留 `minioadmin`**，否则启动即崩溃 |
| `CORS_ORIGINS` | `["https://healthlens.cc"]` | 允许前端跨域 |
| `REDIS_URL` | 第4步复制的 Redis URL | 缓存/限流 |
| `CELERY_BROKER_URL` | `redis://.../1`（Redis URL 末尾改 `/1`） | 异步任务 broker |
| `CELERY_RESULT_BACKEND` | `redis://.../2` | 结果后端 |
| `PUBLIC_BASE_URL` | `https://healthlens.cc` | 已默认，可不动 |
| `SMS_PROVIDER` | `mock` | 先 mock（验证码回传前端），后接阿里云 |
| `AGNES_API_KEY` | 你的 LLM key（可选） | 填了诊断才生效 |

### DATABASE_URL 怎么填（重要）

Railway 的 Postgres 给的是 `postgresql://...`，但本项目的 SQLAlchemy 用的是 **asyncpg** 驱动，需要 `postgresql+asyncpg://` 前缀。

把第 3 步复制的 `DATABASE_URL`：
```
postgresql://user:pass@host:port/railway?sslmode=require
```
改成：
```
postgresql+asyncpg://user:pass@host:port/railway?ssl=require
```
（前缀 `postgresql` → `postgresql+asyncpg`，参数 `sslmode` → `ssl`）

粘到 web 服务的 `DATABASE_URL` 变量里（**用户手动设的会覆盖 Railway 插件自动注入的同名变量**）。

### 生成强随机串

在本地终端跑（任选其一）：
```bash
openssl rand -hex 32      # 用于 JWT_SECRET_KEY
openssl rand -hex 32      # 用于 MINIO_SECRET_KEY（同样生成一份）
```

---

## 6. 重新部署让变量生效

web 服务页面 → 点 **Deploy** 或等它自动 redeploy。等状态 **Active**，且 **/health** 健康检查通过（Railway 会标绿）。

> 如果一直红：看 **Deploy Logs**，大概率就是 `JWT_SECRET_KEY` / `MINIO_SECRET_KEY` 没改，或 `DATABASE_URL` 前缀错了。

---

## 7. 拿到后端 URL → 填回 Cloudflare

1. web 服务页面 → **Settings** → **Networking** → 复制 **Public Networking / Domain**
   - 形如：`https://healthlens-production-xxxx.up.railway.app`
2. 打开 Cloudflare（你已进到 healthlens 项目 Settings → Environment variables）：
   - 加 `BACKEND_URL` = `https://healthlens-production-xxxx.up.railway.app`
   - 作用域 Production → Save（**即时生效，无需重部署**）
3. 验证：
   ```bash
   curl -s https://healthlens.cc/api/v1/health
   # 应返回 200 + JSON，不再是 503
   ```

### （可选）绑定自定义域名 api.healthlens.cc

1. Railway web 服务 → **Settings** → **Networking** → **Custom Domain** → 填 `api.healthlens.cc`
2. Railway 会给你一个 CNAME 目标
3. Cloudflare DNS 里给 `api` 加一条 **CNAME** 指向该目标
4. 之后 `BACKEND_URL` 改成 `https://api.healthlens.cc`（更干净）

---

## 8. 跑数据库迁移 + 种子数据（1247 个 SEO 页）

Railway 只跑 app，不会自动建表/灌数据。在本地（已连 Railway 数据库）执行：

```bash
# 装 railway CLI：https://docs.railway.app/develop/cli
railway login
railway link            # 选你的 healthlens 项目
railway run alembic upgrade head
railway run python scripts/seed_seo_content.py
railway run python scripts/seed_seo_longtail.py
railway run python scripts/seed_seo_topics.py
```

跑完 sitemap 从 39 条涨到 ~1247 条。

---

## 9. 最终验收清单

```bash
curl -s -o /dev/null -w "%{http_code}" https://healthlens.cc/api/v1/health      # 期望 200
curl -s -o /dev/null -w "%{http_code}" https://healthlens.cc/sitemap.xml        # 期望 200
curl -s -o /dev/null -w "%{http_code}" https://healthlens.cc/knowledge/shen-nong-ben-cao-jing  # 期望 200
```

---

## 排错速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 部署红 / 一直重启 | JWT/MINIO 默认值 | 改 JWT_SECRET_KEY、MINIO_SECRET_KEY 为随机串 |
| `/api` 仍 503 | BACKEND_URL 没填或填错 | Cloudflare 环境变量确认 BACKEND_URL 指向 Railway 域名 |
| 连不上数据库 | DATABASE_URL 前缀错 | `postgresql+asyncpg://` + `ssl=require` |
| 表不存在 | 没跑 alembic | `railway run alembic upgrade head` |

---

## 我（AI）能替你做的

- ✅ 已写好 `railway.json`（健康检查 `/health`、失败重启）
- ⏳ 你把 **Railway 后端域名**发我 → 我直接 bake 进 `_worker.js` 重部署 Cloudflare（你不用动 Cloudflare 后台）
- ⏳ 你给 `DATABASE_URL`（Railway 的）+ 本地能跑 `railway` CLI 的环境 → 我替你跑迁移 + 灌 1247 页

需要你操作的只有：Railway 注册、连仓库、加数据库、填那几个变量。其余交给我。
