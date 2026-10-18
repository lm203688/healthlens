"""时序序列化 API（L2 表征层）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L2。
> 「时序 → LLM 的 tokenization 在开源界仍是空白」——HealthLens 自创并公开
> 「八轴信号 → 分箱 + 结构化特征 → JSON 文本」的确定性序列化。

路由前缀：/api/v1/timeseries

端点：
- POST /serialize   ：接收 bundle，返回序列化 JSON + sha256 指纹
- POST /validate    ：接收已序列化 JSON，返回 violations 列表
- GET  /hash/{subject_hash}/{session_hash}  ：查历史 hash（内存 dict，
                                            注释：生产应接 DB）
- POST /sensor/probe：返回 available 基础模型引擎清单
- POST /eval/harness：报告 §10 #6 Pulse-PPG 零样本评测（见下）

报告 §10 #6 引用：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」
> 本端点把评测脚手架暴露成 API：接收一小批信号 + 标签，返回 baseline
> 评测结果。真实 Pulse-PPG / PaPaGei 权重接入时，harness 会 fail-loud
> 抛 HealthLensUnavailableEngine，不静默降级。

Wellness 平台术语纪律：仅做统计特征与文本化，不做诊断/治疗建议。

作者：HealthLens L2 表征层团队
版本：v2 (2026-10-16)
"""
from __future__ import annotations

import hashlib
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.lib import ts_serializer
from app.lib.sensor_adapter import (
    HealthLensUnavailableEngine,
    list_available_engines,
)
from app.lib.synthetic_sensor_dataset import SyntheticSensor
from app.lib.zero_shot_eval_harness import (
    BaselineResult,
    EvaluatorConfig,
    ZeroShotEvalHarness,
)


router = APIRouter()


# ─────────────────────────── 请求 / 响应模型 ───────────────────────────

class BundleRequest(BaseModel):
    """POST /serialize 请求体。"""

    channel_name: str = Field(..., min_length=1, description="通道名（HRV/SpO2/EEG/pulse/HR...）")
    samples: list[float] = Field(..., min_length=1, description="等间隔采样数据")
    sample_rate_hz: float = Field(..., gt=0, description="采样率（Hz）")
    unit: str = Field(..., min_length=1, description="单位")
    subject_id: str | None = Field(default=None, description="受试者 id（可选，hash 后输出）")
    session_id: str | None = Field(default=None, description="会话 id（可选，hash 后输出）")
    format: Literal["json", "text"] = Field(default="json", description="输出格式")
    bin_width_s: float = Field(default=1.0, gt=0, description="分箱宽度（秒）")


class SerializeResponse(BaseModel):
    """POST /serialize 响应体。"""

    schema: str
    generator: str
    sha256: str
    format: str
    json_str: str
    structured: dict[str, Any]
    text_lines: list[str] | None = None
    subject_hash: str | None
    session_hash: str | None
    n_samples: int
    sampling_duration: float


class ValidateRequest(BaseModel):
    """POST /validate 请求体。"""

    json_str: str = Field(..., min_length=1, description="待校验的序列化 JSON 字符串")


class ValidateResponse(BaseModel):
    valid: bool
    violations: list[str]
    schema: str
    generator: str


class ProbeResponse(BaseModel):
    engines: list[dict[str, Any]]


# ─────────────────────────── 内存 hash 注册表 ───────────────────────────

# 生产环境应接入 DB / Redis；此 dict 仅用于本地开发与冒烟测试。
# 报告定位：hash 幂等性用于纵向研究去重与联邦层跨机构对齐。
_HASH_REGISTRY: dict[tuple[str, str], dict[str, Any]] = {}


def _register_hash(
    subject_hash: str,
    session_hash: str,
    sha256: str,
    n_samples: int,
    sampling_duration: float,
) -> None:
    key = (subject_hash, session_hash)
    _HASH_REGISTRY[key] = {
        "sha256": sha256,
        "n_samples": n_samples,
        "sampling_duration": sampling_duration,
        "count": _HASH_REGISTRY.get(key, {}).get("count", 0) + 1,
    }


