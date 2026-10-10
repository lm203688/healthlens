# HealthLens 可扩展性诊断与扩展方向报告

> 复扫日期：2026-10-09 ｜ 代码基线：HEAD `947a9f4` + **133 项未提交变更** ｜ 在线：healthlens.cc 200 / api.healthlens.cc 200
> 本报告聚焦一个命题：**如何把 HealthLens 做成"可扩展的"**，并结合 2026 最新技术与趋势给出扩展方向。
> 前序报告：`HealthLens_全面提升评估报告_2026-10-08.md`（诊断 + 提升建议）

---

## 〇、执行摘要

### 最重要的发现：上一轮 P0 已被采纳

复扫确认，项目在 10-08 之后（含未提交工作树）**真实落地了上一份报告的多项 P0**：

| 上轮编号 | 建议 | 现状 | 证据 |
|---|---|---|---|
| P0-1 | 八轴打分器工程 | ✅ **已实现** | `app/core/axis_scorers.py`（493 行，八轴各有代理指标 + 透明公式） |
| P0-3 | L3→L4 规则化映射 | ✅ **已实现** | `data/pathway_to_syndrome_map.json`（59 通路，v1.0） |
| P0-4 | 替换伪 China-PAR / 改称自评量表 | ✅ **已改** | README 现称"沿用 China-PAR 风险因素**框架**（非系数）" |
| P0-22 | GDPR 同意持久化 | ✅ **已实现** | `app/models/gdpr_consent.py` + `alembic/versions/005_add_gdpr_consent.py` |
| P0-26 | 拆掉 BASELINE=31 | ✅ **已修复** | `ci.yml` 现为"任何 failed/error 直接 exit 1" |
| — | 许可证 | ✅ 已改 | Proprietary → **MIT** |
| — | 版本漂移 | ✅ 部分统一 | README 已改为 v0.22.0 |

> 这是一个**值得肯定的响应速度**。项目已从"八轴只有 1 轴能算"推进到"八轴全部有打分器"。

### 但新的结构性问题浮现了

> **HealthLens 目前是"堆叠式增长"（accretion），不是"扩展点式增长"（extension）。**
> 每新增一条轴、一个连接器、一个证据源、一个技能，都要**改核心文件**。

具体证据：`app/core/axis_scorers.py` 里有 **56 处硬编码阈值**（`penalty += 28` / `>= 7.0` 之类），而 `data/healthlens_config.json` 里每条轴只有 `threshold: 0.5` 一个数字。
**白皮书 §2.2 明确宣称"轴内阈值、权重集中在配置中心，可由领域专家调参，不写死在代码里"——这句话与代码不符。**

这意味着：
- 想加第 9 条轴 → 要改 `axis_scorers.py` + `AXIS_META` + `config.json` + `fusion_engine.py` 四处
- 想让中医师调阈值 → 改不了，得改代码
- 想把 699 部古籍结构化 → 没有批量管线契约，只能一部部手写规则

### 一句话结论

> **科学内核已经"有"了，但它是"铸死的"，不是"可插拔的"。**
> 下一步的决定性动作不是继续加功能，而是**把内核插件化**——让轴、连接器、证据源、技能都变成可注册、可配置、可热插拔的单元。

### 可扩展性评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 模块化程度 | **35%** | 目录分层清晰，但模块间靠 import 硬耦合 |
| 扩展点完备度 | **40%** | ConnectorRegistry / skills / MCP 三个真扩展点；轴、证据源无 |
| 配置驱动程度 | **25%** | config.json 存在但**大半是死配置**，真参数在代码里 |
| 协议开放度 | **55%** | MCP 扎实；缺 A2A / AG-UI / 标准医疗互操作 |
| 数据管线可扩展性 | **30%** | 701 书目 → 2 部结构化，无批量契约 |
| 可测试性 | **50%** | 56 个测试文件；但无契约测试、无插件测试 |
| **加权总分** | **≈ 39%** | **可跑，但不可长大** |

