# CONSORT-AI —— AI 干预试验报告规范

> 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白」标准话语权机会点。
>
> 依据：Krishnamoorthy V, Kuziemsky C, et al. CONSORT-AI (2023 版)。
> HealthLens 提交至 EQUATOR 的候选补充条目在 §8。

## 1. 适用范围

AI 驱动的健康干预研究**试验结果**论文报告。与 SPIRIT-AI 配套使用：
SPIRIT-AI 覆盖方案，CONSORT-AI 覆盖结果。

## 2. 核心条目（31 项主条目）

### 2.1 标题与摘要
- (a) 标题标注 AI 性质（"AI-powered", "LLM-assisted", "algorithmic"）；
- (b) 结构化摘要（背景/方法/结果/结论）。

### 2.2 方法
- (a) 试验设计（含 CONSORT 流程图）；
- (b) 设置与参与来源；
- (c) 纳入/排除标准；
- (d) AI 模型描述（与 SPIRIT-AI 2.2 呼应）；
- (e) 干预描述（内容与剂量）；
- (f) 对照描述；
- (g) 结局指标（含时间窗）；
- (h) 样本量；
- (i) 数据来源、管理、分析；
- (j) 偏差控制（含 AI 模型偏差）；
- (k) 伦理。

### 2.3 结果
- (a) 时间框架；
- (b) 参与流（CONSORT 流程图）；
- (c) 参与特征；
- (d) 干预实际实施；
- (e) AI 模型实际性能（含漂移监测）；
- (f) 结局（含效应量与 CI）；
- (g) 不良事件。

### 2.4 讨论
- (a) 关键发现（含与假设的一致性）；
- (b) AI 模型局限性；
- (c) 推广性（含跨人群/跨部署环境）；
- (d) 与相关研究对比；
- (e) 数据共享（含代码与模型权重）；
- (f) 声明与利益冲突；
- (g) 作者贡献；
- (h) 保证。

### 2.5 AI 特有补充条目
- (a) 模型版本与训练数据版本；
- (b) 部署环境变化披露；
- (c) 人-AI 交互日志摘要；
- (d) 模型响应质量指标（用户满意度、幻觉率）；
- (e) 模型偏见评估结果；
- (f) 模型安全事件（adverse AI events）。

## 3. CONSORT 流程图标准

试验结果论文必须包含 CONSORT 流程图，标注：
1. 招募人数；
2. 分配人数；
3. 每组实际接受干预人数；
4. AI 模型拒绝响应/无响应事件数；
5. 脱落原因（分组）；
6. 分析人群。

## 4. HealthLens 适配说明

HealthLens 作为 wellness 平台，其 CONSORT-AI 结果报告需注意：

- **标题**：应含 "wellness" 关键词，避免 "clinical trial"；
- **结局**：主要结局为 wellness 指标，禁止用临床指标作为主要结局；
- **AI 模型**：HealthLens 使用 SenseNova 系列 LLM + 自研 claims_engine
  guardrail，需在讨论中披露；
- **不良事件**：wellness 场景下的「不良事件」= 错误引导 + 合规越界 +
  隐私泄露三类；不覆盖药物不良反应；
- **推广性**：HealthLens 主要覆盖 zh-CN 人群，跨文化推广性有限，
  需在讨论中诚实披露。

## 5. 参考条目速查表

| 类别 | 条目数 |
|---|---|
| 标题与摘要 | 2 |
| 方法 | 11 |
| 结果 | 7 |
| 讨论 | 8 |
| AI 特有补充 | 6 |
| **合计** | **34** |

## 6. 与 SPIRIT-AI 的关系

- SPIRIT-AI：方案（before trial）
- CONSORT-AI：结果（after trial）
- 结果论文应引用方案注册号，并说明是否偏离原方案。

## 7. HealthLens 示例片段

```yaml
# HealthLens wellness 引导试验结果 —— CONSORT-AI 关键条目
title_suffix: "Wellness guidance only, not clinical"
ai_model:
  family: SenseNova 6.8 Flash-Lite
  version: 2026-10-16
  guardrails: claims_engine v0.29
model_deltas:
  - "12 周期间模型未发生重大版本变更"
  - "guardrail 版本从 v0.28 升级到 v0.29（第 4 周）"
adverse_ai_events:
  misguidance: 3  # 3 起错误引导，均在 24h 内上报
  compliance_boundary: 0
  privacy_leak: 0
generalizability:
  population: "zh-CN primary, zh-TW secondary"
  deployment: "cloud-only (SenseNova API)"
  limitations: "跨文化推广性有限；未评估跨部署环境稳定性"
```

## 8. HealthLens 提交 EQUATOR 的候选补充条目

- (新增 1) **wellness vs clinical 结果分离**：结果论文须明确区分 wellness
  指标与临床指标，禁止用临床指标包装 wellness 结果；
- (新增 2) **模型 guardrail 版本披露**：试验期间 guardrail 版本变更需
  在结果中披露并说明对结局的影响；
- (新增 3) **wellness 不良事件分类**：建议采用 HLE-AE 三分类（misguidance /
  compliance_boundary / privacy_leak）作为 wellness 试验不良事件标准分类；
- (新增 4) **用户反馈闭环披露**：涉及用户反馈驱动的模型更新，需披露
  反馈闭环与模型更新的时序关系；
- (新增 5) **多语言结果报告**：中英双语试验结果论文应披露语言切换对
  结局的影响；
- (新增 6) **数据最小化声明**：结果论文需声明数据最小化策略，避免
  发布过多个人健康数据。

## 9. 常见报告偏差

| 偏差 | 说明 | 防控 |
|---|---|---|
| 选择性报告 | 只报告阳性结果 | 注册后所有预设结局必报 |
| AI 模型披露缺失 | 未披露训练数据/版本 | SPIRIT-AI 2.2 强制 |
| 推广性夸大 | 小样本推广到全球 | 明确人群/环境限制 |
| 不良事件漏报 | 未报 AI 特有不良事件 | HLE-AE 三分类 |
