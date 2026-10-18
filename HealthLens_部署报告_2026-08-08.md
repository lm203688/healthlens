# HealthLens 部署报告 · 2026-08-08

## 部署动作
用 Cloudflare 部署令牌（`cfut_*`）经 `wrangler pages deploy` 将修复后的 `auto-pipeline/dist` 直接上传到 **healthlens** Pages 项目（Direct Upload 模式，账户 `8162aa3b…`，域名 `healthlens.cc` / `www.healthlens.cc`）。
- 新部署：`eb0696ff.healthlens-a3w.pages.dev`
- 上传 35 文件（12 复用），生产域名 `healthlens.cc` 已切换为新版本。

## ✅ 已生效（线上验证，2026-08-08 09:1x GMT+8）
| 项 | 验证结果 |
|---|---|
| 首页 canonical | `https://healthlens.cc/` ✅（原 `healthlens.cc`） |
| 知识页 canonical | `https://healthlens.cc/knowledge/action-7day-challenge` ✅（原 `healthlens.com/education/`） |
| sitemap 域名纯度 | 39 条 `<loc>` **全部** `healthlens.cc`，外部域名 0 ✅ |
| GEO 文件 | `ai.txt` / `llms.txt` / `robots.txt` / `sitemap.xml` 可访问 ✅ |
| 无 `healthlens.com/app` 残留 | dist 全量 0 命中 ✅ |

> SEO 头号问题（canonical 把权重导向外部死域）**已修复并上线**。

## ❌ 未生效：Pages Functions（`/api`、`/knowledge` 动态页）
`/api/v1/health` 仍返回 SPA 的 HTML（不是 JSON），`functions/` 未被当作 Functions 执行。
**根因**：该项目是 **Direct Upload** 类型（`source: None`，无 Git 构建步骤）。`wrangler pages deploy` 只上传静态资源，`functions/` 目录按静态文件处理、不会打包成 Pages Functions。要跑函数，必须二选一：

### 方案 A：写 `_worker.js`（Direct Upload 也能跑函数）—— 我可做
把 `functions/` 的路由逻辑改造成单个 `_worker.js`（Workers 运行时），放在 dist 根，重新部署即生效。
- 优点：沙箱内即可完成，不依赖 GitHub push。
- 依赖：**`BACKEND_URL`**（见下）。

### 方案 B：项目切到 Git 连接构建 —— 你来做
Cloudflare 后台把 healthlens 项目改为连接 GitHub `lm203688/healthlens`，push 即自动 `build_site.py` 构建并把 `functions/` 打包成 Functions。
- 缺点：本沙箱连不上 GitHub，需你在能联网的机器 push（之前的卡点）。

## 还需你提供（函数与 613 页的前提）
1. **`BACKEND_URL`**（FastAPI 源站地址，如 `https://api.healthlens.cc`）
   - 用途：`_proxy.js` / `api/[[path]].js` / `knowledge/[[path]].js` 把请求转发到它。
   - 怎么设：Cloudflare 后台 healthlens → Settings → Environment variables 添加 `BACKEND_URL`；或把地址给我，我用 API 写入（注意：不能填 `healthlens.cc` 自身，否则回环 503）。
2. **生产 `DATABASE_URL`**
   - 用途：连上后跑 3 个 seed，生成 613 古籍 + 613 FAQ + 21 体质/症状页，经 `/knowledge/[[path]].js` 动态呈现，sitemap 从 39 → ~1251。
   - 命令（连上库后）：`DATABASE_URL=<生产库> python scripts/seed_seo_content.py && python scripts/seed_seo_longtail.py && python scripts/seed_seo_topics.py`

## 令牌与安全检查
- 3 个 `cfut_*` 令牌已用于本次部署（Token 2 部署成功；Token 1 仅账户读、Token 3 同项目部署令牌）。
- 令牌临时存于 `.workbuddy/cache/cf_tokens.txt`，**已加入 `.gitignore` 防止误提交**；未推送（沙箱无法连 GitHub）。
- 建议：Cloudflare 后台确认这 3 个令牌的权限范围，用毕可按需吊销。

## 验收 curl（随时自查）
```bash
curl -s https://healthlens.cc/ | grep -o 'canonical" href="[^"]*"'        # 应含 healthlens.cc
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" https://healthlens.cc/api/v1/health   # 函数生效应为 JSON(200 application/json)
curl -s https://healthlens.cc/sitemap.xml | grep -o '<loc>' | wc -l       # 现为 39，seed 后 ~1251
```
