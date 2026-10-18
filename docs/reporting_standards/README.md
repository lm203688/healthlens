# Reporting Standards 目录说明

> **路径**：`docs/reporting_standards/`
> **维护者**：HealthLens L4 深化团队 · Digital Twin Working Group
> **更新日期**：2026-10-16
> **状态**：v0.30.0 版本

---

## 一、目录总览

本目录包含 HealthLens wellness 平台的健康报告规范相关材料，共 **12 份** 文档：

| # | 文件 | 类型 | 行数 | 用途 |
|---|---|---|---|---|
| 1 | **`digital_twin_standard_draft_v0.2.md`** | **数字孪生规范草案（v0.2 提交版）** | **1061** | **主文件，面向 EQUATOR / IEEE / W3C 递交** |
| 2 | `digital_twin_standard_draft_v0.1.md` | 数字孪生规范草案（v0.1 内部草案） | 321 | 保留作版本演进对照，不修改 |
| 3 | `SPIRIT-AI.md` | EQUATOR 规范模板 | 144 | AI 干预试验方案报告规范 |
| 4 | `CONSORT-AI.md` | EQUATOR 规范模板 | 144 | AI 干预试验结果报告规范 |
| 5 | `TRIPOD+AI.md` | EQUATOR 规范模板 | 152 | AI 预测模型开发报告规范 |
| 6 | `DECIDE-AI.md` | EQUATOR 规范模板 | 144 | AI 早期评估报告规范 |
| 7 | `PROBAST+AI.md` | EQUATOR 规范模板 | 132 | AI 研究偏倚风险评估 |
| 8 | `STARD-AI.md` | EQUATOR 规范模板 | 151 | AI 决策准确性研究报告规范 |
| 9 | `equator_submission_letter.md` | 提交信 | ~230 | 提交给 EQUATOR Network |
| 10 | `ieee_cbbmi_submission_letter.md` | 提交信 | ~230 | 提交给 IEEE SB CBBMI |
| 11 | `w3c_aawg_comment.md` | 提交信 | ~230 | 提交给 W3C AI WG |
| 12 | `community_feedback_survey.md` | 反馈问卷 | ~280 | 18 题社区反馈问卷 |
| 13 | `README.md` | 目录说明 | 本文件 | 快速上手指南 |

**总计**：约 **3300+ 行** Markdown 文档。

---

## 二、文件分类

### 2.1 数字孪生规范草案（2 份）

| 文件 | 状态 | 说明 |
|---|---|---|
| `digital_twin_standard_draft_v0.1.md` | 内部草案（保留，不修改） | v0.1（2026-10-16）：48 条初版条目，HealthLens 内部使用 |
| **`digital_twin_standard_draft_v0.2.md`** | **提交版（当前主文件）** | v0.2（2026-10-16）：71 条条目，含 §0 版本演进、§1 术语表（24 条）、§2 条目（含 W1-W15 wellness 专项 15 条）、§3 映射矩阵（6 大 EQUATOR 规范 + ASME V&V 40-2018）、§4 使用指引、§5 声明、§6 贡献者、§7 反馈、附录 A-D |

**v0.1 → v0.2 核心变更**：
- 条目从 48 扩至 71（+23）；
- 新增 §0 版本演进表；
- 术语表从 6 条扩至 24 条；
- 新增 15 条 wellness 专项条目（W1-W15）；
- 新增 6 大外部规范 + ASME V&V 40-2018 完整映射矩阵；
- 新增使用指引、YAML 完整骨架、附录；
- 全文禁用"医疗/诊断/治疗/患者"，改用"健康/关注/引导/干预/个体/人群"。

### 2.2 EQUATOR AI 规范模板（6 份）

EQUATOR Network 的 6 份 AI 相关规范，HealthLens 已提供适配版本：

| 规范 | 版本 | 用途 |
|---|---|---|
| **SPIRIT-AI** | 2023 | AI 干预试验**方案**报告 |
| **CONSORT-AI** | 2023 | AI 干预试验**结果**报告 |
| **TRIPOD+AI** | 2024 | AI 预测模型**开发**报告 |
| **DECIDE-AI** | 2022 | AI **早期探索**报告 |
| **PROBAST+AI** | 2024 | AI 研究**偏倚评估** |
| **STARD-AI** | 2024 | AI **决策准确性**报告 |

