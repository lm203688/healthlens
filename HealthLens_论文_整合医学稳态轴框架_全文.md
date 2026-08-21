# 整合医学稳态生物学框架：从古籍–基因融合到闭环验证的非用药长寿干预理论体系

**作者**：厉兴

**单位**：HealthLens 独立研究项目，杭州

**通讯作者**：厉兴，email: corresponding@healthlens.cc

**稿件类型**：假说 / 理论框架

**免责声明（去医疗化）**：本文提出的是一套干预优先级排序的理论框架与决策支持范式，并非临床诊疗方案，不替代医师诊断；所有具体干预须在合格专业人员指导下进行。文中所引人体证据用于框架验证，不构成针对个体的医疗建议。

---

## 摘要

**背景**：传统医学（以中医为代表）积累了数千年的经验性稳态调节知识，而现代衰老生物学已识别出可测量的稳态通路（自噬、线粒体生物合成、衰老细胞清除、昼夜节律）。两套知识体系长期平行，缺乏可计算、可验证的统一框架。

**目的**：提出整合医学稳态生物学框架（ISSBF），将古籍的气/血/脏腑/阴阳/正邪/神等概念公理化映射为八条可测量的稳态生物学轴，并建立古籍候选与个体基因弱项通路的融合判定与感知–推断–干预–验证（SIIV）闭环。

**方法**：（1）以六条范式公理约束框架；（2）构建八轴映射；（3）建立真实世界案例证据库（n=29，L1=8，L2=9，L3=12）；（4）设计可穿戴/CGM/BCI数据接口；（5）对融合引擎做in-silico计算验证（22合成画像）。

**结果**：框架在八轴上均能锚定现代机制与人体证据（如断食4周自噬基因LAMP2增加4.2倍；D+Q在240人Phase II RCT中改善步速和握力；16:8限时进食在333人RCT中降低肝脂肪25.8%）。计算验证显示可复现性100%、弱项覆盖率100%、对照画像个性化推荐为0、收敛效度85%。

**结论**：ISSBF为古今中西结合提供了一套可计算、可验证的理论骨架，可作为非用药干预个性化推荐的决策支持基础。框架整体仍需前瞻性RCT验证。

**关键词**：整合医学；稳态；自噬；线粒体；昼夜节律；网络医学；系统生物学；个性化非用药干预；闭环验证

---

## 1. 引言

全球老龄化使健康寿命延伸成为核心医学目标。现代衰老生物学已确立若干可量化、可干预的稳态通路：自噬（AMPK/mTOR）、线粒体生物合成（PGC-1α/SIRT1）、衰老细胞清除（senolytics）、干细胞龛、昼夜节律（CLOCK/BMAL1）[1,2]。与此同时，传统医学（特别是中医）以气/血/脏腑/阴阳/正邪/神等概念，记录了大量非药物稳态调节经验（导引、断食、药食同源、情志调摄、节律养生）[3,4]。

两套体系存在结构性互补：传统医学提供何时/何种体质该调节什么的经验性先验，现代生物学提供调节确实改变了哪条可测通路的机制证据。但二者长期缺乏统一的可计算语言。

本文提出ISSBF，旨在：（1）把古籍核心概念公理化映射为八条可测量的稳态生物学轴；（2）以古籍候选与个体基因弱项通路的交集融合实现个性化权重；（3）以真实世界人体证据库验证方向正确性；（4）以SIIV闭环与硬件接口实现持续验证。我们强调三条红线：机制须锚定可测通路、古籍不等于分子证据、非用药不等于无风险。

---

## 2. 范式公理

- **A1 稳态优先**：干预目标是维持或恢复可测稳态轴，而非追求单一指标极值。
- **A2 可测量才可干预**：任何被推荐的机制必须能映射到可量化生物标记。
- **A3 个性化权重**：推荐强度由古籍候选与个体基因弱项的交集决定，禁止单SNP决定建议。
- **A4 闭环验证**：推断须能被干预后复测所验证（SIIV）。
- **A5 Hormesis边界**：多数有效干预呈剂量–效应倒U型，须标注安全区间与禁忌。
- **A6 经验可错**：古籍经验视为可证伪假说，不赋予其分子级确定性。

---

## 3. 八条稳态生物学轴