---

## 一、复扫：项目最新状态

### 1.1 变更盘点（相对 HEAD）

- **133 项未提交变更**（上轮为 95 项）
- **新增关键文件**：
  - `app/core/axis_scorers.py`（493 行）— 八轴打分器
  - `data/pathway_to_syndrome_map.json`（18.9 KB）— 通路→证候映射
  - `app/models/gdpr_consent.py` + `alembic/versions/005_add_gdpr_consent.py`
  - `app/lib/pulse_engine.py`、`app/api/pulse.py`、`app/connectors/pulse_gateway.py`、`app/connectors/edge_gateway.py`、`app/api/edge_ticket.py`、`app/api/device_metrics.py` — 脉象硬件链路
  - `docs/EDGE_GATEWAY.md`、`data/DATASET_CARD.md`、`data/publish_hf.py`、`data/publish_dataset_repo.py`、`data/verify_dataset_repo.py` — 数据集发布
  - `app/utils/geo_translator.py` — GEO 多语言
  - `tests/core/test_axis_scorers.py`
  - 新增 workflow：`docker-publish.yml`、`mcp-publish.yml`、`mcp-test.yml`、`publish-dataset.yml`
- **删除 9 个 API 模块**：`compliance_api.py`、`hl_agent.py`、`hl_compliance_api.py`、`hl_pipeline_api.py`、`hl_report_generator.py`、`hl_skills_api.py`、`pipeline_api.py`、`report_generator.py`、`skills_api.py`
  → ⚠️ **删除的是 9 个 API 层文件，但对应能力是否迁移完成需确认**（`skills_api.py`、`pipeline_api.py` 被删，而 README 仍宣传 `/api/v1/skills/*` 与 `/api/v1/pipeline/*` 端点）

### 1.2 当前规模

| 指标 | 数值 |
|---|---|
| API 端点 | **197 个**（`@router.*` 装饰器计数） |
| 前端页面 | **15 个** |
| 测试文件 | **56 个** |
| 数据库表 | 49 张（白皮书实测） |
| 八轴打分器硬编码阈值 | **56 处** |
| 证据库 | 120 条 |
| 古籍书目 / 已结构化 | 701 部 / **2 部** |

### 1.3 更新后的板块完成度

| 板块 | 上轮 | 本轮 | 变化 |
|---|---|---|---|
| 科学内核（八轴） | 25% | **55%** | ⬆️⬆️ 打分器已实现，但硬编码、未配置化 |
| 合规安全 | 30% | **45%** | ⬆️ GDPR 持久化落地 |
| 工程成熟度 | 45% | **55%** | ⬆️ CI 硬门禁修复 |
| 学术验证 | 45% | **50%** | ⬆️ 轴数统一（A–H），仍 in-silico |
| 数据采集 | 25% | **30%** | ⬆️ 脉象链路补齐，连接器仍 mock |
| **可扩展性** | — | **39%** | 🆕 **本次新增维度，最大短板** |

---

## 二、可扩展性诊断（核心章节）

### 2.1 先定义"可扩展"

> **可扩展 = 新增一种能力时，不需要修改核心文件。**

对照这个定义逐项检查：

| 想新增 | 现在要改什么 | 是否可扩展 |
|---|---|---|
| 第 9 条轴 | `axis_scorers.py`（AXIS_META + 打分函数 + 注册分支）+ `config.json` + `fusion_engine.py` 的 `ALL_AXES` 消费逻辑 | ❌ |
| 调整某轴阈值 | 改 `axis_scorers.py` 里的字面量 | ❌ |
| 新增数据源连接器 | 加一个类 + 在 `app/connectors/__init__.py` 注册 | ⚠️ 半 |
| 新增证据源（如 PubMed 自动抓取） | 无接口，需改 `fusion_engine` 的匹配逻辑 | ❌ |
| 新增一个 Skill | 建目录（SKILL.md + run.py + test.py），`scaffold.py` 自动发现 | ✅ |
| 新增 MCP 工具 | 改 `mcp_server.py` 的 tools 列表 | ⚠️ 半 |
| 新增一部古籍结构化 | 手写/扩展 `rule_extract` 规则，无批量管线 | ❌ |
| 新增一个合规地区（如 EU/PIPL） | 无策略层，散落在各模块 | ❌ |

