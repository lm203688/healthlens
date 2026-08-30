# HealthLens 核心判断 Agent 规格 v1.1
## 古籍 × 基因 → 细胞修复「非用药」方案
> 版本：2026-08-20 ｜ 定位：去医疗化、AI 原生、可追溯
> 适用范围：细胞修复相关非药物干预（导引/断食/药食/情志/节律/外泌体/再生医学）的个性化建议生成

---

## 0. 三条红线（写进「拒判」逻辑）

| # | 红线 | 违反表现 | 处理 |
|---|------|----------|------|
| R1 | 「细胞修复」是机制不是商品 | 出现"修复细胞""激活自愈力"等空话 | 强制改写，锚定到可测通路（含外泌体/再生医学通路） |
| R2 | 古籍≠分子证据，基因≠处方 | 把古籍功效或单 SNP 直接当下结论 | 降级为假设，需机制+人体证据升级 |
| R3 | 非用药≠无风险 | 因"天然"默认安全、漏写禁忌 | 内置禁忌排除，高危项人工闸门 |

**必须锚定的生物学通路（R1 落点）**：自噬(AMPK/mTOR)、线粒体生物合成(PGC-1α/SIRT)、衰老细胞清除(senolytics)、干细胞龛支持、昼夜节律(CLOCK/BMAL1)、外泌体胞间通讯(exosome/miRNA)、再生医学调控(iPSC/细胞重编程)。

---

## 1. 输入 Schema

```yaml
user_input:
  gene_panel:                      # 基因层：必须通路级，禁止 SNP 级结论
    pathway_scores:               # 0-1，标注效应量与不确定区间
      mitochondrial:   {score: 0.32, ci: [0.21,0.45], source: "consumer_array"}
      autophagy:       {score: 0.61, ci: [0.50,0.72]}
      inflammation_clr:{score: 0.40, ci: [0.28,0.53]}
      exosome_signaling:{score: 0.55, ci: [0.42,0.68]}   # I轴：外泌体胞间通讯
      regeneration:    {score: 0.48, ci: [0.35,0.61]}    # J轴：再生医学/iPSC调控
    note: "消费级芯片本就是低效应量、概率性的"
  tcm_corpus_hits:                # 古籍层：复用 data/tcm_structured 实体
    - herb: "黄精"
      property: "平"
      efficacy: "老不饥"            # 来自 食疗本草 source_quote
      source: "食疗本草·卷上"
      evidence_level: "high"        # rule_extract 标记
  user_profile:
    contraindications: ["低血糖史","孕期"]   # 禁忌自动排除
    baseline: {sleep: "差",运动:"无",节律:"紊乱"}
```

---

## 2. 融合判定逻辑（伪代码）

```
def judge(user_input):
    # A. 机制映射：古籍候选 → 现代通路标签
    candidates = []
    for h in user_input.tcm_corpus_hits:
        paths = map_efficacy_to_pathways(h.efficacy)   # 见 §6 映射层
        candidates.append({herb:h, pathways:paths})

    # B. 个性化加权：只保留 古籍候选 ∩ 基因弱项 的交集
    weak = {p for p,s in gene_panel.pathway_scores if s.score < 0.5}
    for c in candidates:
        c.weight = len(c.pathways & weak)             # 交集才有高分
        # 严禁单 SNP 决定一条建议 → 无此分支

    # C. 证据分层标注（四档不可混）
    for c in candidates:
        c.evidence = grade(c)   # mechanism / human_RCT / classic_exp / consensus

    # D. 输出：每条含 7 字段（§3）
    outputs = [build_output(c) for c in top(candidates, k=5) if c.weight>0]

    # E. 安全闸门（§5）
    outputs = apply_safety(outputs, user_input.contraindications)
    return outputs
```

**关键约束**：
- 古籍候选 ∩ 基因弱项通路 才判高分；纯古籍经验（无基因交集）降为「通用建议」。
- **禁单 SNP 决定建议**（如"你有 X SNP 所以必须吃 Y"）——伪个性化，必须拦截。
- 基因只聚合成「通路级得分」，绝不下 SNP 级处方。

