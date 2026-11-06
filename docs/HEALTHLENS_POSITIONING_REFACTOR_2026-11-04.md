# HealthLens 定位重构：诚实边界声明（2026-11-04）

> 本声明记录 2026-11-04 定位重构（用户拍板 3 项，工程侧实施）的架构决策与诚实边界。
> 目的：明确本平台"做什么、不做什么"，不宣称未经验证的能力。

## 1. 定位一句话

HealthLens 是**精准健康评估与健康管理平台**（明确**非医疗**），核心价值是：
**AI 辅助健康评估 + 风险分层 + 趋势预警**，用八轴稳态生物学 A–H + 五层因果链
L1基因→L2蛋白→L3细胞通路→L4中医证候→L5干预，帮助用户理解自身健康状态并给出
可执行的非药物生活方式建议。

## 2. 解释 ↔ 诊断边界（架构层一次做对）

- **核心引擎 = 解释层**（永远可用）：八轴状态解读、风险分层、偏离定位、趋势预警。
  实现：`app/core/diagnosis_gate.py` 的 `interpret()`，`app/lib/fusion_engine.py`，
  `app/core/risk_engine.py`。
- **诊断 = 独立门控模块**（可插拔 / 单独验证 / 单独注册），**当前不激活**，只留接口：
  - `app/core/diagnosis_gate.py::DiagnosisGate`，默认 `active=False`；
  - 未激活时 `diagnose()` **fail-closed**，返回 `not_active`，**不执行任何诊断逻辑**；
  - 激活开关：环境变量 `HEALTHLENS_DIAGNOSIS_GATE`（1/true/yes/on 才激活）；
  - 任何诊断结论须由**持牌医疗机构**出具（门控层内部语义，非本平台提供）。
- **分水岭**：是否激活此门控 = 是否进入"医疗器械"监管路径，本平台**默认不进入**。

## 3. 诊断措辞重构（对外表述）

- 原："AI 诊断" → 现："**AI 辅助健康评估 + 风险分层 + 趋势预警**"。
- 所有对外 API 文档 / docstring / tag 已同步：`/api/v1/diagnosis` 路由 tag 改
  `["健康评估"]`，`/api/v1/diagnosis/agent` tag 改 `["AI辅助评估Agent"]`。
- 评估结果 `kind` 恒为 `risk_finding`（非 `diagnosis`），并带免责声明
  "本结果为 AI 辅助健康评估与风险分层，非诊断结论"。

## 4. 药物隔离

- **个体化家庭合成药 / 家庭中药（可控计量）**：列为**远期隔离方向**，**不进 v1.0 / 近期路线图**。
- 平台只做：**个体化用药建议（经持牌医师处方）→ 持牌药店 / 医疗机构调配**。
- 数据模型**可预留**"药食同源 / 中药成分本体 + 剂量控制"占位（Phase 3+），但**不建功能**。
- 已确认无现有家庭合成药功能代码，无需删除。

## 5. 非药物个性化方案引擎（核心交付物，本次新增）

- 实现：`app/core/non_pharma_engine.py::NonPharmaPlanEngine`。
- **抽屉组合（信息完整度 → 精度分档）**：用户给的信息越全 → 精度越准；给得少 → 精度略低但可用。
  - **basic**：仅生活方式画像 → 基础 6 条日课（晨起温水 / 晨间活动 / 均衡午餐 / 午间小憩 / 傍晚活动 / 规律睡眠）；
  - **standard**：+ 化验 / 体检指标 → 按生物标志追加分层（控糖晚餐 / 降脂早餐 / 限盐监测等）；
  - **advanced**：+ 基因 / 组学通路 → 按 AMPK / MTOR / NAD 通路与八轴弱项精调（运动增敏 / 限时进食 / NAD 前体提示等）。
  - **每档都可用**，输出标注 `precision_level` 与 `precision_tag`。
- 输出：`DailyPlan`（"今天该做什么"可执行日课），按 slot 组织。
- **诚实边界**：研究性 / 探索性；非医疗处方、非诊断结论；补剂仅为一般营养提示，非用药建议。

## 6. 基因深度解析（WGS / PRS）——合规 gate 前置

