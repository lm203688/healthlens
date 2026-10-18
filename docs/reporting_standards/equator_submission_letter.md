# EQUATOR Network 提交信

> **发件方**：HealthLens L4 深化团队 · Digital Twin Working Group
> **收件方**：EQUATOR Network · SPIRIT/CONSORT Workgroup Chairs（占位，正式提交时替换）
> **日期**：2026-10-16
> **主题**：请求纳入 EQUATOR 规范库的补充草案 —— 《Reporting Standard for Causal Digital Twins in Wellness》v0.2
> **状态**：提交信模板，**未实际发送**

---

## 一、收件人（占位）

**主送**：
- SPIRIT/CONSORT Workgroup Co-Chairs, EQUATOR Network
- TRIPOD+AI / PROBAST+AI / DECIDE-AI / STARD-AI 相关工作组协调人

**抄送**：
- EQUATOR Network Editorial Board
- Meta-research Research Network (MRRN)
- WHO Collaborating Centre for Systematic Reviews

**联络邮箱**：（占位，正式提交时填写具体收件人邮箱）

---

## 二、摘要

HealthLens 很高兴向 EQUATOR Network 提交一份补充草案 —— **《Reporting Standard for Causal Digital Twins in Wellness》v0.2**（以下简称 "CDTW v0.2"），共 71 条条目，专为 wellness 场景（面向大众健康管理，非面向临床试验场景）设计。

CDTW v0.2 填补 EQUATOR 现有 6 大 AI 规范（SPIRIT-AI / CONSORT-AI / TRIPOD+AI / DECIDE-AI / PROBAST+AI / STARD-AI）在**个人因果数字孪生（Causal Digital Twin for Wellness, CDTW）** 场景的空白，与 ASME V&V 40-2018 建立条目级映射，并针对 wellness 场景的以下 10 大空白维度提供标准化条目：

1. 数据溯源（Data Provenance, W1）
2. 模型版本治理（Model Version Registry, W2）
3. 幻觉评测指标（Hallucination Evaluation Metrics, W3）
4. 跨租户一致性（Cross-Tenant Consistency, W4）
5. 联邦后验合并协议（Federated Posterior Merge Protocol, W5）
6. 可反驳条件报告（Falsifiable Conditional Reporting, W6）
7. E-value 报告（E-value Reporting, W7）
8. n-of-1 交叉验证（N-of-1 Cross-Validation, W8）
9. GraphRAG 幻觉评测（GraphRAG Hallucination Evaluation, W9）
10. 时序信号序列化协议（Time-Series Signal Serialization Protocol, W10）

CDTW v0.2 采用 CC-BY 4.0 许可，欢迎 EQUATOR Network 审阅、修改、合并。

---

## 三、空白填补依据

本报告规范填补的空白直接来自《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6 的判断：

> "数字孪生专属规范 | ⭐ **仍是空白**"
> "HealthLens 可以提交一份 'Reporting standard for causal digital twins in wellness' 草案。这比发一篇论文更值钱——**立标准的位置只有一次**。"

**判断依据**：

- EQUATOR Network 现有 AI 相关规范 6 份（SPIRIT-AI、CONSORT-AI、TRIPOD+AI、DECIDE-AI、PROBAST+AI、STARD-AI），均聚焦预测/干预/决策准确性等具体研究类型，未提供面向**持续更新、支持反事实查询、个体归属的数字孪生系统**的通用报告框架；
- ASME V&V 40-2018 提供仿真模型 V&V 的通用标准，但未考虑 AI 时代特有的幻觉评测、联邦学习、GraphRAG 等维度；
- 面向临床试验场景的数字孪生规范尚处早期，而 wellness 场景（大众健康管理）的数字孪生报告规范在全球范围内仍是空白；
- HealthLens 作为运营中的 wellness 平台，拥有真实的数字孪生实践（含 claims_engine、GraphRAG 幻觉评测、联邦后验合并协议、Pulse-PPG 零样本评测），可以提炼出可复用的规范条目。

---

## 四、请求事项

### 4.1 请求动作

1. **审阅 CDTW v0.2 草案**：请 EQUATOR Network 相关工作组对 71 条条目进行技术评审；
2. **纳入 EQUATOR 规范库**：请求将 CDTW v0.2 作为 EQUATOR 规范库的补充草案，与 SPIRIT-AI / CONSORT-AI 等并行；
3. **建立与 SPIRIT-AI 的 crosswalk**：请协助建立 CDTW 与 SPIRIT-AI、CONSORT-AI 的官方条目映射表；
4. **建立联合工作组**：建议成立 "Digital Twin Reporting Standards Working Group"，由 HealthLens、EQUATOR、相关学术机构共同参与；
5. **公开征求意见**：请求通过 EQUATOR Network 渠道向全球研究者公开征求意见（建议 6 个月窗口）；
6. **同行评议**：请求协助组织国际同行评议（20 位以上专家）。

### 4.2 建议时间表

| 里程碑 | 建议时间 |
|---|---|
| EQUATOR 初审反馈 | 2026 Q4（3 个月内） |
| 公开征求意见 | 2027 Q1（v0.3） |
| 国际同行评议 | 2027 Q2（v0.4） |
| 中英文定稿 | 2028 H1（v1.0） |
| 纳入 EQUATOR 官方库 | 2028 H2 |

---

## 五、附件清单

本次提交包含以下附件：

### 5.1 核心规范