每份模板包含：
- 核心条目（参考官方版本）；
- HealthLens 适配说明；
- HealthLens 示例片段（YAML）；
- HealthLens 提交 EQUATOR 的候选补充条目。

**与 CDTW v0.2 的关系**：CDTW v0.2 §3 提供 6 大规范的完整条目映射矩阵，与上述模板协同使用。

### 2.3 提交信（3 份）

面向三大标准组织的提交信：

| 文件 | 目标机构 | 请求动作 |
|---|---|---|
| **`equator_submission_letter.md`** | **EQUATOR Network**（SPIRIT/CONSORT Workgroup Chairs） | 审阅 + 纳入 EQUATOR 规范库 + 与 SPIRIT-AI 建立 crosswalk + 建立联合工作组 |
| **`ieee_cbbmi_submission_letter.md`** | **IEEE SB CBBMI**（IEEE Standards Association Board） | 纳入 Standards Track + 建立联合工作组（IEEE-HealthLens Digital Twin for Wellness Joint WG） |
| **`w3c_aawg_comment.md`** | **W3C AI Working Group** | 纳入 W3C AAWG recommendations 考虑范围 + 与 W3C 现有规范（PROV、DCAT）建立 crosswalk |

**共同附件**：
- `digital_twin_standard_draft_v0.2.md`（主规范）
- `digital_twin_standard_draft_v0.1.md`（对照版）
- 6 份 EQUATOR 规范模板
- `community_feedback_survey.md`（反馈问卷）

**共同声明**：
- CC-BY 4.0 许可；
- wellness 定位，非健康建议；
- 术语纪律（禁用医疗/诊断/治疗/患者）；
- 多法域合规边界（GDPR / PIPL / CCPA / UK ICO / CA CCPA）。

### 2.4 反馈问卷（1 份）

`community_feedback_survey.md`：18 题问卷，覆盖 6 大维度：

| 维度 | 题号 | 说明 |
|---|---|---|
| 术语理解 | Q1-Q3 | wellness/临床边界、术语纪律、术语表理解度 |
| 条目覆盖完整性 | Q4-Q7 | 覆盖度、W 组价值、缺失条目、冗余条目 |
| 可执行性 | Q8-Q11 | 可操作性、YAML 骨架可用性、撰写时间、与 EQUATOR 协作顺畅度 |
| 与其他规范兼容性 | Q12-Q14 | ASME V&V 40-2018、IEEE 标准、W3C 标准 |
| 多法域与合规 | Q15-Q16 | 法域覆盖、法域冲突优先级 |
| 开放性问题 | Q17-Q18 | 提交建议、综合反馈 |

**目标读者**：整合医学研究员、临床数据科学家、AI 工程师、伦理学家、监管方（5 类）

**分发渠道**：GitHub issue、邮件列表、学术会议、学术机构合作、微信公众号/知乎专栏、Twitter/X/LinkedIn（6 类）

---

## 三、快速上手指南

### 3.1 场景 A：想提交给 EQUATOR Network

**阅读顺序**：

1. `digital_twin_standard_draft_v0.2.md` §0（版本演进）→ §1（适用范围与术语表）→ §3（与其他规范的映射矩阵）；
2. `equator_submission_letter.md`（提交信全文）；
3. 6 份 EQUATOR 规范模板（了解 CDTW v0.2 与 EQUATOR 规范的映射背景）；
4. `community_feedback_survey.md`（了解反馈机制）。

**关键章节**：
- CDTW v0.2 §0.2 v0.1 → v0.2 核心变更明细；
- CDTW v0.2 §3.1-3.6 六大 EQUATOR 规范映射矩阵；
- EQUATOR 提交信 §4 请求事项。

**请求动作**：
- 审阅 CDTW v0.2 草案；
- 纳入 EQUATOR 规范库；
- 与 SPIRIT-AI 建立 crosswalk；
- 建立联合 "Digital Twin Reporting Standards Working Group"；
- 公开征求意见 6 个月；
- 组织国际同行评议（20 位以上专家）。

### 3.2 场景 B：想提交给 IEEE SB CBBMI

**阅读顺序**：

1. `digital_twin_standard_draft_v0.2.md` 全文（重点关注 §2 条目分组）；
2. `ieee_cbbmi_submission_letter.md`（提交信全文，尤其 §3 SVIEE 五层架构、§4 与既有 IEEE 标准的互补关系）；
3. `equator_submission_letter.md`（了解与 EQUATOR 的协同）。

