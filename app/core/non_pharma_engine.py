"""非药物个性化方案引擎（Non-Pharmacological Personalized Plan Engine）
======================================================================
HealthLens 核心交付物（定位重构 2026-11-04，Chief m00139 工程增量②）。

**定位**：运动 / 饮食 / 睡眠 / 补剂 按个体差异生成「今天该做什么」的可执行日课。
平台定位为非医疗健康养生平台——本引擎输出是**生活方式建议**，不是处方、
不是治疗、不是诊断。

**"抽屉组合 + 信息完整度→精度分档"架构**（Chief 2026-11-04 产品形态约束）：
用户提供的信息越全 → 数据越完整 → 精度越准；给得少 → 精度略低但**可用**。
本引擎按输入完整度输出三档精度方案，每档都可用，但显式标注 precision_level：

  ┌────────────┬───────────────────────────────┬───────────────────────┐
  │ 精度档      │ 需要的输入                     │ 输出语义               │
  ├────────────┼───────────────────────────────┼───────────────────────┤
  │ basic      │ 仅生活方式画像（年龄/性别/     │ 通用生活方式日课       │
  │            │ 作息/禁忌/自述症状）            │ （大众可用，精度最低） │
  ├────────────┼───────────────────────────────┼───────────────────────┤
  │ standard   │ basic + 化验/体检生物标志       │ 按生物标志分层的日课   │
  │            │ （biomarkers）                  │ （如血脂/血糖异常     │
  │            │                                │  → 对应饮食/运动侧重） │
  ├────────────┼───────────────────────────────┼───────────────────────┤
  │ advanced   │ standard + 基因/组学           │ 按个体差异精调的日课   │
  │            │ （pathway_scores/gene_axes）    │ （最高精度，仍非诊断） │
  └────────────┴───────────────────────────────┴───────────────────────┘

**诚实边界**：
- 本引擎是**研究性/探索性**工具，输出为生活方式建议，不宣称"已验证
  疗效"或"已验证抗衰"。
- precision_level 只反映**信息完整度**，不反映医学证据等级；任何
  建议均须用户自评安全（禁忌/疾病史/孕期等），平台不替代医生判断。
- 补剂条目仅按个体差异给出**一般性营养提示**，不构成用药建议；
  如需补充剂处方，须经持牌医师/营养师评估。

**依赖约束**：本模块只依赖标准库 + axis_scorers（按文件路径加载，
与 fusion_engine 同一手法，避免触发 app 包 FastAPI 依赖）。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# 八轴打分器按文件路径加载（避免触发 app/__init__.py → FastAPI）
# ---------------------------------------------------------------------------
_AXIS_SCORERS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "axis_scorers.py",
)


def _load_axis_scorers():
    """按文件路径加载 axis_scorers，绕过 app 包 FastAPI 依赖。"""
    mod = sys.modules.get("axis_scorers")
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location("axis_scorers", _AXIS_SCORERS_PATH)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["axis_scorers"] = mod
    return mod


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class PrecisionLevel(str):
    """精度档（信息完整度分档）。"""

    BASIC = "basic"
    STANDARD = "standard"
    ADVANCED = "advanced"


@dataclass
class DailyAction:
    """一条可执行的日课动作。"""

    slot: str                 # morning / noon / afternoon / evening / bedtime
    category: str             # exercise / diet / sleep / supplement / lifestyle
    title: str
    detail: str
    duration_minutes: int = 0
    rationale: str = ""       # 为什么今天这么做（可追溯）
    precision_tag: str = PrecisionLevel.BASIC


@dataclass
class DailyPlan:
    """一天的完整个性化日课方案。"""

    date_iso: str
    precision_level: str = PrecisionLevel.BASIC
    precision_note: str = ""
    actions: list[DailyAction] = field(default_factory=list)
    rationale_summary: str = ""
    disclaimer: str = (
        "本方案为 AI 辅助生成的生活方式建议（研究性/探索性），"
        "非医疗处方、非诊断结论。请根据自身状况谨慎执行，"
        "如有疾病史/孕期/用药，请咨询持牌医师。"
    )

    def to_dict(self) -> dict:
        return {
            "date": self.date_iso,
            "precision_level": self.precision_level,
            "precision_note": self.precision_note,
            "actions": [a.__dict__ for a in self.actions],
            "rationale_summary": self.rationale_summary,
            "disclaimer": self.disclaimer,
        }


@dataclass
class UserLifestyleProfile:
    """用户画像（抽屉组合的基本输入）。"""

    age: int | None = None
    is_male: bool = True
    constitution: str = ""            # 中医体质（可选，pinghe/qixu/...）
    contraindications: set[str] = field(default_factory=set)
    lifestyle: dict = field(default_factory=dict)   # 作息/运动习惯等自由字段
    biomarkers: dict = field(default_factory=dict)   # standard 档输入（化验/体检）
    pathway_scores: dict = field(default_factory=dict)  # advanced 档输入（基因/组学）
    gene_axes: set[str] = field(default_factory=set)    # advanced 档输入（基因轴）
    symptoms: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 精度档判定（抽屉组合 → precision_level）
# ---------------------------------------------------------------------------

def determine_precision(profile: UserLifestyleProfile) -> tuple[str, str]:
    """按信息完整度判定精度档。

    规则（与"抽屉组合"一致：信息越全精度越高，每档都可用）：
      - advanced: 有基因/组学输入（pathway_scores 或 gene_axes 非空）
      - standard: 有化验/体检生物标志（biomarkers 非空）
      - basic:    仅生活方式画像（默认，大众可用）
    返回 (precision_level, note)。
    """
    if profile.pathway_scores or profile.gene_axes:
        return (
            PrecisionLevel.ADVANCED,
            "已提供基因/组学数据，按个体差异精调（风险≠诊断，仅供参考）。",
        )
    if profile.biomarkers:
        return (
            PrecisionLevel.STANDARD,
            "已提供化验/体检指标，按生物标志分层建议。",
        )
    return (
        PrecisionLevel.BASIC,
        "仅生活方式画像，输出通用日课（精度最低，但可用）。",
    )


# ---------------------------------------------------------------------------
# 基础日课模板（basic 档：通用生活方式）
# ---------------------------------------------------------------------------

def _base_actions() -> list[DailyAction]:
    return [
        DailyAction(
            slot="morning", category="lifestyle", title="晨起温水",
            detail="起床后饮用 200-300ml 温水，唤醒代谢。",
            duration_minutes=5,
            rationale="晨间补水改善循环，为一天打好基础。",
        ),
        DailyAction(
            slot="morning", category="exercise", title="晨间活动",
            detail="轻度有氧或拉伸 20-30 分钟（快走/八段锦/瑜伽）。",
            duration_minutes=25,
            rationale="晨间活动稳定血糖节律，改善胰岛素敏感性。",
        ),
        DailyAction(
            slot="noon", category="diet", title="均衡午餐",
            detail="主食+优质蛋白+蔬菜，少油少盐，细嚼慢咽。",
            duration_minutes=30,
            rationale="均衡供能，避免午后血糖波动。",
        ),
        DailyAction(
            slot="afternoon", category="sleep", title="午间小憩",
            detail="午时(11-13时)小憩 15-30 分钟，不宜超过 1 小时。",
            duration_minutes=20,
            rationale="午时养阳，顺应阴阳消长规律。",
        ),
        DailyAction(
            slot="evening", category="exercise", title="傍晚活动",
            detail="轻中度运动 20-40 分钟，避免睡前 2 小时内剧烈运动。",
            duration_minutes=30,
            rationale="傍晚运动助眠，但避免临睡前过度兴奋。",
        ),
        DailyAction(
            slot="bedtime", category="sleep", title="规律睡眠",
            detail="23:00 前入睡，保证 7-8 小时夜间睡眠。",
            duration_minutes=0,
            rationale="子时大睡养阴，恢复精力。",
        ),
    ]


# ---------------------------------------------------------------------------
# 生物标志分层（standard 档：按指标异常调整）
# ---------------------------------------------------------------------------

def _biomarker_adjustments(biomarkers: dict) -> list[DailyAction]:
    """按化验/体检异常调整日课（standard 档分层）。"""
    actions: list[DailyAction] = []
    # 血糖异常
    glucose = biomarkers.get("glucose") or biomarkers.get("fasting_glucose")
    if glucose is not None:
        try:
            gv = float(glucose)
        except (TypeError, ValueError):
            gv = None
        if gv is not None and gv > 6.1:
            actions.append(DailyAction(
                slot="evening", category="diet", title="控糖晚餐",
                detail="晚餐减少精制碳水，增加膳食纤维（全谷物/蔬菜），"
                       "餐后散步 15 分钟。",
                duration_minutes=20,
                rationale="空腹血糖偏高倾向 → 控制餐后血糖负荷。",
                precision_tag=PrecisionLevel.STANDARD,
            ))
    # 血脂异常
    chol = biomarkers.get("total_cholesterol") or biomarkers.get("cholesterol")
    if chol is not None:
        try:
            cv = float(chol)
        except (TypeError, ValueError):
            cv = None
        if cv is not None and cv > 5.2:
            actions.append(DailyAction(
                slot="morning", category="diet", title="降脂早餐",
                detail="燕麦/全谷物 + 坚果适量，减少饱和脂肪与反式脂肪。",
                duration_minutes=15,
                rationale="总胆固醇偏高倾向 → 增加可溶性纤维。",
                precision_tag=PrecisionLevel.STANDARD,
            ))
    # 血压异常
    sbp = biomarkers.get("systolic_bp") or biomarkers.get("sbp")
    if sbp is not None:
        try:
            sv = float(sbp)
        except (TypeError, ValueError):
            sv = None
        if sv is not None and sv > 130:
            actions.append(DailyAction(
                slot="morning", category="lifestyle", title="限盐+血压监测",
                detail="每日食盐 <5g，规律监测晨起血压，避免情绪激动。",
                duration_minutes=5,
                rationale="收缩压偏高倾向 → 限盐与规律监测。",
                precision_tag=PrecisionLevel.STANDARD,
            ))
    return actions


# ---------------------------------------------------------------------------
# 基因/组学精调（advanced 档：按弱项通路/轴细化）
# ---------------------------------------------------------------------------

def _genetic_refinement(profile: UserLifestyleProfile) -> list[DailyAction]:
    """按基因/组学弱项精调日课（advanced 档）。"""
    actions: list[DailyAction] = []
    weak_paths = [
        k for k, v in (profile.pathway_scores or {}).items() if v < 0.5
    ]
    weak_axes = {a.upper() for a in (profile.gene_axes or set())}

    # 常见弱项通路 → 对应日课
    path_map = {
        "AMPK": ("运动增敏", "增加间歇性高强度运动（HIIT 短时冲刺）",
                 "AMPK 通路弱项 → 运动改善线粒体功能。"),
        "MTOR": ("限时进食", "晚餐提前，采用 16:8 限时进食窗口",
                 "mTOR 通路弱项 → 限时进食调控自噬。"),
        "NAD": ("NAD 前体", "咨询营养师后考虑适量烟酰胺核糖（NR），"
                 "并配合规律运动提升 NAD+",
                 "NAD+ 通路弱项 → 生活方式提升 NAD+（非用药建议）。"),
    }
    for p in weak_paths:
        key = p.upper()
        for k, (title, detail, rationale) in path_map.items():
            if k in key:
                actions.append(DailyAction(
                    slot="evening", category="lifestyle",
                    title=title, detail=detail, duration_minutes=15,
                    rationale=rationale, precision_tag=PrecisionLevel.ADVANCED,
                ))

    # 弱项轴 → 对应日课
    axis_map = {
        "A": ("自噬支持", "轻断食（晚餐提前）或适量运动，支持气化-自噬轴。"),
        "B": ("线粒体支持", "适量高强度间歇训练 + 充足睡眠，支持能量轴。"),
        "C": ("微循环支持", "规律有氧运动 + 深色蔬果（硝酸盐），支持络脉-内皮轴。"),
        "D": ("神志调养", "冥想/深呼吸 10 分钟，调神志-神经内分泌轴。"),
        "E": ("睡眠优先", "严格执行 23:00 前入睡，支持神-睡眠轴。"),
        "F": ("抗炎饮食", "地中海式饮食 + omega-3，支持正邪-炎症轴。"),
        "G": ("肠道支持", "发酵食品 + 膳食纤维，支持肠道-菌群轴。"),
        "H": ("先天养护", "早睡 + 减压，避免透支先天-肾精轴。"),
    }
    for ax in weak_axes:
        if ax in axis_map:
            title, detail = axis_map[ax]
            actions.append(DailyAction(
                slot="evening", category="lifestyle",
                title=title, detail=detail, duration_minutes=10,
                rationale=f"{ax} 轴弱项（基因来源）→ {detail}",
                precision_tag=PrecisionLevel.ADVANCED,
            ))
    return actions


# ---------------------------------------------------------------------------
# 主引擎
# ---------------------------------------------------------------------------

class NonPharmaPlanEngine:
    """非药物个性化方案引擎 —— 生成"今天该做什么"的可执行日课。"""

    def generate(
        self,
        profile: UserLifestyleProfile,
        *,
        today: date | None = None,
        axis_scores: dict[str, Any] | None = None,
    ) -> DailyPlan:
        """按信息完整度生成精度分档的日课方案。

        参数：
          profile: 用户画像（抽屉组合，可只给部分字段）。
          axis_scores: 可选，八轴打分结果（复用 axis_scorers 的输出，
            用于在 advanced 档补充轴级精调）。
        返回：
          DailyPlan（每档都可用，显式标注 precision_level）。
        """
        today = today or date.today()
        precision, note = determine_precision(profile)

        actions = _base_actions()

        # standard 档：生物标志分层
        if precision in (PrecisionLevel.STANDARD, PrecisionLevel.ADVANCED):
            actions.extend(_biomarker_adjustments(profile.biomarkers))

        # advanced 档：基因/组学精调
        if precision == PrecisionLevel.ADVANCED:
            actions.extend(_genetic_refinement(profile))

        # 去重（按 title+slot），保持插入顺序
        seen = set()
        unique = []
        for a in actions:
            k = (a.slot, a.title)
            if k not in seen:
                seen.add(k)
                unique.append(a)
        actions = unique

        rationale_parts = [
            f"precision_level={precision}",
            f"actions={len(actions)}",
        ]
        if profile.biomarkers:
            rationale_parts.append(f"biomarkers={len(profile.biomarkers)}项")
        if profile.pathway_scores or profile.gene_axes:
            rationale_parts.append("基因/组学输入已纳入")

        return DailyPlan(
            date_iso=today.isoformat(),
            precision_level=precision,
            precision_note=note,
            actions=actions,
            rationale_summary="；".join(rationale_parts),
        )


# 便捷入口
def generate_daily_plan(profile: UserLifestyleProfile, **kwargs) -> DailyPlan:
    """模块级便捷入口：生成非药物日课方案。"""
    return NonPharmaPlanEngine().generate(profile, **kwargs)
