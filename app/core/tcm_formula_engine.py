"""方剂推荐引擎
Phase 1: 基于方剂库的搜索 + 中药详情查询
Phase 2: 知识图谱 + 加减规则推理

参考: 《方剂学》(新世纪第四版), 中华中医药学会
"""
from loguru import logger

import json
import os

from app.core.tcm_safety import check_safety

_CH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CHP_PATH = os.path.join(_CH_ROOT, "data", "tcm_mkg", "chp_entities.json")

_NATURE_MAP = {
    "Warm therapeutic": "温", "Hot therapeutic": "热", "Cold therapeutic": "寒",
    "Cool therapeutic": "凉", "Neutral therapeutic": "平",
}
_FLAVOR_MAP = {
    "Sweet medicinal": "甘", "Bitter medicinal": "苦", "Sour medicinal": "酸",
    "Acrid medicinal": "辛", "Salty medicinal": "咸", "Bland medicinal": "淡",
    "Astringent medicinal": "涩",
}


def _parse_chp_props(props: list[dict]):
    """解析 CHP medicinal_properties → (nature, [flavor], [meridian])。

    nature 取 x_rank 最高的 Therapeutic nature；flavor/meridian 取全部去重。
    """
    nature = None
    flavor: list[str] = []
    meridian: list[str] = []
    best_nature = (-1.0, None)
    for p in props or []:
        cls = p.get("Class")
        mp = p.get("Medicinal_properties", "")
        try:
            xr = float(p.get("x_rank") or 0)
        except (TypeError, ValueError):
            xr = 0.0
        if cls == "Therapeutic nature":
            if xr > best_nature[0]:
                best_nature = (xr, mp)
        elif cls == "Medicinal flavor":
            if mp and mp not in flavor:
                flavor.append(mp)
        elif cls == "Meridian tropism":
            m = mp.replace(" meridian", "").replace("Meridian", "").strip()
            if m and m not in meridian:
                meridian.append(m)
    if best_nature[1]:
        nature = best_nature[1]
    return nature, flavor, meridian