**关键章节**：
- IEEE 提交信 §3 SVIEE 五层架构（L0 协议 / L1 统计 / L2 表征 / L3 联邦 / L4 评估）；
- IEEE 提交信 §4 与既有 IEEE 标准的互补关系；
- CDTW v0.2 §3.7 与 ASME V&V 40-2018 映射（作为 IEEE 与 ASME 之间的规范互认桥梁）。

**请求动作**：
- 纳入 IEEE CBBMI Standards Track；
- 建立 "IEEE-HealthLens Digital Twin for Wellness Joint Working Group"；
- 技术评审 + 公开征求意见 12 个月；
- 版本演进纳入 IEEE 标准发布流程。

### 3.3 场景 C：想提交给 W3C AI Working Group

**阅读顺序**：

1. `w3c_aawg_comment.md`（comment 全文，尤其 §3 与 W3C AAWG 关注点的对齐）；
2. `digital_twin_standard_draft_v0.2.md` §1.3 术语表（含 T-11 数据溯源、T-16 可反驳性等）、§2.14 wellness 专项条目（W1-W15）；
3. `equator_submission_letter.md` 与 `ieee_cbbmi_submission_letter.md`（了解跨机构协同）。

**关键章节**：
- W3C comment §3.1 数据溯源与 W3C PROV 对齐；
- W3C comment §3.2 可解释 AI 与 AAWG XAI 关注；
- W3C comment §3.3 联邦学习与多法域合规；
- W3C comment §3.4 wellness AI 与 AI 伦理框架。

**请求动作**：
- 纳入 W3C AAWG recommendations 考虑范围；
- 建立 CDTW v0.2 与 W3C 现有规范（PROV-O、DCAT）的官方映射表；
- 成立 "W3C-AI-Wellness Joint Interest Group"。

### 3.4 场景 D：想参与社区反馈

**阅读顺序**：

1. `community_feedback_survey.md`（问卷全文）；
2. `digital_twin_standard_draft_v0.2.md` §4（使用指引）与附录 A（YAML 骨架）。

**参与方式**：
- GitHub issue 反馈（`/issues`）；
- 邮件反馈（`standards-internal@example.com` 占位）；
- 学术会议现场反馈；
- 学术机构合作反馈。

**反馈承诺**：
- 5 个工作日内响应；
- 公开处理记录；
- v1.0 致谢反馈者（除非明确拒绝）。

### 3.5 场景 E：想按 CDTW v0.2 撰写研究报告

**阅读顺序**：

1. `digital_twin_standard_draft_v0.2.md` §4 使用指引（Step 1-6）；
2. `digital_twin_standard_draft_v0.2.md` §2 条目（71 条）；
3. `digital_twin_standard_draft_v0.2.md` 附录 A（完整 YAML 骨架）；
4. 6 份 EQUATOR 规范模板（了解交叉引用方法）。

**关键步骤**：
1. 确定研究类型（PoC / trial / review / product）；
2. 下载 YAML 骨架，填入研究信息；
3. 逐项填写条目，标记 compliant/partially_compliant/not_applicable/deferred；
4. 交叉引用其他规范（如 "CDTW W6 / TRIPOD+AI AI-6"）；
5. 提交至 wellness outcome registry；
6. 报告末尾添加"CDTW v0.2 合规声明"。

**常见错误速查**（CDTW v0.2 §4.3）：
- 跨场景用词（改用 D2 条目审查）；
- 模型版本缺失（强制 W2）；
- 幻觉评测缺失（强制 W3）；
- 可反驳条件缺失（强制 W6）；
- E-value 缺失（强制 W7）；
- n-of-1 缺失（强制 W8）；
- 联邦后验披露不足（强制 W5）；
- 多法域缺失（强制 W12）；
- 数据溯源缺失（强制 W1）。

---

## 四、术语纪律检查表

所有文档遵循以下术语纪律（CDTW v0.2 §1.2）：

| wellness 场景（覆盖） | 临床场景（不覆盖） |
|---|---|
| 健康（health） | 医疗（medical） |
| 关注（attention） | 诊断（diagnosis） |
| 引导（guidance） | 治疗（treatment） |
| 干预（wellness intervention） | 医疗干预 |
| 个体（individual） | 患者（patient） |
| 人群（population/cohort） | 患者队列 |

