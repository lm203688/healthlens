# HealthLens SCI 就绪度复评（第二轮）

**评估日期**：2026-10-19 05:42（基线：HEAD = 6f64019，工作区干净）
**评估焦点**：10-18 报告的 D 组方案执行后，是否达到 SCI 论文要求；给出评价结果
**方法**：全部实测——论文逐节比对、测试套件完整实跑（3m24s）、关键 artifact 运行时核验、论文-数据-产物三方一致性比对

---

## 一、总体评价结果

> ### SCI 判定：**仍未达到投稿线，但剩余差距从"周级"缩短到"天级 + 一个周级动作"。**
>
> 10-18 报告后一天内，用户完成了 D1（S7 证据库口径修复）、D2 大部分（CI 修复）、D3（信度进论文），并新增因果 E2E 管线、模型卡/系统卡、Zenodo 上传载荷、投稿信——**工程与科学内核的进步是真实的**。但本轮复检在**提交包（submission package）层面**发现 5 个新的、可被编辑/审稿人直接抓到的一致性问题，其中 2 个属于"论文陈述与 tracked artifact 不符"（因果 E2E 数字），1 个属于"图与正文矛盾"（Figure 1 仍是十轴图）。**这些不是科学内核缺陷，但在投稿仪式上是致命的。**
>
> **达到档 1 投稿线的剩余工作**：
> ① 提交包一致性问题（约 3–5 天，纯文本/图表/数据工作，零伦理门槛）
> ② 用户操作（ORCID、电话、字数——约 10 分钟）
> ③ **专家内容效度 CVI（3–5 周，唯一实质科学门槛，10-18 已判定、本轮仍未动）**

### 与 10-18 判定对比

| 维度 | 10-18 复评 | 本轮（10-19） |
|---|---|---|
| S7 证据库口径 | 🔴 论文 over-claim | ✅ **已修复且质量高**（S 类分离、L1 覆盖 95%→75% 重算、池分布 154→127 诚实解释） |
| CI/测试 | 🔴 5 failed | 🟡 2 failed（收敛中，但 manifest 数字第三次不符） |
| E/G 共线 | ✅ 已修复 | ✅ 保持修复（论文 §6.1(iii) 有诚实说明） |
| 信度 | 🟡 有数据未进论文 | ✅ 进论文（§6.1 + Table 2 + 5 条 caveat） |
| 因果层 | 仅 SCM + E-value | ✅ E2E 管线可跑（但论文数字与产物不符） |
| 专家 CVI | 🔴 未做 | 🔴 **仍未做**（档 1 唯一实质门槛） |
| 提交包一致性 | 未查 | 🔴 **新暴露 5 项**（本节三） |

---

## 二、已完成的项（实测确认）

| 项 | 证据 |
|---|---|
| D1 S7 修复 | §5 改名 "Case Evidence Library: Stratified by Verification Status"；摘要重写为 "15 human-trial or classical entries with L1–L3, 14 unverified normalized to L3, 91 synthetic separated into a distinct S class"；48 条合成 L1 归一化为 S 类（权重 0.5）；正文显式声明 "L1 by definition cannot be synthetic" |
| 头条指标重算 | `engine_validation_metrics.json`：coverage_L1 **0.75**（原 0.95）、domain_expectation_concordance **0.879**、池 n=127（原 154）、L1 占比 22%（原 87%）——与论文 Table 1 逐项一致 |
| D2 | 008 migration downgrade 修复（51 passed）；C7 审计启发式修复（50 passed）；agent-card 9,176B（距 10KB 上限 1KB 余量，昨日的 73B 脆弱点解除） |
| D3 信度进论文 | §6.1 "Computational Reliability (Input-Perturbation Bootstrap)"：ICC(2,1) 八轴 + Fisher-Z CI + 加权 κ 表；caveat 明示 "computational reliability, NOT test-retest"、"E/G 非重叠输入域"、"18 画像作者构造未预注册" |
| checklist 自审计 | `tools/checklist_audit.py` 52 项（DECIDE-AI/TRIPOD-AI/SPIRIT-AI）实测 48S/4P/0M = 96.2%，产物 `data/CHECKLIST_COMPLIANCE_REPORT.md` |
| 因果 E2E | `tools/causal_end_to_end.py` 实跑通过：SCM → ATT+CI → E-value → 三反驳器，单命令可复现（seed 20261018）；E-value=1.8382，CI 不跨零 |
| 模型卡/系统卡 | `docs/model_card.md`（Mitchell 2019 模板）、`docs/system_card.md`（ISO/IEC 5259 + OWASP AI Security），诚实标注 "no trained ML model, no learned weights" |
| Zenodo 载荷 | `tools/zenodo_deposit_payload.py` 生成 44 文件 payload + files_manifest.csv + sha256；投稿信（JIM 定向 Hypothesis/Framework 栏）就绪 |
| 测试总量 | 1,846 passed / 12 skipped（1860 collected） |

