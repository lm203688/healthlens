# HealthLens 全面评估与 SCI 就绪度报告

**评估日期**：2026-10-16（基线版本 v0.30.0，全部结论基于当日代码级实测，非文档复述）
**评估范围**：项目完整性、科学先进性、国际化定位、国际竞品比较、技术壁垒与技术深度、最新科技融合、提升方案、SCI 论文阶段判定

---

## 一、结论摘要

> ### SCI 判定（先给答案）
>
> **SCI 期刊投稿：未达到。medRxiv 预印本：已达标，建议本周投。**
>
> 与 10-12 判定"5 个硬阻断、就绪度 3.5/10"相比，**性质已变**：内容级硬伤（八轴失效、验证不可复现、假 DOI、轴数矛盾）在本轮扫描中**全部清零**；剩的是两级——**地基级**（全新部署连注册都跑不通，今天重新实证仍然如此）与**证据级**（零人体纵向数据、案例库 22/120 有 DOI）。这两级都不是"改论文"能解决的，是 4–8 周的工程与数据问题。
>
> 最高性价比动作：**填好 ORCID 投 medRxiv + 铸造 Zenodo DOI**（投稿包已就绪，只差一个字段），先占时间戳、锁死优先权——因为范式预占者已经出现过一次。

### 本轮新发现（相对此前各轮报告）

| # | 发现 | 等级 |
|---|---|---|
| N1 | **冒烟枪仍然有效**：v0.30.0 全新部署 `alembic upgrade head` → 注册即崩（`no such column`）。37 张 ORM 表无迁移，今天一张未补 | 🔴 致命 |
| N2 | **12/12 DOI 全部通过 Crossref 核验**（10-12 的假 DOI 与错标期刊已清零） | 🟢 重大好转 |
| N3 | **版本漂移已被工程化堵死**：`.env.example` 删除 `APP_VERSION`，注明会静默覆盖真源——上次修完又复发的循环有了根因修复 | 🟢 |
| N4 | **medRxiv 投稿包自述与代码事实漂移**：manifest 称"491 tests / 29 DOI"，实际 1669 passed / 22 DOI | 🟡 投稿前必须对齐 |
| N5 | **竞品格局新增变量**：Deep Longevity（励晶太平洋）2026 年 10 月在美国 50 州上线 Accrua，AI BloodAge 直销 C 端——直接争抢"老化时钟"叙事，且与中国团队同源竞争 | 🟡 |
| N6 | **E/G 轴共线未根治**：满分区（hrv=45）两轴输出仍逐点相同，八轴实为 7.5 轴 | 🟡 |
| N7 | **频率疗法免责声明已加但曲目数据仍残留疾病暗示**（"慢性病辅助/内脏调理"） | 🟡 |

### 一句话总评

**楼已够高（v0.30.0、1669 测试、SVIEE 五层、A2A/MCP 对齐、数字孪生规范草案），但地基裂缝今天原样存在——在 D0（迁移对齐）完成前，每加一层都在给裂缝增重。**

---

## 二、实测基线（当日跑出，非读文档）

| 项 | 实测值 | 命令/依据 |
|---|---|---|
| 测试 | **1669 passed / 2 skipped / 0 failed**（177.96s） | `pytest tests/ -q` |
| 版本一致性 | pyproject 0.30.0 = agent-card 0.30.0 = 线上 /version | 三处对齐 |
| ORM 表 / alembic 建表 | **61 / 24 → 37 张无迁移** | 正则对比 |
| 全新部署实证 | alembic upgrade head → 注册 **OperationalError** | TestClient 实测（已清理探针） |
| 生产库 | 25 表、**无 alembic_version**、缺全部新表 | sqlite 直查 |
| CI | 11 工作流，**无一步跑 alembic**；tests/ 零处引用 alembic | grep |
| 依赖锁定 | **无 lock / constraints 文件**，requirements 全 `>=` 无上界 | ls |
| CORS | 默认 `["*"]`，仅 warning 不 fail | app/config.py:15 |
| 案例库 | 120 条，**DOI 22 条**（manifest 称 29） | 直查 JSON |
| 论文引用 | 35 处引用 / 12 唯一 DOI，**Crossref 12/12 通过** | 批量 API 核验 |
| 四向映射表 | A–H 全覆盖，`gbt_confirmation_required=true` | axis_term_mapping.json |
| rubric 基准 | v1 共 200 条 | data/rubric_benchmark_v1.json |
| 验证快照 | git-SHA + 时间戳命名，7 份历史 | validation_snapshots/ |
| GraphRAG | 1661 节点 / 2005 边 | 10-16 早前实测 |
| 真实数据 | users=2，longitudinal_studies 生产库**表都不存在** | 直查 |
| E/G 共线 | hrv=45 时 E=G=100.0 完全重合；25/15 时已分化 | score_all_axes 实测 |

