# HealthLens 案例库 DOI 核验报告（2026-10-13）

**核验方法**：Crossref REST API 实解析（`api.crossref.org/works/<doi>`），不臆造 DOI。

## 一、总体覆盖

- 案例总数：**120**
- ✅ 已验证可解析（含幻觉已替换）：**6**
- 🔁 幻觉 DOI 已替换为真文献：**1**（CASE-006）
- ⚠️ 纯文本来源待复核（无 DOI 或需全文复核）：**14**
- 📜 古籍/传统文献（无需 DOI）：**8**
- 💀 失效引用（DOI 解析 404 / 幻觉）：**1**
- 🤖 自动生成验证夹具（设计上无文献来源）：**91**
- ❌ 完全无来源：**0**

> **诚实说明（数据完整性关键）**：案例库 120 条实为**两种 schema 的混合**——前 29 条（CASE-001…029）是带文献来源的证据案例；后 91 条（HL-0030…0120）是**按低分轴自动生成的验证夹具**（`case_id`/`symptom`/`tcm_source` 模式），设计上即无一手文献来源，并非「真实人体试验/RCT」。meta 中「用真实人体试验/RCT 数据作证」的声明仅适用于前 29 条。本报告**未对无来源的条目臆造 DOI**——S1-1「覆盖率≥95%」在当前真实数据下无法诚实达成，需后续真实回填纵向数据或将验证夹具与证据案例明确分区。

## 二、逐 DOI 解析结果

| DOI | 状态 | 期刊 | 年 | 标题 |
|---|---|---|---|---|
| `10.1016/j.clnesp.2024.11.002` | ✅ | Clinical Nutrition ESPEN | 2025 | Dawn-to-dusk intermittent fasting is associated with overexp |
| `10.1016/j.jhep.2025.06.005` | ✅ | Journal of Hepatology | 2025 | Efficacy and safety of time-restricted eating in metabolic d |
| `10.1016/j.sleep.2020.05.009` | ✅ | Sleep Medicine | 2020 | Decreased functional connectivity within the salience networ |
| `10.1016/j.ther.2026.105127` | ❌not_found | | | |
| `10.1038/s41467-024-45260-9` | ✅ | Nature Communications | 2024 | Fasting-mimicking diet causes hepatic and blood markers chan |
| `10.1038/s41591-024-03096-2` | ✅ | Nature Medicine | 2024 | Effects of intermittent senolytic therapy on bone metabolism |
| `10.1038/s41591-024-03375-y` | ✅ | Nature Medicine | 2025 | Effects of early, late and self-selected time-restricted eat |
| `10.1038/s41591-026-04102-8` | 🔁幻觉→`10.1038/s41591-024-03096-2` | Nature Medicine | 2024 | Effects of intermittent senolytic therapy on bone metabolism |
| `10.1073/pnas.1418490112` | ✅ | Proceedings of the National Academy of Sciences | 2014 | Evening use of light-emitting eReaders negatively affects sl |
| `10.1186/s12967-026-08038-9` | ✅ | Journal of Translational Medicine | 2026 | Exercise-induced muscle exosomes: microRNA cargo as regulato |
| `10.3390/nu17101695` | ✅ | Nutrients | 2025 | Regulation of Metabolic Aging Through Adenosine Mono Phospha |

## 三、案例级 citation_status 分布（见 case_evidence_db.json 各 case 字段）

每个案例现含 `citation_status` / `doi_verified` / `doi` / `source_canonical` 字段，供下游 fusion_engine 与 Agent 引用时区分证据强度。
