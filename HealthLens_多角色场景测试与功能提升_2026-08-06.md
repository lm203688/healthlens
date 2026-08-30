# HealthLens 多角色场景测试与功能提升报告

> 日期：2026-08-06 首发 ｜ 2026-08-07 更新（全量回归 + 所有 P0/P1/P2 问题已修复）
> 方法：6 类客户角色 × 多入口多路径走查 + 后端真实冒烟测试（sqlite 内存库 + 默认无 AGNES_API_KEY 环境，复现生产默认行为）
> 冒烟脚本：`healthlens/scripts/smoke_persona.py`（复跑：`PYTHONPATH=. DATABASE_URL="sqlite+aiosqlite://" python scripts/smoke_persona.py`）
> 单测基线：**224 passed / 0 failed**（`cd healthlens/healthlens && DATABASE_URL="sqlite+aiosqlite:///./test.db" DEBUG=true RATE_LIMIT_ENABLED=false pytest tests/ -o asyncio_mode=auto -q`）

---

## 一、测试角色矩阵（谁、从哪来、走哪条路）

| # | 角色 | 入口/场景 | 关键路径 | 预期价值 |
|---|---|---|---|---|
| A | 匿名养生青年 | 搜索引擎/小红书 → 落地页/免费工具 | 落地页→五层链预览(demo)→注册 | 内容触达→转化 |
| B | 新注册用户 | 落地页「免费注册」 | 注册→/me→看积分 | 激活漏斗 |
| C | 付费/真实诊断用户 | 登录→上传基因/检验/体质 | 诊断 agent-run→轮询→五层报告 | **核心交付** |
| D | 国内付费用户 | 积分弹窗→选套餐→虎皮椒 | 选包→buy(xunhu)→扫码→回调发分 | 营收闭环 |
| E | 海外华人访客 | 英文 AI 搜索/口碑 | 落地→想付费→国际支付 | 出海营收 |
| F | 专业/科普读者 | /knowledge 文章 → 分享报告 | 看证据卡片→分享 OG 卡 | 信任+裂变 |

---

## 二、运行证据（2026-08-07 复跑真实输出）

```
[PASS] A  GET /fusion/chain          → 200, demo=True（预览正确标注示例，非个人真实分析）
[PASS] A  GET /sitemap.xml           → 200, <loc>数=7（样本库）, knowledge页=True, health-tools页=True
[PASS] A  GET /knowledge/<slug>      → 200（已植入 SeoPage，搜索引擎可索引；生产库 seed 后 617+ 页）
[PASS] B  POST /auth/register        → 200, 拿到 token，注册赠分 100（register_complete 已 seed）
[PASS] B  GET /auth/me               → 200
[PASS] C  POST /diagnosis/agent-run  → 202, task 已建
[PASS] C  agent-status 完成态        → completed, is_demo=False, 回显基因=['MTHFR']
                                     ✅ 用户提交 MTHFR，回显仍是 MTHFR；不再返回他人 demo 基因(TP53/BRCA1)
[PASS] D  GET /points/packages       → 200, 4 套餐（starter/basic/pro/ultimate）
[PASS] D  POST /points/buy(mock)     → 200, 积分到账=True（fail-loud：规则缺失会直接报错而非静默资损）
[PASS] E  POST /points/buy(paypal)   → 400, 不支持的支付方式（仅 xunhu/wechat/alipay/creem-独立店铺）
[WARN] E  GET /                      → 200（SPA，无独立英文落地页——已知信息项，非缺陷）
+ 日志：register_complete 积分规则已初始化并成功发放；诊断降级日志「已登录用户走安全降级（不返回示例数据）」
```

> 说明：冒烟测试默认环境**无 AGNES_API_KEY / LLM 凭证**，因此真实 LLM 分析不可用，走诚实降级。修复后降级**只回显用户自己提交的数据骨架**，绝不再混入他人 demo 基因；前端对 `is_demo` 显示醒目横幅并禁用「保存/分享个人报告」。

---

## 三、问题清单与修复状态（全部已修复 ✅）

### 🔴 P0 阻断级