---

## 三、对标核心目标的完成度

项目核心目标（白皮书定义）可归纳为四层，逐层对标：

| 目标层 | 定义 | 达成度 | 证据 |
|---|---|---|---|
| G1 可计算 | 中医证候语义 → 8 个可测量生物学轴的显式映射 | **90%** | axis_term_mapping 覆盖 A–H；打分器参数外置 config/axes/ |
| G2 可验证 | 框架结论可复现、可证伪 | **55%** | 序列化幂等、快照机制、E-value 已有；但耦合系数是先验非识别量，且部署路径断裂使外部复现不可能 |
| G3 合规输出 | 按法域过滤医疗宣称 | **85%** | 5 法域 fail-closed claims 引擎 + region_guard 16 处接线 |
| G4 证据引擎 | 从单点评估走向可自证证据网络（SVIEE） | **40%** | 五层代码齐备（统计/表征/联邦/协议/评估），但零真实租户、零人体数据——"引擎就绪、油箱空" |

**判断**：G1/G3 接近完成；G2 卡在地基；G4 是当前最关键的未完成层——**代码先行 12 个月，数据零天**。

---

## 四、完整性评估（四层）

### 4.1 功能完整性 ✅

- 14 功能板块、38 个 API 模块、200+ 路径、15 个前端页面、9 连接器
- 全链路闭环：上传/连接 → 八轴 → 融合 → 因果推演 → 报告（合规过滤）→ 干预/依从 → Agent
- 边缘硬件（ESP32 脉搏波）、支付（虎皮椒 CNY + Creem USD）、i18n（中英各 ~380 key）

### 4.2 数据完整性 🟡

| 资产 | 规模 | 问题 |
|---|---|---|
| 案例证据库 | 120 条（29 真证据 + 91 合成夹具，已诚实标注） | 直查 DOI 仅 22；manifest 称 29，**口径必须对齐** |
| 古籍 | 699 部书目 / 613 切片 / 613 结构化实体 | 原文仅对已结构化书目提供 quote，覆盖不全 |
| 四向映射 | A–H 全覆盖 | GB/T 20348 对应关系为"通行对应"，**待官方校订** |
| rubric 基准 | 200 条 | 未到可公开立标准的 300+ 规模 |
| 人体数据 | **0** | users=2；纵向表在真实库不存在 |

### 4.3 部署完整性 🔴（今日重新实证）

```
docker-compose.yml:154   sh -c "alembic upgrade head && python scripts/seed_admin.py"
                         ↑ 生产初始化路径
tests/conftest.py:32     Base.metadata.create_all
                         ↑ 测试路径

# 今日实测（.aoci_probe2，已清理）
alembic upgrade head  →  TestClient POST /api/v1/auth/register
sqlalchemy.exc.OperationalError: no such column: users.is_active
```

**同日同时刻：`pytest tests/` = 1669 passed, 0 failed。** 两条建 schema 路径分叉 37 张表，零测试覆盖该分叉，CI 无一步跑迁移。生产库、迁移、ORM 三方分叉（生产库无 alembic_version）。

### 4.4 引用完整性 ✅

12 个唯一 DOI 全部通过 Crossref 解析且期刊/年份正确。10-12 审计发现的两个硬伤——不可解析的 AFFIRM DOI、错标期刊的 *J Nanobiotechnol*——均已修复。**这是学术诚信层面从"会被拒"到"站得住"的跨越。**

---

## 五、科学先进性评估

### 5.1 已达国际水准的资产（竞品对照确有差异化）