def _load_chp_index():
    """载入 CHP 实体，构建 名称→实体 与 别名→规范名 索引（防御式，缺文件则空）。"""
    index: dict[str, dict] = {}
    syn: dict[str, str] = {}
    try:
        with open(_CHP_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return index, syn
    for e in data.get("entities", []):
        name = e.get("name")
        if not name:
            continue
        nature, flavor, meridian = _parse_chp_props(e.get("medicinal_properties", []))
        rec = {
            "name": name,
            "pinyin": e.get("pinyin", ""),
            "english": e.get("english", ""),
            "nature": _NATURE_MAP.get(nature, nature or ""),
            "flavor": "、".join(_FLAVOR_MAP.get(x, x) for x in flavor),
            "meridian": "、".join(meridian),
            "source": "TCM-MKG(GraphAI-for-TCM, MIT)",
            "evidence_level": e.get("evidence_level", "L3"),
        }
        index[name] = rec
        syn[name] = name
        for s in e.get("synonyms", []) or []:
            if s and s not in syn:
                syn[s] = name
    return index, syn


_CHP_INDEX, _CHP_SYN = _load_chp_index()


class FormulaEngine:
    """方剂库搜索引擎"""

    # 经典方剂数据 (与 tcm_engine.py 中 TCM_FORMULAS 对齐)
    _formula_library: list[dict] | None = None

    # 中药性味归经数据
    _herb_database: dict[str, dict] | None = None

    @classmethod
    def _get_formula_library(cls) -> list[dict]:
        if cls._formula_library is None:
            from app.core.tcm_engine import TCM_FORMULAS
            cls._formula_library = [
                {
                    "id": f"formula_{i}",
                    "name": f["name"],
                    "source": f.get("source", "经典方"),
                    "category": f.get("category", ""),
                    "composition": f.get("composition", []),
                    "indications": f.get("indications", ""),
                    "modifications": f.get("modifications", {}),
                }
                for i, f in enumerate(TCM_FORMULAS.values())
            ]
        return cls._formula_library

    @classmethod
    def _get_herb_database(cls) -> dict[str, dict]:
        if cls._herb_database is None:
            cls._herb_database = {
                "人参": {
                    "pinyin": "Renshen", "nature": "微温", "flavor": "甘、微苦",
                    "meridian": "脾、肺、心、肾经", "effect": "大补元气，补脾益肺，生津，安神",
                    "dosage": "3-9g", "contraindications": "实热证、热毒证忌用",
                },
                "黄芪": {
                    "pinyin": "Huangqi", "nature": "微温", "flavor": "甘",
                    "meridian": "脾、肺经", "effect": "补气升阳，益卫固表，利水消肿",
                    "dosage": "9-30g", "contraindications": "表实邪盛、气滞湿阻忌用",
                },
                "白术": {
                    "pinyin": "Baizhu", "nature": "温", "flavor": "苦、甘",
                    "meridian": "脾、胃经", "effect": "健脾益气，燥湿利水，止汗",
                    "dosage": "6-12g", "contraindications": "阴虚燥渴、气滞胀闷忌用",
                },
                "当归": {
                    "pinyin": "Danggui", "nature": "温", "flavor": "甘、辛",
                    "meridian": "肝、心、脾经", "effect": "补血活血，调经止痛，润肠通便",
                    "dosage": "6-12g", "contraindications": "湿盛中满、大便溏泄忌用",
                },
                "熟地黄": {
                    "pinyin": "Shudihuang", "nature": "微温", "flavor": "甘",
                    "meridian": "肝、肾经", "effect": "滋阴补血，益精填髓",
                    "dosage": "10-30g", "contraindications": "脾胃虚弱、气滞痰多忌用",
                },
                "茯苓": {
                    "pinyin": "Fuling", "nature": "平", "flavor": "甘、淡",
                    "meridian": "心、肺、脾、肾经", "effect": "利水渗湿，健脾，宁心",
                    "dosage": "9-15g", "contraindications": "阴虚津伤者慎用",
                },
                "甘草": {
                    "pinyin": "Gancao", "nature": "平", "flavor": "甘",
                    "meridian": "心、肺、脾、胃经", "effect": "补脾益气，清热解毒，调和诸药",
                    "dosage": "2-10g", "contraindications": "湿盛胀满、水肿者不宜",
                },
                "白芍": {
                    "pinyin": "Baishao", "nature": "微寒", "flavor": "苦、酸",
                    "meridian": "肝、脾经", "effect": "养血调经，敛阴止汗，柔肝止痛",
                    "dosage": "6-15g", "contraindications": "阳衰虚寒之证不宜",
                },
                "柴胡": {
                    "pinyin": "Chaihu", "nature": "微寒", "flavor": "苦、辛",
                    "meridian": "肝、胆、肺经", "effect": "和解表里，疏肝升阳",
                    "dosage": "3-10g", "contraindications": "真阴亏损、肝阳上升忌用",
                },
                "陈皮": {
                    "pinyin": "Chenpi", "nature": "温", "flavor": "辛、苦",
                    "meridian": "脾、肺经", "effect": "理气健脾，燥湿化痰",
                    "dosage": "3-10g", "contraindications": "气虚、阴虚燥咳忌用",
                },
                "半夏": {
                    "pinyin": "Banxia", "nature": "温", "flavor": "辛",
                    "meridian": "脾、胃、肺经", "effect": "燥湿化痰，降逆止呕，消痞散结",
                    "dosage": "3-9g", "contraindications": "阴虚燥咳、出血证忌用",
                },
                "桂枝": {
                    "pinyin": "Guizhi", "nature": "温", "flavor": "辛、甘",
                    "meridian": "心、肺、膀胱经", "effect": "发汗解肌，温通经脉，助阳化气",
                    "dosage": "3-10g", "contraindications": "温热病、阴虚阳盛忌用",
                },
                "丹参": {
                    "pinyin": "Danshen", "nature": "微寒", "flavor": "苦",
                    "meridian": "心、心包、肝经", "effect": "活血祛瘀，通经止痛，清心除烦",
                    "dosage": "9-15g", "contraindications": "月经过多、出血证慎用",
                },
                "川芎": {
                    "pinyin": "Chuanxiong", "nature": "温", "flavor": "辛",
                    "meridian": "肝、胆、心包经", "effect": "活血行气，祛风止痛",
                    "dosage": "3-10g", "contraindications": "阴虚火旺、月经过多忌用",
                },
                "枸杞子": {
                    "pinyin": "Gouqizi", "nature": "平", "flavor": "甘",
                    "meridian": "肝、肾经", "effect": "滋补肝肾，益精明目",
                    "dosage": "6-12g", "contraindications": "外感实热、脾虚泄泻忌用",
                },
            }
        # 合并 CHP 6207 饮片实体（开源蒸馏，MIT）：已策展 15 味优先，其余补 CHP 药性
        for name, rec in _CHP_INDEX.items():
            if name in cls._herb_database:
                continue
            cls._herb_database[name] = {
                "pinyin": rec.get("pinyin", ""),
                "nature": rec.get("nature", ""),
                "flavor": rec.get("flavor", ""),
                "meridian": rec.get("meridian", ""),
                "effect": "",
                "dosage": "",
                "contraindications": "",
                "source": rec.get("source", ""),
                "evidence_level": rec.get("evidence_level", "L3"),
            }
        return cls._herb_database

    def search_library(self, keyword: str, source: str | None = None) -> list[dict]:
        """搜索方剂库

        Args:
            keyword: 搜索关键词(方剂名、功效、主治)
            source: 数据来源过滤 (经典方/自定义)
        """
        library = self._get_formula_library()
        results = []

        for formula in library:
            if source and formula.get("source") != source:
                continue

            # 在名称、功效、主治中搜索
            search_text = f"{formula['name']} {formula.get('indications', '')} {formula.get('category', '')}"
            if keyword.lower() in search_text.lower():
                results.append({
                    "id": formula["id"],
                    "name": formula["name"],
                    "source": formula["source"],
                    "category": formula["category"],
                    "composition_count": len(formula.get("composition", [])),
                    "indications": formula["indications"],
                    "has_modifications": bool(formula.get("modifications")),
                })

        logger.info(f"Formula search: keyword='{keyword}', results={len(results)}")
        return results

    def get_herb_info(self, herb_name: str) -> dict | None:
        """获取中药详情（覆盖策展 15 味 + CHP 6207 饮片）

        Args:
            herb_name: 中药名称或别名
        """
        database = self._get_herb_database()

        herb = database.get(herb_name)
        if herb:
            return self._herb_to_info(herb_name, herb)

        # CHP 别名归一
        canon = _CHP_SYN.get(herb_name)
        if canon and canon in database:
            return self._herb_to_info(canon, database[canon])

        # 模糊匹配
        for name, info in database.items():
            if herb_name in name or name in herb_name:
                return self._herb_to_info(name, info)

        logger.warning(f"Herb not found: {herb_name}")
        return None

    @staticmethod
    def _herb_to_info(name: str, herb: dict) -> dict:
        return {
            "name": name,
            "pinyin": herb.get("pinyin", ""),
            "nature": herb.get("nature", ""),
            "flavor": herb.get("flavor", ""),
            "meridian_tropism": herb.get("meridian", ""),
            "effect": herb.get("effect", ""),
            "dosage": herb.get("dosage", ""),
            "contraindications": herb.get("contraindications", ""),
            "source": herb.get("source", ""),
            "evidence_level": herb.get("evidence_level", ""),
        }

    def check_compatibility(self, herb_names: list[str]) -> dict:
        """配伍禁忌推理：委托 tcm_safety 检查十八反/十九畏/中西药相互作用。

        输入药材名先经 CHP 别名归一，再走经典规则引擎。返回结构化结果：
        {herbs_checked, safe, report}。report 为 tcm_safety.SafetyReport.to_dict()。
        """
        herbs = []
        for h in herb_names or []:
            h = (h or "").strip()
            if not h:
                continue
            canon = _CHP_SYN.get(h, h)  # CHP 别名 → 规范名
            herbs.append(canon)
        report = check_safety(herbs=herbs)
        return {
            "herbs_checked": herbs,
            "safe": not report.has_blocking(),
            "report": report.to_dict(),
        }

    def list_all_herbs(self) -> list[dict]:
        """列出所有已知中药"""
        database = self._get_herb_database()
        return [
            {"name": name, **info}
            for name, info in database.items()
        ]

    def get_formula_composition(self, formula_id: str) -> list[dict]:
        """获取方剂组成详情"""
        library = self._get_formula_library()
        for formula in library:
            if formula["id"] == formula_id:
                herbs = []
                for herb_name in formula.get("composition", []):
                    herb_info = self.get_herb_info(herb_name)
                    herbs.append(herb_info or {"name": herb_name, "note": "暂无详细数据"})
                return herbs
        return []