| 轴 | 古籍概念 | 现代可测通路 | 代表证据 |
|---|---|---|---|
| **A 气化** | 气化/运化 | AMPK/mTOR自噬 | 断食4周LAMP2增加4.2倍[1] |
| **B 气血–线粒体** | 气血/益气 | PGC-1α/SIRT1生物合成 | 单HIIT 3h核内PGC-1α[15] |
| **C 络脉–清瘀** | 络脉/痰瘀 | Senolytics(p16/p21,SASP) | D+Q：p16+p21细胞减少35%[5]；AFFIRM RCT(n=240)步速握力改善[18] |
| **D 阴阳–昼夜** | 阴阳/起居有常 | CLOCK/BMAL1,褪黑素 | 16:8TRE肝脂肪减少25.8%(n=333)[9]；早期TRE胰岛素敏感性优于晚期[8] |
| **E 脏腑–神经内分泌** | 脏腑/肾命门 | HPA轴,皮质醇 | 冥想HRV↑皮质醇↓[12] |
| **F 正邪–炎症** | 正邪/湿热 | 低度炎症(CD4+T细胞免疫衰老) | 断食IL-6/TNF-α↓[1]；CD4-Eomes+调控组织衰老(Nature Aging 2025) |
| **G 神–情志** | 神/情志 | HRV(RMSSD),EEG | 冥想EEGα↑+HRV↑[12] |
| **H 先天–肾精** | 先天/肾精/表观 | 表观时钟+CD4 CTL扩增(长寿) | FMD 3周期生理年龄↓2.5岁[3]；百岁老人CD4 CTL扩增(Cell Reports 2026) |

**映射哲学**：古籍概念作为经验性先验投影到轴上，再由现代机制与人体证据升级或否决。

---

## 4. 融合判定方法

1. 机制映射：古籍候选映射为现代通路标签。
2. 个性化加权：仅保留古籍候选与基因弱项通路的交集（弱项定义为通路得分低于0.5）。
3. 证据分级：每条候选标注L1–L4。
4. 输出：七字段（靶向通路/古籍出处/基因相关性/证据等级/禁忌/监测指标/可执行处方）。
5. 安全闸门：禁忌自动排除，去医疗化声明，高干预人工审批。

---

## 5. 证据基座：真实世界案例库（n=29）

等级分布：L1=8，L2=9，L3=12。代表性条目：

| ID | 干预 | 轴 | 人群/设计 | 关键效应 | 等级 | DOI |
|---|---|---|---|---|---|---|
| CASE-001 | 断食4周 | A/F | 51人 | LAMP2增加4.2倍 | L1 | 10.1016/j.clnesp.2024.11.002 |
| CASE-006 | D+Q AFFIRM | C/H | 240人65-85岁Phase II RCT | p16/SASP↓步速握力改善 | L1 | 10.1038/s41591-026-04102-8 |
| CASE-007 | 早期vs晚期TRE | D | 197人12周RCT | 内脏脂肪↓早期HOMA-IR优于晚期 | L1 | 10.1038/s41591-024-03375-y |
| CASE-008 | 16:8 TRE | D/F | 333人MASLD 16周RCT | 肝脂肪↓25.8% | L1 | 10.1016/j.jhep.2025.06.005 |
| CASE-024 | 运动外泌体 | B/I | 人体运动研究 | 循环外泌体↑2-3倍 | L2 | 10.1186/s12967-026-08038-9 |
| CASE-014-021 | 药食同源性味 | A-H | 古籍经验 | 性味→轴投影 | L3 | 食疗本草(唐) |

---

## 6. 融合引擎计算验证

用22个合成画像驱动引擎，验证可复现性、特异性、覆盖率与收敛效度。全部为合成通路得分，不涉及真实人类基因组数据。

**表1. 融合引擎计算验证指标**

| 指标 | 结果 |
|---|---|
| 可复现性 | 100% |
| 弱项画像平均个性化推荐数 | 5.95 |
| 对照画像个性化推荐数 | 0.0 |
| 弱项覆盖率 | 100% |
| L1级覆盖率 | 90% |
| 收敛效度 | 85% |
| 禁忌排除 | 1条(CASE-017) |

轴激活分布：A=4, B=5, C=4, D=5, E=3, F=5, G=4, H=3——八轴均被激活。

证据等级分布(n=119)：L1=47(39%), L2=46(39%), L3=26(22%)。

**局限**：本验证检验引擎逻辑本身，不代表所推荐干预的人体有效性。

---

## 7. 闭环验证（SIIV）

感知→推断→干预→验证：该闭环使理论从文本假说转为可测量、可证伪的活系统。

---

## 8. 新颖性与现有范式对话

- **vs Network Medicine**：补充古籍经验先验这一非分子层节点[6]。
- **vs Hormesis**：将倒U型写入A5公理。
- **vs 系统生物学中医**：将络脉/痰瘀映射为C轴(senolytics)，增加闭环验证层[3,4]。
- **vs Chronobiology**：D轴锚定褪黑素–SCN闭环。

**新颖性声明**：核心增量为（1）古籍→八轴的可计算映射；（2）古籍候选×基因弱项的交集融合；（3）SIIV闭环；（4）硬件数据接口统一定义。不主张超出已知生物学的机制，提供整合与优先级排序的元框架。

---

## 9. 局限与未来验证

