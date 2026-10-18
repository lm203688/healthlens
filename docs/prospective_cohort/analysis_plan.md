# HealthLens 前瞻队列统计分析计划

**版本**：v0.1.0-draft · 2026-10-16
**代码入口**：`app/lib/nof_one_effect.py`（L1-2）+ `app/lib/federated/`（L3）

> 参考：`study_protocol.md` §7；`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §5 L1-2 / L3。
> 本计划对齐 SPIRIT-AI v1.0 的统计分析披露要求；所有分析代码开源并附测试。

## 1. 总体原则

- **个体优先**：所有主要终点以个体层效应量为基本单元（n-of-1 paired bootstrap），再做层次聚合；
- **贝叶斯优先**：主体分析用贝叶斯（PyMC 可选，纯 Python Monte Carlo 兜底）；
- **可反驳**：所有主要结论必须输出 E-value 与敏感性分析，避免过拟合；
- **联邦优先**：所有跨参与者聚合通过 `app/lib/federated/` 完成，避免明细数据越域。

## 2. 分析集定义

### 2.1 全分析集（ITT）
所有签署知情同意书并至少完成**基线**与**1 臂 2 周**的参与者。
- 用途：主要终点主分析集

### 2.2 主要分析集（PP）
ITT 基础上，完成**全部 4 臂**且**可穿戴同步率 ≥ 70%**、**问卷应答率 ≥ 80%**、**3 次抽血完成率 100%** 的参与者。
- 用途：主要终点敏感性分析

### 2.3 探索分析集（ES）
PP 基础上，完成**所有 4 臂且无重大方案偏离**（例如中途换臂、干预中断）的参与者。
- 用途：探索性终点

### 2.4 排除标准
- 中途退出并明确要求删除数据
- 未签署知情同意书
- 严重方案偏离（例如完全未做干预）

## 3. 主要终点分析

### 3.1 个体层：paired bootstrap
- **代码**：`app/lib/nof_one_effect.py::IndividualEffect`
- **方法**：
  - 对每个参与者、每个臂，计算 `(post_arm - baseline) - (post_washout - baseline)`；
  - 10 000 次 paired bootstrap 得到 95% CI；
  - 计算 Cohen's d 与 E-value（`compute_evalue`）。
- **产出**：`IndividualEffect` 对象数组，写入 `participant_id → IndividualEffect[]`。

### 3.2 群体层：贝叶斯层次模型
- **代码**：`app/lib/nof_one_effect.py::BayesianHierarchicalAggregator`
- **模型**：
  - `group_effect ~ N(mu_pop, tau)`
  - `tau ~ HalfNormal(1)`
  - `mu_pop ~ Normal(0, 10)`
- **推断**：
  - PyMC 可用：NUTS 4 000 次迭代，warm-up 2 000 次，3 chain
  - PyMC 不可用：纯 Python Monte Carlo 20 000 次采样
- **产出**：`pooled_effect`, `tau_squared`, `random_effect_weights`, `posterior_mean`

### 3.3 联邦聚合
- **代码**：`app/lib/federated/aggregation.py` + `sufficient_stats.py`
- **策略**：每个参与者本地计算 `IndividualEffect`，仅上传 `(point_estimate, std_error, n)` 三元组；
- **验证**：`app/lib/federated/single_machine_fabric.py` 上先做单机多租户仿真，与集中式结果对比 CI 宽度。

## 4. 次要终点分析

### 4.1 分轴效应量
- 对 A–H 每一轴分别跑 §3.1 + §3.2；
- 多重比较校正见 §6。

### 4.2 生物标志物变化
- **参数化模型**：`endpoint ~ baseline + arm + period + carryover(arm_prev)`（混合效应模型）
- **代码**：`app/lib/causal_simulator.py` 的辅助工具
- **协变量**：年龄、性别、基线值

### 4.3 生物学年龄偏移
- 使用 `data/phenoage_alignment.json` 的映射关系，计算 PhenoAge / GrimAge；
- 定义**生物学年龄偏移**：`shift = PhenoAge(post) - PhenoAge(baseline)`；
- 分析同上：paired bootstrap + 贝叶斯层次。

## 5. 缺失数据处理

### 5.1 缺失机制
- **MCAR**：随机缺失（例如设备掉线一天）
- **MAR**：非完全随机（例如低依从性者更可能漏答）
- **MNAR**：非随机（例如症状恶化导致中断）

### 5.2 处理策略

| 缺失场景 | 主分析处理 | 敏感性分析 |
|---|---|---|
| MCAR 日粒度 | 线性插值（≤ 3 天） | 直接删除 |
| MAR 中期问卷缺失 | **多重插补**（m=20） | 完整案例分析 |
| MAR 期末缺失 | **末次观测携带（LOCF）** | 多重插补 |
| MNAR 退出 | 主分析中保留至退出日 | 敏感性分析：假定退出处为最差结局 |
| 可穿戴同步率低 | 使用已同步日的日均值 | 主分析：仅使用同步率 ≥ 70% 参与者 |

### 5.3 敏感性分析
- **LOCF vs MICE vs 完整案例**三种方式对比主要终点；
- 若三种方式给出**方向一致但幅度不同**的结果，采用 LOCF（最保守）为主分析。

## 6. 多重比较校正

主要终点仅 1 个（八轴综合分变化），无需校正。次要终点需校正：

- **分轴效应量（8 项）**：Benjamini-Hochberg FDR α=0.05
- **生物标志物（10+ 项）**：Holm-Bonferroni（保守）
- **生物学年龄偏移（3 种时钟）**：Benjamini-Hochberg FDR α=0.05

**贝叶斯分析**不做传统 p-value 校正，但报告后验概率 `P(effect > 0 | data)`；若需与频率派比较，采用 `P(|effect| > 0) > 0.95` 作为显著阈值。

## 7. 先验设置

### 7.1 主先验（无信息）
- `mu_pop ~ Normal(0, 10)`
- `tau ~ HalfNormal(1)`
- `group_effect ~ Normal(mu_pop, tau)`

### 7.2 弱信息先验（有历史效应量参考）
若引用已验证文献（如 `data/case_evidence_db.json` 中 `citation_status == "verified_crossref"` 的条目），可设：
- `mu_pop ~ Normal(log(expected_effect), 0.5)`

### 7.3 先验敏感性分析
- **先验 A（无信息）**：主分析
- **先验 B（历史效应量）**：敏感性分析
- 若两先验下结论方向一致，报告为主分析；否则报告差异。

## 8. 反事实与因果推断

- **代码**：`app/lib/causal_simulator.py`
- **方法**：对每个参与者、每个臂，构造反事实——"若未接受此臂干预，结局如何"
- **实现**：washington 反事实（用 washout 期作为对照）+ IV 反事实（用未接受臂的参与者作为对照）
- **产出**：ATE / ATT / CATE 三个层级的估计

## 9. 探索性分析

### 9.1 联邦层 tau² 稳定性
- 分 3 个亚组（性别 / 年龄 / 基线综合分高/低）跑联邦聚合；
- 对比 tau² 是否稳定；不稳定则报告并讨论。

### 9.2 个体预测准确度
- 用前 2 臂预测后 2 臂反应；
- 用 8 折交叉验证；
- 报告 AUC 与校准曲线。

## 10. 统计软件与复现性

| 用途 | 工具 | 版本 |
|---|---|---|
| 主分析 | Python 3.11 | 3.11.x |
| 贝叶斯 | PyMC（可选） | 5.x |
| 层次模型 | 纯 Python Monte Carlo | 项目内实现 |
| 因果推断 | `app/lib/causal_simulator.py` | 项目内实现 |
| 联邦聚合 | `app/lib/federated/` | 项目内实现 |
| 随机数种子 | NumPy default_rng | 123456（OSF 预注册时固定） |

**复现要求**：所有分析脚本、随机数种子、PyMC 采样器参数、缺失数据处理策略均在 OSF 预注册时固定；任何事后变更需 IRB 备案。

## 11. 版本历史

- v0.1.0-draft（2026-10-16）：初稿，等待 IRB 提交前评审

---

**wellness 声明**：本统计分析计划**不做医疗决策**；所有效应量报告为 wellness 信号变化，非疗效评估。
