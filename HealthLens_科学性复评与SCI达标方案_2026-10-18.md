# HealthLens 科学性复评与 SCI 达标方案

**评估日期**：2026-10-18 08:34（基线 v0.31.0；本轮全部实测，非文档复述）
**评估焦点**：10-17 方案执行复验、科学内核新增资产审计、是否达到 SCI 论文水平与贡献度、下一步达标方案
**复验范围**：293 个文件变更 / 13.6 万行新增；全量测试套件实跑（2m47s）；E/G、E-value、PhenoAge、证据库分级运行时核验；外部文献对标

---

## 一、结论摘要

> ### SCI 判定
>
> **仍未达到 SCI 投稿线，但卡点已经换位。** 10-17 报告判定的三项工程硬阻断（schema 迁移、依赖锁定、E/G 共线）本轮**全部实测修复**；A 组 6 项口径修复**全部落地且质量高**。现在的卡点是：
>
> **(a) 一个新发现的口径硬伤 S7**——论文 §5 把 76% 是合成夹具的案例库称为"真实世界案例库"，L1=56 里 48 条是合成件（2–3 天可修，纯口径）；
> **(b) 10-17 就已判定但仍未做的 C1 专家内容效度**（3–5 周协调期，不可压缩，是档 1 期刊唯一真正的门槛）。
>
> **贡献度评级：系统集成型贡献，新颖性成立且有真实增量，但外部效度证据仍为零。** 本项目不是"又一个 TCM 框架论文"——它有竞品都没有的东西：可计算轴 + 结构因果模型 + E-value + fail-closed 声明引擎 + n-of-1 联邦栈 + 信度量化。但在独立专家内容效度（C1）完成前，论文的全部验证仍是"作者构造的东西互相印证"，这是档 1 期刊唯一真正的门槛。

### 与 10-17 报告的差异

10-17 判定"未达 SCI，4–6 周可达档 1"，瓶颈是 B 组地基 + C1/C2 协调。本轮复验：**B 组已完工（实测通过），C2 已完工（ICC 全优），A 组 6 项全部落地**；但执行过程中暴露出一个当时没看到的问题——**S7：论文对证据库的 over-claim 与数据自相矛盾**；同时 **manifest 宣称"1680 tests pass"与实测（1723 passed / 5 failed）再次不符**——10-17 的 A5 复发了。

---

## 二、上一轮方案执行复验总表

| 组 | 项 | 10-17 要求 | 本轮实测 | 结论 |
|---|---|---|---|---|
| A1 | 轴数三口径统一 | 全文只留 reserved 一种说法 | §3.2 "Reserved Axes (I–J, Not Implemented)" 独立成节；摘要 / §3.1 / §6 分布说明三处一致 | ✅ |
| A2 | 证据分级降档 | 不把 L2 说成 human-RCT | line 134 显式免责："L2 by its own definition does not require human RCTs, so the pooled percentage is not a claim that 97% of the pool is human-RCT-level" | ✅ |
| A3 | 收敛效度改名 | domain-expectation concordance + 披露自编码 | 摘要与表 1 均已改，注明 "author-encoded keyword dictionary; exploratory content-validity proxy, not a psychometric convergent-validity estimate" | ✅ |
| A4 | 校准带改名 | prior uncertainty bands | manifest 已改并加 "NOT empirical calibration against observed outcomes" 免责 | ✅ |
| A5 | manifest 数字对齐 | 测试数/DOI/ORCID 零偏差 | DOI 已诚实化（7 verified + 8 traditional + 14 unverified + 91 synthetic，manifest 与 DB 一致）；**测试数写成 1680，实测 1723 passed / 5 failed——不符**；**ORCID 仍 PENDING_USER_FILL** | 🟡 复发 |
| B1 | schema parity + 37 表迁移 | 干净库 alembic 跑通；CI 含 parity | 007 补 32 表（tools/gen_schema_migration.py 生成 + 人工复核说明）+ 008 联邦乐观锁；parity 测试 5 用例在；全量套件仅 1 个相关失败（见 S10） | ✅ |
| B2 | 依赖锁定 | 两次安装哈希一致 | constraints.txt 哈希化 + lock 测试 12 用例（== 精确 pin + PEP 503 规范化） | ✅ |
| B3 | E/G 解耦 | hrv=45 时 E≠G | G 轴重构主输入（sleep_duration_cv 第二主输入，HRV 降副锚点 weight 16→8）；**运行时验证：仅 HRV → G 诚实返回 unmeasured；中段 E=81.2 vs G=24.4 完全分化** | ✅ 超预期 |
| C1 | 专家内容效度 Delphi | S-CVI ≥0.90 进论文 | **未动**；论文 limitations 仍写 "needs further calibration by independent expert Delphi and quantitative text mining" | 🔴 |
| C2 | 信度量化 | 八轴 ICC/Kappa 进论文 | 工具 + 指标已产出（ICC 0.956–1.000，种子确定性有测试锁定）**但论文未集成、未上 Zenodo** | 🟡 半步 |
| C3 | n-of-1 启动 | 8–12 周数据回流 | 仅方案层：SPIRIT-AI 队列协议 6 件套（30–60 人、4 臂 crossover、OSF/DOI 占位符），无真实数据 | 🟡 未启动 |
| C4 | Zenodo 铸 DOI | DOI 可引用 | deposit_manifest + README 就绪，尚未执行上传 | 🟡 待执行 |

