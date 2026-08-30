"""
HealthLens 个性化融合引擎 v0.3（moat 脚手架 + LLM 增强）
============================================
v0.3 新增（2026-08-27）：
  - USE_LLM=1 时调用本地 Ollama 模型对处方文本做语义增强（个人化、自然化）
  - 失败静默回退到规则引擎，永不阻断主流程
  - LLM 模型名通过 HEALTHLENS_LLM_MODEL 环境变量配置（默认 qwen3.8）
"""
from __future__ import annotations
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "case_evidence_db.json")
MAP_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tcm_pathway_map.json")
EVIDENCE_WEIGHT = {"L1": 3, "L2": 2, "L3": 1}

# 载入规范化映射
with open(MAP_PATH, encoding="utf-8") as _f:
    _MAP = json.load(_f)
_AXIS_LABEL = _MAP.get("axis_labels", {})
_ALIASES = _MAP.get("aliases", {})
_AXIS_PATHWAYS = _MAP.get("axis_pathways", {})
# 规范通路 → 轴
_CANON_TO_AXIS = {}
for _ax, _paths in _AXIS_PATHWAYS.items():
    for _p in _paths:
        _CANON_TO_AXIS[_p] = _ax


def _norm(s: str) -> str:
    """归一化：去非字母数字、转小写。'Circadian_CLOCK_BMAL1' → 'circadianclockbmal1'。"""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canon(token: str) -> str:
    """token → 规范通路键（自带别名回退）。未知 token 原样返回归一化串。"""
    n = _norm(token)
    return _ALIASES.get(n, n)


def canon_to_axis(canonical: str) -> Optional[str]:
    return _CANON_TO_AXIS.get(canonical)


@dataclass
class UserProfile:
    # 基因/组学：通路级得分（0-1），<0.5 视为弱项；禁 SNP 级
    pathway_scores: dict[str, float] = field(default_factory=dict)
    # 也可直接给弱项轴字母（A-H）
    weak_axes: set[str] = field(default_factory=set)
    # 个体禁忌（命中即排除相关建议）
    contraindications: set[str] = field(default_factory=set)


@dataclass
class Recommendation:
    case_id: str
    targeted_pathway: str        # ⑦字段①
    tcm_source: str              # ⑦字段②
    gene_relevance: str          # ⑦字段③
    evidence_level: str          # ⑦字段④
    contraindication: str        # ⑦字段⑤
    monitor_markers: str         # ⑦字段⑥
    prescription: str            # ⑦字段⑦
    mode: str = "personalized"   # personalized / general
    score: float = 0.0


