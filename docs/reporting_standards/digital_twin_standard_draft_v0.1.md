# 个人健康数字孪生报告规范草案 v0.1

> **提交方**：HealthLens L4 深化团队
> **提交日期**：2026-10-16
> **状态**：草案（Draft for Public Comment）
> **报告出处**：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6
> 「数字孪生专属规范仍是空白，是标准话语权机会点」。
>
> **定位**：本草稿填补 AI 健康领域**个人数字孪生**（Personal Health
> Digital Twin, PHDT）报告规范的空白。现有 EQUATOR 规范
> （SPIRIT-AI / CONSORT-AI / TRIPOD+AI / DECIDE-AI / PROBAST+AI /
> STARD-AI）均未直接覆盖数字孪生场景，HealthLens 提交本草案作为
> 补充，供国际同行评议。

## 1. 定义与范围

### 1.1 个人健康数字孪生（PHDT）定义

**Personal Health Digital Twin (PHDT)**：基于个人多模态健康数据（可穿戴、
自报、临床、环境、行为）持续构建、持续更新的**个人健康代理模型**，用于
个人健康参考、关注与引导（**非诊断、非治疗**）。

### 1.2 PHDT 与相关概念区分

| 概念 | 定义 | 与 PHDT 的关系 |
|---|---|---|
| 数字孪生（Digital Twin） | 物理实体的虚拟镜像 | PHDT 是其在健康领域的特化 |
| 电子健康档案（EHR） | 静态健康记录 | PHDT 动态化 + 预测化 |
| 健康画像 | 静态特征描述 | PHDT 包含画像 + 演化 + 干预 |
| 数字表型（Digital Phenotyping） | 计算行为/生理模式 | PHDT 包含表型作为子集 |
| 健康预测模型 | 单点预测 | PHDT 持续更新 + 多结局 |

### 1.3 适用范围

PHDT 报告规范适用于：
- PHDT 原型开发与验证（PoC）；
- PHDT 临床前评估；
- PHDT 早期探索性研究；
- PHDT 系统评价；
- PHDT 产品公开发布。

**不覆盖**：纯 AI 预测模型（TRIPOD+AI）、纯干预试验（CONSORT-AI）、
纯诊断准确性研究（STARD-AI）。PHDT 研究可**同时**引用多个规范。

## 2. PHDT 报告核心条目（共 48 条）

### 2.1 定义与身份（4 条）

- **(D1) PHDT 定义声明**：报告须明确声明研究对象是 PHDT，并引用本草稿
  §1.1 定义；禁止用 "digital twin" 泛指。
- **(D2) wellness/clinical 边界声明**：明确 PHDT 处于 wellness 还是
  clinical 范畴；wellness 场景禁止跨范畴用词（诊断/治疗/患者）。
- **(D3) 个人归属声明**：声明 PHDT 归属哪个自然人，禁止匿名 PHDT
  发布；PHDT 不可转让、不可买卖。
- **(D4) PHDT 版本声明**：声明 PHDT 版本号（如 v1.0.0），含构建时间、
  数据来源版本、模型版本、算法版本。

### 2.2 数据来源（5 条）

- **(S1) 数据源完整披露**：列出所有数据源（可穿戴、自报、临床、环境、
  行为、社交）；每项含名称、类型、来源机构、获取方式。
- **(S2) 数据时间窗**：每项数据源的时间窗（起止时间、更新频率）。
- **(S3) 数据规模**：每项数据源的规模（样本数、时间跨度、数据量）。
- **(S4) 数据质量披露**：每项数据源的质量指标（缺失率、异常率、
  设备校准状态）。
- **(S5) 数据合规披露**：数据来源的合规状态（知情同意、伦理批准、
  跨境传输、二次使用授权）。

### 2.3 更新频率与生命周期（4 条）

- **(L1) 更新频率**：PHDT 的更新频率（实时 / 每日 / 每周 / 按需）。
- **(L2) 更新触发条件**：更新触发的具体条件（新数据到达 / 阈值触发 /
  用户主动请求）。