---

## 3. 输出 7 字段模板

每条建议必须含：

| 字段 | 说明 | 示例 |
|------|------|------|
| ① 靶向通路 | 锚定 R1 通路 | 线粒体生物合成(PGC-1α) |
| ② 古籍出处 | 原文可溯 | 食疗本草·黄精"九蒸九曝，能老不饥" |
| ③ 基因相关性 | 哪条弱项通路 | 基因 panel: mitochondrial=0.32(弱) |
| ④ 证据等级 | 四档之一 | 人体证据 Tier-2（断食→AMPK） |
| ⑤ 禁忌 | 自动排除项 | 低血糖史者禁用 16:8 断食 |
| ⑥ 监测指标 | 可量化 | 静息心率、疲劳量表、睡眠时长 |
| ⑦ 可执行处方 | 强度/时长/节奏 | 导引 20min×3/周 + 16:8 限食 |

**底层基线（任何人都优先于花哨方案）**：睡眠、运动、限食、节律——若用户基线已达标，不叠加复杂方案。

---

## 4. 降级规则（is_demo 三态横幅）

沿用项目已有护栏：

| 状态 | 触发 | 表现 |
|------|------|------|
| `live` | 古籍+基因+人体证据三者齐备 | 正常输出 7 字段 |
| `is_demo` | 缺基因数据 / 缺人体证据 / 仅古籍 | 横幅提示"示例，非为你定制" |
| `blocked` | 越界诊断 / 无禁忌数据却给高危干预 | 拦截，转人工闸门 |

**任何结论须能追溯到「机制文献 + 古籍原文 + 用户基因证据」三者之一，且标注置信度。三者皆缺 → 只能叫"通用健康建议"，不得叫"为你定制的细胞修复方案"。**

---

## 5. 安全治理（agent-boost 闭环）

```
禁忌自动排除 → 去医疗化声明 → 高干预人工审批 → Governor 自审
```

- **禁忌排除**：先比对 `user_profile.contraindications`，命中即移除该建议。
- **去医疗化声明**：文末固定"本内容不替代医师诊断，疾病请就医"。
- **高干预人工闸门**：涉及断食>24h、冷热应激、补剂高剂量 → 标记需人工确认后才可推送。
- **Governor 自审**：输出前独立审查是否越界诊断/过度承诺；数据不足时强制降级（§4）。

---

## 6. 古籍功效 → 通路映射层（落地到 rule_extract）

现有 `data/tcm_structured/*.json` 实体字段：`type/name/property/efficacy/source_quote/evidence_level`。
**新增映射层**，不改动原结构，单独建 `data/tcm_pathway_map.json`：

```json
{
  "黄精":   {"efficacy_tags":["耐饥","益精"], "pathways":["autophagy","mitochondrial"], "systems":["脾","肾"]},
  "天门冬": {"efficacy_tags":["补虚劳","润肺"], "pathways":["autophagy"], "systems":["肺","肾"]}
}
```

抽取规则（补进 `tcm_structurer.py` / `rule_extract`）：
1. 归经 → 生理系统（脾/肾/肺…）；性味(平/微寒) → 干预强度档。
2. `efficacy` 关键词 → 通路标签（"老不饥/耐饥"→autophagy；"补虚/益精"→mitochondrial）。
3. 仅做候选标注，证据升级仍走 §2-C 四档。

---

## 7. 基因层约束

- **禁 SNP 级结论**：消费级芯片效应量低、概率性强，绝不下"你有某 SNP 故…"的处方。
- **聚合成通路级得分**：如线粒体功能、解毒、炎症清除倾向，输出 0-1 + 置信区间。
- 基因只用于「个性化加权」（§2-B），不作为独立证据源。

---

## 8. 落地范例

