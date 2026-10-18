# HealthLens 产品完整性评估与开源技术提升建议

> 评估日期：2026-09-23｜评估口径：线上实测 + 仓库代码清点 + 既有文档比对
> 评估目标：在「wellness 定位 + 出海（英文优先）+ 硬件对接」新方向下，判断产品完整性、定位断层，并给出结合开源平台的提升路径。

---

## 一、取证方法（先说结论怎么来的）

| 来源 | 取证内容 |
|---|---|
| 线上探测 | `healthlens.cc/health` → `{"status":"ok","version":"0.22.0"}`；`/api/v1/axes/meta` 200；`/app/` 200；`sitemap.xml` **1255 条 URL**；`llms.txt` 可访问 |
| 后端代码清点 | `app/__init__.py` 注册 **41 个 include_router**；`app/api/` **48 个文件**；`app/models/` **29 个**；`app/core/` **15 个引擎**；`app/connectors/` **7 个** |
| 前端清点 | `App.jsx` **10 个页面 / 9 个导航项**；`api/client.js` 仅 93 行，消费 **约 25 个端点**；依赖仅 8 个（无图表库 / 表单库 / PWA） |
| 内容语言实测 | 抽查 `health-tools/tools/bmi-calculator`：`<html lang="zh-CN">`、`<title>免费BMI计算器…</title>`、中文字符 1136 个 → **GEO 内容 100% 中文** |
| 测试规模 | `tests/` **42 个测试文件** |
| 既有文档 | 产品技术白皮书、开源互补项目扫描（2026-09-07）、各期部署日志 |

---

## 二、一句话结论

**产物很厚，暴露很薄；出海只做了一层，硬件只到了 Mock。**

- 后端已是一套相当完整的健康数据平台（41 路由、29 模型、15 引擎），但前端只把它们里的约 1/4 暴露给了用户 —— 其中恰恰包括**收款、数据入口、分享传播**这三条最影响商业闭环的链路。
- 新方向里的「国际化」目前只完成了 React SPA（`/app/`）那一层；真正带来自然流量的 **1255 篇 GEO/SEO 页面仍是纯中文**，且 `llms.txt` 也是中文 —— 对海外 LLM 引用的价值大打折扣。
- 硬件对接架构选型正确（Open Wearables，MIT，零许可费），但**真实设备零接入**，跑通的是 Mock。

结论：**当前瓶颈不在引擎能力，在产品面与出海面。** 继续堆引擎的边际收益已经很低。

---

## 三、产品完整性体检

| 维度 | 现状 | 关键证据 | 完整度 |
|---|---|---|---|
| 后端引擎 | 八轴融合 v0.6 + 中医 6820 实体 + PGx + 风险 + OCR + 审计 + 推演 | `core/` 15 引擎、`data/tcm_mkg` 6207 饮片 | **90%** |
| 前端暴露面 | 10 页面，每页平均 2.5 个 API 调用 | `client.js` 93 行 / ~25 端点 | **35%** |
| 数据入口 | 无任何上传 UI（报告 OCR / 基因组均无入口） | `grep upload` / `input:file` = **0 命中** | **10%** |
| 商业化闭环 | 后端有虎皮椒(CNY)+Creem(USD)+freemium+积分，前端无结账 | `grep payment/checkout` = **0 命中** | **20%** |
| 传播闭环 | `share_report` + `share_public` 后端就绪，前端无分享按钮 | `grep share` = 1 命中（非入口） | **15%** |
| 留存机制 | goals / notifications / adherence / points 全部有后端 | 前端对应页面 **0 个** | **15%** |
| 国际化 | SPA 完整 i18n（zh/en 各 ~380 key） | 10 页面 + 6 组件 + LanguageSwitcher | SPA **95%** / 内容 **5%** |
| 硬件集成 | OW 连接器 + Mock 端到端通（621 items） | 真实 provider OAuth **0 接入** | **30%** |
| 安全护栏 | 双层（提示词库 + 执行层）+ 4 轴红队 + 分诊闸门 | `safety.py` / `guardrail_prompts.py` / `redteam_eval.py` | **80%** |
| 可观测性 | 后端 Prometheus `/metrics` 就绪 | 前端**无埋点**，analytics 模块无消费者 | **25%** |
| 文档一致性 | 白皮书严重滞后 | 白皮书 v0.9.0 / fusion v0.3 / 6 页 / 15 模块 **vs 实际** v0.22.0 / v0.6 / 10 页 / 41 模块 | **30%** |

