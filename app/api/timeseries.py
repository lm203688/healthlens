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

Wellness 平台术语纪律：仅做统计特征与文本化，不做诊断/治疗建议。

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-15)
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
    # bind-mount 兜底：/opt/healthlens/data 常是 bind mount，可放镜像外更新的文件
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