> **输入**：基因 panel `mitochondrial=0.32(弱)` + `inflammation_clr=0.40(弱)`；古籍命中「导引/八段锦/站桩 + 周期性辟谷 + 黑色入肾食疗」。
>
> **判定**：① 导引/断食现代证据支持 AMPK→PGC-1α 线粒体生物合成（人体证据 Tier-2/3）；② 与用户弱项通路(线粒体)交集成立 → 加权高分；③ 输出"每周 3 次导引 + 16:8 限食 + 监测静息心率/疲劳量表"，标注**禁忌**（低血糖史禁用断食）。
>
> **降级**：若缺人体证据则标注 Tier-3 并加 `is_demo` 横幅，绝不写"专为你修复线粒体"。

---

## 9. 下一步（可选实现）

1. 实现 `data/tcm_pathway_map.json` + `tcm_structurer.py` 映射抽取（§6）。
2. 把 §2 伪代码落地为 `app/services/cell_repair_agent.py`，接 `is_demo` 护栏。
3. 输入侧接基因 panel 解析器（通路级聚合，§7）。

---

## 10. 外泌体与再生医学判定逻辑（v1.1 新增）

### 10.1 外泌体通路（I轴）判定规则

外泌体胞间通讯是细胞修复信号的"放大器"。判定逻辑：

```
# 外泌体通路弱项判定
if exosome_signaling.score < 0.5:
    # 用户外泌体胞间通讯通路偏弱 → 推荐促进外泌体释放的干预
    candidates.append({
        "pathway": "exosome_signaling",
        "interventions": [
            {"name": "规律有氧运动", "evidence": "L2", "mechanism": "运动→肌肉/脂肪释放外泌体↑2-3×→miR-133a/miR-126全身信号"},
            {"name": "间歇性断食(16:8)", "evidence": "L2", "mechanism": "断食→外泌体cargo重编程→miR-21↑/miR-155↓"},
        ],
        "weight": 1.0 if autophagy.score < 0.5 else 0.7,  # 自噬也弱时加权
    })
```

**关键约束**：
- 外泌体检测目前无消费级产品，不进入"监测指标"字段（§3-⑥）。
- 外泌体通路弱项通过**代理指标**推断：运动量低 + 炎症标记高 → 推测外泌体信号不足。
- **禁止宣称"提升外泌体水平"**——只能说"促进身体自然的胞间信号传导"。

### 10.2 再生医学通路（J轴）判定规则

iPSC/细胞重编程是再生医学的基石。判定逻辑：

```
# 再生医学通路弱项判定
if regeneration.score < 0.5:
    # 用户细胞再生能力通路偏弱 → 推荐支持干细胞龛的干预
    candidates.append({
        "pathway": "regeneration",
        "interventions": [
            {"name": "周期性模拟禁食(FMD)", "evidence": "L1", "mechanism": "FMD→干细胞龛激活→生理年龄↓2.5岁(CASE-003)"},
            {"name": "充足深度睡眠", "evidence": "L2", "mechanism": "睡眠→生长激素分泌→干细胞龛支持"},
        ],
        "weight": 1.0 if epigenetic_clock.score < 0.5 else 0.7,
    })
```

**关键约束**：
- iPSC疗法属于医疗行为，**严禁推荐**任何iPSC注射/移植。
- 再生医学通路弱项只能推荐**生活方式干预**（FMD、睡眠、运动），不推荐任何细胞疗法。
- 输出中"再生"表述为"支持身体自然的细胞更新能力"，禁用"干细胞治疗""细胞再生疗法"等医疗化表述。

### 10.3 外泌体×古籍映射层

| 古籍概念 | 外泌体机制 | 证据等级 | 可执行干预 |
|----------|-----------|---------|-----------|
| 气血周流 / 经络 | 外泌体胞间信号传导 | L2（机制+人体） | 规律运动促进外泌体释放 |
| 导引 / 动则生阳 | 运动诱导外泌体miRNA释放 | L2 | 有氧/HIIT 20-30min×3-5/周 |
| 辟谷 / 气化重启 | 断食调控外泌体cargo | L2 | 16:8 TRE或周期性FMD |
| 药食同源通络 | 外泌体纳米递送增强生物利用度 | L3（体外/动物） | 抗炎饮食（多酚类食物） |