---

## 四、六个关键断层（按商业影响排序）

### 断层 1｜支付闭环断了 —— 有钱收不到
后端 `api/payment.py`（虎皮椒 + Creem）已注册，`freemium` / `points` / `tiered_growth` 三套积分与邀请逻辑齐备；前端 `grep payment|checkout` **0 命中**。
**后果**：无任何付费入口，出海最需要的 USD 通道（Creem）形同虚设，整个变现设计停在架构层。

### 断层 2｜数据入口断了 —— 最强引擎没有输入
平台差异化最强的三条链都需要「用户给数据」：PGx 需基因型文件、双轨诊断需体检报告 OCR、风险引擎需指标。而前端**没有任何文件上传控件**。
**后果**：用户只能靠 3 分钟自评问卷进入，核心能力（基因定制、报告解读）在真实使用中无法被触发。

### 断层 3｜传播闭环断了 —— 没有增长引擎
`share_report.py` + `share_public.py`（免登录分享页）后端已就绪，前端无分享入口。
**后果**：健康报告是这个品类天然的社交货币，分享是零成本获客主路径，目前完全未启用。

### 断层 4｜留存机制断了 —— 有数据飞轮没有召回
`goals` / `notifications` / `medication_adherence` 三个留存支柱后端齐全且已注册，前端**无对应页面**。
**后果**：打卡 → 趋势 → 推演的飞轮转起来了，但没有「回访理由」（目标提醒、通知、依从追踪），用户容易一次性使用后流失。

### 断层 5｜出海只做了一半 —— 有 SPA 没有内容
- ✅ SPA 层：react-i18next，zh/en 各约 380 key，10 页面 + 6 组件全覆盖，浏览器语言自动检测。
- ❌ 内容层：`sitemap.xml` 1255 条 URL **全部 `lang="zh-CN"`**，标题正文皆中文；`llms.txt` 中文；无英文内容管线（auto-pipeline 生成的是中文）。
**后果**：海外自然流量阵地（GEO/SEO 页面）与 AI 引擎引用入口（llms.txt）实际仍锁定中文市场。已投入的 i18n 工程只能服务「已进站的海外用户」，无法获客。

### 断层 6｜硬件停在 Mock —— 真实设备零接入
Open Wearables 连接器 + Mock 端到端已通（10 providers、621 items、7 类映射 6/6 通过），选型（MIT、自托管、零许可费）正确。
但：真实 provider OAuth **一个都没接**，且缺少出海最主流的两条路径 —— **Apple Health** 与 **Google Health Connect**。
**后果**：演示可用、真实用户不可用；且 ECS 1.9GB 内存（可用 479MB）不足以承载真实 OW 全栈。

---

## 五、技术债与一致性缺口

**1）9 个孤儿 API 模块（有 router 但未注册）**
`compliance_api.py`、`skills_api.py`、`pipeline_api.py`、`report_generator.py`，以及 `hl_*` 组合（`hl_agent` / `hl_compliance_api` / `hl_pipeline_api` / `hl_report_generator` / `hl_skills_api`）。
其中 `hl_*` 系列与独立的 `healthlens_agent/` 包属**重复实现**。→ 应收敛为单一实现，或正式挂载，避免「代码在仓库里但线上不存在」的持续误判。

**2）文档漂移（对外宣传风险）**
| 项 | 白皮书写的 | 线上实际 |
|---|---|---|
| 版本 | 0.9.0 | **0.22.0** |
| 融合引擎 | v0.3 | **v0.6** |
| 前端页面 | 6 页 | **10 页** |
| 路由模块 | 15 个 | **41 个** |
| API 端点 | 75+ | 41 路由（端点数更高） |
| 推理后端 | Ollama qwen3.8 + `150.158.119.19:8420/v1` | **qwen3.8 已删除；8420 无监听** |

白皮书是对外宣传与合作材料，引用已下线的模型与已停服的网关，属可被外部核查发现的硬伤。

**3）前端技术栈缺件**
无图表库（健康数据可视化为刚需）、无表单库（上传/问卷要手写）、无 PWA（移动端体验与推送缺失）、无 UI 组件库（一致性/a11y 成本高）。