**结论：8 个高频扩展场景中，只有 1 个（Skill）是真正可扩展的。**

### 2.2 现有扩展点盘点（值得保留的真资产）

| 扩展点 | 位置 | 评价 |
|---|---|---|
| **ConnectorRegistry** | `app/connectors/base.py` | ✅ 真注册表模式（`_connectors: dict` + `register()` 装饰器），设计正确 |
| **Skill 契约** | `skills/scaffold.py` + `SKILL.md/run.py/test.py` | ✅ 契约清晰、可自动发现，是全仓最成熟的扩展点 |
| **MCP 三层工具** | `healthlens_agent/mcp_server.py` | ✅ L1/L2/L3 分级 + 官方包双路径，真协议 |
| **pipeline_registry** | `healthlens_agent/pipeline_registry.py` | ⚠️ 有注册表，但与 auto-pipeline 的 8 阶段关系不清 |
| **配置中心** | `data/healthlens_config.json` | ⚠️ **只被 `healthlens_agent/config.py` 加载，FastAPI 后端从不读它** —— 死配置 |

### 2.3 阻断扩展的 7 个结构性障碍

#### 障碍 1：参数与代码耦合（最致命）
`axis_scorers.py` 中 **56 处硬编码阈值**：
```python
if g > 7.0:      penalty += 28
elif g > 6.1:    penalty += 18
elif g > 5.6:    penalty += 8
```
而 `config.json` 里 A 轴只有：
```json
{"name":"气化-自噬","aliases":["autophagy","气"],"threshold":0.5,"risk_threshold":0.3}
```
→ **配置中心是装饰品**。领域专家（中医师/营养师/内分泌医生）无法调参，产品迭代被代码发布节奏绑架。

#### 障碍 2：模块加载用 importlib-by-path 硬编码
`app/lib/fusion_engine.py:74`：
```python
"core", "axis_scorers.py",
```
用 `importlib.util.spec_from_file_location("axis_scorers", _AXIS_SCORERS_PATH)` 按**文件路径**加载模块。
→ 脆弱耦合：重命名/移动文件即静默失效（`_HAS_AXIS_SCORERS = False` 后降级）；无插件发现机制。

#### 障碍 3：无事件总线
全仓**无 EventBus / emit / subscribe**（已 grep 确认）。
报告上传 → OCR → 解析 → 八轴打分 → 融合 → 通知，全靠显式函数调用串联。
→ 想加"用户上传报告后自动推送到企业微信"，必须改 `records.py` 核心流程。

#### 障碍 4：无依赖注入容器
只有 FastAPI 的 `Depends(get_db)` / `Depends(get_current_user)`；引擎层全是模块级单例 + 直接 import。
→ 无法替换实现（如把 mock 连接器换成真连接器而不改调用方），无法做 A/B 测试两套融合算法。

#### 障碍 5：无版本化契约层
没有 Pydantic 定义的 `AxisScorerContract` / `ConnectorContract` / `EvidenceSourceContract`。
→ 第三方（或未来的自己）无法安全地实现一个"外部轴插件"。

#### 障碍 6：数据散落三处，无单一真源
八轴的参数同时存在于：
1. `data/healthlens_config.json`（threshold/risk_threshold）
2. `app/core/axis_scorers.py`（56 个真阈值）
3. `data/case_evidence_db.json`（`axes_legend`，且含 I/J 两轴残留）

