"""SEO Content Factory - 自动生成 SEO 优化的健康知识页面

核心引擎：基于中医古籍知识库和生物学数据库，程序化生成符合 GEO 优化标准
（Generative Engine Optimization）的 HTML 知识页面。

设计原则：
  - 倒金字塔开头：前两句必须是一个完整、可直接提取的答案
  - 明确的局限性声明：AI 引擎引用带有局限性声明的内容频率提高 1.7 倍
  - Schema.org 结构化数据：FAQ / Article / MedicalWebPage / HowTo
  - 品牌一致的绿色健康主题（--primary: #0d8a6a）
  - 零外部依赖的响应式页面

依赖：Python 标准库 + loguru
"""
import json
import re
import html as html_mod
from datetime import date
from string import Template
from itertools import product
from pathlib import Path
from typing import Any

from loguru import logger


# ===========================================================================
#  常量：关键词矩阵素材
# ===========================================================================

# 列 1 - 症状词
SYMPTOM_KEYWORDS: list[str] = [
    "失眠", "高血压前期", "慢性疲劳", "血糖偏高", "血脂异常",
    "免疫力低下", "脾胃虚弱", "更年期综合征", "骨密度下降",
    "睡眠障碍", "代谢综合征", "焦虑抑郁", "脑力下降",
    "便秘", "反复感冒", "脱发", "痛经", "过敏体质",
    "口干口苦", "腰膝酸软", "潮热盗汗", "记忆力减退",
    "消化不良", "眼睛干涩", "手脚冰凉", "体重管理困难",
]

# 列 2 - 人群标签
AUDIENCE_KEYWORDS: list[str] = [
    "40岁以上男性", "产后妈妈", "程序员", "更年期女性", "上班族",
    "老年人", "学生", "教师", "医护人员", "健身人群",
    "熬夜人群", "备孕女性", "中青年女性", "高压职场人",
    "久坐人群", "脑力工作者", "睡眠质量差者", "亚健康人群",
]

# 列 3 - 方案类型
SOLUTION_KEYWORDS: list[str] = [
    "食疗方", "穴位按摩", "食养调理", "药食同源", "睡眠修复",
    "体质调理", "经典名方", "季节养生", "药膳搭配", "代茶饮",
    "艾灸方案", "导引功法", "呼吸调节", "作息调整", "情志调摄",
]

# 药食同源核心食材（国家卫健委公布）
FOOD_MEDICINE_HOMOLOGY: list[dict[str, str]] = [
    {"name": "山药", "nature": "平", "meridian": "脾、肺、肾", "effect": "健脾益气、养肺固肾"},
    {"name": "枸杞子", "nature": "平", "meridian": "肝、肾", "effect": "滋补肝肾、明目润肺"},
    {"name": "生姜", "nature": "温", "meridian": "肺、脾、胃", "effect": "温中止呕、散寒解表"},
    {"name": "红枣", "nature": "温", "meridian": "脾、胃", "effect": "补中益气、养血安神"},
    {"name": "莲子", "nature": "平", "meridian": "脾、肾、心", "effect": "补脾止泻、养心安神"},
    {"name": "茯苓", "nature": "平", "meridian": "心、脾、肾", "effect": "健脾渗湿、宁心安神"},
    {"name": "黄芪", "nature": "微温", "meridian": "脾、肺", "effect": "补气升阳、益卫固表"},
    {"name": "薏苡仁", "nature": "凉", "meridian": "脾、胃、肺", "effect": "健脾渗湿、除痹排脓"},
    {"name": "芡实", "nature": "平", "meridian": "脾、肾", "effect": "益肾固精、补脾止泻"},
    {"name": "百合", "nature": "微寒", "meridian": "心、肺", "effect": "养阴润肺、清心安神"},
    {"name": "龙眼肉", "nature": "温", "meridian": "心、脾", "effect": "补益心脾、养血安神"},
    {"name": "黑芝麻", "nature": "平", "meridian": "肝、肾", "effect": "补肝肾、润五脏"},
    {"name": "核桃仁", "nature": "温", "meridian": "肾、肺", "effect": "补肾固精、温肺定喘"},
    {"name": "陈皮", "nature": "温", "meridian": "脾、肺", "effect": "理气健脾、燥湿化痰"},
    {"name": "山楂", "nature": "微温", "meridian": "脾、胃、肝", "effect": "消食化积、活血散瘀"},
    {"name": "桑葚", "nature": "寒", "meridian": "心、肝、肾", "effect": "滋阴补血、生津润燥"},
    {"name": "菊花", "nature": "微寒", "meridian": "肺、肝", "effect": "疏风散热、平肝明目"},
    {"name": "金银花", "nature": "寒", "meridian": "肺、心、胃", "effect": "清热解毒、疏散风热"},
    {"name": "薄荷", "nature": "凉", "meridian": "肺、肝", "effect": "疏散风热、清利头目"},
    {"name": "决明子", "nature": "微寒", "meridian": "肝、大肠", "effect": "清肝明目、润肠通便"},
    {"name": "黄精", "nature": "平", "meridian": "脾、肺、肾", "effect": "补气养阴、健脾润肺"},
    {"name": "阿胶", "nature": "平", "meridian": "肺、肝、肾", "effect": "补血滋阴、润燥止血"},
    {"name": "酸枣仁", "nature": "平", "meridian": "心、肝", "effect": "养心补肝、宁心安神"},
    {"name": "麦冬", "nature": "微寒", "meridian": "心、肺、胃", "effect": "养阴生津、润肺清心"},
    {"name": "罗汉果", "nature": "凉", "meridian": "肺、大肠", "effect": "清热润肺、利咽开音"},
    {"name": "人参", "nature": "微温", "meridian": "脾、肺、心、肾", "effect": "大补元气、补脾益肺"},
    {"name": "当归", "nature": "温", "meridian": "肝、心、脾", "effect": "补血活血、调经止痛"},
    {"name": "杜仲", "nature": "温", "meridian": "肝、肾", "effect": "补肝肾、强筋骨"},
    {"name": "荷叶", "nature": "平", "meridian": "肝、脾、胃", "effect": "清热解暑、升发清阳"},
    {"name": "白芷", "nature": "温", "meridian": "肺、胃、大肠", "effect": "解表散寒、祛风止痛"},
]

# 四级认知阶梯模板（用于 education 类别）
COGNITION_LADDER: dict[str, dict[str, str]] = {
    "cognition": {
        "tag": "认知觉醒",
        "section_title": "为什么这件事比你以为的更重要",
        "pattern": "hook → data → insight → question",
        "cta_level": "了解详情",
    },
    "understanding": {
        "tag": "深度理解",
        "section_title": "背后的科学原理和中医智慧",
        "pattern": "mechanism → evidence → tcm_wisdom → connection",
        "cta_level": "开始体验",
    },
    "trust": {
        "tag": "效果验证",
        "section_title": "这些方案为什么真的有效",
        "pattern": "studies → cases → comparison → credibility",
        "cta_level": "亲自验证",
    },
    "action": {
        "tag": "行动指南",
        "section_title": "从今天开始的 7 天行动计划",
        "pattern": "prepare → day_plan → track → adjust",
        "cta_level": "立即开始",
    },
}

