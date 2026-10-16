# HealthLens 案例库 DOI 富化报告（2026-10-16）

> 参考章节：`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §6（前瞻性队列 + 
> 预注册）与 §10 #5（案例库剩余 95 条补 DOI）。上一轮基线：
> `data/DOI_VERIFICATION_REPORT_2026-10-13.md`。

**核验方法**：所有新写入的 DOI 均通过 Crossref REST API 
`/works/<doi>` 单条解析二次验证（HTTP 200 + `status=ok` 才接受）。

## 一、本轮结果

- 案例总数：**120**
- ✅ 本轮新增 verified_crossref：**7**（新增/规范化 DOI）
- 📜 传统食疗条目（保留 traditional，不需 DOI）：**8**
- 🤖 验证夹具（保留 synthetic_validation）：**91**
- ⚠️ 未匹配文献（unverified_no_publication）：**14**

## 二、本轮新增 verified_crossref 清单

| Case | DOI | 期刊 | 年 | 标题 |
|---|---|---|---|---|
| CASE-004 | `10.1152/japplphysiol.01262.2011` | Journal of Applied Physiology | 2012 | Does SIRT1 determine exercise-induced skeletal muscle mitochondrial biogenesis:  |
| CASE-005 | `10.1016/j.ebiom.2019.08.069` | EBioMedicine | 2019 | Senolytics decrease senescent cells in humans: Preliminary report from a clinica |
| CASE-007 | `10.1038/s41591-024-03375-y` | Nature Medicine | 2025 | Effects of early, late and self-selected time-restricted eating on visceral adip |
| CASE-008 | `10.1016/j.jhep.2025.06.005` | Journal of Hepatology | 2025 | Efficacy and safety of time-restricted eating in metabolic dysfunction-associate |
| CASE-011 | `10.1016/j.ctcp.2016.03.007` | Complementary Therapies in Clinical Practice | 2016 | Effects of Tai Chi exercise on heart rate variability |
| CASE-024 | `10.1038/s41587-026-03231-z` | Nature Biotechnology | 2026 | High numerical aperture confocal volumetric mesoscope reveals mesoscale subcellu |
| CASE-029 | `10.1186/s12967-026-08038-9` | Journal of Translational Medicine | 2026 | Exercise-induced muscle exosomes: microRNA cargo as regulators of cardiovascular |

## 三、已 verified 但未走本轮 enrichment（先前工具确认，本轮保留）

| Case | DOI | 期刊 | 年 |
|---|---|---|---|

## 四、未匹配案例（需人工介入）

> 以下条目**未强行编造 DOI**。每条附检索关键词供 PubMed / Crossref 手工检索；如找到真实出版物，请以与本次一致的方法
> 补齐（写 DOI → 用 `tools/verify_evidence_dois.py` 反查 → 更新本表）。

### CASE-001
- **干预**：间歇性断食(IF) 4 周
- **原 source**：`{'journal': 'Clinical Nutrition ESPEN', 'year': 2024, 'doi': '10.1016/j.clnesp.2024.11.002'}`
- **effect_size**：LAMP2 上调 4.2 倍（强效应）
- **检索关键词**：
  - `间歇性断食(IF) 4 周`
  - `气化 / 脾运化（促运化、通腑）`
  - `AMPK↑ / mTOR↓ → 自噬流(autophagic flux)上调`
  - `LAMP2`
  - `LC3B`
  - `ATG5`
  - `AMPK_signaling`
  - `Autophagy`

### CASE-002
- **干预**：间歇性断食 vs 限时进食(TRF) 20 天
- **原 source**：`{'journal': 'Nutrients', 'year': 2024, 'doi': '10.3390/nu17101695'}`
- **effect_size**：组间差异偏向 TRF（非显著）
- **检索关键词**：
  - `间歇性断食 vs 限时进食(TRF) 20 天`
  - `气化 / 节律（子午流注雏形）`
  - `AMPK/mTOR 调控；进食窗口影响昼夜振幅`
  - `AMPK`
  - `mTOR`
  - `体成分/代谢`
  - `AMPK_signaling`
  - `Circadian`

### CASE-003
- **干预**：模拟禁食(FMD) 3 个月
- **原 source**：`{'journal': 'Nature Communications', 'year': 2024, 'doi': '10.1038/s41467-024-45260-9'}`
- **effect_size**：生理年龄下降 2.5 岁
- **检索关键词**：
  - `模拟禁食(FMD) 3 个月`
  - `辟谷 / 气化重启`
  - `周期性低热量触发自噬与表观重编程 → 生理年龄下降`
  - `表观遗传生理年龄`
  - `代谢标记`
  - `Autophagy`
  - `Epigenetic_clock`

### CASE-006
- **干预**：D+Q (dasatinib+quercetin) 间歇性 senolytic 给药 — Farr 2024 Phase II RCT
- **原 source**：`{'authors': 'Farr JN, Atkinson EJ, Khosla S, et al.', 'title': 'Effects of intermittent senolytic therapy on bone metabolism in postmenopausal women: a phase 2 randomized controlled trial', 'journal': 'Nature Medicine', 'year': 2024, 'doi': '10.1038/s41591-024-03096-2', 'note': "原幻觉 DOI 10.1038/s41591-026-04102-8（'AFFIRM' 试验）已替换为真实 Phase II RCT；真实结果为骨形成标志物早期升高、骨降解无明确改善（subtle），非功能改善。"}`
- **effect_size**：骨形成标志物早期升高、骨降解无明确改善（结果 subtle，假设生成性）；真实研究未报告步速/握力等功能改善。
- **检索关键词**：
  - `D+Q (dasatinib+quercetin) 间歇性 senolytic 给药 — Farr 2024 Phase II RCT`
  - `扶正祛瘀 / 延缓衰老`
  - `衰老细胞清除 → 骨代谢调节（真实结果：骨形成标志物早期升高、骨降解无明确改善）`
  - `骨形成标志物 P1NP`
  - `骨降解标志物 CTX`
  - `Senescence`
  - `Physical_function`

### CASE-009
- **干预**：16:8 限时进食 抗衰抗炎（协和/湘雅）
- **原 source**：`{'journal': '协和/湘雅 人体研究', 'year': 2024, 'doi': '2024 16+8 抗衰抗炎（投稿前需全文复核）'}`
- **effect_size**：抗炎抗衰趋势
- **检索关键词**：
  - `16:8 限时进食 抗衰抗炎（协和/湘雅）`
  - `节律养生 / 扶正`
  - `TRE 降低炎症与衰老相关标记`
  - `炎症标记`
  - `衰老相关标记`
  - `Inflammation`
  - `Senescence`

### CASE-010
- **干预**：连续血糖监测(CGM) 餐后暴露
- **原 source**：`{'journal': 'Cell Metabolism', 'year': 2024, 'doi': 'Cell Metabolism 2024 CGM 57人（投稿前需全文复核）'}`
- **effect_size**：96% 存在显著餐后高血糖
- **检索关键词**：
  - `连续血糖监测(CGM) 餐后暴露`
  - `气化失司 / 血糖波动（未病先防）`
  - `量化餐后血糖漂移 → 个体化饮食/进食窗口`
  - `餐后血糖 >140 mg/dL`
  - `Glucose_metabolism`

### CASE-012
- **干预**：冥想 / 呼吸训练（HRV、压力）
- **原 source**：`{'journal': '冥想 HRV/EEG 文献', 'year': 2021, 'doi': 'meditation HRV review（投稿前需全文复核）'}`
- **effect_size**：压力↓/HRV↑（中效应）
- **检索关键词**：
  - `冥想 / 呼吸训练（HRV、压力）`
  - `调息 / 安神 / 疏肝`
  - `迷走神经刺激 → HRV↑、HPA 轴下调、默认网络重调`
  - `HRV`
  - `感知压力`
  - `EEG α/θ`
  - `Vagal_tone`
  - `HPA_axis`

### CASE-013
- **干预**：药食同源 senolytic（槲皮素食源：红洋葱/苹果/茶）
- **原 source**：`{'journal': '食源槲皮素 / D+Q 机制', 'year': 2024, 'doi': 'Kirkland 2024 Nature Aging（投稿前需全文复核）'}`
- **effect_size**：机制外推（日常剂量弱于药物级 D+Q）
- **检索关键词**：
  - `药食同源 senolytic（槲皮素食源：红洋葱/苹果/茶）`
  - `药食同源 / 活血（食养清瘀）`
  - `槲皮素为 D+Q 中 senolytic 组分 → 日常低剂量清瘀`
  - `衰老细胞负荷`
  - `Senescence`
  - `p16_INK4a`

### CASE-022
- **干预**：避蓝光：夜间(睡前4h)避免短波蓝光暴露（发光eBook/手机屏 vs 印刷书）
- **原 source**：`{'journal': 'Proc Natl Acad Sci U S A', 'year': '2015', 'doi': '10.1073/pnas.1418490112'}`
- **effect_size**：褪黑素抑制 >55%；相位延迟 1.5 h（交叉内差异，p<0.05 量级）
- **检索关键词**：
  - `避蓝光：夜间(睡前4h)避免短波蓝光暴露（发光eBook/手机屏 vs 印刷书）`
  - `昼夜养护：夜卧避光、敛阳入阴（D轴阴阳-昼夜轴·保护性实证）`
  - `视网膜 ipRGC(黑视蛋白)→SCN→松果体轴：夜间短波(蓝)光经此信号抑制松果体褪黑素分泌、延迟昼夜相位；等价于'夜卧不敛阳'，扰动 D 轴稳态`
  - `褪黑素分泌`
  - `昼夜相位(DLMO)`
  - `睡眠潜伏期`
  - `Circadian_CLOCK_BMAL1`
  - `Melatonin_signaling`

### CASE-023
- **干预**：晨光暴露：晨间 1h 明亮光(10,000 lux)暴露
- **原 source**：`{'journal': 'Sleep Medicine', 'year': '2020', 'doi': '10.1016/j.sleep.2020.05.009'}`
- **effect_size**：睡眠效率 t=2.27 p=0.03；潜伏期 t=-2.40 p=0.03（组间差）
- **检索关键词**：
  - `晨光暴露：晨间 1h 明亮光(10,000 lux)暴露`
  - `昼夜养护：晨兴沐阳、升发阳气（D轴阴阳-昼夜轴·正面实证）`
  - `晨光经视网膜→SCN 提前昼夜相位、强化褪黑素节律幅度；等价于'晨兴升阳'，巩固 D 轴稳态`
  - `睡眠效率`
  - `睡眠潜伏期`
  - `显著性网络FC(右前岛叶)`
  - `Circadian_CLOCK_BMAL1`
  - `Melatonin_signaling`

### CASE-024-EXO
- **干预**：运动诱导外泌体释放（肌肉-脂肪串扰）
- **原 source**：`{'journal': 'Exosome / Sports Medicine', 'year': '2024', 'doi': '运动外泌体综述（投稿前需全文复核）'}`
- **effect_size**：循环外泌体浓度上调2-3倍（中-强效应）
- **检索关键词**：
  - `运动诱导外泌体释放（肌肉-脂肪串扰）`
  - `导引 / 气血流通（动则气血周流，外达四肢百骸）`
  - `运动→骨骼肌/脂肪组织释放外泌体(exosome)，携带miRNA(miR-133a/miR-206/miR-126)→调节远端组织代谢、血管新生、抗炎`
  - `循环外泌体浓度`
  - `外泌体miR-133a（肌肉源）`
  - `外泌体miR-126（内皮源）`
  - `Exosome_biogenesis`
  - `miRNA_signaling`

### CASE-025
- **干预**：间歇性断食调节外泌体miRNA谱
- **原 source**：`{'journal': 'Autophagy / Fasting exosome studies', 'year': '2023', 'doi': '断食外泌体研究（投稿前需全文复核）'}`
- **effect_size**：外泌体miRNA谱显著改变（中效应）
- **检索关键词**：
  - `间歇性断食调节外泌体miRNA谱`
  - `辟谷 / 气化重启（断食激活全身修复信号）`
  - `断食→细胞释放外泌体携带特定miRNA(miR-21/miR-155/miR-223)→调节免疫、代谢、自噬相关通路`
  - `外泌体miR-21（抗炎）`
  - `外泌体miR-155（免疫调节）`
  - `外泌体cargo自噬相关蛋白`
  - `Autophagy`
  - `Exosome_miRNA`

### CASE-026
- **干预**：外泌体递送天然活性成分（姜黄素/槲皮素纳米载体）
- **原 source**：`{'journal': 'Drug Delivery / Exosome-based delivery', 'year': '2024', 'doi': '外泌体药物递送综述（投稿前需全文复核）'}`
- **effect_size**：生物利用度提升40-50倍（强效应，体外/动物级）
- **检索关键词**：
  - `外泌体递送天然活性成分（姜黄素/槲皮素纳米载体）`
  - `药食同源 / 通络载药（经络传输药力）`
  - `天然姜黄素/槲皮素被包裹进外泌体→提高生物利用度（40-50×）→靶向递送至炎症/衰老组织→增强senolytic/抗炎效果`
  - `姜黄素生物利用度`
  - `炎症组织靶向递送效率`
  - `衰老细胞清除效率`
  - `Exosome_delivery`
  - `Senescence`

### CASE-030
- **干预**：Intermittent fasting strategies network meta-analysis
- **原 source**：`ScienceDirect 2026, DOI:10.1016/j.ther.2026.105127 (19 RCTs, 1149 participants)`
- **effect_size**：TRF liver fat MD:-23.32 dB/m (strong)
- **检索关键词**：
  - `Intermittent fasting strategies network meta-analysis`
  - `节律饮食/运化痰湿`
  - `TRE most effective IF regimen for hepatic steatosis reduction; ADF most effective for weight loss and HOMA-IR`
  - `Liver fat (TRF)`
  - `HOMA-IR (ADF)`
  - `Circadian`
  - `Hepatic_lipid`
  - `Insulin_sensitivity`

## 五、验证夹具与食疗条目（本轮不做 DOI 化）

- **验证夹具**（HL-0030…HL-0120，共 91 条）：由低分轴自动生成，设计上非文献案例；不做 DOI 匹配。
- **传统食疗**（CASE-014…021，共 8 条）：来源为古籍/本草，保留 traditional 状态与 L3 证据等级。

> **诚实披露**：'案例库 DOI 覆盖率'当前真实值 = 7/120。报告 §10 #5 目标 95% 在当前混合 schema 下不可诚实达成；
> 需将『真实文献案例』与『自动生成验证夹具』分区后再做覆盖率统计。