→ 三处不一致的风险已经发生：`case_evidence_db.json` 的 `axes_legend` 里仍有 **I 轴（外泌体-细胞通讯）与 J 轴（再生医学）**，而代码只有 A–H。

#### 障碍 7：仓库结构混乱，边界模糊
- **双 alembic**：`alembic/versions/`（5 个）vs `healthlens/alembic/versions/`（4 个）
- **双前端**：`frontend/`（SPA）vs FastAPI 服务端渲染的 GEO/SEO 站（无互相链接）
- **`healthlens/` 旧副本**与 `app/` 并行存在
- `auto-pipeline/` 26 MB 中 97% 是重复构建产物

---

## 三、扩展方向（结合 2026 最新技术）

### 方向 1：插件化内核 —— 把"轴"变成可插拔单元【P0，最高优先】

**问题**：加一条轴要改 4 处代码。

**目标**：加一条轴 = 新增一个 YAML/JSON 描述文件 + 一个实现文件，**不改核心**。

**做法**：
```
data/axes/
  A.autophagy.yaml     ← 声明式：指标、阈值、公式、证据来源、版本
  B.mitochondria.yaml
  ...
  I.exosome.yaml       ← 未来新增，核心零改动
```
```yaml
# A.autophagy.yaml
axis: A
label: 气化-自噬
concept: 气/气化
version: 1.2.0
evidence_source: 中国血脂异常防治指南2023 / ADA2024
inputs:
  - key: glucose
    unit: mmol/L
    bands: [{op: ">", v: 7.0, penalty: 28}, {op: ">", v: 6.1, penalty: 18}, {op: ">", v: 5.6, penalty: 8}]
  - key: hba1c
    bands: [{op: ">=", v: 6.5, penalty: 22}, ...]
aggregate: {form: "100 - sum(penalty)", normalize: true}
```

**收益**：
- 领域专家可调参（改 YAML 不改代码）
- 加轴零核心改动
- 阈值可版本化、可审计、可回滚
- 解决障碍 1、2、5、6

**技术要点（2026）**：配置即代码（Config-as-Product）+ JSON Schema 校验 + 启动时契约测试。

---

### 方向 2：Agent 协议三层化（MCP + A2A + AG-UI）【P0-P1】

**2026 协议生态已分层明确**：

| 层 | 协议 | 解决什么 | HealthLens 现状 |
|---|---|---|---|
| 工具集成层 | **MCP** | Agent 如何接工具与数据 | ✅ **已有**（10 工具三层分级） |
| Agent 协作层 | **A2A** | Agent 之间如何互相调用 | ❌ 缺 |
| 前端交互层 | **AG-UI** | Agent 状态如何流式呈现给前端 | ❌ 缺 |

**扩展动作**：
1. **A2A**：发布 `/.well-known/agent-card.json`，把"八轴融合 Agent""证据分级 Agent"注册为可被外部 Agent 调用的服务
   → HealthLens 从"一个 App"变成"**健康领域的 Agent 能力节点**"
2. **AG-UI**：四角色 Agent 团队（Planner/Executor/Critic/Referee）目前是**单向管道无 LLM**（上轮已诊断）。用 AG-UI 协议重构为可观测的流式推理，前端实时看到"思考→执行→批判→裁决"过程
3. **MCP 加注**：上轮已定位 MCP 为最被低估的真资产 → 发布官方 MCP Registry、提供 Claude/Cursor 一键配置

**战略意义**：这是 HealthLens 唯一能"以极小团队撬动极大生态"的路径。竞品（Function/Superpower）没有 MCP/A2A 布局。

---

### 方向 3：医疗互操作标准接入（FHIR / SMART / CDS Hooks / Health Connect / GA4GH）【P1】

**现状**：已有 FHIR R5 导出（`app/core/fhir_exporter.py`），但是"单向导出"。

**2026 标准的正确用法**：