### 10.4 CD4+T细胞免疫衰老评估（F轴/H轴交叉，v1.1新增）

CD4+T细胞是免疫衰老的核心驱动因子，横跨F轴（正邪-炎症）和H轴（先天-肾精）。判定逻辑：

```
# CD4免疫衰老评估（交叉判定）
if cd4_cd8_ratio < 1.0 or cd4_naive_ratio < 0.2:
    # 免疫衰老信号 → F轴炎症加重 + H轴干细胞龛功能下降
    candidates.append({
        "pathway": "immunosenescence",
        "axes": ["F", "H"],
        "interventions": [
            {"name": "热量限制/间歇性断食", "evidence": "L1", "mechanism": "CR→自噬增强→CD4+T细胞线粒体清除→免疫功能恢复"},
            {"name": "规律有氧运动", "evidence": "L1", "mechanism": "运动→CD4 CTL维持→免疫监视功能"},
            {"name": "D+Q饮食源模拟", "evidence": "L2", "mechanism": "槲皮素(食源)→mTOR抑制→CD4+T细胞向年轻表型分化"},
        ],
        "weight": 1.0 if inflammaging.score < 0.5 else 0.7,
    })
```

**古籍映射**："正气存内，邪不可干"→CD4 CTL扩增=现代免疫监视的"正气"表现；"肾精亏虚"→CD4 naiveT细胞池萎缩=先天免疫储备下降。

**关键约束**：
- CD4/CD8比值和CD4 naive/Tm比例目前需实验室检测（Flow Cytometry），无消费级产品。
- 通过代理指标推断免疫衰老状态：年龄>60 + 慢性炎症标记高 + 睡眠质量差 → 推测CD4免疫衰老风险。
- 严禁宣称"检测免疫衰老"——只能说"支持免疫系统的自然防御能力"。

### 10.5 BioWell GDV经脉光子评估（E轴硬件接口，v1.1新增）

BioWell通过指尖光电发射成像（GDV）测量经脉能量状态，直接桥接中医经脉理论与现代光子物理学。

```
# BioWell经脉能量评估（E轴可选硬件）
if biowell_scan.available:
    # BioWell数据接入 → 脏腑经脉能量分布
    organ_energy = biowell_scan.get_organ_energies()  # 各脏腑能量评分
    stress_index = biowell_scan.get_stress_index()    # 自主神经平衡
    entropy = biowell_scan.get_entropy()               # 系统组织度

    # 与E轴（脏腑-神经内分泌）融合
    if stress_index > threshold_high:
        candidates.append({
            "pathway": "neuroendocrine_hpa",
            "axis": "E",
            "evidence": "BioWell Stress Index > 高阈值",
            "interventions": [
                {"name": "冥想/呼吸训练", "mechanism": "调节自主神经→降低BioWell Stress Index"},
                {"name": "规律作息/节律养生", "mechanism": "D轴昼夜节律→E轴HPA平衡"},
            ],
        })
```

**BioWell参数与HealthLens轴映射**：

| BioWell参数 | 健康范围 | 映射轴 | 健康含义 |
|---|---|---|---|
| Area（光子面积） | 越大越好 | A/B | 整体功能容量、代谢活性 |
| Intensity（光子强度） | 中等最佳 | B/C | 电子发射强度、细胞代谢活力 |
| Stress Index | 越低越好 | D/E/G | 自主神经平衡（交感/副交感） |
| Entropy Coefficient | 中等最佳 | 系统级 | 组织有序度/混沌度 |
| Form Coefficient | 越高越好 | A/I | 发射规则性、系统协调性 |