**4）12 个前端源文件仍含中文硬编码**（多为注释与 TCM 术语，属合法保留，但需分类标注，避免后续误判为 i18n 漏网）。

---

## 六、开源技术借鉴路线

选型原则沿用既有约定：**MIT/Apache 优先、可自托管、零许可费、不与自研护城河冲突**。以下活跃度与许可均已实测核实（2026-09-23）。

### A. 出海内容层（P0 — 收益最大、成本最低）

| 开源项目 | 许可 | 借鉴点 | 落点 |
|---|---|---|---|
| **Argos Translate / LibreTranslate** | MIT / AGPL | 本地离线神经翻译，**零 API 成本**批量把 1255 篇中文 GEO 页转英文 | 新增 `tools/translate_geo_pages.py` + 内容管线加 en 分支 |
| **Astro** | MIT | 以静态站重建 GEO 层，原生 i18n 路由 + 更好的 Core Web Vitals | 替换现有 SEO 模板渲染 |
| **Open Food Facts** | **ODbL** | 400 万+ 商品、150 国、条码级营养与配料数据 → 食养/药食同源模块国际化 | `tcm_food_therapy.py` 接入条码查询 |
| **USDA FoodData Central** | 公有领域 | 无 share-alike 约束的营养基础数据，适合美国市场 | 与 OFF 互为备份 |
| **vite-plugin-pwa** | MIT | 免应用商店成本的移动端外壳 + 推送 | `frontend/` |

> ⚠️ **Open Food Facts 许可红线（必须诚实标记）**：数据库为 **ODbL**，图片为 CC-BY-SA。
> ① 必须显著标注来源；② **Share-Alike 传染性** —— 若把 OFF 数据与其他商品库混合成一个衍生数据库，该衍生库也须以 ODbL 发布。商业产品混库前需法务评估。若不可接受，改用 **USDA FoodData Central（公有领域）** 即可规避。

### B. 硬件接入层（P0 — 从 Mock 到真机）

| 路径 | 项目/协议 | 说明 |
|---|---|---|
| **第一步（最快、零 OAuth）** | **Apple Health XML 导出解析** | 用户手动导出 `export.xml` 上传即可接入，绕开 OAuth 审核与服务器成本，是出海冷启动最短路径 |
| **第二步** | **Google Health Connect**（Android 原生） | Android 侧标准入口，聚合三星/小米/Garmin 等已写入 HC 的数据 |
| **第三步（差异化）** | **Gadgetbridge**（AGPLv3，2026-08 发布 0.93.0，支持数百款设备） | 「数据不出手机」的隐私优先叙事，与 OW 自托管理念一致 |
| **聚合层（已用）** | Open Wearables（MIT） | 继续作为统一 provider 抽象 |

> ⚠️ **Gadgetbridge 为 AGPLv3**：只做**数据格式互通**（导出/解析），**不得链接其代码**，否则传染。定位为「用户侧工具推荐 + 格式兼容」。

### C. 安全护栏层（P1 — 从自研正则到可验证体系）

| 开源项目 | 许可 | 状态（实测） | 借鉴点 |
|---|---|---|---|
| **Microsoft Presidio** | MIT | v2.2.364，约 10.4K★，仓库已迁至 `data-privacy-stack/presidio`（社区共治，微软背书），镜像改为 `ghcr.io/data-privacy-stack/presidio-*` | **完全离线**的 PII 识别与脱敏（文本/图像/结构化）→ 直接替换自研 `find_pii` / `scrub_pii` |
| **Guardrails AI** | Apache 2.0 | v0.10.2（2026-06-04），约 7.3K★ | 声明式 output validator，可「校验失败自动重问」→ 比手写正则更可维护 |
| **garak**（NVIDIA） | Apache 2.0 | 约 8.8K★ | 对抗探测harness，把 `redteam_eval.py` 从 23 用例脚本升级为 **CI 内常跑** |
| **promptfoo** | MIT | 约 24K★ | 红队 + 回归，适合放进 CI（注意已被 OpenAI 收购，路线图独立性下降） |
| **Llama Guard 4**（12B） | Llama 许可 | 2025 年发布，原生多模态 | 本机 3090/4090 可自托管（40–80ms） |