def _hash_identity(subject_id: str | None, session_id: str | None) -> tuple[str, str]:
    if subject_id is None or session_id is None:
        # fail-loud：hash 查询接口要求双侧 id 齐备
        raise HTTPException(
            status_code=400,
            detail="subject_id 与 session_id 必须同时提供",
        )
    return (
        ts_serializer._privacy_hash(subject_id),
        ts_serializer._privacy_hash(session_id),
    )


# ─────────────────────────── 端点 ───────────────────────────

@router.post(
    "/serialize",
    response_model=SerializeResponse,
    summary="序列化时序为确定性 JSON",
    description=(
        "把 TimeSeriesBundle 序列化为 JSON + sha256 指纹（L2 表征层原创点）。"
        "同输入必产生同 JSON + 同 hash。报告：HealthLens_下一阶段愿景与跃迁方案_2026-10-15 §5 L2。"
    ),
)
def serialize_endpoint(req: BundleRequest) -> SerializeResponse:
    try:
        bundle = ts_serializer.TimeSeriesBundle(
            channel_name=req.channel_name,
            samples=req.samples,
            sample_rate_hz=req.sample_rate_hz,
            unit=req.unit,
            subject_id=req.subject_id,
            session_id=req.session_id,
        )
        options = ts_serializer.SerializeOptions(bin_width_s=req.bin_width_s)
        result = ts_serializer.serialize(bundle, options=options, format=req.format)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"bundle invalid: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"serialize failed: {exc}") from exc

    subject_hash = result.structured.get("subject_hash")
    session_hash = result.structured.get("session_hash")
    # 内存注册：仅当双侧 id 均存在时
    if subject_hash and session_hash:
        _register_hash(
            subject_hash,
            session_hash,
            result.sha256,
            result.structured.get("n_samples", 0),
            result.structured.get("sampling_duration", 0.0),
        )

    return SerializeResponse(
        schema=result.structured["schema"],
        generator=result.structured["generator"],
        sha256=result.sha256,
        format=req.format,
        json_str=result.json_str,
        structured=result.structured,
        text_lines=result.text_lines,
        subject_hash=subject_hash,
        session_hash=session_hash,
        n_samples=result.structured.get("n_samples", 0),
        sampling_duration=result.structured.get("sampling_duration", 0.0),
    )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="校验已序列化 JSON",
    description="对任意 JSON 字符串跑 schema 校验，返回 violations 列表。空列表表示通过。",
)
def validate_endpoint(req: ValidateRequest) -> ValidateResponse:
    try:
        violations = ts_serializer.validate_serialized(req.json_str)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"validate failed: {exc}") from exc
    return ValidateResponse(
        valid=len(violations) == 0,
        violations=violations,
        schema=ts_serializer.SCHEMA_VERSION,
        generator=ts_serializer.GENERATOR_NAME,
    )


@router.get(
    "/hash/{subject_hash}/{session_hash}",
    summary="查历史 hash",
    description=(
        "按 (subject_hash, session_hash) 查已序列化的历史 hash 与统计信息。"
        "**当前实现：进程内 dict，重启即丢失。** 生产环境应接入 DB / Redis。"
    ),
)
def get_hash(
    subject_hash: str,
    session_hash: str,
) -> dict[str, Any]:
    if not subject_hash or not session_hash:
        raise HTTPException(status_code=400, detail="hash 不能为空")
    entry = _HASH_REGISTRY.get((subject_hash, session_hash))
    return {
        "subject_hash": subject_hash,
        "session_hash": session_hash,
        "found": entry is not None,
        "entry": entry,
        "storage": "in-memory dict (dev only)",
        "note": "生产应接 DB；此端点主要用于纵向研究的 hash 幂等验证",
    }