---

## 三、本轮新发现问题（按严重度）

### N1 🔴 manifest 测试数第三次不符（A5'' 复发 ×3）

- manifest：**"All 1840 automated tests pass"**
- 实测：**1,846 passed / 2 failed / 12 skipped**
- 失败项：`tests/tools/test_fill_placeholders.py` ×2——IMR 投稿包残留 4 个占位符（`{{YOUR_ORCID_ID}}`×2、`{{YOUR_PHONE}}`、`{{WORD_COUNT}}`）使 `--check` 退出码 1。其中 ORCID/电话属用户信息（合理待填），但 **WORD_COUNT 应可自动生成**（工具目前不填）。
- 判定：数字必须由 CI 实跑注入 manifest，手写必然再次漂移。

### N2 🔴 论文因果 E2E 数字与 tracked artifact 不符

| 项 | 论文 §7 陈述 | `data/causal_end_to_end.json` 实际 |
|---|---|---|
| 样本量 | 400 individuals | **100** |
| bootstrap | n_boot = 10,000 | **2,000** |
| ATT | −0.251 [−0.312, −0.191] | **−0.2331 [−0.359, −0.1081]** |
| E-value | 1.89 | **1.8382** |

根因：`tests/tools/test_causal_end_to_end.py::_run()` 用 `--n-bootstrap 2000 --n-individuals 100`（测试加速）**覆写了 tracked 的 `data/causal_end_to_end.json`**——测试污染真 artifact。审稿人跑默认参数（400/10000）会得到另一组数字，跑测试后 artifact 变成第三组。

### N3 🔴 论文未披露反驳电池失败

`refutation.all_passed = False`：data_subset_refuter 未过（50% 子样本效应 2.100 不被原 CI [2.60, 3.20] 覆盖，Δ=1.0 超阈值）。报告 MD 如实列出 "All refuters passed: False"，但论文 §7 只写 "refutes the estimate with three standard refuters"，未提一个未过。**引用具体 ATT/CI/E-value 却隐去失败的稳健性检验，是审稿人可以复现抓到的。**

### N4 🔴 Figure 1 仍是十轴图（S1 遗留复活）

`HealthLens_论文_框架概念图_Figure1.svg` 含 "Ten Axioms, Ten Axes" / "Ten-axis pathway weakness scores" / "Ten-Axis Mapping"；IMR 投稿包内 `Figure1_Ten_Axis_Framework.eps/.png` 同源。论文正文已改八轴（A–H，I/J reserved），**图与正文直接矛盾**；且 "Ten Axioms" 与论文 "Six paradigm axioms" 矛盾。

### N5 🟡 model_card.md 数据错误

"120-entry evidence DB (**29 verified** + 91 synthetic)"——与事实（**7 verified + 8 classical + 14 unverified + 91 synthetic**）不符，是 10-18 之前的旧口径残留；卡片版本 v0.30.0 落后于项目 0.31.0。

### N6 🟡 cover letter 引用错误

"7 Crossref-verified human-trial or classical-experience entries (including **the 2026 AFFIRM Phase II senolytics RCT**)"——两处错：(a) "AFFIRM" 正是 10-13 抓出的**幻觉试验名**（DOI 10.1038/s41591-026-04102-8 不存在），真实引用已更正为 Farr 2024 Nat Med；(b) CASE-006（该 RCT）现状是 `unverified_no_publication`，不属 7 条 verified。cover letter 把已更正的幻觉名又带回了提交包。

### N7 🟡 数据冻结注释 SHA 过期

论文 freeze note 仍引 commit `7b75e9a`；实际指标来自 `a9d916a`（`BASELINE.json` 的 git_sha 与 _meta 均为 a9d916a，数字与论文一致）。note 的 SHA 未随重跑更新。

### N8 🟡 专家 CVI 仍未启动；checklist 96.2% 是关键词扫描

- D4（原定义：专家 mini-Delphi）未动，limitations 仍写 "needs further calibration by independent expert Delphi"。
- 现有 checklist_audit 96.2% 是**关键词证据扫描**（工具自述 "keyword-evidence scan"），部分 "Satisfied" 项的证据片段与条目实际要求并不对应（如 D2 证据是一句 convergent-validity 免责声明）。它是完整性清单，不构成合规证明。

---

