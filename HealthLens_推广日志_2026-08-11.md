# HealthLens 推广日志 · 2026-08-11（夜间定时巡检）

## 一、线上健康巡检（实时 curl，已加 `?cb=` 穿透边缘缓存）

| 指标 | 结果 | 判定 |
|---|---|---|
| `sitemap.xml` `<loc>` 数 | **39** | ❌ 远低于 1255 目标 |
| 首页 canonical | `https://healthlens.app/` | ❌ 最严重缺陷（权重外流+主动放弃收录） |
| `ai.txt` | 200 / 449B | ✅ |
| `llms.txt` | 200 / 13.3KB | ✅ |
| `robots.txt` | 200 / 515B | ✅ |
| 后端 `api.healthlens.cc/health` | **525**（TLS 握手失败） | ❌ |

**要点（200 字内）**：本次实测线上已回落到 pre-fix 旧构建——sitemap 仅 39 条、首页 canonical 仍指向 `healthlens.app`、后端经 Cloudflare 代理返 525。GEO 文件（ai/llms/robots）健康无污染。根因定位：本工作区 8-11 修复提交 `83404e8`（canonical→.cc + worker `resolveOverride`×4）**仅存在于本地 detached HEAD，未推上 `origin/main`**（`git branch -r --contains` 仅返回本地 HEAD），故每小时部署器始终从「未修复的 origin/main」出包，把修复覆盖掉。铺量与 IndexNow 在 P0 未解前均无意义。

## 二、内容铺量（步骤 2）

- 跳过：沙箱未设置 `DATABASE_URL`（env 校验：DATABASE_URL / INDEXNOW_KEY / BACKEND_URL 均不存在），本地 5432 亦关闭。
- 备注：后端 `seo_pages` 此前已 seed 至 1251（613 古籍 + 613 FAQ + 21 体质/症状 + 4 health-tools）。一旦 worker 修复（resolveOverride 生效），sitemap 即可回弹至 ~1255，**无需重跑 seed**。

## 三、主动推送（步骤 3）

- 跳过：环境变量 `INDEXNOW_KEY` 未设置。即便设置，因 worker 未修复、key 文件 `d0ff98…txt` 当前返 SPA，也会 `SiteVerificationNotCompleted`。

## 四、根因与下一步建议（按优先级）

1. **【P0 阻断】推送修复到 origin/main**：`git push origin 83404e8:refs/heads/main`（红线：绝不 `git add -A`，勿带 `.workbuddy/` 与 `.wrangler/`）。
2. **确认部署源唯一**：核查是否存在第二份每小时出包副本（Cloudflare Pages `healthlens` 为 Direct Upload，`source:null`，理论上不连 Git，但实测有 hourly ad_hoc 部署）。找到即关停其自动部署，避免再次覆盖。
3. **验证修复生效**：部署后 `curl https://healthlens.cc/?cb=1` 确认 canonical=`.cc`；`curl https://healthlens.cc/sitemap.xml` 应回到 1255；`api.healthlens.cc/health` 经 resolveOverride 直连源站 IP 应 200。
4. P0 解除后再跑步骤 2/3（配生产 `DATABASE_URL` + `INDEXNOW_KEY`）做增量铺量与推送。

> 说明：本次未自行部署/推送——历史记录表明重复部署会触发覆盖战，正确解法是让本工作区成为唯一可信源并关停竞争部署器，故交用户决策执行。
