# HealthLens 前瞻队列数据字典

**版本**：v0.1.0-draft · 2026-10-16
**规范**：DCAT / DataCite 元数据约定；对齐 `app/models/longitudinal.py`

> 参考：`study_protocol.md` §5；`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §6。
> 本字典列出前瞻队列的 32 个字段定义，含数据类型、单位、缺失值编码、采集频率与隐私级别。

## 隐私级别定义

| 级别 | 含义 | 存储策略 | 是否可入共享聚合 |
|---|---|---|---|
| **L0-public** | 完全匿名化聚合 | 可直接公开 | 是 |
| **L1-internal** | 项目内部成员可见 | 加密 + 最小权限 | 否 |
| **L2-sensitive** | 需研究医生角色 | 加密 + 双因子 | 否（脱敏后可） |
| **L3-forbidden** | 明确禁止收集 | 不采集 | 否 |

**缺失值编码**：
- 数值：`NULL`（数据库）/ `null`（JSON）/ `-999`（CSV，慎用）
- 字符串：空字符串 `""`
- 布尔：`null`（未知，非 false）

## 字段清单（32 项）

### A. 参与标识（4 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `participant_id` | string(36) | UUID v4 | 一次性 | L1-internal | 参与者假名 ID，跨研究唯一 |
| `questionnaire_response_id` | string(36) | UUID v4 | 一次性 | L1-internal | 招募问卷响应 ID |
| `study_id` | string(36) | UUID v4 | 一次性 | L1-internal | 关联 `LongitudinalStudy.id` |
| `data_residency_region` | enum | CN / US / EU / UK / AU | 一次性 | L1-internal | 关联 `LongitudinalStudy.data_residency_region` |

### B. 人口学与基本背景（6 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `age_at_enrollment` | int | 岁（25–65） | 一次性 | L2-sensitive | 年龄入排标准 |
| `year_of_birth` | int | 4 位年份 | 一次性 | L3-forbidden（不采集） | 由年龄反推，不入库 |
| `sex` | enum | female / male / non-binary / prefer_not | 一次性 | L2-sensitive | 与生物性别区分 |
| `pregnancy_status` | enum | yes / no / unknown | 一次性 + 每次随访 | L2-sensitive | 排组标准 |
| `city_of_residence` | string(200) | 自由填写 | 一次性 | L2-sensitive | 城市级，非精确坐标 |
| `wearable_device_model` | string(50) | Apple Watch SE / ... | 一次性 | L1-internal | 设备兼容性 |

### C. 健康史与用药（4 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `chronic_disease_history` | list[string] | CV/肿瘤/代谢/精神 | 一次性 | L2-sensitive | 排除标准筛选 |
| `current_medications` | list[string] | 药名列表 | 一次性 + 每月 | L2-sensitive | Q6 前 4 类药物为关键排除项 |
| `food_allergies` | list[string] | 过敏原列表 | 一次性 | L2-sensitive | 饮食臂排除标准 |
| `dietary_restriction` | enum | omnivore / vegetarian / vegan / none | 一次性 | L2-sensitive | 饮食臂匹配 |

### D. 基线测量（5 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `baseline_axis_scores` | JSON | `{A..H: {score, measured, penalty_ratio}}` | 一次性 | L2-sensitive | 八轴基线 |
| `baseline_overall_score` | decimal(5,2) | 0–100 | 一次性 | L2-sensitive | 八轴综合基线 |
| `baseline_biomarkers` | JSON | HbA1c/TG/CRP/... | 一次性 | L2-sensitive | 首次抽血 |
| `baseline_wearable_avg` | JSON | 24 h 平均心率/HRV/步数 | 一次性（前 7 日均值） | L1-internal | 可穿戴基线 |
| `baseline_snapshot_fingerprint` | string(64) | SHA-256 | 一次性 | L1-internal | 对齐 `AxisSnapshot.input_fingerprint` |

### E. 干预期纵向测量（6 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `axis_snapshots` | array | `AxisSnapshot[]` | 每日 | L2-sensitive | 关联 `axis_snapshots` 表 |
| `intervention_events` | array | `InterventionEvent[]` | 事件驱动 | L1-internal | 干预臂切换时点 |
| `biomarker_readings` | array | `BiomarkerReading[]` | 3 次（基线/中期/期末） | L2-sensitive | LOINC 编码 |
| `wearable_daily_sync` | array | 日粒度 JSON | 每日 | L1-internal | 每日同步记录 |
| `subjective_wellness_qol` | JSON | QoL 5 维评分 | 每 2 周 | L1-internal | 主观福祉 |
| `sleep_hrv_daily` | array | `[{date, rmssd, sdnn, deep_sleep_min}]` | 每日 | L1-internal | HRV 与睡眠细粒度 |

### F. 主要终点（3 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `primary_endpoint_delta` | JSON | `{arm: {delta, ci_lower, ci_upper}}` | 研究结束时 | L2-sensitive | 8 周八轴综合分变化 |
| `individual_effect_sizes` | JSON | `IndividualEffect[]` | 研究结束时 | L1-internal | 关联 `nof_one_effect.py` |
| `aggregate_effect` | JSON | `{mu_pop, tau_squared, n, posterior}` | 研究结束时 | L1-internal | 关联 `BayesianHierarchicalAggregator` |

### G. 次要与探索性终点（3 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `biomarker_deltas` | JSON | `{marker: {baseline, endpoint, delta}}` | 研究结束时 | L2-sensitive | 各生物标志物变化 |
| `biological_age_shift` | JSON | `{phenoage, grimage, shift}` | 研究结束时 | L1-internal | 引用 `data/phenoage_alignment.json` |
| `federated_stats` | JSON | 充分统计量 | 各阶段末 | L0-public（已聚合） | 关联 `federated/sufficient_stats.py` |

### H. 元数据与合规（4 项）

| 字段 | 类型 | 单位/枚举 | 采集频率 | 隐私级别 | 说明 |
|---|---|---|---|---|---|
| `consent_version` | string(50) | v0.1.0-draft | 每次同意变更 | L1-internal | 关联 `LongitudinalStudy.consent_version` |
| `data_jurisdiction` | enum | cn / eu / uk / ... | 一次性 | L1-internal | 关联 `AxisSnapshot.jurisdiction` |
| `audit_trail_ref` | string(36) | UUID v4 | 事件驱动 | L1-internal | 关联 `audit_event.py` |
| `study_protocol_version` | string(50) | v0.1.0-draft | 一次性 | L1-internal | 关联本方案版本 |

## 与现有模型的对齐

| 字典字段 | `app/models/longitudinal.py` 表 |
|---|---|
| `participant_id` / `study_id` | `LongitudinalStudy.user_id` / `.id` |
| `data_residency_region` | `LongitudinalStudy.data_residency_region` |
| `consent_version` | `LongitudinalStudy.consent_version` |
| `axis_snapshots` | `AxisSnapshot` 表 |
| `baseline_snapshot_fingerprint` | `AxisSnapshot.input_fingerprint` |
| `data_jurisdiction` | `AxisSnapshot.jurisdiction` |
| `intervention_events` | `InterventionEvent` 表 |
| `biomarker_readings` | `BiomarkerReading` 表 |

## 版本历史

- v0.1.0-draft（2026-10-16）：初稿，等待 IRB 提交前评审

---

**wellness 声明**：本字典字段设计符合 wellness 研究定位；不采集 L3-forbidden 级别数据；不用于医疗诊断。
