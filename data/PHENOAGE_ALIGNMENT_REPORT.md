# H 轴自造代理 vs PhenoAge 对标报告（S1-3，2026-10-13）

> **合成画像装置验证**，不是真实队列校准。两把尺子共享的原始输入只有 glucose 与 CRP；相关性度量的是**仪器间一致性**，不能推断 HealthLens 代理的人体效度。真实校准需公开队列本地重跑（后续工作）。

## 口径
- x = PhenoAge 偏移 = PhenoAge − 实岁（Liu 2018 公开公式，SI 单位，公式订正 DOI 10.1371/journal.pmed.1002760）
- y = HealthLens 生物学年龄偏移 = BioAgeEngine.assess().delta（8 项自造扣分表：glucose/hba1c/hs_crp/waist/hdl/tg/sbp/bmi）
- 合成画像：n=200（seed=20261013），年龄 20–80，同一潜变量 z 驱动两套标志物

## 结果

| 指标 | 值 |
|---|---|
| 可计算画像 | 200/200 |
| **Pearson r** | **0.806** |
| Spearman ρ | 0.812 |
| PhenoAge 平均偏移 | +6.13 岁 |
| HealthLens 平均偏移 | +9.44 岁 |
| 偏移>3 岁（加速） | PhenoAge 135 / HealthLens 177 / 双标 133 |

## 解读边界（诚实声明）
1. r/ρ 显著不为零且为正 ⇒ 两把尺子在合成数据上**方向一致**，装置可跑、公式无误；
2. 共享输入仅 glucose+CRP ⇒ 相关性**不能**作为 H 轴人体效度证据；
3. 论文可写的措辞：「we implemented the published PhenoAge (Liu 2018) as a benchmark harness and established an alignment装置 on synthetic profiles; calibration against a reference cohort remains future work」——**不可**写成「aligned with PhenoAge on real data」。

*逐画像明细：`data/phenoage_alignment.json`；散点：`data/phenoage_alignment_scatter.svg`。*