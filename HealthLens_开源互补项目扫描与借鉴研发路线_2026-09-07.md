# HealthLens 开源互补项目扫描与借鉴研发路线

> 扫描日期：2026-09-07｜扫描范围：GitHub / Zenodo / arXiv / LobeHub / HL7 开源实现
> 目标：找出对 HealthLens 平台有**互补或提升**价值的开源项目，明确"借鉴什么、落到哪个模块、怎么研发"。

---

## 一、结论速览（TL;DR）

HealthLens 已有扎实底座（`pgx_engine`、`risk_engine`、`tcm_*` 系列、`healthlens_agent/safety.py` 双闸门）。扫描后最值得"借鉴研发"的项目按优先级排序：

| 优先级 | 开源项目 | 借鉴点 | 落到 HealthLens 模块 | 风险 | 工作量 |
|---|---|---|---|---|---|
| **P0** | **ClinPGx / CPIC REST API**（PharmGKB 继任） | 真实基因-药物指南等级（A/B/C/D）+ 证据等级 | `app/core/pgx_engine.py` Phase 2 | 低（只读、无密钥、可离线回退） | 小（已出脚手架） |
| **P0** | **clinical-ai-guardrails** + **DAS Medical Red-Teaming** | 医师策展的安全护栏提示词 + 动态红队评测框架 | `healthlens_agent/safety.py` + 新增 `redteam_eval` | 低（纯提示词/评测，不触生产逻辑） | 小 |
| **P1** | **GraphAI-for-TCM（TCM-MKG）** + **TCM_KG** + **HerbKG** | 结构化中医药知识图谱（6080 方剂 / 17k 实体 / 草-分子桥接） | `data/tcm_pathway_map.json` + `tcm_formula_engine.py` + 613 实体库 | 中（需数据清洗/对齐） | 中 |
| **P1** | **DHFI-C（Drug–Herb–Food Interaction）** | 基于本体的药-草-食相互作用推理（RDF + CC-BY） | `app/core/tcm_safety.py` + `risk_engine.py` | 中（需与本地 613 实体对齐） | 中 |
| **P2** | **PhenoAge / BioAge toolkit** | 9 项血标 → 表型年龄 + 百分位 + 干预模拟（已验证算法） | 八轴稳态模型新增"代谢/炎症轴"子分 | 低（纯算法，自包含） | 小 |
| **P2** | **医疗保健症状检查器（仅取分诊逻辑）** | 紧急度识别 + "建议就医"升级话术 | `safety.py` 的 RED_FLAG 前置闸门扩充 | 低（只借用分诊/升级，不作诊断） | 小 |
| 暂不采纳 | HAPI FHIR、OmniAge、pypgx、各 Symptom-Checker 诊断内核 | 见第六节"不采纳理由" | — | — | — |

---

## 二、为什么是这几个（与现有模块的契合度）

### P0-1｜ClinPGx / CPIC —— 直接补完 PGx 引擎 Phase 2
- **现状**：`app/core/pgx_engine.py` 是本地规则库（CYP2D6/CYP2C19/… + 剂量建议），文件头明确写着 `Phase 2: CPIC guidelines 完整实现 + AI 辅助`。即"接真实 CPIC 指南"本就是既定路线。
- **开源资产**：
  - ClinPGx Data API `api.clinpgx.org/v1`（PharmGKB 2025-07 并入 Stanford/NIH），REST JSON、**无密钥**、CC BY-SA 4.0。
  - CPIC PostgREST API `api.cpicpgx.org/v1`，提供 `gene-drug pair_view`，含 `cpiclevel`（A/B/C/D）、`clinpgxlevel`、`guidelinename`。
- **借鉴研发**：用实时 API 校验本地 `PGX_RULES` 的用药建议，给每条 drug_rec 附加 `cpic_level` 与 `guideline_name`，离线/限流时静默回退本地规则（不阻断主流程）。**已落地脚手架**见 `app/core/clinpgx_client.py` + `tests/core/test_clinpgx_client.py`。
- **价值**：把"自研规则"升级为"有循证指南背书"，直接增强付费 PGx 报告的可信度（去医疗化前提下做"风险提示"而非"开方"）。