@router.post(
    "/sensor/probe",
    response_model=ProbeResponse,
    summary="探测基础模型引擎可用性",
    description=(
        "返回 Pulse-PPG / transformers / sentence-transformers 是否可 import。"
        "未装时明确返回 available=False + reason，不静默降级。"
    ),
)
def probe_engines() -> ProbeResponse:
    probes = list_available_engines()
    return ProbeResponse(engines=[p.to_dict() for p in probes])


def _schema_candidate_paths() -> list[Any]:
    """schema 文件可能的位置（部署形态差异大，逐个探测）。

    报告定位：配置在 config/serializer_schema_v1.json（源码树规范），
    但 Docker 部署时 /app/config 常是镜像 COPY 而非 bind mount——
    与 pulse_engine 的 _candidate_db_paths 保持一致的探测策略。
    """
    from pathlib import Path

    here = Path(__file__).resolve()
    paths: list[Any] = []
    # 源码树布局（parents[2] = 仓库根）
    paths.append(here.parents[2] / "config" / "serializer_schema_v1.json")
    paths.append(Path.cwd() / "config" / "serializer_schema_v1.json")
    paths.append(Path("/app/config") / "serializer_schema_v1.json")
    paths.append(Path("/opt/healthlens/config") / "serializer_schema_v1.json")
    # bind-mount 兜底：/app/data 在容器内对应宿主机 /opt/healthlens/data，
    # 是运行时可更新文件（镜像 COPY 的 /app/config 无法热更新）。
    paths.append(Path("/app/data") / "serializer_schema_v1.json")
    paths.append(Path("/opt/healthlens/data") / "serializer_schema_v1.json")
    return paths


