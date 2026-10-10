# HealthLens 全面提升评估报告

> 扫描日期：2026-10-08 ｜ 代码基线：HEAD `947a9f4`（55 次提交）｜ 在线实测：healthlens.cc 200 / api.healthlens.cc 200
> 评估方法：全量代码审计（4 路并行深度取证）+ 在线实测 + 国际市场与监管检索
> 评估原则：**只采信代码事实，不采信文档自述**

---

## 〇、执行摘要

### 一句话定位
HealthLens 想做的是**"用精准检测数据重构中医辨证体系"**——把基因、血液、影像、可穿戴等客观数据映射到「稳态生物学轴」（A–H 八轴），反推中医证候，输出千人千面的药食同源修复方案，靠数据飞轮持续变准。

### 一句话结论
> **工程外壳达到生产级，科学内核停留在原型级，商业与合规停留在纸面级。**
> 项目最大的资产是「架构正确 + 诚实降级 + 已上线」；最大的风险是**宣称的五层因果链与八轴融合引擎在代码中并不成立**——这是产品全部差异化叙事的地基。

### 完成度总评

| 维度 | 权重 | 完成度 | 判定 |
|---|---|---|---|
| 工程外壳（API/部署/监控/安全） | 15% | **80%** | 生产级 |
| 科学内核（算法真实性） | 25% | **25%** | 原型级 · **生死线** |
| 前端产品体验 | 15% | **40%** | 能跑通的外壳 |
| AI Agent / Skills | 10% | **30%** | 演示级 |
| 数据采集（连接器/OCR/硬件） | 10% | **25%** | 占位级 |
| 商业化 / 增长 | 10% | **35%** | 半成品 |
| 合规 / 安全 | 8% | **30%** | 高风险敞口 |
| 学术 / 验证 | 7% | **45%** | in-silico only |
| **加权总分** | 100% | **≈ 42%** | **MVP+，非产品化** |

### 三个必须先知道的真相

1. **八轴只有 1 轴能算。** `data/healthlens_config.json` 定义了 A–H 八轴，但全仓只有 `bioage_engine` 的第 9 轴（代谢-炎症）有打分器。`fusion_engine.recommend()` 的 `weak_axes` **完全由调用方传入**（`fusion_engine.py:334`），体检指标只能映射到 F、A 两轴。**B/C/D/E/G/H 六轴没有任何数据来源。**
2. **L1→L5 不是链，是三个并行的 API 注释器 + 一次不可用的 LLM。** `diagnosis_agent.py:236-242` 中 L1 查 ClinVar、L2 查 UniProt 且**不消费 L1 输出**、L3 靠用户自带 `uniprot_id`（否则写死 `status="unknown", score=50`）、L4/L5 交给 LLM，而 LLM 在当前配置下必然抛 `ValueError`（`.env` 无任何 LLM 凭证）。**PRINCIPLES.md 宣称的"从客观数据反推证候"在代码中没有任何反推逻辑。**
3. **测试门禁被三重架空。** `ci.yml` 用 `BASELINE=31`（31 个失败测试视为"正常"）判定，ruff `continue-on-error: true`，mypy 挂 `|| true`。**CI 实际不拦截任何东西。**

---

## 一、对标基准：先明确"核心目标"这把尺子

评估任何板块前，必须先把核心目标拆成可判定的子命题。从 `PRINCIPLES.md` 抽出 5 条：

| # | 核心目标命题 | 判定标准 | 现状 |
|---|---|---|---|
| G1 | 精准检测数据替代望闻问切 | 真连接器 ≥3 个且能跑通 OAuth | ❌ 5 个连接器 `fetch_health_data()` 全返回 `*_mock`；`.configure()` 零调用点 |
| G2 | L1→L2→L3→L4→L5 链式推导 | 相邻层有真实数据传递 | ❌ L1→L2 断开，L3→L4 靠 LLM 自由生成 |
| G3 | 八轴可测量 | 8 个轴各有独立打分器 | ❌ 仅 1 轴（且是第 9 轴） |
| G4 | 千人千面的药食同源方案 | 方案随输入实质变化 | ⚠️ 120 条真实证据库 + 集合交集匹配，无归一化/权重学习 |
| G5 | 数据飞轮 | 用户数据回填 → 模型变准 | ❌ 无闭环，无反馈训练路径 |

**G1–G3、G5 全部未达成，G4 部分达成。核心目标的达成度 ≈ 20%。**

这就是本报告所有建议的锚点：**先把 G1–G3 补齐，其余板块的优化才有意义。**

---

## 二、全景资产盘点（扫描结果）

### 2.1 代码资产

| 目录 | 文件 | 行数 | 性质 |
|---|---|---|---|
| `app/`（后端） | 165 py | 33,699 | 43 个路由模块，**211 个端点** |
| `frontend/` | 35 | 5,767 | 15 页 / 11 组件，纯 JSX |
| `healthlens_agent/` | 36 | 5,474 | safety/audit/pipeline/team/benchmark/flow/multimodal |
| `auto-pipeline/` | **1,104**（git 跟踪 154） | **409,835**（真实代码 11,819） | **97% 是 12 份重复构建产物** |
| `healthlens/`（旧副本） | 86 | 15,399 | 与 `app/` 并行，含**第二套 alembic** |
| `tests/` | 51 | 5,399 | 336 个 test 函数，937 处 assert |
| `edge/` | 10 | 1,358 | 脉象 DSP（真算法）+ 合成波形 |
| `mcp_servers/` + `mcp-server/` | 3 | 436 | 两套真实 JSON-RPC 实现 |
| `skills/` | 8 | 734 | 3 个 skill，均为关键词字典 |

### 2.2 数据资产（真实部分）