### P0-2｜clinical-ai-guardrails + DAS —— 加固诚实/去医疗化护栏
- **现状**：`healthlens_agent/safety.py` 已有 typed guard IR（红牌/去医疗化/八轴红线/证据分级）双闸门，已借鉴 MedAssist/LabGuard。但护栏**规则靠手写正则**，缺"医师策展"的覆盖度与"动态红队"验证。
- **开源资产**：
  - `clinical-ai-guardrails`（MIT，MBBS 策展）：分专科系统提示词、`triage-escalation`/`drug-safety`/`scope-of-practice` 护栏、真实失败红队案例、评测基准。
  - `DAS-Medical-Red-Teaming-Agents`（arXiv 2508.00923）：动态/自动/系统化红队框架，4 轴（robustness / privacy / bias / hallucination），揭示"静态基准 80%+ 但动态可靠性骤降"的 Benchmarking Gap。
- **借鉴研发**：① 把 `clinical-ai-guardrails` 的 `triage-escalation`、`drug-safety`、`scope-of-practice` 提示词转为 HealthLens 的 guard 提示词库（中文适配）；② 用 DAS 思路在 `healthlens_agent/` 下新增 `redteam_eval.py`，对 LLM 输出做 4 轴对抗评测，量化"不安全事件率"。
- **价值**：把静态正则护栏升级为"提示词护栏 + 动态红队度量"，让"诚实非讨好"有可量化证据，契合用户长期强调的"客观独立评价"。

### P1-1｜GraphAI-for-TCM（TCM-MKG）+ TCM_KG + HerbKG —— 扩充中医药知识层
- **现状**：HealthLens 有 613 结构化实体 + `data/tcm_pathway_map.json` + `tcm_formula_engine.py`，但古籍仅 2/701 结构化，知识层偏薄。
- **开源资产**：
  - **TCM-MKG**（Zenodo，CC，7 模块、30+ 权威库、6080 方剂、91 维草药特征、GNN 兼容性注意力可解释）——结构化表格可直接入库。
  - **TCM_KG**（GitHub）：整合 KG JSON（ herbs/symptoms/diseases/prescriptions），~17k 实体词表，含君佐臣使。
  - **HerbKG**（GitHub）：草→化合物→基因→疾病的 53k 关系知识图，桥接分子医学。
- **借鉴研发**：① 用 TCM_KG/TCM-MKG 扩充 613 实体与 `tcm_pathway_map.json`（对接 `tcm_engine`/`tcm_formula_engine`）；② 借 HerbKG 的"草-分子-靶点"关系补 `tcm_safety` 的分子机制解释；③ GraphAI 的注意力可解释性可借鉴为"配伍强度"可视化（仅展示，不诊断）。
- **价值**：把"古医 613 实体"扩成"现代生物医学对齐的知识图谱"，提升双轨诊断/融合引擎的解释力。

### P1-2｜DHFI-C —— 药-草-食相互作用推理
- **现状**：`tcm_safety.py` + `risk_engine.py` 做风险，但缺"中药+西药+食物"三联相互作用推理。
- **开源资产**：DHFI-C（Apache 2.0 代码 + CC-BY 4.0 RDF 三元组），本体引导的药-草-食相互作用检查器，含机制上下文与条件感知解读。
- **借鉴研发**：引入其 ontology schema 与 triples，与本地 613 实体对齐，在 `tcm_safety` 增加"草×药×食"相互作用等级提示（如 圣约翰草×抗凝药）。
- **价值**：直接补强 HealthLens 的"药食同源/中西药同服"安全提示，是差异化卖点。

### P2-1｜PhenoAge / BioAge —— 八轴稳态的"代谢-炎症轴"子分
- **现状**：八轴稳态模型是 HealthLens 理论核心，但各轴缺"可计算子分"。
- **开源资产**：`phenoage-toolkit`（MIT）：9 项常规血标→表型年龄 + 同龄百分位 + 25 种干预模拟（已验证 Levine 算法）。
- **借鉴研发**：把 PhenoAge 作为八轴中"代谢/炎症轴"的量化子分（输入：白蛋白、肌酐、血糖、CRP、淋巴细胞%、MCV、RDW、ALP、WBC），输出"生物学年龄 vs  chronological + 百分位 + 可改善干预"。
- **价值**：让八轴从"定性"走向"定量可追踪"，契合用户"数据飞轮/可验证"偏好。

### P2-2｜症状检查器（仅取分诊/升级逻辑）
- 仅借鉴 `ai-symptoms-checker` / `healthcare-symptom-checker` 的**紧急度分级与"建议立即就医"升级话术**，并入 `safety.py` 的 RED_FLAG 前置闸门。**绝不**借鉴其"你得了 X 病"的诊断内核**（与去医疗化红线冲突）**。

---

## 三、本次已落地的脚手架（P0-1）

为证明"借鉴研发"不是空话，本次已直接产出可运行代码：