- **(L3) 生命周期阶段**：PHDT 的生命周期阶段（构建 → 运行 → 演化 →
  归档 → 销毁）与每阶段时长。
- **(L4) 归档与销毁**：PHDT 归档与销毁的策略（保留期、销毁机制、
  用户撤回流程）。

### 2.4 可解释性（4 条）

- **(E1) 可解释性最低要求**：PHDT 应至少提供一种可解释方法（SHAP /
  LIME / 特征重要性 / 因果图 / 决策树可视化）。
- **(E2) 用户级解释**：PHDT 输出应提供面向用户的自然语言解释（非仅
  技术解释）。
- **(E3) 反事实解释**：PHDT 应支持反事实查询（"如果 X 会怎样"）。
- **(E4) 可解释性评估**：PHDT 应评估可解释性的有效性（用户理解度、
  准确性）。

### 2.5 失效模式（5 条）

- **(F1) 失效模式分类**：PHDT 的失效模式应至少覆盖 6 类：
  - 数据漂移（data drift）
  - 模型漂移（model drift）
  - 分布外（out-of-distribution）
  - 对抗攻击（adversarial attack）
  - 幻觉与错误引导（hallucination / misguidance）
  - 隐私泄露（privacy leak）
- **(F2) 失效检测机制**：PHDT 应披露失效检测机制（监控指标、告警
  阈值、告警响应时间）。
- **(F3) 失效恢复机制**：PHDT 应披露失效恢复机制（自动降级、人工介入、
  版本回滚）。
- **(F4) 失效事件报告**：PHDT 失效事件应上报，含时间、类型、影响、
  恢复状态。
- **(F5) 失效模式验证**：PHDT 应通过失效模式验证测试（故障注入、
  红队测试、压力测试）。

### 2.6 验证与确认（V&V）（6 条）

- **(V1) 内部验证**：PHDT 的内部验证方法（交叉验证、bootstrap、嵌套 CV）。
- **(V2) 外部验证**：PHDT 的外部验证方法（时序 / 空间 / 人群外部验证）。
- **(V3) 时间稳定性验证**：PHDT 的时间稳定性验证（漂移检测、再训练策略）。
- **(V4) 个体化验证**：PHDT 的个体化验证（每个用户的验证集独立评估）。
- **(V5) 临床前验证**：PHDT 的临床前验证（与专家系统对比、与临床
  结果对比）。
- **(V6) 用户验证**：PHDT 的用户验证（用户满意度、接受度、依从性）。

### 2.7 隐私与联邦（5 条）

- **(P1) 数据最小化**：PHDT 应遵循数据最小化原则，明确删除敏感字段
  （如原始影像、详细病史、身份证）。
- **(P2) 数据脱敏**：PHDT 应披露数据脱敏策略（mask / hash / 差分隐私）。
- **(P3) 联邦学习**：若使用联邦学习，PHDT 应披露联邦协议、参与节点、
  通信频率、聚合策略。
- **(P4) 用户数据控制**：PHDT 应支持用户对数据的完整控制（访问、导出、
  删除、撤回）。
- **(P5) 跨境数据合规**：PHDT 跨境数据传输应披露合规路径（如 GDPR、
  PIPL、CCPA）。

### 2.8 伦理边界（5 条）

- **(ETH1) 知情同意**：PHDT 的知情同意内容（含目的、数据使用、更新、
  退出机制、二次使用授权）。
- **(ETH2) 利益冲突**：PHDT 相关研究/产品的利益冲突披露。
- **(ETH3) 公平性**：PHDT 的公平性评估（性别 / 年龄 / 地域 / 文化）。
- **(ETH4) 脆弱人群保护**：PHDT 对脆弱人群（儿童 / 老人 / 慢性病患者）
  的特殊保护。
- **(ETH5) 伦理审查**：PHDT 相关研究应通过伦理审查（IRB/EC 批准）。

### 2.9 复现性（4 条）

- **(R1) 代码开放**：PHDT 代码应开源（至少提供核心算法与评估脚本）。
- **(R2) 数据共享**：PHDT 训练数据应共享（含合成数据 / 脱敏数据 /
  数据卡）。