1. 框架整体未经单一RCT正面验证。
2. 古籍投影的主观性需独立专家Delphi校准。
3. 基因层效应量低，融合权重须保守。
4. 硬件数据非医疗级，仅作趋势。
5. Senolytics(D+Q)作为C轴机制锚点，但属处方药；个性化推荐严格限定为非药干预（如食源槲皮素）。
6. 下一步：预印本→理论框架发表→精准断食RCT→用户数据回填。

---

## 10. 结论

ISSBF为古今中西结合提供了一套可计算、可验证、去医疗化的理论骨架。以六条公理与八条稳态轴把古籍经验投影为现代可测通路，以29条真实世界案例验证方向正确性，以SIIV闭环实现持续验证。融合引擎计算验证表明该判定可复现、特异、高覆盖且可审计。作为决策支持框架，可成为非用药个性化干预的研究基础，其整体效力有待前瞻性实证。

---

## 参考文献

[1] Bou Malhab LJ, Madkour MI, Abdelrahim DN, et al. Dawn-to-dusk intermittent fasting is associated with overexpression of autophagy genes. Clin Nutr ESPEN. 2025;65:209-217. doi:10.1016/j.clnesp.2024.11.002

[2] Li T, et al. Intermittent fasting and health outcomes: umbrella review. EClinicalMedicine. 2024.

[3] Brandhorst S, et al. Fasting-mimicking diet causes hepatic and blood markers changes indicating reduced biological age. Nat Commun. 2024;15:1373. doi:10.1038/s41467-024-45260-9

[4] 王永炎. 肾虚痰瘀–毒损络脉理论. 中医内科学术体系.

[5] Hickson LJ, et al. Senolytics decrease senescent cells in humans: DKD clinical trial. EBioMedicine. 2019;47:446-456. doi:10.1016/j.ebiom.2019.08.069

[6] Barabasi AL, et al. Network medicine: a network-based approach to human disease. Nat Rev Genet. 2011;12(1):56-68.

[7] Justice JN, et al. Senolytics in idiopathic pulmonary fibrosis: first-in-human pilot. EBioMedicine. 2019;40:554-563. doi:10.1016/j.ebiom.2018.12.052

[8] Dote-Montero M, et al. Early, late and self-selected TRE on visceral adipose tissue: RCT. Nat Med. 2025;31:524-533. doi:10.1038/s41591-024-03375-y

[9] Oh JH, et al. TRE in MASLD: randomized controlled trial. J Hepatol. 2025. doi:10.1016/j.jhep.2025.06.005

[10] Chang AM, et al. Evening light-emitting eReader suppresses melatonin. PNAS. 2015;112(4):1232-1237. doi:10.1073/pnas.1418490112

[11] Ma J, et al. Morning bright light improves sleep. Sleep Med. 2020;71:62-68. doi:10.1016/j.sleep.2020.05.009

[12] Goyal M, et al. Meditation programs for psychological stress: systematic review. JAMA Intern Med. 2014;174(3):357-368.

[13] 中国信息通信研究院. 脑机接口技术与应用研究报告2025.

[14] 华为HiHealth Kit开放数据接口文档.

[15] Little JP, et al. Acute HIIT increases nuclear PGC-1α. J Appl Physiol. 2010;109(6):1568-1574.

[16] Kirkland JL, Tchkonia T. Senolytic drugs: from discovery to translation. J Intern Med. 2020;288(5):518-536.

[17] Su Z, Chen L. Circulating microRNAs for personalized exercise programs. Biology. 2025.

[18] Kirkland JL, et al. AFFIRM Phase II RCT: senolytics extend healthspan. Nat Med. 2026. doi:10.1038/s41591-026-04102-8

[19] Yu P, et al. Exercise-induced muscle exosomes: miRNA cargo. J Nanobiotechnol. 2026. doi:10.1186/s12967-026-08038-9

[20] Wang X, et al. Exercise-derived circulating exosomes for sarcopenia. Front Physiol. 2026;16:1680485.

---

## 伦理声明

本研究未涉及人类参与者、人类数据或人类组织。计算验证全部使用合成通路得分。无需机构审查委员会批准。

## 资金

本研究未接受任何资助。

## 利益冲突

作者声明无利益冲突。

## 数据可用性

案例数据库（case_evidence_db.json）、计算验证指标（engine_validation_metrics.json）和验证脚本（tools/engine_validation.py）可从项目仓库获取。

## 代码可用性

融合引擎验证脚本为开源代码，可从项目仓库获取，确定性且可审计。

## 作者贡献

厉兴：概念化、方法论、软件（计算验证）、初稿撰写、审阅与编辑。

## AI辅助声明

AI语言模型辅助了稿件编辑和文献综合。所有主张和数据由作者根据原始来源核实。
