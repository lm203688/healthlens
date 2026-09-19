"""
HealthLens 个性化融合引擎 v0.6（moat 脚手架 + LLM 增强 + 代谢-炎症轴 + 轴间桥接网络）
============================================
v0.6 新增（2026-09-19，前沿机制嫁接）：
  - AXIS_BRIDGES 由 3 条扩到 5 条，补上 H（先天-肾精）作为上游枢纽的两条出边：
      H → A（表观遗传信息完整性 / 部分重编程 → 自噬相关基因转录程序）
      H → F（剪接体稳态 → 异常蛋白亚型与炎症负荷）
    两条均为 Tier-3 假说级，锚点来自 2026 年前沿（RNA 剪接体可成药依赖、
    OSK 部分重编程进入首个 FDA 批准的人体安全性试验）。
  - 【红线】桥接只解释机制，不引入任何干预承诺。"不涉及任何重编程/剪接
    靶向干预"写进 intervention_link，内容层不得据此声称可"逆转衰老"。

v0.5 新增（2026-09-15，gasdermin/焦亡范式借鉴）：
  - 轴间桥接网络 AXIS_BRIDGES：把"单轴偏弱"的解释升级为"轴间因果链条"。
    头条条目：A(自噬)↑ → 自噬-溶酶体选择性降解 NLRP3 / GSDMD → F(正邪-炎症)轴
    焦亡性炎症↓。锚点生物学为 Tier-2/3 证据，标注为假说级、非临床结论。
  - axis_bridges_for(weak_axes) 供 API / 前端把机制解释直接呈现给用户。

v0.4 新增（2026-09-10，研发路线三期 P2-1）：
  - 接入 bioage_engine 的「代谢-炎症轴」（PhenoAge 借鉴，透明体检指标代理）
  - 轴分低于阈值时，把该轴映射到既有八轴 F(正邪-炎症)/A(气化-自噬 AMPK-mTOR) 参与匹配
  - 体检指标驱动的个性化与基因驱动的个性化分别标注（is_demo 三态不被污染）
  - 任何异常静默回退到规则引擎，永不阻断主流程

v0.3 新增（2026-08-27）：
  - USE_LLM=1 时调用本地 Ollama 模型对处方文本做语义增强（个人化、自然化）
  - 失败静默回退到规则引擎，永不阻断主流程
  - LLM 模型名通过 HEALTHLENS_LLM_MODEL 环境变量配置（默认 qwen3.8）
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import urllib.request
from dataclasses import asdict, dataclass, field

# 【关键约束】这里绝不能写成 `from app.core.bioage_engine import ...`。
#
# 那样会触发 app/__init__.py，后者在 import 时构建整个 FastAPI 应用
# （fastapi / loguru / slowapi / 全部路由模块），导致本模块在「无重型依赖的
# 精简环境」里根本无法导入。受影响的具体场景：
#   · CI 作业 "Agent Library Test (no FastAPI deps)"（只装 pytest+ruff）
#     —— 2026-09-15 run 34938135916 即因此 ImportError，作业已连续红。
#   · healthlens_agent/_loader.py 用 importlib 按文件路径加载本模块，
#     本模块再回头 import app 包，等于把精简环境的设计破坏掉。
# bioage_engine.py 自身只依赖标准库（dataclasses），按文件路径加载即可，
# 与 healthlens_agent/_loader.py 的手法一致。
_BIOAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "core", "bioage_engine.py",
)


def _load_bioage():
    """按文件路径加载 bioage_engine，绕过 app 包的 FastAPI 依赖。"""
    mod = sys.modules.get("bioage_engine")
    if mod is not None and hasattr(mod, "BioAgeEngine"):
        return mod
    spec = importlib.util.spec_from_file_location("bioage_engine", _BIOAGE_PATH)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(_BIOAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bioage_engine"] = module  # 预注册，避免内部相对导入问题
    spec.loader.exec_module(module)
    return module


try:
    _bioage = _load_bioage()
    BioAgeEngine = _bioage.BioAgeEngine
    AXIS_KEY = _bioage.AXIS_KEY
    AXIS_LABEL = _bioage.AXIS_LABEL
except Exception:  # noqa: BLE001 —— 精简环境缺文件时降级，见下方 _HAS_BIOAGE
    BioAgeEngine = None  # type: ignore[assignment]
    AXIS_KEY = "metabolic_inflammatory"
    AXIS_LABEL = "代谢-炎症轴"

_HAS_BIOAGE = BioAgeEngine is not None

# 代谢-炎症轴 → 既有八轴落点（假说级映射，非临床结论）：
#   F = 正邪-炎症（CRP 等炎症负荷）；A = 气化/自噬(AMPK-mTOR)（糖脂代谢底物感应）
BIOAGE_AXIS_MAP: set[str] = {"F", "A"}
# 轴分低于该阈值视为该轴偏弱，参与个性化匹配
BIOAGE_WEAK_THRESHOLD: float = 60.0
# assess() 接受的标志物字段（用于过滤用户传入的未知键）
_BIOAGE_FIELDS = (
    "glucose", "hba1c", "hs_crp", "waist_cm",
    "hdl", "triglycerides", "sbp", "bmi",
)

# v0.5/v0.6：轴间桥接网络（机制级映射，假说级结论，非临床）
# 把"单轴偏弱"的解释升级为"轴间因果链条"。头条条目：
#   A(自噬)↑ → 自噬-溶酶体选择性降解 NLRP3 / GSDMD → F(正邪-炎症)轴焦亡性炎症↓
# 锚点生物学：自噬选择性降解炎症小体组分（细胞与动物证据 Tier-2/3），
# 属合理机制推演，非已验证的干预结论，内容层须写"可能/相关"而非"导致/改善"。
# v0.6 补 H 轴出边后，H 成为机制网络的上游枢纽（先天为本 → 影响 A/F 两轴）。
AXIS_BRIDGES: list[dict] = [
    {
        "from": "A", "to": "F",
        "direction": "negative",  # from 增强 → to 减弱
        "mechanism": (
            "自噬-溶酶体选择性降解 NLRP3 炎症小体组分与 GSDMD 成孔蛋白，"
            "降低炎症小体活化与焦亡性炎症（IL-1β / IL-18 释放）"
        ),
        "molecules": ["NLRP3", "GSDMD", "caspase-1", "IL-1β", "IL-18"],
        "evidence": "Tier-2/3（自噬选择性降解炎症小体；细胞与动物证据）",
        "hypothesis_level": True,
        "intervention_link": "间歇性限食、规律运动、充足睡眠（AMPK→自噬流）",
    },
    {
        "from": "A", "to": "H",
        "direction": "positive",
        "mechanism": "自噬/线粒体更新支持先天之本（肾精 H 轴）相关能量稳态与清除效率",
        "molecules": ["PGC-1α", "AMPK", "mitophagy"],
        "evidence": "Tier-2（线粒体自噬与能量稳态）",
        "hypothesis_level": True,
        "intervention_link": "有氧训练、冷热应激、限食",
    },
    {
        "from": "F", "to": "D",
        "direction": "negative",
        "mechanism": "慢性低度炎症（正邪失衡）削弱阴阳互根的动态平衡；炎症状态下行利于 D 轴稳态",
        "molecules": ["CRP", "IL-6", "TNF-α"],
        "evidence": "Tier-2/3（炎症与整体稳态关联，群体与机制证据）",
        "hypothesis_level": True,
        "intervention_link": "抗炎饮食、压力管理、规律运动",
    },
    # ── v0.6 增补（2026-09-19）──
    # 锚点：RNA 剪接体功能稳态属转录后调控核心；剪接失调产生异常蛋白亚型并
    # 触发未折叠蛋白反应与炎症信号。2026 Nat Commun 证实剪接体是 RAS 驱动
    # 衰老与肿瘤的可成药依赖（细胞+动物证据），故列 Tier-2/3。
    # 【边界】该锚点是"疾病靶点研究"，不是健康管理手段；intervention_link
    # 只写生活方式，任何剪接靶向药物都不得出现在用户可见输出里。
    {
        "from": "H", "to": "F",
        "direction": "negative",  # H 完整性增强 → F 炎症负荷减弱
        "mechanism": (
            "先天之本（H 轴，表观遗传信息完整性）维持剪接体功能稳态；"
            "剪接失调（异常外显子跳跃 / 内含子滞留）会产生异常蛋白亚型，"
            "进而触发未折叠蛋白反应与炎症信号。H 轴信息完整性越好，"
            "异常亚型与伴随的炎症负荷可能越低。"
        ),
        "molecules": ["SF3B1", "U2AF2", "SRSF", "RBM20", "IL-6"],
        "evidence": "Tier-3（剪接失调与炎症/衰老的关联有细胞与群体证据；尚无人体干预结论）",
        "hypothesis_level": True,
        "intervention_link": "规律作息、充足睡眠、均衡蛋白摄入（不涉及任何剪接靶向药物）",
    },
    # 锚点：2020《Nature》封面（吕垣澄 / Sinclair 实验室）用 OSK 三因子
    # （去掉致癌的 c-Myc）实现活体部分重编程，恢复青光眼小鼠视力；2026 年
    # 该路线进入首个 FDA 批准的人体安全性试验。属活体动物+细胞证据，
    # 且明确未到人体干预阶段，故列 Tier-3。
    # 【红线】内容层严禁据此写"逆转衰老 / 返老还童"——Phase 5 门禁已把
    # 这两类表述列为 HIGH 级 fail 词。此处只解释机制，不承诺任何干预效果。
    {
        "from": "H", "to": "A",
        "direction": "positive",  # H 完整性增强 → A 轴转录程序支持增强
        "mechanism": (
            "表观遗传信息完整性（H 轴）支持自噬相关基因的正常转录程序；"
            "部分重编程研究提示，衰老细胞的表观遗传标记状态可能影响自噬通量"
            "与组织修复能力（属机制假说，非临床结论）。"
        ),
        "molecules": ["Oct4", "Sox2", "Klf4", "DNA甲基化", "LC3", "p16"],
        "evidence": "Tier-3（部分重编程为活体动物与细胞证据；2026 年才进入首个 FDA 批准的人体安全性试验）",
        "hypothesis_level": True,
        "intervention_link": "睡眠、限食、规律运动（不涉及任何重编程干预）",
    },
]

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


def canon_to_axis(canonical: str) -> str | None:
    return _CANON_TO_AXIS.get(canonical)


def axis_bridges_for(weak_axes: set[str]) -> list[dict]:
    """返回与弱项轴相关的轴间桥接（机制解释线索，非临床结论）。

    例：弱项含 F 或 A 时返回 A→F 焦亡抑制桥接，可在前端/API 直接呈现
    「自噬增强 → 炎症小体降解 → 焦亡性炎症下降」的因果链条。
    """
    return [b for b in AXIS_BRIDGES if b["from"] in weak_axes or b["to"] in weak_axes]


@dataclass
class UserProfile:
    # 基因/组学：通路级得分（0-1），<0.5 视为弱项；禁 SNP 级
    pathway_scores: dict[str, float] = field(default_factory=dict)
    # 也可直接给弱项轴字母（A-H）
    weak_axes: set[str] = field(default_factory=set)
    # 个体禁忌（命中即排除相关建议）
    contraindications: set[str] = field(default_factory=set)
    # v0.4：体检指标驱动的「代谢-炎症轴」（PhenoAge 代理，非临床）
    chrono_age: int | None = None
    is_male: bool = True
    biomarkers: dict[str, float] = field(default_factory=dict)


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


def _contra_hit(case: dict, user_contra: set[str]) -> str | None:
    blob = " ".join([case.get("gene_link", ""), case.get("mechanism", "")])
    for kw in user_contra:
        if kw in blob:
            return kw
    return None


def _llm_enhance_prescription(text: str, context: str) -> str:
    """用本地 LLM 对处方文本做个人化语义增强。失败返回原文。"""
    try:
        model = os.environ.get("HEALTHLENS_LLM_MODEL", "qwen3.8")
        url = "http://127.0.0.1:11434/api/generate"
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


def recommend(profile: UserProfile, cases: list[dict] | None = None,
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

    # has_gene 仅由基因/组学来源判定（先算，避免被体检指标污染 is_demo 三态）
    has_gene = bool(weak_canon) or bool(weak_axes)

    # v0.4：代谢-炎症轴（体检指标代理，PhenoAge 借鉴）。
    # 轴分偏低 → 映射到 F(正邪-炎症)/A(气化-自噬) 参与个性化匹配。
    bioage_block: dict | None = None
    has_bioage = False
    bm = {
        k: v for k, v in (profile.biomarkers or {}).items()
        if k in _BIOAGE_FIELDS and v is not None
    }
    if bm and profile.chrono_age is not None:
        try:
            engine = BioAgeEngine()
            ba = engine.assess(profile.chrono_age, is_male=profile.is_male, **bm)
            has_bioage = True
            axis_weak = ba.axis_score < BIOAGE_WEAK_THRESHOLD
            if axis_weak:
                weak_axes |= BIOAGE_AXIS_MAP
            bioage_block = {
                "axis_key": AXIS_KEY,
                "axis_label": AXIS_LABEL,
                "chrono_age": ba.chrono_age,
                "bio_age": ba.bio_age,
                "delta": ba.delta,
                "axis_score": ba.axis_score,
                "axis_weak": axis_weak,
                "band": engine.delta_band(ba.delta),
                "mapped_axes": sorted(BIOAGE_AXIS_MAP),
                "not_clinical": ba.not_clinical,
                "method": ba.method,
                "markers": [asdict(m) for m in ba.markers],
            }
        except Exception:
            bioage_block = None  # 静默回退，永不阻断主流程
            has_bioage = False

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

    # is_demo 三态：基因/组学 与 体检指标 两条个性化来源分别标注
    banner = None
    if not has_gene and not has_bioage:
        banner = "is_demo：未提供基因/组学数据，以下为「通用健康建议」示例，非为你定制。"
    elif not has_gene and has_bioage:
        banner = (
            "未提供基因/组学数据；已按体检指标（代谢-炎症轴）做个性化匹配，"
            "属生活方式参考，非基因定制、非临床结论。"
        )
    elif any(r["mode"] == "general" for r in rec_dicts):
        banner = "部分条目无基因交集，标记为通用建议；个性化条目已标 personalized。"

    return {
        "banner": banner,
        "has_gene": has_gene,
        "has_bioage": has_bioage,
        "weak_pathways": sorted(weak_display),
        "weak_axes": sorted(weak_axes),
        "axis_bridges": axis_bridges_for(weak_axes),
        "axis_scores": (
            {AXIS_KEY: bioage_block["axis_score"]} if bioage_block else {}
        ),
        "bioage": bioage_block,
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
    print("HealthLens fusion_engine v0.5 — 个性化融合引擎（+ LLM 增强 + 代谢-炎症轴 + 轴间桥接）")
    print("载入案例库:", len(load_cases()), "条 | 映射通路:", len(_CANON_TO_AXIS), "条")
    print("LLM:", "已启用" if os.environ.get("USE_LLM", "").lower() in ("1", "true") else "规则模式（USE_LLM=1 开启）")
    print(f"代谢-炎症轴: {AXIS_LABEL}（{AXIS_KEY}）→ 落点轴 {sorted(BIOAGE_AXIS_MAP)}，弱轴阈值 {BIOAGE_WEAK_THRESHOLD}")
    print("轴间桥接网络:", len(AXIS_BRIDGES), "条 | 头条 A→F 焦亡抑制:",
          any(b["from"] == "A" and b["to"] == "F" for b in AXIS_BRIDGES))
