# TRIPOD+AI —— AI 预测模型开发报告规范

> 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白」标准话语权机会点。
>
> 依据：Collins GS, et al. TRIPOD+AI (2024 版)。
> HealthLens 提交至 EQUATOR 的候选补充条目在 §8。

## 1. 适用范围

AI 预测模型的**开发**研究论文报告——包括：
- 传统 ML（逻辑回归、随机森林、梯度提升）；
- 深度学习（CNN、RNN、Transformer）；
- 大语言模型（LLM）作为预测器；
- 混合模型（ML + LLM + 规则）；
- 因果预测模型（如 DoWhy 集成）。

**边界**：TRIPOD+AI 仅覆盖预测模型开发，不覆盖干预试验（CONSORT-AI）
或诊断试验（STARD-AI）。

## 2. 核心条目（25 项主条目 + AI 补充）

### 2.1 标题与摘要
- (a) 标题标注 "predictive model"；
- (b) 结构化摘要。

### 2.2 引言
- (a) 背景与重要性；
- (b) 目标（明确预测目标与时间窗）。

### 2.3 方法
- (a) 研究设计与设置；
- (b) 数据来源（含获取时间、样本量、时间窗）；
- (c) 变量与预测目标；
- (d) 缺失数据处理；
- (e) 数据质量与清理；
- (f) 样本量与事件数（每变量 EPP = events per predictor）；
- (g) 建模方法（含算法、损失函数、正则化）；
- (h) 特征工程（含 AI 特征选择）；
- (i) 模型训练（含超参搜索）；
- (j) 内部验证（含 bootstrap、交叉验证、嵌套 CV）；
- (k) 外部验证（含时序/空间/人群外部验证）；
- (l) 校准评估；
- (m) 决策曲线分析（DCA）。

### 2.4 结果
- (a) 数据描述（含缺失率、分布）；
- (b) 建模过程（含超参）；
- (c) 模型性能（含 AUC、NRI、IDI）；
- (d) 校准（含校准曲线）；
- (e) DCA 结果；
- (f) 外部验证结果；
- (g) 亚组分析。

### 2.5 讨论
- (a) 关键发现；
- (b) 与现有模型对比；
- (c) 推广性；
- (d) 模型局限；
- (e) 数据共享与代码开放；
- (f) 伦理与潜在滥用；
- (g) AI 特有：可解释性、公平性、鲁棒性。

## 3. AI 特有补充条目（12 项）

- (a1) 模型架构完整描述（含层数、激活函数、Dropout）；
- (a2) 训练数据完整描述（来源、规模、时间、语言、人群）；
- (a3) 训练/验证/测试划分策略；
- (a4) 数据泄漏防控机制；
- (a5) 超参数搜索方法与搜索空间；
- (a6) 优化器与学习率调度；
- (a7) 训练时间与计算资源；
- (a8) 随机种子与可复现性；
- (a9) 模型版本控制；
- (a10) 部署环境描述；
- (a11) 模型漂移监测计划；
- (a12) 模型回滚策略。

## 4. HealthLens 适配说明

HealthLens 涉及的 AI 预测模型场景：

- **八轴评分预测**：基于可穿戴数据 + 用户输入预测未来 4 周八轴评分变化；
- **中医证型预测**：基于症状 + 舌象 + 脉象预测可能倾向的证型；
- **健康风险预测**：基于生活方式数据预测未来 12 周健康风险。

HealthLens 的 TRIPOD+AI 适配需注意：

- **预测目标**：wellness 指标，非临床诊断；
- **训练数据**：主要来自 HealthLens 用户，人群偏 zh-CN，跨文化推广性有限；
- **模型**：混合模型（自研评分器 + LLM 解释器 + 规则引擎）；
- **可解释性**：HealthLens 优先使用可解释的评分器，而非黑盒 LLM；
- **公平性**：需评估八轴评分在不同性别/年龄/地域人群中的公平性。

## 5. HealthLens 示例片段

```yaml
# HealthLens 八轴评分预测模型 —— TRIPOD+AI 关键条目
title: "Predictive model for 12-week eight-axis wellness score change"
target:
  variable: eight_axis_score_delta
  time_horizon: 12 weeks
  outcome_type: continuous
data:
  source: HealthLens wearable + user self-report
  n: 4200
  time_window: "2024-01 to 2026-06"
  population: zh-CN primary, zh-TW secondary
model:
  architecture: hybrid (gradient_boosting + LLM explainer)
  algorithm: LightGBM
  loss: mse
  regularization: lambda=0.1
  hyperparams: num_leaves=63, learning_rate=0.05, n_estimators=500
  seed: 42
validation:
  internal: "5-fold nested CV (bootstrap 200x)"
  external: "temporal hold-out (last 3 months)"
  calibration: Hosmer-Lemeshow p=0.42
performance:
  auc: 0.78
  nri: 0.12
  idd: 0.08
generalizability:
  population: "zh-CN only; zh-TW partial validation"
  limitations: "跨文化推广性有限"
```

## 6. HealthLens 提交 EQUATOR 的候选补充条目

- (新增 1) **wellness 预测模型声明**：预测 wellness 指标而非临床诊断
  的模型，须在标题与讨论中明确标注；
- (新增 2) **健康数据最小化**：训练数据收集应遵循最小化原则，明确
  删除敏感字段（如原始影像、详细病史）；
- (新增 3) **中医证型预测特殊披露**：预测中医证型的模型需披露证型
  分类标准、辨证规则、临床验证状态；
- (新增 4) **多模态融合披露**：融合可穿戴 + 自报 + 中医切诊数据的
  模型需披露各模态贡献度；
- (新增 5) **动态更新披露**：模型持续在线学习的，需披露更新频率、
  数据回灌策略、版本回滚机制；
- (新增 6) **可解释性最小要求**：AI 预测模型应至少提供一种可解释
  方法（SHAP/LIME/特征重要性/因果图）。

## 7. 常见报告偏差

| 偏差 | 说明 | 防控 |
|---|---|---|
| 数据泄漏 | 训练/测试数据重叠 | 时序/空间/人群严格划分 |
| 超参未披露 | 未报告搜索空间与最优解 | 强制披露 (a5) |
| 校准缺失 | 只报告 AUC 不报告校准 | 强制校准曲线 |
| 外部验证缺失 | 只做内部验证 | 强制外部验证 (b) |
| AI 黑盒 | 未提供可解释性 | 强制 (新增 6) |
