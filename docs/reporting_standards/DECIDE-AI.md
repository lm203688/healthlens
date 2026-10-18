# DECIDE-AI —— 早期临床 AI 评估报告规范

> 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白」标准话语权机会点。
>
> 依据：Krishnamoorthy V, Kuziemsky C, et al. DECIDE-AI (2022 版)。
> HealthLens 提交至 EQUATOR 的候选补充条目在 §8。

## 1. 适用范围

AI 技术在**早期临床评估**阶段（探索性研究、概念验证、前瞻性队列）的报告
——包括：
- 算法探索性研究（algorithmic exploratory study）；
- 数字孪生原型验证；
- 概念验证试验（proof-of-concept trial）；
- 前瞻性队列评估；
- 早期信号发现研究。

**边界**：DECIDE-AI 不覆盖成熟 RCT（CONSORT-AI）或诊断准确性研究
（STARD-AI）。

## 2. 核心条目（31 项）

### 2.1 研究设计
- (a) 研究设计类型（探索性研究 / PoC / 前瞻性队列）；
- (b) 研究设置（临床 / 真实世界 / 混合）；
- (c) 参与来源（人群描述）。

### 2.2 AI 模型披露
- (a) 模型类型与版本；
- (b) 训练数据来源与规模；
- (c) 训练/验证/测试划分；
- (d) 部署环境；
- (e) 模型更新与回滚策略；
- (f) 模型安全与隐私设计。

### 2.3 干预与对照
- (a) 干预描述（若适用）；
- (b) 对照描述；
- (c) 干预依从性；
- (d) 交叉污染防控。

### 2.4 结局
- (a) 主要结局（探索性主要结局需明确标注）；
- (b) 次要结局；
- (c) 中间结局；
- (d) AI 特有结局（安全性、可解释性、公平性）；
- (e) 替代终点声明。

### 2.5 样本与统计
- (a) 样本量估算（含探索性研究的最小样本量依据）；
- (b) 主要分析模型；
- (c) 缺失数据；
- (d) 亚组分析。

### 2.6 数据治理与伦理
- (a) 数据收集与质量控制；
- (b) 数据存储与访问；
- (c) 数据最小化；
- (d) IRB/EC 批准；
- (e) 知情同意；
- (f) 不良事件报告。

### 2.7 透明度
- (a) 注册号（如适用）；
- (b) 数据分析计划；
- (c) 结果公告计划；
- (d) 数据共享；
- (e) 利益冲突。

## 3. DECIDE-AI 与 CONSORT-AI 的区分

| 维度 | DECIDE-AI | CONSORT-AI |
|---|---|---|
| 阶段 | 早期探索 / PoC | 成熟 RCT |
| 主要结局 | 探索性 | 确定性 |
| 样本量 | 通常较小 | 通常较大 |
| 推广性 | 探索性声明 | 明确推广性声明 |
| 注册要求 | 可选 | 强制 |

## 4. HealthLens 适配说明

HealthLens 涉及的 DECIDE-AI 场景：

- **中医证型预测探索研究**：基于症状数据探索中医证型预测可行性；
- **可穿戴 + AI 融合探索**：探索多模态数据融合的健康预测能力；
- **数字孪生原型 PoC**：验证个人数字孪生概念可行性。

HealthLens 的 DECIDE-AI 适配需注意：

- **主要结局**：探索性研究的主要结局需明确标注 "exploratory"；
- **样本量**：健康数据量通常较大，但人群代表性有限；
- **推广性**：HealthLens 主要覆盖 zh-CN 人群，跨文化推广性有限；
- **伦理**：wellness 场景下的伦理边界需明确声明。

## 5. HealthLens 示例片段

```yaml
# HealthLens 数字孪生原型 PoC —— DECIDE-AI 关键条目
study_type: proof_of_concept
design: prospective_cohort
population:
  n: 200
  source: HealthLens pilot users
  setting: real-world
ai_model:
  family: SenseNova 6.8 + 自研八轴评分器
  version: v0.29.0
  deployment: cloud
primary_outcome:
  type: exploratory
  metric: eight_axis_score_concordance
  timepoint: 12 weeks
generalizability:
  population: zh-CN primary
  limitations: "跨文化推广性有限；样本量较小"
ethics:
  irb_approval: "HL-EC-2026-001"
  consent: "opt-in with withdrawal mechanism"
```

## 6. HealthLens 提交 EQUATOR 的候选补充条目

- (新增 1) **早期 AI 研究声明**：早期探索性研究须在标题与摘要中明确
  标注 "exploratory" 或 "proof-of-concept"；
- (新增 2) **数字孪生 PoC 特殊披露**：涉及个人数字孪生的 PoC 需披露
  数据源、更新频率、失效模式、隐私保护；
- (新增 3) **wellness 探索研究伦理**：wellness 场景下早期研究需明确
  声明 wellness 边界，禁止跨范畴用词；
- (新增 4) **多语言探索研究披露**：中英双语探索研究需披露语言切换
  策略与影响；
- (新增 5) **硬件协同声明**：涉及可穿戴设备的探索研究需披露设备
  校准流程与数据质量；
- (新增 6) **原型迭代披露**：涉及原型迭代的探索研究需披露迭代次数、
  版本变更、回滚机制。

## 7. 常见报告偏差

| 偏差 | 说明 | 防控 |
|---|---|---|
| 过度推广 | 小样本推广到全球 | 明确标注 "exploratory" |
| 注册缺失 | 未注册探索性研究 | 注册到 ChiCTR 或类似平台 |
| 结果夸大 | 探索性结果包装成确定性结果 | 区分 exploratory 与 confirmatory |
| 伦理缺失 | 未说明 wellness 边界 | 强制声明 wellness/clinical 范畴 |
