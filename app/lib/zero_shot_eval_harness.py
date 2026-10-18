"""零样本评测 harness（Pulse-PPG / PaPaGei 评测脚手架）

报告出处：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」

本 harness 提供「给定信号 + 标签 → baseline 结果」的端到端脚手架：
- **零权重即可运行**：内置极简 KNN 分类器 + 线性回归（纯 Python，无 sklearn）。
- **权重接口预留**：`run_engine(engine, dataset)` 未装真实模型时抛
  `HealthLensUnavailableEngine`，装了后可接入。
- **任务类型**：classification（3 类活动识别）/ regression（心率估计）/ anomaly。
- **报告生成**：`compare(results)` 输出 Markdown 表格 + 结论段。

Wellness 平台术语纪律：仅做统计/评测流程验证，不诊断、不做健康推断。
"""
from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


# 从 sensor_adapter 复用统一异常，避免多头
from app.lib.sensor_adapter import HealthLensUnavailableEngine
from app.lib.feature_baseline import extract_baseline_features, feature_names, to_feature_matrix


TaskType = Literal["classification", "regression", "anomaly"]
Metric = Literal["accuracy", "f1", "auroc"]
SignalType = Literal["PPG", "ECG", "EMG", "EEG"]


# ─────────────────────────── 数据模型 ───────────────────────────

@dataclass
class EvaluatorConfig:
    """零样本评测配置。

    字段：
    - signal_type: PPG / ECG / EMG / EEG
    - task: classification / regression / anomaly
    - metric: accuracy / f1 / auroc
    - train_ratio: 训练集比例（0–1）
    - random_seed: 随机种子（数据划分 + 模型）
    """

    signal_type: SignalType = "PPG"
    task: TaskType = "classification"
    metric: Metric = "accuracy"
    train_ratio: float = 0.7
    random_seed: int = 42

    def validate(self) -> None:
        if self.signal_type not in ("PPG", "ECG", "EMG", "EEG"):
            raise ValueError(f"unsupported signal_type: {self.signal_type!r}")
        if self.task not in ("classification", "regression", "anomaly"):
            raise ValueError(f"unsupported task: {self.task!r}")
        if self.metric not in ("accuracy", "f1", "auroc"):
            raise ValueError(f"unsupported metric: {self.metric!r}")
        if not (0.0 < self.train_ratio < 1.0):
            raise ValueError(f"train_ratio must be in (0, 1), got {self.train_ratio}")


@dataclass
class BaselineResult:
    """单次评测结果。

    字段：
    - engine_name: baseline（默认）或 "Pulse-PPG" / "PaPaGei"
    - accuracy: 分类准确率（回归/异常任务留 0.0，用 metric_value 承载主指标）
    - f1_macro: 宏平均 F1
    - auroc: 二分类 AUROC
    - metric_value: 按 metric 主指标（accuracy / f1 / auroc 之一）
    - r2: 回归任务 R²（其它任务留 0.0）
    - latency_ms: 评测耗时（毫秒）
    - n_samples: 参与评测的样本数
    - details: 附加信息（如 per_class_f1）
    """

    engine_name: str
    accuracy: float
    f1_macro: float
    auroc: float
    metric_value: float
    r2: float = 0.0
    latency_ms: float = 0.0
    n_samples: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown_row(self) -> str:
        """一行 Markdown 表格（横向对比用）。"""
        return (
            f"| {self.engine_name} "
            f"| {self.accuracy:.4f} "
            f"| {self.f1_macro:.4f} "
            f"| {self.auroc:.4f} "
            f"| {self.r2:.4f} "
            f"| {self.latency_ms:.1f} "
            f"| {self.n_samples} |"
        )


# ─────────────────────────── 极简分类/回归（纯 Python） ───────────────────────────

