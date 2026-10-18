"""中医食疗推荐引擎
基于古籍知识库 (食疗本草、食疗方、本草纲目) 提供食疗方案
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FoodTherapyRecommendation:
    """食疗推荐结果"""
    name: str
    category: str  # 粥/羹/汤/酒/茶
    ingredients: dict  # 食材及用量
    indications: str  # 主疗
    method: str  # 制法
    source: str  # 古籍出处
    match_reason: str  # 推荐理由
    seasonal: str = "all"


@dataclass
class NonPharmaRecommendation:
    """非药物治疗推荐"""
    treatment_type: str  # diet/acupressure/massage/qigong/lifestyle
    treatment_type_name: str  # 食疗/穴位按压/推拿/气功导引/起居调养
    name: str
    description: str
    indications: str
    instructions: dict
    frequency: str
    duration: str
    precautions: str = ""
    source: str = ""


# 经典食疗方案 (基于《食疗方》《食疗本草》等核心古籍整理)
CLASSICAL_FOOD_RECIPES = [
    # 气虚体质
    {
        "name": "山药粥",
        "category": "粥",
        "ingredients": {"山药": "200g", "粳米": "100g", "白糖": "适量"},
        "indications": "气虚乏力、食欲不振、脾虚泄泻",
        "method": "山药去皮切块，与粳米同煮粥，空腹食之。",
        "source": "《食疗本草》",
        "constitution_types": ["qixu"],
        "syndrome_keywords": ["乏力", "食欲不振", "泄泻", "脾虚"],
        "seasonal": "all",
    },
    {
        "name": "莲子粥",
        "category": "粥",
        "ingredients": {"莲子": "一升(去心)", "粳米": "三合"},
        "indications": "心志不宁、补中强志、聪明耳目",
        "method": "莲子煮熟研如泥，与粳米合作粥，空腹食之。",
        "source": "《食疗方》",
        "constitution_types": ["qixu", "yinxu"],
        "syndrome_keywords": ["失眠", "心悸", "健忘", "心虚"],
        "seasonal": "all",
    },
    {
        "name": "黄精蒸食",
        "category": "丸",
        "ingredients": {"黄精": "适量", "蜜": "适量"},
        "indications": "补气养阴、健脾润肺、益肾",
        "method": "黄精九蒸九曝，去刺人咽喉之性，蒸熟或蜜丸服之。",
        "source": "《食疗本草》",
        "constitution_types": ["qixu", "yinxu"],
        "syndrome_keywords": ["气虚", "阴虚", "肺虚", "肾虚"],
        "seasonal": "all",
    },
    # 阳虚体质
    {
        "name": "姜汁地黄饮",
        "category": "汤",
        "ingredients": {"生姜汁": "半鸡子壳", "生地黄汁": "少许", "蜜": "一匙头", "水": "三合"},
        "indications": "胃气虚、风热、不能食",
        "method": "姜汁、地黄汁、蜜和水三合，顿服。",
        "source": "《食疗本草》",
        "constitution_types": ["yangxu", "qixu"],
        "syndrome_keywords": ["胃寒", "食欲不振", "恶心", "胃气虚"],
        "seasonal": "autumn",
    },
    {
        "name": "花椒姜馄饨",
        "category": "馄饨",
        "ingredients": {"花椒": "适量(烙为末)", "干姜": "等分", "醋": "适量", "面": "适量"},
        "indications": "冷痢",
        "method": "椒末姜末等分，醋和面作小馄饨，水煮更之饮中重煮，停冷吞之，以粥饮下，空腹日一度。",
        "source": "《食疗本草》",
        "constitution_types": ["yangxu"],
        "syndrome_keywords": ["冷痢", "腹泻", "寒湿", "脾寒"],
        "seasonal": "winter",
    },
    # 阴虚体质
    {
        "name": "地黄煎",
        "category": "煎",
        "ingredients": {"地黄": "适量", "蜜": "适量"},
        "indications": "清热滋阴、生津止渴",
        "method": "地黄以少蜜煎，或浸食之，或煎汤，或入酒饮。生则寒，主齿痛、唾血。",
        "source": "《食疗本草》",
        "constitution_types": ["yinxu"],
        "syndrome_keywords": ["口干", "咽燥", "低热", "阴虚"],
        "seasonal": "all",
    },
    {
        "name": "甘菊羹",
        "category": "羹",
        "ingredients": {"甘菊叶": "适量"},
        "indications": "头风目眩、去烦热、利五脏",
        "method": "正月采叶，可作羹食之。",
        "source": "《食疗本草》",
        "constitution_types": ["yinxu", "shire"],
        "syndrome_keywords": ["目眩", "头痛", "烦热", "阴虚"],
        "seasonal": "spring",
    },
    {
        "name": "萝卜粥",
        "category": "粥",
        "ingredients": {"大萝卜": "五个", "粳米": "三合"},
        "indications": "消渴、舌焦、口干、小便数",
        "method": "萝卜煮熟绞取汁，用粳米同水并汁煮粥食之。",
        "source": "《食疗方》",
        "constitution_types": ["yinxu", "shire"],
        "syndrome_keywords": ["消渴", "口干", "小便频数", "糖尿病"],
        "seasonal": "all",
    },
    # 痰湿体质
    {
        "name": "马齿菜粥",
        "category": "粥",
        "ingredients": {"马齿菜": "适量", "粳米": "适量"},
        "indications": "脚气、头面水肿、心腹胀满、小便淋涩",
        "method": "马齿菜洗净取汁，和粳米同煮粥，空腹食之。",
        "source": "《食疗方》",
        "constitution_types": ["tanshi", "shire"],
        "syndrome_keywords": ["水肿", "腹胀", "小便不利", "湿盛"],
        "seasonal": "summer",
    },
    {
        "name": "决明子饮",
        "category": "茶",
        "ingredients": {"决明子": "一匙(去尘埃)"},
        "indications": "肝热毒、风眼赤泪、明目",
        "method": "每日取一匙去尘埃，空腹水吞之。百日后夜见物光。",
        "source": "《食疗本草》",
        "constitution_types": ["shire", "yinxu"],
        "syndrome_keywords": ["目赤", "眼干", "肝热", "头痛"],
        "seasonal": "all",
    },
    # 血瘀体质
    {
        "name": "白蒿菹",
        "category": "菜",
        "ingredients": {"白蒿叶": "适量", "醋": "适量"},
        "indications": "去热黄、心痛",
        "method": "春初采叶生食，醋淹之为菹，甚益人。",
        "source": "《食疗本草》",
        "constitution_types": ["xueyu", "shire"],
        "syndrome_keywords": ["黄疸", "心痛", "湿热", "瘀血"],
        "seasonal": "spring",
    },
    # 中风恢复 (通用)
    {
        "name": "荆芥粥",
        "category": "粥",
        "ingredients": {"荆芥穗": "一两", "薄荷叶": "一两", "豉": "三合", "白粟米": "三合"},
        "indications": "中风、言语蹇涩、精神昏愦、口面歪斜",
        "method": "水四升煮荆芥薄荷豉取三升去滓，下米煮粥，空腹食之。",
        "source": "《食疗方》",
        "constitution_types": ["xueyu", "qiyu", "tanshi"],
        "syndrome_keywords": ["中风", "言语蹇涩", "面瘫", "半身不遂"],
        "seasonal": "all",
    },
    {
        "name": "葛粉羹",
        "category": "羹",
        "ingredients": {"葛根": "半斤(捣粉四两)", "荆芥穗": "一两", "豉": "三合"},
        "indications": "中风、心脾风热、言语蹇涩、手足不遂",
        "method": "先水煮荆芥豉六七沸去滓取汁，葛粉作索面于汁中煮熟，空心服之。",
        "source": "《食疗方》",
        "constitution_types": ["xueyu", "tanshi"],
        "syndrome_keywords": ["中风", "言语不清", "手足不遂"],
        "seasonal": "all",
    },
    {
        "name": "麻子粥",
        "category": "粥",
        "ingredients": {"冬麻子": "二两(炒去皮研)", "白粟米": "三合", "薄荷叶": "一两", "荆芥穗": "一两"},
        "indications": "中风、五脏风热、语言蹇涩、手足不遂、大肠滞涩",
        "method": "水三升煮薄荷荆芥去滓取汁，入麻子仁同煮粥，空腹食之。",
        "source": "《食疗方》",
        "constitution_types": ["xueyu", "yinxu"],
        "syndrome_keywords": ["中风", "便秘", "肠燥", "风热"],
        "seasonal": "autumn",
    },
    # 精气不足
    {
        "name": "鸡头粥",
        "category": "粥",
        "ingredients": {"鸡头实(芡实)": "三合", "粳米": "一合"},
        "indications": "精气不足、强志、明耳目",
        "method": "鸡头实煮熟研如泥，与粳米一合煮粥食之。",
        "source": "《食疗方》",
        "constitution_types": ["qixu", "yinxu", "yangxu"],
        "syndrome_keywords": ["精气不足", "遗精", "尿频", "腰酸"],
        "seasonal": "all",
    },
    # 湿热
    {
        "name": "天门冬蜜煎",
        "category": "煎",
        "ingredients": {"天门冬": "适量(去皮心)", "蜜": "适量"},
        "indications": "补虚劳、治肺劳、止渴、去热风",
        "method": "去皮心入蜜煮之食后服，或曝干入蜜丸尤佳。",
        "source": "《食疗本草》",
        "constitution_types": ["yinxu", "shire"],
        "syndrome_keywords": ["肺虚", "咳嗽", "口渴", "虚劳"],
        "seasonal": "autumn",
    },
]


# 非药物治疗方案
NON_PHARMA_TREATMENTS = [
    {
        "treatment_type": "acupressure",
        "treatment_type_name": "穴位按压",
        "name": "足三里按揉",
        "description": "足三里为足阳明胃经合穴，健脾和胃、扶正培元。",
        "indications": "脾胃虚弱、食欲不振、气虚乏力、消化不良",
        "constitution_types": ["qixu", "yangxu", "tanshi"],
        "syndrome_keywords": ["脾胃虚弱", "食欲不振", "乏力"],
        "instructions": {"取穴": "外膝眼下三寸，胫骨外一横指处", "手法": "拇指按压，由轻到重，以有酸胀感为度", "时间": "每次3-5分钟，每日2-3次"},
        "frequency": "每日2-3次",
        "duration": "30天为一疗程",
        "precautions": "孕妇慎用，饭后1小时方可操作",
        "source": "《灵枢·经脉》",
    },
    {
        "treatment_type": "acupressure",
        "treatment_type_name": "穴位按压",
        "name": "合谷穴按摩",
        "description": "合谷为大肠经原穴，疏风解表、镇痛通络。",
        "indications": "头痛、感冒、牙痛、面瘫、上肢疼痛",
        "constitution_types": ["qiyu", "xueyu", "tebing"],
        "syndrome_keywords": ["头痛", "感冒", "牙痛", "上肢痛"],
        "instructions": {"取穴": "手背虎口处，第一、二掌骨之间", "手法": "拇指按压或揉按，有酸胀感", "时间": "每次2-3分钟，每日3次"},
        "frequency": "每日3次",
        "duration": "7天为一疗程",
        "precautions": "孕妇禁用",
        "source": "《针灸甲乙经》",
    },
    {
        "treatment_type": "acupressure",
        "treatment_type_name": "穴位按压",
        "name": "三阴交按揉",
        "description": "三阴交为肝脾肾三经交会穴，健脾养血、调肝补肾。",
        "indications": "月经不调、失眠、脾胃虚弱、腰膝酸软",
        "constitution_types": ["qixu", "yinxu", "yangxu", "xueyu"],
        "syndrome_keywords": ["失眠", "月经不调", "腰膝酸软", "血虚"],
        "instructions": {"取穴": "内踝尖上三寸，胫骨后缘", "手法": "拇指按揉，酸胀为度", "时间": "每次3-5分钟，每日2次"},
        "frequency": "每日2次",
        "duration": "30天为一疗程",
        "precautions": "孕妇禁用",
        "source": "《针灸甲乙经》",
    },
    {
        "treatment_type": "massage",
        "treatment_type_name": "推拿",
        "name": "腹部按摩",
        "description": "摩腹健脾助运，促进消化吸收，调理肠胃功能。",
        "indications": "脾胃虚弱、便秘、腹胀、消化不良、气虚",
        "constitution_types": ["qixu", "yangxu", "tanshi"],
        "syndrome_keywords": ["腹胀", "便秘", "消化不良", "脾虚"],
        "instructions": {"体位": "仰卧位，放松腹部", "手法": "掌根贴脐，顺时针方向摩腹，力量适中", "时间": "每次15-20分钟，每日1-2次"},
        "frequency": "每日1-2次（早起及睡前）",
        "duration": "30天为一疗程",
        "precautions": "饭后不宜立即进行，孕妇及腹部术后禁用",
        "source": "《千金要方·养性序》",
    },
    {
        "treatment_type": "lifestyle",
        "treatment_type_name": "起居调养",
        "name": "子午觉养生法",
        "description": "顺应阴阳消长规律，子时(23-1时)大睡养阴，午时(11-13时)小憩养阳。",
        "indications": "失眠、心悸、疲劳、阴虚、阳虚",
        "constitution_types": ["yinxu", "yangxu", "qixu", "qiyu"],
        "syndrome_keywords": ["失眠", "疲劳", "心悸", "阴阳失调"],
        "instructions": {"子时": "23:00前入睡，保证7-8小时夜间睡眠", "午时": "11:00-13:00间小憩15-30分钟", "注意": "午睡不宜超过1小时，以免影响夜间睡眠"},
        "frequency": "每日",
        "duration": "长期坚持",
        "precautions": "严重失眠者子时可提前至22:00入睡",
        "source": "《黄帝内经·灵枢》",
    },
    {
        "treatment_type": "lifestyle",
        "treatment_type_name": "起居调养",
        "name": "四季饮食调养",
        "description": "春夏养阳、秋冬养阴，顺应四时调整饮食。",
        "indications": "体质调理、预防疾病、四季养生",
        "constitution_types": ["pinghe", "qixu", "yangxu", "yinxu"],
        "syndrome_keywords": ["体质调理", "养生", "预防"],
        "instructions": {"春季": "少酸增甘，养肝护脾。多食韭菜、菠菜、山药", "夏季": "清淡少油腻，养心健脾。多食绿豆、西瓜、苦瓜", "秋季": "润燥养肺，少辛增酸。多食梨、百合、银耳", "冬季": "温补阳气，补肾御寒。多食羊肉、核桃、黑芝麻"},
        "frequency": "按季节调整",
        "duration": "长期坚持",
        "precautions": "根据自身体质适当调整，不可一味进补",
        "source": "《黄帝内经·素问·四气调神大论》",
    },
    {
        "treatment_type": "qigong",
        "treatment_type_name": "气功导引",
        "name": "八段锦",
        "description": "传统健身功法，调理脏腑、疏通经络、行气活血。",
        "indications": "气虚乏力、肩颈疼痛、心肺功能下降、亚健康",
        "constitution_types": ["qixu", "xueyu", "yinxu", "tanshi"],
        "syndrome_keywords": ["乏力", "肩颈痛", "胸闷", "亚健康"],
        "instructions": {"第一式": "两手托天理三焦", "第二式": "左右开弓似射雕", "第三式": "调理脾胃须单举", "第四式": "五劳七伤往后瞧", "第五式": "摇头摆尾去心火", "第六式": "两手攀足固肾腰", "第七式": "攒拳怒目增气力", "第八式": "背后七颠百病消", "要领": "每次练习8-12遍，配合自然呼吸"},
        "frequency": "每日1-2次",
        "duration": "3个月为一疗程",
        "precautions": "动作宜缓，循序渐进， elderly 适当减少幅度",
        "source": "《八段锦》传统功法",
    },
    {
        "treatment_type": "diet",
        "treatment_type_name": "食疗",
        "name": "体质调理膳食建议",
        "description": "根据体质类型选择适宜食物，避免不利食物。",
        "indications": "体质调理、日常保健",
        "constitution_types": ["pinghe", "qixu", "yangxu", "yinxu", "tanshi", "shire", "xueyu", "qiyu", "tebing"],
        "syndrome_keywords": ["体质调理"],
        "instructions": {
            "qixu": {"宜食": "山药、黄芪炖鸡、红枣、莲子、粳米", "忌食": "萝卜、山楂、茶叶", "原则": "补气健脾"},
            "yangxu": {"宜食": "羊肉、生姜、桂圆、韭菜、核桃", "忌食": "冷饮、西瓜、绿豆、螃蟹", "原则": "温阳散寒"},
            "yinxu": {"宜食": "银耳、百合、梨、蜂蜜、枸杞", "忌食": "辣椒、羊肉、韭菜、煎炸", "原则": "滋阴润燥"},
            "tanshi": {"宜食": "薏米、冬瓜、荷叶、白萝卜", "忌食": "甜食、肥肉、油炸、酒类", "原则": "健脾化湿"},
            "shire": {"宜食": "绿豆、苦瓜、黄瓜、冬瓜", "忌食": "辛辣、油炸、酒类、羊肉", "原则": "清热利湿"},
            "xueyu": {"宜食": "山楂、红花、黑木耳、玫瑰花茶", "忌食": "寒凉、油腻", "原则": "活血化瘀"},
            "qiyu": {"宜食": "玫瑰花茶、佛手、金桔、芹菜", "忌食": "咖啡、浓茶、辛辣", "原则": "疏肝理气"},
            "tebing": {"宜食": "黄芪、大枣、山药、灵芝", "忌食": "海鲜、花粉类食物、过敏原", "原则": "益气固表"},
        },
        "frequency": "日常饮食",
        "duration": "长期坚持",
        "precautions": "根据体质类型选择食物，可以混合体质兼顾调理",
        "source": "《中医体质分类与判定》中华中医药学会",
    },
]


class FoodTherapyEngine:
    """食疗推荐引擎 - 基于体质/证型匹配古籍食疗方案"""

    def recommend_by_constitution(
        self,
        constitution_type: str,
        symptoms: list[str] | None = None,
        seasonal: str | None = None,
        limit: int = 5,
    ) -> list[FoodTherapyRecommendation]:
        """根据体质推荐食疗方案"""
        results = []
        for recipe in CLASSICAL_FOOD_RECIPES:
            types = recipe.get("constitution_types", [])
            if constitution_type not in types:
                continue
            # 季节过滤
            rec_season = recipe.get("seasonal", "all")
            if seasonal and rec_season != "all" and rec_season != seasonal:
                continue
            # 症状匹配加分
            match_reason = f"适用于{constitution_type}体质"
            if symptoms:
                keywords = recipe.get("syndrome_keywords", [])
                matched = [s for s in symptoms if any(kw in s or s in kw for kw in keywords)]
                if matched:
                    match_reason += f"，匹配症状: {', '.join(matched)}"
                elif keywords:
                    # 如果有症状但未匹配，降低优先级但保留
                    match_reason += "（基于体质推荐）"
            results.append(FoodTherapyRecommendation(
                name=recipe["name"],
                category=recipe.get("category", ""),
                ingredients=recipe.get("ingredients", {}),
                indications=recipe.get("indications", ""),
                method=recipe.get("method", ""),
                source=recipe.get("source", ""),
                match_reason=match_reason,
                seasonal=recipe.get("seasonal", "all"),
            ))
        return results[:limit]

    def recommend_by_symptoms(
        self,
        symptoms: list[str],
        constitution_type: str | None = None,
        limit: int = 5,
    ) -> list[FoodTherapyRecommendation]:
        """根据症状推荐食疗方案"""
        results = []
        for recipe in CLASSICAL_FOOD_RECIPES:
            keywords = recipe.get("syndrome_keywords", [])
            matched_kw = []
            for s in symptoms:
                for kw in keywords:
                    if kw in s or s in kw:
                        matched_kw.append(kw)
                        break
            if not matched_kw:
                continue
            if constitution_type:
                types = recipe.get("constitution_types", [])
                if constitution_type not in types:
                    continue
            results.append(FoodTherapyRecommendation(
                name=recipe["name"],
                category=recipe.get("category", ""),
                ingredients=recipe.get("ingredients", {}),
                indications=recipe.get("indications", ""),
                method=recipe.get("method", ""),
                source=recipe.get("source", ""),
                match_reason=f"匹配症状: {', '.join(matched_kw)}",
                seasonal=recipe.get("seasonal", "all"),
            ))
        return results[:limit]

    def get_non_pharma_treatments(
        self,
        constitution_type: str,
        symptoms: list[str] | None = None,
        treatment_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[NonPharmaRecommendation]:
        """获取非药物治疗方案"""
        results = []
        for tx in NON_PHARMA_TREATMENTS:
            types = tx.get("constitution_types", [])
            if constitution_type not in types:
                continue
            if treatment_types and tx.get("treatment_type") not in treatment_types:
                continue
            match_reason = f"适用于{constitution_type}体质"
            if symptoms:
                keywords = tx.get("syndrome_keywords", [])
                matched = [s for s in symptoms if any(kw in s or s in kw for kw in keywords)]
                if matched:
                    match_reason += f"，匹配: {', '.join(matched)}"
            results.append(NonPharmaRecommendation(
                treatment_type=tx["treatment_type"],
                treatment_type_name=tx.get("treatment_type_name", ""),
                name=tx["name"],
                description=tx.get("description", ""),
                indications=tx.get("indications", ""),
                instructions=tx.get("instructions", {}),
                frequency=tx.get("frequency", ""),
                duration=tx.get("duration", ""),
                precautions=tx.get("precautions", ""),
                source=tx.get("source", ""),
            ))
        return results[:limit]