- 实现：`app/core/prs_framework.py::PRSGenomicsFramework`。
- **合规架构设计是前置 gate**：基因 / 化验数据接入前，先做医疗器械分类评估 + 基因数据合规路径评估。
- gate 未过（默认）：`assess_prs` / `annotate_wgs` 返回 `gate_pending`，**不处理数据**。
- 激活开关：环境变量 `HEALTHLENS_GENOMICS_GATE`（默认关闭）。
- **诚实边界**：PRS 是**群体相对风险评分，非个体诊断**；AUC 0.6–0.7（低–中等区分度）；
  不能用于个体诊断或筛查决策；风险 ≠ 诊断。

## 7. 产品形态约束（Chief 2026-11-04 补充）

- **抽屉组合**：模块化信息输入，每个信息模块可独立接入 / 缺失，非"要么全给要么不能用"。
- **非高净值专属**：目标客群是大众（高净值只是高端档，不是唯一）。
- 以上已纳入边界层 / 非药物引擎 / PRS 框架的架构理解（`determine_precision` 三档即此设计落地）。

## 8. 合规前置说明（依赖合规专家）

- 本次工程侧**已完成不依赖合规评估的部分**：边界层架构、诊断措辞重构、药物隔离声明、
  非药物方案引擎框架、基因 WGS/PRS 框架接口（gate 前置，默认不接数据）。
- **基因数据实际接入 / 化验数据接入 / 医疗器械分类**：等合规架构设计（合规专家负责）评估后启动，
  属后续工作，**不在本次交付范围**。

## 9. 真实数据验证第一优先（依赖合规评估）

- **定位优先项**：**真实人群数据验证是项目第一优先战略目标**（非合成数据扩展）。
  - 当前全部验证为 **in-silico 合成数据**（200 合成画像 / 300 对抗 / 2500 多 seed），
    论文自认"真实数据验证是 limitation"——**不因合成数据全绿而宣称已验证真实能力**。
  - 真实数据接入路径：**医疗器械分类评估 + 基因数据合规路径评估**（合规专家负责）是前置 gate，
    gate 未过不接数据（与 §6/§8 一致）。
- **接入后验证目标**：
  - 八轴稳态框架 / 融合引擎在**真实人群**上的外部有效性检验（跨受试者泛化，非仅合成自洽）。
  - 非药物方案引擎 / PRS 框架在真实数据上的**泛化衰减诚实报告**（低于 chance 如实报告，
    不美化、不宣称"已验证"）。
- **接入前姿态**：本平台定位为"研究性 / 探索性"健康评估工具，所有"真实数据验证"能力
  以**真实数据接入 + 合规评估通过**为前提，**未达成前不宣称**。

## 10. 不宣称清单（诚实边界）

| 能力 | 状态 |
| --- | --- |
| "已验证诊断" | ✗ 不宣称（诊断为独立门控，默认不激活） |
| "已验证抗衰 / 抗衰老" | ✗ 不宣称（研究性 / 探索性） |
| "PRS 可个体诊断" | ✗ 不宣称（群体相对风险，AUC 0.6–0.7） |
| "非药物方案可治疗疾病" | ✗ 不宣称（健康管理建议，非医疗处方） |
| "专家 Delphi 内容效度" | ✗ 尚未完成（L-CVI 为构造级文献收敛代理，非专家判断） |

## 11. 相关文件

- `app/core/diagnosis_gate.py`（新增）— 解释↔诊断边界层
- `app/core/non_pharma_engine.py`（新增）— 非药物个性化方案引擎
- `app/core/prs_framework.py`（新增）— 基因 WGS/PRS 框架接口
- `app/core/diagnosis_engine.py`（改）— 西医健康评估引擎（评估语义）
- `app/services/diagnosis_service.py`、`app/api/diagnosis.py`、`app/api/v1/diagnosis_agent.py`、
  `app/services/diagnosis_agent.py`（改）— 措辞重构
- `app/api/medications.py`（改）— 药物隔离声明
- `app/middleware/emergency_interceptor.py`、`app/__init__.py`、`app/api/frequency.py`、
  `app/services/notification_service.py`（改）— 相关措辞同步
- `tests/core/test_diagnosis_gate.py`、`tests/core/test_non_pharma_engine.py`、
  `tests/core/test_prs_framework.py`（新增）+ 相关测试更新（`test_diagnosis_engine.py`、
  `test_diagnosis.py`、`test_notification_service.py`）