def load_cases(path: str = DB_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["cases"]


def _pathway_tokens(case: dict) -> set[str]:
    return {canon(t) for t in case.get("gene_pathway", [])}


def _axes(case: dict) -> set[str]:
    axes = case.get("axes", []) or []
    ax = case.get("axis")
    if ax and ax not in axes:
        axes.append(ax)
    return {a.upper() for a in axes}


def _contra_hit(case: dict, user_contra: set[str]) -> Optional[str]:
    blob = " ".join([case.get("gene_link", ""), case.get("mechanism", "")])
    for kw in user_contra:
        if kw in blob:
            return kw
    return None


def _llm_enhance_prescription(text: str, context: str) -> str:
    """用本地 LLM 对处方文本做个人化语义增强。失败返回原文。"""
    try:
        model = os.environ.get("HEALTHLENS_LLM_MODEL", "qwen3.8")
        url = f"http://127.0.0.1:11434/api/generate"
        prompt = (
            f"你是一个中医健康顾问。用户的健康背景：{context}\n"
            f"请基于以下建议，生成一段更自然、更个人化的表述（不超过 80 字），"
            f"不要医疗化语言，不要诊断用语，只说生活方式建议：\n\n{text}"
        )
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("response", text).strip()
    except Exception:
        return text  # 静默回退


def _llm_enhance(recommendations: list[dict], user_context: str) -> list[dict]:
    """对每条建议的 prescription 做 LLM 增强。"""
    if os.environ.get("USE_LLM", "").lower() not in ("1", "true", "yes"):
        return recommendations
    enhanced = []
    for r in recommendations:
        rx = r.get("prescription", "")
        if rx:
            r["prescription"] = _llm_enhance_prescription(rx, user_context)
            r["llm_enhanced"] = True
        enhanced.append(r)
    return enhanced


def recommend(profile: UserProfile, cases: Optional[list[dict]] = None,
              include_general: bool = True, top_k: int = 8) -> dict:
    cases = cases or load_cases()

    # 弱项规范通路集合 + 原始键（用于展示）
    weak_canon: set[str] = set()
    weak_display: list[str] = []
    for k, v in profile.pathway_scores.items():
        if v < 0.5:
            weak_canon.add(canon(k))
            weak_display.append(k)
    # 弱项轴集合：直接给的轴 + 由弱项通路反查的轴
    weak_axes: set[str] = {a.upper() for a in profile.weak_axes}
    for c in weak_canon:
        ax = canon_to_axis(c)
        if ax:
            weak_axes.add(ax)

    has_gene = bool(weak_canon) or bool(weak_axes)

    recs: list[Recommendation] = []
    for c in cases:
        case_canon = _pathway_tokens(c)
        case_axes = _axes(c)
        # 交集：① 规范通路命中；② 弱项轴字母命中（双保险，修复原字面不匹配）
        hit_path = case_canon & weak_canon
        hit_axis = case_axes & weak_axes
        overlap = len(hit_path) + len(hit_axis)
        ew = EVIDENCE_WEIGHT.get(c.get("evidence_level", "L3"), 1)

        if overlap > 0:
            mode = "personalized"
            score = overlap * ew
        elif include_general:
            mode = "general"
            score = ew * 0.3  # 通用建议权重低
        else:
            continue

        # 禁忌排除
        contra = _contra_hit(c, profile.contraindications)
        if contra:
            continue

        recs.append(Recommendation(
            case_id=c.get("id", c.get("case_id", "")),
            targeted_pathway="; ".join(_AXIS_LABEL.get(a, a) for a in sorted(case_axes)),
            tcm_source=c.get("tcm_source", c.get("tcm_concept", "")),
            gene_relevance=(
                "交集弱项: " + ", ".join(sorted(hit_path)) +
                (("; 轴 " + ",".join(sorted(hit_axis))) if hit_axis and hit_path else (",".join(sorted(hit_axis)) if hit_axis else ""))
            ) if overlap else "无基因交集→通用建议",
            evidence_level=c.get("evidence_level", "L3"),
            contraindication=(
                c.get("gene_link", "").split("；")[-1]
                if ("慎用" in c.get("gene_link", "") or "禁用" in c.get("gene_link", "")) else "无特别禁忌"
            ),
            monitor_markers="; ".join(m.get("marker", "") for m in c.get("primary_outcomes", [])[:3]),
            prescription=c.get("intervention", ""),
            mode=mode, score=score,
        ))

    recs.sort(key=lambda r: r.score, reverse=True)
    recs = recs[:top_k]

    rec_dicts = [asdict(r) for r in recs]

    # LLM 增强（USE_LLM=1 时启用，失败静默回退）
    user_context = "; ".join(profile.pathway_scores.keys())
    rec_dicts = _llm_enhance(rec_dicts, user_context)

    # is_demo 三态：缺基因数据 → 整批示例横幅
    banner = None
    if not has_gene:
        banner = "is_demo：未提供基因/组学数据，以下为「通用健康建议」示例，非为你定制。"
    elif any(r["mode"] == "general" for r in rec_dicts):
        banner = "部分条目无基因交集，标记为通用建议；个性化条目已标 personalized。"

    return {
        "banner": banner,
        "has_gene": has_gene,
        "weak_pathways": sorted(weak_display),
        "weak_axes": sorted(weak_axes),
        "recommendations": rec_dicts,
        "llm_enabled": os.environ.get("USE_LLM", "0"),
    }


def disclaimer() -> str:
    """去医疗化免责（产品层统一注入）。"""
    return (
        "【免责声明】HealthLens 提供基于古籍经验与现代稳态生物学证据的养生/修复参考，"
        "不构成医疗诊断、处方或治疗建议。个体差异显著，涉及疾病、用药、孕期及特殊体质请遵医嘱。"
        "基因相关建议仅基于通路级群体证据，禁单 SNP 决定个人方案。"
    )


if __name__ == "__main__":
    print("HealthLens fusion_engine v0.3 — 个性化融合引擎（+ LLM 增强）")
    print("载入案例库:", len(load_cases()), "条 | 映射通路:", len(_CANON_TO_AXIS), "条")
    print("LLM:", "已启用" if os.environ.get("USE_LLM", "").lower() in ("1", "true") else "规则模式（USE_LLM=1 开启）")