1. **法域感知 claims 引擎**：5 法域 fail-closed + 字段级过滤。国际竞品（Function/Neko/Superpower）全部单法域运营；制药向工具（Veeva PromoMats、Klick Guardrail、RegASK）面向 MLR 流程而非 wellness 报告生成——**"可编程、覆盖五法域的 wellness claims 过滤层"仍是空白位**。
2. **结构因果模型 + 反事实 + E-value + refutation**：8 节点 DAG 带机制注释，输出含 calibration/sensitivity/not_clinical。且代码诚实声明"耦合系数非因果识别量"。
3. **时序确定性序列化**（ts_serializer）：幂等性实测成立（两次 sha256 一致）+ 隐私 hash。检索确认该方向**生态空白**（TEMPO/LiPCoT 均不成熟）——原创点成立。
4. **数字孪生报告规范草案 v0.1/v0.2 + 三封提交信**（EQUATOR/IEEE CBBMI/W3C AAWG）：检索确认医学数字孪生**无专属报告规范**（DECIDE-AI/TRIPOD+AI 均非孪生专属）——立标准的位置只有一次，草稿已就绪未提交。
5. **rubric 基准 200 条 + position-swap 校准 + 评审引擎**：中西医结合领域自建评估基准，"谁定义基准谁定义标准"。

### 5.2 仍停留在先验阶段的环节

- **耦合系数是先验信念，不是识别量**（自研承认）→ 需要前瞻队列或 n-of-1 标定
- **验证完全 in-silico**（22 合成 profile）→ 只能支撑 methodology 类论文
- **E-value 对负效应/零效应的处理**：10-16 早前修过 complex bug，需回归测试守护
- **dowhy 严格模式**：10-16 修过死代码（装了 dowhy 也走纯 Python 回退），但同类模式在 CI 从不执行（`flower_adapter.py:53 pragma: no cover`）——**"重型库分支无真实执行"是系统性风险，今天仍然存在**

### 5.3 预占研判（与 10-12 相比无恶化）

- 《科学通报》2026-06 稳态医学整合框架：战略倡议级，无可运行实现——本项目"可计算实现 + 开放验证装置"定位仍存活
- 未检索到新的同类可计算框架预占
- **新风险**：Deep Longevity Accrua（2026-10 美国 50 州）把"AI 老化时钟直销 C 端"落地了，若其后续引入整合医学叙事，novelty 窗口收窄

---

## 六、国际化定位与国际竞品比较

### 6.1 定位判断

**不做"第 N 个长寿会员平台"**（Function Health 已用 $450M 级增长资金买获客，Neko Health 单轮 $700M——资本竞赛无胜算）；**做"整合医学的合规解释层 + 证据引擎"，B2B2C 嵌入**。

已验证的对标路线：**Tiny Health "Powered by Tiny"**——B2B 一年增长 4 倍、6,000+ practitioners、客户含 Mayo Clinic Executive Health、Atria、Superpower。其护城河不是算法（测序已商品化）而是**20 万纵向样本 + 一篇干预性 RCT**。HealthLens 可用"八轴纵向 + n-of-1"复刻，且无测序成本。

### 6.2 竞品矩阵（2026-10 更新）

| 竞品 | 模式 | 定价/规模 | 法域 | 核心资产 | 对 HealthLens 的启示 |
|---|---|---|---|---|---|
| Function Health | 会员制检测 | ~$365/年 | 单一 | 100+ 指标 + 临床医生解读 | 只卖"测量"，无干预推演 |
| Superpower | 会员制检测 | ~$349/年 | 单一 | 血液追踪 | 同上 |
| Neko Health | 影像 + AI 体检 | 单轮 $700M | 单一 | 全身扫描 | 医疗化玩家，进保险支付 |
| Prenuvo | 影像 | 高端 | 单一 | MRI 全身 | 同上 |
| **Deep Longevity Accrua**（新） | AI 老化时钟 C 端直销 | 2026-10 美国 50 州 | 美国 | BloodAge + 持牌医生远程 | **直接争抢"老化时钟"叙事，须差异化** |
| Tiny Health | B2B2C | 6000+ practitioners | 单一 | 20 万纵向样本 + RCT | **定位对标；样本与 RCT 是标杆** |
| Zoe / Viome / Levels |  microbiome/CGM | 订阅 | 单一 | 纵向数据 | 都在攒纵向，但无中医维度 |
| 中医大模型（岐黄/华佗类） | 国内 LLM | — | 中国 | 中文语料 | 无生物学轴Mapping、无合规输出层 |