class _KNNClassifier:
    """k-NN 分类器（纯 Python，欧氏距离）。

    训练：记录 (feature_vec, label) 对。
    预测：k 个最近邻投票。
    """

    def __init__(self, k: int = 3):
        self.k = max(1, k)
        self.train_x: list[list[float]] = []
        self.train_y: list[str] = []

    def fit(self, X: list[list[float]], y: list[str]) -> None:
        if not X or not y or len(X) != len(y):
            raise ValueError("X and y must be non-empty and equal length")
        self.train_x = list(X)
        self.train_y = list(y)

    @staticmethod
    def _dist(a: list[float], b: list[float]) -> float:
        return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))

    def predict(self, x: list[float]) -> str:
        if not self.train_x:
            raise ValueError("model not fitted")
        scored = [(self._dist(x, xt), yt) for xt, yt in zip(self.train_x, self.train_y)]
        scored.sort(key=lambda t: t[0])
        votes = [label for _, label in scored[: self.k]]
        # 简单多数投票；平局按字典序取最小
        from collections import Counter
        counts = Counter(votes)
        max_c = max(counts.values())
        for label, c in counts.items():
            if c == max_c:
                return label
        return votes[0]

    def predict_batch(self, X: list[list[float]]) -> list[str]:
        return [self.predict(x) for x in X]


class _LinearRegression:
    """极简岭回归（正规方程 + 岭正则化，纯 Python）。

    实现：解 (X^T X + λI) w = X^T y（含偏置项，通过给 X 加一列常数 1；
    偏置项不加正则化，避免压缩截距）。λ 用于防止高维欠定问题导致过拟合。
    用高斯消元 + 部分主元解线性方程组。
    """

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.weights: list[float] = []
        self.bias: float = 0.0
        self._dim: int = 0

    def fit(self, X: list[list[float]], y: list[float]) -> None:
        n = len(X)
        if n < 2:
            raise ValueError("need >= 2 samples for linear regression")
        d = len(X[0])
        if any(len(row) != d for row in X):
            raise ValueError("X rows must have equal length")
        if n != len(y):
            raise ValueError("X and y must have equal length")
        # 自适应 λ：特征维度远大于样本数时加大正则化（避免欠定矩阵病态）
        effective_alpha = self.alpha * max(1.0, d / max(n, 1))
        # 加偏置列
        X_aug = [[1.0] + list(row) for row in X]
        # 构造正规方程 A w = b: A = X^T X (d+1 x d+1), b = X^T y (d+1)
        p = d + 1
        A = [[0.0] * p for _ in range(p)]
        b = [0.0] * p
        for i in range(n):
            xi = X_aug[i]
            for a in range(p):
                b[a] += xi[a] * y[i]
                for cc in range(p):
                    A[a][cc] += xi[a] * xi[cc]
        # 岭正则化：给 A 对角线加 λ（偏置项索引 0 除外）
        for i in range(1, p):
            A[i][i] += effective_alpha
        w = _solve_linear(A, b, p)
        self.bias = w[0]
        self.weights = w[1:]
        self._dim = d

    def predict(self, x: list[float]) -> float:
        if not self.weights:
            raise ValueError("model not fitted")
        return self.bias + sum(w * xi for w, xi in zip(self.weights, x))

    def predict_batch(self, X: list[list[float]]) -> list[float]:
        return [self.predict(x) for x in X]


def _solve_linear(A: list[list[float]], b: list[float], n: int) -> list[float]:
    """高斯消元 + 部分主元。返回 x 长度 n。"""
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        # 主元
        pivot = col
        for row in range(col + 1, n):
            if abs(M[row][col]) > abs(M[pivot][col]):
                pivot = row
        M[col], M[pivot] = M[pivot], M[col]
        if abs(M[col][col]) < 1e-12:
            # 奇异：正则化一点
            M[col][col] += 1e-9
        # 消元
        pv = M[col][col]
        for row in range(col + 1, n):
            factor = M[row][col] / pv
            for c in range(col, n + 1):
                M[row][c] -= factor * M[col][c]
    # 回代
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        for j in range(i + 1, n):
            s -= M[i][j] * x[j]
        x[i] = s / M[i][i] if abs(M[i][i]) > 1e-15 else 0.0
    return x