---

## 三、本轮新增的科学资产（正面清单，全部实测）

1. **B3 修复是科学级而非工程级。** G 轴引入 `sleep_duration_cv`（睡眠时长变异系数）为第二主输入、HRV 降为副锚点，并以"构造独立性闸门"处理无睡眠输入（返回 unmeasured + 诚实说明"仅 HRV 不足以刻画神/情志，会退化为 E 轴领域的重叠测量"）。docstring 明写这消除了审稿人"八轴实为 7.5 轴"的把柄。实测三场景：`hrv=45 only → E=100 measured, G=unmeasured`；`hrv=25,cv=0.50 → E=81.2, G=24.4`；`hrv=18,cv=0.35 → E=62.5, G=31.1`。
2. **PhenoAge 对标装置**（`app/core/phenoage.py`）：Liu 2018 + 2019 更正版公式照抄（DOI 10.1371/journal.pmed.1002760，系数逐字一致），SI 单位纪律写进 docstring（临床单位代入会发散），`from_clinical_units()` 提供转换。H 轴从"自造扣分表"升级为"与已发表时钟的偏移对照装置"——把自证组件换成对标组件的范式动作。
3. **信度量化落地**：输入扰动 bootstrap（±5%，n=1000，种子 20261017）产出八轴 ICC(2,1)：

   | 轴 | A | B | C | D | E | F | G | H |
   |---|---|---|---|---|---|---|---|---|
   | ICC(2,1) | .9935 | .9569 | .9751 | .9813 | .9964 | 1.0000 | .9832 | .9668 |
   | Kappa(linear) | 1.000 | 1.000 | 1.000 | .961 | 1.000 | 1.000 | .872 | .934 |

   Fisher-Z CI 齐全，全部 excellent；D/G 的 Kappa < 1 反映阈值附近档位穿越，边缘画像（P17/P18）是真实不稳定区，应如实报告。
4. **复现地基完工**：schema parity 门禁（ORM ↔ 迁移差集必须为空）、007 迁移（32 表，含 longitudinal_studies / axis_snapshots / biomarker_readings / partners / field_consents / audit_events 等）、008 联邦乐观锁（version_id + 唯一索引防双算）、constraints 哈希锁、版本同步（`sync_version.py --check` 实测 0.31.0 三处一致）、DOI 交叉核验工具链（抓出并标注 1 条幻觉 DOI 10.1038/s41591-026-04102-8、1 条 not_found 10.1016/j.ther.2026.105127）、A2A 任务生命周期真实实现 + MCP/A2A 契约测试层。
5. **medRxiv 提交包内部诚实**（manifest / data_availability_statement / reviewer_guidance 三件套）：明确披露 91 合成夹具、15/120 可独立验证（"this coverage is stated, not rounded"）、prior-uncertainty bands 性质。
6. **历史科学缺陷保持修复状态**：dowhy strict-mode 死代码修复仍在（`dowhy_mode in {"auto","dowhy"}`）；E-value 与 VanderWeele & Ding (2017) 公式精确一致（负效应 abs、零效应报错、exp 上限 30 防溢出）；fusion_engine 单轴失败改为结构化 `axis_scoring_errors`（2026-10-14 M06 P0-2，fail-loud，不再静默吞掉）。

---

## 四、科学性问题清单（本轮，按严重度）