| 标准 | 用途 | 扩展动作 |
|---|---|---|
| **SMART on FHIR** | 让 HealthLens 作为 App 嵌入医院 EHR | 实现 OAuth2 + launch context，成为 EHR 内可启动应用 |
| **CDS Hooks** | 在 EHR 工作流中触发健康建议 | 把"八轴评估"包装为 `patient-view` hook 服务 |
| **HL7 FHIR R4/R5** | 双向数据交换 | 从"导出"升级为"订阅 + 写入" |
| **Android Health Connect / HealthKit** | 统一可穿戴数据入口 | **替代逐个厂商 OAuth**（华为/小米/Withings 各自对接成本极高） |
| **GA4GH（VCF / Beacon）** | 基因数据标准 | 基因上传走 VCF 标准校验，未来可接 Beacon 网络 |
| **OMOP CDM** | 研究数据模型 | 把用户数据映射为 OMOP，支撑真实世界研究（RWS） |

**关键洞察**：HealthLens 的 5 个连接器全是 mock、`.configure()` 零调用点（上轮诊断）。
**与其逐个对接厂商 OAuth，不如直接接 Health Connect / HealthKit**——一次接入覆盖全部主流设备。这是**成本最低、覆盖最广**的路径。

⚠️ **合规提示**：SMART on FHIR / CDS Hooks 会显著拉近与临床系统的距离。需严守 wellness 边界（见第六章）。

---

### 方向 4：GraphRAG + 中医知识图谱 —— 内容护城河的扩展引擎【P1】

**现状**：
- `data/tcm_mkg/chp_entities.json` 6.0 MB 中药知识图谱
- 701 部书目（仅元数据）+ **仅 2 部结构化**（613 条实体）
- `data/pathway_to_syndrome_map.json` 59 通路（新建）
- 结构化靠**手写规则抽取**（`rule_extract`）

**瓶颈**：699 部古籍待结构化，靠手写规则需要数年。

**2026 技术路径：GraphRAG（向量 + 图谱 + LLM）**
- Gartner 报告：**68% 传统 RAG 项目因推理失败陷入困境**；GraphRAG 通过引入图谱结构化关系解决
- 微软 GraphRAG 框架已开源，社区实践成熟

**扩展架构**：
```
古籍语料（699 部）
   ↓ ① LLM 抽取（实体/关系/原文引证，强制引用）
   ↓ ② 规则校验（术语表 + 国家标准术语对齐）
   ↓ ③ 人工抽检（抽样 N% 复核）
   ↓ ④ 图谱融合（并入 chp_entities + pathway_to_syndrome_map）
   ↓ ⑤ 向量索引（GraphRAG 检索层）
   ↓ ⑥ 对外服务（MCP 工具 / A2A / 公开数据集）
```

**必须做的两件事**：
1. **术语对齐国家标准**：2026-04 发布的《中医舌脉象术语》国家标准 + 2026-07-01 实施的《中医基础理论术语》等 4 项国标 → 图谱实体必须映射到国标术语，这是**国际化与学术可信度的前提**
2. **建"抽取契约"**：定义实体/关系/证据的 JSON Schema，让抽取可批量、可增量、可回滚

**数据质量警告**：现有 `pathway_to_syndrome_map.json` 中已出现垃圾条目 —— `"_"` 和 `"a"`（单字符键，`syndromes: []`，`case_ids: ["","","","",""]`）。59 个通路中仅 38 个有证候。**建管线前先做数据清洗。**

---

### 方向 5：数字健康孪生（Digital Twin）【P2】

**2026 趋势**：数字孪生正从"静态虚拟副本"转向"智能、AI 驱动、可预测"的系统。在长寿医学中，AI + 数字孪生已在 2026 到达拐点。

**HealthLens 的起点**：`app/lib/wellness_simulator.py`（333 行）已有一个自造的线性差分模型，耦合系数写死（0.12/0.10/0.10/0.12/0.10），docstring 诚实标注"启发式/非临床"。