**检查方法**：`grep -nE "医疗|诊断|治疗|患者" docs/reporting_standards/*.md`（应仅在对比表格或明确引用其他规范的地方出现，正文禁用）。

---

## 五、许可与授权

- **CDTW v0.2 规范**：CC-BY 4.0
- **EQUATOR 6 份规范模板**：CC-BY 4.0（基于 EQUATOR 官方版本的改编）
- **3 份提交信**：CC-BY 4.0
- **1 份反馈问卷**：CC-BY 4.0
- **本 README**：CC-BY 4.0

完整条款：https://creativecommons.org/licenses/by/4.0/

---

## 六、健康建议免责声明

**本目录中所有文档均为方法学报告规范**，**不构成健康建议**：

- 不替代个体与专业健康角色的沟通；
- 不作为个体健康决策的唯一依据；
- wellness 场景与临床场景有明确边界，本目录仅覆盖前者；
- 使用本目录撰写报告的研究者须自行评估其在适用法域下的合规义务。

---

## 七、贡献指南

欢迎对本目录做出贡献：

### 7.1 反馈类型

- **Bug**（条目描述错误）；
- **Enhancement**（条目建议扩展）；
- **Question**（条目理解咨询）；
- **Crosswalk**（与其他规范的映射建议）；
- **Jurisdictional**（法域合规建议）。

### 7.2 提交方式

- **GitHub issue**：`/issues`（正式启用后）；
- **邮件**：`standards-internal@example.com`（占位）；
- **学术会议现场**：AMIA Annual、IEEE EMBC、CHI、WWW、IJCAI 等。

### 7.3 反馈处理时间

| 反馈类型 | 响应时间 | 处理方式 |
|---|---|---|
| Bug | 5 工作日 | v0.2.1 补丁 |
| Enhancement | 20 工作日 | v0.3 讨论 |
| Question | 3 工作日 | issue 内回复 |
| Crosswalk | 15 工作日 | v0.3 更新 |
| Jurisdictional | 30 工作日 | 与法律专家协作 |

---

## 八、版本演进路线

| 版本 | 日期 | 状态 | 主要变更 |
|---|---|---|---|
| **v0.1** | 2026-10-16 | 内部草案 | 48 条初版条目（保留，不修改） |
| **v0.2** | 2026-10-16 | 提交版（**当前**） | 71 条条目，4 份提交信，1 份反馈问卷 |
| v0.3 | 2027 Q1（预计） | 公开评议 | 吸收公开评议，新增/合并/删除条目 |
| v0.4 | 2027 Q2（预计） | 同行评议 | 国际同行评议（20 位以上专家） |
| v1.0 | 2028（预计） | 正式 | 中英文定稿，纳入 EQUATOR 规范库 |

---

## 九、相关资源

### 9.1 参考规范

- SPIRIT-AI (2023), CONSORT-AI (2023), TRIPOD+AI (2024), DECIDE-AI (2022), PROBAST+AI (2024), STARD-AI (2024)
- ASME V&V 40-2018 Standard for Verification and Validation
- W3C PROV Data Model v1.1
- OASIS OpenLineage
- IEEE 23202 Personal Health Data Privacy (2024)
- IEEE P3620, IEEE P7000, IEEE P3189
- ISO/IEC 25012 Data Quality Model (2022)
- ISO/TR 13677, IEEE P2883（临床数字孪生，参考对比）

### 9.2 HealthLens 实践

- claims_engine v0.29（wellness 声明合规引擎）
- GraphRAG 幻觉评测
- 联邦后验合并协议
- Pulse-PPG 零样本评测脚手架（v0.30.0）
- 八轴评分体系

### 9.3 上游报告

- 《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§6

---

## 十、致谢

感谢：

- EQUATOR Network、IEEE SB CBBMI、W3C AAWG 提供既有规范框架；
- ASME V&V 40-2018 提供 V&V 基础；
- 学术界（VanderWeele & Ding、Popper）提供 E-value 与可反驳性理论基础；
- HealthLens 团队提供实践积累；
- 全球 wellness 研究者、工程师、伦理学家、监管方的未来反馈。

---

**目录维护者**：HealthLens L4 深化团队 · Digital Twin Working Group
**最后更新**：2026-10-16
**许可**：CC-BY 4.0
**版本**：v0.30.0