| 资产 | 规模 | 价值 |
|---|---|---|
| `case_evidence_db.json` | **120 条真实人体试验/RCT，带 DOI/期刊/年份/效应量/证据等级** | ⭐⭐⭐⭐⭐ 最硬资产 |
| `tcm_mkg/chp_entities.json` | 6.0 MB 中药知识图谱 | ⭐⭐⭐⭐ |
| `pulse_signatures.json` | 28 条脉象特征库 | ⭐⭐⭐（库缺失时**显式报错**而非造假，设计诚实） |
| `classical_books.json` | 701 条**书目元数据**（无正文） | ⭐⭐ |
| `tcm_structured/` | **仅 2 部全文**（神农本草经 150KB、食疗本草 94KB） | ⭐ |
| `tcm_pathway_map.json` | 8 轴 / 96 通路别名 | ⭐⭐⭐ |

> ⚠️ **README 宣称的"701 部中医古籍语料库"是目录不是语料**——701 条记录字段仅 `title/author/dynasty/year_text/category/source_file`，真正带全文的只有 2 部。这是对外叙事与事实的显著落差。

### 2.3 部署现状（实测）

```
https://healthlens.cc/                  → 200  ✅ "您的健康全景平台"
https://api.healthlens.cc/openapi.json  → 200  ✅ OpenAPI 3.1.0 / v0.22.0
https://healthlens.app/                 → 000  ❌ 连接失败（TLS/解析失败）
```
- `/api/v1/health`、`/docs` 返回 404（文档已关闭）
- Cloudflare Pages + GitHub Actions CD，10 个 workflow，含 `uptime-watchdog`（cron `*/30`）与 `scheduled-pipeline`（cron `0 */2`）
- 看门狗有**内容级身份校验**（`grep -q "HealthLens"` + 校验 llms.txt/sitemap/robots）—— 这条是真经验，源于"源站返回 200 但内容是另一个项目"的事故
- ⚠️ `app/api/growth.py:46` 分享域名**硬编码 `https://healthlens.app`**，而该域名当前不可达 → **外部分享链接全部失效**

---

## 三、板块级完成度评估与提升建议

### 板块 1：科学内核（融合引擎 / 五层链）— 完成度 25% · **P0 生死线**

**现状取证：**

| 模块 | 行数 | 判定 |
|---|---|---|
| `app/lib/fusion_engine.py` | 520 | ❌ 八轴无打分器；匹配是集合交集 `overlap * ew`；`score_formula` 只存在于 JSON，**后端从不读取该 config**（死配置） |
| `app/core/risk_engine.py` | 517 | ❌ 文件头称"基于 China-PAR"，实为**自造点量表**：`if age>=55: score+=3`；概率是分段线性拼凑（无 Cox 系数、无 S0(t)）。CDRS 同理。**唯一真实的是代谢综合征（CDS 五项阈值）** |
| `app/core/tcm_engine.py` | 488 | ⚠️ 体质转化分**是真的中华中医药学会标准公式** `(raw-n)/(n*4)*100`；但辨证置信度是 `0.4 + match*0.08 + tongue*0.05 + pulse*0.03` 的**拍脑袋加权**；方剂未命中时**永远返回四君子汤** |
| `app/core/pgx_engine.py` | 342 | ✅ **最真实**（CPIC 活性评分法）。⚠️ Bug：`phenotype_map` 区间重叠，AS=0.5 判为 PM（CPIC 应为 IM） |
| `app/core/bioage_engine.py` | 221 | ⚠️ 明确声明"非 DNAm PhenoAge"（诚实 ✔），但 8 项扣分表 + 年龄偏移系数 1.0/1.5/3.0/5.0 **全为自定，无拟合数据** |
| `app/core/tcm_tongue_analyzer.py` | 206 | ❌ 200×200 缩略图 RGB 均值 + 手写阈值；舌形靠亮度猜（`brightness>180 → 胖大`）；舌下络脉**硬编码"未检测"** |
| `app/core/diagnosis_engine.py` | 178 | ❌ 置信度**硬编码 0.65**，7 条 LOINC→ICD 查表 |
| `app/lib/wellness_simulator.py` | 333 | ⚠️ 自造线性差分模型，耦合系数写死 0.12/0.10/0.10/0.12/0.10；但 docstring 诚实标注"启发式/非临床" ✔ |

**外部知识库接入：** `app/services/bio_database.py` 有**真实 httpx 调用** UniProt / NCBI E-utilities(ClinVar) / KEGG / STRING，带 24h TTL 缓存 + 按域限流 3 req/s。工程质量真实。
❌ 但**全仓只有 `diagnosis_agent.py` 一个调用方**，`app/core/` 下所有引擎一处都不调用；**AlphaFold 零命中**（PRINCIPLES.md 提及但代码不存在）。

**提升建议：**