# 品牌配置
SITE_CONFIG: dict[str, str] = {
    "site_name": "HealthLens",
    "base_url": "https://healthlens.com",
    "logo_url": "https://healthlens.com/logo.png",
    "tagline": "基于你独特生物学特征的健康改善量化追踪系统",
}

# 分类路径映射
CATEGORY_PATHS: dict[str, str] = {
    "herbs": "knowledge",
    "conditions": "knowledge",
    "education": "education",
}

# 分类标签映射
CATEGORY_TAGS: dict[str, str] = {
    "herbs": "健康知识库 · 药食同源",
    "conditions": "健康知识库 · 症状调理",
    "education": "健康教育 · 认知升级",
}


# ===========================================================================
#  工具函数
# ===========================================================================

def _slugify(text: str) -> str:
    """将中文/英文文本转为 URL 友好的 slug"""
    # 移除特殊字符，替换空格
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text.strip())
    text = re.sub(r'[\s]+', '-', text)
    # 如果全是中文，简单截取并使用拼音风格（此处用原文+dash）
    return text.lower()


def _escape_html(text: str) -> str:
    """HTML 转义"""
    return html_mod.escape(text)


def _today_iso() -> str:
    """返回今天的 ISO 日期字符串"""
    return date.today().isoformat()


def _estimate_reading_minutes(text: str) -> int:
    """估算阅读时间（中文约 400 字/分钟）"""
    char_count = len(re.sub(r'\s', '', text))
    return max(3, char_count // 400)


# ===========================================================================
#  SeoContentFactory 主类
# ===========================================================================

class SeoContentFactory:
    """SEO 内容工厂 - 程序化生成符合 GEO 标准的健康知识页面

    生成特性：
      - GEO 倒金字塔结构（前两句可被 AI 直接提取引用）
      - 局限性声明（提高 AI 引用率 1.7 倍）
      - 多层 Schema.org 结构化数据
      - 品牌一致的绿色健康主题
      - 零外部依赖的响应式 HTML
    """

    def __init__(
        self,
        site_name: str = SITE_CONFIG["site_name"],
        base_url: str = SITE_CONFIG["base_url"],
        logo_url: str = SITE_CONFIG["logo_url"],
    ):
        self.site_name = site_name
        self.base_url = base_url.rstrip("/")
        self.logo_url = logo_url
        self._generated_slugs: set[str] = set()

    # -------------------------------------------------------------------
    #  核心公共方法
    # -------------------------------------------------------------------

    def generate_page(
        self,
        slug: str,
        title: str,
        content_sections: list[dict[str, Any]],
        faq_items: list[dict[str, str]],
        keywords: list[str],
        category: str = "herbs",
        *,
        related_slugs: list[dict[str, str]] | None = None,
        howto_steps: list[dict[str, str]] | None = None,
        subtitle: str = "",
        medical_audience: str = "",
        points_incentive: int = 0,
    ) -> str:
        """生成完整的 SEO 优化 HTML 页面

        Args:
            slug: URL 路径标识（如 "ginger-food-medicine"）
            title: 页面 H1 标题
            content_sections: 内容区块列表，每项包含：
                - heading: H2 标题
                - body: HTML 内容字符串（可包含 H3/p/mark 等）
            faq_items: FAQ 列表，每项包含：
                - question: 问题
                - answer: 答案
            keywords: SEO 关键词列表
            category: 页面分类（herbs / conditions / education）
            related_slugs: 相关文章列表，每项包含：
                - slug: URL slug
                - title: 文章标题
            howto_steps: HowTo 结构化数据步骤（可选），每项包含：
                - name: 步骤名称
                - text: 步骤说明
            subtitle: 副标题/描述语
            medical_audience: MedicalWebPage 受众描述
            points_incentive: 注册积分激励数量

        Returns:
            完整的 HTML 字符串
        """
        logger.info(f"Generating SEO page: slug={slug}, category={category}")

        cat_path = CATEGORY_PATHS.get(category, "knowledge")
        cat_tag = CATEGORY_TAGS.get(category, "健康知识库")
        canonical_url = f"{self.base_url}/{cat_path}/{slug}"

        # 组装页面数据
        page_data = {
            "slug": slug,
            "title": title,
            "subtitle": subtitle,
            "keywords": keywords,
            "category": category,
            "category_tag": cat_tag,
            "canonical_url": canonical_url,
            "date_published": _today_iso(),
            "date_modified": _today_iso(),
            "faq_items": faq_items,
            "howto_steps": howto_steps or [],
            "related_slugs": related_slugs or [],
            "medical_audience": medical_audience,
            "points_incentive": points_incentive,
            "content_sections": content_sections,
        }

        # 计算 meta description
        if content_sections:
            first_body = content_sections[0].get("body", "")
            plain_text = re.sub(r'<[^>]+>', '', first_body)
            desc = plain_text[:120].strip()
            if len(plain_text) > 120:
                desc += "..."
        else:
            desc = subtitle
        page_data["meta_description"] = desc

        # 计算阅读时间
        all_text = " ".join(s.get("body", "") for s in content_sections)
        page_data["reading_minutes"] = _estimate_reading_minutes(all_text)

        # 生成各组件
        structured_data = self._build_structured_data(page_data)
        meta_tags = self._build_meta_tags(page_data)
        cta_section = self._build_cta_section(page_data)
        internal_links = self._build_internal_links(page_data)
        breadcrumb = self._build_breadcrumb(page_data)
        limitation = self._build_limitation_section(page_data)

        # 渲染完整页面
        html = self._render_full_page(page_data, {
            "structured_data": structured_data,
            "meta_tags": meta_tags,
            "cta_section": cta_section,
            "internal_links": internal_links,
            "breadcrumb": breadcrumb,
            "limitation": limitation,
        })

        self._generated_slugs.add(slug)
        logger.info(f"SEO page generated successfully: {slug} ({len(html)} chars)")
        return html

    def generate_keyword_matrix(self) -> list[dict[str, str]]:
        """生成症状 x 人群 x 方案的关键词组合矩阵

        Returns:
            列表，每项包含 slug 和 title，用于程序化 SEO 批量生成
        """
        logger.info(
            f"Generating keyword matrix: "
            f"{len(SYMPTOM_KEYWORDS)} symptoms x "
            f"{len(AUDIENCE_KEYWORDS)} audiences x "
            f"{len(SOLUTION_KEYWORDS)} solutions"
        )

        results: list[dict[str, str]] = []
        seen_slugs: set[str] = set()

        for symptom, audience, solution in product(
            SYMPTOM_KEYWORDS, AUDIENCE_KEYWORDS, SOLUTION_KEYWORDS
        ):
            # 过滤不合理的组合
            if self._is_invalid_combination(symptom, audience, solution):
                continue

            slug = _slugify(f"{symptom}-{audience}-{solution}")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            title = f"{audience}{symptom}的{solution}指南"
            results.append({
                "slug": slug,
                "title": title,
                "symptom": symptom,
                "audience": audience,
                "solution": solution,
            })

        logger.info(f"Keyword matrix generated: {len(results)} combinations")
        return results

    def batch_generate(
        self,
        count: int = 10,
        category: str = "herbs",
        *,
        output_dir: str | Path | None = None,
        include_html: bool = False,
    ) -> list[dict[str, Any]]:
        """批量生成 N 个 SEO 页面

        Args:
            count: 生成页面数量
            category: 分类
                - herbs: 药食同源食材页面
                - conditions: 症状+人群+方案组合页面
                - education: 四级认知阶梯教育页面
            output_dir: 输出目录（可选，默认不写入磁盘）
            include_html: 是否在返回结果中包含 HTML 内容（用于数据库存储）

        Returns:
            列表，每项包含 slug, title, filepath（如果有输出），
            当 include_html=True 时还包含 content_html, meta_description,
            meta_keywords, word_count, structured_data
        """
        logger.info(f"Batch generating {count} pages, category={category}")

        results: list[dict[str, Any]] = []

        if category == "herbs":
            results = self._batch_herbs(count, output_dir, include_html=include_html)
        elif category == "conditions":
            results = self._batch_conditions(count, output_dir, include_html=include_html)
        elif category == "education":
            results = self._batch_education(count, output_dir, include_html=include_html)
        else:
            logger.warning(f"Unknown category: {category}, falling back to herbs")
            results = self._batch_herbs(count, output_dir, include_html=include_html)

        logger.info(f"Batch generation complete: {len(results)} pages")
        return results

    # -------------------------------------------------------------------
    #  批量生成策略
    # -------------------------------------------------------------------

    def _batch_herbs(
        self, count: int, output_dir: str | Path | None, *, include_html: bool = False
    ) -> list[dict[str, Any]]:
        """药食同源批量生成 - 基于食材属性 + 体质适配"""
        results: list[dict[str, Any]] = []
        herbs = list(FOOD_MEDICINE_HOMOLOGY)
        import random
        random.shuffle(herbs)

        for herb in herbs[:count]:
            slug = _slugify(f"{herb['name']}-food-medicine")
            title = f"{herb['name']}：药食同源智慧的现代科学解读"
            subtitle = (
                f"{herb['name']}是经典的药食同源食材，"
                f"{herb['nature']}性，归{herb['meridian']}经，"
                f"具有{herb['effect']}的功效。"
            )

            content_sections = self._build_herb_sections(herb)
            faq_items = self._build_herb_faqs(herb)
            keywords = [
                herb["name"], "药食同源", herb["effect"].split("、")[0],
                "日常修复", "中医食材", "HealthLens",
            ]

            # 生成相关页面链接
            related = [
                {"slug": _slugify(f"{h['name']}-food-medicine"), "title": f"{h['name']}"}
                for h in herbs[:6] if h["name"] != herb["name"]
            ][:3]

            html_content = self.generate_page(
                slug=slug,
                title=title,
                content_sections=content_sections,
                faq_items=faq_items,
                keywords=keywords,
                category="herbs",
                subtitle=subtitle,
                related_slugs=related,
                points_incentive=50,
            )

            filepath = ""
            if output_dir:
                out = Path(output_dir)
                out.mkdir(parents=True, exist_ok=True)
                fp = out / f"{slug}.html"
                fp.write_text(html_content, encoding="utf-8")
                filepath = str(fp)

            result: dict[str, Any] = {"slug": slug, "title": title, "filepath": filepath}
            if include_html:
                plain = re.sub(r'<[^>]+>', '', html_content)
                result["content_html"] = html_content
                result["meta_description"] = plain[:150].strip()
                result["meta_keywords"] = ",".join(keywords)
                result["word_count"] = len(plain)
            results.append(result)

        return results

    def _batch_conditions(
        self, count: int, output_dir: str | Path | None, *, include_html: bool = False
    ) -> list[dict[str, Any]]:
        """症状+人群+方案批量生成"""
        matrix = self.generate_keyword_matrix()
        results: list[dict[str, Any]] = []

        for item in matrix[:count]:
            slug = item["slug"]
            title = item["title"]
            symptom = item["symptom"]
            audience = item["audience"]
            solution = item["solution"]

            content_sections = self._build_condition_sections(
                symptom, audience, solution
            )
            faq_items = self._build_condition_faqs(symptom, audience, solution)
            keywords = [symptom, audience, solution, "日常修复", "HealthLens"]

            html_content = self.generate_page(
                slug=slug,
                title=title,
                content_sections=content_sections,
                faq_items=faq_items,
                keywords=keywords,
                category="conditions",
                subtitle=f"专为{audience}设计的{symptom}{solution}方案",
                points_incentive=30,
            )

            filepath = ""
            if output_dir:
                out = Path(output_dir)
                out.mkdir(parents=True, exist_ok=True)
                fp = out / f"{slug}.html"
                fp.write_text(html_content, encoding="utf-8")
                filepath = str(fp)

            result: dict[str, Any] = {"slug": slug, "title": title, "filepath": filepath}
            if include_html:
                plain = re.sub(r'<[^>]+>', '', html_content)
                result["content_html"] = html_content
                result["meta_description"] = plain[:150].strip()
                result["meta_keywords"] = ",".join(keywords)
                result["word_count"] = len(plain)
            results.append(result)

        return results

    def _batch_education(
        self, count: int, output_dir: str | Path | None, *, include_html: bool = False
    ) -> list[dict[str, Any]]:
        """四级认知阶梯批量生成"""
        # 教育主题池
        topics = [
            {
                "key": "health-data",
                "cognition": ("为什么你的健康数据比你想的更有价值",
                             "健康数据不只是体检报告上的数字。了解基因、体质和生活方式如何共同决定你的健康走向。"),
                "understanding": ("基因-营养代谢的科学原理",
                                  "从 MTHFR 到维生素 D 代谢，了解基因如何影响你对食物和营养素的反应。"),
                "trust": ("中医修复方案与现代科学的对照验证",
                          "古人总结的食疗方、体质调理方案，在现代双盲实验中表现如何？"),
                "action": ("从今天开始的 7 天健康修复行动",
                          "循序渐进的每日计划，将知识转化为可量化的健康改善行动。"),
            },
            {
                "key": "sleep-repair",
                "cognition": ("睡眠修复不只是'早睡早起'那么简单",
                             "你的基因决定了你最适合的入睡时间、睡眠时长和深度睡眠比例。"),
                "understanding": ("昼夜节律基因与中医子午流注的对应关系",
                                  "现代时间生物学发现 PER/CRY/CLOCK 基因群调控昼夜节律，与中医子午流注理论高度吻合。"),
                "trust": ("睡眠修复方案的真实效果数据",
                          "基于用户修复评分追踪的真实数据，展示中医睡眠方案的效果。"),
                "action": ("7 天睡眠修复行动方案",
                          "从光照管理到药茶搭配的完整计划。"),
            },
            {
                "key": "inflammaging",
                "cognition": ("慢性炎症：衰老和疾病的共同底色",
                             "inflammaging（炎性衰老）是现代医学发现的关键机制，与中医'久病入络'理论相通。"),
                "understanding": ("NRF2 抗氧化通路与中医清热解毒的关联",
                                  "NRF2 是人体最重要的抗氧化通路，其调控机制与中医清热解毒治则有分子层面的对应。"),
                "trust": ("抗炎食疗方案的现代验证",
                          "姜辣素、姜黄素、茶多酚等药食同源成分的抗炎研究汇总。"),
                "action": ("7 天抗炎修复饮食行动方案",
                          "每日核心食材+搭配建议，量化追踪炎症指标变化。"),
            },
            {
                "key": "constitution",
                "cognition": ("九种体质不是'标签'，而是你的健康操作指南",
                             "中华中医药学会标准的九种体质分类，是你个性化健康管理的起点。"),
                "understanding": ("体质的基因基础和可调控机制",
                                  "体质不是固定的——基因表达可以通过饮食和生活方式调控。"),
                "trust": ("体质调理方案在用户中的真实效果",
                          "基于 HealthLens 用户修复评分的体质调理效果统计。"),
                "action": ("14 天体质优化行动方案",
                          "根据你的体质类型，制定个性化的两周调理计划。"),
            },
            {
                "key": "gut-microbiome",
                "cognition": ("肠道菌群：你的第二基因组",
                             "肠道菌群的基因总量是你自身基因的 150 倍，深刻影响着你的免疫、代谢和情绪。"),
                "understanding": ("药食同源食材如何塑造肠道菌群",
                                  "膳食纤维、多酚和多糖类成分是肠道有益菌的食物来源。"),
                "trust": ("菌群调理方案的科学证据",
                          "哪些药食同源食材在随机对照试验中证实能改善菌群组成。"),
                "action": ("7 天肠道修复饮食行动",
                          "每日核心食材+发酵食品搭配方案。"),
            },
        ]

        results: list[dict[str, Any]] = []
        import random
        random.shuffle(topics)

        for topic in topics[:count]:
            for level_key, level_cfg in COGNITION_LADDER.items():
                topic_content = topic.get(level_key)
                if not topic_content:
                    continue

                title, subtitle = topic_content
                slug = _slugify(f"{level_key}-{topic['key']}")

                content_sections = self._build_education_sections(
                    level_key, topic, title, subtitle
                )
                faq_items = self._build_education_faqs(level_key, topic)
                keywords = [
                    title.split("：")[0] if "：" in title else title,
                    level_cfg["tag"], "HealthLens", "日常修复",
                ]

                html_content = self.generate_page(
                    slug=slug,
                    title=title,
                    content_sections=content_sections,
                    faq_items=faq_items,
                    keywords=keywords,
                    category="education",
                    subtitle=subtitle,
                    points_incentive=20,
                )

                filepath = ""
                if output_dir:
                    out = Path(output_dir)
                    out.mkdir(parents=True, exist_ok=True)
                    fp = out / f"{slug}.html"
                    fp.write_text(html_content, encoding="utf-8")
                    filepath = str(fp)

                result: dict[str, Any] = {"slug": slug, "title": title, "filepath": filepath}
                if include_html:
                    plain = re.sub(r'<[^>]+>', '', html_content)
                    result["content_html"] = html_content
                    result["meta_description"] = plain[:150].strip()
                    result["meta_keywords"] = ",".join(keywords)
                    result["word_count"] = len(plain)
                results.append(result)

                if len(results) >= count:
                    break

            if len(results) >= count:
                break

        return results

    # -------------------------------------------------------------------
    #  内容区块生成器（供 batch 使用）
    # -------------------------------------------------------------------

    def _build_herb_sections(self, herb: dict[str, str]) -> list[dict[str, str]]:
        """生成药食同源食材的内容区块"""
        name = herb["name"]
        nature = herb["nature"]
        meridian = herb["meridian"]
        effect = herb["effect"]

        return [
            {
                "heading": f"《神农本草经》中的{name}",
                "body": (
                    f"<p><mark class=\"key\">{name}</mark>在中医古籍中有着悠久的记载。"
                    f"其性{nature}，归{meridian}经，"
                    f"核心功效为{effect}。</p>"
                    f"<p>传统中医认为，{name}作为药食同源的代表食材，"
                    f"可以在日常饮食中长期使用，起到调理体质、预防亚健康的作用。"
                    f"这种「食疗为先」的理念，与现代预防医学不谋而合。</p>"
                ),
            },
            {
                "heading": f"{name}的现代科学验证",
                "body": (
                    f"<p>现代药理学研究发现，{name}中富含多种活性成分，"
                    f"具有抗氧化、抗炎、调节免疫等多重生物学活性。</p>"
                    f"<p>在基因组学层面，{name}中的活性成分能够影响多个信号通路，"
                    f"与炎症修复、代谢调节和免疫平衡密切相关。</p>"
                ),
            },
            {
                "heading": f"{name}的日常食疗方案",
                "body": (
                    f'<div class="recipe-grid">'
                    f'<div class="recipe-card">'
                    f'<h4>{name}粥</h4>'
                    f'<p>适合脾胃虚弱的人群，温和调理。</p>'
                    f'<div class="how">{name}30g + 粳米100g，文火煮粥</div>'
                    f'</div>'
                    f'<div class="recipe-card">'
                    f'<h4>{name}代茶饮</h4>'
                    f'<p>适合日常保健，方便快捷。</p>'
                    f'<div class="how">{name}10g，沸水冲泡，每日1-2杯</div>'
                    f'</div>'
                    f'</div>'
                    f'<div class="callout green">'
                    f'<p><strong>体质适配：</strong>'
                    f'{name}性{nature}，'
                    f'最适合体质偏{self._nature_to_constitution(nature)}的人群。'
                    f'建议先完成体质评估，确定最适合的用量和搭配。</p>'
                    f'</div>'
                ),
            },
        ]

    def _build_herb_faqs(self, herb: dict[str, str]) -> list[dict[str, str]]:
        """生成药食同源食材的 FAQ"""
        name = herb["name"]
        return [
            {
                "question": f"每天吃多少{name}比较合适？",
                "answer": (
                    f"一般建议每天食用{name} 10-30 克（干品）。"
                    f"具体用量因体质而异，阳虚质可适量增加，阴虚质则需控制用量。"
                    f"建议通过体质评估确定个性化用量。"
                ),
            },
            {
                "question": f"{name}有哪些食用禁忌？",
                "answer": (
                    f"{name}性{herb['nature']}，"
                    f"体质偏{self._opposite_nature(herb['nature'])}的人群应减少用量。"
                    f"孕妇、哺乳期妇女及慢性病患者在增加摄入前建议咨询健康管理顾问。"
                ),
            },
            {
                "question": f"{name}和什么搭配效果最好？",
                "answer": (
                    f"{name}常与红枣、枸杞等药食同源食材搭配使用，"
                    f"可起到协同增效的作用。具体搭配方案建议根据个人体质评估结果来确定。"
                ),
            },
        ]

    def _build_condition_sections(
        self, symptom: str, audience: str, solution: str
    ) -> list[dict[str, str]]:
        """生成症状+人群+方案的内容区块"""
        return [
            {
                "heading": f"为什么{audience}容易出现{symptom}",
                "body": (
                    f"<p><mark class=\"key\">{symptom}</mark>是{audience}群体中常见的健康困扰。"
                    f"从中医角度来看，{symptom}的发生与体质偏颇、脏腑功能失调密切相关。</p>"
                    f"<p>现代医学研究也证实，生活方式、环境因素和遗传背景共同影响着"
                    f"{symptom}的发生概率。{audience}由于特定的工作和生活习惯，"
                    f"更容易出现这一症状。</p>"
                ),
            },
            {
                "heading": f"中医对{symptom}的认识",
                "body": (
                    f"<p>中医认为{symptom}的核心病机与体质类型高度相关。"
                    f"不同体质的人群，{symptom}的表现形式和调治方向有所不同。</p>"
                    f"<p>通过体质辨识，可以确定你的{symptom}属于哪种中医证型，"
                    f"从而制定针对性的{solution}方案。</p>"
                ),
            },
            {
                "heading": f"适合{audience}的{solution}方案",
                "body": (
                    f'<div class="callout green">'
                    f'<p>以下方案基于中医辨证论治原则和现代营养学研究，'
                    f'专为{audience}群体设计。建议先完成体质评估，获取个性化方案。</p>'
                    f'</div>'
                    f'<p>方案核心思路是通过{solution}，从源头调理体质，'
                    f'改善{symptom}的内在根源，而非仅针对症状本身。</p>'
                ),
            },
        ]

    def _build_condition_faqs(
        self, symptom: str, audience: str, solution: str
    ) -> list[dict[str, str]]:
        """生成症状+人群+方案的 FAQ"""
        return [
            {
                "question": f"{audience}{symptom}需要去看医生吗？",
                "answer": (
                    f"如果{symptom}持续时间较长（超过两周）或症状加重，"
                    f"建议先到医院进行规范检查，排除器质性疾病。"
                    f"日常保健调理可以作为辅助手段，但不能替代医学诊疗。"
                ),
            },
            {
                "question": f"{solution}多久能看到效果？",
                "answer": (
                    f"中医调理讲究循序渐进，一般需要持续 2-4 周才能感受到明显变化。"
                    f"体质基础较好的人群可能在 1-2 周就有改善。"
                    f"建议配合修复评分量化追踪，客观评估效果。"
                ),
            },
            {
                "question": f"除了{solution}，还需要注意什么？",
                "answer": (
                    f"除了{solution}外，建议关注睡眠质量、运动习惯和情绪管理。"
                    f"这三个维度是健康修复的基础，任何单一方案都需要配合整体生活方式的调整。"
                ),
            },
        ]

    def _build_education_sections(
        self,
        level_key: str,
        topic: dict,
        title: str,
        subtitle: str,
    ) -> list[dict[str, str]]:
        """生成教育页面的内容区块"""
        level_cfg = COGNITION_LADDER[level_key]
        topic_key = topic["key"]

        if level_key == "cognition":
            body = (
                f"<p>{subtitle}</p>"
                f"<p>大多数人忽视了这些数据背后的价值。"
                f"事实上，了解自己的生物学特征，"
                f"是做出精准健康决策的前提。</p>"
                f"<p>HealthLens 平台正是基于这一理念，"
                f"将基因数据、中医体质和生活数据融合分析，"
                f"帮你发现个性化的健康改善机会。</p>"
            )
        elif level_key == "understanding":
            body = (
                f"<p>{subtitle}</p>"
                f"<p>从分子层面到整体体质，这些机制构成了一个完整的调控网络。</p>"
                f"<p>中医古籍中记载的治则治法，"
                f"往往与这些现代科学发现高度吻合——"
                f"这正是 HealthLens 将中医与现代科学融合的根基。</p>"
            )
        elif level_key == "trust":
            body = (
                f"<p>{subtitle}</p>"
                f"<p>效果不是靠想象，而是靠数据说话。</p>"
                f"<p>HealthLens 通过修复评分系统量化追踪每个用户的健康改善进程，"
                f"让效果可衡量、可对比、可优化。</p>"
            )
        else:  # action
            body = (
                f"<p>{subtitle}</p>"
                f'<div class="callout green">'
                f"<p><strong>行动原则：</strong>"
                f"从最简单的一步开始，每天进步一点点。"
                f"不要追求完美，追求持续。</p>"
                f"</div>"
                f"<p> HealthLens 平台会自动追踪你的每日行动，"
                f"通过修复评分量化反馈，让你清晰看到每一天的进步。</p>"
            )

        return [
            {
                "heading": level_cfg["section_title"],
                "body": body,
            },
            {
                "heading": f"为什么这件事对{topic_key.replace('-', '')}至关重要",
                "body": (
                    f"<p>这是一个容易被忽视但实际上非常关键的健康维度。</p>"
                    f"<p>了解其背后的原理，"
                    f"能帮助你做出更明智的日常健康决策。</p>"
                ),
            },
        ]

    def _build_education_faqs(
        self, level_key: str, topic: dict
    ) -> list[dict[str, str]]:
        """生成教育页面的 FAQ"""
        level_cfg = COGNITION_LADDER[level_key]
        topic_key = topic["key"]

        base_faqs = {
            "health-data": [
                {
                    "question": "健康数据到底包括哪些内容？",
                    "answer": (
                        "健康数据远不止体检报告上的数字。它包括你的基因信息、"
                        "生活方式数据（饮食、运动、睡眠模式）、身体指标数据、"
                        "以及环境暴露数据等。这些数据共同构成了你独特的健康画像。"
                    ),
                },
                {
                    "question": "我的健康数据安全吗？",
                    "answer": (
                        "HealthLens 采用端到端加密和去标识化处理，"
                        "确保你的健康数据在传输和存储过程中的安全。"
                        "我们不会将你的数据出售给第三方。"
                    ),
                },
            ],
            "sleep-repair": [
                {
                    "question": "我怎么知道自己的最佳睡眠时间？",
                    "answer": (
                        "基因检测可以揭示你的昼夜节律基因型（如 PER3、CLOCK 等），"
                        "从而推断你最适合的入睡和起床时间。"
                        "HealthLens 会根据你的基因型给出个性化的睡眠建议。"
                    ),
                },
                {
                    "question": "中药助眠和安眠药有什么区别？",
                    "answer": (
                        "中药助眠侧重调理体质、恢复自然睡眠节律，"
                        "如酸枣仁汤、甘麦大枣汤等经典方剂。"
                        "安眠药直接作用于中枢神经系统，可能有依赖性和副作用。"
                        "中药更适合慢性睡眠问题的长期调理。"
                    ),
                },
            ],
        }

        faqs = base_faqs.get(topic_key, [
            {
                "question": "如何开始了解和应用这些知识？",
                "answer": (
                    "从最简单的一步开始：完成 HealthLens 的体质评估和基因分析，"
                    "了解你的独特生物学特征。平台会根据你的数据生成个性化方案。"
                ),
            },
            {
                "question": "这些方案有科学依据吗？",
                "answer": (
                    "HealthLens 的所有方案都基于中医古籍经典理论和现代科学研究证据。"
                    "我们会标注每个方案的古籍出处和现代研究参考文献。"
                ),
            },
        ])

        return faqs

    # -------------------------------------------------------------------
    #  模板组件构建器
    # -------------------------------------------------------------------

    def _build_structured_data(self, page_data: dict) -> str:
        """构建 Schema.org JSON-LD 结构化数据

        包含：Article + FAQPage + MedicalWebPage + HowTo（可选）
        """
        scripts: list[str] = []

        # 1. Article Schema
        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": page_data["title"],
            "description": page_data.get("meta_description", ""),
            "author": {"@type": "Organization", "name": self.site_name},
            "publisher": {
                "@type": "Organization",
                "name": self.site_name,
                "logo": {"@type": "ImageObject", "url": self.logo_url},
            },
            "datePublished": page_data["date_published"],
            "dateModified": page_data["date_modified"],
            "mainEntityOfPage": page_data["canonical_url"],
            "articleSection": page_data["category_tag"],
            "about": page_data["keywords"][:5],
            "inLanguage": "zh-CN",
        }
        scripts.append(
            f'<script type="application/ld+json">\n'
            f"{json.dumps(article_schema, ensure_ascii=False, indent=2)}\n"
            f"</script>"
        )

        # 2. FAQPage Schema
        if page_data["faq_items"]:
            faq_entities = []
            for item in page_data["faq_items"]:
                faq_entities.append({
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": item["answer"],
                    },
                })
            faq_schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": faq_entities,
            }
            scripts.append(
                f'<script type="application/ld+json">\n'
                f"{json.dumps(faq_schema, ensure_ascii=False, indent=2)}\n"
                f"</script>"
            )

        # 3. MedicalWebPage Schema
        medical_schema = {
            "@context": "https://schema.org",
            "@type": "MedicalWebPage",
            "headline": page_data["title"],
            "description": page_data.get("meta_description", ""),
            "author": {"@type": "Organization", "name": self.site_name},
            "publisher": {
                "@type": "Organization",
                "name": self.site_name,
                "logo": {"@type": "ImageObject", "url": self.logo_url},
            },
            "datePublished": page_data["date_published"],
            "dateModified": page_data["date_modified"],
            "mainEntityOfPage": page_data["canonical_url"],
            "about": page_data["keywords"][:5],
            "inLanguage": "zh-CN",
        }
        if page_data.get("medical_audience"):
            medical_schema["medicalAudience"] = {
                "@type": "PeopleAudience",
                "audienceType": page_data["medical_audience"],
            }
        scripts.append(
            f'<script type="application/ld+json">\n'
            f"{json.dumps(medical_schema, ensure_ascii=False, indent=2)}\n"
            f"</script>"
        )

        # 4. HowTo Schema（可选）
        if page_data.get("howto_steps"):
            steps = []
            for i, step in enumerate(page_data["howto_steps"], 1):
                steps.append({
                    "@type": "HowToStep",
                    "position": i,
                    "name": step["name"],
                    "text": step["text"],
                })
            howto_schema = {
                "@context": "https://schema.org",
                "@type": "HowTo",
                "name": page_data["title"],
                "description": page_data.get("meta_description", ""),
                "totalTime": "P7D",
                "step": steps,
            }
            scripts.append(
                f'<script type="application/ld+json">\n'
                f"{json.dumps(howto_schema, ensure_ascii=False, indent=2)}\n"
                f"</script>"
            )

        return "\n  ".join(scripts)

    def _build_meta_tags(self, page_data: dict) -> str:
        """构建 HTML meta 标签（SEO + Open Graph + Twitter Card）"""
        title = _escape_html(page_data["title"])
        description = _escape_html(page_data.get("meta_description", ""))
        keywords = _escape_html(", ".join(page_data["keywords"]))
        canonical = page_data["canonical_url"]

        lines = [
            f'<meta charset="UTF-8">',
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f'<title>{title} | {self.site_name} 健康管理</title>',
            f'<meta name="description" content="{description}">',
            f'<meta name="keywords" content="{keywords}">',
            f'<meta name="author" content="{self.site_name}">',
            f'<meta name="robots" content="index, follow">',
            f'<link rel="canonical" href="{canonical}">',
            # Open Graph
            f'<meta property="og:title" content="{title}">',
            f'<meta property="og:description" content="{description}">',
            f'<meta property="og:type" content="article">',
            f'<meta property="og:url" content="{canonical}">',
            f'<meta property="og:site_name" content="{self.site_name}">',
            f'<meta property="og:locale" content="zh_CN">',
            # Twitter Card
            f'<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{title}">',
            f'<meta name="twitter:description" content="{description}">',
        ]
        return "\n  ".join(lines)

    def _build_cta_section(self, page_data: dict) -> str:
        """构建注册/体验 CTA 区域（含积分激励）"""
        points = page_data.get("points_incentive", 0)
        points_text = f"，注册即送 {points} 积分" if points > 0 else ""
        category = page_data["category"]

        if category == "herbs":
            cta_title = "了解你的体质，精准搭配食材"
            cta_desc = f"完成体质评估，获取个性化的药食同源日常修复方案{points_text}。"
            cta_btn = "免费体质评估"
        elif category == "conditions":
            cta_title = "获取你的个性化调理方案"
            cta_desc = f"HealthLens 根据你的基因和体质数据，生成专属调理方案{points_text}。"
            cta_btn = "立即获取方案"
        elif category == "education":
            cta_title = "从知识到行动，开始你的健康修复之旅"
            cta_desc = f"完成体质评估和基因分析，获取个性化健康改善方案{points_text}。"
            cta_btn = "免费开始"
        else:
            cta_title = "开始你的健康管理之旅"
            cta_desc = f"注册 HealthLens，获取个性化健康方案{points_text}。"
            cta_btn = "立即注册"

        return (
            f'<div class="cta-box">\n'
            f'  <h3>{_escape_html(cta_title)}</h3>\n'
            f'  <p>{_escape_html(cta_desc)}</p>\n'
            f'  <a href="{self.base_url}/start" class="btn">{_escape_html(cta_btn)}</a>\n'
            f'</div>'
        )

    def _build_internal_links(self, page_data: dict) -> str:
        """构建相关文章内部链接区块"""
        related = page_data.get("related_slugs", [])
        if not related:
            return ""

        cat_path = CATEGORY_PATHS.get(page_data["category"], "knowledge")
        links_html = []
        for item in related[:5]:
            url = f"{self.base_url}/{cat_path}/{item['slug']}"
            links_html.append(
                f'<li><a href="{url}">{_escape_html(item["title"])}</a></li>'
            )

        return (
            f'<div class="related-links">\n'
            f'  <h3>相关阅读</h3>\n'
            f'  <ul>\n    '
            + "\n    ".join(links_html)
            + f'\n  </ul>\n'
            f'</div>'
        )

    def _build_breadcrumb(self, page_data: dict) -> str:
        """构建面包屑导航"""
        cat_path = CATEGORY_PATHS.get(page_data["category"], "knowledge")
        cat_label = "健康知识库" if page_data["category"] != "education" else "健康教育"

        return (
            f'<nav class="breadcrumb" aria-label="Breadcrumb">\n'
            f'  <a href="{self.base_url}">首页</a>\n'
            f'  <span class="sep">/</span>\n'
            f'  <a href="{self.base_url}/{cat_path}">{cat_label}</a>\n'
            f'  <span class="sep">/</span>\n'
            f'  <span class="current">{_escape_html(page_data["title"])}</span>\n'
            f'</nav>'
        )

    def _build_limitation_section(self, page_data: dict) -> str:
        """构建局限性声明（GEO 优化关键要素）

        研究表明，带有明确局限性声明的内容被 AI 引擎引用频率提高 1.7 倍。
        """
        return (
            f'<div class="callout limitation">\n'
            f'  <p><strong>内容说明：</strong>'
            f'本文内容基于中医古籍理论和现代科学研究整理，'
            f'仅供健康教育和日常保健参考，不构成医学诊断或治疗建议。'
            f'个体体质差异较大，具体方案建议在专业健康管理顾问指导下实施。'
            f'如有急性或严重症状，请及时就医。</p>\n'
            f'</div>'
        )

    # -------------------------------------------------------------------
    #  完整页面渲染
    # -------------------------------------------------------------------

    def _render_full_page(
        self, page_data: dict, components: dict[str, str]
    ) -> str:
        """渲染完整 HTML 页面"""

        # 构建 content sections HTML
        sections_html = ""
        for section in page_data["content_sections"]:
            heading = _escape_html(section.get("heading", ""))
            body = section.get("body", "")
            sections_html += (
                f'<section class="content-section">\n'
                f'  <h2>{heading}</h2>\n'
                f'  {body}\n'
                f'</section>\n\n'
            )

        # 构建 FAQ HTML
        faq_html = ""
        if page_data["faq_items"]:
            faq_items_html = ""
            for item in page_data["faq_items"]:
                q = _escape_html(item["question"])
                a = _escape_html(item["answer"])
                faq_items_html += (
                    f'<div class="faq-item">\n'
                    f'  <h3>{q}</h3>\n'
                    f'  <p>{a}</p>\n'
                    f'</div>\n'
                )
            faq_html = (
                f'<section class="faq-section">\n'
                f'  <h2>常见疑问</h2>\n'
                f'  {faq_items_html}\n'
                f'</section>\n'
            )

        # 分类标签
        category_tag = page_data.get("category_tag", "健康知识库")
        meta_info = f"{self.site_name} · {_today_iso_display()} · 阅读约 {page_data['reading_minutes']} 分钟"

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {components["meta_tags"]}
  {components["structured_data"]}
  <style>
{self._get_page_css()}
  </style>