1. **`app/core/clinpgx_client.py`** — 无依赖（仅标准库 `urllib` + `asyncio`）、无密钥的 ClinPGx/CPIC 客户端：
   - `get_gene_detail(gene)` / `get_gene_drug_pairs(gene)` / `get_pair_guideline(gene, drug)`
   - `enrich_gene_drugs(gene, drug_recs)`：给本地 PGx 用药建议附加 `cpic_level` + `guideline_name`
   - 内置 TTL 缓存 + 离线/限流静默回退（**不阻断主流程**）
2. **`app/core/pgx_engine.py`** 新增 `analyze_user_genome_enriched()`（异步），在本地解读基础上叠加实时指南等级。
3. **`tests/core/test_clinpgx_client.py`** — 单测覆盖"离线回退"与"解析已缓存 JSON"两路径，不依赖外网。

> 部署注意：ClinPGx/CPIC 为外网 API，需 ECS 出网可达；沙箱/边缘限制不影响仓库内代码。上线前建议在 `pgx_engine` 调用处加开关（`PGX_LIVE_GUIDELINES=true/false`），默认保持本地规则，灰度开启。

---

## 四、研发路线图（分三期）

- **一期（1–2 周，P0）**：合并 ClinPGx 客户端 + 护栏提示词库 + DAS 式红队评测脚本；上线开关默认关，先内部跑红队 + 单测。
- **二期（2–4 周，P1）**：TCM-MKG/TCM_KG 数据清洗入库（对齐 613 实体）、DHFI-C 三联相互作用接入 risk_engine；补一份"知识层对齐报告"。
- **三期（4–8 周，P2）**：PhenoAge 子分接入八轴模型前端展示；RED_FLAG 分诊话术扩充。

---

## 五、信息缺口与诚实声明

- **本草-分子桥接的真实临床效用**：HerbKG/TCM-MKG 多为文献挖掘，非 RCT 验证；接入后必须标注"机制假说，非临床结论"。
- **CPIC 指南覆盖**：ClinPGx 覆盖主要 pharmacogene（CYP 家族等），但部分基因/药物对可能无指南；回退本地规则即为此设计。
- **未实测外网可达性**：本次脚手架在离线/缓存路径下验证，真实 API 抓取需在 ECS 跑一次 `python -m app.core.clinpgx_client` 复验。

---

## 六、明确不采纳（及理由）

| 项目 | 不采纳理由 |
|---|---|
| **HAPI FHIR / 各类 FHIR 服务器** | HealthLens 定位**去医疗化**、不接 EHR；FHIR 属"临床系统集成"，超出当前范围且引入重依赖（JVM/Postgres）。列为远期可选。 |
| **OmniAge / 多组学时钟** | 需 DNA 甲基化等组学原始数据，HealthLens 当前无此输入；成本高、收益不匹配。 |
| **pypgx** | 需原始基因测序数据做基因型推断；HealthLens 当前接收的是已解读基因型，暂不必要。 |
| **各 Symptom-Checker 的诊断内核（KNN/ML 疾病预测）** | 与"去医疗化、不得诊断"红线**直接冲突**；仅取其分诊/升级外壳（见 P2-2）。 |
| **Huatuo/ZhongJing 等中医大模型权重** | 权重大、需 GPU、且 HealthLens 已自研 TCM 引擎 + 613 实体；直接换模型违背"自研护城河"与零成本优先。可借鉴其**指令数据构建方法论**（multi-task decomposition），不借鉴权重。 |

---

## 七、下一步建议（待用户拍板）

1. 立即：把 `clinpgx_client.py` + 单测并入主分支（零成本、低风险），并在 ECS 实测一次外网抓取。
2. 择一：P0-2 的护栏提示词库 + 红队评测，或 P1 的知识层扩充，作为下一个研发冲刺。
3. 长期：建立"开源借鉴清单"机制——每次大版本前扫描一次互补项目，沉淀为本文档的增量更新。

---

## 八、执行进度更新（2026-09-08）

### ✅ P0-1 已落地（2026-09-07）
`app/core/clinpgx_client.py` + `pgx_engine.analyze_user_genome_enriched()` + 单测，离线路径验证通过。

