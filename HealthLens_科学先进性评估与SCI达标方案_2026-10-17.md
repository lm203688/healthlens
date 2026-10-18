# HealthLens 科学先进性评估与 SCI 达标方案

**评估日期**：2026-10-17 06:30（基线 v0.30.0；今日实测，非文档复述）
**评估焦点**：科学先进性内核质量、距 SCI 投稿的真实距离、逐项达标方案与验收标准

---

## 一、结论摘要

> ### SCI 判定
>
> **当前不可投 SCI；达到档 1 投稿线的路径明确且全部无人类受试者伦理门槛：口径修复（1 周）+ 地基（1–2 周）+ 科学增益（4–6 周，主体是专家协调）**。medRxiv 预印本本周即可投（只差 ORCID）。
>
> **本报告核心论点：本项目当前处在"测量工具开发"的科学阶段，却按"框架描述"的范式写作。** SCI 方法学论文验收的是工具开发五步——条目生成 → **专家内容效度** → **信度** → 结构效度 → 效标效度。项目有第 1 步和半个第 4 步（in-silico 检验），**缺的第 2、3 步恰好不需要人体试验，4–6 周可补**。补上之后，"自证"变"他证"，档 1 期刊的方法学门槛即达标。

### 与 10-16 报告的差异

10-16 报告给出"6 项硬阻断"的清单；本轮**逐项复验：一项未动**（ORCID 仍 PENDING、manifest 仍 491 tests、E/G 仍共线、迁移仍 6 个、仍无 lock）。因此本报告不再重复罗列，转向两个新问题：**(a) 科学内核到底站不站得住（深挖）；(b) 用什么范式把论文送到 SCI 线**。

### 本轮科学审计最关键发现

| # | 发现 | 严重度 |
|---|---|---|
| S1 | 论文 §3 标题 "**Ten** Steady-State Biology Axes" 且表格列出 I/J 两轴的"代表性证据"；摘要却说 "eight (A–H), I/J not implemented"；line 123 第三套说法"I/J added after initial validation"。**打分器只实现 A–H——论文三个口径互相矛盾，且对实现 over-claim** | 🔴 |
| S2 | "approximately 97% supported by human or RCT-level (L1 plus L2)"：L2 的自身定义是"单人体 RCT **或强机制+动物**"——把动物/机制证据算进"human or RCT-level" | 🟡 |
| S3 | "收敛效度 70%"实测是**作者自编码关键词匹配**（引擎输出 ∩ 中医预期词表）——这是 content validity 自证，不是 convergent validity（后者需与同构念的独立测量相关） | 🟡 |
| S4 | manifest 称 "calibration bands"，实现是耦合系数 ±20% + 依从性 0.85–1.0 的 bootstrap 带宽 = **先验不确定性传播，不是 empirical calibration**（需真实结局数据） | 🟡 |
| S5 | 验证电池 20 弱轴画像 + 2 对照**全部由作者构造**（pair 自选、无预注册） | 🟢 已部分披露 |
| S6 | **零信度证据**：固定阈值打分器无 test-retest / 输入扰动稳定性量化——工具开发论文的必填项 | 🟡 |

**同时确认站得住的内核**：E-value 与 VanderWeele & Ding (2017) 公式精确一致（含负效应 abs、零效应报错、溢出保护）；数据冻结机制（BASELINE.json + git commit + CI diff）真实有效；证据分级 L1–L4 定义文档化；因果四件套附"耦合系数尚未被因果识别"的诚实免责；对照画像 0 推荐的特异性证伪测试成立；rubric 200 条 5 类均衡。

---

## 二、科学先进性内核审计（实测证据）

### 2.1 站得住的部分（正面清单）

1. **E-value 实现引用级正确**
   `RR = exp(|estimate|)`，`E = RR + sqrt(RR×(RR−1))`，负效应取 abs、零效应抛 `ValueError`、`exp` 上限 30 防溢出——与 VanderWeele & Ding 2017 一致。
