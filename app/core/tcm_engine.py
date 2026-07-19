"""中医辨证论治引擎
Phase 1: 基于中华中医药学会标准的九种体质辨识
Phase 2: 知识图谱推理 + 大模型辅助
"""
from dataclasses import dataclass


# 九种体质标准问卷维度和评分
# 每个维度包含若干条目，每条目 1-5 分
CONSTITUTION_DIMENSIONS = {
    "pinghe": {  # 平和质
        "name": "平和质",
        "keywords": ["精力充沛", "睡眠良好", "食欲正常", "二便正常", "面色红润"],
        "threshold": 28,  # 转化分 > threshold 为该体质
    },
    "qixu": {  # 气虚质
        "name": "气虚质",
        "keywords": ["容易疲劳", "气短懒言", "容易感冒", "出汗多", "声音低"],
        "threshold": 26,
    },
    "yangxu": {  # 阳虚质
        "name": "阳虚质",
        "keywords": ["手脚发凉", "怕冷", "吃凉的东西不舒服", "胃怕凉", "腰膝酸冷"],
        "threshold": 26,
    },
    "yinxu": {  # 阴虚质
        "name": "阴虚质",
        "keywords": ["口干咽燥", "手足心热", "感到燥热", "皮肤干燥", "大便干燥"],
        "threshold": 26,
    },
    "tanshi": {  # 痰湿质
        "name": "痰湿质",
        "keywords": ["腹部肥满", "身体沉重", "面部油脂多", "额头油脂", "嗜食肥甘"],
        "threshold": 26,
    },
    "shire": {  # 湿热质
        "name": "湿热质",
        "keywords": ["面部痤疮", "口苦口臭", "大便粘滞", "小便发黄", "阴囊潮湿"],
        "threshold": 26,
    },
    "xueyu": {  # 血瘀质
        "name": "血瘀质",
        "keywords": ["皮肤偏暗", "容易出现瘀斑", "嘴唇颜色偏暗", "舌有瘀点", "眼眶暗黑"],
        "threshold": 26,
    },
    "qiyu": {  # 气郁质
        "name": "气郁质",
        "keywords": ["情绪低落", "多愁善感", "容易紧张", "胸闷叹气", "咽喉异物感"],
        "threshold": 26,
    },
    "tebing": {  # 特禀质
        "name": "特禀质",
        "keywords": ["容易过敏", "打喷嚏", "皮肤过敏", "哮喘", "花粉过敏"],
        "threshold": 24,
    },
}


@dataclass
class TcmConstitutionResult:
    primary_type: str
    scores: dict[str, float]
    description: str
    all_types: list[dict]  # 排名后的所有体质


# 经典方剂数据 - 供 tcm_formula_engine 导入使用
TCM_FORMULAS = {
    "四君子汤": {
        "name": "四君子汤",
        "source": "《太平惠民和剂局方》",
        "category": "补益剂",
        "composition": ["人参", "白术", "茯苓", "甘草"],
        "indications": "脾胃气虚证",
        "modifications": {
            "食欲不振": ["加 山药 15g", "加 砂仁 6g"],
            "容易感冒": ["加 黄芪 15g", "加 防风 6g"],
        },
    },
    "附子理中汤": {
        "name": "附子理中汤",
        "source": "《阎氏小儿方论》",
        "category": "温里剂",
        "composition": ["附子", "人参", "白术", "干姜", "甘草"],
        "indications": "脾胃阳虚证",
        "modifications": {
            "腰膝酸软": ["加 杜仲 12g", "加 牛膝 12g"],
            "水肿": ["加 茯苓 15g", "加 泽泻 9g"],
        },
    },
    "六味地黄丸": {
        "name": "六味地黄丸",
        "source": "《小儿药证直诀》",
        "category": "补益剂",
        "composition": ["熟地黄", "山茱萸", "山药", "泽泻", "茯苓", "牡丹皮"],
        "indications": "肾阴虚证",
        "modifications": {
            "盗汗": ["加 牡蛎 15g", "加 浮小麦 15g"],
            "口干甚": ["加 石斛 12g", "加 麦冬 12g"],
        },
    },
    "二陈汤": {
        "name": "二陈汤",
        "source": "《太平惠民和剂局方》",
        "category": "祛痰剂",
        "composition": ["半夏", "橘红", "白茯苓", "甘草"],
        "indications": "痰湿证",
        "modifications": {
            "肥胖": ["加 苍术 9g", "加 厚朴 6g"],
            "头晕": ["加 天麻 9g", "加 白术 9g"],
        },
    },
    "龙胆泻肝汤": {
        "name": "龙胆泻肝汤",
        "source": "《医方集解》",
        "category": "清热剂",
        "composition": ["龙胆", "黄芩", "栀子", "泽泻", "木通", "车前子", "当归", "生地", "柴胡", "甘草"],
        "indications": "肝胆湿热证",
        "modifications": {
            "口苦甚": ["加 黄连 3g"],
            "小便短赤": ["加 滑石 15g"],
        },
    },
    "血府逐瘀汤": {
        "name": "血府逐瘀汤",
        "source": "《医林改错》",
        "category": "理血剂",
        "composition": ["桃仁", "红花", "当归", "生地", "川芎", "赤芍", "牛膝", "桔梗", "柴胡", "枳壳", "甘草"],
        "indications": "胸中血瘀证",
        "modifications": {
            "疼痛甚": ["加 延胡索 9g", "加 郁金 9g"],
            "气虚": ["加 黄芪 15g"],
        },
    },
}