| 优先级 | 动作 | 验收标准 |
|---|---|---|
| **P0-1** | **八轴打分器工程**：为 B/C/D/E/G/H 六轴定义可计算的数据来源与公式（HRV→G 轴、睡眠/皮质醇节律→D 轴、hs-CRP/IL-6→F 轴、NAD+/mtDNA→B 轴…），每轴至少一个可验证代理指标 | 8 轴各有独立 `score_axis()` 且有单元测试；单轴缺失时显式标记 `unmeasured` 而非填 0 |
| **P0-2** | **修好 L1→L2→L3 链路**：`_annotate_proteins` 消费 `_annotate_variants` 输出；L3 用 UniProt→KEGG 自动解析，不依赖用户传 `uniprot_id` | 输入基因列表能端到端产出 L1/L2/L3 三份带引用的结构化结果，无 `unknown` 占位 |
| **P0-3** | **L3→L4 建立可审计映射**：用 `tcm_pathway_map.json`（96 别名）+ 120 条证据库构建通路→证候的**规则化映射表**，LLM 只做措辞润色不做判定 | 映射表可导出为 CSV 供专家评审；LLM 不可用时结果不降级为"待 AI 分析" |
| **P0-4** ✅ 已完成 (2026-10-09) | **替换伪 China-PAR**：接入真实 Pooled Cohort / China-PAR 系数与基线生存函数，或**在 UI 与论文中明确改称"自评风险量表"** | 二选一必须完成；禁止"挂名已发表模型" → **走"改称自评量表"路径**：`risk_engine.py` 三引擎改名自评量表、返回体加 `disclaimer` 字段、`risk_type` 改 `ascvd_self_assess`/`diabetes_self_assess`；API 层与 MCP 层同步返回 disclaimer；README/CHANGELOG/白皮书全部改口径；代谢综合征保留 CDS 真实阈值。**未接入真实 China-PAR 系数**（数据授权成本大，Roadmap 保留）。 |
| **P1** | 修复 `pgx_engine` 表型边界 Bug；用药建议改为 CPIC gene-drug 逐条而非按表型套模板 | AS=0.5 → IM；CYP2D6/他莫昔芬 与 CYP2D6/可待因 给出相反方向的建议 |
| **P1** | 舌诊升级为**色彩空间 + 纹理特征**（Lab 色彩 + 舌苔覆盖率 + 齿痕检测），或**诚实下架** | 二选一 |
| **P2** | `wellness_simulator` 参数拟合：用 120 条证据库的效应量做标定 | 输出带置信区间 |

---

### 板块 2：数据采集（连接器 / OCR / 硬件）— 完成度 25% · **P0**

**现状取证：**
- **5 个连接器全为占位**：`huawei_health.py:103 "source": "huawei_health_mock"`、`withings.py:96 "withings_mock"`、`xiaomi_health.py:85 "xiaomi_health_mock"`，注释直书 `"Phase 1: 返回模拟数据结构"`
- **决定性证据**：全仓 `app/` 内 `.configure()` **零调用点** → OAuth 凭据从未注入，`client_id` 始终为 `None`，**OAuth 流程从未跑通过一次**
- `apple_health.py`: 3 个 `NotImplementedError`，唯一真实代码是 HealthKit XML 导出解析 + 10 项 LOINC 映射
- **OCR 会伪造数据**：`ocr_engine.py:43` Tesseract 缺依赖时**静默返回假体检报告**（固定"血糖 6.8、胆固醇 5.8"）。若生产环境缺 `pytesseract`/`pdf2image`，用户上传真实报告会看到**伪造数值** —— 这是**医疗级事故隐患**
- **P0-5 级 Bug**：`frontend/src/pages/Upload.jsx:38` 声明 `fileInputRef`，第 101 行**从未赋值 `fileInputRef.current`**，第 111 行 `fileInputRef.current?.click()` 永远为 null → **三个上传按钮全部点了没反应**，基因组/Apple Health/Google Fit 上传完全不可用
- `edge/pulse_source.py` 的 DSP 特征提取**是真实算法**（局部极大检测 + NMS 非极大抑制 `min_dist=0.4s` 避免脉率翻倍 + RR 间期中位数离群剔除 + h3/h1、h5/h1、升支斜率）—— 但默认走 `synthesize_ppg()` 合成波形，仓库内无固件、无 `.jsonl` 回放样本

**提升建议：**

| 优先级 | 动作 | 验收标准 |
|---|---|---|
| **P0-5** | **修 Upload.jsx 的 ref 未赋值 Bug**（10 行改动，当前整页不可用） | 三个上传入口可真实选文件并回调 |
| **P0-6** | **OCR Mock 必须 fail-loud**：缺依赖时抛出明确错误并提示，绝不返回假数值 | 生产环境 OCR 不可用时返回 `503 + 明确文案`，禁止任何固定数值回落 |
| **P0-7** | **打通 1 个连接器做到真实**：优先 Withings（有开放 API、OAuth2 文档完整、覆盖体重/血压/睡眠/活动） | 完整 OAuth 授权→回调→拉取→入库→趋势展示全链路可用 |
| **P1** | 接入 **Apple HealthKit XML 导入**作为无 OAuth 的降级路径（用户手动导出 XML 上传） | 支持标准 `export.xml` 解析 ≥10 类指标 |
| **P1** | 硬件：提供**脉象 `.jsonl` 回放样本集** + 串口协议文档，让 edge 链路可被第三方复现 | ≥20 条真实/半真实波形样本入库 |
| **P2** | Huawei / Xiaomi 走各自开放平台正式申请（需企业资质） | — |

---

### 板块 3：前端产品 — 完成度 40%

**亮点（高于平均）：**
- 15 个页面**全部真实可交互，无 "coming soon" 占位页**
- i18n：中英各 **702 个叶子键、24 个顶层 section，键集完全对齐** ✔
- PWA 三件套齐全（manifest / sw.js / offline.html）

**致命问题：**

