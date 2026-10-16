# SPIRIT-AI —— AI 干预试验方案报告规范

> 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白」标准话语权机会点。
>
> 依据：Chan AMC, Sriraman N, et al. SPIRIT-AI 2023 版核心条目。
> HealthLens 提交至 EQUATOR 的候选补充条目在 §8。

## 1. 适用范围

AI 驱动的健康干预研究试验方案（protocol paper）——包括但不限于：
- LLM/ML 模型作为干预主体（推荐、引导、教育）；
- AI 辅助的数字化疗法（digital therapeutics）；
- 智能硬件 + AI 算法组合干预；
- 人机混合干预（AI + 真人）。

**HealthLens 边界**：本规范不覆盖诊断、治疗、处方类试验；HealthLens
作为 wellness 平台，仅用于方案模板中「干预」= 健康引导/参考/关注场景。

## 2. 核心条目（2023 版）

### 2.1 试验设计
- (a) 试验设计（RCT/集群随机/整群随机/交叉/非随机）与随机化单元；
- (b) 分配比的公开或保密（含分配隐藏机制）；
- (c) 分配序列生成方法（如 permuted block）。

### 2.2 AI 模型披露
- (a) 模型类型（LLM/传统 ML/深度学习/混合）；
- (b) 训练数据（来源、规模、时间窗、语言、人群）；
- (c) 训练/验证/测试划分；
- (d) 目标函数与损失函数；
- (e) 关键超参数与优化器；
- (f) 部署环境（云端/边缘/端侧）；
- (g) 模型版本控制与回滚策略。

### 2.3 干预与对照
- (a) 干预内容与剂量（每日交互次数、时长）；
- (b) 对照类型（空白对照/安慰剂对照/标准护理）；
- (c) 干预依从性测量方式；
- (d) 交叉污染防控。

### 2.4 结局指标
- (a) 主要结局（时间窗、测量工具）；
- (b) 次要结局；
- (c) AI 特有结局（用户满意度、模型响应质量、安全性事件）；
- (d) 中间结局与替代终点。

### 2.5 样本量与统计
- (a) 样本量估算方法（含 AI 响应不确定性调整）；
- (b) 主要分析模型（意向治疗 / as-treated / per-protocol）；
- (c) 缺失数据处理策略；
- (d) 亚组分析计划。

### 2.6 数据治理
- (a) 数据收集工具与质量控制；
- (b) 数据存储与访问控制；
- (c) 数据最小化原则；
- (d) 二次使用授权；
- (e) 跨境数据流动（如适用）。

### 2.7 伦理与安全
- (a) IRB/EC 批准编号；
- (b) 知情同意内容与撤回机制；
- (c) 数据安全事件响应；
- (d) AI 特有安全：幻觉、错误引导、偏见、隐私；
- (e) 不良事件（adverse events）与预期不良事件（SUsAR）报告。

### 2.8 透明度
- (a) 方案注册号（如 ChiCTR、ChiTRS、ClinicalTrials.gov）；
- (b) 数据分析计划（SAP）公开；
- (c) 结果公告计划（无论阳性阴性）；
- (d) 数据共享计划。

## 3. HealthLens 适配说明

HealthLens 作为 wellness 平台，其 SPIRIT-AI 适配需注意：

- **干预定义**：HealthLens 干预 = wellness 引导/参考/关注，不产生临床干预；
- **对照设计**：对照组可设为「健康信息标准护理」或「无干预」；
- **AI 模型披露**：HealthLens 使用 SenseNova 系列 LLM，需披露模型版本、
  上下文长度、温度参数、guardrail 配置；
- **结局指标**：主要结局为 wellness 指标（如睡眠规律性、饮食均衡度、
  八轴评分变化），非临床指标；
- **安全性**：HealthLens 的「不良事件」定义为错误引导、合规越界、
  隐私泄露三类；不覆盖药物不良反应。

## 4. 参考条目速查表

| 条目类别 | 建议最少 15 项 |
|---|---|
| 试验设计 | 3 |
| AI 模型披露 | 7 |
| 干预与对照 | 4 |
| 结局指标 | 4 |
| 样本量与统计 | 4 |
| 数据治理 | 5 |
| 伦理与安全 | 5 |
| 透明度 | 4 |

## 5. 与 CONSORT-AI 的关系

SPIRIT-AI 是**方案**报告规范；CONSORT-AI 是**结果**报告规范。二者配套使用：
方案注册后应引用 SPIRIT-AI 条目编号；结果发表时按 CONSORT-AI 编号对应回复。

## 6. 与 TRIPOD+AI 的关系

TRIPOD+AI 覆盖**预测模型**开发报告；若 SPIRIT-AI 试验中 AI 干预依赖
自训预测模型，需在方案中同时披露 TRIPOD+AI 相关条目（模型开发、验证、
外部验证、模型性能）。

## 7. HealthLens 示例片段

```yaml
# HealthLens wellness 引导试验方案 —— SPIRIT-AI 关键条目
intervention:
  type: wellness_guidance_only  # 非临床干预
  modality: LLM-chat + wearable
  ai_model:
    family: SenseNova 6.8
    context_window: 128k
    temperature: 0.3
    guardrails: claims_engine v0.29
outcome_primary:
  metric: eight_axis_score_delta  # 八轴评分变化
  timepoint: 12 weeks
safety:
  event_classes:
    - misguidance
    - compliance_boundary_violation
    - privacy_leak
  reporting: SAE within 24h
```

## 8. HealthLens 提交 EQUATOR 的候选补充条目

（草案，待国际同行评议）

- (新增 1) **wellness/clinical 边界声明**：AI 干预试验方案须明确干预处于
  wellness 还是 clinical 范畴，禁止跨范畴用词；
- (新增 2) **wellness 结局指标注册**：主要 wellness 结局应在试验前注册
  到 wellness outcome registry（如 OMR 联盟）；
- (新增 3) **多语言干预披露**：中英双语干预需在方案中披露语言切换策略；
- (新增 4) **文化适配声明**：跨文化人群试验需披露文化适配方法与验证；
- (新增 5) **硬件协同声明**：涉及可穿戴设备的试验需披露设备校准流程。
