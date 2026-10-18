# 核心概念（Concepts）

术语、枚举、公式与接口说明。**面向开发者与非技术阅读者双通道**：每个概念同时给出"通俗解释"和"代码位置"。

---

## 1. 术语表（Glossary）

| 术语 | 通俗解释 | 代码位置 |
|------|----------|----------|
| 体检指标（Metric） | 一次体检中被测量的项目，如 ALT、LDL-C | `backend/src/models/report_schema.py` |
| 参考范围（Reference Range） | 该指标在健康人群中的正常区间 | 同上（`reference_range` 字段） |
| 临床显著阈值（Clinical Threshold） | 医学事实库中定义的"值得干预"的临界值 | `backend/medical_facts.json` |
| 危急值（Critical Value） | 达到需要立即就医水平的极端值 | `backend/medical_facts.json`（`critical_value` 字段） |
| 体检摘要（Health Summary） | 面向用户的自然语言解读 | `backend/src/services/report_generator.py` |
| 健康画像（Health Profile） | 结构化的解读结果，机器可读写 | `backend/src/models/report_schema.py` |
| 知识卡（Knowledge Card） | 围绕某个指标组装的事实/百科/指南证据链 | `backend/src/services/health_profile.py` |
| 随访计划（Follow-up Plan） | 基于风险分层的复查建议 | `backend/src/services/follow_up.py` |
| 记忆（Memory） | 用户档案、画像、随访计划的持久化存储 | `backend/src/services/memory_store.py` |

---

## 2. 枚举定义

### 2.1 风险象限（`Quadrant`）

```python
enum Quadrant:
    I   = "正常 / 低风险"
    II  = "轻度异常"
    III = "中度异常"
    IV  = "重度异常 / 优先关注"
```

定义位置：`backend/src/models/report_schema.py`

### 2.2 置信度（`Confidence`）

```python
enum Confidence:
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"
```

定义位置：`backend/src/models/report_schema.py`

### 2.3 指标单位（`Unit`）

常见单位枚举（示例）：`mmol/L`、`μmol/L`、`g/L`、`U/L`、`mmHg`、`bpm`、`mg/dL`、`ng/mL`、`%`、`次/分`。

完整清单见 `backend/src/models/report_schema.py` 中 `Unit` 枚举。

### 2.4 报告来源（`Source`）

```python
enum Source:
    TEXT  = "text"      # 用户粘贴的文本
    IMAGE = "image"     # 图片上传后经 OCR
    API   = "api"       # 第三方系统对接
```

### 2.5 医学领域标签（`DomainTag`）

- `cardiovascular`（心血管）
- `endocrine`（内分泌）
- `hepatic`（肝胆）
- `renal`（肾脏）
- `hematology`（血液）
- `immune`（免疫）
- `tumor_marker`（肿瘤标志物）
- `urine`（尿液）
- `imaging`（影像）
- `biochemistry`（生化）

---

## 3. 关键公式

### 3.1 异常方向判定

```
if value > reference_range.upper:   direction = "↑"   # 偏高
elif value < reference_range.lower: direction = "↓"   # 偏低
else:                                direction = "—"   # 正常
```

### 3.2 象限分档

```
over_ratio = (value - upper) / upper        # 偏高幅度
under_ratio = (lower - value) / lower       # 偏低幅度

if direction == "—":           quadrant = I
elif direction == "↑" and over_ratio >= 0.50:      quadrant = IV
elif direction == "↑" and over_ratio >= 0.20:      quadrant = III
elif direction == "↑" and over_ratio >  0:         quadrant = II
# 偏低侧同理，使用 under_ratio
```

> 具体阈值以 `backend/src/services/report_generator.py` 为准。

### 3.3 置信度计算

```
confidence = "high"     # 初始

if reference_range is None:
    confidence = downgrade(confidence)
if metric not in medical_facts:
    confidence = downgrade(confidence)
if source == "image" and ocr_confidence < 0.7:
    confidence = downgrade(confidence)
if rule_channel_result != knowledge_channel_result:
    confidence = downgrade(confidence)
```

`downgrade` 顺序：`high → medium → low`，最低保持 `low`。

