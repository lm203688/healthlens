"""一键运行 Pulse-PPG / PaPaGei 零样本评测脚手架 + 生成 Markdown 报告。

报告出处：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」

用法：
    python tools/run_puls_egg_eval.py                            # 默认 seed=42, n=200
    python tools/run_puls_egg_eval.py --n-samples 100
    python tools/run_puls_egg_eval.py --with-engine              # 尝试接真实模型（缺权重会 fail-loud）

产物：
    docs/pulse_ppg_evaluation_report.md —— 初始评测报告（合成数据 + baseline，无真实模型）。

Wellness 平台术语纪律：本报告仅验证评测脚手架流程正确性，不用于生产健康推断。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

# 让脚本可在非包上下文直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.lib.synthetic_sensor_dataset import (
    CLASS_LABELS,
    SyntheticSensor,
    SyntheticSensorDataset,
    generate_batch,
)
from app.lib.zero_shot_eval_harness import (
    BaselineResult,
    EvaluatorConfig,
    ZeroShotEvalHarness,
)
from app.lib.sensor_adapter import (
    HealthLensUnavailableEngine,
    load_papagei_model,
    load_pulse_ppg_model,
)


# ─────────────────────────── 报告生成 ───────────────────────────

REPORT_TEMPLATE = """# Pulse-PPG / PaPaGei 零样本评测报告

**报告版本**：v0.30.0 初始脚手架
**生成时间**：{timestamp}
**种子**：{seed}
**样本数**：{n_samples}
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
- 总样本数：{n_samples}（按 rest / exercise / stress 三类均分轮转）
- 数据集指纹（sha256[:16]）：`{fingerprint}`

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

{classification_table}

**分类细节**：
{classification_details}

### 4.2 Regression（心率估计，BPM）

{regression_table}

**回归细节**：
{regression_details}

### 4.3 Anomaly（异常检测）

{anomaly_table}