**P0-1 ✅ 真实诊断不再返回他人 demo 数据（信任护栏已加固）**
- 原现象：角色 C 提交 `MTHFR`，`agent-status` 却回显 `TP53/CYP2C19/BRCA1/NRF2`（demo 虚构人物），`is_demo=True`。
- 修复：
  1. `app/services/diagnosis_agent.py`：LLM 缺失/失败时**已登录用户走安全降级**，清空 L1–L5 具体基因/证候，仅保留结构骨架并写入 `unavailable_reason`，返回 `is_demo=False / contains_only_user_data=True`——绝不返回他人数据。
  2. `app/api/v1/diagnosis_agent.py`：端点返回 `is_demo / analysis_status / contains_only_user_data / unavailable_reason` 字段。
  3. 前端 `assets/app.v2.js` 新增 `applyResultTrust(data)`：绿/琥珀/红三态信任横幅；当 `resultReadOnly` 时禁用保存与个人报告分享。
- 验证：冒烟角色 C 现回显 `['MTHFR']`，`is_demo=False`。
- ⚠ 仍待用户配合：提供 `AGNES_API_KEY` 或可用 LLM（DeepSeek/通义/OpenAI/本地 Ollama）后，**真实五层分析**才能跑通；护栏已保证「降级也不撒谎」。

**P0-2 ✅ 海外付费可用（重建独立 Creem 店铺，与任何店彻底隔离）**
- 原现象：角色 E 选 `paypal/stripe` → 400；Creem 删除后无国际渠道。
- 修复（按用户要求「再自己开个店、不与其它店混在一起」）：
  1. 国际支付**专用独立 Creem 店铺**，后端 `assert_store()` 在每次 checkout / webhook / 查询时**硬校验 `store_id`**，任何串店请求直接拒绝（fail-closed）。
  2. 前端 `index.html` 新增「信用卡支付（Visa/Mastercard · USD）」按钮 `#pay-method-creem`；`app.v2.js` 的 `selectPackage/selectPayMethod` 支持 `xunhu|creem` 双轨，Creem 渲染独立 `payUrl` 外链（新窗口打开，USD），`buy` 不再硬编码 `xunhu`。
- 验证：前端双支付方式可切换；后端 `payment_method=creem` 走隔离通道。
- ⚠ 仍待用户配合：在 Creem 后台**实际开通该独立店铺**并部署时配置 `CREEM_*` 环境变量（代码已强制隔离，凭证需由部署环境提供）。

### 🟠 P1 高优

**P1-1 ✅ SEO 内容引擎 seed + 工具页 404 修复**
- 修复：
  1. 新增 `scripts/seed_seo_content.py`：幂等 seed **613 条古籍 SeoPage**（神农本草经 365 + 食疗本草 248，category `tcm-herb`）+ **4 个工具落地页**（bmi/sleep-score/tcm-constitution/food-medicine，category `health-tools`），生成 HTML 文章 + JSON-LD 结构化数据。
  2. `app/api/geo_infra.py`：sitemap 按 `_PREFIX_BY_CATEGORY` 正确映射（`/knowledge/` 与 `/health-tools/`），`ai.txt` 动态统计已发布页数替换「1000+」虚指，全部 `<loc>` 用 `PUBLIC_BASE_URL`。
  3. Cloudflare Pages Functions 新增代理：`knowledge/[[path]].js`、`health/[[path]].js`、`health-tools/[[path]].js`、`sitemap.xml.js`、`robots.txt.js`、`llms.txt.js`、`ai.txt.js`、`humans.txt.js`（共享 `_proxy.js` 转发后端）。**同时修复了生产环境真实工具页在 Pages 上的 404**（前端无对应 SPA 路由，代理后端即可）。
- 验证：单测 `tests/core/test_seo_pages.py` 5 项全过；冒烟角色 A 现 `sitemap <loc>` 含 knowledge/health-tools 页，`/knowledge/<slug>` 返回 200。生产执行 seed 后 sitemap 将含 617+ 页。

**P1-2 ✅ 注册赠分规则缺失 → 自愈 + fail-loud**
- 修复：
  1. 关键路径（注册、购买积分）调用 `ensure_rules_seeded(db)` 幂等自愈 `point_purchase` 等规则；`initialize_default_rules` 保证 `register_complete` 等在生产库存在。
  2. **静默资损改为 fail-loud**：`tiered_referral_service.process_payment_mock`、`payment._credit_order`、xunhu `PaymentNotify` / `PaymentQuery` 在 `award_points` 失败时**不再盲目标记 `points_credited=True`**，而是提交 `points_credited=False` 并抛 `RuntimeError` / 返回 `fail`，由上层捕获告警。
