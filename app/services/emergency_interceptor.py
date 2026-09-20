"""
紧急健康信号前置拦截器
========================

HealthLens 是 wellness（健康管理）平台，不做医疗诊断。
但用户可能输入需要立即关注的健康信号（如胸痛、呼吸困难），
此时必须拦截并引导用户立即寻求专业帮助，而非给出 wellness 推荐。

这不是"医疗急症诊断"，而是"健康护栏"——
确保平台在用户可能面临紧急状况时不误导、不延误。
"""

from typing import Optional
from dataclasses import dataclass, field

@dataclass
class EmergencySignal:
    """检测到的紧急健康信号"""
    category: str  # 分类：心血管/呼吸/神经/出血/意识/过敏/其他
    keywords: list[str] = field(default_factory=list)
    urgency: str = "immediate"  # immediate / urgent


@dataclass
class EmergencyCheckResult:
    """拦截检查结果"""
    is_emergency: bool
    signal: Optional[EmergencySignal] = None
    guidance: Optional[str] = None
    message: Optional[str] = None


# ============================================================
# 紧急信号关键词库（按类别）
# ============================================================

# 这些不是"医疗诊断标准"，而是"需要立即关注的健康信号"
# 措辞刻意避开"症状""疾病""医疗"等词

EMERGENCY_KEYWORDS = {
    "心血管": [
        "胸痛", "胸闷", "心前区痛", "胸口痛", "心脏疼",
        "心脏骤停", "心律不齐", "心悸",
    ],
    "呼吸": [
        "呼吸困难", "喘不上气", "无法呼吸", "窒息",
        "呼吸急促", "呼吸衰竭",
    ],
    "神经/卒中": [
        "突然偏瘫", "半身不遂", "一侧肢体无力",
        "言语不清", "口角歪斜", "面部歪斜",
        "突然失明", "视力骤降",
        "剧烈头痛", "剧烈头疼", "从未有过的头痛",
        "晕厥", "昏迷", "意识丧失", "叫不醒",
    ],
    "出血": [
        "大出血", "大量出血", "血流不止",
        "呕血", "呕吐鲜血",
        "黑便", "柏油样便",
        "咳血", "咯血",
    ],
    "过敏/休克": [
        "严重过敏", "过敏性休克",
        "全身皮疹", "全身荨麻疹",
        "喉咙肿胀", "声带肿胀",
        "全身发麻",
    ],
    "中毒": [
        "食物中毒", "误食毒物", "中毒",
        "服用过量", "药物过量",
    ],
    "创伤": [
        "头部外伤", "头部撞击", "脑震荡",
        "骨折", "开放性伤口",
        "刀伤", "枪伤", "严重割伤",
        "烧伤", "烫伤", "严重烧伤",
    ],
    "代谢危机": [
        "血糖极低", "低血糖", "血糖测不出",
        "高血糖", "酮症酸中毒",
        "严重脱水",
    ],
}

# 组合关键词（单个词不够，需要组合才判定为紧急）
COMBO_KEYWORDS = [
    ("胸痛", "放射"),  # 胸痛放射到左臂
    ("胸痛", "出汗"),
    ("呼吸困难", "嘴唇发紫"),
    ("头痛", "呕吐"),  # 剧烈头痛+呕吐
    ("头痛", "视力模糊"),
]

# 需要立即引导就医的指引文本
EMERGENCY_GUIDANCE = """
⚠️ 需要立即关注

您描述的内容包含需要立即寻求专业帮助的健康信号。

**请立即：**
1. 拨打 120 急救电话
2. 前往最近的医院急诊科
3. 联系您的家庭医生或信任的医疗专业人员

**注意：** HealthLens 是健康管理平台，不提供医疗诊断或治疗建议。
在紧急情况下，请优先寻求专业医疗帮助。
""".strip()


def check_emergency(text: str) -> EmergencyCheckResult:
    """
    检查文本中是否包含需要立即关注的健康信号。

    参数：
        text: 用户输入的文本（症状描述、健康评估等）

    返回：
        EmergencyCheckResult：检查结果
    """
    if not text or not isinstance(text, str):
        return EmergencyCheckResult(is_emergency=False)

    text_lower = text.lower()
    matched_signal = None

    # 1. 检查单关键词
    for category, keywords in EMERGENCY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                matched_signal = EmergencySignal(
                    category=category,
                    keywords=[kw],
                    urgency="immediate",
                )
                break
        if matched_signal:
            break

    # 2. 检查组合关键词
    if not matched_signal:
        for combo in COMBO_KEYWORDS:
            if all(kw in text_lower for kw in combo):
                matched_signal = EmergencySignal(
                    category="组合信号",
                    keywords=list(combo),
                    urgency="immediate",
                )
                break

    if matched_signal:
        return EmergencyCheckResult(
            is_emergency=True,
            signal=matched_signal,
            guidance=EMERGENCY_GUIDANCE,
            message=f"检测到需要立即关注的健康信号（{matched_signal.category}），已拦截并引导就医。",
        )

    return EmergencyCheckResult(is_emergency=False)