**中国市场特殊性**：GB/T 20348-2026 已实施（含中英文定义）+ 中医大模型评测国标（三大能力域 13 子域 30+ 指标）+ 虎皮椒支付——**中国有原产地优势，且竞品极少，是 L3 层壁垒的合法来源**。

---

## 七、技术壁垒与技术深度深挖

### 7.1 六层壁垒模型（更新版）

| 层 | 当前 | 潜力 | 判断 |
|---|---|---|---|
| L1 特征层 | 2/10 | — | 手挑 hrv_rmssd 等特征正被可穿戴基础模型商品化（SensorFM 500 万人/1 万亿分钟/35 任务），**贬值中** |
| L2 知识层 | 5/10 | 8 | GraphRAG 1661 节点 + 四向映射 + 古籍 613 切片；但共现规则非学习，**接图学习可二次跃迁** |
| L3 编排层 | 2/10 | — | MCP 2026-07-28 / A2A v1.0.1 已上收为协议，**已对齐 = 无壁垒，仅资格线** |
| L4 合规输出层 | **8/10** | 9 | 五法域 fail-closed 是当前最强项，wellness 向可编程 API 化仍空白 |
| L5 证据层 | 1/10 | **9/10** | 框架齐、数据零。一旦建立不可复制——**Tiny Health 的护城河正在这一层** |
| L6 标准卡位层（新立） | 3/10 | 8 | 数字孪生规范草案 + rubric 200 + GB/T 自评；**草稿未提交 = 0，提交了才叫卡位** |

### 7.2 三个真空白（检索核实，非猜测）

| 空白 | 状态 | 对应资产 |
|---|---|---|
| 联邦目标试验仿真 | 论文成体系，无成熟开源实现 | federated + causal 已有骨架 |
| 医学数字孪生报告规范 | **标准空白**（今日复检仍无） | docs/reporting_standards/ 13 文件就绪 |
| 时序信号→LLM 确定性序列化 | 生态空白 | ts_serializer 幂等实测成立 |

**这三个恰好对应已有布局——不是巧合，是位置优势。**

### 7.3 明确"不是壁垒"的清单（避免误投）

- 556 行 if-elif 打分器（转声明式配置即可，知识资产在规则不在形态；但禁忌/危急值类规则必须保留硬编码）
- 自研 5000 行 Agent 包（框架折旧 <18 个月，AutoGen 已进维护模式）
- GraphRAG 图谱本身（LightRAG/nano-graphrag 可复现，壁垒在数据源独占性）

---

## 八、最新科技发展与融合跟踪

### 8.1 已融合（且经实测）

| 技术 | 落地 | 验证 |
|---|---|---|
| MCP 2026-07-28 规范 | 754 行 server 改造 | 测试覆盖 |
| A2A v1.0.1 + JSON-RPC 端点 | a2a_task_store + /a2a 路由 | 端点在线可调 |
| DoWhy refutation | dowhy_adapter（10-16 修真死代码） | 需装库后复验 |
| Flower 联邦 | 单机多租户 fabric + 充分统计量 | 冷启动实测 |
| PhenoAge（Liu 2018） | bioage 引擎 | — |
| Pulse-PPG / PaPaGei | sensor_adapter optional + 手工 fallback | 脚手架，**未接真实权重** |
| GB/T 20348-2026 | national_standard_gate + 四向映射 + 自评报告 | 待官方校订 |
| Biomni / RAGAS | L4 adapter（optional） | — |

### 8.2 待融合/待验证

- **SensorFM 权重不可得**——只能做对标基准，不能写进路线图（10-15 已警示，复检仍无开源）
- **Pulse-PPG 零样本评测**：脚手架就绪，等 pip install 后填 checkpoint 出数
- **XGrammar 类强制解码**：L4 用了 rubric/ragas adapter，强制合规 JSON 的解码层未见落地（对"必须输出合规 JSON"场景是缺口）
- **DP（差分隐私）**：只应用于聚合统计，勿用于模型训练（小样本效用崩塌）

### 8.3 技术债（今天仍然）

