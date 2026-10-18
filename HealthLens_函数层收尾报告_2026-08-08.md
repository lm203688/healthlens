# HealthLens 函数层收尾报告 · 2026-08-08

## 本次完成（"全部做掉"的代码/部署层）

把原 `functions/` 目录的 12 个 Pages Functions 整合为**单一 `_worker.js`**（Workers 运行时），
解决 Direct Upload 模式下 `functions/` 不被编译、导致 `/api` 与 `/knowledge` 等全部返回 SPA HTML 软 404 的根因。

**已落地并上线（部署 `7039a25b`，生产域 healthlens.cc 已切换）：**
- 新增 `healthlens/frontend/_worker.js`：整合全部路由——`/api/**` 代理、`/knowledge|/health|/health-tools` 静态优先后代理、`packages` 静态兜底、`buy` 下单转发、GEO 文件静态服务。
- `build_site.py` 同步改造：复制 `_worker.js` 进 dist；存在 `_worker.js` 时跳过 `functions/` 目录（避免两种模式冲突）；新增 `humans.txt` 静态生成。
- humans.txt 线上此前返回 0 字节，`_worker.js` 加了一道"ASSETS 空则内联"兜底，已验证 200 非空。

## 线上验证（curl，已生效）
| 路由 | 结果 |
|---|---|
| `/api/v1/health` | JSON 503 `application/json`（明确"后端未配置"）→ 证明 Worker 在运行 |
| `/api/v1/growth/points/packages` | JSON 200 + 静态兜底（starter/basic/pro/ultimate） |
| `/humans.txt` | 200 非空（262B） |
| 首页 canonical | `https://healthlens.cc/` |
| `/knowledge/action-7day-challenge` | 200 静态 HTML |
| `/sitemap.xml` | 39 条全 `healthlens.cc` |

## 还差两项外部资源（客观缺失，需你提供地址，我无法凭空生成）

1. **`BACKEND_URL`** —— FastAPI 源站地址（如 `https://api.healthlens.cc` 或 `http://<服务器IP>:8000`）。
   - 作用：`_worker.js` 的 `/api` 代理与 `/knowledge` 动态 613 页靠它转发到后端。
   - 约束：**不能填 `healthlens.cc` 自身**（会回环 503）；需是独立源站域名/IP。
   - 给地址后我可用 Cloudflare API 直接写入环境变量，或你后台 Settings → Environment variables 手动加。

2. **生产 `DATABASE_URL`** —— 连线上 Postgres（非本地 localhost 库）。
   - 作用：跑 `seed_seo_content.py` + `seed_seo_longtail.py` + `seed_seo_topics.py`，
     把 613 古籍 + 613 FAQ + 21 体质/症状页写入生产库，sitemap 从 39 → ~1251。
   - 给地址后我连上即跑（幂等），无需重部署。

## 你只需回我这两行，我立刻收尾
```
BACKEND_URL=https://你的FastAPI源站
DATABASE_URL=postgresql+asyncpg://用户:密码@生产库地址:5432/healthlens
```

> 安全：3 个 `cfut_*` 令牌仅存于 `.workbuddy/cache/`（已加 `.gitignore`），沙箱连不上 GitHub 故未推送代码；建议用毕按需在 Cloudflare 吊销。