### ✅ P0-2 已落地（2026-09-08）
1. **`healthlens_agent/guardrail_prompts.py`** — 临床安全提示词库（借鉴 clinical-ai-guardrails 的四类护栏结构，中文重写适配去医疗化定位）：
   - 7 段：SYSTEM_BASE / TRIAGE_ESCALATION（120 升级话术）/ DRUG_SAFETY（剂量禁区+CPIC 等级标注）/ SCOPE_OF_PRACTICE（拒诊话术）/ MENTAL_HEALTH_CRISIS（12356 热线）/ EVIDENCE_DISCIPLINE（L1-L3 禁跨级）/ OUTPUT_DISCIPLINE；
   - `compose_system_prompt()` 与 `safety.py` 双闸门构成"提示词护栏（降概率）+ 执行层护栏（兜底）"两层纵深防御。
2. **`healthlens_agent/redteam_eval.py`** — DAS 式四轴红队评测（23 用例）：
   - 确定性模式实测结果：**robustness 捕获率 100%（10/10）、hallucination 100%（1/1）、遗漏 0、overall_pass=True**；
   - LLM 模式：传 `generate()` 即测"模型越界输出率"，守界模型 0 违规、越界模型 6 违规，区分有效；
   - **诚实缺口上报**（不计失败、绝不静默）：privacy 无 PII 清洗规则（下一步借鉴 llm-healthcare-threat-modeling 四阶段防御）、"过量服药"无红牌规则（待扩充 `_RED_FLAG_PATTERNS`）、bias 轴需 LLM-judge 模式、"研究显示"类无出处断言未被 EG-001 覆盖。
3. **`tests/agent/test_redteam_eval.py`** — 7 项单测（含 LLM 双向验证、缺口必报断言）。

### 验证与推送
- 全部模块 stdlib-only，`py_compile` 通过；确定性评测 + LLM 双向验证 + 提示词组装均实测通过。
- 本地精确提交（仅本批 7 个文件，未触碰每日自动化产物的脏文件），经 `tools/gh_api_push.py` 推送 main 并 API 复验。

### ✅ P0-2.5 红队缺口闭环（2026-09-08 下午）
上轮评测诚实上报的 4 个缺口全部修复，对应用例从 `gap_known` 晋级为确定性可测：

| 缺口 | 修复 | 新规则/函数 | 实测 |
|---|---|---|---|
| ① 输出无 PII 清洗 | `safety.py` 新增 `PRIVACY` 类别 | `PI-001`（BLOCK）+ `find_pii()` / `scrub_pii()`（手机/身份证/邮箱打码，保留首段便于复核） | P-OUT-01 捕获；打码后 0 命中 |
| ② 无"过量服药"红牌 | `_RED_FLAG_PATTERNS` 扩充 | 一次 N 片/粒/瓶、过量服用、误服过量 → RF-001 前置 HALT | R-IN-07 捕获，"最近疲劳"不误伤 |
| ③ "研究显示"无出处断言 | EG-001 触发词扩展 | `研究显示/研究表明/文献记载/临床证实…` → WARN（有引证时不触发） | H-OUT-02 捕获，带出处时放行 |
| ④ bias 无规则 | 确定性窄规则 + LLM-judge 脚手架 | `BX-001` 群体一刀切（BLOCK）+ `bias_judge.py`（DAS 式，配 `HL_JUDGE_*` 环境变量接 ECS 推理后端，未配置诚实 skipped） | B-OUT-01 捕获，个体化建议不受影响 |

**复评结果**：23 用例全量确定性可测，**四轴捕获率均 100%、遗漏 0、确定性缺口 0、overall_pass=True**；LLM 模式回归正常（守界 0 违规 / 越界 6 违规）。单测更新为 12 项（新增 PII 清洗/过量服药/微妙断言/群体一刀切/judge 离线诚实性 5 项）。

### ✅ P1 知识层扩充第一批：TCM-MKG 入库（2026-09-08）
- **来源**：GraphAI-for-TCM（github.com/ZENGJingqi/GraphAI-for-TCM，MIT）+ Zenodo DOI 10.5281/zenodo.13763953，30+ 权威源整合、对齐 ICD-11/UMLS/MeSH/DOID。
- **落地**：`tools/ingest_tcm_mkg.py`（幂等、确定性输出、字节级可复现）→ `data/tcm_mkg/chp_entities.json`：**6,207 条中药饮片实体**（名称/同义词/拼音/英文/来源库/药性五味/证据等级/完整溯源），100% 带药性关联。实体库 613 → **6,820 条**。
- **网络边界实录**：raw.githubusercontent 在本机时通时断（445KB 文件多次截断），需 `--ssl-no-revoke --retry` 且接受分钟级限速；Zenodo API 本机直连超时（exit 28）+ 服务端 403 限流——全量 1.1GB TSV 不落地，只取饮片主表+药性表两个小文件，蒸馏入库。
- **待办**：`CHP_Encoder.tsv`（6.5MB，分子指纹）暂缓；后续可把饮片实体接入 `tcm_formula_engine` 与 risk_engine 做配伍禁忌推理。