1. 无依赖锁定 → 三个月后装出的不是同一个系统（Zenodo DOI 的复现承诺被架空）
2. 重型库分支 `pragma: no cover` → "装有 dowhy/flwr"路径 CI 从不执行（dowhy 死代码正是产于此）
3. 218 处 `except Exception`，采集链路最密（13 处）——吞异常 = 静默丢数据
4. CORS 默认 `["*"]` 只 warning

---

## 九、提升方案（P0–P3）

### P0 打地基（1–2 周，先于一切新楼层）

| # | 动作 | 成本 | 验收标准 |
|---|---|---|---|
| D0 | 建 `tests/test_schema_parity.py`：空库跑 alembic，对比 `Base.metadata.tables` 与 `PRAGMA table_info`，缺任一表/列即 fail；随后 autogenerate + 人工审补齐 37 表迁移 | 1 天 + 3–5 天 | 全新空库 `alembic upgrade head` → 注册/建 study 全通；CI 增加 alembic 步骤 |
| D1 | 重型库真实 stub 进 CI：装 dowhy/flwr 跑严格模式分支，删 `pragma: no cover` | 1 天 | CI 中 DoWhy 严格模式有真实通过记录 |
| D2 | 依赖锁定：pip-compile 生成 constraints（含 hash） | 0.5 天 | `pip install -c constraints.txt` 两次安装产物字节级一致 |
| D3 | CORS 生产硬结构：非 DEBUG 且 `["*"]` 时启动即拒 | 1 小时 | 配置错误无法启动 |
| D4 | 联邦预埋：`axis_snapshots` 加 `version_id` 乐观锁；`biomarker_readings` 加唯一索引 `(study_id, ts, channel)`；新迁移必须写 `downgrade()` 并测往返 | 1–2 天 | 重复提交不双算；迁移 up→down→up 往返通过 |

### P1 证据与投稿（2–6 周，与 P2 并行）

1. **medRxiv 提交**：ORCID 补上即可发（投稿包已就绪）
2. **Zenodo 铸造 DOI**：suffix 尚为 null；D2 完成后"复现"承诺才成立
3. **口径对齐三处**：manifest 的 491→1669、29 DOI→22（或补齐到 29）、删除 line 123 的"I/J added after initial validation"残留表述
4. **启动 n-of-1 自追踪**：一台穿戴设备 8–12 周，直接补掉"仅 in-silico"这个最致命短板——**单一最有效的投稿加分动作**
5. **claims 引擎实测拦截频率疗法**：曲目数据仍含"慢性病辅助/内脏调理"，验证是否被 fail-closed 拦住；拦不住就删字段
6. 剩余真证据补 DOI（22→29）

### P2 壁垒外化（1–3 月）

1. **数字孪生报告规范正式提交** EQUATOR / IEEE CBBMI / W3C AAWG（提交信已备）——立标准的位置只有一次
2. **Pulse-PPG 权重接入** + 零样本表征质量评测出数
3. **rubric 200→300+ 并公开**：中西医结合评估基准公开即标准卡位
4. **GB/T 20348 官方校订**（解除 gbt_confirmation_required）
5. **耦合系数标定**：用 n-of-1 数据做第一轮后验标定，公开标定过程（可审计）

### P3 生态（3–12 月）

- 联邦真实租户 ≥3（数据不出域）
- 中医大模型评测国标 2.0 征求意见参与
- "Powered by HealthLens" 签约试点（对标 Tiny Health 的 6,000 practitioners 里程碑，先求 1 家）

---

## 十、SCI 论文阶段判定

### 10.1 加权就绪度

| 维度 | 分 | 说明 |
|---|---|---|
| 代码质量与测试 | 8 | 1669 测试全绿、防漂移护栏有效 |
| 引用诚信 | 8 | 12/12 DOI 过 Crossref |
| 写作成熟度 | 6 | manifest 诚实列 limitations，但口径漂移 3 处 |
| 统计严谨 | 5 | SCM+E-value+refutation，但耦合未识别、重型分支不执行 |
| 可复现性 | 3 | 序列化幂等、快照机制加分；无 lock + 部署断裂致命 |
| 证据等级 | 2 | 91/120 合成夹具、零人体数据 |
| 新颖性定位 | 6 | 预占后以"可计算实现 + 验证装置"存活 |
| 合规与伦理 | 7 | 5 法域 + 审计链，未经法律实务评审 |
| **加权总分** | **≈4.5/10** | **未达 SCI 投稿线（≥6.5）；预印本已够（≥5）** |