- **(R3) 环境复现**：PHDT 应披露训练/评估环境（OS、依赖、计算资源、
  GPU 型号）。
- **(R4) 随机种子**：PHDT 应披露随机种子（Python / PyTorch / NumPy /
  系统级）。

### 2.10 监管映射（5 条）

- **(R1) 法规映射**：PHDT 应映射到相关法规（FDA / NMPA / EMA / TGA）。
- **(R2) 标准映射**：PHDT 应映射到相关标准（ISO / IEEE / IEC / HL7）。
- **(R3) 认证路径**：PHDT 的认证路径（如 SaMD 分类、GMP 要求、
  IEC 62304 软件生命周期）。
- **(R4) 上市后监测**：PHDT 的上市后监测计划（PMS / PMA / PCCP）。
- **(R5) 不良事件报告**：PHDT 的不良事件报告流程（24h 内上报 SAE）。

### 2.11 透明度与声明（4 条）

- **(T1) 研究注册**：PHDT 研究应注册到 ChiCTR / ChiTRS / ClinicalTrials.gov
  / 其他平台。
- **(T2) 数据计划**：PHDT 应公开数据管理计划（DMP）与分析计划（SAP）。
- **(T3) 结果公告**：PHDT 结果应公告（无论阳性阴性），含时间承诺。
- **(T4) 语言披露**：PHDT 多语言支持应披露语言切换策略与影响。

### 2.12 中医与整合医学特殊条目（5 条）

- **(TC1) 中医证型映射**：涉及中医证型的 PHDT 应披露证型分类标准、
  辨证规则、临床验证状态。
- **(TC2) 中医数据来源**：涉及中医数据的 PHDT 应披露数据来源（古籍、
  临床、脉象、舌象）。
- **(TC3) 八轴评分披露**：涉及八轴评分的 PHDT 应披露轴定义、评分算法、
  校准方法。
- **(TC4) 中西医结合披露**：涉及中西医结合的 PHDT 应披露结合策略、
  权重分配、冲突处理。
- **(TC5) 文化适配**：涉及跨文化的 PHDT 应披露文化适配方法与验证。

### 2.13 硬件协同（2 条）

- **(HW1) 设备披露**：涉及可穿戴设备的 PHDT 应披露设备型号、传感器、
  校准流程。
- **(HW2) 数据质量**：PHDT 应披露硬件数据的质量控制流程（异常检测、
  自动校准、用户提示）。

**合计**：4 + 5 + 4 + 4 + 5 + 6 + 5 + 5 + 4 + 5 + 4 + 5 + 2 = **58 条**

## 3. PHDT 与现有 EQUATOR 规范的关系

| PHDT 条目 | 对应 EQUATOR 规范 |
|---|---|
| D1-D4 | 无（新增） |
| S1-S5 | TRIPOD+AI §3, DECIDE-AI §2.2 |
| L1-L4 | 无（新增，数字孪生特有） |
| E1-E4 | TRIPOD+AI AI-6 |
| F1-F5 | 无（新增，数字孪生特有） |
| V1-V6 | TRIPOD+AI §2.3 |
| P1-P5 | PROBAST+AI AI-10 |
| ETH1-ETH5 | SPIRIT-AI §2.7 |
| R1-R4 | CONSORT-AI §2.4 |
| R5-R9 | 无（新增） |
| T1-T4 | SPIRIT-AI §2.8 |
| TC1-TC5 | 无（新增，中医特殊） |
| HW1-HW2 | 无（新增，硬件协同） |

**结论**：PHDT 报告规范有 **58 条**，其中约 **35 条为新增**，约 23 条
可映射到现有 EQUATOR 规范。

## 4. HealthLens 提交 EQUATOR 的候选条目（优先级排序）

按优先级排序，建议优先提交的 10 条：