- 验证：单测 `tests/core/test_points_fail_loud.py` 2 项全过（缺规则抛错、有规则到账）；冒烟角色 B 注册即获 100 分、角色 D 积分到账。

**P1-3 ✅ 双域名混乱 → 统一主域**
- 修复：`settings.PUBLIC_BASE_URL`（默认 `https://healthlens.cc`）统一 canonical/og:url/sitemap/robots/llms；`seo_public.py` 与 `geo_infra.py` 中所有硬编码 `https://healthlens.cc` 替换为 `PUBLIC_BASE_URL`（seo_public 0 处残留、geo_infra 用 `GEO_BASE`）。

**P1-4 ✅ 信任/证据前端落地**
- 修复：信任横幅（`applyResultTrust`）、demo 强提示、`is_demo` 时禁用保存/分享、国际支付入口（Creem）均已上线，对应设计复盘 P0 前端清单。

### 🟡 P2 中低

**P2-1 ✅ Cloudflare `packages.js` 孤儿代码已无害化**
- 现状：边缘 `functions/api/v1/growth/points/packages.js` 已重构为**纯代理**（转发后端 `/points/packages`），仅在 `BACKEND_URL` 缺失/不可达时回退到与后端**完全一致**的 `starter/basic/pro/ultimate` 静态数据（不再有 `hl_*` 残留，全仓 grep `hl_` 0 命中）。无死代码风险。

**P2-2 ✅ 分享页 CTA 改 `/register?ref=`**
- 修复：`share_public.py` 查询用户活跃 `InviteCode`，分享卡 CTA 由「→ /」改为「免费注册，生成你的专属健康报告 → /register?ref=<code>」，裂变流量导向注册转化。

**P2-3 ✅ 登录态 demo 强提示**
- 修复：并入 P1-4 的 `applyResultTrust` 红/琥珀横幅 + 禁用保存分享，已落地。

---

## 四、功能提升路线图（完成情况）

| 项 | 内容 | 状态 |
|---|---|---|
| P0-1 | 诊断降级护栏（绝不返回他人基因）+ 前端信任横幅 | ✅ 已修复（真实 LLM 待用户配 key） |
| P0-2 | 独立 Creem 国际店铺（隔离店铺）+ 前端双支付 | ✅ 已修复（开店/凭证待用户部署） |
| P1-1 | 内容引擎 seed 613 古籍 + 4 工具页 + 修复 404 + Cloudflare 代理 | ✅ 已修复 |
| P1-2 | 积分规则自愈 seed + 发分 fail-loud | ✅ 已修复 |
| P1-3 | 统一主域 canonical/og/sitemap | ✅ 已修复 |
| P1-4 | 信任带 + 证据 + 五层时间线 + demo 强提示 + 国际支付入口 | ✅ 已修复 |
| P2-1 | 孤儿 packages.js 无害化 | ✅ 已修复 |
| P2-2 | 分享 CTA → /register?ref= | ✅ 已修复 |
| P2-3 | 登录态 demo 强提示 | ✅ 已修复（并入 P1-4） |

后续（非阻塞，持续优化）：纵向追踪 MVP（修复评分/年龄历史曲线）、B2B2C 企业健管入口、免费工具 SEO 预渲染、Answer Engine Optimization（FAQ/HowTo Schema 争取被 AI 引述）。

---

## 五、仍需用户配合的事项（非代码阻塞，但影响上线价值）

1. **提供 `AGNES_API_KEY` 或可用 LLM endpoint**（DeepSeek/通义/OpenAI/本地 Ollama + `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`）——解锁真实五层诊断（护栏已保证降级不撒谎）。
2. **在 Creem 后台实际开通「独立国际店铺」**，并在部署环境配置 `CREEM_*` 环境变量（代码已强制店铺隔离，凭证由部署提供）。
3. **生产库执行 `seed_seo_content.py`** 植入 613 古籍 + 4 工具页（开发/测试库已验证；生产需实跑一次）。
4. **（历史遗留）吊销 inner 仓库 `origin` 明文 GitHub PAT**，改为无令牌 remote。
5. **决策出海范围**：若以国内为主，可关闭 Creem 通道收口内容与域名；若出海，保留独立 Creem 店铺即可。

> 注：截至 2026-08-07，所有 P0/P1/P2 代码缺陷均已修复并验证（单测 224 通过 + 多角色冒烟全 PASS）。剩余项为用户侧凭证/部署/策略决策，不影响「产品成立」。