### 3.4 整体风险升级规则

```
if 存在单项 quadrant == IV:
    overall = IV
elif 存在 >= 2 项 quadrant ∈ {II, III} 且领域相同:
    overall = III        # 同领域多项联动升级
else:
    overall = max(quadrant)
```

---

## 4. 健康咨询 Agent 工具清单

Agent 以 ReAct 循环运行，可调用以下工具（定义于 `backend/src/agents/tools.py`）：

| 工具名 | 参数 | 返回 |
|--------|------|------|
| `lookup_medical_facts` | `{metric: str, query?: str}` | 医学事实列表 |
| `get_encyclopedia` | `{term: str}` | 百科条目（`{definition, details}`） |
| `retrieve_guideline` | `{topic: str, limit?: int}` | 指南片段 |
| `generate_report` | `{profile: HealthProfile}` | 自然语言解读报告 |

Agent 主循环：`backend/src/agents/health_consultation_agent.py`

---

## 5. MemoryStore 接口

统一记忆访问入口，位于 `backend/src/services/memory_store.py`。

### 5.1 画像相关

- `store_profile(profile: HealthProfile) -> Profile`
- `get_profile(profile_id: str) -> Profile | None`
- `list_profiles(user_id?: str) -> list[Profile]`

### 5.2 医学事实

- `get_facts(metric: str) -> list[Fact]`
- `get_facts_by_tag(tag: str) -> list[Fact]`
- `search_facts(query: str) -> list[Fact]`

### 5.3 指南

- `get_guidelines() -> list[Guideline]`
- `get_guideline(guideline_id: str) -> Guideline | None`
- `search_guidelines(query: str) -> list[Guideline]`

### 5.4 百科

- `get_encyclopedia(term: str) -> EncyclopediaEntry | None`
- `get_encyclopedia_all() -> list[EncyclopediaEntry]`

### 5.5 健康档案

- `store_health_profile(profile) -> UserHealthProfile`
- `get_health_profile(user_id) -> UserHealthProfile | None`
- `add_test_record(profile, record) -> UserHealthProfile`
- `list_test_records(user_id) -> list[TestRecord]`
- `get_trends(user_id, metric) -> list[TrendPoint]`

### 5.6 随访计划

- `store_followup(profile, plan) -> FollowUpPlan`
- `get_followup_by_profile(profile_id) -> FollowUpPlan | None`
- `get_overdue_tasks(profile_id) -> list[FollowUpTask]`

### 5.7 系统

- `reset_all()` — 清空所有内存数据（仅开发/测试用）
- `get_stats() -> dict` — 返回各类数据的计数

**后端端点**：`/api/memory/*`（详见 `backend/src/api/main.py`）

---

## 6. 知识库规模

| 数据源 | 路径 | 规模 |
|--------|------|------|
| 医学事实 | `backend/medical_facts.json` | 242 条，覆盖 181 个指标 |
| 百科 | `backend/medical_encyclopedia.json` | 152 条 |
| 临床指南 | `data/clinical_guidelines_zh.json` | 15 份 |

---

## 7. 常见指标清单（部分）

| 中文名 | 英文名 | 常见参考范围 | 领域 |
|--------|--------|--------------|------|
| 丙氨酸转氨酶 | ALT | 7–40 U/L | 肝胆 |
| 天冬氨酸转氨酶 | AST | 13–35 U/L | 肝胆 |
| 低密度脂蛋白胆固醇 | LDL-C | 0–3.4 mmol/L | 心血管 |
| 糖化血红蛋白 | HbA1c | 4.0–5.6 % | 内分泌 |
| 空腹血糖 | FBG | 3.9–6.1 mmol/L | 内分泌 |
| 尿酸 | UA | 男 208–428 / 女 155–357 μmol/L | 代谢 |
| 肌酐 | CRE | 男 53–106 / 女 44–84 μmol/L | 肾脏 |
| 白细胞计数 | WBC | 4.3–9.6 ×10⁹/L | 血液 |
| 红细胞压积 | HCT | 男 40–50 / 女 37–48 % | 血液 |

完整指标覆盖 30+ 项，解析器见 `backend/src/services/report_parser.py`。