class TcmDiagnosisEngine:

    def analyze_constitution(self, questionnaire_data: dict) -> TcmConstitutionResult:
        """九种体质辨识

        问卷数据格式: questionnaire_data = {
            "answers": {
                "dim_pinghe": [4, 5, 3, 4, 5],  # 5个条目，1-5分
                "dim_qixu": [3, 4, 2, 3, 0],    # 0表示未答
                ...
            }
        }

        算法: 原始分 = 条目总分
              转化分 = (原始分 - 条目数) / (条目数 * 4) * 100
        """
        answers = questionnaire_data.get("answers", {})
        scores = {}
        all_types = []

        for dim_key, dim_info in CONSTITUTION_DIMENSIONS.items():
            dim_answers = answers.get(f"dim_{dim_key}", [])
            # 过滤 0（未答）
            valid_answers = [a for a in dim_answers if a > 0]

            if not valid_answers:
                scores[dim_key] = 0.0
                continue

            raw_score = sum(valid_answers)
            n_items = len(valid_answers)
            # 转化分公式
            transformed = (raw_score - n_items) / (n_items * 4) * 100
            scores[dim_key] = round(transformed, 1)

            all_types.append({
                "type": dim_info["name"],
                "key": dim_key,
                "score": round(transformed, 1),
                "is_primary": False,
            })

        # 确定主要体质（得分最高的非平和质）
        # 特殊规则：平和质必须 > 60 才算主要，否则取其他最高分
        non_pinghe = {k: v for k, v in scores.items() if k != "pinghe"}
        pinghe_score = scores.get("pinghe", 0)

        if pinghe_score > 60 and all(v < pinghe_score * 0.7 for v in non_pinghe.values()):
            primary_type = "pinghe"
        elif non_pinghe:
            primary_type = max(non_pinghe, key=non_pinghe.get)
        else:
            primary_type = "pinghe"

        # 标记主要体质
        for t in all_types:
            t["is_primary"] = (t["key"] == primary_type)

        # 按分数降序排列
        all_types.sort(key=lambda x: x["score"], reverse=True)

        primary_name = CONSTITUTION_DIMENSIONS[primary_type]["name"]
        description = f"主要体质: {primary_name}"
        if primary_type != "pinghe" and pinghe_score > 30:
            description += f"，兼夹平和质倾向"

        return TcmConstitutionResult(
            primary_type=primary_type,
            scores=scores,
            description=description,
            all_types=all_types,
        )

    async def diagnose_syndrome(
        self,
        symptoms: list[str],
        tongue_analysis: dict | None = None,
        pulse_description: str | None = None,
        constitution: str | None = None,
    ) -> dict:
        """AI 辨证论治 - Phase 1 简化版"""
        # Phase 1: 基于症状关键词匹配的简化辨证
        SYNDROME_MAP = {
            "气虚证": {"keywords": ["疲劳", "气短", "乏力", "懒言", "出汗", "自汗"], "principle": "补气"},
            "阳虚证": {"keywords": ["怕冷", "手脚凉", "腰冷", "膝冷", "畏寒"], "principle": "温阳"},
            "阴虚证": {"keywords": ["口干", "咽干", "手足热", "盗汗", "潮热"], "principle": "滋阴"},
            "痰湿证": {"keywords": ["肥胖", "沉重", "痰多", "嗜睡", "油腻"], "principle": "化痰祛湿"},
            "湿热证": {"keywords": ["口苦", "口臭", "痤疮", "小便黄", "大便粘"], "principle": "清热利湿"},
            "血瘀证": {"keywords": ["疼痛", "瘀斑", "暗沉", "舌暗", "脉涩"], "principle": "活血化瘀"},
        }

        matched = []
        for syndrome, info in SYNDROME_MAP.items():
            match_count = sum(1 for kw in info["keywords"] if any(kw in s for s in symptoms))
            if match_count >= 2:
                matched.append({
                    "syndrome_name": syndrome,
                    "syndrome_code": f"TCD-{len(matched):03d}",
                    "principle": info["principle"],
                    "confidence": min(0.5 + match_count * 0.1, 0.9),
                    "matched_symptoms": [s for s in symptoms if any(kw in s for kw in info["keywords"])],
                })

        if not matched:
            # 默认返回气虚证
            matched.append({
                "syndrome_name": "气虚证",
                "syndrome_code": "TCD-001",
                "principle": "补气",
                "confidence": 0.3,
                "matched_symptoms": [],
            })

        matched.sort(key=lambda x: x["confidence"], reverse=True)
        return matched[0]  # 返回置信度最高的

    def recommend_formula(self, syndrome_code: str, patient_signs: dict) -> dict:
        """方剂推荐与加减 - Phase 1 简化版"""
        FORMULA_MAP = {
            "气虚": {
                "formula": "四君子汤",
                "source": "《太平惠民和剂局方》",
                "composition": ["人参 9g", "白术 9g", "茯苓 9g", "甘草 6g"],
                "modifications": {
                    "食欲不振": ["加 山药 15g", "加 砂仁 6g"],
                    "容易感冒": ["加 黄芪 15g", "加 防风 6g"],
                },
            },
            "阳虚": {
                "formula": "附子理中汤",
                "source": "《阎氏小儿方论》",
                "composition": ["附子 6g", "人参 9g", "白术 9g", "干姜 6g", "甘草 6g"],
                "modifications": {
                    "腰膝酸软": ["加 杜仲 12g", "加 牛膝 12g"],
                    "水肿": ["加 茯苓 15g", "加 泽泻 9g"],
                },
            },
            "阴虚": {
                "formula": "六味地黄丸",
                "source": "《小儿药证直诀》",
                "composition": ["熟地黄 24g", "山茱萸 12g", "山药 12g", "泽泻 9g", "茯苓 9g", "牡丹皮 9g"],
                "modifications": {
                    "盗汗": ["加 牡蛎 15g", "加 浮小麦 15g"],
                    "口干甚": ["加 石斛 12g", "加 麦冬 12g"],
                },
            },
            "痰湿": {
                "formula": "二陈汤",
                "source": "《太平惠民和剂局方》",
                "composition": ["半夏 9g", "橘红 9g", "白茯苓 9g", "甘草 4g"],
                "modifications": {
                    "肥胖": ["加 苍术 9g", "加 厚朴 6g"],
                    "头晕": ["加 天麻 9g", "加 白术 9g"],
                },
            },
            "湿热": {
                "formula": "龙胆泻肝汤",
                "source": "《医方集解》",
                "composition": ["龙胆 6g", "黄芩 9g", "栀子 9g", "泽泻 9g", "木通 6g", "车前子 9g", "当归 9g", "生地 9g", "柴胡 6g", "甘草 6g"],
                "modifications": {
                    "口苦甚": ["加 黄连 3g"],
                    "小便短赤": ["加 滑石 15g"],
                },
            },
            "血瘀": {
                "formula": "血府逐瘀汤",
                "source": "《医林改错》",
                "composition": ["桃仁 12g", "红花 9g", "当归 9g", "生地 9g", "川芎 5g", "赤芍 6g", "牛膝 9g", "桔梗 5g", "柴胡 3g", "枳壳 6g", "甘草 3g"],
                "modifications": {
                    "疼痛甚": ["加 延胡索 9g", "加 郁金 9g"],
                    "气虚": ["加 黄芪 15g"],
                },
            },
        }

        # 从治法匹配
        for principle, info in FORMULA_MAP.items():
            if principle in syndrome_code or principle in str(patient_signs.get("principle", "")):
                formula = dict(info)
                # 根据患者体征加减
                extra_herbs = []
                for sign_key, modifications in info["modifications"].items():
                    if sign_key in str(patient_signs.get("symptoms", "")):
                        extra_herbs.extend(modifications)
                formula["extra_herbs"] = extra_herbs if extra_herbs else None
                return formula

        # 默认返回四君子汤
        formula = dict(FORMULA_MAP["气虚"])
        formula["extra_herbs"] = None
        return formula