## 四、贡献度与分级（维持 10-18 框架，微调）

| 维度 | 10-18 | 本轮 | 说明 |
|---|---|---|---|
| 新颖性 | 7/10 | 7/10 | 无同构竞品判断不变 |
| 严谨性 | 5.5/10 | **6/10** | D1/D3 真实提升；N1–N3/N6 是提交包严谨性问题，扣分有限但刺眼 |
| 完整性 | 6/10 | **6.5/10** | +因果 E2E/+模型卡/+checklist；−Figure/CVI |
| 可复现性 | 8.5/10 | **7.5/10** | N2 测试覆写 artifact 是复现性倒退（跑过测试的 checkout ≠ 论文数字） |
| 影响力潜力 | 6.5/10 | 6.5/10 | 待真实数据点火 |

---

## 五、结论与剩余路径

**评价结果：未达到 SCI 论文要求。** 科学内核（八轴、S 类分级、E-value、计算信度、诚实的 in-silico 边界）已经达到方法学工具论文的内核标准；但当前提交包存在 6 个可被编辑/审稿人直接核验的一致性问题（N1–N6），且第 4 步科学验证（专家 CVI）仍空缺。

**修复清单（按优先级，全部无人类受试者伦理门槛）：**

| # | 动作 | 工作量 |
|---|---|---|
| R1 | Figure 1 重绘为八轴（A–H）+ reserved I/J 小表，更新 IMR 包 eps/png 文件名 | 1–2 天 |
| R2 | 因果 E2E：用默认参数（400/10000）重跑并重提交 JSON；测试改为写 tmp 副本**禁止覆写 tracked artifact**；论文更新 ATT/CI/E-value；**补充 data_subset_refuter 未过的事实及含义** | 1 天 |
| R3 | model_card.md 修正 "29 verified" → 真实分层；版本升 0.31.0；cover letter 删 "2026 AFFIRM" 改 Farr 2024 并修正 verified 分类 | 0.5 天 |
| R4 | manifest 测试数改由 CI 实跑注入；`fill_placeholders.py` 支持自动 WORD_COUNT（或从投稿步骤中移除该占位符） | 0.5 天 |
| R5 | freeze note SHA：7b75e9a → a9d916a（或最新 baseline） | 5 分钟 |
| R6 | **专家 mini-Delphi 算 CVI**（档 1 唯一实质门槛，用户协调 5–8 位中医专家） | 3–5 周 |
| R7 | 用户操作：填 ORCID（medRxiv/IMR/medRxiv cover letter）、电话；Zenodo token 上传铸 DOI | 10 分钟 |

**判定摘要**：R1–R5（约 3–4 天）完成后，提交包达到"编辑级诚实"；R1–R5 + R6 完成后，达到档 1 整合医学方法学刊（JIM/EJIM/IMR）投稿线；R7 完成后 medRxiv 可先占时间戳。**当前不可投——不是内核不行，是包裹不诚实。**

---

## 附：本轮复验命令索引

```bash
# S7 修复确认
grep -n "Stratified by Verification Status\|S class\|75% weakness-profile L1" HealthLens_论文_英文版_全文.md

# N1 manifest vs 实测
grep -o "All [0-9]* automated tests pass" submissions/medrxiv/submission_manifest.json   # 1840
python -m pytest tests/ -q --no-header -p no:cacheprovider 2>&1 | tail -3                # 1846 passed / 2 failed

# N2/N3 因果 E2E 数字
python tools/causal_end_to_end.py --json-only | python -c "import json,sys; d=json.load(sys.stdin); print(d['att'], d['evalue'], d['refutation']['all_passed'])"  # n=100/2000 → ATT -0.2331, E 1.8382, all_passed False
grep -n "400 simulated individuals\|ATT = -0.251" HealthLens_论文_英文版_全文.md        # 论文陈述

# N4 Figure1 十轴残留
grep -c "Ten" HealthLens_论文_框架概念图_Figure1.svg   # 8+ 处

# N5/N6 model card / cover letter
grep -n "29 verified" docs/model_card.md
grep -n "AFFIRM" HealthLens_论文_投稿信_cover_letter.md

# N7 freeze note SHA
grep -n "Data freeze note" -A 2 HealthLens_论文_英文版_全文.md                            # 7b75e9a（过期）
python -c "import json; print(json.load(open('validation_snapshots/BASELINE.json'))['_meta'])"  # a9d916a

# D2/D3 已修复项
python -m pytest tests/test_federated_migration.py tests/protocol/test_a2a_contract.py -q  # 全绿
python tools/checklist_audit.py   # 48S/4P/0M 96.2%
```
