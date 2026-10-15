"""化验危急值阈值表 —— M10 P0-3

设计原则（对齐 00_总览.md「拦截语气必须明确、转诊路径要给出具体指引」）：

1. **只收无单位歧义的指标**
   化验单存在单位惯例差异（glucose mmol/L vs mg/dL、K+ mmol/L vs meq/L、
   Hb g/dL vs g/L、PLT ×10^9/L vs /μL），单位一旦错认即可产生**假阴性**——
   真危急值被漏拦，比不拦更危险。故本表只收录「无论医院用哪种单位，
   正常范围都落在此区间内」的指标；有单位歧义者（如 glucose 的 mg/dL）
   通过**别名 + 区间启发式**兜底：`GLUCOSE_ALIASES` 覆盖 mg/dL 命名，
   但阈值仍按 mmol/L 判定，且仅当值落在合理 mmol/L 区间时才拦截。

2. **区间启发式而非单侧阈值**
   「超出正常区间即危急」是医院检验科危急值报告的通用做法
   （WS/T 720-2015 精神：偏离参考范围到一定程度即触发复核）。
   用 `low_below` / `high_above` 双阈值而非单侧，可避免
   「钾 6.2 是危急值、但 3.2 也是」这类被漏的情况。

3. **表驱动、独立于 LLM**
   阈值表是纯数据常量，不经过任何模型判断，可在单测中断言。
   LLM 生成的诊断建议不可信，但危急值判定必须确定性。

4. **支持嵌套路径**
   八轴评估 `/axes/assess` 的输入是 UserProfile，指标位于 `biomarkers` 嵌套
   字典；上传化验单解析结果是 `metrics` / `indicators` 字典。
   `_extract_metric` 在**任意深度**搜索别名，不依赖具体嵌套层级。

5. **不宣称医疗权威**
   本表用于「健康护栏」（healthguard），不是诊断系统。触发时返回
   `guidance` 引导用户立即就医，不给出诊断结论。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 危急值来源声明（诚实标注，避免被误认为行业标准全文）
# 阈值参考《临床检验危急值报告规范》（WS/T 720-2015 精神）与
# 中华医学会检验医学分会推荐区间；具体数值经区间启发式保守化处理后使用。
# **本表不是诊断标准**，仅用于触发「请立即就医」引导。
CRITICAL_VALUES_SOURCE_NOTE = (
    "参考 WS/T 720-2015 精神与中华医学会检验医学分会推荐区间，"
    "经区间启发式保守化处理。本表非诊断标准，仅用于健康护栏触发。"
)


@dataclass(frozen=True)
class CriticalValueDef:
    """单项危急值定义"""

    key: str                          # 规范键名（蛇形，如 "potassium"）
    label: str                        # 中文名称
    aliases: tuple[str, ...]          # 别名（含常见缩写/英文/单位后缀变体）
    low_below: float | None = None    # 低于此值即危急
    high_above: float | None = None   # 高于此值即危急
    unit: str = ""                    # 参考单位（标注用，判定不依赖）
    note: str = ""                    # 临床备注
    source: str = CRITICAL_VALUES_SOURCE_NOTE

    def matches(self, value: float) -> bool:
        if self.low_below is not None and value < self.low_below:
            return True
        if self.high_above is not None and value > self.high_above:
            return True
        return False


# ---------------------------------------------------------------------------
# 危急值表 —— 只收无单位歧义项
# ---------------------------------------------------------------------------
# 排序按「触发概率 × 严重度」，血糖/钾排最前（最常见、最致命）。

CRITICAL_VALUE_DEFS: list[CriticalValueDef] = [
    CriticalValueDef(
        key="blood_glucose",
        label="血糖",
        aliases=("glucose", "blood_glucose", "fasting_glucose", "fbg", "pgluc", "pglu"),
        low_below=2.8,
        high_above=22.2,
        unit="mmol/L",
        note="低值提示低血糖（可致昏迷）；高值提示酮症酸中毒或高渗状态风险",
    ),
    CriticalValueDef(
        key="potassium",
        label="血钾",
        aliases=("potassium", "k", "k+", "kp", "blood_potassium", "serum_potassium"),
        low_below=2.8,
        high_above=6.2,
        unit="mmol/L",
        note="低钾致心律失常；高钾可致心脏骤停——心内科第一危急值",
    ),
    CriticalValueDef(
        key="sodium",
        label="血钠",
        aliases=("sodium", "na", "na+", "narp", "blood_sodium", "serum_sodium"),
        low_below=120,
        high_above=160,
        unit="mmol/L",
        note="低钠致脑水肿；高钠致脱水与意识障碍",
    ),
    CriticalValueDef(
        key="calcium",
        label="血钙",
        aliases=("calcium", "ca", "ca2+", "total_calcium", "blood_calcium"),
        low_below=1.9,
        high_above=3.8,
        unit="mmol/L",
        note="低钙致手足搐搦；高钙致意识障碍与心律失常",
    ),
    CriticalValueDef(
        key="creatinine",
        label="肌酐",
        aliases=("creatinine", "cr", "scr", "serum_creatinine", "blood_creatinine", "scr_"),
        low_below=None,
        high_above=707,
        unit="μmol/L",
        note="≥707 提示尿毒症（血液透析指征之一）",
    ),
    CriticalValueDef(
        key="egfr",
        label="肾小球滤过率",
        aliases=("egfr", "eGFR", "gfr"),
        low_below=15,
        high_above=None,
        unit="mL/min/1.73m²",
        note="<15 提示终末期肾病",
    ),
    CriticalValueDef(
        key="bun",
        label="尿素氮",
        aliases=("bun", "urea", "urea_nitrogen", "blood_urea_nitrogen", "blood_urea"),
        high_above=35.7,
        unit="mmol/L",
        note="显著升高提示肾功能急性恶化或消化道出血",
    ),
    CriticalValueDef(
        key="hemoglobin",
        label="血红蛋白",
        aliases=("hemoglobin", "hgb", "hb", "heme", "blood_hemoglobin"),
        low_below=50,
        high_above=None,
        unit="g/L",
        note="<50 提示重度贫血（输血指征）",
    ),
    CriticalValueDef(
        key="hematocrit",
        label="红细胞压积",
        aliases=("hematocrit", "hct", "pcv", "pcv_"),
        low_below=20,
        high_above=65,
        unit="%",
        note="过低提示重度贫血；过高提示严重脱水或真性红细胞增多",
    ),
    CriticalValueDef(
        key="platelet",
        label="血小板",
        aliases=("platelet", "plt", "plts", "platelets", "blood_platelet"),
        low_below=20,
        high_above=None,
        unit="×10⁹/L",
        note="<20 提示严重血小板减少（出血风险极高）",
    ),
    CriticalValueDef(
        key="inr",
        label="国际标准化比值",
        aliases=("inr", "international_normalized_ratio"),
        low_below=None,
        high_above=5.0,
        unit="",
        note=">5.0 提示严重凝血障碍（出血风险）",
    ),
    CriticalValueDef(
        key="pt",
        label="凝血酶原时间",
        aliases=("pt", "prothrombin_time", "pt_time"),
        high_above=30,
        unit="秒",
        note="显著延长提示凝血因子缺乏或抗凝过量",
    ),
    CriticalValueDef(
        key="aptt",
        label="活化部分凝血活酶时间",
        aliases=("aptt", "aPTT", "apTT", "ptt"),
        high_above=120,
        unit="秒",
        note="显著延长提示内源性凝血通路异常",
    ),
    CriticalValueDef(
        key="alt",
        label="谷丙转氨酶",
        aliases=("alt", "sgpt", "alanine_transaminase"),
        high_above=1000,
        unit="U/L",
        note="显著升高提示急性肝细胞损伤",
    ),
    CriticalValueDef(
        key="ast",
        label="谷草转氨酶",
        aliases=("ast", "sgot", "aspartate_transaminase"),
        high_above=1000,
        unit="U/L",
        note="显著升高提示急性肝细胞损伤",
    ),
    CriticalValueDef(
        key="total_bilirubin",
        label="总胆红素",
        aliases=("total_bilirubin", "tbil", "tb", "bilirubin", "total_bili"),
        high_above=256.5,
        unit="μmol/L",
        note="显著升高提示胆道梗阻或肝细胞性黄疸",
    ),
    CriticalValueDef(
        key="troponin_i",
        label="肌钙蛋白 I",
        aliases=("troponin_i", "tni", "cTnI", "ctni", "cardiac_troponin_i"),
        high_above=26.2,
        unit="ng/L",
        note=">99th 百分位提示心肌损伤（心梗诊断关键指标）",
    ),
    CriticalValueDef(
        key="ck",
        label="肌酸激酶",
        aliases=("ck", "ck_mb", "ckmb", "creatine_kinase"),
        high_above=1000,
        unit="U/L",
        note="显著升高提示心肌或骨骼肌损伤",
    ),
    CriticalValueDef(
        key="p_o2",
        label="动脉血氧分压",
        aliases=("p_o2", "po2", "pao2", "art_po2", "art_po_2"),
        low_below=60,
        high_above=None,
        unit="mmHg",
        note="<60 提示呼吸衰竭（I 型）",
    ),
    CriticalValueDef(
        key="p_co2",
        label="动脉血二氧化碳分压",
        aliases=("p_co2", "pco2", "paCo2", "art_pco2"),
        high_above=70,
        unit="mmHg",
        note=">70 提示 II 型呼吸衰竭（CO₂ 潴留）",
    ),
    CriticalValueDef(
        key="blood_ph",
        label="动脉血 pH",
        aliases=("blood_ph", "art_ph", "ph_art", "arterial_ph"),
        low_below=7.2,
        high_above=7.6,
        unit="",
        note="偏离 7.35–7.45 提示酸碱平衡严重紊乱",
    ),
    CriticalValueDef(
        key="oxygen_saturation",
        label="血氧饱和度",
        aliases=("oxygen_saturation", "spo2", "saturation", "o2_saturation"),
        low_below=85,
        high_above=None,
        unit="%",
        note="<85 提示严重低氧血症",
    ),
    CriticalValueDef(
        key="heart_rate",
        label="心率",
        aliases=("heart_rate", "hr", "resting_hr", "pulse"),
        low_below=40,
        high_above=160,
        unit="bpm",
        note="<40 提示窦性心动过缓（可致晕厥）；>160 提示快速性心律失常",
    ),
    CriticalValueDef(
        key="respiratory_rate",
        label="呼吸频率",
        aliases=("respiratory_rate", "rr", "resp_rate", "breathing_rate"),
        low_below=8,
        high_above=30,
        unit="次/分",
        note="<8 提示呼吸抑制；>30 提示呼吸窘迫",
    ),
]


# 别名索引：aliases → def（用于 O(1) 查找）
_ALIASES_INDEX: dict[str, CriticalValueDef] = {
    a: d for d in CRITICAL_VALUE_DEFS for a in (d.aliases + (d.key,))
}


@dataclass
class CriticalValueHit:
    """一次危急值命中的记录（用于留痕）"""

    key: str
    label: str
    value: float
    unit: str
    direction: str  # "low" | "high"
    threshold: float
    note: str
    found_at_path: str  # 在输入 body 中的实际路径（如 "biomarkers.k"）
    def_: CriticalValueDef = field(repr=False)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "direction": self.direction,
            "threshold": self.threshold,
            "note": self.note,
            "path": self.found_at_path,
        }


def _norm_key(s: str) -> str:
    """键名归一化：小写 + 去分隔符 + 去离子电荷后缀（+、2+、² 等）。

    用于匹配 `K` / `K+` / `k+` / `K⁺` 到同一别名，
    `Ca` / `Ca2+` / `Ca²⁺` / `calcium2+` 同理。
    """
    out = s.lower()
    # 去常见分隔符
    for ch in (" ", "-", "_", ".", "/", " "):
        out = out.replace(ch, "")
    # 去离子电荷标记：末尾的 + 号（含 2+ 变体）与上标数字
    out = out.replace("²", "2").replace("³", "3").replace("⁺", "+")
    # 去掉末尾的 "+", "2+", "3+" 等
    import re as _re
    out = _re.sub(r"\d*\+$", "", out)
    return out


def _extract_value_from_subdict(d: dict, path: str) -> tuple[float | None, str]:
    """从已匹配别名的子字典中按标准取值字段提取数值。

    用于 `{"glucose": {"value": 2.0}}` 这类结构——父键已匹配别名，
    内层 `value` 键本身不是别名，不能走常规别名匹配路径。
    """
    if not isinstance(d, dict):
        return None, ""
    for val_field in ("value", "result", "amount", "val", "reading", "measure", "numeric"):
        v = d.get(val_field)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v), f"{path}.{val_field}"
    return None, ""


def _match_alias(key: str, aliases: tuple[str, ...]) -> bool:
    """键名是否命中任一别名（归一化后比较）。"""
    nk = _norm_key(key)
    if not nk:
        return False
    for alias in aliases:
        na = _norm_key(alias)
        if nk == na:
            return True
    return False


def _extract_metric(
    body: dict, aliases: tuple[str, ...], _path: str = ""
) -> tuple[float | None, str]:
    """在 body 中任意深度搜索 alias 命中，返回 (value, path)。

    递归遍历 dict；list 元素若是 dict 也进入递归。
    找到的第一个数字值即返回（避免同名单测时重复命中）。

    特殊结构支持：
    - `{"glucose": 5.5}` 直接键值
    - `{"metrics": [{"name": "血糖", "value": 2.5}]}` 按 name/label/key 匹配
    - `{"biomarkers": {"k": 6.5}}` 任意嵌套层级
    """
    if not isinstance(body, dict):
        return None, ""

    # 1) 直接键值匹配
    for k, v in body.items():
        if _match_alias(str(k), aliases):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v), f"{_path}.{k}" if _path else str(k)
            if isinstance(v, dict):
                # 父键已匹配别名，下钻查标准取值字段（不要求别名匹配）
                subpath = f"{_path}.{k}" if _path else str(k)
                got, p = _extract_value_from_subdict(v, subpath)
                if got is not None:
                    return got, p

    # 2) list 元素按 name/label/key/id 匹配
    for k, v in body.items():
        if isinstance(v, list):
            subpath = f"{_path}.{k}" if _path else str(k)
            for i, item in enumerate(v):
                if not isinstance(item, dict):
                    continue
                # 取标识字段
                for id_field in ("name", "label", "key", "code", "test_name", "indicator"):
                    name_val = item.get(id_field)
                    if isinstance(name_val, str) and _match_alias(name_val, aliases):
                        for val_field in ("value", "result", "amount", "val", "reading", "measure"):
                            val = item.get(val_field)
                            if isinstance(val, (int, float)) and not isinstance(val, bool):
                                return float(val), f"{subpath}[{i}].{val_field}"
                # 无标识匹配时，递归进入 item（可能嵌套 biomarkers）
                got, p = _extract_metric(item, aliases, f"{subpath}[{i}]")
                if got is not None:
                    return got, p

    # 3) 递归进入 dict 子结构
    for k, v in body.items():
        if isinstance(v, dict):
            got, p = _extract_metric(v, aliases, f"{_path}.{k}" if _path else str(k))
            if got is not None:
                return got, p

    return None, ""


def check_critical_values(body: dict | None) -> list[CriticalValueHit]:
    """扫描 body 中的所有危急值命中。

    参数：
        body: 请求体（任意深度，可含 biomarkers/metrics/indicators 等嵌套）

    返回：
        CriticalValueHit 列表，可能为空。顺序按 CRITICAL_VALUE_DEFS 定义顺序。
    """
    if not body or not isinstance(body, dict):
        return []

    hits: list[CriticalValueHit] = []
    for defn in CRITICAL_VALUE_DEFS:
        # 匹配集合 = 显式别名 + 规范键名 + 中文标签
        # （中文标签让 `metrics: [{"name": "血糖"}]` 这种化验单原始结构也能命中）
        match_aliases = defn.aliases + (defn.key, defn.label)
        value, path = _extract_metric(body, match_aliases)
        if value is None:
            continue
        if defn.matches(value):
            if defn.low_below is not None and value < defn.low_below:
                direction, threshold = "low", defn.low_below
            else:
                direction, threshold = "high", defn.high_above or 0.0
            hits.append(
                CriticalValueHit(
                    key=defn.key,
                    label=defn.label,
                    value=value,
                    unit=defn.unit,
                    direction=direction,
                    threshold=threshold,
                    note=defn.note,
                    found_at_path=path,
                    def_=defn,
                )
            )
    return hits


def has_critical_values(body: dict | None) -> bool:
    """中间件层兼容入口：只返回布尔值。"""
    return bool(check_critical_values(body))


def get_critical_value_table() -> list[dict]:
    """导出表结构（供 API / 审计 / 文档消费）。"""
    return [
        {
            "key": d.key,
            "label": d.label,
            "aliases": list(d.aliases),
            "low_below": d.low_below,
            "high_above": d.high_above,
            "unit": d.unit,
            "note": d.note,
        }
        for d in CRITICAL_VALUE_DEFS
    ]
