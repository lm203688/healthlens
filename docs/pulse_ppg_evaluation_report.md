# Pulse-PPG / PaPaGei 零样本评测报告

**报告版本**：v0.30.0 初始脚手架
**生成时间**：2026-10-16T10:55:52
**种子**：42
**样本数**：100
**任务**：classification / regression / anomaly（各跑一次）

> 报告出处：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」

## 1. 诚实声明

本报告的**评测脚手架已就绪**：合成数据 + 特征 baseline + 分类/回归/异常
三任务的 harness 全部可跑通，能验证端到端评测链路本身正确。

**但**：报告的 §10 #6 核心命题——"评测 Pulse-PPG / PaPaGei 在现有脉搏波
数据上的零样本表征质量"——需要用户提供真实模型权重才能闭合。当前 baseline
只用手工特征 + 极简分类器/回归器，只能验证流程，**不能代表真实模型能力**。

## 2. 数据规模

- 信号类型：PPG
- 采样率：100 Hz
- 单条时长：5.0 s
- 总样本数：100（按 rest / exercise / stress 三类均分轮转）
- 数据集指纹（sha256[:16]）：`47ddb42c9f1d2f94`

### 合成数据构造（仅供评测脚手架验证）

- **PPG**：主正弦（心率基频 0.8–2.0 Hz）+ 呼吸调制（0.2 Hz）+ 高斯噪声
- 分类预设：
  - `rest`：freq=0.9 Hz, noise=0.05, breath=0.05
  - `exercise`：freq=1.8 Hz, noise=0.15, breath=0.12
  - `stress`：freq=1.3 Hz, noise=0.20, breath=0.08

> 合成数据的分布与真人传感器数据差异极大，仅用于验证 harness 流程本身
> 正确，不用于生产健康推断。

## 3. 任务定义

| 任务 | 目标 | 主指标 |
| --- | --- | --- |
| classification | 3 类活动识别（rest/exercise/stress） | accuracy, f1_macro |
| regression | 心率估计（BPM） | R², MAE |
| anomaly | 心律失常检测（正常 vs 异常二分） | AUROC, accuracy |

## 4. Baseline 结果

### 4.1 Classification（3 类活动识别）

| engine | accuracy | f1_macro | auroc | r2 | latency_ms | n_samples |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 310.5 | 100 |

**分类细节**：
- **baseline** (n_test=30): per-class F1 = ['rest', 'stress', 'rest'] vs true = ['rest', 'stress', 'rest']
  - per_class_f1: {'exercise': 1.0, 'rest': 1.0, 'stress': 1.0}

### 4.2 Regression（心率估计，BPM）

| engine | accuracy | f1_macro | auroc | r2 | latency_ms | n_samples |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.0000 | 0.0000 | 0.0000 | 0.9093 | 276.3 | 100 |

**回归细节**：
- **baseline** (n_test=30): MAE=5.1749, NRMSE=0.0655, target_mean_hr=79.0 BPM

### 4.3 Anomaly（异常检测）

| engine | accuracy | f1_macro | auroc | r2 | latency_ms | n_samples |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.8667 | 0.8611 | 0.8612 | 0.0000 | 313.8 | 100 |

**异常检测细节**：
- **baseline** (n_test=30): n_pos=11, n_neg=19, threshold=7.017

## 5. SensorFM 基准对照（引用，不作为对比基线）

Google 2026-07 发布的 SensorFM：500 万人 / 1 万亿分钟 / 35 项任务，号称
SOTA。**但该模型未见开源**，本报告的路线图不能押在拿不到的权重上。
引用数字仅供参考，不纳入对比表格。

- 训练规模：5,000,000 用户 × 10¹² 分钟数据
- 任务覆盖：35 项（HRV / HR / SpO2 / sleep / activity / ECG / PPG ...）
- 发布形式：仅论文 + demo，未见 checkpoint 或权重分发

**HealthLens 立场**：路线图押 Pulse-PPG（IMWUT 2025, arXiv 2502.01108）
与 PaPaGei（ICLR 2025, Nokia Bell Labs）——两者均为公开论文 + 部分权重。

## 6. 局限与后续

**局限**：
1. **无真实权重**：baseline 只用手工特征 + 极简 KNN/线性回归，
   评测脚手架验证 ≠ 真实模型能力。
2. **合成数据**：波形由参数化公式生成，与真人传感器分布差异极大。
3. **单信号类型**：本轮只跑 PPG；ECG / EMG / EEG 需在报告中加跑。
4. **小样本**：默认 n=200，用于 CI 快速跑通；正式评测应扩大到
   数千到数万样本。

**后续**：
1. 用户 pip install torch transformers 并配置 `HL_PULSE_PPG_CHECKPOINT`
   环境变量后，`--with-engine` 即可跑真实模型零样本评测。
2. 接入真实野外 PPG 数据集（如 IMWUT 2025 官方数据集），复算 §10 #6。
3. 与 PaPaGei（ICLR 2025, Nokia Bell Labs）横向对比（当前仅占位）。
4. 把 §10 #6 从「3–5 天」推进到「报告闭合」。

## 7. 附录：文件清单

- `app/lib/synthetic_sensor_dataset.py`：合成数据生成
- `app/lib/feature_baseline.py`：特征工程 baseline
- `app/lib/zero_shot_eval_harness.py`：零样本评测 harness
- `tools/run_puls_egg_eval.py`：一键评测脚本
- `tests/lib/test_zero_shot_eval.py`：契约测试

---

**Wellness 平台术语纪律**：本报告仅做统计/评测流程验证，不诊断、不做健康推断。