2. **论文-代码数字桥已建成**：论文"Data freeze note"指明数字源自 commit `7b75e9a` 的 BASELINE.json，且"未来脚本或案例库变更触发 CI 基线 diff 需人工确认"——10-12 的 N2 硬阻断修复是真实的。
3. **证据分级有定义**：L1 = ≥2 项独立人体 RCT/试验一致；L2 = 单人体 RCT 或强机制+动物；L3 = 体外/观察/古籍；L4 = 假说（不进推荐）。数据库自带版本号 v1.3。
4. **因果推演诚实**：`causal_report()` 返回 scm/counterfactual/calibration/sensitivity + `not_clinical` + 免责明示"耦合系数尚未被因果识别，效应须经前瞻队列验证"。
5. **有真证伪测试**：对照画像（无弱轴）推荐数 = 0，证明交叉逻辑响应真实输入而非滥发。
6. **rubric 基准设计均衡**：200 条 = 5 类 × 40（axes_interpretation / tcm_terminology / claims_boundary / critical_values / uncertainty_expression）。

### 2.2 科学性问题（按严重度排序，均附修复方案）

**S1｜轴数三套口径 + 对实现 over-claim（🔴 必改）**

| 位置 | 说法 |
|---|---|
| §3 标题与表格 | "Ten Steady-State Biology Axes"，列出 I（外泌体）/J（再生医学）及证据（UPenn OSKM mRNA-LNP、siRNA-RIVER） |
| 摘要 | "eight-axis mapping (A–H) is constructed（axes I/J reserved for future extension, **not implemented**）" |
| §6 line 123 | "Axes I and J were **added after initial validation** and require independent computational validation" |
| 代码 | `axis_scorers` 仅 A–H |

四种表述互相矛盾；审稿人对照软件即发现论文含未实现的轴。**修复**：§3 拆为"Implemented axes (A–H)"表 + "Reserved axes (I–J, not implemented)"小表（删证据列）；line 123 改为"Axes I–J were reserved after initial validation of A–H and are not implemented in the current engine"；摘要不动。

**S2｜证据分级宣称越级（🟡）**
论文称推荐池"约 97% 由 human or RCT-level（L1+L2）支持"，但 L2 含动物/强机制。**修复**：改为"supported by human-trial evidence (L1) or single-trial/strong-mechanism evidence (L2)"——一字不改事实，只改口径诚实度。

**S3｜"收敛效度"概念误用（🟡）**
`tools/engine_validation.py` 的 convergent_validity_rate = 引擎输出与中医领域预期关键词的匹配率，**词表由作者自编码**。心理测量学中 convergent validity 需与同构念的独立测量相关；此为 content validity 的自证 proxy。**修复**：全文改名 "domain-expectation concordance"，在方法节披露"关键词表由作者依据领域知识编码，未经独立 elicitation，属内容效度的探索性证据"。

**S4｜"calibration bands"名不副实（🟡）**
实现 = bootstrap(耦合 ±20%, 依从性 0.85–1.0)，是**先验不确定性传播**；empirical calibration 需真实结局。manife st 摘要用词超标。**修复**：manifest 改 "prior uncertainty bands"；论文如描述该模块须注明是先验带宽。

**S5｜验证电池自证（🟢，管理性）**
画像由作者构造。已有 mitigation：随机种子 20260818 固定、`engine_validation_metrics.json` 可复现、2 对照画像做证伪。**修复**：limitation 明示"profile battery is author-constructed and not pre-registered"，并在 Zenodo 数据集中附画像生成脚本（已有，随 DOI 发布）。

**S6｜零信度证据（🟡，可计算补齐）**
固定阈值打分器无任何信度量化。工具开发论文的必填项。**修复（纯计算，无受试者）**：对 120 条案例的指标值做 ±5% 输入扰动 bootstrap（n=1000），报告八轴分的 ICC(2,1) 或加权 Kappa；若某轴信度低（预期 E/G，因其共线），如实报告并成为 H5 解耦的科学理由。

### 2.3 范式错配：为什么现在是"工具开发"而不是"框架论文"

