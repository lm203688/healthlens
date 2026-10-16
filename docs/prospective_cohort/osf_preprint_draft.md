# HealthLens 前瞻队列 OSF 预注册草案

**版本**：v0.1.0-draft · 2026-10-16
**平台**：Open Science Framework (OSF) · `https://osf.io/`
**规范**：SPIRIT-AI v1.0 + CONSORT-AI
**URL 占位**：`https://osf.io/<PREREG_PLACEHOLDER>`

> 参考：`study_protocol.md`；`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §6 与 §8 阶段 E。
> OSF 预注册是"预注册 + 前瞻队列 30–60 人 + 联邦扩展"的关键交付物之一。
> **本草案不实际提交 OSF 账号**——需研究者用个人 OSF 账号在 IRB 提交前手动上传。

---

## 1. 预注册元信息

| 字段 | 值 |
|---|---|
| 研究标题 | HealthLens Integrated Medicine n-of-1 Prospective Cohort Study (2026–2027) |
| 中文标题 | HealthLens 整合医学 n-of-1 前瞻队列研究（2026-2027） |
| 研究类型 | Prospective cohort study, n-of-1 crossover, wellness lifestyle intervention |
| 主要研究者 | HealthLens Research Team（占位，IRB 提交时替换为具名 PI） |
| 机构 | （占位） |
| 伦理批件号 | （待 IRB 审批后填入） |
| 版本号 | v0.1.0-draft |
| 提交日期 | 2026-12-15（目标） |
| 预注册 URL | https://osf.io/`<PREREG_PLACEHOLDER>` |
| 数据 DOI 占位 | Zenodo `10.5281/zenodo.<DATASET_ID_PLACEHOLDER>` |

## 2. 摘要

**背景**：现有 wellness 干预研究普遍缺失个体异质性测量、统一稳态轴表征与可复用的因果装置。HealthLens 已交付八轴稳态框架（A–H）与 L1 层 n-of-1 效应量与层次聚合代码，本次前瞻队列把该装置放到真实数据上做首次外部有效性检验。

**目的**：评估四类 wellness 干预（睡眠节律 / 抗炎饮食 / 有氧力量 / 正念冥想）对个体八轴综合分与关键生物标志物的影响，并通过联邦聚合验证群体效应量。

**设计**：前瞻性 n-of-1 crossover，四臂 × 2 期，n=40（可扩展至 n=60），8–12 周，含 4 周 washout。

**主要终点**：8 周时八轴综合分较基线的变化。

**次要终点**：各轴单独变化、生物学年龄偏移、关键生物标志物变化、可穿戴指标变化、依从性。

**主要方法**：个体层 paired bootstrap + 群体层贝叶斯层次模型 + 联邦聚合。

## 3. 假设

### 3.1 主要假设
- **H1**：至少一种 wellness 干预臂在 8 周内显著改善八轴综合分（8 周个体效应量后验均值 > 0 且 95% CI 不含 0）。

### 3.2 次要假设
- **H2a**：睡眠节律臂主要改善 D 轴（阴阳-昼夜轴）；
- **H2b**：抗炎饮食臂主要改善 F 轴（正邪-炎症轴）与 hsCRP；
- **H2c**：有氧力量臂主要改善 B 轴（气血-线粒体轴）与 RMSSD；
- **H2d**：正念臂主要改善 G 轴（神-情志轴）与感知压力；
- **H2e**：主要臂效应量的后验概率 `P(effect > 0 | data) > 0.95`。

### 3.3 探索性假设
- **H3a**：联邦层聚合得到的 tau² 与集中式估计一致（差异 < 0.1）；
- **H3b**：生物学年龄偏移（PhenoAge）与八轴综合分变化方向一致；
- **H3c**：个体预测准确度（前 2 臂预测后 2 臂）AUC > 0.7。

## 4. 方法

详细见 `study_protocol.md`。核心要点：

- **样本**：30–60 人，年龄 25–65，非孕，无重疾病史；
- **设计**：4 臂 × 2 期 crossover，随机化块=8，随机数种子=123456；
- **测量**：八轴综合分 + 生物标志物（3 次抽血）+ 可穿戴（每日）+ 问卷（每 2 周）；
- **分析**：paired bootstrap 10 000 次 + 贝叶斯层次（Monte Carlo 20 000 次或 PyMC 4 000 次）+ 联邦聚合；
- **代码**：`app/lib/nof_one_effect.py`, `app/lib/federated/`, `app/lib/causal_simulator.py`。

## 5. 时间线与里程碑

| 里程碑 | 目标日期 | 状态 |
|---|---|---|
| IRB 提交 | 2026-11-30 | 待完成 |
| OSF 预注册 | 2026-12-15 | 待完成 |
| 招募开始 | 2027-01-15 | 待完成 |
| 首批入组 | 2027-02-01 | 待完成 |
| 队列完成（末例入组） | 2027-04-30 | 待完成 |
| 干预期结束 | 2027-06-30 | 待完成 |
| 主要分析完成 | 2027-08-31 | 待完成 |
| Zenodo 数据发布 | 2027-09-30 | 待完成 |
| 论文投稿 | 2027-10-31 | 待完成 |

## 6. 预注册变更策略

- 任何方法学变更（分析口径、主要终点、排除标准）**必须**在 OSF 记录版本变更，并同步更新 IRB；
- 版本变更记录格式：`version + date + author + rationale + diff`；
- 未备案的变更视为**方案偏离**，在分析报告中如实披露。

## 7. 作者贡献声明（CRediT）

| 角色 | 人员 |
|---|---|
| Conceptualization | HealthLens Research Team |
| Methodology | HealthLens Research Team |
| Software | `app/lib/nof_one_effect.py`, `app/lib/federated/` |
| Validation | 待 IRB 提交时明确 |
| Data curation | 待研究进行中明确 |
| Writing – original draft | 本草案 |
| Writing – review & editing | 待 IRB 提交时明确 |
| Supervision | 待 IRB 提交时明确 |

## 8. 数据与代码可用性

- **代码**：`https://github.com/HealthLens/healthlens`，MIT License
- **数据**：Zenodo `10.5281/zenodo.<DATASET_ID_PLACEHOLDER>`，CC-BY 4.0
- **分析脚本**：随代码仓库一并发布
- **匿名化明细数据**：Zenodo 公开版本仅含**聚合级**数据；个体级明细数据在**受控访问**下提供（申请邮件联系占位邮箱）

## 9. 财务与利益冲突

- 本研究**无商业资助方**；
- HealthLens Research Team 无与本研究相关的商业利益冲突；
- 可穿戴设备如为项目统一采购，将在分析报告中披露设备来源。

## 10. 版本与预注册 URL

**版本号**：v0.1.0-draft
**OSF 预注册 URL**：https://osf.io/`<PREREG_PLACEHOLDER>`
**下一版本目标**：v0.2.0（IRB 提交前 30 日）
**下一版本变更计划**：
- 补充具名 PI 与机构信息
- 补充伦理批件号
- 补充详细招募流程图（流程图未在本次草案产出）
- 补充统计代码的具体哈希引用

---

**wellness 声明**：本研究为 wellness 生活方式研究，非医疗研究。预注册内容不承诺任何治疗效果。