**异常检测细节**：
{anomaly_details}

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
"""


def _format_details(d: dict) -> str:
    if not d:
        return "- (no details)"
    lines = []
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            lines.append(f"- **{k}**：`{v}`")
        else:
            lines.append(f"- **{k}**：{v}")
    return "\n".join(lines)


def build_report(
    classification_results: list[BaselineResult],
    regression_results: list[BaselineResult],
    anomaly_results: list[BaselineResult],
    seed: int,
    n_samples: int,
    fingerprint: str,
) -> str:
    """组装 Markdown 报告。"""
    from app.lib.zero_shot_eval_harness import ZeroShotEvalHarness

    cls_cmp = ZeroShotEvalHarness.compare(classification_results)
    reg_cmp = ZeroShotEvalHarness.compare(regression_results)
    ano_cmp = ZeroShotEvalHarness.compare(anomaly_results)

    # 分类细节
    cls_details_lines = []
    for r in classification_results:
        if r.details.get("task") == "classification":
            cls_details_lines.append(
                f"- **{r.engine_name}** (n_test={r.details.get('n_test')}): "
                f"per-class F1 = {r.details.get('y_pred_sample', [])[:3]} vs "
                f"true = {r.details.get('y_true_sample', [])[:3]}"
            )
            # 详细 per_class_f1
            pc = r.details.get("per_class_f1", {})
            if pc:
                cls_details_lines.append(
                    f"  - per_class_f1: {pc}"
                )

    reg_details_lines = []
    for r in regression_results:
        if r.details.get("task") == "regression":
            reg_details_lines.append(
                f"- **{r.engine_name}** (n_test={r.details.get('n_test')}): "
                f"MAE={r.details.get('mae')}, NRMSE={r.details.get('nrmse')}, "
                f"target_mean_hr={r.details.get('target_mean_hr')} BPM"
            )

    ano_details_lines = []
    for r in anomaly_results:
        if r.details.get("task") == "anomaly":
            ano_details_lines.append(
                f"- **{r.engine_name}** (n_test={r.details.get('n_test')}): "
                f"n_pos={r.details.get('n_pos_test')}, n_neg={r.details.get('n_neg_test')}, "
                f"threshold={r.details.get('threshold')}"
            )

    return REPORT_TEMPLATE.format(
        timestamp=_dt.datetime.now().isoformat(timespec="seconds"),
        seed=seed,
        n_samples=n_samples,
        fingerprint=fingerprint,
        classification_table=cls_cmp["markdown_table"],
        classification_details="\n".join(cls_details_lines) or "- (empty)",
        regression_table=reg_cmp["markdown_table"],
        regression_details="\n".join(reg_details_lines) or "- (empty)",
        anomaly_table=ano_cmp["markdown_table"],
        anomaly_details="\n".join(ano_details_lines) or "- (empty)",
    )


# ─────────────────────────── 主入口 ───────────────────────────

def run(
    seed: int = 42,
    n_samples: int = 200,
    output: str = "docs/pulse_ppg_evaluation_report.md",
    with_engine: bool = False,
) -> str:
    """端到端评测 + 报告生成。返回报告路径。"""
    # 1. 生成合成数据
    sensors = generate_batch(
        n=n_samples,
        seed=seed,
        signal_type="PPG",
        duration_sec=5.0,
    )
    dataset = SyntheticSensorDataset(
        sensors=sensors,
        metadata={
            "seed": seed,
            "n_samples": n_samples,
            "signal_type": "PPG",
            "tasks": ["classification", "regression", "anomaly"],
        },
    )
    fingerprint = dataset.fingerprint()

    # 2. 跑三个任务的 baseline
    classification_results: list[BaselineResult] = []
    regression_results: list[BaselineResult] = []
    anomaly_results: list[BaselineResult] = []

    h_cls = ZeroShotEvalHarness(EvaluatorConfig(
        signal_type="PPG", task="classification", metric="accuracy", random_seed=seed
    ))
    classification_results.append(h_cls.run_baseline(sensors))

    h_reg = ZeroShotEvalHarness(EvaluatorConfig(
        signal_type="PPG", task="regression", metric="accuracy", random_seed=seed
    ))
    regression_results.append(h_reg.run_baseline(sensors))

    # anomaly 任务：把 labels 重映射到 normal/anomaly（每 3 条标 1 条 anomaly 模拟）
    anomaly_sensors = []
    for i, s in enumerate(sensors):
        # 复制一份，标签重映射（不修改原对象）
        new_s = SyntheticSensor(
            signal_type=s.signal_type,
            sample_rate_hz=s.sample_rate_hz,
            duration_sec=s.duration_sec,
            subject_id=s.subject_id + "_ano",
            samples=list(s.samples),
            label=("anomaly" if i % 3 == 2 else "normal"),
            ground_truth_hr_bpm=s.ground_truth_hr_bpm,
        )
        anomaly_sensors.append(new_s)

    h_ano = ZeroShotEvalHarness(EvaluatorConfig(
        signal_type="PPG", task="anomaly", metric="auroc", random_seed=seed
    ))
    anomaly_results.append(h_ano.run_baseline(anomaly_sensors))

    # 3. 可选：接真实模型
    if with_engine:
        try:
            pulse_ppg_engine = load_pulse_ppg_model(load_weights=True)
            # 用真实模型跑分类
            engine_result = h_cls.run_engine(pulse_ppg_engine, sensors)
            classification_results.append(engine_result)
            print(f"[with-engine] Pulse-PPG loaded: {pulse_ppg_engine}")
        except HealthLensUnavailableEngine as exc:
            print(f"[with-engine] Pulse-PPG skipped: {exc}")

        try:
            papagei_engine = load_papagei_model(load_weights=True)
            engine_result = h_cls.run_engine(papagei_engine, sensors)
            classification_results.append(engine_result)
            print(f"[with-engine] PaPaGei loaded: {papagei_engine}")
        except HealthLensUnavailableEngine as exc:
            print(f"[with-engine] PaPaGei skipped: {exc}")

    # 4. 生成报告
    report_md = build_report(
        classification_results=classification_results,
        regression_results=regression_results,
        anomaly_results=anomaly_results,
        seed=seed,
        n_samples=n_samples,
        fingerprint=fingerprint,
    )

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"[run_puls_egg_eval] report written: {out_path}")
    print(f"[run_puls_egg_eval] dataset fingerprint: {fingerprint}")
    print(f"[run_puls_egg_eval] classification best: "
          f"{classification_results[0].engine_name} acc={classification_results[0].accuracy} "
          f"f1={classification_results[0].f1_macro}")
    print(f"[run_puls_egg_eval] regression R²: "
          f"{regression_results[0].r2} (MAE={regression_results[0].details.get('mae')})")
    print(f"[run_puls_egg_eval] anomaly AUROC: "
          f"{anomaly_results[0].auroc} (acc={anomaly_results[0].accuracy})")

    return str(out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pulse-PPG / PaPaGei zero-shot eval harness")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument("--n-samples", type=int, default=200, help="number of samples (default: 200)")
    parser.add_argument(
        "--output",
        default="docs/pulse_ppg_evaluation_report.md",
        help="output report path (default: docs/pulse_ppg_evaluation_report.md)",
    )
    parser.add_argument(
        "--with-engine",
        action="store_true",
        help="try to load real Pulse-PPG / PaPaGei models (default: False)",
    )
    args = parser.parse_args(argv)

    run(
        seed=args.seed,
        n_samples=args.n_samples,
        output=args.output,
        with_engine=args.with_engine,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