| 工具开发五步（SCI 方法学范式） | 本项目现状 |
|---|---|
| 1. 条目/轴生成 | ✅ 八轴 + 通路 + 古籍映射（四向表） |
| 2. **专家内容效度** | ❌ 论文自己写在 limitations："needs further calibration by independent expert Delphi and quantitative text mining"——**把 future work 写进了论文，而不是做掉它** |
| 3. **信度** | ❌ 无（S6） |
| 4. 结构效度 | 🟡 in-silico 轴激活/特异性（自证 Battery） |
| 5. 效标效度 | ❌ 无外部效标（n-of-1 数据回流后可得） |

**结论：把第 2、3 步做掉，论文从"又一个框架"变成"一个经内容效度与信度检验的计算工具"——这正是 integrative medicine 与 digital medicine 方法学期刊愿意发、且竞品（Function/Neko/Tiny Health）没有的东西。**

---

## 三、SCI 阶段定义与目标梯度

"达到 SCI 阶段"的操作性定义（Definition of Done）：

1. **可独立复现**：审稿人从干净 checkout 出发 `docker compose up` 能跑通注册与核心端点（H1）且依赖可锁定（H2）
2. **口径零矛盾**：轴数、证据分级、指标口径在论文/manifest/代码三处一致（S1–S4、H3、H4）
3. **引用可核验**：DOI 全过 Crossref（已达成）且无过度归因（S2）
4. **效度有第三方成分**：专家内容效度（CVI）+ 信度量化（I1/I2）
5. **不越权宣称**：wellness 定位 + 五法域 claims 过滤在文中可验证

| 档 | 目标 | 性质 | 费用 | 状态 |
|---|---|---|---|---|
| 0 | medRxiv 预印本 | 时间戳占位 | 免费 | **本周可投（补 ORCID）** |
| 1 | 整合医学方法学 Q1（JIM / European J of Integrative Medicine / IMR 一类） | Methodology/Instrument | 需官网复核（既往轮次核到 JIM ~IF5.2、IMR APC 全免，**投稿前复核**） | 4–6 周 |
| 1' | npj Digital Medicine / JMIR（数字医学方法学/数据论文） | 影响因子更高，APC 较高 | 高 | 同 4–6 周可试 |
| 2 | Ageing Research Reviews（综述）/ 高分数据论文 | 需真实数据或系统工作 | — | n-of-1 数据后 |
| — | 纲要中的 *Nature Medicine* RCT 一栏 | **长期项，明确降级** | — | 资源不匹配 |

---

## 四、提升方案（三组，均含验收标准）

### A 组：口径修复（1 周，纯文本/配置，零技术风险）

| # | 动作 | 验收标准 |
|---|---|---|
| A1 | §3 轴数三处统一（S1） | 全文检索 "ten axis"/"I/J" 只剩"reserved, not implemented"一种口径 |
| A2 | 证据分级宣称降档（S2） | 论文无 "human or RCT-level" 表述 L2 |
| A3 | "收敛效度"→"domain-expectation concordance" + 披露自编码（S3） | 论文与 `engine_validation.py` 输出术语一致 |
| A4 | manifest "calibration bands"→"prior uncertainty bands"（S4） | manifest 与代码免责语一致 |
| A5 | manifest 数字对齐：491→实跑通过数、DOI 22、ORCID 填写（H3/H4） | manifest 与实际三项零偏差 |
| A6 | 频率疗法曲目残留暗示经 claims 引擎实测拦截或删除 | 频率页输出过一遍 claims_engine 有记录 |

### B 组：地基（1–2 周，见 10-16 报告 D0–D2）

| # | 动作 | 验收标准 |
|---|---|---|
| B1 | `tests/test_schema_parity.py` + 补齐 37 表迁移（H1） | 干净空库 `alembic upgrade head` → 注册/建 study 通过；CI 含 alembic 步骤 |
| B2 | 依赖锁定 constraints（H2） | 两次安装产物哈希一致；Zenodo "reproducible" 承诺成立 |
| B3 | E/G 满分解耦（H5） | `hrv=45` 时 E≠G；G 轴引入第二主输入（如睡眠midpoint/EEG 代理） |