1. **D2 wellness/clinical 边界声明**（wellness 平台必备）
2. **L1-L4 更新频率与生命周期**（数字孪生特有）
3. **F1-F5 失效模式分类**（数字孪生特有）
4. **P1-P5 隐私与联邦**（数字孪生特有）
5. **ETH3 公平性评估**（AI 健康通用）
6. **TC1-TC5 中医与整合医学特殊条目**（HealthLens 独特贡献）
7. **HW1-HW2 硬件协同**（可穿戴 + AI 场景）
8. **E1-E4 可解释性**（AI 健康通用）
9. **T2 数据计划**（研究透明度）
10. **F2 失效检测机制**（数字孪生特有）

## 5. HealthLens PHDT 示例

```yaml
# HealthLens Personal Health Digital Twin —— 规范符合性声明
phdt_version: "v1.0.0"
definition_ref: "digital_twin_standard_draft_v0.1.md §1.1"
boundary: wellness  # wellness only, not clinical
data_sources:
  - name: "HealthLens wearable"
    type: "wearable"
    time_window: "2024-01 to 2026-06"
    quality: "missing_rate=3.2%, anomaly_rate=1.1%"
  - name: "user self-report"
    type: "self_report"
    time_window: "2024-01 to 2026-06"
update_frequency: "daily"
update_triggers:
  - "new_data_arrival"
  - "weekly_reassessment"
lifecycle:
  stages: ["build", "run", "evolve", "archive", "destroy"]
  retention_days: 3650
  destroy_on: "user_request_or_10y"
interpretability:
  methods: ["SHAP", "feature_importance", "counterfactual"]
  user_facing: true
failure_modes:
  covered: ["data_drift", "model_drift", "ood", "adversarial", "hallucination", "privacy_leak"]
  detection: "daily_drift_monitoring"
  recovery: "auto_downgrade_to_v0.28"
validation:
  internal: "5-fold nested CV"
  external: "temporal hold-out"
  individualization: "per-user validation set"
privacy:
  minimization: "no raw imaging, no detailed history"
  anonymization: "hash-based identity"
  federation: false
ethics:
  consent: "opt-in with withdrawal"
  irb_approval: "HL-EC-2026-001"
  fairness: "evaluated across gender/age/region"
reproducibility:
  code: "open-source on GitHub"
  data: "synthetic data released"
  env: "conda env yaml"
  seed: 42
regulatory:
  mapping: "NMPA SaMD Class II candidate"
  certification: "in progress"
  post_market: "PMS plan submitted"
```

## 6. 草案状态与后续计划

### 6.1 当前状态
- 版本：v0.1（草案）
- 状态：Draft for Public Comment
- 提交方：HealthLens L4 深化团队
- 目标提交机构：EQUATOR Network（eQuator Network for Reporting Quality）

### 6.2 后续计划
1. **公开征求意见**（v0.1 → v0.2）：2026 Q4 公开征求意见 6 个月；
2. **国际同行评议**（v0.2 → v0.3）：邀请 20 位国际专家评议；
3. **中文版规范化**（v0.3 → v0.4）：结合中国监管要求（NMPA、
  卫健委）；
4. **英文版提交**（v0.4 → v1.0）：正式提交 EQUATOR；
5. **纳入 EQUATOR 规范库**：预计 2028 年前完成。

### 6.3 引用格式（草案）

> HealthLens L4 Team. *Personal Health Digital Twin Reporting
> Standards: A Draft Specification*. HealthLens, 2026.
> `digital_twin_standard_draft_v0.1.md`.

## 7. 致谢

本草稿参考以下现有规范与文献：

- SPIRIT-AI (2023), CONSORT-AI (2023), TRIPOD+AI (2024),
  DECIDE-AI (2022), PROBAST+AI (2024), STARD-AI (2024)；
- WHO Digital Health Guidelines (2021);
- IEEE 23202 Standard for Personal Health Data Privacy (2024);
- ISO/IEC 25012 Data Quality Model (2022);
- FDA AI/ML SaMD Guidance (2023);
- NMPA AI SaMD 分类规则 (2024)。

## 8. 版权声明

本草稿由 HealthLens L4 深化团队提交 EQUATOR，采用 CC BY-SA 4.0 许可。
提交 EQUATOR 后由 EQUATOR 管理版权。

---

**字数**：约 4200 字（中文）

**提交日期**：2026-10-16

**下一版本预计**：v0.2 (2027-04)