**扩展路径**：
1. 八轴时序数据（`observations` 表已有 TimescaleDB）→ 学习轴间真实耦合矩阵
2. 干预响应建模：用户采纳某建议后，观测八轴变化 → 反推干预效应
3. 反事实仿真："如果我把睡眠提前 1 小时，D 轴和 G 轴会怎样？"
4. 用 120 条证据库的效应量作为先验标定

**价值**：这是把"数据飞轮"（PRINCIPLES.md 的核心主张）真正落地的载体 —— 目前飞轮完全不存在（上轮诊断 G5 未达成）。

---

### 方向 6：边缘 AI + 隐私计算【P2】

**问题**：连接器与合规是两个死结 —— 数据进不来（连接器全 mock），进来了又不敢用（HIPAA/PIPL 零实现）。

**2026 技术解法**：

| 技术 | 用途 | HealthLens 落点 |
|---|---|---|
| **端侧推理（Edge AI）** | 舌象/脉象/面部在设备端推理，原图不出端 | `edge/` 已有真实 DSP 特征提取（NMS + RR 间期离群剔除），只差模型部署 |
| **联邦学习（Federated Learning）** | 数据不出端，只上传梯度 | 直接解决"数据飞轮 vs 隐私"矛盾 |
| **隐私保护训练加速** | MIT 2026-04 提出在消费级设备上加速隐私保护训练 | 让"每台手机都是训练节点"变得可行 |

**战略意义**：如果 HealthLens 能做到"用户数据永不离开设备，但群体模型持续变准"，这将是一个**竞品无法在短期内复制的差异化壁垒**——Function/Superpower 的商业模式依赖中心化数据。

---

### 方向 7：配置即产品（Config-as-Product）【P0，与方向 1 并行】

把 `data/healthlens_config.json` 从"死配置"变成**单一真源 + Schema 校验 + 版本化 + 可视化编辑**。

```
data/config/
  schema/config.schema.json      ← JSON Schema，CI 校验
  v1.2.0/axes/*.yaml             ← 版本化
  v1.2.0/fusion.yaml
  CHANGELOG.md                   ← 参数变更审计
```
- 后端启动时加载并**校验**（不合规拒绝启动）
- 提供"参数实验室"页面：领域专家改参数 → 预览对样例用户的影响 → 提交
- 每次变更留痕（谁在何时把 A 轴血糖阈值从 7.0 改成 6.8）

**解决**：障碍 1、5、6，并让"中医师参与调参"成为可能 —— 这是**领域知识进入产品的唯一可持续通道**。

---

### 方向 8：开放数据与生态【P1】

**已有基础**：`data/DATASET_CARD.md`、`publish_hf.py`（HuggingFace）、`publish_dataset_repo.py`、`verify_dataset_repo.py`、`.github/workflows/publish-dataset.yml`

**扩展动作**：
1. 把三份资产发布为**可引用数据集**：
   - 120 条案例证据库（带 DOI/效应量/证据等级）
   - 613 条古籍实体（含原文引证）
   - 八轴定义与映射表
2. 加 **DOI**（Zenodo/HuggingFace DOI）+ **LICENSE**（数据用 CC-BY，注意 AGPL/ODbL 传染风险）
3. 写**方法学声明**（抽取规则、校验流程、局限）
4. 建**引用 → 学术影响力 → 用户增长**的正循环

**战略意义**：数据开源是**最便宜的获客与背书**。学术引用会反向强化"八轴框架"的权威性，这正是论文当前最缺的。

---

## 四、目标架构（Target Architecture）

