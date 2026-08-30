"""
tcm_text_mining/run.py — 中医古籍文本挖掘

从古籍原文中抽取症状—治法—方药结构化证据，映射到 HealthLens 八轴-通路体系。
借鉴 Hunter/AgentPit SKILL 架构：run(**kwargs) 函数式接口。
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

AXIS_LABELS = {
    "A": "气化/自噬(AMPK-mTOR)",
    "B": "气血-线粒体(PGC-1α/SIRT)",
    "C": "络脉-清瘀(senolytics)",
    "D": "阴阳-昼夜(CLOCK/BMAL1)",
    "E": "脏腑-神经内分泌",
    "F": "正邪-炎症",
    "G": "神-情志(HRV/EEG)",
    "H": "先天-肾精(表观时钟/干细胞)",
}

# 症状关键词
_SYMPATOMS = {
    "疲劳": "B", "乏力": "B", "气短": "B", "喘": "B",
    "瘀": "C", "血瘀": "C", "痛": "C", "炎症": "F",
    "失眠": "D", "睡不好": "D", "昼夜": "D",
    "焦虑": "G", "抑郁": "G", "情志": "G",
    "衰老": "H", "肾": "H", "先天": "H",
    "面色萎黄": "B", "舌淡": "B", "苔白": "B", "脉细": "B",
}
# 治法关键词
_TREATMENTS = {
    "补气": "B", "养血": "B", "健脾": "A", "升阳": "A",
    "活血化瘀": "C", "通络": "C", "清热": "F", "解毒": "F",
    "安神": "G", "镇静": "G", "补肾": "H", "益精": "H",
    "滋阴": "B", "温中": "B", "散寒": "B", "利湿": "F",
}
# 方剂关键词
_FORMULAS = {
    "四君子汤": "B", "四物汤": "B", "补中益气汤": "A",
    "六味地黄丸": "H", "桂枝汤": "B", "麻黄汤": "B",
    "逍遥散": "G", "血府逐瘀汤": "C", "生脉饮": "B",
    "归脾汤": "G", "知柏地黄丸": "H", "金匮肾气丸": "H",
}

_AXIS_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H"]


@dataclass
class Entity:
    symptom: str = ""
    treatment: str = ""
    formula: str = ""
    source_axis: str = ""


def _score_axis(text: str) -> dict[str, float]:
    scores = {a: 0.0 for a in _AXIS_ORDER}
    total = 0
    for kw, axis in {**_SYMPATOMS, **_TREATMENTS, **_FORMULAS}.items():
        count = len(re.findall(re.escape(kw), text))
        if count:
            scores[axis] = min(scores[axis] + count * 0.15, 1.0)
            total += count
    if total == 0:
        return scores
    return {k: round(v / max(total * 0.15, 1), 2) for k, v in scores.items()}


def run(text: str = "", target_axis: str = None, language: str = "zh") -> dict:
    entities: list[Entity] = []
    raw_evidence: list[str] = []

    for line in text.split("。"):
        line = line.strip()
        if not line:
            continue
        raw_evidence.append(line)

        symptom = next((s for s in _SYMPATOMS if s in line), "")
        treatment = next((t for t in _TREATMENTS if t in line), "")
        formula = next((f for f in _FORMULAS if f in line), "")

        axis = ""
        if target_axis:
            axis = target_axis
        elif formula:
            axis = _FORMULAS[formula]
        elif treatment:
            axis = _TREATMENTS[treatment]
        elif symptom:
            axis = _SYMPATOMS[symptom]

        if any([symptom, treatment, formula]):
            entities.append(Entity(symptom, treatment, formula, axis))

    axis_mapping = _score_axis(text)
    confidence = round(max(axis_mapping.values()) if axis_mapping else 0.0, 2)

    return {
        "entities": [asdict(e) for e in entities],
        "axis_mapping": axis_mapping,
        "confidence": confidence,
        "raw_evidence": raw_evidence[:20],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="患者面色萎黄，神疲乏力，舌淡苔白，脉细弱，宜补气养血")
    parser.add_argument("--axis", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = run(text=args.text, target_axis=args.axis)
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    print(out)