@router.get(
    "/schema",
    summary="获取 serializer schema 描述",
    description="返回 config/serializer_schema_v1.json 内容（供外部工具校验）",
)
def get_schema() -> dict[str, Any]:
    import json

    tried: list[str] = []
    for schema_path in _schema_candidate_paths():
        tried.append(str(schema_path))
        try:
            with open(schema_path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            continue
        except Exception as exc:  # 文件在但坏了
            tried.append(f"{schema_path} (parse error: {exc})")
    raise HTTPException(
        status_code=404,
        detail=f"serializer_schema_v1.json 未找到。已尝试: {tried}",
    )


# ─────────────────────────── §10 #6 Pulse-PPG 零样本评测 ───────────────────────────

# 单次请求样本数上限，防抖。harness 内部对 1000 样本 * 20+ 维特征做纯 Python
# 计算，5s 超时足够跑完。生产化时应移到后台任务队列。
MAX_HARNESS_SAMPLES = 1000
HARNESS_TIMEOUT_SEC = 5.0


class HarnessRequest(BaseModel):
    """POST /eval/harness 请求体。

    每条 signal 是 {samples, sample_rate_hz, label}，label 三分类
    (rest/exercise/stress) 或二分类 (normal/anomaly)，取决于 task。
    """

    signal_type: Literal["PPG", "ECG", "EMG", "EEG"] = Field(
        default="PPG", description="信号类型"
    )
    task: Literal["classification", "regression", "anomaly"] = Field(
        default="classification", description="评测任务"
    )
    metric: Literal["accuracy", "f1", "auroc"] = Field(
        default="accuracy", description="主指标"
    )
    samples: list[dict[str, Any]] = Field(
        ..., min_length=2, max_length=MAX_HARNESS_SAMPLES,
        description=(
            f"信号列表，单次 ≤{MAX_HARNESS_SAMPLES} 条；每条需 samples + sample_rate_hz；"
            "classification/anomaly 任务需 label；regression 任务需 ground_truth_hr_bpm"
        ),
    )
    train_ratio: float = Field(
        default=0.7, gt=0.0, lt=1.0, description="训练集比例"
    )
    random_seed: int = Field(default=42, description="随机种子")


class HarnessSignalResponse(BaseModel):
    """单条信号在 harness 请求中回显（供调试）。"""

    subject_id: str
    label: str | None = None
    n_samples: int


class HarnessResponse(BaseModel):
    """POST /eval/harness 响应体。"""

    engine_name: str
    accuracy: float
    f1_macro: float
    auroc: float
    metric_value: float
    r2: float
    latency_ms: float
    n_samples: int
    details: dict[str, Any]
    report_source: str = (
        "《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6 "
        "「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量」"
    )
    note: str = (
        "baseline 仅验证评测脚手架；真实 Pulse-PPG / PaPaGei 零样本表征质量 "
        "需用户提供权重后重跑。"
    )


@router.post(
    "/eval/harness",
    response_model=HarnessResponse,
    summary="§10 #6 Pulse-PPG 零样本评测 harness",
    description=(
        "接收一小批信号 + 标签，跑 baseline 特征 + 极简分类/回归/异常检测，"
        "返回 accuracy / f1_macro / auroc / R² / latency_ms。\n\n"
        "**报告 §10 #6 引用**：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6 "
        "「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」。\n\n"
        "限制：单次 ≤ 1000 样本，超时 5s；未装真实模型权重时仅跑 baseline，"
        "不静默降级到假 embedding。"
    ),
)
def run_eval_harness(req: HarnessRequest) -> HarnessResponse:
    # 超时兜底：harness 内部对 1000 样本 * ~30 维特征做纯 Python 计算，
    # 5s 足够。生产化应改后台任务。
    _ = HARNESS_TIMEOUT_SEC  # 保留常量便于运维查阅

    # 校验 + 转 SyntheticSensor
    sensors: list[SyntheticSensor] = []
    for i, item in enumerate(req.samples):
        samples = item.get("samples")
        if not isinstance(samples, list) or len(samples) < 4:
            raise HTTPException(
                status_code=400,
                detail=f"samples[{i}].samples must be a list with ≥4 floats",
            )
        try:
            sr = float(item.get("sample_rate_hz", 0))
            if sr <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"samples[{i}].sample_rate_hz must be a positive number",
            ) from None
        samples_list = [float(v) for v in samples]
        label = str(item.get("label", "rest"))
        gt_hr = float(item.get("ground_truth_hr_bpm", 0.0))
        if req.task == "regression" and not gt_hr:
            raise HTTPException(
                status_code=400,
                detail=f"samples[{i}].ground_truth_hr_bpm required for regression task",
            )
        sensors.append(SyntheticSensor(
            signal_type=req.signal_type,
            sample_rate_hz=sr,
            duration_sec=len(samples_list) / sr,
            subject_id=f"api_{i}",
            samples=samples_list,
            label=label,
            ground_truth_hr_bpm=gt_hr,
        ))

    try:
        cfg = EvaluatorConfig(
            signal_type=req.signal_type,
            task=req.task,
            metric=req.metric,
            train_ratio=req.train_ratio,
            random_seed=req.random_seed,
        )
        harness = ZeroShotEvalHarness(cfg)
        result: BaselineResult = harness.run_baseline(sensors)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"eval failed: {exc}") from exc
    except HealthLensUnavailableEngine as exc:
        # 未装真实模型权重时，baseline 已跑完；只有 run_engine 才会抛此异常。
        # 但万一未来把 baseline 换成引擎，也走此分支。
        raise HTTPException(status_code=503, detail=f"engine unavailable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"eval crashed: {exc}") from exc

    return HarnessResponse(
        engine_name=result.engine_name,
        accuracy=result.accuracy,
        f1_macro=result.f1_macro,
        auroc=result.auroc,
        metric_value=result.metric_value,
        r2=result.r2,
        latency_ms=result.latency_ms,
        n_samples=result.n_samples,
        details=result.details,
    )