### 10.2 硬阻断清单（投稿前必须清零）

| # | 阻断 | 修复成本 |
|---|---|---|
| H1 | 部署路径断裂：审稿人复现即失败 | 3–5 天（D0） |
| H2 | 无依赖锁定：Zenodo 复现承诺不可兑现 | 0.5 天（D2） |
| H3 | manifest 口径漂移（491 tests / 29 DOI） | 1 小时 |
| H4 | 轴数口径残留（line 123） | 10 分钟 |
| H5 | E/G 满分区共线（八轴=7.5 轴的统计学把柄） | 1–2 天（G 轴引入第二主输入） |
| H6 | 零人体纵向数据 | 8–12 周（n-of-1，与投稿并行启动） |

### 10.3 档位路线

| 档 | 目标 | 前置条件 | 预计 |
|---|---|---|---|
| **档 1（立即）** | **medRxiv + Zenodo DOI** | ORCID + D2 | 本周 |
| 档 2（4–6 周） | JIM（IF 5.2 Q1，$0 APC）或 IMR（IF 4.9 Q1，APC 全免），类型 Methodology/Hypothesis | H1–H5 清零 | 1.5–2 月 |
| 档 3（+8–12 周） | npj Digital Medicine / JMIR：+ n-of-1 真实纵向数据 | H6 | 4–6 月 |
| 不做 | Nature Medicine 级 RCT | — | 资源不匹配，明确放弃 |

### 10.4 最终判定

> **未达到 SCI 论文投稿阶段；已达到 medRxiv 预印本阶段。**
>
> 阻碍不是论文质量，是 (a) 别人复现不了（H1+H2）和 (b) 没有自己的数据（H6）。前者 4 天工日活动可清零，后者 8–12 周可与投稿并行。**建议：本周投 medRxiv 锁时间戳，同时启动 n-of-1；档 2 期刊在 H1–H5 清零后立即投。**

---

## 十一、风险清单与"不做"清单

### 风险

| # | 风险 | 应对 |
|---|---|---|
| R1 | 继续盖楼不修地基，某层增重触发坍塌（alembic 真跑一次与既有列冲突） | P0 先于一切 |
| R2 | 他人先发"可计算稳态框架 + 验证装置"，novelty 归零 | 本周 medRxiv 占位 |
| R3 | 频率疗法残留暗示在 FDA/MHRA 口径下构成 claims 越界 | 实测 claims 拦截面，拦不住即删 |
| R4 | 可穿戴基础模型使手挑特征层持续贬值 | 重心移向 L4/L5/L6 |
| R5 | 引用虽净但领域顶刊引用少，审稿人疑"领域相关性弱" | 档 2 选 Methodology 类型 + 预印本先行 |
| R6 | Deep Longevity Accrua 抢"老化时钟"叙事 | 差异化在"干预推演 + 整合医学 + 合规"，不在时钟本身 |

### 明确不做

不重写 Agent 包｜不自研 Co-Scientist｜不把 VLM 下沉 MCU｜不追 Nature Medicine RCT｜不进 C 端获客竞赛（拼不过 Function/Neko 资金）｜不把 DP 用于模型训练｜不再宣称"首套框架"｜在 D0 完成前不加新楼层。

---

## 附：本轮复验命令索引

```bash
# 测试基线
pytest tests/ -q --no-header -p no:cacheprovider          # 1669 passed, 2 skipped

# schema 分叉量化
python - <<'EOF'  # ORM 61 表 vs alembic 24 表 → 37 缺
（见第四节正则脚本）
EOF

# 全新部署冒烟枪（实证后已清理探针目录）
DATABASE_URL="sqlite+aiosqlite:///<path>" python -m alembic upgrade head
DATABASE_URL=... python -c "TestClient(app).post('/api/v1/auth/register', ...)"
# → OperationalError: no such column: users.is_active

# DOI 批量核验（12/12 通过）
curl -s https://api.crossref.org/works/10.xxxx/yyyy ...

# E/G 共线复验
score_all_axes(wearable={'hrv_rmssd': 45})  # E=G=100.0 重合
```

**本轮对仓库零源码改动**；仅临时创建并删除 `.aoci_probe2/` 用于部署实证。所有结论均可用上述命令复现。
