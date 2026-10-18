# HealthLens 推广进展日志 · 2026-08-08

## 第 1 节｜每日发现巡检（23:55 执行）

### 要点（约 190 字）

线上 sitemap 仅 **39 条**（远低于 100 阈值）。本次定位到真正阻塞：**healthlens.cc 部署的是 `auto-pipeline/dist/` 旧构建产物，而非含全部代理函数的 `healthlens/frontend/`**。旧产物无 `knowledge/`、`health/`、`api/` catch-all 函数，`sitemap.xml`/`llms.txt`/`ai.txt` 全是静态文件，因此**即便 seed 613 页进生产库，线上也无法暴露**——此前"只需跑 seed"的判断需修正为"必须先重新部署前端"。更严重的是 38 个知识页中 **24 个 canonical 指向 healthlens.com（403，非本站）**、8 个路径写成 `/education/`，首页 canonical 指向 healthlens.cc（500）。当前站点 SEO 权重基本为零。

### 巡检结果

| 检查项 | 结果 | 判定 |
|---|---|---|
| `/sitemap.xml` | HTTP 200，**39 条 loc**（1 首页 + 38 knowledge `.html`） | ⚠️ < 100，未铺量 |
| `/ai.txt` | 200，449B，Last-Updated 2026-08-07 | ✅ 可访问（静态） |
| `/llms.txt` | 200，13.3KB，索引 38 条 | ✅ 可访问（静态） |
| `/robots.txt` | 200，含 GPTBot/ClaudeBot/PerplexityBot 白名单 | ✅ 正常 |
| `/humans.txt` | 200 但 149,739B ≈ index.html(149,399B) | ❌ **soft-404 假阳性** |
| `/knowledge/人参` | 200 但返回首页 HTML | ❌ **soft-404** |
| `/health/constitution-qixu` | 200 但返回首页 HTML | ❌ **soft-404** |
| `/api/v1/health` | 200 但返回首页 HTML | ❌ **API 代理未生效** |
| `/knowledge/*.html` | 308 → 无扩展名 URL，内容真实 | ⚠️ sitemap 应直接写终态 URL |

### 根因：部署产物错配

| | `auto-pipeline/dist/`（线上实际） | `healthlens/frontend/`（应部署） |
|---|---|---|
| GEO 文件 | 静态 sitemap.xml / ai.txt / llms.txt / robots.txt | 动态函数 `sitemap.xml.js` 等（经 `_proxy.js` 走后端） |
| 代理函数 | 仅 3 个支付 js | `api/[[path]].js`、`knowledge/[[path]].js`、`health/[[path]].js`、`health-tools/[[path]].js` |
| 知识页 | 38 个静态 html（canonical 错误） | 由后端动态输出 613+ 页 |
| 首页 canonical | `https://healthlens.cc/`（500） | 由 `PUBLIC_BASE_URL` 统一 |

字节数比对佐证：线上 sitemap 7,592B ≈ dist 7,828B；llms.txt 13,314B ≈ dist 13,370B（差值为 CRLF）。

### canonical 缺陷清单（38 个知识页）

| canonical 域名 | 页数 | 该域状态 |
|---|---|---|
| `https://healthlens.com` | **24** | 403，非本站 |
| `https://healthlens.cc` | 14 | ✅ 正确 |
| 路径写成 `/education/` | 8 | 线上无此路径 |
| 首页 canonical → `healthlens.cc` | 1 | 500 |

后果：63% 的知识页把索引权重导向一个 403 的外部域名，搜索引擎会判定 healthlens.cc 为非规范副本而不予收录。

### 步骤 2｜内容铺量

未执行。`DATABASE_URL` 环境变量未设置，`.env` 内为 `postgresql+asyncpg://healthlens:***@localhost:5432/healthlens`（本地库，非生产）。**需配置生产 DATABASE_URL**。

补充：即使配置并 seed 成功，在前端重新部署前线上仍不可见（见上"根因"）。三个脚本均幂等，预期产出 613 古籍主页 + 613 FAQ 页 + 21 体质/症状页 + 4 工具页 ≈ **1,251 页**。

另发现 `scripts/seed_seo_content.py:162` 工具落地页模板硬编码 `https://healthlens.cc/health-tools/tools/{slug}`（该域 500），会在生成内容中产生死链——建议改为读取 `PUBLIC_BASE_URL`。本次遵守"不修改业务代码"约束，仅记录。

