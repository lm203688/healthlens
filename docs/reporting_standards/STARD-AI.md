# STARD-AI —— AI 诊断准确性研究报告规范

> 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白」标准话语权机会点。
>
> 依据：Mann RM, et al. STARD-AI (2024 版)。
> HealthLens 提交至 EQUATOR 的候选补充条目在 §8。

## 1. 适用范围

AI **诊断准确性**研究——包括：
- AI 影像诊断研究；
- AI 实验室检测辅助诊断；
- AI 症状分析辅助诊断；
- AI 多模态融合诊断。

**边界**：STARD-AI 仅覆盖诊断准确性研究，不覆盖预测模型开发
（TRIPOD+AI）或干预试验（CONSORT-AI）。

## 2. 核心条目（34 项）

### 2.1 研究设计
- (a) 研究设计类型（横断面 / 时序 / 队列）；
- (b) 研究设置（临床 / 真实世界）；
- (c) 参与来源；
- (d) 参与流程（含偏倚防控）。

### 2.2 参与者
- (a) 纳入标准；
- (b) 排除标准；
- (c) 样本量估算；
- (d) 参与特征（含疾病谱分布）。

### 2.3 索引试验（AI 模型）
- (a) 模型描述（含版本）；
- (b) 输入数据描述；
- (c) 输出描述（概率 / 分类 / 分段）；
- (d) 阈值选择与依据；
- (e) 模型部署环境；
- (f) 模型更新与回滚。

### 2.4 参考标准（Reference Standard）
- (a) 参考标准定义；
- (b) 参考标准评估者盲法；
- (c) 参考标准评估流程；
- (d) 参考标准与索引试验的独立性。

### 2.5 结局
- (a) 主要结局（诊断准确性指标）；
- (b) 次要结局；
- (c) 敏感性/特异性；
- (d) ROC 曲线与 AUC；
- (e) 校准（含校准曲线）；
- (f) 决策曲线分析。

### 2.6 数据与分析
- (a) 数据来源；
- (b) 数据质量控制；
- (c) 分析方法（含模型验证）；
- (d) 缺失数据处理；
- (e) 亚组分析。

### 2.7 伦理与透明度
- (a) IRB/EC 批准；
- (b) 知情同意；
- (c) 结果公告计划；
- (d) 数据共享。

## 3. STARD-AI 与 STARD 的区别

STARD 是传统诊断准确性研究规范；STARD-AI 在 STARD 基础上增加 AI 特有
条目：

- 模型描述（含版本）；
- 阈值选择与依据；
- 模型部署环境；
- 模型更新与回滚；
- 模型漂移监测；
- 模型可解释性。

## 4. HealthLens 适配说明

HealthLens 作为 wellness 平台，**不进行临床诊断准确性研究**。STARD-AI
用于：

- **健康风险筛查 PoC**（非诊断）：探索性评估 HealthLens 健康风险
  筛查能力的可行性；
- **中医证型辅助评估**（非诊断）：探索中医证型辅助评估的可行性；
- **系统评价**：评估现有 AI 诊断准确性研究质量。

**HealthLens 的 STARD-AI 关键约束**：

- HealthLens 不得作为诊断工具发布 STARD-AI 论文；
- HealthLens 相关 STARD-AI 论文须明确标注 "not for diagnosis"；
- HealthLens 相关 STARD-AI 论文主要结局须为 "screening performance"
  而非 "diagnostic accuracy"。

## 5. HealthLens 示例片段

```yaml
# HealthLens 健康风险筛查 PoC —— STARD-AI 关键条目
study_title: "AI-based wellness risk screening (not for diagnosis)"
not_for_diagnosis: true
study_type: cross_sectional
population:
  n: 500
  setting: real-world
  spectrum: wellness population only
ai_model:
  family: SenseNova 6.8 + 自研评分器
  version: v0.29.0
  threshold: 0.5 (exploratory)
  threshold_rationale: "maximizing F1 on internal validation"
reference_standard:
  definition: clinician_assessment_wellness_only
  blinded: true
  independence: independent evaluation
primary_outcome:
  metric: screening_sensitivity_specificity
  a_uc: 0.72
  calibration: "Hosmer-Lemeshow p=0.38"
  dca: "net_benefit 0.4-0.7 at threshold 0.5"
generalizability:
  population: zh-CN wellness
  limitations: "not for diagnosis; cross-cultural limitations"
```

## 6. HealthLens 提交 EQUATOR 的候选补充条目

- (新增 1) **wellness 筛查声明**：AI wellness 筛查研究须在标题、摘要、
  讨论中明确标注 "not for diagnosis"；
- (新增 2) **筛查与诊断区分**：区分 screening（筛查）与 diagnosis
  （诊断）的术语与用途；
- (新增 3) **中医证型辅助评估特殊披露**：涉及中医证型辅助评估的研究
  需披露证型分类标准与临床验证状态；
- (新增 4) **多模态融合披露**：涉及多模态融合的 AI 研究需披露各模态
  贡献度与融合策略；
- (新增 5) **健康数据最小化**：涉及健康数据的 AI 研究需声明数据
  最小化策略；
- (新增 6) **个人数字孪生筛查特殊披露**：涉及个人数字孪生的 AI 筛查
  研究需披露数据源、更新频率、隐私保护。

## 7. 常见报告偏差

| 偏差 | 说明 | 防控 |
|---|---|---|
| 部分验证 | 只在部分人群验证 | 完整人群验证 |
| 阈值缺失 | 未报告阈值选择 | 强制报告阈值与依据 |
| 参考标准盲法缺失 | 参考标准评估者非盲 | 强制盲法 |
| 校准缺失 | 只报告 AUC 不报告校准 | 强制校准曲线 |
| 推广性夸大 | 小样本推广到全球 | 明确人群限制 |
