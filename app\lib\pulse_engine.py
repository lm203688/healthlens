"""脉象解读引擎（云端）

输入：号脉硬件经边缘盒上送的 hl.pulse.* 特征（见 data/pulse_signatures.json 的
      device_output_contract）。
输出：多标签脉象判定 + 八轴信号 + 养生参考 + 健康护栏。

定位：养生参考 / 健康信号，不构成医学诊断。所有结论带 guardrail。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_FILENAME = "pulse_signatures.json"


def _candidate_db_paths() -> list[Path]:
    """知识库可能的位置（部署形态差异大，逐个探测）。

    - HL_PULSE_DB：运维显式指定，最高优先级
    - <repo>/data/：源码树布局（parents[2] = 仓库根）
    - CWD/data/、/app/data/：容器里 data/ 常是镜像 COPY 而非 bind mount
    """
    here = Path(__file__).resolve()
    paths: list[Path] = []
    env = os.getenv("HL_PULSE_DB", "").strip()
    if env:
        paths.append(Path(env))
    paths.append(here.parents[2] / "data" / _DB_FILENAME)
    paths.append(Path.cwd() / "data" / _DB_FILENAME)
    paths.append(Path("/app/data") / _DB_FILENAME)
    return paths


def _load_db() -> dict:
    for path in _candidate_db_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except Exception as exc:  # 文件在但坏了
            logger.warning(f"[pulse_engine] 知识库 {path} 解析失败: {exc}")
            continue
        if data.get("pulses"):
            logger.info(f"[pulse_engine] 知识库已加载: {path}（{len(data['pulses'])} 脉）")
            return data
    # 降级不是「返回空库」而是「明确不可用」：空库会让 28 脉全部退化成 id、
    # 八轴清空、养生参考丢文案，产出一个看起来正常的假结论。宁可显式失败。
    logger.error(
        "[pulse_engine] 脉象知识库未找到或为空，脉象解读不可用。"
        "已尝试: %s；可用 HL_PULSE_DB 指定路径",
        [str(p) for p in _candidate_db_paths()],
    )
    return {}


_DB = _load_db()
# 库不可用时，classify_pulse 直接报错而不是给假结论
DB_AVAILABLE = bool(_DB.get("pulses"))

# 危急脉象：触发强护栏、引导就医
_ALERT_PULSES = {"ji", "wei", "san", "dai"}
# 需关注：持续出现应留意
_WATCH_PULSES = {"xian", "se", "jie", "cu", "chen", "xu", "ruo", "ge", "lao", "fu_v"}


def _pulse_meta(pid: str) -> dict:
    for p in _DB.get("pulses", []):
        if p["id"] == pid:
            return p
    return {}


_COMPOUND_INDEX: dict[frozenset, dict] = {}


class PulseKnowledgeBaseError(RuntimeError):
    """知识库缺失/损坏时抛出。宁可报错也不产出假解读。"""
for _ex in _DB.get("compound_examples", []) or []:
    _comp = frozenset(_ex.get("compose", []))
    if len(_comp) >= 2:
        _COMPOUND_INDEX[_comp] = _ex


def _compound_pulse(ids: set[str]) -> dict | None:
    """查相兼脉（如弦+滑 -> 弦滑）。

    临床多兼见，单标签会丢失组合语义。命中组合时 confidence 取两脉较低者再打折，
    因为组合的确定性低于两个单脉各自独立成立。
    """
    if len(ids) < 2:
        return None
    ex = _COMPOUND_INDEX.get(frozenset(ids))
    if not ex:
        return None
    return {
        "id": "compound:" + "+".join(sorted(ids)),
        "name": ex.get("name", "相兼脉"),
        "confidence": 0.0,  # 由调用方按单脉置信填充
        "category": "相兼",
        "compose": sorted(ids),
        "ref": ex.get("ref", ""),
    }


def _f(features: dict, key: str, default: float | None = None) -> float | None:
    v = features.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def classify_pulse(features: dict[str, Any]) -> dict[str, Any]:
    """规则式多标签脉象判定。

    返回：
    {
      "labels": [{"id","name","confidence","category"}],
      "compounds": [{"name","confidence","compose","ref"}],  # 相兼脉
      "axis_signals": {"A":0.6, ...},   # 命中的八轴及强度
      "severity": "normal|watch|alert",
      "wellness_ref": "...",
      "guardrail": "...",
      "db_available": True,
    }
    """
    if not DB_AVAILABLE:
        # 宁可显式失败，也不给一个标签名退化、八轴全空的假结论
        raise PulseKnowledgeBaseError(
            "脉象知识库未加载，无法给出可信解读（脉象解读服务暂不可用）"
        )

    rate = _f(features, "hl.pulse.rate_bpm")
    h1 = _f(features, "hl.pulse.h1")
    h3_h1 = _f(features, "hl.pulse.h3_h1")
    h4_h1 = _f(features, "hl.pulse.h4_h1")
    h5_h1 = _f(features, "hl.pulse.h5_h1")
    dicrotic = _f(features, "hl.pulse.dicrotic_present", 0.0)
    slope = _f(features, "hl.pulse.ascending_slope")
    perf = _f(features, "hl.pulse.perfusion_index")
    rhythm = _f(features, "hl.pulse.rhythm_regularity", 1.0)
    pause = str(features.get("hl.pulse.pause_pattern", "none") or "none").lower()
    depth = str(features.get("hl.pulse.depth", "") or "").lower()

    labels: list[dict[str, Any]] = []
    axis_signals: dict[str, float] = {}

    def add(pid: str, conf: float):
        meta = _pulse_meta(pid)
        labels.append({
            "id": pid,
            "name": meta.get("name", pid),
            "confidence": round(conf, 2),
            "category": meta.get("category", ""),
        })
        for ax in meta.get("axes", []):
            axis_signals[ax] = max(axis_signals.get(ax, 0.0), conf)

    # —— 数纲（频率）——
    if rate is not None:
        if rate > 100:
            add("ji", 0.9)
        elif rate > 90:
            add("shu", 0.85)
        elif rate < 60:
            add("chi", 0.85)
        elif rate < 70:
            add("huan", 0.6)

    # —— 形纲（波形）——
    if h1 is not None:
        if h1 >= 0.8 and (h3_h1 is None or h3_h1 < 0.5):
            add("hong", 0.7)
        elif h1 < 0.2:
            add("wei", 0.85)
        elif h1 < 0.4:
            add("xi", 0.7)
            if depth == "deep":
                add("ruo", 0.6)
    if h3_h1 is not None and h3_h1 >= 0.8:
        add("xian", 0.8)
    if dicrotic is not None:
        # 滑脉：高振幅 + 重搏切迹清晰 + 不紧张（h3/h1 不高）；避免与平脉混淆
        if dicrotic >= 0.5 and (h1 is not None and h1 >= 0.72) and (h3_h1 is None or h3_h1 < 0.75):
            add("hua", 0.65)
        # 涩脉：重搏切迹缺失/模糊（dicrotic 低，或 h4/h1 重搏切迹比明显偏低）
        # —— 两者都指向血管壁弹性差、血流不畅；取更强的一条证据。
        elif dicrotic < 0.5 or (h5_h1 is not None and h5_h1 < 0.2):
            add("se", 0.6)
        elif h4_h1 is not None and h4_h1 < 0.35:
            add("se", 0.55)
    if slope is not None:
        if slope >= 0.7 and (h1 is None or h1 >= 0.6):
            add("shi", 0.6)
        elif slope <= 0.3 and (h1 is None or h1 < 0.5):
            add("xu", 0.6)

    # —— 位纲（深度）——
    if depth == "superficial":
        add("fu", 0.7)
    elif depth == "deep":
        add("chen", 0.7)
    elif perf is not None:
        # 无显式 depth 时，用灌注指数近似：低灌注且在浅压弱 → 偏沉
        if perf < 0.3:
            add("chen", 0.4)

    # —— 律纲（节律）——
    if pause == "irregular":
        if rate is not None and rate < 60:
            add("jie", 0.8)
        elif rate is not None and rate > 90:
            add("cu", 0.8)
        else:
            add("jie", 0.5)
    elif pause == "regular":
        add("dai", 0.85)
    elif rhythm is not None and rhythm < 0.6:
        add("jie", 0.4)

    # 去重（按 id 保留最高置信）
    by_id: dict[str, dict] = {}
    for lab in labels:
        cur = by_id.get(lab["id"])
        if cur is None or lab["confidence"] > cur["confidence"]:
            by_id[lab["id"]] = lab
    labels = sorted(by_id.values(), key=lambda x: -x["confidence"])

    # —— 相兼脉合成 ——
    # 临床多兼见（弦滑 / 沉细迟…）。只给独立标签会丢掉组合语义，
    # 而组合的养生含义常与单脉不同（弦+滑 = 痰热食积，不是单纯肝郁）。
    compounds: list[dict[str, Any]] = []
    if _COMPOUND_INDEX and len(by_id) >= 2:
        conf = {lab["id"]: lab["confidence"] for lab in labels}
        hit_ids = [i for i, c in conf.items() if c >= 0.6]
        # 两两组合命中即可（临床常见三脉相兼，逐一枚举代价高且过拟合）
        for a_i in range(len(hit_ids)):
            for b_i in range(a_i + 1, len(hit_ids)):
                ex = _COMPOUND_INDEX.get(frozenset((hit_ids[a_i], hit_ids[b_i])))
                if not ex:
                    continue
                pair_conf = round(min(conf[hit_ids[a_i]], conf[hit_ids[b_i]]) * 0.9, 2)
                compounds.append({
                    "name": ex.get("name", "相兼脉"),
                    "confidence": pair_conf,
                    "compose": sorted([hit_ids[a_i], hit_ids[b_i]]),
                    "ref": ex.get("ref", ""),
                })
        compounds.sort(key=lambda x: -x["confidence"])
        compounds = compounds[:3]

    # —— 严重度 ——
    ids = {lab["id"] for lab in labels}
    severity = "normal"
    if ids & _ALERT_PULSES:
        severity = "alert"
    elif ids & _WATCH_PULSES:
        severity = "watch"

    # —— 养生参考 / 健康护栏 ——
    wellness_parts = []
    guardrail_parts = []
    for lab in labels:
        meta = _pulse_meta(lab["id"])
        if meta.get("wellness_ref"):
            wellness_parts.append(f"{meta['name']}：{meta['wellness_ref']}")
        if meta.get("guardrail"):
            guardrail_parts.append(f"{meta['name']}：{meta['guardrail']}")

    if not labels:
        wellness_ref = "本次脉象特征处于常见范围，可作为养生基线参考。"
        guardrail = "本结论为健康信号参考，非医学诊断；如感不适请咨询注册中医师。"
    else:
        parts = list(wellness_parts) or ["脉象特征已采集，建议结合日常作息综合判断。"]
        # 相兼脉的参考优先于单脉：临床以兼见为主，单脉含义常被组合改写
        for cp in compounds:
            if cp.get("ref"):
                parts.insert(0, f"相兼 {cp['name']}：{cp['ref']}")
        wellness_ref = "；".join(parts)
        if severity == "alert":
            guardrail = ("⚠️ 检测到需关注的脉象信号（" +
                         "、".join(_pulse_meta(lab["id"]).get("name", lab["id"]) for lab in labels if lab["id"] in _ALERT_PULSES) +
                         "），本平台不做诊断，请尽快咨询专业医师。")
        elif severity == "watch":
            guardrail = "；".join(guardrail_parts) if guardrail_parts else "本次信号偏偏离常见范围，建议关注作息与情绪，持续异常请就医。"
        else:
            guardrail = "本结论为健康信号参考，非医学诊断；如感不适请咨询注册中医师。"

    return {
        "labels": labels,
        "compounds": compounds,
        "axis_signals": {k: round(v, 2) for k, v in sorted(axis_signals.items())},
        "severity": severity,
        "wellness_ref": wellness_ref,
        "guardrail": guardrail,
        "db_available": True,
    }


def build_pulse_observation(features: dict[str, Any], user_ref: str, day: str) -> dict[str, Any]:
    """把一次号脉解读结果包装成 HealthObservation 风格记录，便于进八轴。"""
    interp = classify_pulse(features)
    return {
        "source": f"pulse_gateway:{user_ref}",
        "recorded_at": day,
        "pulse_labels": [lab["id"] for lab in interp["labels"]],
        "axis_signals": interp["axis_signals"],
        "severity": interp["severity"],
        "wellness_ref": interp["wellness_ref"],
        "guardrail": interp["guardrail"],
        "raw_features": {k: v for k, v in features.items() if k.startswith("hl.pulse.")},
    }