> ⚠️ **两条必须诚实标注的边界**：
> ① **LLM Guard 已归档**，不要采纳（其曾是最常被推荐的护栏库）。
> ② **Llama Guard 4 不能当唯一防线**：2026-02 第三方测试显示其仅拦截 **66.2%** 的对抗提示（约 1/3 穿透），且有研究指出其表现不如通用 LLM 改装的判官。定位为纵深防御中的一层。

### D. 留存与增长基础设施（P1）

| 开源项目 | 许可 | 借鉴点 |
|---|---|---|
| **Novu** | MIT core（open core） | 一个 API 覆盖 In-Web/Email/SMS/Push/Chat + 可嵌入 Inbox 组件 + digest 聚合 → 直接支撑「目标提醒 / 依从追踪 / 打卡召回」 |
| **PostHog / Umami** | MIT 系 | 自托管埋点与漏斗，替代自研 `analytics.py` 的空转 |
| **Recharts / visx** | MIT | 补上健康数据可视化（八轴轨迹、指标趋势、打卡热力图） |
| **react-hook-form** | MIT | 上传表单与问卷（当前 0 表单库） |

> ⚠️ **Novu 许可细节**：核心为 MIT，但**自托管部署在官方定价页被标注为 enterprise-only**，企业包路径为专有许可（仓库 license 显示 NOASSERTION 即因混合许可）。采用前须核实当前版本的自托管条款边界。

### E. 明确不采纳（含理由）

| 项目 | 不采纳理由 |
|---|---|
| **LLM Guard** | 已归档，无维护 |
| **HAPI FHIR / FHIR 服务器** | 与去医疗化定位冲突，且引入 JVM 重依赖 |
| **OmniAge / 多组学时钟 / pypgx** | 需甲基化或原始测序数据，与当前输入边界不符 |
| **各 Symptom-Checker 诊断内核** | 与「不得诊断」红线直接冲突 |
| **Huatuo / 中医大模型权重** | 需 GPU、与自研护城河冲突；只借鉴其指令数据构建方法论 |
| **把生成类模型塞进 models.json** | 架构不匹配（沿用既有经验，生成模型应走 MCP/服务） |

---

## 七、优先级与收益 / 成本矩阵

| 优先级 | 动作 | 开源依赖 | 工作量 | 影响的商业指标 |
|---|---|---|---|---|
| **P0** | 接支付结账 UI（Creem 先） | — | 小 | **收入**从 0 到 1 |
| **P0** | 报告 OCR + 基因上传 UI | react-hook-form | 中 | **激活率**（核心能力可用） |
| **P0** | 分享报告入口 | — | 小 | **获客**（零成本裂变） |
| **P0** | GEO 内容英文化首批 200 页 + 英文 llms.txt | Argos Translate | 中 | **海外自然流量**从 0 到 1 |
| **P0** | Apple Health 导出解析 | 自研 parser | 中 | **硬件真实可用** |
| **P1** | 目标 / 通知中心 UI | Novu | 中 | **留存 / 复访** |
| **P1** | Presidio 替换自研 PII + garak 入 CI | Presidio, garak | 中 | **合规可信度**（出海刚需） |
| **P1** | 健康数据可视化 | Recharts | 小 | 付费转化（报告价值感） |
| **P1** | 9 个孤儿模块收敛 | — | 小 | 维护成本 / 文档可信 |
| **P2** | 白皮书对齐 v0.22.0 | — | 小 | 对外合作可信度 |
| **P2** | PWA + Health Connect 桥 | vite-plugin-pwa | 中 | 移动端留存 |
| **P2** | Gadgetbridge 格式互通 | AGPL 边界 | 中 | 隐私差异化叙事 |
| **P2** | 真实 OW 部署（需算力） | — | 大 | 硬件规模化 |

---

## 八、建议执行顺序（4 周，每周可独立验收）

**第 1 周｜打通三条断裂的商业链路**
支付结账 UI（Creem USD 优先）→ 报告 OCR + 基因上传入口 → 分享报告按钮 → 9 个孤儿模块收敛。
验收：能完成「上传报告 → 出方案 → 分享 → 付款」全流程。

**第 2 周｜出海内容层起步**
Argos Translate 离线翻译管线 → 首批 200 篇核心 GEO 页英文化 → 英文 `llms.txt` / `ai.txt` → 双语 sitemap（hreflang）。
验收：`curl` 抽查英文页 `lang="en"`，Google/Bing 索引到英文 URL。