### S7 🔴 论文对证据库 over-claim（本轮最严重，10-17 未覆盖）

实测交叉统计 `data/case_evidence_db.json`（n=120）：

| citation_status | 数量 | 其中标 L1 | 其中标 L2 |
|---|---|---|---|
| synthetic_validation | **91 (76%)** | **48** | 20 |
| unverified_no_publication | 14 | 4 | 8 |
| traditional（古籍） | 8 | 0 | 0 |
| verified_crossref | 7 | 4 | 3 |

- 论文 §5 标题 **"Evidence Base: Real-World Case Library (n=120)"**、正文 "containing 120 **real human-trial or classical-experience** entries"、摘要 "a **real-world** case evidence base (n=120; L1=56, L2=31, L3=33)"——**三处均未披露 76% 为合成夹具**；而提交 manifest 如实披露。审稿人对照 Zenodo 公开数据即可证伪，属可外部核验的 over-claim。medRxiv 页面显示 manifest 摘要（诚实）、论文正文 over-claim，同一次提交内自相矛盾。
- 更深一层：**L1 的定义（≥2 项独立人体 RCT 一致）在定义上不可能由合成夹具满足**——48 条合成件被标 L1 是分级口径的范畴错误。
- **该错误污染头条指标**：`coverage_L1 = 0.95`（"95% with L1-grade evidence"）由推荐池反推，而池中 L1 多数源自这些合成件（证据分级分布 L1=134/154）；重新分级后该数字会大幅下降，论文必须报告真实值。

### A5' 🔴 manifest 测试数复发

manifest 写 "All 1680 automated tests pass"。本轮实跑：**1723 passed / 5 failed / 10 skipped**。5 个失败的定性：

| 失败 | 性质 |
|---|---|
| ×3 A2A-C7（protocol_audit / a2a_contract ×2） | 审计规则的模式匹配启发式与实现脱节——任务生命周期端点其实已实现（TaskStore + 四 handler 为真实代码，JWS 有真实实现），是审计规则 stale，**不是卡片谎称** |
| agent-card 大小测试（全序瞬时失败） | 暂存版 10,167B，距 10KB 注册上限仅 **73B 余量**，真实脆弱点 |
| `test_federated_migration.py::test_downgrade_then_upgrade_roundtrip` | **真缺陷**：008 迁移 downgrade 未移除 `axis_snapshots.version_id`（该测试为新增未跟踪文件，正是它抓到的） |

数字必须由 CI 实跑生成，禁止手写。

### S8 🟡 信度解释需精确

ICC 来自输入扰动，度量的是"确定性打分器在输入噪声下的**计算可复现性**"，不是心理测量学的 test-retest 信度（后者需真人重复测量）。论文引用必须写明口径；D 轴 Kappa .961 / G 轴 .872 反映阈值附近档位穿越，边缘画像应报告为不稳定区——这反而是优点（如实暴露确定性打分器的边界）。

### S9 🟡 C1 仍是最大单项缺口

论文 limitations 把专家 Delphi 写成 future work——"把 future work 写进论文而不是做掉它"。这是自证变他证的唯一支点，也是档 1 方法学期刊的实质门槛。10-17 已判定，本轮仍未动。

### S10 🟢 工程脆弱点

agent-card 73B 余量（增长即爆）；008 downgrade 缺陷；C7 审计启发式需改为校验 `SUPPORTED_METHODS` 而非匹配文案；A2A conformanceNote 对未实现项的声明方式需与实现对齐；Puls-EGG / RAGAS 为零样本评测脚手架（诚实标注"无真实模型权重"，尚无真实模型运行，只能证明流程正确）。

---

## 五、贡献度评估（对标外部）

2025–2026 检索（TCM 计算框架 / n-of-1 联邦开源栈 / wellness 数字孪生/E-value 组合）**未发现同构竞品**：最接近的分别为 TCM 数据库类（TCMSID 等，纯数据资产）、FL 框架综述类（Flower 等，通用框架）、影像 FL 应用（npj Digital Medicine，无中医映射与因果层）。ISSBF 的"经典构念 → 可测通路 → 可计算轴 → SCM → E-value → 五法域 fail-closed 声明"链条是独有组合。