| 文件 | 说明 |
|---|---|
| `digital_twin_standard_draft_v0.1.md` | v0.1 内部草案（保留作参考，321 行） |
| **`digital_twin_standard_draft_v0.2.md`** | v0.2 提交版（**主文件**，1061 行，71 条条目，含 §0 版本演进、§1 术语表、§2 条目、§3 映射矩阵、§4 使用指引、§5 声明、§6 贡献者、§7 反馈、附录 A-D） |

### 5.2 参考规范模板

| 文件 | 说明 |
|---|---|
| `SPIRIT-AI.md` | SPIRIT-AI 参考条目 + HealthLens 适配（144 行） |
| `CONSORT-AI.md` | CONSORT-AI 参考条目 + HealthLens 适配（144 行） |
| `TRIPOD+AI.md` | TRIPOD+AI 参考条目 + HealthLens 适配（152 行） |
| `DECIDE-AI.md` | DECIDE-AI 参考条目 + HealthLens 适配（144 行） |
| `PROBAST+AI.md` | PROBAST+AI 参考条目 + HealthLens 适配（132 行） |
| `STARD-AI.md` | STARD-AI 参考条目 + HealthLens 适配（151 行） |

### 5.3 辅助材料

| 文件 | 说明 |
|---|---|
| `equator_submission_letter.md` | 本提交信（当前文件） |
| `community_feedback_survey.md` | 社区反馈问卷（18 题） |
| `README.md` | 目录说明 |

### 5.4 相关提交信（供 EQUATOR 参考）

- `ieee_cbbmi_submission_letter.md`（IEEE CBBMI 提交信，同步提交）
- `w3c_aawg_comment.md`（W3C AAWG comment，同步提交）

---

## 六、HealthLens 的资质说明

**HealthLens** 是一家面向大众健康管理的 wellness 平台，运营范围：

- **定位**：wellness（大众健康管理），**非**面向临床试验场景；
- **实践积累**：
  - claims_engine v0.29（wellness 声明合规引擎，用于 wellness/临床边界拦截）；
  - GraphRAG 幻觉评测（多类型幻觉识别与量化）；
  - 联邦后验合并协议（联邦学习下多节点后验合规合并）；
  - Pulse-PPG 零样本评测脚手架（可穿戴 PPG 时序信号跨模型评估）；
  - 八轴评分体系（睡眠、饮食、运动、情绪、社交、压力、中医证型、整体）；
  - 4200 名 zh-CN/zh-TW 个体的真实健康数据；
- **规范贡献基础**：
  - 已整理 6 份 EQUATOR AI 规范的 HealthLens 适配版本；
  - 已构建 ASME V&V 40-2018 与 CDTW 的条目映射；
  - 内部实践与规范条目双向对齐。

---

## 七、术语纪律与合规边界

**CDTW v0.2 全文严格区分 wellness 与临床场景**，遵循以下术语纪律：

| wellness 场景（CDTW v0.2 覆盖） | 临床场景（CDTW v0.2 不覆盖） |
|---|---|
| 健康（health） | 医疗（medical） |
| 关注（attention） | 诊断（diagnosis） |
| 引导（guidance） | 治疗（treatment） |
| 干预（wellness intervention） | 医疗干预 |
| 个体（individual） | 患者（patient） |
| 人群（population/cohort） | 患者队列 |

**声明**：CDTW v0.2 是一份**方法学报告规范**，不构成健康建议。使用本规范撰写报告的研究者须自行评估其在适用法域下的合规义务（GDPR、PIPL、CCPA 等）。

---

## 八、许可

CDTW v0.2 采用 **CC-BY 4.0** 许可。

- 允许 EQUATOR Network 免费使用、修改、分发；
- 要求署名 HealthLens L4 深化团队与 contributors；
- 允许 EQUATOR 在纳入官方规范库后按 EQUATOR 标准流程管理版本；
- 完整条款：https://creativecommons.org/licenses/by/4.0/。

---

## 九、联络方式

| 角色 | 姓名 | 邮箱 | 电话 |
|---|---|---|---|
| 规范组长 | （占位） | （占位） | （占位） |
| EQUATOR 联络人 | （占位） | standards-internal@example.com | （占位） |
| 安全与隐私 | （占位） | security-internal@example.com | （占位） |
| 技术支持 | （占位） | support-internal@example.com | （占位） |

**GitHub 仓库**：（正式提交时填写仓库 URL）

**反馈渠道**：

- GitHub issue：`/issues`（正式提交时填写仓库 URL）
- 邮件：`standards-internal@example.com`（占位）
- 应急响应时间：5 个工作日

---

## 十、结尾

感谢 EQUATOR Network 审阅我们的补充草案。HealthLens 期望通过本次提交：

1. 帮助填补 wellness digital twin 报告规范的全球空白；
2. 与 EQUATOR Network 共同推进 "digital twin for wellness" 的科学话语体系建设；
3. 与 SPIRIT-AI / CONSORT-AI 等既有规范建立正式映射，形成完整的 AI 健康研究报告规范生态；
4. 为全球 wellness 领域研究者提供可复用、可追溯、可反驳的标准化报告框架。

HealthLens 期待 EQUATOR Network 的反馈，并愿承担 v0.3（2027 Q1）之前的所有修订工作。

**HealthLens L4 深化团队 · Digital Twin Working Group**
**2026-10-16**

---

*本提交信为提交模板，正式提交时替换占位信息（收件人邮箱、联络人姓名、GitHub 仓库 URL）。*
