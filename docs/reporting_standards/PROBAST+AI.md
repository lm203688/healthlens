# PROBAST+AI —— AI 研究偏倚风险评估工具

> 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白」标准话语权机会点。
>
> 依据：Whippy NS, et al. PROBAST+AI (2024 版)。
> HealthLens 提交至 EQUATOR 的候选补充条目在 §8。

## 1. 适用范围

**AI 相关研究**的偏倚风险评估——包括：
- AI 预测模型开发研究（TRIPOD+AI）；
- AI 诊断准确性研究（STARD-AI）；
- AI 干预试验（SPIRIT-AI / CONSORT-AI）；
- AI 早期探索研究（DECIDE-AI）；
- AI 决策支持系统评价研究。

**用途**：用于系统评价（systematic review）中的研究质量评估。

## 2. 核心条目（4 域 16 项 + AI 补充）

### 2.1 域 1：参与者（Participants）
- (P1) 参与者的纳入/排除是否恰当（与目标人群匹配）；
- (P2) 参与者的代表性（是否覆盖目标人群的关键亚组）；
- (P3) 参与者数据的完整性（缺失率与缺失机制）。

### 2.2 域 2：预测变量（Predictors / Interventions）
- (I1) 预测变量/干预的描述是否充分；
- (I2) 预测变量/干预的测量是否标准化；
- (I3) 预测变量/干预在时间上的可比性（含漂移）；
- (I4) 模型训练/评估的独立性（含数据泄漏防控）。

### 2.3 域 3：结局（Outcome）
- (O1) 结局的定义是否明确；
- (O2) 结局的测量是否标准化；
- (O3) 结局评估者是否盲法；
- (O4) 结局的随访是否完整。

### 2.4 域 4：分析（Analysis）
- (A1) 分析方法是否恰当（含模型选择、验证方法）；
- (A2) 缺失数据处理是否恰当；
- (A3) 是否报告了适当的不确定性（含 CI）；
- (A4) 是否做了外部验证。

### 2.5 AI 特有补充条目
- (AI-1) 训练数据是否充分披露；
- (AI-2) 模型架构是否充分披露；
- (AI-3) 超参搜索空间是否充分披露；
- (AI-4) 是否报告了校准；
- (AI-5) 是否报告了公平性评估；
- (AI-6) 是否报告了可解释性；
- (AI-7) 是否报告了鲁棒性；
- (AI-8) 是否报告了模型漂移监测计划；
- (AI-9) 是否报告了模型回滚策略；
- (AI-10) 是否报告了数据泄漏防控；
- (AI-11) 是否报告了计算资源；
- (AI-12) 是否报告了随机种子与可复现性。

## 3. 偏倚风险评估方法

对每项条目评估：
- **低风险**（low risk of bias）：充分披露且方法恰当；
- **中度风险**（some concerns）：部分披露但方法基本恰当；
- **高风险**（high risk of bias）：披露不足或方法不恰当；
- **无法评估**（no information）：未披露相关信息。

**总体评估**：
- 无高风险 → 总体低风险；
- 有高风险 → 总体高风险（无论其他域如何）；
- 有中度风险但无高风险 → 总体中度风险。

## 4. HealthLens 适配说明

HealthLens 涉及的 PROBAST+AI 评估场景：

- **系统评价**：对 HealthLens 相关文献做系统评价时，使用 PROBAST+AI
  评估每项研究质量；
- **模型选择**：在自研模型选型时，对候选模型评估其训练研究质量；
- **合作研究**：与学术机构合作时，评估其研究质量。

HealthLens 的 PROBAST+AI 适配需注意：

- **训练数据**：HealthLens 训练数据主要来自自有用户，人群代表性有限；
- **模型架构**：HealthLens 使用混合模型，需完整披露各组件；
- **可解释性**：HealthLens 优先使用可解释评分器，可解释性通常较高；
- **公平性**：需评估不同性别/年龄/地域人群中的公平性。

## 5. HealthLens 示例片段

```yaml
# HealthLens 相关研究偏倚风险评估 —— PROBAST+AI
study_title: "Predictive model for eight-axis wellness score"
participants:
  risk: some_concerns
  rationale: "zh-CN primary; zh-TW partial; n=4200"
predictors:
  risk: low
  rationale: "training/testing temporal split; no data leakage"
outcome:
  risk: low
  rationale: "exploratory outcome pre-registered"
analysis:
  risk: low
  rationale: "5-fold nested CV + temporal hold-out + calibration"
ai_specific:
  risk: low
  rationale: "model architecture, hyperparams, seed, resources all disclosed"
overall_risk: low
```

## 6. HealthLens 提交 EQUATOR 的候选补充条目

- (新增 1) **wellness 研究特殊域**：wellness 研究需增加 "wellness 边界
  合规" 域，评估是否跨范畴用词；
- (新增 2) **中医证型研究特殊域**：涉及中医证型的 AI 研究需评估证型
  分类标准披露是否充分；
- (新增 3) **多语言研究特殊域**：中英双语 AI 研究需评估语言切换对
  模型性能的影响披露；
- (新增 4) **可穿戴数据特殊域**：涉及可穿戴数据的 AI 研究需评估数据
  质量与设备校准披露；
- (新增 5) **个人数字孪生特殊域**：涉及个人数字孪生的 AI 研究需评估
  隐私保护与隐私泄露风险评估披露。

## 7. 常见偏倚来源

| 偏倚来源 | 说明 | 防控 |
|---|---|---|
| 数据泄漏 | 训练/测试重叠 | 时序/空间/人群严格划分 |
| 选择偏倚 | 样本非代表性 | 明确披露人群限制 |
| 报告偏倚 | 选择性报告 | 预注册 + 完整报告 |
| 测量偏倚 | 测量不标准化 | 标准化测量工具 |
| 分析偏倚 | 分析方法不恰当 | 强制披露分析方法 |