| 维度 | 评级 | 依据 |
|---|---|---|
| 新颖性 | **7/10** | 无同构竞品；但属系统集成创新而非算法发现 |
| 严谨性 | **5.5/10** | S7 口径硬伤 + manifest 数字复发 + C1 缺失；内核公式（E-value、PhenoAge）经复核正确 |
| 完整性 | **6/10** | 工程层完整（协议/合规/迁移/锁/评测脚手架）；验证链缺第 2、5 步 |
| 可复现性 | **8.5/10** | 本轮最大进步：parity 门禁、哈希锁、快照冻结、Zenodo 材料包 |
| 影响力潜力 | **6.5/10** | wellness n-of-1 + 联邦开源栈是真实空白，但需真实数据点火 |

**范式定位**：按测量工具开发五步（条目生成 → 专家内容效度 → 信度 → 结构效度 → 效标效度），当前处于**第 3 步完成（计算信度）、第 1/4 步有半份、第 2/5 步空缺**。这正是"框架描述论文"与"工具开发论文"的分水岭——做完 C1，论文从"又一个框架"变成"一个经专家内容效度与信度检验的计算工具"。

---

## 六、SCI 阶段判定与投稿梯度

- **当前不可投**：档 1 必要条件 C1 未满足；S7 若带病投稿属可外部证伪的 over-claim，有被撤稿/flag 风险。
- 修复 S7 + 集成 C2 后：medRxiv 更新版即可投（补 ORCID，占时间戳）。
- 完成 C1 后：档 1 整合医学方法学刊（JIM / European J of Integrative Medicine / IMR 一类，APC 投稿前官网复核）实验性达标；npj Digital Medicine / JMIR 可试。
- 档 2（Ageing Research Reviews 综述级/高影响数据论文）：等 C3 真实 n-of-1 数据回流，明确不在本轮路径。
- 纲要中的 Nature Medicine RCT 一栏：维持降级（资源不匹配）。

---

## 七、提升方案（D 组：口径与证据；E 组：科学增益）

### D 组：口径与证据（先做，决定论文是否诚实）

| # | 动作 | 工作量 | 验收标准 |
|---|---|---|---|
| **D1（P0）** | **S7 修复**：§5 改名 "Case Evidence Library: stratified by verification status"；合成件单列并禁止进入 L1–L3 文献分级（另设 S 类或从计级中剔除）；摘要去掉 "real-world case evidence base" 表述；**重跑 `tools/engine_validation.py`，用重新分级后的真实 L1 数更新 95% 指标与 Table 1** | 2–3 天 | 论文声称的等级分布与 DB 实际分布逐项相等；新增 `tests/test_paper_claims_match_data.py` 锁死"论文数字 == 数据实况"（防再次漂移） |
| **D2（P0）** | manifest 测试数改由 CI 实跑输出生成（禁手写）；修 008 downgrade（移除 version_id）；C7 审计改为校验 `SUPPORTED_METHODS` 而非匹配 conformanceNote 文案；agent-card 瘦身（extensions 外置或压缩）留 ≥1KB 余量 | 1 天 | CI 全绿；manifest 数字与 CI 输出同源；卡片余量 ≥1KB |
| **D3（P1）** | ICC 表 + Kappa + CI 进论文新增 "Reliability (computational)" 一节，注明输入扰动口径、D/G 档位穿越与边缘不稳定画像；信度 JSON 随 Zenodo 数据集发布 | 2–3 天 | 论文含 8 轴信度表，术语与 `tools/reliability_bootstrap.py` 输出一致 |

### E 组：科学增益（把自证变他证）

| # | 动作 | 成本 | 验收标准 |
|---|---|---|---|
| **D4（P1）** | **专家内容效度 mini-Delphi**：5–8 位中医专家对 A–H 四向映射（经典概念↔通路↔轴）独立评分，算 I-CVI/S-CVI | 3–5 周（协调为主） | S-CVI ≥0.90 或如实报告低 CVI 的轴；论文新增 "Expert content validity" 一节——**单项最大增益，把论文从 describe 变成 validate** |
| **D5（P2）** | OSF 预注册落地（去占位符，固定随机种子与分析计划）；启动一台穿戴设备 8–12 周个人纵向（n-of-1 自追踪） | 1 天 + 8–12 周并行 | 预注册 URL 可访问；回流至少一条轴的前后对比 + 效应量（为耦合系数标定供首批真实数据） |
| **D6（P2）** | PhenoAge 对标跑数（用可核验案例的标志物子集做 H 轴偏移对照），出装置级报告 | 2–3 天 | 附录级结果 + 诚实声明"装置级验证，真实校准需公开队列数据" |
| **D7（P2）** | Zenodo 正式上传执行（画像生成脚本 + 信度 JSON + 验证指标快照 + DOI 核验结果） | 1 天 | DOI 可引用；data availability 落地 |