### C 组：科学增益（4–6 周，把自证变他证）

| # | 动作 | 成本 | 验收标准 |
|---|---|---|---|
| C1 | **专家内容效度 mini-Delphi**：5–8 位中医专家对 A–H 映射（经典概念↔通路↔轴）独立评分，算 I-CVI/S-CVI | 3–5 周（协调为主） | S-CVI ≥0.90 或如实报告低 CVI 的轴；论文新增 "Expert content validity" 一节——**这是单项最大增益** |
| C2 | **信度量化**：输入扰动 bootstrap（±5%, n=1000）出 ICC/Kappa（S6） | 2–3 天（纯计算） | 八轴信度表进论文；E/G 低信度成为 B3 的科学依据 |
| C3 | **n-of-1 自追踪启动**：一台穿戴设备 8–12 周个人纵向 | 8–12 周（并行） | 至少一条轴的前后对比 + 效应量；为档 2 与"耦合系数标定"供首批真实数据 |
| C4 | 画像电池 + 验证数据集上 Zenodo 铸 DOI | 1 天 | DOI 可引用；data availability 落地 |

**优先级**：B1 > A5 > C1 > B2 > C2 > C4 > A1–A4 > C3（C3 最早启动但最晚出数）。

---

## 五、路线图

```
第 1 周    A 组全部 + B1/B2 → CI 全绿、干净 checkout 复现通过、口径统一
第 1 周    medRxiv 投出（ORCID + manifest 对齐后）——先占时间戳
第 2-3 周  C1（专家 Delphi 进行中）+ C2（信度表）+ C4（Zenodo DOI）
第 4 周    论文补 "Validity and Reliability" 一节（C1/C2 结果）
第 4-6 周  档 1 期刊投稿（Definition of Done 五项全过）
第 6-12 周 C3 数据回流 → 耦合系数首轮标定 + 档 2 冲刺
```

---

## 六、最终判定

> **未达到 SCI 论文阶段。达成条件明确：A 组（口径）+ B 组（复现地基）+ C1/C2（专家内容效度与信度）= 档 1 投稿线，预计 4–6 周（瓶颈是专家协调，不是代码）。**
>
> 分水岭只有一条：**论文里不能再出现"作者说自己对"的指标**。S3（收敛效度）和 S5（自证电池）现在的形态是"作者编码的词表与作者构造的画像互相印证"——这在任何一本 SCI 方法学期刊的评审眼里都是 content validity 都谈不上的自证。C1（独立专家 CVI）就是把这个结构性弱点翻转成论文最强一节的那一步，且论文作者自己早已在 limitations 里指认了这条路。
>
- 本周立刻可做：填 ORCID 投 medRxiv；A1/A2/A3/A4 纯文本修复；B1 建 parity 测试
- 明确不做：不追纲要里的 Nature Medicine RCT；不自建文本挖掘替代专家 Delphi（先做专家）；不把 E-value 当干预效力证据；不进 C 端获客竞赛

---

## 附：本轮复验命令索引

```bash
# 轴数口径三处矛盾
grep -n "Ten Steady-State\|eight-axis mapping\|added after initial validation" HealthLens_论文_英文版_全文.md
# E-value 公式
python -c "import inspect; from app.lib import nof_one_effect as ne; print(inspect.getsource(ne.compute_evalue))"
# 收敛效度实测定义
grep -n "convergent" tools/engine_validation.py && sed -n '123,169p' tools/engine_validation.py
# 校准带性质
grep -n "calibrat" app/lib/causal_simulator.py   # ±20% 耦合 + 0.85-1.0 依从性 bootstrap
# 阻塞项未动复验
ls tests/test_schema_parity.py 2>/dev/null; ls *.lock 2>/dev/null; grep -o "491 automated tests" submissions/medrxiv/submission_manifest.json
score_all_axes(wearable={'hrv_rmssd':45})  # E=G=100.0 仍共线
```

**本轮对仓库零源码改动**，仅读取与外部核验。