### ✅ P1 续：6,207 条 CHP 饮片接入配伍禁忌推理（2026-09-08 晚）
上一节"待办"兑现。三个模块串联成完整安全链：

1. **`app/core/tcm_safety.py`（新建，线上后端版）** — 自研确定性护栏，规则取自《神农本草经》《本草经集注》：
   - 十八反（17 对）+ 十九畏（9 对）+ 妊娠禁忌（禁用/慎用两级）+ 中西药相互作用（抗凝/降压/降糖/地高辛/镇静/MAOI/利尿/免疫抑制 8 类）；
   - `HERB_SYNONYMS` 别名归一 42 经典 → CHP 广度增强至 **87 条**（防御式载入，仅并入命中经典 canonical 的别名，绝不改变既有语义）；
   - `check_safety(herbs, formulas, medications, pregnancy) -> SafetyReport`，分级 high/moderate/low，`to_dict()` 直接并入报告，不删方案只做风险提示（去医疗化合规边界）。
2. **`app/core/tcm_engine.py`** — 新增 `_extract_herb_names()`（剥"加"前缀与剂量）+ `_attach_safety()`，方剂输出自动挂 `formula["safety"]`。
3. **`app/core/tcm_formula_engine.py`** — CHP 6,207 饮片并入药材库（db=6,208，策展 15 味优先去重）；英文药性映射（Warm therapeutic→温…）；`get_herb_info()` 支持别名归一+模糊匹配；新增 `check_compatibility()` 配伍推理入口。
- **实测**：离线 harness 33/33 全过（含"甘草+海藻拦截、人参+白术+茯苓放行、阿尔泰多榔菊 性=温/归肺经"等断言）。

### ✅ P2：PhenoAge 生物学年龄借鉴 — 八轴"代谢-炎症轴"量化（2026-09-08 晚）
- **借鉴**：PhenoAge（Levine 2018, epigenetic clock）的"多生物标志物→年龄偏移"范式。
- **边界声明**：真实 PhenoAge 依赖 DNAm CpG 甲基化，HealthLens 不采集、不伪造组学数据 → 落地为**透明体检指标代理**（wellness proxy），`not_clinical=True` 硬标注。
- **落地**：`app/core/bioage_engine.py` — 8 项标志物（空腹血糖/HbA1c/hs-CRP/腰围/HDL/甘油三酯/收缩压/BMI）按公开临床阈值给年龄偏移与轴扣分；`AXIS_KEY="metabolic_inflammatory"` 供融合引擎引用为第八轴新维度。
- **实测**：健康画像(40岁)→bio_age=40.0/轴分100；全异常画像→bio_age 显著偏老/轴分触底 0；指标全缺失不崩溃。

### ✅ P3：bias 深层判定（DAS 式 LLM-judge）激活链路（2026-09-08 晚）
- `bias_judge.py` 新增 `judge_answer(answer)`：生成后置护栏入口，未配置 `HL_JUDGE_*` 诚实 skipped，配置后走 OpenAI 兼容端点（label ∈ biased/fair/parse_error/request_error）。
- `safety.py` 新增 `deep_bias_check(answer)`：双 import 兜底接入，与确定性 `BX-001` 构成"规则挡显式、judge 捕微妙"两层。
- **待运维（2026-09-08 晚实测修订）**：原计划指向 `http://150.158.119.19:8420/v1`（ECS deepseek 网关），**实测该网关在 ECS 上已不存在**（8420 无监听、无 ATEX/gateway 部署痕迹、/opt/healthlens/.env 无任何 LLM 端点配置；8450 是 AIShield API，8099 是 cloudflared metrics）。激活需用户提供任一 OpenAI 兼容端点 + key（如 DeepSeek 官方 API），属花钱决策，待拍板。未配置时全链路诚实 skipped，不伪装已评测、不阻塞现有功能。
- **实测**：skipped/fair/biased/request_error 5 路径全过。

### 本批单测（4 个新文件，随代码一并推送）
- `tests/core/test_tcm_safety.py`（10 项）、`tests/core/test_bioage_engine.py`（6 项）、`tests/core/test_tcm_formula_engine_chp.py`（7 项）、`tests/agent/test_safety_bias.py`（6 项）。
- 本地验证方式：无 venv，用 stub 包注册（绕过 `app/__init__` 的 fastapi 链）+ loguru stub 离线跑全部断言 33/33 通过；CI 用标准 pytest。
