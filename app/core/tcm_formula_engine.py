"""方剂推荐引擎
Phase 1: 基于方剂库的搜索 + 中药详情查询
Phase 2: 知识图谱 + 加减规则推理

参考: 《方剂学》(新世纪第四版), 中华中医药学会
"""
from loguru import logger


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
        """获取中药详情

        Args:
            herb_name: 中药名称
        """
        database = self._get_herb_database()

        herb = database.get(herb_name)
        if herb:
            return {
                "name": herb_name,
                "pinyin": herb["pinyin"],
                "nature": herb["nature"],
                "flavor": herb["flavor"],
                "meridian_tropism": herb["meridian"],
                "effect": herb["effect"],
                "dosage": herb["dosage"],
                "contraindications": herb["contraindications"],
            }

        # 模糊匹配
        for name, info in database.items():
            if herb_name in name or name in herb_name:
                return {
                    "name": name,
                    "pinyin": info["pinyin"],
                    "nature": info["nature"],
                    "flavor": info["flavor"],
                    "meridian_tropism": info["meridian"],
                    "effect": info["effect"],
                    "dosage": info["dosage"],
                    "contraindications": info["contraindications"],
                }

        logger.warning(f"Herb not found: {herb_name}")
        return None

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