```
┌─────────────────────────────────────────────────────────────┐
│  接入层（Interop Layer）                                     │
│  MCP ✅ │ A2A 🆕 │ AG-UI 🆕 │ SMART on FHIR 🆕 │ CDS Hooks 🆕 │
├─────────────────────────────────────────────────────────────┤
│  插件内核（Plugin Kernel）🆕  ← 本次核心改造                  │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │ Axis     │ Connector│ Evidence │ Skill    │ Compliance│ │
│  │ Registry │ Registry │ Registry │ Registry │ Strategy  │ │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
│  统一契约层（Pydantic Schema + 版本 + 契约测试）              │
├─────────────────────────────────────────────────────────────┤
│  领域引擎层                                                  │
│  八轴打分 │ 融合推荐 │ 辨证 │ PGx │ 风险自评 │ 脉象/舌象      │
├─────────────────────────────────────────────────────────────┤
│  知识层                                                      │
│  古籍图谱(GraphRAG) 🆕 │ 证据库120 │ 通路映射59 │ CHP 6MB     │
├─────────────────────────────────────────────────────────────┤
│  数据层                                                      │
│  PostgreSQL+TimescaleDB │ Redis │ MinIO │ 配置中心(单一真源)🆕 │
├─────────────────────────────────────────────────────────────┤
│  基础层                                                      │
│  FastAPI │ Celery │ Prometheus │ CI(硬门禁) ✅ │ 事件总线 🆕  │
└─────────────────────────────────────────────────────────────┘
```

**三条改造主线**：
1. **向上**：接协议与标准（MCP → A2A/AG-UI → SMART/CDS Hooks）
2. **向内**：插件化内核 + 配置单一真源（把铸死的变成插拔的）
3. **向下**：知识层 GraphRAG + 数据层孪生/联邦

---

## 五、扩展路线图

### 阶段 A（0–6 周）：内核插件化 —— 让内核"能长大"

| # | 动作 | 出口标准 |
|---|---|---|
| A1 | 定义三大契约：`AxisScorerContract` / `ConnectorContract` / `EvidenceSourceContract`（Pydantic + 版本） | 契约有 Schema + 契约测试 |
| A2 | 八轴参数外置为 `data/axes/*.yaml` + JSON Schema 校验 | 删除 `axis_scorers.py` 中 56 处硬编码；改 YAML 即改行为 |
| A3 | 建 `AxisRegistry`，替换 importlib-by-path 硬编码加载 | 新增轴 = 加 YAML + 实现，核心零改动 |
| A4 | config 单一真源 + CI 校验 + 变更留痕 | 三处不一致问题消除；启动时校验失败即拒绝 |
| A5 | 引入轻量事件总线（进程内 + Redis pub/sub） | "报告上传 → 自动评估 → 通知"可声明式订阅 |
| A6 | 清洗 `pathway_to_syndrome_map.json` 垃圾条目 + 统一轴数（删 I/J 残留） | 无单字符键、无空 case_ids；全仓只有 A–H |

### 阶段 B（6–16 周）：协议与标准 —— 让生态"接得上"

| # | 动作 |
|---|---|
| B1 | 发布 A2A `agent-card.json`，把八轴/证据分级注册为外部可调用 Agent |
| B2 | 用 AG-UI 重构四角色 Agent 为可观测流式推理（同时补真实 LLM，上轮 P0-13） |
| B3 | MCP 发布官方 Registry + 一键配置文档 |
| B4 | 接入 Android Health Connect + HealthKit，**替代逐个厂商 OAuth** |
| B5 | 基因上传走 GA4GH VCF 标准 + 校验 |
| B6 | 探索 SMART on FHIR / CDS Hooks（严守 wellness 边界，见第六章） |

### 阶段 C（16–36 周）：知识与孪生 —— 让护城河"长得深"