### 步骤 3｜IndexNow

跳过。`INDEXNOW_KEY` 未设置，站点根未托管 key 文件。当前 sitemap 仅 39 条，铺量前推送价值有限。

### 下一步建议（按优先级）

1. **P0｜修正 canonical**：24 个页面的 `healthlens.com` → `healthlens.cc`，8 个 `/education/` → `/knowledge/`，首页 `healthlens.cc` → `healthlens.cc`。不改这一项，后续所有铺量都不会被收录。
2. **P0｜重新部署前端**：Cloudflare Pages 构建输出目录切到 `healthlens/frontend/`，并配置环境变量 `BACKEND_URL`（指向 FastAPI 源站，**不可填 Pages 域名**，否则回环）。部署后验证 `/api/v1/health` 返回 JSON 而非 HTML。
3. **P1｜生产库铺量**：提供生产 `DATABASE_URL` 后依次跑 `seed_seo_content.py` → `seed_seo_longtail.py` → `seed_seo_topics.py`，sitemap 应涨到约 1,251 条。
4. **P2｜sitemap 去 `.html`**：当前全部 308 跳转，浪费抓取预算，应直接输出终态 URL。
5. **P2｜IndexNow**：待页数 > 500 后再配置 key 并批量推送。

---

## 第 2 次巡检（23:55，推广加速·每日发现）

### 要点

线上 **39 页**（<100，未铺开）。GEO 层健康：`llms.txt`/`ai.txt`/`robots.txt` 均 200，域名全 `.cc`、零 `.app`/`.com` 污染，AI 引擎可正常引述。

**新发现 P0（比上次更严重）**：首页 canonical 指向 `https://healthlens.cc/`，而该域名已查实是**另一个不相关的英文站**（"AI Medical Companion"，2.2KB，无 sitemap），并非本站镜像。等于首页主动告诉搜索引擎「别收录我，去收录那个站」，权重外流。`cf-cache-status: DYNAMIC` 已排除边缘缓存，是真实产物问题。

**根因（本次定位）**：生产存在**每小时一次的外部自动部署**（8 次 ad_hoc，最新 `0207f882` / commit `8134516`「新增 _routes.json」）。该提交**不在本地仓库**，本地 `_routes.json`、`functions_count` 逻辑也不存在 → 另一份工作副本在部署，它构建工具更新但**缺 canonical 修复**，持续覆盖 8 月 8 日上午的修复成果。本地源已全部干净（`frontend/` 内 `healthlens.cc` 命中 0）。

**连带**：`_worker.js` 未生效 → `/api/*` 返回 SPA HTML、`humans.txt` 0 字节、38 个 `.html` 全部 308 跳转（与 canonical 终态 URL 不一致，白耗抓取预算）。

### 步骤结果

| 步骤 | 结果 |
|---|---|
| 1 巡检 | sitemap 39 `<loc>`（全 `.cc`）；ai/llms/robots 200 ✅；`/api/v1/health` 返回 HTML ❌ |
| 2 铺量 | **未执行** — `DATABASE_URL` 未设置，`.env` 仅 localhost 且本地 5432 亦不可达。需配置生产 `DATABASE_URL` |
| 3 IndexNow | 跳过 — `INDEXNOW_KEY` 未设置 |
| 4 报告 | 本节 |

### 下一步建议

1. **P0｜先停部署战**：本次**未重新部署**。本地 dist 虽 canonical 正确，但覆盖上去会丢掉对方更新的 `_routes.json`/构建修复，且 1 小时内必被再次覆盖。须先确认那份工作副本归属，把 canonical 修复合并进**它**的源码。
2. **P0｜首页 canonical/og:url** → `https://healthlens.cc/`；并决定 `healthlens.cc` 存废（建议 301 到 `.cc` 或下线，避免品牌词分流）。
3. **P1｜`_routes.json` 复核**：Worker 未执行极可能是它把 `/api/*` 排除了；修好后 `/api/v1/health` 应返回 JSON。
4. **P1｜生产 `DATABASE_URL`** → 跑 3 个 seed，sitemap 39 → ~1,251。
5. **P2｜sitemap 直接输出无扩展名 URL**，消除 38 次 308。