**第 3 周｜硬件从 Mock 到真机**
Apple Health XML 导出解析（零 OAuth 最快路径）→ Health Connect 数据接入 → OW 连接器对接真实 provider 试跑。
验收：真实用户导出文件导入后，睡眠/活动数据进入八轴画像。

**第 4 周｜护栏与可信度加固**
Presidio 替换自研 PII → garak/promptfoo 进 CI → 白皮书对齐 v0.22.0 → 前端技术栈补件（Recharts + react-hook-form）。
验收：CI 内含对抗探测报告；白皮书数字与线上一致。

---

## 九、诚实边界与风险提示

1. **ODbL share-alike 传染**（Open Food Facts）：混库会要求衍生库同样开源，商业产品须先法务评估；规避方案是用公有领域的 USDA FoodData Central。
2. **AGPL 传染**（Gadgetbridge）：只做格式互通，不链接代码。
3. **Llama Guard 4 拦截率不足**（第三方实测 66.2%）：只能作为纵深防御的一层，不可替代确定性规则。
4. **Novu self-host 许可边界**：官方标注 enterprise-only，采用前需核实版本条款。
5. **出海合规不止翻译**：GDPR/CCPA、健康数据跨境传输、以及「TCM / 食养」在 FDA/EFSA 语境下同样**不得做疾病声称** —— 与国内去医疗化红线一致，英文文案需重新过一遍主张级审核，不能直译。
6. **算力约束**：ECS 1.9GB 内存（可用 479MB）已不足以承载真实 OW 全栈，真实硬件规模化需独立 VPS 或本机 GPU 分担。
7. **本次未做的验证**：未实测 Argos Translate 中文→英文在中医术语上的翻译质量，也未实测 Presidio 对中文健康文本的召回率 —— 两项都需在落地前用真实语料跑一次基线。

---

---

## 七、实施状态更新（2026-09-24 终版）

### 优先级完成情况

| 优先级 | 项目 | 状态 |
|:---:|---|:---:|
| **P0** | 支付（6 routes 双通道）✅ / 上传✅ / 分享✅ / 导出✅ / PWA✅ | **5/5 完成** |
| **P1** | 孤儿收敛✅ / PII✅ / CI/CD✅ / Agent编排✅ / i18n⚠️ | **4/5 完成** |
| **P2** | 白皮书✅ / 前端补件✅ / 测试⚠️ | **2/3 完成** |

### 关键修正（原评估事实错误）
1. **支付**：原称「0 routes」→ 实际 6 条路由（虎皮椒+Creem，¥9.9-¥999 三档）
2. **测试**：原称「59 空文件 / 0 真实测试」→ 实际 33 文件 / 137 passed
3. **PWA**：原称「icons placeholder」→ 已生成 3 PNG icons（含 maskable）
4. **前端架构**：healthlens.cc 部署 vanilla JS 静态站，React+i18n 前端仅在仓库

### 本轮新增
- docker-compose 添加 `./tests:/app/tests` 卷挂载
- 生成 icon-192x192.png / icon-512x512.png / icon-maskable-512x512.png
- 更新 manifest.json 含 maskable purpose
- 白皮书 v0.22.0 对齐，医疗术语 74→0
- PII sanitizer 重写（strict/loose 双模式）
- 孤儿模块 9 个收敛删除
- 翻译管线框架（26 条示例）

### GOAI 2026 对标落地（2026-09-24 补充）

对标 GOAI 2026 获奖项目，评估 6 个获奖项目对 HealthLens 的适配度，落地 1 项：

| 获奖项目 | 赛道 | 与 HealthLens 关系 | 落地 |
|---|---|---|---|
| **CyberGuard** | Agent Infra 季军 | 🔵 高 — 审计链完整性 | ✅ 已落地 |
| DataFlow-Agent | Agent Infra 冠军 | ❌ 不适配 — HealthLens 非 DAG 编排 | — |
| RepoMesh | Agent Infra 亚军 | ❌ 不适配 — 非多 Agent 交付 | — |
| Agentero | 无界应用 亚军 | ❌ 不适配 — 非科研工作台 | — |
| MirrorPeptidizer | 全场大奖 | ❌ 不适配 — 多肽设计 | — |
| MD Transformer | AI for Research | ❌ 不适配 — 分子动力学 | — |