| # | 动作 |
|---|---|
| C1 | GraphRAG 管线：699 部古籍批量抽取 + 规则校验 + 人工抽检 |
| C2 | 术语对齐 2026 国标（舌脉象术语 / 中医基础理论术语） |
| C3 | 数字孪生 v1：八轴时序 → 耦合矩阵 → 反事实仿真 |
| C4 | 联邦学习 PoC：端侧舌象/脉象推理，数据不出端 |
| C5 | 数据集发布（Zenodo/HF DOI + 方法学声明） |
| C6 | 真实用户研究（n≥30 前后对照，上轮 P1-31） |

---

## 六、风险与边界

| 风险 | 等级 | 说明与对策 |
|---|---|---|
| **合规越线** | 🔴 高 | SMART on FHIR / CDS Hooks 会显著拉近临床距离。**对策**：把互操作定位为"数据通道"而非"决策输出"；PGx 去"致病性分级"（上轮 P0-23 仍未做）；严守 FDA General Wellness 四要素 |
| **过度设计** | 🟠 中高 | 插件化本身有成本。**对策**：只对**会重复增长**的维度插件化（轴、连接器、证据源、技能），不要对一次性业务逻辑插件化。第 9 条轴出现前，先把 8 条轴外置即可 |
| **GraphRAG 成本与幻觉** | 🟠 中 | LLM 抽取古籍会产生幻觉。**对策**：强制原文引证 + 规则校验 + 人工抽检 + 只发布校验过的子集；保留现有确定性 `rule_extract` 作为基线 |
| **数据质量** | 🟠 中 | `pathway_to_syndrome_map.json` 已出现垃圾条目；`case_evidence_db.json` 仍有 I/J 轴残留。**对策**：阶段 A6 先清洗 |
| **API 删除未迁移** | 🟠 中 | 9 个 API 模块被删（含 `skills_api.py`/`pipeline_api.py`），但 README 仍宣传对应端点。**对策**：核对并修正文档，或恢复端点 |
| **单人 + 133 项未提交** | 🟠 中 | 知识单点；未提交变更持续累积有丢失风险。**对策**：先提交；引入 pre-commit |
| **数据开源许可传染** | 🟡 中 | 古籍语料可能含 AGPL/ODbL 成分。**对策**：发布前做许可审计（上轮已识别该风险） |
| **联邦学习的收益不确定性** | 🟡 中 | 小用户量下联邦学习收益低。**对策**：先做端侧推理（确定收益），联邦学习等用户量到万级再启动 |

---

## 七、结语

上一轮报告的核心判断是"**宣称的五层因果链与八轴引擎是叙事，不是实现**"。
这一轮复扫发现：**这个判断已经过时了——八轴打分器真的被写出来了**。这是一个真实且重要的进步。

但新的问题也随之浮现，而且性质不同：

> 上一轮的问题是"**有没有**"；这一轮的问题是"**长得大吗**"。

八轴打分器现在是 493 行、56 个硬编码阈值、靠文件路径加载的**单文件实现**。
它可以算，但它不能：
- 让中医师调阈值
- 加第 9 条轴而不改核心
- 把 699 部古籍批量结构化
- 被第三方实现并注册进来

而 HealthLens 的全部战略价值，恰恰压在"**轴会持续增加、古籍会持续结构化、证据会持续积累**"这个假设上。

所以这份报告的第一优先级只有一句话：

> **把内核插件化。让"轴"从代码变成数据，让"扩展"从改文件变成加文件。**

这件事做成了，HealthLens 就从"一个不断加功能的 App"变成"一个能自我生长的平台"——
MCP/A2A 的生态接入、GraphRAG 的知识扩展、数字孪生的数据飞轮、开放数据集的学术影响，才会从"要做的事"变成"能做的事"。

做不成，每一条新轴、每一部新古籍、每一个新数据源，都会继续以"改核心文件"的方式堆积，
最终把一个正确的架构方向，拖成一个改不动的巨石。

---

*本报告基于 2026-10-09 的代码工作树（HEAD `947a9f4` + 133 项未提交变更）与在线实测。所有判定均附文件路径与行号证据，可逐条复核。*
