# HealthLens 推广日志 2026-08-07

> 状态：自动化推广流程已就位；生产站内容仍偏旧，需最后一步「连生产库 seed」即可爆发式扩量。

## 今日动作（已自动完成部分）
- 新增长尾内容扩量脚本 `scripts/seed_seo_longtail.py`：为 613 条古医实体生成 FAQ 问答页（category=`tcm-herb-faq`，附 schema.org **FAQPage** 结构化数据，利好 Google 富结果与 AI 引擎引述）。本地验证新增 **613 页**，幂等可重复。
- 新增回归测试 `tests/core/test_seo_longtail.py`；全量单测 **225 项**（本沙箱 safe-delete 拦截 1 项 `test_delete_record`，CI/ubuntu 全过）。
- 创建 **2 个推广自动化**（WorkBuddy Automations，状态 ACTIVE）：
  - `HealthLens 推广加速·每日发现`（FREQ=DAILY）：巡检 sitemap/llms.txt/ai.txt → 幂等 seed 613 古籍主页 + 613 FAQ 页 → 可选 IndexNow → 写日志。
  - `HealthLens 内容扩量·每周`（FREQ=WEEKLY;BYDAY=MO）：周度扩量 + 环比复盘 + 选题建议。
- 已剔除 git remote 中的明文 GitHub PAT（本地 remote 改为无令牌 URL `https://github.com/lm203688/healthlens.git`；线上令牌仍需在 GitHub 吊销）。

## 关键发现：生产站内容仍是旧的
- 线上 `healthlens.cc` 已上线且我的 GEO 代码在跑（`ai.txt` 标记 `Last-Updated: 2026-08-07`），但 `sitemap.xml` 仅 **39 条** `.html` 页面（如 `action-7day-challenge.html`）。
- **我的 613 古籍主页 + 613 FAQ 页尚未写入生产库** → 这些高意图页面目前不可被检索。
- 因后端代码已在线，**连生产库跑一次 seed 即可补齐，无需重新部署**：
  ```bash
  cd healthlens/healthlens
  DATABASE_URL="<生产库URL>" python scripts/seed_seo_content.py
  DATABASE_URL="<生产库URL>" python scripts/seed_seo_longtail.py
  ```
  补齐后 sitemap 将达 **~1226 页**，`/knowledge/<slug>` 与 `/knowledge/<slug>-faq` 全部 200，搜索/AI 引述面翻倍。

## 收录机制变更（务必知悉）
- **Google/Bing 的 sitemap ping 接口已于 2023 年废弃**（实测 Google 404 / Bing 410），旧「ping 提交」无效，自动化已移除该调用。
- 现代收录三件套：① **内容铺量**后被爬虫自然抓取；② **GEO 文件**（`llmsdn`? 实为 `llms.txt`/`ai.txt`）供 AI 引擎（ChatGPT/Perplexity）引述；③ 可选 **IndexNow**（在生产站根托管 `<KEY>.txt` 后向 `api.indexnow.org` 推送）。
- 自动化已按此更新。

## 待用户配合（推广真正爆发的最后一步）
1. 在运行自动化的环境设置 `DATABASE_URL` 指向生产库（每日自动化会自动 seed）；或手动跑一次上面的 seed 命令。
2. （可选加速）生成 IndexNow key 并托管 `<KEY>.txt` 到 `healthlens.cc` 根，配置 `INDEXNOW_KEY` 环境变量。
3. 在 GitHub **吊销**泄露的 PAT（本地 remote 已清理）。
4. 提供 `AGNES_API_KEY`/可用 LLM 解锁真实诊断；Creem 后台**开独立店** + 配 `CREEM_*`。