# ─────────────────────────── 指标计算 ───────────────────────────

def _accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    return sum(1 for a, b in zip(y_true, y_pred) if a == b) / len(y_true)


def _f1_macro(y_true: list[str], y_pred: list[str]) -> float:
    """宏平均 F1（多类通用）。"""
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return 0.0
    f1s: list[float] = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s)


def _auroc(y_true_bin: list[int], scores: list[float]) -> float:
    """Mann-Whitner U 近似 AUROC（0/1 标签）。"""
    n_pos = sum(1 for y in y_true_bin if y == 1)
    n_neg = len(y_true_bin) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    pairs = sum(
        1 for i, yi in enumerate(y_true_bin)
        for j, yj in enumerate(y_true_bin)
        if yi == 1 and yj == 0 and scores[i] > scores[j]
    )
    half_tie = sum(
        0.5 for i, yi in enumerate(y_true_bin)
        for j, yj in enumerate(y_true_bin)
        if yi == 1 and yj == 0 and scores[i] == scores[j]
    )
    return (pairs + half_tie) / (n_pos * n_neg)


def _r2(y_true: list[float], y_pred: list[float]) -> float:
    """决定系数 R²。"""
    if not y_true:
        return 0.0
    mean = statistics.fmean(y_true)
    ss_tot = sum((y - mean) ** 2 for y in y_true)
    ss_res = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred))
    if ss_tot < 1e-18:
        return 0.0
    return 1.0 - ss_res / ss_tot


def _z_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    m = statistics.fmean(values)
    s = statistics.pstdev(values) if len(values) > 1 else 0.0
    if s < 1e-12:
        return [0.0] * len(values)
    return [(v - m) / s for v in values]


# ─────────────────────────── Harness ───────────────────────────