**关键约束**：
- BioWell测量的是受激光电发射（非人体原生生物场），经脉映射基于中医理论+Empirical验证。
- BioWell是手动设备，不适合连续监测——作为周期性评估工具（月度/季度扫描）。
- 设备价格约$500-1000，属于个人可购买级别，适合HealthLens用户画像。
- 输出中表述为"经脉能量状态评估"，严禁"诊断疾病"或"检测生物场"。

### 10.6 C2S-Scale条件推理验证层（v1.1新增）

C2S-Scale（Google DeepMind+Yale）用单细胞基础模型做4000+药物的双上下文虚拟筛选——药物有效性取决于细胞类型和生物状态。HealthLens借鉴此方法论：古籍候选干预只在匹配的基因弱项背景下才有效。

```
# C2S-Scale条件推理同构验证
def validate_classical_candidate(classical_candidate, genetic_profile):
    """
    C2S-Scale启示：干预有效性取决于生物上下文。
    古籍候选 × 基因弱项 = 条件推理
    """
    # 1. 古籍候选的通路映射
    pathway = map_classical_to_pathway(classical_candidate)
    # 2. 用户基因弱项的通路得分
    user_score = genetic_profile.pathway_scores[pathway]
    # 3. 条件判定：只有用户该通路偏弱时，候选才有效
    if user_score < 0.5:
        return {"valid": True, "weight": 1.0 - user_score}  # 弱项越弱，权重越高
    else:
        return {"valid": False, "reason": "pathway_not_weak"}
```

**HealthLens与C2S-Scale的方法论同构**：

| 维度 | C2S-Scale | HealthLens |
|------|-----------|-----------|
| 条件输入 | 细胞类型+生物状态 | 基因弱项+古籍候选 |
| 筛选对象 | 4000+药物 | 30+古籍干预 |
| 推理方式 | 虚拟筛选→条件有效 | 融合判定→条件推荐 |
| 共同原则 | 不在所有上下文中普适 | 只在匹配的生物背景下推荐 |

**关键约束**：
- C2S-Scale是药物发现工具，HealthLens是非用药干预框架——方法论借鉴，不做药物推荐。
- 条件推理的验证需独立RCT，当前仅做逻辑层面的同构论证。

### 10.7 GeneLLM cfRNA检测增强层（v1.1新增）

GeneLLM（Bilford Lab/Jindu Life Sciences）将cfRNA原始测序数据作为token处理，无需基因组注释即可发现癌症相关"伪生物标志物"（pseudo-biomarkers）。其核心洞察：RNA序列本身就是语言，Transformer可以理解细胞的"语言行为"。

**对HealthLens的增强路径**：

```
# GeneLLM启发的cfRNA检测增强
if cfrna_data.available:
    # GeneLLM处理cfRNA原始数据 → 发现伪生物标志物
    pseudo_biomarkers = geneLLM.detect(cfrna_raw_reads)
    # 与HealthLens十轴映射
    axis_scores = map_biomarkers_to_axes(pseudo_biomarkers)
    # 增强外泌体通路（I轴）的检测精度
    exosome_enhanced = fuse(consumer_chip_scores, axis_scores.exosome)
```

**HealthLens与GeneLLM/BioFord的协同**：

| 组件 | 功能 | 对HealthLens的价值 |
|------|------|-------------------|
| GeneLLM | cfRNA→伪生物标志物 | 增强I轴外泌体检测，无需基因组注释 |
| Gene Universe | AI驱动实验验证平台 | 为HealthLens推荐提供实验验证参考 |
| BioFord | 实验室即代码 | 未来可接入实验室自动化，实现推荐→验证闭环 |

**关键约束**：
- GeneLLM（158.63GB）为研究级模型，当前不适合消费端部署——作为后台增强引擎。
- cfRNA检测需专业实验室（NGS测序），无消费级产品——通过代理指标推断外泌体通路状态。
- BioFord实验室自动化属于前沿概念，HealthLens暂不接入，仅作为方法论参考。
