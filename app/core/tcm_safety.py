"""中医安全护栏引擎（线上后端版）
================================

覆盖四类必须前置的安全校验，直接消解法域/专家/监管对「食疗/方剂推荐」的第一攻击点：

1. **配伍禁忌（十八反 / 十九畏）** —— 药材与药材同方时的经典禁忌。
2. **妊娠禁忌** —— 孕期禁用/慎用药材。
3. **中西药相互作用** —— 在服西药（抗凝/降压/降糖/地高辛/镇静/MAOI…）与中药的
   已知相互作用，给出风险等级与机制说明（可配置，便于持续补全）。
4. **药-草-食三联相互作用（借鉴 DHFI-C 本体思路）** —— 食物与西药、食物与中药的
   已知相互作用（如葡萄柚×抗凝药、牛奶×四环素、萝卜×人参），给出风险等级。

所有规则为确定性数据 + 规范化别名匹配，零外部依赖、可单测、可解释。
诊断/方剂推荐输出前必须调用 `check_safety`，将告警并入报告，且不删除原方案，
仅做「风险提示 + 就医建议」，符合去医疗化合规边界。

借鉴来源：本方为 HealthLens 自研确定性护栏，规则取自《神农本草经》《本草经集注》
十八反十九畏传统禁忌与中西药相互作用公开药学资料；药名别名通过
`data/tcm_mkg/chp_entities.json`（GraphAI-for-TCM, MIT）做广度增强。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["high", "moderate", "low"]

_CH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHP_PATH = os.path.join(_CH_ROOT, "data", "tcm_mkg", "chp_entities.json")


# ---------------------------------------------------------------------------
# 别名归一化（覆盖常见异名/炮制品；CHP 实体做广度增强）
# ---------------------------------------------------------------------------
HERB_SYNONYMS: dict[str, str] = {
    "附子": "乌头", "川乌": "乌头", "草乌": "乌头", "天雄": "乌头",
    "半夏": "半夏", "瓜蒌": "瓜蒌", "天花粉": "瓜蒌", "贝母": "贝母",
    "浙贝母": "贝母", "川贝母": "贝母", "白蔹": "白蔹", "白及": "白及",
    "甘草": "甘草", "甘遂": "甘遂", "大戟": "大戟", "京大戟": "大戟",
    "海藻": "海藻", "芫花": "芫花",
    "藜芦": "藜芦", "人参": "人参", "丹参": "丹参", "玄参": "玄参",
    "苦参": "苦参", "沙参": "沙参", "细辛": "细辛", "芍药": "芍药",
    "白芍": "芍药", "赤芍": "芍药",
    "肉桂": "官桂", "官桂": "官桂", "赤石脂": "赤石脂",
    "朴硝": "朴硝", "芒硝": "朴硝", "牙硝": "朴硝", "玄明粉": "朴硝",
    "三七": "三七", "田七": "三七", "田三七": "三七",
    "丹参": "丹参", "当归": "当归", "川芎": "川芎", "红花": "红花",
    "桃仁": "桃仁", "银杏": "银杏叶", "银杏叶": "银杏叶",
    "益母草": "益母草", "麻黄": "麻黄", "五味子": "五味子", "天麻": "天麻",
    "钩藤": "钩藤", "牛黄": "牛黄",
}


def _load_chp_classic_aliases() -> dict[str, str]:
    """把 CHP 实体中命中经典禁忌药的别名并入 HERB_SYNONYMS。

    防御式：文件缺失/解析失败则返回空 dict，不影响主流程。仅把「其名或别名
    等于某经典 canonical key / 已映射别名」的 CHP 实体的其余名称并入该 canonical，
    严格扩充识别广度、绝不改变既有映射语义。
    """
    extra: dict[str, str] = {}
    try:
        with open(CHP_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return extra
    classic_keys = set(HERB_SYNONYMS.values())
    for ent in data.get("entities", []):
        names = [ent.get("name")] + list(ent.get("synonyms", []) or [])
        hit = None
        for n in names:
            canon = HERB_SYNONYMS.get(n)
            if canon:
                hit = canon
                break
            if n in classic_keys:
                hit = n
                break
        if not hit:
            continue
        for n in names:
            if n not in HERB_SYNONYMS and n != hit:
                extra[n] = hit
    return extra


# 合并 CHP 增强别名（后写覆盖，且不破坏既有经典映射）
HERB_SYNONYMS = {**HERB_SYNONYMS, **_load_chp_classic_aliases()}


def norm(name: str) -> str:
    name = (name or "").strip()
    return HERB_SYNONYMS.get(name, name)


# ---------------------------------------------------------------------------
# 1. 十八反
# ---------------------------------------------------------------------------
EIGHT_ANTAGONISMS: list[tuple[str, str]] = [
    ("甘草", "甘遂"), ("甘草", "大戟"), ("甘草", "海藻"), ("甘草", "芫花"),
    ("乌头", "半夏"), ("乌头", "瓜蒌"), ("乌头", "贝母"), ("乌头", "白蔹"), ("乌头", "白及"),
    ("藜芦", "人参"), ("藜芦", "沙参"), ("藜芦", "丹参"), ("藜芦", "玄参"),
    ("藜芦", "苦参"), ("藜芦", "细辛"), ("藜芦", "芍药"),
]

# ---------------------------------------------------------------------------
# 2. 十九畏
# ---------------------------------------------------------------------------
NINETEEN_INCOMPAT: list[tuple[str, str]] = [
    ("硫黄", "朴硝"), ("水银", "砒霜"), ("狼毒", "密陀僧"), ("巴豆", "牵牛"),
    ("丁香", "郁金"), ("乌头", "犀角"), ("朴硝", "三棱"), ("官桂", "赤石脂"),
    ("人参", "五灵脂"),
]

# ---------------------------------------------------------------------------
# 3. 妊娠禁忌（禁用/慎用，节选高频药）
# ---------------------------------------------------------------------------
PREGNANCY_CONTRA: dict[str, set[str]] = {
    "禁用": {"附子", "乌头", "半夏", "南星", "麝香", "虻虫", "水蛭", "斑蝥",
             "巴豆", "牵牛", "三棱", "莪术", "商陆", "甘遂", "大戟", "芫花",
             "海藻", "瞿麦", "桃仁", "红花", "牛膝", "干姜", "肉桂", "麝香"},
    "慎用": {"当归", "川芎", "丹参", "益母草", "芍药", "地黄", "黄芩", "牛膝"},
}

# ---------------------------------------------------------------------------
# 4. 中西药相互作用（可配置：药物类 → [(药材, 机制, 等级)]）
# ---------------------------------------------------------------------------
DRUG_INTERACTIONS: dict[str, list[tuple[str, str, Severity]]] = {
    "抗凝药/华法林": [
        ("丹参", "增强抗凝、增加出血风险", "high"),
        ("当归", "含香豆素类，增强抗凝", "high"),
        ("川芎", "抑制血小板聚集", "moderate"),
        ("红花", "活血，增强抗凝", "high"),
        ("桃仁", "活血，增强抗凝", "moderate"),
        ("三七", "双向调节但大剂量增加出血", "moderate"),
        ("银杏叶", "抑制血小板活化因子", "high"),
        ("益母草", "兴奋子宫+活血", "moderate"),
    ],
    "抗血小板药/阿司匹林/氯吡格雷": [
        ("丹参", "叠加抗血小板，出血风险", "high"),
        ("银杏叶", "增加出血风险", "high"),
        ("红花", "出血风险", "moderate"),
    ],
    "降压药": [
        ("麻黄", "麻黄碱升高血压，拮抗降压药", "high"),
        ("甘草", "致水钠潴留、升血压", "moderate"),
        ("人参", "部分患者血压升高", "moderate"),
    ],
    "降糖药/胰岛素/磺脲类": [
        ("甘草", "甘草酸升血糖，拮抗降糖", "moderate"),
        ("人参", "降糖协同，警惕低血糖", "moderate"),
        ("五味子", "影响糖代谢", "low"),
    ],
    "地高辛": [
        ("甘草", "低血钾增加地高辛毒性", "high"),
        ("麻黄", "低钾+心律影响", "moderate"),
    ],
    "镇静催眠药/苯二氮䓬": [
        ("天麻", "中枢抑制增强", "moderate"),
        ("钩藤", "中枢抑制增强", "moderate"),
        ("牛黄", "镇静协同", "moderate"),
    ],
    "单胺氧化酶抑制剂/MAOI": [
        ("麻黄", "含拟交感胺，高血压危象", "high"),
        ("人参", "可能影响血压/情绪", "moderate"),
    ],
    "利尿剂": [
        ("甘草", "低钾风险叠加", "moderate"),
    ],
    "环孢素/免疫抑制剂": [
        ("甘草", "影响免疫与代谢", "moderate"),
    ],
}

# 药物名 → 类别的粗略识别（用于把用户输入的药品名映射到交互库）
_DRUG_NAME_TO_CLASS = {
    "华法林": "抗凝药/华法林", "warfarin": "抗凝药/华法林",
    "阿司匹林": "抗血小板药/阿司匹林/氯吡格雷", "aspirin": "抗血小板药/阿司匹林/氯吡格雷",
    "氯吡格雷": "抗血小板药/阿司匹林/氯吡格雷",
    "降压药": "降压药", "硝苯地平": "降压药", "氨氯地平": "降压药", "缬沙坦": "降压药",
    "胰岛素": "降糖药/胰岛素/磺脲类", "二甲双胍": "降糖药/胰岛素/磺脲类",
    "格列": "降糖药/胰岛素/磺脲类", "磺脲": "降糖药/胰岛素/磺脲类",
    "地高辛": "地高辛", "digoxin": "地高辛",
    "安定": "镇静催眠药/苯二氮䓬", "地西泮": "镇静催眠药/苯二氮䓬",
    "苯二氮": "镇静催眠药/苯二氮䓬",
    "司来吉兰": "单胺氧化酶抑制剂/MAOI", "maoi": "单胺氧化酶抑制剂/MAOI",
    "呋塞米": "利尿剂", "氢氯噻嗪": "利尿剂", "利尿剂": "利尿剂",
    "环孢素": "环孢素/免疫抑制剂", "cyclosporin": "环孢素/免疫抑制剂",
    # 药-草-食三联相互作用补充类别
    "他汀": "降脂药/他汀", "阿托伐他汀": "降脂药/他汀", "辛伐他汀": "降脂药/他汀",
    "瑞舒伐他汀": "降脂药/他汀", "洛伐他汀": "降脂药/他汀",
    "铁": "铁剂", "铁剂": "铁剂", "硫酸亚铁": "铁剂", "ferrous": "铁剂",
    "四环素": "抗生素/四环素", "喹诺酮": "抗生素/四环素", "左氧氟沙星": "抗生素/四环素",
    "环丙沙星": "抗生素/四环素", "多西环素": "抗生素/四环素", "米诺环素": "抗生素/四环素",
    "头孢": "头孢/甲硝唑", "头孢克肟": "头孢/甲硝唑", "头孢呋辛": "头孢/甲硝唑",
    "甲硝唑": "头孢/甲硝唑", "metronidazole": "头孢/甲硝唑",
}


# ---------------------------------------------------------------------------
# 5. 药-草-食三联相互作用（借鉴 DHFI-C 本体思路：food × drug / food × herb）
#    确定性证据级规则；机制多属文献/传统理论，输出须标注非临床结论。
# ---------------------------------------------------------------------------
# 食物名 → canonical（用户口语化食物归一到可匹配的标准名）
FOOD_SYNONYMS: dict[str, str] = {
    "葡萄柚": "葡萄柚", "西柚": "葡萄柚", "柚子": "葡萄柚",
    "菠菜": "高维K食物", "西兰花": "高维K食物", "纳豆": "高维K食物",
    "羽衣甘蓝": "高维K食物", "甘蓝": "高维K食物",
    "牛奶": "牛奶/乳制品", "乳制品": "牛奶/乳制品", "酸奶": "牛奶/乳制品",
    "奶酪": "牛奶/乳制品", "钙片": "牛奶/乳制品", "钙": "牛奶/乳制品",
    "茶": "茶/浓茶", "浓茶": "茶/浓茶", "绿茶": "茶/浓茶", "红茶": "茶/浓茶",
    "咖啡": "茶/浓茶",
    "酒": "酒精", "酒精": "酒精", "白酒": "酒精", "啤酒": "酒精", "红酒": "酒精",
    "萝卜": "萝卜", "白萝卜": "萝卜",
    "辛辣": "辣椒/辛辣", "辣椒": "辣椒/辛辣", "麻辣": "辣椒/辛辣", "花椒": "辣椒/辛辣",
    "高盐": "高盐食物", "咸菜": "高盐食物", "腌制品": "高盐食物",
}


def classify_food(name: str) -> str | None:
    """把用户输入的食物名归一到 canonical；无命中返回 None。"""
    n = (name or "").strip().lower()
    for k, v in FOOD_SYNONYMS.items():
        if k.lower() in n:
            return v
    return None


# 食物 × 西药类别：[(西药类别, 机制, 等级)]
FOOD_DRUG_INTERACTIONS: dict[str, list[tuple[str, str, Severity]]] = {
    "葡萄柚": [
        ("抗凝药/华法林", "葡萄柚抑制 CYP3A4，升高华法林血药浓度、增加出血风险", "high"),
        ("降压药", "葡萄柚升高钙拮抗剂（如硝苯地平）血药浓度，致低血压", "high"),
        ("环孢素/免疫抑制剂", "葡萄柚升高环孢素血药浓度，增加肾毒性", "high"),
        ("降脂药/他汀", "葡萄柚抑制代谢，增加他汀肌病/横纹肌溶解风险", "high"),
    ],
    "高维K食物": [
        ("抗凝药/华法林", "高维生素K食物拮抗华法林抗凝效果，INR 波动", "moderate"),
    ],
    "牛奶/乳制品": [
        ("抗生素/四环素", "钙螯合四环素/喹诺酮，显著降低抗菌药物吸收", "moderate"),
    ],
    "茶/浓茶": [
        ("铁剂", "鞣酸与铁结合，抑制铁剂吸收", "moderate"),
    ],
    "酒精": [
        ("降糖药/胰岛素/磺脲类", "酒精诱发迟发性低血糖，风险高", "high"),
        ("镇静催眠药/苯二氮䓬", "酒精叠加中枢抑制，呼吸抑制风险", "high"),
        ("头孢/甲硝唑", "双硫仑样反应（面红、心悸、呕吐）", "high"),
        ("降压药", "酒精致血压波动/体位性低血压", "low"),
    ],
}

# 食物 × 中药（canonical）：[(药材 canonical, 机制, 等级)]；多为传统理论，标注假说级
FOOD_HERB_INTERACTIONS: dict[str, list[tuple[str, str, Severity]]] = {
    "萝卜": [
        ("人参", "萝卜破气，传统理论认为削弱人参补气效力", "low"),
    ],
    "茶/浓茶": [
        ("人参", "鞣酸/茶碱影响人参皂苷类吸收（传统理论）", "low"),
    ],
    "高盐食物": [
        ("甘草", "高盐叠加甘草水钠潴留，升高血压", "moderate"),
    ],
    "辣椒/辛辣": [
        ("附子", "辛辣助热，传统理论认为加剧温热药燥性", "low"),
        ("肉桂", "辛辣助热，传统理论认为加剧温热药燥性", "low"),
    ],
}


def classify_drug(name: str) -> str | None:
    n = (name or "").strip().lower()
    for k, v in _DRUG_NAME_TO_CLASS.items():
        if k.lower() in n:
            return v
    return None


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------
@dataclass
class SafetyFinding:
    kind: str  # incompatibility / pregnancy / drug_interaction
    severity: Severity
    detail: str
    advice: str = "建议咨询主治医师或执业中药师后再用"


@dataclass
class SafetyReport:
    level: Severity = "low"
    findings: list[SafetyFinding] = field(default_factory=list)
    source: str = "tcm_safety"  # 便于上层溯源

    def add(self, f: SafetyFinding):
        self.findings.append(f)
        order = {"high": 0, "moderate": 1, "low": 2}
        if order[f.severity] < order[self.level]:
            self.level = f.severity

    def has_blocking(self) -> bool:
        return any(f.severity == "high" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "has_high_risk": self.has_blocking(),
            "count": len(self.findings),
            "findings": [
                {
                    "kind": f.kind,
                    "severity": f.severity,
                    "detail": f.detail,
                    "advice": f.advice,
                }
                for f in self.findings
            ],
        }


_PAIR_RULES = [
    ("十八反", EIGHT_ANTAGONISMS),
    ("十九畏", NINETEEN_INCOMPAT),
]


def check_safety(
    herbs: list[str] | None = None,
    formulas: list[list[str]] | None = None,
    medications: list[str] | None = None,
    foods: list[str] | None = None,
    pregnancy: bool = False,
) -> SafetyReport:
    """统一安全入口。

    Args:
        herbs: 单味药材/食物列表（含推荐食疗方的组成）。
        formulas: 复方组成列表，如 [["附子","干姜","甘草"], ...]。
        medications: 用户正在服用的西药名/类名。
        foods: 用户日常/同服食物（药-草-食三联相互作用校验）。
        pregnancy: 是否孕期。
    Returns:
        SafetyReport（含分级与处置建议）。
    """
    report = SafetyReport()
    herbs = [norm(h) for h in (herbs or []) if h]
    formulas = [[norm(h) for h in f] for f in (formulas or [])]
    foods = [classify_food(f) or (f or "").strip() for f in (foods or []) if f]

    # 1. 配伍禁忌：逐对检查十八反/十九畏
    all_herb_sets = [set(herbs)] + [set(f) for f in formulas]
    for label, rules in _PAIR_RULES:
        for a, b in rules:
            for hset in all_herb_sets:
                if a in hset and b in hset:
                    report.add(
                        SafetyFinding(
                            kind="incompatibility",
                            severity="high",
                            detail=f"{label}：{a} 与 {b} 同用属禁忌配伍",
                        )
                    )

    # 2. 中西药相互作用
    for med in medications or []:
        cls = classify_drug(med)
        if not cls:
            continue
        for herb, mechanism, sev in DRUG_INTERACTIONS.get(cls, []):
            present = herb in herbs or any(herb in f for f in formulas)
            if present:
                report.add(
                    SafetyFinding(
                        kind="drug_interaction",
                        severity=sev,
                        detail=f"西药[{med}] 与中药[{herb}]：{mechanism}",
                    )
                )

    # 3. 妊娠禁忌
    if pregnancy:
        for level, herbset in PREGNANCY_CONTRA.items():
            for h in set(herbs) | {hh for f in formulas for hh in f}:
                if h in herbset:
                    report.add(
                        SafetyFinding(
                            kind="pregnancy",
                            severity="high" if level == "禁用" else "moderate",
                            detail=f"妊娠{level}：{h}",
                        )
                    )

    # 4. 药-草-食三联相互作用
    for food in foods:
        # 4a. 食物 × 西药
        for drug_cls, mechanism, sev in FOOD_DRUG_INTERACTIONS.get(food, []):
            hit_med = None
            for med in medications or []:
                if classify_drug(med) == drug_cls:
                    hit_med = med
                    break
            if hit_med:
                report.add(
                    SafetyFinding(
                        kind="food_interaction",
                        severity=sev,
                        detail=f"食物[{food}] 与西药[{hit_med}]：{mechanism}（机制假说，非临床结论）",
                    )
                )
        # 4b. 食物 × 中药
        for herb, mechanism, sev in FOOD_HERB_INTERACTIONS.get(food, []):
            present = herb in herbs or any(herb in f for f in formulas)
            if present:
                report.add(
                    SafetyFinding(
                        kind="food_interaction",
                        severity=sev,
                        detail=f"食物[{food}] 与中药[{herb}]：{mechanism}（传统理论，非临床结论）",
                    )
                )

    return report


if __name__ == "__main__":
    r = check_safety(
        herbs=["甘草", "海藻"],
        formulas=[["附子", "半夏", "干姜"]],
        medications=["华法林", "氨氯地平"],
        pregnancy=True,
    )
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