class ZeroShotEvalHarness:
    """零样本评测 harness。

    用法（纯 baseline）：
        h = ZeroShotEvalHarness(EvaluatorConfig(signal_type="PPG", task="classification"))
        result = h.run_baseline(dataset)   # dataset: list[SyntheticSensor]

    用法（真实模型）：
        engine = load_pulse_ppg_model(load_weights=True)  # 需用户提供权重
        result = h.run_engine(engine, dataset)
    """

    def __init__(self, config: EvaluatorConfig | None = None):
        self.config = config or EvaluatorConfig()
        self.config.validate()

    # ─── baseline ───

    def run_baseline(self, dataset: list[Any]) -> BaselineResult:
        """用 feature_baseline + 极简分类器/回归器跑 baseline。

        dataset 每项需有：
          - .samples: list[float]
          - .sample_rate_hz: float
          - .signal_type: str
          - .label: str（分类任务）或 .ground_truth_hr_bpm（回归）或 .label in {"normal","anomaly"}（异常）
        """
        if not dataset:
            raise ValueError("dataset is empty")

        cfg = self.config
        t0 = time.perf_counter()

        sensors = list(dataset)
        # 分类和异常任务都从 label 抽类别；回归从 ground_truth_hr_bpm 抽
        y_all: list[Any]
        if cfg.task == "regression":
            y_all = [float(getattr(s, "ground_truth_hr_bpm", 0.0)) for s in sensors]
        else:
            y_all = [str(getattr(s, "label", "")) for s in sensors]

        # 分 train/test（按 seed 稳定洗牌）
        idx = list(range(len(sensors)))
        rng = random.Random(cfg.random_seed)
        rng.shuffle(idx)
        n_train = max(1, int(len(sensors) * cfg.train_ratio))
        train_idx = idx[:n_train]
        test_idx = idx[n_train:]
        if not test_idx:
            # 训练集不够分：全部当训练 + 用留一法近似
            test_idx = idx[:1]

        # 特征化
        _, X_all, _ = to_feature_matrix(sensors)
        X_train = [X_all[i] for i in train_idx]
        X_test = [X_all[i] for i in test_idx]
        y_train = [y_all[i] for i in train_idx]
        y_test = [y_all[i] for i in test_idx]

        # 按 task 分派
        if cfg.task == "classification":
            k = 3 if len(y_train) >= 3 else 1
            clf = _KNNClassifier(k=k)
            clf.fit(X_train, [str(y) for y in y_train])
            y_pred = [str(p) for p in clf.predict_batch(X_test)]
            acc = _accuracy([str(y) for y in y_test], y_pred)
            f1 = _f1_macro([str(y) for y in y_test], y_pred)
            # per-class f1
            per_class: dict[str, float] = {}
            for lab in sorted({str(y) for y in y_test}):
                tp = sum(1 for t, p in zip(y_test, y_pred) if str(t) == lab and str(p) == lab)
                fp = sum(1 for t, p in zip(y_test, y_pred) if str(t) != lab and str(p) == lab)
                fn = sum(1 for t, p in zip(y_test, y_pred) if str(t) == lab and str(p) != lab)
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                per_class[lab] = round(2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0, 4)
            latency = (time.perf_counter() - t0) * 1000
            return BaselineResult(
                engine_name="baseline",
                accuracy=round(acc, 4),
                f1_macro=round(f1, 4),
                auroc=0.0,
                metric_value=round(acc, 4),
                r2=0.0,
                latency_ms=round(latency, 2),
                n_samples=len(sensors),
                details={
                    "task": "classification",
                    "n_train": len(train_idx),
                    "n_test": len(test_idx),
                    "per_class_f1": per_class,
                    "y_true_sample": [str(y) for y in y_test][:5],
                    "y_pred_sample": y_pred[:5],
                },
            )

        if cfg.task == "regression":
            reg = _LinearRegression()
            reg.fit(X_train, [float(y) for y in y_train])
            y_pred = reg.predict_batch(X_test)
            y_true = [float(y) for y in y_test]
            r2 = _r2(y_true, y_pred)
            # 归一化 MAE
            mean_y = statistics.fmean(y_true) if y_true else 0.0
            mae = statistics.fmean([abs(a - b) for a, b in zip(y_true, y_pred)]) if y_true else 0.0
            nrmse = mae / abs(mean_y) if abs(mean_y) > 1e-9 else 0.0
            latency = (time.perf_counter() - t0) * 1000
            return BaselineResult(
                engine_name="baseline",
                accuracy=0.0,
                f1_macro=0.0,
                auroc=0.0,
                metric_value=round(r2, 4),
                r2=round(r2, 4),
                latency_ms=round(latency, 2),
                n_samples=len(sensors),
                details={
                    "task": "regression",
                    "n_train": len(train_idx),
                    "n_test": len(test_idx),
                    "mae": round(mae, 4),
                    "nrmse": round(nrmse, 4),
                    "target_mean_hr": round(mean_y, 2),
                },
            )

        # anomaly：二分（label == "anomaly" 或 "abnormal" 视为正类）
        y_bin = [1 if str(y).lower() in ("anomaly", "abnormal") else 0 for y in y_all]
        # 用「normal 样本」的距离作为异常分数（正常信号 = 参考基线）
        # 关键：训练基线只用 normal 样本，否则均值被异常污染
        X_train_normal = [X_train[i] for i, lab in enumerate(y_train)
                          if str(lab).lower() not in ("anomaly", "abnormal")]
        if not X_train_normal:
            # 没有 normal 样本时退化为全部训练样本
            X_train_normal = X_train
        if X_train_normal:
            d = len(X_train_normal[0])
            mu = [statistics.fmean(row[i] for row in X_train_normal) for i in range(d)]
            # 特征尺度（std）用于 z-score 归一化，避免不同量纲主导距离
            sigma = []
            for i in range(d):
                col = [row[i] for row in X_train_normal]
                s = statistics.pstdev(col) if len(col) > 1 else 0.0
                sigma.append(s if s > 1e-12 else 1.0)
        else:
            mu = [0.0] * len(X_test[0]) if X_test else []
            sigma = [1.0] * len(mu)

        def _dist_to_baseline(x: list[float]) -> float:
            if not mu or len(x) != len(mu):
                return 0.0
            return math.sqrt(sum(
                ((v - m) / s) ** 2 for v, m, s in zip(x, mu, sigma)
            ))

        scores = [_dist_to_baseline(x) for x in X_test]
        y_test_bin = [y_bin[i] for i in test_idx]
        auroc = _auroc(y_test_bin, scores) if y_test_bin else 0.0
        # 阈值取 normal 训练集距离的 95 分位
        train_scores = [_dist_to_baseline(x) for x in X_train_normal]
        if train_scores:
            sorted_s = sorted(train_scores)
            thr = sorted_s[max(0, int(len(sorted_s) * 0.95) - 1)]
        else:
            thr = 0.0
        y_pred = ["anomaly" if s > thr else "normal" for s in scores]
        y_true_labels = ["anomaly" if y == 1 else "normal" for y in y_test_bin]
        acc = _accuracy(y_true_labels, y_pred)
        f1 = _f1_macro(y_true_labels, y_pred)
        latency = (time.perf_counter() - t0) * 1000
        return BaselineResult(
            engine_name="baseline",
            accuracy=round(acc, 4),
            f1_macro=round(f1, 4),
            auroc=round(auroc, 4),
            metric_value=round(auroc, 4),
            r2=0.0,
            latency_ms=round(latency, 2),
            n_samples=len(sensors),
            details={
                "task": "anomaly",
                "n_train": len(train_idx),
                "n_train_normal": len(X_train_normal),
                "n_test": len(test_idx),
                "n_pos_test": sum(1 for y in y_test_bin if y == 1),
                "n_neg_test": sum(1 for y in y_test_bin if y == 0),
                "threshold": round(thr, 4),
            },
        )

    # ─── 真实模型接口 ───

    def run_engine(self, engine: Any, dataset: list[Any]) -> BaselineResult:
        """用真实引擎（Pulse-PPG / PaPaGei 等）跑评测。

        当前未装真实权重时抛 `HealthLensUnavailableEngine`——fail-loud，
        不静默降级。用户装了真实模型后可把 engine 传入，harness 会用其
        输出做零样本评测。

        engine 契约（可选 duck-typing）：
        - `engine["engine_name"]: str`
        - `engine["predict"](X: list[list[float]]) -> list[float]` 或 `-> list[str]`
        - 或 `engine["embedding"](x: list[float]) -> list[float]`
        """
        if engine is None:
            raise HealthLensUnavailableEngine(
                "engine is None; install real Pulse-PPG / PaPaGei weights and pass engine dict. "
                "See app/lib/sensor_adapter.py load_pulse_ppg_model() / load_papagei_model()."
            )
        engine_name = getattr(engine, "engine_name", None) or engine.get("engine_name") if isinstance(engine, dict) else getattr(engine, "engine_name", None)
        if not engine_name:
            raise HealthLensUnavailableEngine("engine missing 'engine_name'")

        predict_fn = None
        if isinstance(engine, dict):
            predict_fn = engine.get("predict")
        else:
            predict_fn = getattr(engine, "predict", None)
        if predict_fn is None:
            raise HealthLensUnavailableEngine(
                f"engine {engine_name!r} has no 'predict' callable; "
                "install real Pulse-PPG / PaPaGei weights (see sensor_adapter.py)."
            )

        if not dataset:
            raise ValueError("dataset is empty")

        cfg = self.config
        t0 = time.perf_counter()

        sensors = list(dataset)
        if cfg.task == "regression":
            y_all = [float(getattr(s, "ground_truth_hr_bpm", 0.0)) for s in sensors]
        else:
            y_all = [str(getattr(s, "label", "")) for s in sensors]

        idx = list(range(len(sensors)))
        rng = random.Random(cfg.random_seed)
        rng.shuffle(idx)
        n_train = max(1, int(len(sensors) * cfg.train_ratio))
        train_idx = idx[:n_train]
        test_idx = idx[n_train:]
        if not test_idx:
            test_idx = idx[:1]

        _, X_all, _ = to_feature_matrix(sensors)
        X_test = [X_all[i] for i in test_idx]

        preds = predict_fn(X_test)  # type: ignore[misc]
        y_test = [y_all[i] for i in test_idx]

        if cfg.task == "regression":
            y_pred = [float(p) for p in preds]
            r2 = _r2([float(y) for y in y_test], y_pred)
            return BaselineResult(
                engine_name=str(engine_name),
                accuracy=0.0, f1_macro=0.0, auroc=0.0,
                metric_value=round(r2, 4), r2=round(r2, 4),
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                n_samples=len(sensors),
                details={"task": "regression", "engine_name": str(engine_name)},
            )

        if cfg.task == "anomaly":
            scores = [float(p) for p in preds]
            y_bin = [1 if str(y).lower() in ("anomaly", "abnormal") else 0 for y in y_test]
            auroc = _auroc(y_bin, scores) if y_bin else 0.0
            return BaselineResult(
                engine_name=str(engine_name),
                accuracy=0.0, f1_macro=0.0, auroc=round(auroc, 4),
                metric_value=round(auroc, 4),
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                n_samples=len(sensors),
                details={"task": "anomaly", "engine_name": str(engine_name)},
            )

        # classification
        y_pred = [str(p) for p in preds]
        acc = _accuracy([str(y) for y in y_test], y_pred)
        f1 = _f1_macro([str(y) for y in y_test], y_pred)
        return BaselineResult(
            engine_name=str(engine_name),
            accuracy=round(acc, 4), f1_macro=round(f1, 4), auroc=0.0,
            metric_value=round(acc, 4),
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            n_samples=len(sensors),
            details={"task": "classification", "engine_name": str(engine_name)},
        )

    # ─── 对比报告 ───

    @staticmethod
    def compare(results: list[BaselineResult]) -> dict[str, Any]:
        """横向对比多个结果，生成 Markdown 表格 + 总结。

        Returns:
            {
              "rows": list[BaselineResult],
              "markdown_table": str,
              "best_accuracy": str,
              "best_f1_macro": str,
              "best_auroc": str,
              "summary": str,
            }
        """
        if not results:
            return {
                "rows": [],
                "markdown_table": "",
                "best_accuracy": None,
                "best_f1_macro": None,
                "best_auroc": None,
                "summary": "no results",
            }
        header = "| engine | accuracy | f1_macro | auroc | r2 | latency_ms | n_samples |"
        sep = "| --- | --- | --- | --- | --- | --- | --- |"
        rows = [r.to_markdown_row() for r in results]
        table = "\n".join([header, sep, *rows])

        def _best(key: str, min_val: float = -1.0) -> str | None:
            candidates = [r for r in results if r.__getattribute__(key) >= min_val]
            if not candidates:
                return None
            return max(candidates, key=lambda r: r.__getattribute__(key)).engine_name

        return {
            "rows": results,
            "markdown_table": table,
            "best_accuracy": _best("accuracy", 0.0) if any(r.accuracy > 0 for r in results) else None,
            "best_f1_macro": _best("f1_macro", 0.0) if any(r.f1_macro > 0 for r in results) else None,
            "best_auroc": _best("auroc", 0.0) if any(r.auroc > 0 for r in results) else None,
            "summary": (
                f"{len(results)} result(s) compared; best accuracy: "
                f"{_best('accuracy', 0.0) or 'n/a'}; "
                f"best f1_macro: {_best('f1_macro', 0.0) or 'n/a'}; "
                f"best auroc: {_best('auroc', 0.0) or 'n/a'}."
            ),
        }


__all__ = [
    "EvaluatorConfig",
    "BaselineResult",
    "ZeroShotEvalHarness",
    "_KNNClassifier",
    "_LinearRegression",
    "_accuracy",
    "_f1_macro",
    "_auroc",
    "_r2",
]
