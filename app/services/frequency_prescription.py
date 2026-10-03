"""频率疗法处方引擎 — 将五层诊断映射为个性化频率处方"""
import uuid
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# 频率曲库数据（同步自小程序 tracks.js）
# ---------------------------------------------------------------------------

TRACKS = [
    {"id": "FQ-001", "title": "安眠", "subtitle": "174Hz · Delta波", "frequency": 174, "beatFreq": 2,
     "category": "sleep", "bodyParts": ["全身"], "symptoms": ["失眠", "入睡困难", "浅眠"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-001.wav",
     "description": "像大地的心跳，慢慢把你推向深睡", "duration": 30},
    {"id": "FQ-002", "title": "归静", "subtitle": "528Hz · 纯频率", "frequency": 528, "beatFreq": None,
     "category": "relax", "bodyParts": ["全身"], "symptoms": ["疲劳", "压力", "紧张"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-002.wav",
     "description": "爱的频率，让紧绷的身体一点点松开", "duration": 20},
    {"id": "FQ-003", "title": "释然", "subtitle": "396Hz · Alpha波", "frequency": 396, "beatFreq": 10,
     "category": "emotion", "bodyParts": ["胸部", "心脏"], "symptoms": ["焦虑", "恐惧", "内疚"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-003.wav",
     "description": "释放恐惧和内疚，让心回到安全的地方", "duration": 15},
    {"id": "FQ-006", "title": "清醒", "subtitle": "40Hz · Gamma波", "frequency": 40, "beatFreq": 40,
     "category": "focus", "bodyParts": ["头部", "大脑"], "symptoms": ["脑雾", "记忆力差", "注意力不集中"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-006.wav",
     "description": "激活大脑清除废物，让思维重新清晰", "duration": 15},
    {"id": "FQ-007", "title": "净化", "subtitle": "741Hz · 纯频率", "frequency": 741, "beatFreq": None,
     "category": "healing", "bodyParts": ["肝脏", "消化系统"], "symptoms": ["沉闷", "消化不良", "毒素积累"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-007.wav",
     "description": "清理毒素的频率，让身体和心灵一起呼吸", "duration": 20},
    {"id": "FQ-009", "title": "愈合", "subtitle": "285Hz · 纯频率", "frequency": 285, "beatFreq": None,
     "category": "healing", "bodyParts": ["全身", "伤口"], "symptoms": ["疼痛", "炎症", "术后调养"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-009.wav",
     "description": "组织修复的频率，让身体回到完整的状态", "duration": 20},
    {"id": "FQ-010", "title": "入定", "subtitle": "963Hz · Gamma波", "frequency": 963, "beatFreq": 40,
     "category": "spirit", "bodyParts": ["全身", "松果体"], "symptoms": ["烦躁", "精神疲惫", "需要深度放松"],
     "audioSrc": "https://freq-audio-1341839497.cos.ap-shanghai.myqcloud.com/audio/FQ-010.wav",
     "description": "潜入很深很深的水底，世界安静了", "duration": 25},
    {"id": "FQ-011", "title": "深眠", "subtitle": "136.1Hz · OM频率 · Delta波", "frequency": 136.1, "beatFreq": 1,
     "category": "sleep", "bodyParts": ["全身"], "symptoms": ["深度失眠", "多梦", "早醒"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-011.wav",
     "description": "OM的频率包裹你，像回到子宫里的安宁", "duration": 30},
    {"id": "FQ-012", "title": "沉梦", "subtitle": "194.71Hz · 地球日频率 · Delta波", "frequency": 194.71, "beatFreq": 2,
     "category": "sleep", "bodyParts": ["全身"], "symptoms": ["入睡困难", "时差调整", "作息紊乱"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-012.wav",
     "description": "地球自转的频率，和大地的节奏一起呼吸", "duration": 25},
    {"id": "FQ-013", "title": "入观", "subtitle": "210.42Hz · 月亮频率 · Theta波", "frequency": 210.42, "beatFreq": 6,
     "category": "spirit", "bodyParts": ["头部", "全身"], "symptoms": ["需要冥想", "情绪波动", "内心嘈杂"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-013.wav",
     "description": "月亮的频率，带你进入深层冥想", "duration": 20},
    {"id": "FQ-014", "title": "禅定", "subtitle": "172.06Hz · 柏拉图年频率 · Theta波", "frequency": 172.06, "beatFreq": 4,
     "category": "spirit", "bodyParts": ["全身"], "symptoms": ["深度冥想", "精神疲惫", "需要超脱"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-014.wav",
     "description": "宇宙大年的频率，在无限中找到宁静", "duration": 25},
    {"id": "FQ-015", "title": "专注", "subtitle": "432Hz · 自然频率 · Beta波", "frequency": 432, "beatFreq": 14,
     "category": "focus", "bodyParts": ["头部", "大脑"], "symptoms": ["注意力不集中", "工作效率低", "学习困难"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-015.wav",
     "description": "自然调律的专注力，让思维像激光一样聚焦", "duration": 20},
    {"id": "FQ-016", "title": "心流", "subtitle": "528Hz · Beta波 20Hz", "frequency": 528, "beatFreq": 20,
     "category": "focus", "bodyParts": ["头部", "大脑"], "symptoms": ["拖延", "缺乏灵感", "工作卡壳"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-016.wav",
     "description": "进入心流状态，时间感消失，效率翻倍", "duration": 15},
    {"id": "FQ-017", "title": "修复", "subtitle": "285Hz · Theta波 · 组织再生", "frequency": 285, "beatFreq": 6,
     "category": "healing", "bodyParts": ["全身", "能量场"], "symptoms": ["慢性疼痛", "术后调养", "免疫力低"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-017.wav",
     "description": "能量场修复频率，帮助身体回到最佳状态", "duration": 25},
    {"id": "FQ-018", "title": "再生", "subtitle": "396Hz · Alpha波 · 深层放松", "frequency": 396, "beatFreq": 10,
     "category": "healing", "bodyParts": ["肌肉", "关节"], "symptoms": ["肌肉紧张", "关节不适", "慢性疲劳"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-018.wav",
     "description": "释放深层紧张，让身体启动自我修复", "duration": 20},
    {"id": "FQ-019", "title": "释怀", "subtitle": "417Hz · Alpha波 · 情绪转化", "frequency": 417, "beatFreq": 8,
     "category": "emotion", "bodyParts": ["心脏", "胸腔"], "symptoms": ["情绪波动", "焦虑", "压抑"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-019.wav",
     "description": "温和地释放情绪，不需要对抗，只需要流动", "duration": 20},
    {"id": "FQ-020", "title": "连结", "subtitle": "639Hz · Theta波 · 关系修复", "frequency": 639, "beatFreq": 7,
     "category": "emotion", "bodyParts": ["心脏", "喉咙"], "symptoms": ["孤独感", "社交焦虑", "关系修复"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-020.wav",
     "description": "打开心轮的频率，重新感受与世界的连接", "duration": 20},
    {"id": "FQ-021", "title": "觉醒", "subtitle": "741Hz · Gamma波 · 直觉激活", "frequency": 741, "beatFreq": 40,
     "category": "focus", "bodyParts": ["头部", "第三眼"], "symptoms": ["决策困难", "缺乏直觉", "方向不明"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-021.wav",
     "description": "激活直觉中心，看清迷雾中的方向", "duration": 15},
    {"id": "FQ-022", "title": "超越", "subtitle": "852Hz · Gamma波 30Hz", "frequency": 852, "beatFreq": 30,
     "category": "spirit", "bodyParts": ["头部", "顶轮"], "symptoms": ["瓶颈期", "思维受限", "需要突破"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-022.wav",
     "description": "突破思维的天花板，看到更大的世界", "duration": 20},
    {"id": "FQ-023", "title": "大地", "subtitle": "126.22Hz · 太阳频率", "frequency": 126.22, "beatFreq": None,
     "category": "healing", "bodyParts": ["全身", "消化系统"], "symptoms": ["体力不足", "消化弱", "缺乏活力"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-023.wav",
     "description": "太阳的频率，温暖而有力，重新充电", "duration": 25},
    {"id": "FQ-025", "title": "舒缓", "subtitle": "174Hz · Alpha波 · 疼痛缓解", "frequency": 174, "beatFreq": 10,
     "category": "healing", "bodyParts": ["疼痛部位", "全身"], "symptoms": ["头痛", "身体疼痛", "经痛"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-025.wav",
     "description": "疼痛缓解频率，温和地安抚不适", "duration": 20},
    {"id": "FQ-026", "title": "化解", "subtitle": "285Hz · Delta波 · 深层修复", "frequency": 285, "beatFreq": 3,
     "category": "healing", "bodyParts": ["全身", "内脏"], "symptoms": ["慢性病辅助", "内脏调理", "深层修复"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-026.wav",
     "description": "深层修复频率，在睡眠中启动自愈", "duration": 25},
    {"id": "FQ-027", "title": "安心", "subtitle": "396Hz · Theta波 · 恐惧释放", "frequency": 396, "beatFreq": 5,
     "category": "emotion", "bodyParts": ["心脏", "腹部"], "symptoms": ["恐惧", "不安", "恐慌"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-027.wav",
     "description": "温柔地释放恐惧，让安全感从心底升起", "duration": 20},
    {"id": "FQ-028", "title": "平和", "subtitle": "432Hz · Alpha波 12Hz", "frequency": 432, "beatFreq": 12,
     "category": "relax", "bodyParts": ["全身", "呼吸系统"], "symptoms": ["紧张", "呼吸急促", "需要冷静"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-028.wav",
     "description": "自然调律的平和，清醒而安宁", "duration": 15},
    {"id": "FQ-029", "title": "守护", "subtitle": "528Hz · Beta波 15Hz · 免疫激活", "frequency": 528, "beatFreq": 15,
     "category": "healing", "bodyParts": ["免疫系统", "全身"], "symptoms": ["免疫力低", "易感冒", "调养期"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-029.wav",
     "description": "爱的频率激活免疫，让身体重新充满力量", "duration": 20},
    {"id": "FQ-030", "title": "活力", "subtitle": "741Hz · Beta波 18Hz · 排毒净化", "frequency": 741, "beatFreq": 18,
     "category": "healing", "bodyParts": ["肝脏", "淋巴系统"], "symptoms": ["身体沉重", "毒素积累", "代谢慢"],
     "audioSrc": "http://150.158.119.19/freq-audio/FQ-030.wav",
     "description": "排毒净化的频率，让身体轻盈起来", "duration": 15},
]

# 证候 → 频率映射（基于中医-分子-频率三角理论）
SYNDROME_FREQ_MAP = {
    "气虚证": {
        "tracks": ["FQ-023", "FQ-029", "FQ-002", "FQ-028"],
        "rationale": "气虚证对应线粒体ATP生成效率降低。126.22Hz太阳频率补充能量，528Hz免疫激活提升正气，432Hz自然调律恢复节律。",
        "target_pathways": ["hsa04115", "hsa04140"],
        "schedule_type": "energy_boost",
    },
    "阴虚证": {
        "tracks": ["FQ-007", "FQ-030", "FQ-010", "FQ-013"],
        "rationale": "阴虚证对应Nrf2抗氧化通路代偿不足、氧化应激累积。741Hz净化排毒，963Hz深层放松修复，210.42Hz月亮频率滋阴潜阳。",
        "target_pathways": ["custom_nrf2", "hsa04140"],
        "schedule_type": "detox_repair",
    },
    "肾精不足证": {
        "tracks": ["FQ-001", "FQ-011", "FQ-012", "FQ-026", "FQ-017"],
        "rationale": "肾精不足证对应DNA修复能力先天性缺陷。174Hz+Delta波深睡修复，136.1Hz OM频率固本培元，194.71Hz地球频率同步生物节律，285Hz组织再生修复DNA损伤。",
        "target_pathways": ["hsa03440", "hsa03430"],
        "schedule_type": "deep_repair",
    },
    "气滞证": {
        "tracks": ["FQ-003", "FQ-019", "FQ-028", "FQ-018"],
        "rationale": "气滞证对应细胞增殖信号紊乱、气机不畅。396Hz释放恐惧平衡交感神经，417Hz情绪转化，432Hz自然调律恢复气机流通。",
        "target_pathways": ["hsa04110", "hsa04115"],
        "schedule_type": "flow_balance",
    },
    "阳虚证": {
        "tracks": ["FQ-023", "FQ-029", "FQ-011", "FQ-025"],
        "rationale": "阳虚证对应基础代谢率降低、能量生成不足。126.22Hz太阳频率温阳，528Hz免疫激活提升卫气，136.1Hz OM频率固本。",
        "target_pathways": ["hsa04140", "hsa04920"],
        "schedule_type": "warm_yang",
    },
    "痰湿证": {
        "tracks": ["FQ-007", "FQ-030", "FQ-018", "FQ-028"],
        "rationale": "痰湿证对应代谢综合征、炎症状态。741Hz净化清理代谢产物，432Hz平和调律恢复代谢平衡，396Hz放松促进淋巴流动。",
        "target_pathways": ["hsa04620", "hsa04931"],
        "schedule_type": "metabolic_clear",
    },
    "血瘀证": {
        "tracks": ["FQ-025", "FQ-017", "FQ-009", "FQ-028"],
        "rationale": "血瘀证对应微循环障碍、慢性炎症。174Hz缓解疼痛改善循环，285Hz组织再生修复血管，432Hz自然调律恢复血流节律。",
        "target_pathways": ["hsa04610", "hsa04611"],
        "schedule_type": "circulation",
    },
    "湿热证": {
        "tracks": ["FQ-007", "FQ-030", "FQ-003", "FQ-028"],
        "rationale": "湿热证对应氧化应激+炎症双重负荷。741Hz净化排毒，396Hz释放焦虑平复炎症反应，432Hz平和清热。",
        "target_pathways": ["hsa04620", "custom_nrf2"],
        "schedule_type": "clear_heat",
    },
}

# 细胞通路 → 频率映射
PATHWAY_FREQ_MAP = {
    "hsa03440": {"tracks": ["FQ-026", "FQ-017", "FQ-011"], "rationale": "同源重组修复缺陷 → 深层睡眠中启动DNA修复"},
    "hsa04115": {"tracks": ["FQ-003", "FQ-027", "FQ-028"], "rationale": "p53信号下调 → 396Hz释放恐惧，恢复细胞安全感"},
    "hsa04140": {"tracks": ["FQ-010", "FQ-013", "FQ-014"], "rationale": "自噬/AMPK通路 → 963Hz深层放松，Theta波促进细胞自噬清理"},
    "custom_nrf2": {"tracks": ["FQ-007", "FQ-030", "FQ-029"], "rationale": "Nrf2抗氧化通路 → 741Hz净化排毒，528Hz免疫激活"},
    "hsa04110": {"tracks": ["FQ-015", "FQ-016", "FQ-006"], "rationale": "细胞周期紊乱 → 40Hz Gamma波激活大脑，Beta波提升专注力"},
    "hsa04620": {"tracks": ["FQ-007", "FQ-030", "FQ-018"], "rationale": "炎症通路激活 → 741Hz净化，396Hz放松抗炎"},
}

# 症状 → 频率映射
SYMPTOM_FREQ_MAP = {
    "失眠": ["FQ-001", "FQ-011", "FQ-012"],
    "入睡困难": ["FQ-001", "FQ-012"],
    "焦虑": ["FQ-003", "FQ-019", "FQ-027"],
    "疲劳": ["FQ-002", "FQ-018", "FQ-023"],
    "疼痛": ["FQ-009", "FQ-025", "FQ-017"],
    "脑雾": ["FQ-006", "FQ-015", "FQ-021"],
    "注意力不集中": ["FQ-006", "FQ-015"],
    "压力大": ["FQ-002", "FQ-028", "FQ-019"],
    "免疫力低": ["FQ-029", "FQ-023", "FQ-017"],
    "情绪波动": ["FQ-019", "FQ-027", "FQ-020"],
    "消化不良": ["FQ-007", "FQ-023"],
    "紧张": ["FQ-002", "FQ-028", "FQ-018"],
}


# ---------------------------------------------------------------------------
# 处方引擎
# ---------------------------------------------------------------------------

class FrequencyPrescriptionEngine:
    """频率处方引擎 — 基于五层诊断生成个性化频率疗法方案"""

    def generate_prescription(
        self,
        user_id: str,
        diagnosis_data: dict,
        tcm_symptoms: list[str] | None = None,
    ) -> dict:
        """
        根据五层诊断数据生成频率处方。

        Args:
            user_id: 用户ID
            diagnosis_data: 五层诊断数据（含 layer3_pathways, layer4_syndromes）
            tcm_symptoms: 额外中医症状

        Returns:
            频率处方字典
        """
        logger.info(f"生成频率处方 | user_id={user_id}")

        layers = diagnosis_data.get("layers", {})
        pathways = layers.get("layer3_pathways", [])
        syndromes = layers.get("layer4_syndromes", [])
        interventions = layers.get("layer5_interventions", [])

        # 收集所有推荐曲目ID
        track_ids: set[str] = set()
        rationale_parts: list[str] = []

        # 1. 基于证候映射
        for syndrome in syndromes:
            name = syndrome.get("name", "")
            mapping = SYNDROME_FREQ_MAP.get(name)
            if mapping:
                track_ids.update(mapping["tracks"])
                rationale_parts.append(f"【{name}】{mapping['rationale']}")

        # 2. 基于通路映射
        for pw in pathways:
            pw_id = pw.get("pathway_id", "")
            mapping = PATHWAY_FREQ_MAP.get(pw_id)
            if mapping:
                track_ids.update(mapping["tracks"])
                rationale_parts.append(f"【{pw.get('display_name', pw_id)}】{mapping['rationale']}")

        # 3. 基于症状映射
        symptoms = tcm_symptoms or []
        for symptom in symptoms:
            ids = SYMPTOM_FREQ_MAP.get(symptom, [])
            track_ids.update(ids)

        # 4. 默认保底
        if not track_ids:
            track_ids = {"FQ-002", "FQ-028", "FQ-001"}
            rationale_parts.append("基于整体放松与睡眠修复的基础方案")

        # 构建曲目详情列表
        tracks = []
        for tid in track_ids:
            track = self._get_track_by_id(tid)
            if track:
                tracks.append(track)

        # 去重并排序（按证候相关度）
        tracks = self._sort_tracks_by_relevance(tracks, syndromes, pathways)

        # 生成日程安排
        daily_plan = self._build_daily_plan(tracks, syndromes)
        weekly_plan = self._build_weekly_plan(tracks, daily_plan)

        prescription = {
            "prescription_id": str(uuid.uuid4()),
            "user_id": user_id,
            "created_at": self._now_iso(),
            "source_diagnosis_id": diagnosis_data.get("user_id", "unknown"),
            "rationale": "\n\n".join(rationale_parts) if rationale_parts else "基于整体健康调律的频率处方",
            "syndromes": [s.get("name") for s in syndromes],
            "pathways": [p.get("display_name", p.get("pathway_id")) for p in pathways],
            "tracks": tracks,
            "daily_plan": daily_plan,
            "weekly_plan": weekly_plan,
            "expected_outcomes": self._build_expected_outcomes(syndromes, pathways),
            "contraindications": self._build_contraindications(tracks),
            "usage_tips": self._build_usage_tips(tracks),
        }

        logger.info(f"频率处方生成完成 | prescription_id={prescription['prescription_id']} | tracks={len(tracks)}")
        return prescription

    def _get_track_by_id(self, track_id: str) -> dict | None:
        """根据ID获取曲目详情"""
        for t in TRACKS:
            if t["id"] == track_id:
                return {
                    "track_id": t["id"],
                    "title": t["title"],
                    "subtitle": t["subtitle"],
                    "frequency": t["frequency"],
                    "beatFreq": t["beatFreq"],
                    "category": t["category"],
                    "description": t["description"],
                    "duration": t["duration"],
                    "audioSrc": t["audioSrc"],
                    "symptoms": t["symptoms"],
                    "bodyParts": t["bodyParts"],
                }
        return None

    def _sort_tracks_by_relevance(
        self,
        tracks: list[dict],
        syndromes: list[dict],
        pathways: list[dict],
    ) -> list[dict]:
        """按与诊断的相关度排序曲目"""
        syndrome_names = {s.get("name", "") for s in syndromes}
        pathway_ids = {p.get("pathway_id", "") for p in pathways}

        def score(track: dict) -> int:
            s = 0
            tid = track["track_id"]
            # 证候匹配
            for sn in syndrome_names:
                mapping = SYNDROME_FREQ_MAP.get(sn)
                if mapping and tid in mapping["tracks"]:
                    s += 10
            # 通路匹配
            for pwid in pathway_ids:
                mapping = PATHWAY_FREQ_MAP.get(pwid)
                if mapping and tid in mapping["tracks"]:
                    s += 8
            # 睡眠类证候优先睡眠曲目
            if "失眠" in str(syndrome_names) and track["category"] == "sleep":
                s += 5
            return s

        tracks.sort(key=score, reverse=True)
        return tracks

    def _build_daily_plan(self, tracks: list[dict], syndromes: list[dict]) -> dict:
        """构建每日频率日程"""
        # 识别主要证候类型
        syndrome_names = [s.get("name", "") for s in syndromes]
        has_sleep_issue = any("失眠" in str(s) or "入睡" in str(s) or "早醒" in str(s) for s in syndrome_names)
        has_qi_deficiency = "气虚证" in syndrome_names
        has_yin_deficiency = "阴虚证" in syndrome_names

        plan: dict[str, Any] = {}

        # 早晨：能量/专注
        morning_tracks = [t for t in tracks if t["category"] in ("focus", "healing", "spirit")]
        if has_qi_deficiency:
            morning_tracks = [t for t in tracks if t["track_id"] in ("FQ-023", "FQ-029", "FQ-015")] or morning_tracks
        if morning_tracks:
            plan["morning"] = {
                "time": "07:00-09:00",
                "track": morning_tracks[0],
                "duration": morning_tracks[0]["duration"],
                "purpose": "晨间能量激活，提升日间精力与专注力",
                "tip": "起床后或早餐时聆听，音量适中，配合深呼吸",
            }

        # 午间：放松/情绪
        noon_tracks = [t for t in tracks if t["category"] in ("relax", "emotion")]
        if noon_tracks:
            plan["noon"] = {
                "time": "12:00-14:00",
                "track": noon_tracks[0],
                "duration": noon_tracks[0]["duration"],
                "purpose": "午间放松，缓解压力与紧张",
                "tip": "午餐后或午休前聆听，帮助身心转换节奏",
            }

        # 晚间：修复/睡眠
        evening_tracks = [t for t in tracks if t["category"] in ("sleep", "healing", "spirit")]
        if has_sleep_issue:
            evening_tracks = [t for t in tracks if t["category"] == "sleep"] or evening_tracks
        if has_yin_deficiency:
            evening_tracks = [t for t in tracks if t["track_id"] in ("FQ-007", "FQ-010", "FQ-013")] or evening_tracks
        if evening_tracks:
            plan["evening"] = {
                "time": "21:00-23:00",
                "track": evening_tracks[0],
                "duration": evening_tracks[0]["duration"],
                "purpose": "晚间修复，促进深度睡眠与细胞自愈",
                "tip": "睡前30分钟聆听，调暗灯光，配合渐进式放松",
            }

        # 深夜：深睡
        sleep_tracks = [t for t in tracks if t["category"] == "sleep"]
        if sleep_tracks:
            plan["bedtime"] = {
                "time": "23:00-次日07:00",
                "track": sleep_tracks[0],
                "duration": sleep_tracks[0]["duration"],
                "purpose": "整夜深睡修复，启动细胞DNA修复程序",
                "tip": "入睡前开启，可设置定时关闭，保持音量轻柔",
            }

        return plan

    def _build_weekly_plan(self, tracks: list[dict], daily_plan: dict) -> list[dict]:
        """构建每周进阶计划"""
        weekly = []
        categories = list({t["category"] for t in tracks})

        for day in range(1, 8):
            day_tracks = []
            # 每天侧重不同主题
            if categories:
                cat = categories[(day - 1) % len(categories)]
                day_tracks = [t for t in tracks if t["category"] == cat][:2]
            if not day_tracks and tracks:
                day_tracks = tracks[:2]

            weekly.append({
                "day": day,
                "theme": day_tracks[0]["category"] if day_tracks else "综合调律",
                "tracks": day_tracks,
                "total_duration": sum(t["duration"] for t in day_tracks),
                "focus": f"第{day}天：以{day_tracks[0]['title'] if day_tracks else '综合'}为主轴进行深度调律",
            })

        return weekly

    def _build_expected_outcomes(self, syndromes: list[dict], pathways: list[dict]) -> list[str]:
        """构建预期效果说明"""
        outcomes = []
        syndrome_names = [s.get("name", "") for s in syndromes]

        if "气虚证" in syndrome_names:
            outcomes.append("连续使用7-14天后，日间精力提升，疲劳感减轻，对应线粒体ATP合成效率改善")
        if "阴虚证" in syndrome_names:
            outcomes.append("连续使用14-21天后，抗氧化应激指标改善，睡眠质量提升，对应Nrf2通路活性恢复")
        if "肾精不足证" in syndrome_names:
            outcomes.append("连续使用21-30天后，深度睡眠时长增加，DNA修复效率提升，对应同源重组修复功能改善")
        if "气滞证" in syndrome_names:
            outcomes.append("连续使用7-14天后，情绪稳定性提升，身体紧张感减轻，对应细胞信号传导平衡")
        if "血瘀证" in syndrome_names:
            outcomes.append("连续使用14-21天后，局部循环改善，疼痛缓解，对应微循环与炎症指标改善")

        if not outcomes:
            outcomes.append("连续使用7天后，整体放松度提升，睡眠质量改善，身心节律趋于平衡")

        outcomes.append("频率疗法作为药食同源和日常修复的辅助手段，需持续使用以积累效果")
        return outcomes

    def _build_contraindications(self, tracks: list[dict]) -> list[str]:
        """构建禁忌说明"""
        contras = [
            "癫痫患者慎用含有双声拍（binaural beats）的频率曲目（如标注Delta/Alpha/Theta/Beta/Gamma波）",
            "孕妇建议避免使用强Gamma波（40Hz）频率",
            "佩戴心脏起搏器者请在使用前咨询医生",
            "超声波驱蚊系列（FQ-031至FQ-035）不适用于宠物和婴幼儿",
        ]
        # 检查是否有双声拍曲目
        has_binaural = any(t.get("beatFreq") is not None for t in tracks)
        if not has_binaural:
            contras = [c for c in contras if "双声拍" not in c]
        return contras

    def _build_usage_tips(self, tracks: list[dict]) -> list[str]:
        """构建使用建议"""
        tips = [
            "建议使用耳机以获得完整的双声拍效果（标注需要耳机的曲目）",
            "音量调节至舒适水平，不宜过大（约40-60%音量）",
            "在安静环境中使用，避免操作机械或驾驶时聆听",
            "可配合呼吸练习：吸气4秒-屏息4秒-呼气6秒，增强频率调节效果",
            "建议连续使用同一频率7天以上，让神经系统形成条件反射",
            "记录使用前后的身心状态变化，帮助优化处方",
        ]
        return tips

    def _now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 内存处方存储（生产环境应替换为数据库）
# ---------------------------------------------------------------------------

_prescription_store: dict[str, dict] = {}


def store_prescription(prescription: dict) -> None:
    _prescription_store[prescription["prescription_id"]] = prescription


def get_prescription(prescription_id: str) -> dict | None:
    return _prescription_store.get(prescription_id)


def get_prescriptions_by_user(user_id: str) -> list[dict]:
    return [p for p in _prescription_store.values() if p.get("user_id") == user_id]