**落地内容：HMAC 审计链完整性（对标 CyberGuard）**

给现有 `AuditEvent` 模型 + `runtime_audit.py` 增加防篡改保证：

| 改动 | 文件 | 说明 |
|---|---|---|
| 新增字段 | `app/models/audit_event.py` | `prev_hash` / `signature` / `signed_at` |
| HMAC 签名 | `app/services/runtime_audit.py` | 写入时链式签名，HMAC-SHA256 |
| 链验证 | `app/services/runtime_audit.py` | `verify_chain()` 校验完整性 |
| 验证端点 | `app/api/audit.py` | `GET /api/v1/audit/verify`（admin） |
| 密钥配置 | `app/config.py` | `AUDIT_CHAIN_SECRET` |
| DB 迁移 | `ALTER TABLE audit_events` | 3 新列，非破坏性 |

**验证结果：**
- ✅ 未篡改链 → verify OK
- ✅ 载荷篡改（detail）→ 检测到
- ✅ prev_hash 篡改 → 检测到
- ✅ 密钥错误 → 检测到
- ✅ 向后兼容（signature=None 视为 legacy 行）

### 待办
- i18n：healthlens.cc vanilla JS 前端无 i18n，React 仓库内已覆盖 10 页面
- 测试：30 个失败为 fixture 问题（KeyError: 'data'），需修复测试客户端
- 审计链密钥：生产环境需配置 `AUDIT_CHAIN_SECRET` 环境变量（当前使用 JWT 派生回退）

---

## GOAI 对标落地第二轮（2026-09-24 补充）

基于评估报告，全面实施 6 项改进。生产环境 ECS (150.158.119.19) 已部署验证。

### 实施清单

| 优先级 | 项目 | 状态 | 验证 |
|:---:|---|:---:|---|
| **P0** | 审计链 HMAC 签名 | ✅ 已部署 | 4 种攻击向量全部检测到 |
| **P0** | 生产配置加固 | ✅ 已部署 | `AUDIT_CHAIN_SECRET` 64 字符 / CORS 收紧 / `SMS_PRODUCTION_GUARD=true` |
| **P1** | OpenAPI 契约自动生成 | ✅ 已部署 | `GET /api/v1/spec` 192 路径 / 70 schemas |
| **P1** | 审计归档 + 巡检 | ✅ 已部署 | crontab 每日 03:00 巡检 |
| **P2** | API 限流 | ✅ 已部署 | auth 7 端点 + audit 2 端点 |
| **P3** | 合规扫描 | ✅ 已部署 | `POST /api/v1/compliance/scan` |

### 新增端点

| 端点 | 方法 | 权限 | 说明 |
|------|------|------|------|
| `/api/v1/spec` | GET | 公开 | 完整 OpenAPI 3.1 规范 |
| `/api/v1/spec/summary` | GET | 公开 | 端点摘要 |
| `/api/v1/audit/check-integrity` | POST | Admin | 主动巡检并记录 |
| `/api/v1/audit/integrity-history` | GET | Admin | 巡检历史 |
| `/api/v1/compliance/scan` | POST | 公开 | 合规扫描 |

### 生产配置加固

- `AUDIT_CHAIN_SECRET`: 64 字符强密钥（之前为空，空转）
- `CORS_ORIGINS`: 仅 `healthlens.cc` / `www.healthlens.cc`（去掉 localhost）
- `SMS_PRODUCTION_GUARD`: `true`（之前为 `false`，护栏关闭）
- `ENV=production` / `DEBUG=false`（已确认）

### 审计链巡检

```bash
# crontab（每天 03:00 UTC+8）
0 19 * * * /opt/healthlens/scripts/audit_integrity_cron.sh
```

巡检结果写入 `audit_events` 表（`event_type="integrity_check"`），形成可追溯的完整性证明链。

### 合规扫描

扫描项：
1. 审计链完整性（HMAC + prev_hash 校验）
2. 敏感操作（severity >= 3，24h 内）
3. 数据删除操作统计

当前状态：`compliance_status=ok`，`total_violations=0`

### 归档策略文档

`docs/audit_archive_policy.md`：90 天在线 + 7 年归档，月度归档流程，恢复流程。

---

*本更新基于 2026-09-24 的线上验证，所有数字可复现。*