**优先级**：D1 > D2 > D3 > D7 > D4 > D5 > D6。**D1 是纯口径修复且防"可证伪 over-claim"，优先于一切新增功能。**

---

## 八、路线图

```
第 1 周    D1 + D2 → 口径零矛盾、CI 全绿、论文-数据一致性测试上线
第 1 周    medRxiv 更新（补 ORCID + S7 修复版文本）——先占时间戳
第 2 周    D3 信度进论文 + D7 Zenodo 正式上传（DOI 落地）
第 2-6 周  D4 专家 Delphi（协调期，最早启动）→ 第 6 周论文补效度一节 → 档 1 投稿
第 6 周起  D5 数据回流 → 耦合系数首轮标定 + 档 2 冲刺
```

---

## 九、最终判定

> **未达到 SCI 论文阶段。达成条件明确且全部无人类受试者伦理门槛：D1（证据库口径，2–3 天）+ D2（CI 口径，1 天）+ D3（信度进论文，2–3 天）+ D4（专家内容效度，3–5 周）= 档 1 投稿线。**
>
> 与 10-17 相比，项目从"地基松 + 口径乱"前进到"地基实 + 一个口径硬伤 + 一个科学动作"——工程侧已不再是瓶颈。**S7（D1）决定论文是否诚实，C1（D4）决定论文是否够格。** 两者完成后，本项目作为"首个可计算、可审计、诚实标注证据边界的中西医整合计算框架"，达到档 1 整合医学方法学期刊的投稿水平；贡献度的下一跳（从工具论文到有真实数据的验证论文）由 n-of-1 队列（D5）点燃。
>
> - 本周立刻可做：D1 口径修复 + D2 CI 修复 + medRxiv 更新（ORCID 仍需用户填写）
> - 明确不做：不追纲要里的 Nature Medicine RCT；不把输入扰动 ICC 冒充 test-retest 信度；Puls-EGG 评测在拿到真实权重前不得对外宣称模型能力

---

## 附：本轮复验命令索引

```bash
# 执行复验总表 A 组
grep -n "Ten Steady-State\|eight-axis mapping\|reserved for future" HealthLens_论文_英文版_全文.md
grep -n "human or RCT-level\|convergent\|calibration band" HealthLens_论文_英文版_全文.md
grep -n "prior-uncertainty\|prior uncertainty" submissions/medrxiv/submission_manifest.json

# B3 E/G 解耦运行时验证
python -c "from app.core.axis_scorers import score_all_axes; r=score_all_axes(wearable={'hrv_rmssd':45}); print(r['E'].score, r['E'].measured, r['G'].score, r['G'].measured)"  # E=100 True, None False

# S7 证据库交叉统计
python -c "import json; from collections import Counter; db=json.load(open('data/case_evidence_db.json')); cases=db['cases']; print(Counter((c['evidence_level'],c['citation_status']) for c in cases))"

# manifest 测试数 vs 实测
grep -o "All [0-9]* automated tests pass" submissions/medrxiv/submission_manifest.json
python -m pytest tests/ -q --no-header -p no:cacheprovider 2>&1 | tail -3   # 实测 1723 passed / 5 failed / 10 skipped

# A5' 五项失败定性
python -m pytest tests/test_federated_migration.py -q 2>&1 | grep -A 5 "AssertionError"
git show :agent-card.json | wc -c   # 10167B（73B 余量）

# 历史缺陷保持修复
python -c "import inspect; from app.lib import nof_one_effect as ne; print(inspect.getsource(ne.compute_evalue))"
sed -n '395,400p' app/lib/dowhy_adapter.py   # dowhy_mode in {'auto','dowhy'}
grep -n "axis_scoring_errors" app/lib/fusion_engine.py

# 信度指标
python -c "import json; [print(r['axis'], r['icc_2_1'], r['weighted_kappa']) for r in json.load(open('engine_reliability_metrics.json'))['results']]"

# 版本同步
python tools/sync_version.py --check
```

**本轮对仓库零源码改动**，仅读取、运行测试与外部核验。