| 问题 | 证据 | 影响 |
|---|---|---|
| **移动端无导航** | `App.jsx:59 <nav className="hidden md:flex">`，无汉堡菜单/底部 Tab 兜底 | 移动端**完全无法导航** |
| **无路由守卫** | `App.jsx` 读 token 只切换按钮外观，`/profile`、`/reports`、`/payment` 未登录也能渲染 | 越权访问 |
| **token 永不刷新** | `client.js` 定义了 `refresh` 但**从未被调用** | 用户静默掉线 |
| **后端 75% 功能无 UI** | 211 个端点，前端仅消费 ≈52 个（25%） | `gdpr.py`(7)、`repair.py`(6)、`medications.py`(7)、`frequency.py`(6) 等全无入口 |
| **支付价格硬编码** | `Payment.jsx` 内写死 `¥39.9 / ¥79.9 / ¥199`，不走 `payment/packages` | 改价需发版 |
| **前端调了不存在的端点** | `client.js:73 paymentFeatures → /payment/features`，后端只有 `/packages` | 套餐加载静默失败 |
| **SW 缓存失效** | `sw.js` 判断 `url.pathname.startsWith('/app/api/')`，实际 API 基址是 `/api/v1` | 离线能力为死代码 |
| **a11y 近零** | 25 个文件中 13 个 `aria-*` 命中数为 0；无 skip-link、无 focus trap | 无障碍合规风险 |
| **SEO 资产为零**（SPA 层） | 无 og:/twitter:/canonical/JSON-LD；SPA 纯客户端渲染 | 不可被索引 |
| **TS 是僵尸依赖** | `devDependencies` 有 typescript，`src/` 下 **0 个 .ts/.tsx** | — |
| **零测试** | 无 vitest/jest/playwright，`src/` 下 0 个测试文件 | — |
| **lint 配置缺失** | `package.json` 有 `"lint": "eslint src/"` 但 **eslint 不在依赖中，无配置文件** | `npm run lint` 必报错 |
| **react-query 空转** | 装了 5.51.21，全库**零处 `useQuery`** | 纯装饰 |

**提升建议（P0/P1）：**
- **P0-8** 移动端导航（底部 Tab / 汉堡菜单）+ 路由守卫 + token 自动刷新
- **P0-9** 修 SW 路径判断；补 og:/canonical/JSON-LD；补 `robots.txt`/`sitemap.xml`（服务端已有，SPA 需对齐）
- **P1-10** 补齐 `gdpr.py`（数据导出/删除——**合规硬需求**）与 `repair.py`（细胞修复，**论文核心卖点却无界面**）的 UI
- **P1-11** 引入 TypeScript（渐进式 `.jsx → .tsx`）+ Vitest 冒烟测试 + 修复 eslint 配置
- **P1-12** 价格/套餐改为后端驱动；修正 `/payment/features` 端点
- **P2** a11y 补 `aria-label` + `aria-live`；基于 `frontend/api-contract/openapi.json`（173KB）做类型生成

---

### 板块 4：AI Agent / Skills / MCP — 完成度 30%（MCP 单项 65%）

**分层判定：**