</head>
<body>
  <div class="container">
    {components["breadcrumb"]}

    <header class="article-header">
      <span class="tag">{_escape_html(category_tag)}</span>
      <h1>{_escape_html(page_data["title"])}</h1>
      <p class="subtitle">{_escape_html(page_data.get("subtitle", ""))}</p>
      <p class="meta">{meta_info}</p>
    </header>

    <article>
      {components["limitation"]}

      {sections_html}

      {faq_html}

      {components["cta_section"]}
    </article>

    {components["internal_links"]}

    <footer>
      <p>{self.site_name} 健康管理平台 · {SITE_CONFIG["tagline"]}</p>
      <p>本文内容仅供健康教育参考，不构成任何医学建议。</p>
    </footer>
  </div>
</body>
</html>'''

        return html

    def _get_page_css(self) -> str:
        """返回品牌一致的页面 CSS 样式

        绿色健康主题，匹配现有 SEO 页面风格
        """
        return '''    :root {
      --primary: #0d8a6a;
      --primary-dark: #09705a;
      --primary-light: #e6f5f0;
      --bg: #FDFBF7;
      --bg2: #F0F2EC;
      --ink: #2C3E2D;
      --muted: #6B7B6C;
      --rule: #D5DCD6;
      --accent: #0d8a6a;
      --accent2: #D4A843;
      --card-shadow: 0 2px 8px rgba(13,138,106,0.06);
      --radius: 8px;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: 'PingFang SC', 'Microsoft YaHei', -apple-system, sans-serif;
      font-size: 16px;
      line-height: 1.8;
      color: var(--ink);
      background: var(--bg);
      -webkit-font-smoothing: antialiased;
    }

    .container {
      max-width: 780px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }

    /* Breadcrumb */
    .breadcrumb {
      font-size: 0.82rem;
      color: var(--muted);
      margin-bottom: 1.5rem;
    }
    .breadcrumb a {
      color: var(--accent);
      text-decoration: none;
    }
    .breadcrumb a:hover { text-decoration: underline; }
    .breadcrumb .sep { margin: 0 0.4rem; }
    .breadcrumb .current { color: var(--ink); }

    /* Header */
    .article-header {
      text-align: center;
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--rule);
    }
    .article-header .tag {
      display: inline-block;
      background: var(--primary);
      color: #fff;
      font-size: 0.72rem;
      padding: 0.2rem 0.7rem;
      border-radius: 20px;
      margin-bottom: 0.75rem;
      letter-spacing: 0.05em;
    }
    .article-header h1 {
      font-size: 1.6rem;
      font-weight: 700;
      line-height: 1.4;
      color: var(--ink);
      margin-bottom: 0.6rem;
    }
    .article-header .subtitle {
      font-size: 0.95rem;
      color: var(--muted);
      line-height: 1.6;
    }
    .article-header .meta {
      font-size: 0.78rem;
      color: var(--muted);
      margin-top: 0.75rem;
    }

    /* Content Sections */
    .content-section {
      margin-bottom: 2.5rem;
    }
    h2 {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--ink);
      margin-bottom: 0.75rem;
      padding-left: 0.7rem;
      border-left: 3px solid var(--accent);
    }
    h3 {
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--ink);
      margin: 1.25rem 0 0.6rem;
    }
    p {
      margin-bottom: 0.85rem;
    }

    /* Key point highlight */
    mark.key {
      background: none;
      color: var(--accent);
      font-weight: 600;
    }

    /* Definition highlight */
    dfn {
      font-style: normal;
      font-weight: 600;
      color: var(--accent);
      border-bottom: 1px dotted var(--rule);
    }

    /* Data value highlight */
    data {
      font-weight: 600;
      color: var(--accent2);
    }

    /* Callout box */
    .callout {
      background: var(--bg2);
      border-left: 4px solid var(--accent);
      padding: 1.1rem 1.3rem;
      margin: 1.5rem 0;
      border-radius: 0 var(--radius) var(--radius) 0;
    }
    .callout p {
      margin: 0;
      font-size: 0.92rem;
    }
    .callout.green {
      border-left-color: var(--primary);
    }
    .callout.limitation {
      border-left-color: var(--accent2);
      background: #FFF8E8;
    }
    .callout.limitation p {
      font-size: 0.85rem;
      color: #8A7A4A;
    }

    /* Recipe grid */
    .recipe-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.85rem;
      margin: 1.5rem 0;
    }
    .recipe-card {
      background: var(--bg2);
      border-radius: var(--radius);
      padding: 1rem;
      box-shadow: var(--card-shadow);
    }
    .recipe-card h4 {
      font-size: 0.88rem;
      font-weight: 600;
      color: var(--primary);
      margin-bottom: 0.4rem;
    }
    .recipe-card p {
      font-size: 0.82rem;
      color: var(--muted);
      margin: 0;
    }
    .recipe-card .how {
      font-size: 0.78rem;
      color: var(--accent);
      margin-top: 0.4rem;
    }

    /* FAQ Section */
    .faq-section {
      margin-top: 2.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--rule);
    }
    .faq-section h2 {
      text-align: center;
      border-left: none;
      padding-left: 0;
    }
    .faq-item {
      margin-bottom: 1.25rem;
    }
    .faq-item h3 {
      font-size: 0.95rem;
      margin: 0 0 0.4rem;
    }
    .faq-item p {
      font-size: 0.9rem;
      color: var(--muted);
    }

    /* CTA Box */
    .cta-box {
      background: linear-gradient(135deg, var(--primary), var(--primary-dark));
      color: #fff;
      text-align: center;
      padding: 1.75rem;
      border-radius: var(--radius);
      margin: 2.5rem 0 1.5rem;
    }
    .cta-box h3 {
      color: #fff;
      margin: 0 0 0.4rem;
    }
    .cta-box p {
      color: rgba(255,255,255,0.85);
      font-size: 0.9rem;
      margin-bottom: 0.75rem;
    }
    .cta-box .btn {
      display: inline-block;
      background: #fff;
      color: var(--primary);
      padding: 0.55rem 1.4rem;
      border-radius: 20px;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.88rem;
      transition: transform 0.2s, box-shadow 0.2s;
    }
    .cta-box .btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }

    /* Related Links */
    .related-links {
      margin: 2rem 0;
      padding: 1.25rem;
      background: var(--bg2);
      border-radius: var(--radius);
    }
    .related-links h3 {
      font-size: 1rem;
      color: var(--accent);
      margin-bottom: 0.75rem;
    }
    .related-links ul {
      list-style: none;
      padding: 0;
    }
    .related-links li {
      margin-bottom: 0.5rem;
    }
    .related-links a {
      color: var(--accent);
      text-decoration: none;
      font-size: 0.88rem;
    }
    .related-links a:hover {
      text-decoration: underline;
    }

    /* Footer */
    footer {
      text-align: center;
      padding-top: 1.25rem;
      border-top: 1px solid var(--rule);
      font-size: 0.78rem;
      color: var(--muted);
    }

    /* Responsive */
    @media (max-width: 600px) {
      .container { padding: 1.25rem 1rem; }
      .recipe-grid { grid-template-columns: 1fr; }
      .article-header h1 { font-size: 1.35rem; }
    }'''

    # -------------------------------------------------------------------
    #  辅助方法
    # -------------------------------------------------------------------

    @staticmethod
    def _is_invalid_combination(symptom: str, audience: str, solution: str) -> bool:
        """过滤不合理的症状-人群-方案组合"""
        invalid_rules = [
            # 痛经不适合男性/老年人/程序员
            ("痛经", "40岁以上男性"),
            ("痛经", "老年人"),
            ("痛经", "程序员"),
            # 产后妈妈不适合与学生/老人相关的部分方案
            # 更年期女性不适合产后相关
            # 脱发不适合老人
        ]
        for s, a in invalid_rules:
            if symptom == s and audience == a:
                return True
        return False

    @staticmethod
    def _nature_to_constitution(nature: str) -> str:
        """根据药性推测适合的体质"""
        mapping = {
            "寒": "热性",
            "微寒": "偏热",
            "凉": "偏热",
            "温": "寒凉",
            "微温": "偏寒凉",
            "热": "寒凉",
            "平": "各种",
        }
        return mapping.get(nature, "各种")

    @staticmethod
    def _opposite_nature(nature: str) -> str:
        """返回相反的药性描述"""
        mapping = {
            "寒": "热",
            "微寒": "热",
            "凉": "温热",
            "温": "热",
            "微温": "偏热",
            "热": "寒凉",
            "平": "特殊（需根据体质判断）",
        }
        return mapping.get(nature, "偏热")


def _today_iso_display() -> str:
    """返回中文格式的今日日期"""
    d = date.today()
    return f"{d.year}年{d.month}月{d.day}日"


# ===========================================================================
#  便捷函数（模块级）
# ===========================================================================

_default_factory: SeoContentFactory | None = None


def get_factory() -> SeoContentFactory:
    """获取默认的 SeoContentFactory 实例（单例模式）"""
    global _default_factory
    if _default_factory is None:
        _default_factory = SeoContentFactory()
    return _default_factory
