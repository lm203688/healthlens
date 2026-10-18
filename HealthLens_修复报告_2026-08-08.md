# HealthLens 修复报告 · 2026-08-08

> 针对《推广巡检 2026-08-08》发现的 P0 阻断项「全部修复」。
> 结论：**代码层全部修复并在本地重建校验通过；剩余为运维部署步骤（本沙箱无法访问 GitHub，需你在可联网环境推送）。**

## 一、根因（与初判不同）

不是"Pages 构建目录配错"。`build_site.py` 本就会把 `frontend/functions` 全量复制到 dist；问题在于 **线上跑的是一份旧 dist**：
- 旧 dist 构建于"functions 与正确 canonical 源文件生成之前"，所以缺 `api/[[path]].js`、`knowledge/[[path]].js` 等函数；
- 源知识页 canonical 写的是 `healthlens.com`/`/education/`，首页写 `healthlens.cc`。

所以只需**修正源 + 加固构建 + 重新部署**即可，无需改 Pages 构建目录。

## 二、已修复（代码层，已本地校验）

| # | 修复项 | 文件 | 结果 |
|---|---|---|---|
| 1 | 首页 canonical / og:url / og:image / twitter:image | `healthlens/frontend/index.html` | `healthlens.cc` → `healthlens.cc` ✅ |
| 2 | 38 个知识页 canonical / og:url / JSON-LD / 内部链接 | `reports/seo-pages/*`、`reports/education/*` | `healthlens.com`/`app` → `healthlens.cc`，`/education/` → `/knowledge/` ✅ |
| 3 | 分享/邀请 base URL（demo 模式死链） | `healthlens/frontend/assets/app.v2.js` | `var base='https://healthlens.cc'` → `healthlens.cc` ✅ |
| 4 | preview 页 canonical/og | `healthlens/frontend/preview.html` | → `healthlens.cc` ✅ |
| 5 | seed 脚本硬编码死链 | `healthlens/scripts/seed_seo_content.py:162` | `healthlens.cc/health-tools/...` → `healthlens.cc` ✅ |
| 6 | **防御性构建**：复制每个 HTML 时强制把 canonical/og/正文/JSON-LD 的外部域名与 `/education/` 收敛到 `SITE_URL` | `auto-pipeline/scripts/phase_6_deploy/build_site.py`（新增 `normalize_links()`） | 今后任何旧源都污染不了 dist ✅ |

## 三、重建 dist 校验结果

```
产物目录 : auto-pipeline/dist
文件总数 : 59    体积: 1265 KB
知识页面 : 38    sitemap: 39 条
```

- ✅ dist 内 `healthlens.com` / `healthlens.cc` **零残留**
- ✅ 首页 canonical/og:url = `https://healthlens.cc/`
- ✅ 知识页 canonical 错误页 = **0**（此前 24 个指向 healthlens.com、8 个 `/education/`）
- ✅ 关键函数齐备：`api/[[path]].js`、`knowledge/[[path]].js`、`health/[[path]].js`、`health-tools/[[path]].js`、`sitemap.xml.js`、`llms.txt.js`、`ai.txt.js`、`humans.txt.js`、`_proxy.js`、支付 `buy.js`/`packages.js`
- ✅ `humans.txt` 改由函数提供 → 修掉此前 149KB 首页软 404
- ✅ sitemap 39 条全为 `healthlens.cc`

## 四、仍待运维（必须你来执行）

> 本沙箱**无法访问 GitHub**（`git ls-remote` → Connection reset），且本地仓库**尚无任何提交**。以下需在**有 GitHub 网络**的环境操作。

**① 提交并推送（触发 Cloudflare 自动部署）**
```bash
cd /path/to/healthlens
git pull origin master            # 先对齐远端历史（本地当前无提交）
git add healthlens/frontend auto-pipeline/scripts reports/seo-pages reports/education healthlens/scripts/seed_seo_content.py
git commit -m "fix(seo): canonical/og 收敛到 healthlens.cc，构建加防御性重写，补全部 serverless 函数"
git push origin master            # Cloudflare「连 GitHub」自动跑 build_site.py 重建发布
```

**② Cloudflare Pages 环境变量**（后台 → 项目 → Settings → Environment variables）
- 新增 `BACKEND_URL` = 你的 FastAPI 源站（如 `https://api.healthlens.cc`）。**不可填 Pages 域名，否则回环 503**。

**③ 铺量 613 古籍 + FAQ + 体质/症状页**（让 sitemap 从 39 → ~1251）
```bash
cd healthlens/healthlens
export DATABASE_URL="<生产库 URL>"
python scripts/seed_seo_content.py      # 613 古籍主页
python scripts/seed_seo_longtail.py     # 613 FAQ 长尾
python scripts/seed_seo_topics.py       # 9 体质 + 12 症状 = 21 页
```
- 这些页经 `knowledge/[[path]].js` → `BACKEND_URL` 代理呈现，**前提是 ② 已配好**。
- 当前静态 `sitemap.xml` 仅含 39 条；铺量后需让 `sitemap.xml.js`（代理后端）或构建期纳入 DB 页，sitemap 才能同步到 1251 条。

**④ 验收**
```bash
curl -sI https://healthlens.cc/knowledge/body-constitution-types.html | grep -i canonical   # 应含 healthlens.cc
curl -s  https://healthlens.cc/api/v1/health                                                    # 应返回 JSON
curl -s  https://healthlens.cc/sitemap.xml | grep -c "<loc>"                                    # 铺量后应 >> 39
```

## 五、本次未做（非阻塞，按需）

- **IndexNow**：sitemap 破 500 页后再上，需站点根托管 `<KEY>.txt` 后 POST `api.indexnow.org`；属 P2，本任务未配置 `INDEXNOW_KEY`。
- **sitemap 去 `.html`**：当前 `.html` URL 与真实文件/canonical 一致，无 308 浪费；如需无扩展名可后续在构建期 strip。