| 子层 | 判定 | 证据 |
|---|---|---|
| **MCP Server** | ✅ **真实协议** | JSON-RPC 2.0，`protocolVersion: "2024-11-05"`，`tools/list` + `tools/call`，标准错误码 -32601/-32602/-32603，**10 个工具三层分级**，优先用官方 `mcp` 包、缺失时降级自研 stdio（正确的双路径设计）。`mcp-server/server.json` 是官方 Registry schema，声明 PyPI + OCI 双分发 |
| **安全闸门** | ⚠️ **半真实** | `safety.py` 529 行，9 条 typed GuardRule，覆盖 8 组真实急症（胸痛/呼吸困难/卒中/大出血/意识丧失/自杀/抽搐/急性过量，含量词正则 `一次\s*(吃了?|服用了?)\s*\d+\s*(片|粒|颗|瓶)`）+ 10 条橙牌分诊 + 11 类 PII 正则。**但本质仍是正则表，对否定句（"我没有胸痛"）、同义改写零鲁棒性** |
| **四角色 Agent** | ❌ **DEMO，无 LLM** | `healthlens_agent/` 全目录**无任何 LLM 客户端调用**。Planner=关键词字典子串匹配；Executor=`scores = {h: 0.35 for h in ...}` **所有命中通路写死 0.35**；Critic=`score=100` 后固定扣分表；Referee=4 个 if 分支。`team_run()` 是**单次单向管道**，Critic 判 REVISE 后**不回灌 Executor**，直接返回 `output: None` |
| **Benchmark** | ❌ **自指涉** | 6 条作者手写探针，实测指标仅 3 个；**GOAI 七维度分数是硬编码常量 `70,45,35,65,55,75,60`**；`audit_unsafe_rate = audit_events/(total*2)` 分子分母不同量纲，无统计意义。**自己出题、自己判卷、自己打分** |
| **skills/** | ⚠️ 薄封装 | `tcm_text_mining` 是 3 个字典（23/14/12 项）+ 逐句子串查找，无分词无 NLP；`fusion_inference` 是 importlib 转发层；测试共 ~60 行，仅在作者构造样本上 assert，**无独立测试集、无准确率指标** |

**提升建议：**
- **P0-13** 四角色 Agent 接**真实 LLM**（保留规则引擎为降级），并实现 Critic→Executor 的**真闭环迭代**（最多 N 轮 + 收敛判定）
- **P0-14** Benchmark 去自指涉：构建 ≥100 条**独立标注测试集**（含红牌/橙牌/正常/对抗/否定句），七维度分数改为**实测计算**，launch-risk 公式修正量纲
- **P1-15** MCP 是**本项目最被低估的真资产**，应战略加注：补齐 L3 工具鉴权文档、发布到官方 MCP Registry、提供 Claude/Cursor 一键配置、写 `llms.txt` 面向 Agent 的能力说明
- **P1-16** 版本漂移：`pyproject.toml` 0.8.2 vs `config.py` 0.22.0 vs `server.json` 0.3.0 vs README 0.9.0 vs PRINCIPLES 0.16.0 —— **统一单一版本源**
- **P2** skills 升级为真实 NLP（术语词典 + 分词 + 否定检测），建立准确率基准

---

### 板块 5：商业化 / 增长 — 完成度 35%

**已实现（质量高于预期）：**
- 支付：虎皮椒（微信/支付宝 CNY）+ Creem（USD）
- **Creem webhook 做了 HMAC 验签 + store_id 隔离 + user_id 二次归属 + 幂等发分 + 发分失败 fail-loud** —— 这是认真写的代码 ✔
- 增长机制真实：邀请码、阶梯奖励、排行榜/渠道/漏斗、`share_report.py` 免登录分享页
- **GEO/SEO 是重投入且意识领先**：`seo.py`(564行)、`geo_infra.py` 提供 `/llms.txt`、`/ai.txt`、`/robots.txt`、动态 `/sitemap.xml`、`seo_factory.py`(63KB)

**关键缺口：**

| 问题 | 证据 | 影响 |
|---|---|---|
| **无订阅制** | 全仓 `subscription` 仅 1 处命中（webhook 事件名字符串） | 商业模式是"一次性积分充值"（¥9.9/¥39.9/¥129.9/¥299.9 四档），**与国际竞品的 membership 模式不一致，LTV 模型弱** |
| **Creem 是死代码路径** | `config.py:101 CREEM_ENABLED=False`，`.env` 24 个键中**无任何 `CREEM_*`** | 国际支付不通 |
| **增长数据造假** | `app/api/growth.py:17-22` `DEMO_REFERRALS = {"total_invited": 3, "rewards_earned": 150...}`，服务异常时**直接返回编造数字** | 投资人看板会显示虚构邀请数 |
| **分享域名失效** | `growth.py:46` 硬编码 `https://healthlens.app`（实测 000 不可达） | **所有外部分享链接失效** |
| **无检测供应链** | 依赖用户自行上传 PDF | 与国际竞品核心（lab/imaging 履约）的根本差距 |

**提升建议：**
- **P0-17** 删除 `DEMO_REFERRALS` 硬编码假数据，改为返回 `null` + 明确空态
- **P0-18** 修正分享域名为 `healthlens.cc` 并配置化
- **P1-19** 引入**订阅制**（月/年 membership），与积分制并行；对标 Function Health $365/yr、Superpower $349/yr
- **P1-20** 打通 Creem 国际支付（或评估 Stripe/Paddle），支撑出海
- **P1-21** 检测履约：与国内第三方检验机构（如金域/迪安/美年）或上门采血服务做 API 对接，把"用户自己上传"升级为"平台下单→采样→回传"
- **P2** GEO 加注：面向 ChatGPT/Perplexity/豆包 的结构化内容（已有 llms.txt/ai.txt 基础，可扩展 Schema.org + 权威引用）

---

### 板块 6：合规 / 安全 — 完成度 30% · **高风险敞口**

**真实实现：**
- `app/utils/pii_sanitizer.py` 真实现（手机号/身份证 GB11643 校验位/银行卡 Luhn/护照/车牌），双档 strict
- `gdpr.py` 有真导出（JSON+CSV）、真删除（软删+邮箱脱敏）、DPIA、权利清单
- `app/core/desensitize.py` 三级脱敏网关（mask/pseudonymize/anonymize）
- 红牌拦截 + 去医疗化文案（`MedicalDisclaimer.jsx` 已刻意去除"医疗"表述）

**硬伤：**

| 问题 | 证据 | 风险 |
|---|---|---|
| **同意状态存内存** | `gdpr.py:59 _consent_store: dict = {}`，注释自认"简化实现…应持久化"。**重启即丢、多 worker 不一致** | GDPR 同意记录**不可审计**，且无 UI 入口 |
| **HIPAA / PIPL 零实现** | 全仓代码命中数 **0**，仅在 .md 中被反复提及 | 出海/国内合规均无落地 |
| **命名规避 ≠ 实质合规** | 靠禁用"诊断/处方"等词规避器械监管，但 `pgx_engine.py` 仍在输出**致病性分级** | 各国监管看的是 **intended use 与实质功能**，不看用词 |
| **DPIA 自评 `residual_risk: "Low"`** | 无第三方审计支撑的自我声明 | — |
| **`.env` 有明文密钥** | `JWT_SECRET_KEY=healthlens-dev-secret-key-2026-08-28`（未被 git 跟踪 ✓） | 仅本地风险 |

**监管窗口（2026 最新，重要）：**
- **FDA 2026-01-06 更新 General Wellness 指南**：鼓励健康生活方式、与诊断/治疗无关的软件**可排除在器械定义外**；2026-01-29 更新 Clinical Decision Support 指南。**判断依据是 intended use 与宣传口径，功能逐个判定**
- **EU AI Act**：2026-05-07 "Digital Omnibus on AI" 确认——AI 赋能的医疗器械/IVD **确认为高风险**，但**适用日期从 2027-08-02 推迟到 2028-08-02**；独立高风险 AI 系统从 2026-08-02 推迟到 **2027-12-02**
- 台湾地区：AI/ML 医疗软件须走医疗器械法产品注册

> **结论：HealthLens 当前定位（健康管理、非医疗）在 FDA General Wellness 下是可行的，但前提是严格守住"不诊断、不治疗、不输出疾病名/药物处方"——而 PGx 致病性分级与 ICD-11 映射正在突破这条线。**

**提升建议：**
- **P0-22** 同意状态持久化到数据库 + 提供 UI 入口（当前 GDPR 7 个端点零 UI）
- **P0-23** **合规红线重构**：明确"去医疗化"的技术边界——PGx 输出改为"代谢倾向说明"而非"致病性分级"；ICD-11 映射仅在内部留痕，不对用户输出
- **P1-24** 建立 intended use 声明文件 + 逐功能合规判定表（对齐 FDA General Wellness 四要素）
- **P1-25** 出海路径：先做 GDPR（同意持久化 + DPIA 真审计），EU AI Act 高风险条款有到 2028-08 的窗口期
- **P2** 等保三级 / ISO 27001 / SOC 2 路线图

---

### 板块 7：工程成熟度（测试/CI/仓库）— 完成度 45%

**问题清单：**

| 问题 | 证据 |
|---|---|
| **测试门禁被三重架空** | `ci.yml` `BASELINE=31`（31 failed 视为正常）；ruff `continue-on-error: true`（自述"约 420 项历史 lint 债务"）；mypy 挂 `\|\| true` |
| **两套 alembic 已分叉** | `alembic/versions/` 4 个 vs `healthlens/alembic/versions/` 4 个；`app/models/` **53 个 `__tablename__`** 对 4 个迁移 → **模型与迁移不同步** |
| **auto-pipeline 97% 是垃圾** | 26MB / 409,835 行中真实代码仅 11,819 行；12 份**字节级完全相同**的 dist 副本；`.gitignore:67` 有 `!auto-pipeline/dist/` 例外但 `git ls-files` = 0（规则自相矛盾） |
| **95 项变更未提交** | 含 `D app/api/pipeline_api.py`、`D app/api/skills_api.py` 等 **9 个删除的 API 文件** |
| **根目录垃圾** | `fix_tests.py`/`fix_tests2.py`/`fix_tests3.py`、空文件 `0.19.0` |
| **历史伪造自动化** | `phase_7_feedback/run.py` 自述"此前此文件仅做 `path.exists()` 检查便上报 `available`，6 个业务子模块从未被…" |
| **单人项目** | 55 次提交 / 3 个月；贡献者 = lm203688(24) + 部署 bot(23) + bot(5) + agent(2) + WorkBuddy(1) |

**提升建议：**
- **P0-26** 拆掉 `BASELINE=31`，改为"零失败 + 覆盖率阈值"；ruff/mypy 改为硬门禁（可接受一次性 `ruff --fix` 批量清理）
- **P1-27** 合并两套 alembic，用 `alembic check` 或 autogenerate 校验模型-迁移一致性并加入 CI
- **P1-28** 清理 `auto-pipeline/dist*`（26MB）与根目录临时脚本；删除空文件 `0.19.0`；提交或明确废弃 9 个已删 API
- **P1-29** 版本单一真源（见 P1-16）
- **P2** 引入 pre-commit + 依赖锁定；`requirements.txt` 与 `pyproject.toml` 对齐

---

### 板块 8：学术 / 验证 — 完成度 45%

**科学主张**：ISSBF 框架，把中医气/血/脏腑/阴阳公理化为稳态生物学轴 + SIIV 闭环。**方向有原创性**。

**验证数据 = in-silico 合成，无人体：**
- 22 个**合成**画像；`engine_validation_metrics.json`：`determinism_rate 1.0`、`mean_personalized_control 0.0`、`convergent_validity_rate 0.848`
- 论文第 8 节自限"**不代表所推荐干预的人体有效性**" —— 诚实 ✔
- "真实世界案例证据库 n=29" = **文献引用库**，非患者队列；参考文献仅 24 条
- 产物齐全：补充数据 CSV(177行)、IMR 投稿包（含 Figure1 + DOI 验证报告）、medRxiv 投稿包。**未见已发表/接收证据**

**内部矛盾（重要）：**
> 论文摘要与 §3 表是**十轴（A–J）**，§1 引言却写"**八条**可测量的稳态生物学轴"；而**代码只有八轴 A–H** → **I/J 两轴论文里有、代码里没有**。

**提升建议：**
- **P0-30** 统一轴数（论文十轴 vs 代码八轴），否则学术主张与产品实现互相证伪
- **P1-31** 从 in-silico 走向**前瞻性真实用户研究**：即使 n=30 的自身前后对照（pre/post 干预，8–12 周）也是质的飞跃。这是把"假说"变成"证据"的唯一路径，也是与国际竞品拉开差距的关键
- **P1-32** 120 条证据库是**最硬资产**，应：① 建公开可引用的数据集（已有 `publish-dataset.yml` workflow）② 扩展至 ≥300 条 ③ 加系统综述方法学声明（PRISMA）
- **P2** 预注册（OSF/ClinicalTrials.gov）+ 与高校/医院合作获取伦理审批的真实队列

---

## 四、国际市场竞品对标

### 4.1 竞品格局（2026）

| 竞品 | 模式 | 价格 | 核心能力 | HealthLens 差距 |
|---|---|---|---|---|
| **Function Health** | 会员制血液检测 | **$365/yr** | 100+ 生物标志物，1 年 2 次，医师解读 | 检测履约、医师网络、纵向对比 |
| **Superpower** | 会员制 | **$349/yr** | 100+ 标志物 + 补剂推荐 | 同上；性价比竞争（43.8 vs 28.7 标志物/$100） |
| **Neko Health** | 全身扫描 | **$499/次** | 传感器一体扫描 + AI，瑞典/英国 | 硬件 + 影像 AI |
| **Prenuvo / Ezra** | 全身 MRI | $1,199–$4,999 | 影像级早筛 | 重资产影像 |
| **Zoe** | 微生物组 + CGM | 订阅 | 肠道菌群 + 血糖个性化营养 | 硬件 + RCT 级研究 |
| **Levels** | CGM 代谢 | 订阅 | 连续血糖 + 教练 | 硬件 + 社区 |
| **InsideTracker** | 血液 + DNA | 分层 | 生物标志物 + 基因 + 行动建议 | 最接近 HealthLens 定位 |
| **Lifeforce** | 高端会员 | ~$129/mo | 检测 +  concierge 医师 | 服务履约 |
| **Oura / WHOOP** | 可穿戴订阅 | $–$$/mo | HRV/睡眠/恢复，千万级用户 | 硬件 + 数据飞轮 |

**市场规模**：Personalized Testing & Supplements 2026 年 **$182.6 亿**，预计 2030 年 **$360.1 亿**（CAGR ~18.5%）。

### 4.2 竞品共同的成功要素（HealthLens 对照）

| 要素 | 竞品 | HealthLens |
|---|---|---|
| ① **检测履约闭环**（下单→采样→实验室→回传） | ✅ 全有 | ❌ 靠用户上传 PDF |
| ② **订阅制 / 会员制** | ✅ 全有 | ❌ 一次性积分充值 |
| ③ **纵向趋势**（每年 2 次对比） | ✅ 全有 | ⚠️ 有 observations 趋势 API，但数据进不来 |
| ④ **人类专家履约**（医师/ND/教练） | ✅ 全有 | ❌ 无 |
| ⑤ **真实世界研究 / 发表** | ✅ Zoe/RCT、Function/队列 | ⚠️ in-silico only |
| ⑥ **硬件或独家数据** | ✅ 全有 | ❌ 连接器 mock |
| ⑦ **监管清晰**（ wellness 边界 / CLIA / CE ） | ✅ | ⚠️ 靠改词规避 |

### 4.3 HealthLens 的**真实差异化**（全球空白）

1. **中医 × 稳态生物学的轴映射**——国际上没有竞品在做。Function/Superpower 只做"指标异常→补剂"，HealthLens 做的是"指标→通路→证候→药食同源"，**叙事层级更高**。
2. **非药物 / 药食同源干预**——竞品几乎全部导向补剂销售（合规与副作用风险高），HealthLens 导向食物、穴位、八段锦、作息，**边际成本近零、监管风险低**。
3. **古籍语料 + 120 条证据库**——可成为独有的知识资产。
4. **MCP / Agent 生态**——竞品无 MCP 布局，这是 2026 年的窗口期。
5. **GEO 领先意识**——已有 `/llms.txt`、`/ai.txt`。

> **但差异化必须建立在"轴能算出来"之上。** 当前 8 轴只有 1 轴有打分器、L3→L4 无映射——**叙事是 10 分的，实现是 2 分的**。这是全项目最大的"宣称-实现落差"，也是投资人与审稿人一击致命的地方。

### 4.4 中医 AI 赛道的国内外环境

- 2026 年国内中医 AI 已从"概念验证"进入"实战比拼"：互联网大厂（通用基座）+ 高校科研机构 + 垂直创业企业三条路线
- 中国中医科学院提出 20 年技术路线图：从"症状→方剂"端到端黑箱，**转向"辨证→立法→用方"的思维链透明化**——**这与 HealthLens 的诉求完全一致，是可引用的权威背书**
- 2024-07 国家中医药管理局 + 国家数据局《关于促进数字中医药发展的若干意见》：3–5 年目标
- **国际化阻力**：西方主流体系基于循证医学（EBM）的标准化要求，中医出海必须提供可量化的机制解释与临床终点——**这正是"稳态生物学轴"理论的价值所在，也正因如此，它必须被真正实现而非仅被宣称**

---

## 五、最新技术趋势对标（2026）

| 趋势 | 现状 | 对 HealthLens 的启示 |
|---|---|---|
| **多组学 / 蛋白质组学年龄时钟** | 2026-08 *Nature Medicine*：一滴血评估全身**器官年龄**；OMICmAge（多组学 + EHR）；蛋白质组学时钟对死亡预测性能可比经典生活方式因素 | HealthLens 的 `bioage_engine` 是 8 项自造扣分表。**应对齐/替换为有外部验证的时钟，或明确标注差异**——这是最容易补的学术短板 |
| **FDA 2026-01 双指南更新** | General Wellness（01-06）+ Clinical Decision Support（01-29）；按 intended use 逐功能判定 | **利好**：守好 wellness 边界即可豁免。但 PGx 致病性分级越线，需整改 |
| **EU AI Act 医疗器械条款推迟** | 高风险条款 2028-08-02 适用（原 2027-08）；独立高风险 AI 2027-12-02 | **窗口期约 2 年**，出海可先做 GDPR，AI Act 文档并行准备 |
| **MCP 生态成熟** | 协议版本 2024-11-05；Registry schema 2025-12-11；主流 Agent 客户端全面支持 | **HealthLens MCP 是真资产，应立即加注**：发布 Registry、提供一键配置 |
| **Agent 从"演示"走向"闭环"** | 行业已从单轮 prompt 转向 plan-execute-critic 真迭代 + 工具调用 + 可验证轨迹 | HealthLens 的四角色是**单向管道且无 LLM**，落后一代。P0-13 必做 |
| **连续监测（CGM/HRV/睡眠/血压）** | 可穿戴数据成为健康平台主要数据源 | 连接器是 HealthLens 最大短板（G1 未达成） |
| **GEO / AI 搜索优化** | `llms.txt`、`ai.txt` 成为新标准 | HealthLens 已有，**领先意识值得肯定，应继续加注** |

---

## 六、全面提升路线图

### 阶段一：止血与证伪清零（0–30 天）· 目标：消除"不可使用/不可信"

| # | 动作 | 板块 |
|---|---|---|
| P0-5 | 修 `Upload.jsx` ref Bug（整页不可用） | 前端 |
| P0-6 | OCR Mock 改 fail-loud（禁止伪造检验数值） | 数据 |
| P0-17 | 删除 `DEMO_REFERRALS` 假数据 | 商业 |
| P0-18 | 修正分享域名 `healthlens.app` → `healthlens.cc` | 商业 |
| P0-26 | 拆掉 `BASELINE=31`，CI 改零失败硬门禁 | 工程 |
| P0-22 | GDPR 同意持久化到 DB + UI 入口 | 合规 |
| P0-30 | 统一论文十轴 vs 代码八轴 | 学术 |
| P0-23 | PGx 输出去"致病性分级"，守住 wellness 边界 | 合规 |

**阶段一出口标准**：无已知 P0 级功能故障；无伪造数据路径；CI 真实拦截；对外叙事与代码无直接矛盾。

### 阶段二：把地基补实（1–3 个月）· 目标：让核心目标 G1–G3 成立

| # | 动作 | 板块 |
|---|---|---|
| **P0-1** | **八轴打分器工程**（B/C/D/E/G/H 六轴补数据来源与公式） | 科学内核 |
| **P0-2** | **修好 L1→L2→L3 数据传递**，去掉 `unknown` 占位 | 科学内核 |
| **P0-3** | **L3→L4 规则化映射表**（LLM 只润色不判定） | 科学内核 |
| **P0-7** | 打通 1 个真实连接器（优先 Withings） | 数据 |
| **P0-13** | 四角色 Agent 接真实 LLM + Critic→Executor 真闭环 | AI |
| **P0-14** | Benchmark 去自指涉（≥100 条独立测试集，分数实测） | AI |
| P0-8 | 移动端导航 + 路由守卫 + token 刷新 | 前端 |
| P0-4 ✅ 已完成 (2026-10-09) | 替换伪 China-PAR 或改称"自评风险量表" | 科学内核 |

**阶段二出口标准**：输入一份真实体检报告 + 基因数据，能端到端产出**八轴全部有值**的结果，且每一层的输入来自上一层的输出，全程可追溯引用。

### 阶段三：商业化与验证（3–6 个月）

| # | 动作 |
|---|---|
| P1-19 | 引入订阅制（月/年 membership） |
| P1-20 | 打通 Creem 国际支付 |
| P1-21 | 检测履约对接（第三方检验/上门采血） |
| **P1-31** | **n≥30 前瞻性自身前后对照真实用户研究**（8–12 周） |
| P1-15 | MCP 战略加注：发布 Registry、一键配置、Agent 能力文档 |
| P1-10 | 补 `gdpr.py` / `repair.py` 的 UI（合规硬需求 + 论文卖点） |
| P1-11 | TypeScript 渐进迁移 + Vitest + 修 eslint |
| P1-27 | 合并两套 alembic，模型-迁移一致性入 CI |
| P1-24 | intended use 声明 + 逐功能合规判定表 |

### 阶段四：规模化（6–12 个月）

- P2：多组学时钟对齐（器官年龄 / OMICmAge / PhenoAge）
- P2：证据库扩至 ≥300 条 + 公开数据集 + PRISMA 声明
- P2：预注册 + 高校/医院合作真实队列
- P2：等保三级 / ISO 27001 / SOC 2
- P2：硬件（脉象）开源固件 + 回放样本集，建开发者生态
- P2：移动 App（Capacitor 或 RN）

---

## 七、风险与红线

| 风险 | 等级 | 说明 |
|---|---|---|
| **宣称-实现落差被识破** | 🔴 极高 | 投资人/审稿人/技术尽调只要跑一遍 `fusion_engine` 就能发现八轴无打分器、L1→L2 断开。**建议在对外材料主动披露"当前为研究原型，轴映射覆盖率 2/8"**，用诚实换信任 |
| **OCR 伪造检验数值** | 🔴 极高 | 生产环境可能输出假血糖/胆固醇，属医疗级事故隐患。**P0-6 必须立即修** |
| **合规越线** | 🔴 高 | PGx 致病性分级 + ICD-11 映射突破 wellness 边界；FDA/EU 按 intended use 判定，改词无效 |
| **同意记录不可审计** | 🟠 中高 | 内存存储，重启即丢；GDPR 下无法证明取得有效同意 |
| **单人项目 + 95 项未提交** | 🟠 中高 | 知识单点、无代码评审、工作可能丢失 |
| **auto-pipeline 26MB 构建垃圾** | 🟡 中 | 仓库膨胀、CI 变慢、误导"体量"认知 |
| **两套 alembic 分叉** | 🟡 中 | 53 张表对 4 个迁移，数据库演进不可控 |

---

## 八、结语

HealthLens 的真实水平是：**一个架构正确、诚实降级、已经上线的研究原型，配上了大量诚实的自我评估文档**。

它的优势不是"已经做完了"，而是**三件真东西**：
1. **架构方向正确**——"稳态生物学轴"这个理论抽象在国际上是空白，且契合中医科学院"思维链透明化"的路线；
2. **工程质量真实**——限流、缓存、脱敏、FHIR、护栏、webhook 幂等、看门狗内容校验，这些是认真写的代码；
3. **诚实**——120 条带 DOI 的真实证据库、bioage 明确声明"非 PhenoAge"、pulse 库缺失时报错而非造假、论文自限"不代表人体有效性"。**这份诚实是稀缺资产，应继续保持。**

它的问题也很清楚：**宣称的五层因果链与八轴引擎是叙事，不是实现**。

所以全面提升的第一优先级不是加功能、不是做增长，而是——

> **把 A–H 八轴的打分器真正做出来，把 L1→L2→L3→L4 的链条真正接上，让"轴"这个字从 PPT 走进代码。**

这件事做成了，其余所有板块（前端、商业化、学术、出海）的优化才有了支点；做不成，加再多功能也只是把落差做得更大。

---

*报告基于 2026-10-08 的代码基线 `947a9f4` 与在线实测。所有判定均附文件路径与行号证据，可逐条复核。*
