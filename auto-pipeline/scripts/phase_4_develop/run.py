"""
阶段4：开发/生成
基于决策阶段的任务队列，生成SEO知识页面和用户教育内容
输出：生成的HTML/MD内容文件 + 开发完成报告

内容新鲜度跳过（2026-09-17 新增）
---------------------------------
此前本阶段遍历所有 task 并**无脑覆盖** content_file。这意味着：
  1. reset_pipeline / start-new 后，人工精修过的内容会被 f-string 模板覆盖；
  2. self_heal 把 test_failed 退回 pending_test 后，phase_4 不重跑（状态不对），
     但如果人工 reset 又跑 phase_3 → phase_4，精修内容照样被覆盖；
  3. 模板内容是占位符（"深入了解{title}的科学原理"），没有 AI 生成，
     覆盖等于把有价值的人工内容换成无价值的占位符。

现在：content_file 已存在且 < 7 天 → 跳过重写，只更新 task 状态为 generated。
这是借鉴 Karpathy autoresearch 的「冻结指标」思想——已有成果是资产，
不应被自动循环无脑覆盖。
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import (
    BASE_DIR,
    complete_phase,
    fail_phase,
    get_state,
    log,
    save_state,
    start_phase,
)
from llm_client import generate as llm_generate, is_available as llm_available, generate_with_metadata, is_generation_enabled

# 内容新鲜度阈值：content_file 修改时间在此天数内 → 跳过重写
CONTENT_FRESH_DAYS = 7

# LLM 生成质量下限：正文 < 此字数视为垃圾，回退模板
LLM_MIN_CHARS = 200

# minimind 35B 已知套话（保留作快速命中）
_LLM_JUNK_PATTERNS = [
    r'(电磁场强度变化时，电磁场会)',
    r'(核心原理是利用电磁场的强度和频率)',
]

# 复读窗口：任意 6+ 字短语在此窗口内重复出现即判定垃圾
_REPEAT_WINDOW = 200
_REPEAT_MIN_LEN = 6


def _has_repetition(text: str) -> bool:
    """检测自我复读：任意 6+ 字短语在 200 字窗口内重复出现。

    minimind 35B 的典型幻觉模式：
    "基因的表达调控、基因的表达调控、基因与环境的相互作用"
    "包括代谢产物的生成、代谢产物的作用等"
    这些不是套话，是模型在卡壳时机械重复。硬编码正则抓不住，
    必须用窗口扫描。
    """
    n = len(text)
    if n < LLM_MIN_CHARS:
        return False
    # 按 6-10 字滑窗扫描，记录每个窗口内出现过的 n-gram
    # 用 set 存 (start_pos, ngram)，O(n^2) 但 n<2000 没问题
    seen: dict[str, int] = {}  # ngram -> first position
    for length in range(_REPEAT_MIN_LEN, 11):
        for i in range(0, n - length + 1):
            ng = text[i:i + length]
            # 跳过纯标点/空白
            if ng.strip() in ('', '，、。；：""''（）【】', '，、', '——', '…'):
                continue
            if ng in seen:
                # 距离过近的重复（<200 字）
                if i - seen[ng] < _REPEAT_WINDOW and i - seen[ng] >= length:
                    return True
            else:
                seen[ng] = i
    return False


def _has_format_violation(text: str) -> bool:
    """检测格式违规：要求纯段落但 LLM 返回编号列表/markdown。

    minimind 经常无视"不要标题、不要列表、不要 markdown"的指令，
    返回 "1. **xxx** 2. **xxx**" 这种格式。
    """
    # 编号列表（1. 2. 3. 或 ① ② ③）
    if re.search(r'(?:^|\n)\s*(?:\d+[.)、]|①|②|③|④|⑤)', text):
        return True
    # markdown 标题
    if re.search(r'(?:^|\n)#{1,6}\s', text):
        return True
    # markdown 粗体滥用（** 连续 3 次以上）
    if text.count('**') >= 6:
        return True
    # markdown 链接
    if re.search(r'\[.+?\]\(.+?\)', text):
        return True
    return False


def _has_medical_hallucination(text: str) -> bool:
    """检测明显的医学事实幻觉。

    minimind 35B 在健康领域会编造具体数字/范围，比如：
    "生物年龄在 1-3 岁之间"——生物年龄是相对指标，不是绝对年龄。
    "n=59,078 降低 64%"——无来源的具体研究数据。
    """
    # 具体样本量 + 百分比（无来源的研究引用）
    if re.search(r'n\s*=\s*\d[\d,]*', text):
        return True
    if re.search(r'(降低|减少|提升|增加)了?\s*\d{1,3}\s*%', text):
        return True
    # 生物年龄/表观年龄被描述为具体岁数（应是相对指标）
    if re.search(r'生物年龄[^\n]{0,15}(\d{1,3}\s*岁|\d{1,3}[\.\d]*\s*岁)', text):
        return True
    # 虚假的"研究表明"无来源引用
    if re.search(r'(研究表明|研究发现|最新研究|多项研究)[^。]{0,30}(降低|减少|提升)\s*\d', text):
        return True
    return False


def _is_llm_junk(text: str) -> bool:
    """检测 LLM 输出是否是垃圾（太短/复读/格式违规/医学幻觉）。

    分层检测，任一命中即判定垃圾回退模板：
    1. 长度不足（<200 字）
    2. 已知套话模式
    3. 自我复读（任意 6+ 字短语在 200 字窗口内重复）
    4. 格式违规（要求段落但返回列表/markdown）
    5. 医学事实幻觉（具体数字/百分比/年龄岁数）
    """
    if not text or len(text) < LLM_MIN_CHARS:
        return True
    for pat in _LLM_JUNK_PATTERNS:
        if re.search(pat, text):
            return True
    if _has_repetition(text):
        return True
    if _has_format_violation(text):
        return True
    if _has_medical_hallucination(text):
        return True
    return False


# FDA Structure/Function 声明转换表（2025-09-09 新规）
# ----------------------------------------------------
# 2025-09-09 起 FDA 关闭 "adequate provision" loophole，疾病治疗声明
# 必须替换为结构/功能声明。此前内容合规检查只做"高风险词阻断"，
# 但 LLM 生成时不知道应该改成什么——现在在 Phase 4 里自动替换。
# 长词优先，避免"降血压"被"降压"先替换后残留"压"字。
# 保守策略：一律替换，宁可在个别中性感句上产生"支持血压维持在正常范围"
# 这类稍显生硬的表达，也不让疾病治疗声明上线。
STRUCTURE_FUNCTION_REPLACEMENTS = [
    # 长词优先（疾病治疗声明）
    ("治疗抑郁症", "可能有助于情绪调节"),
    ("治疗糖尿病", "支持血糖维持在正常范围"),
    ("治疗高血压", "支持心血管健康"),
    ("治疗关节炎", "支持关节活动"),
    ("治疗失眠", "支持放松与休息"),
    ("治疗焦虑", "可能有助于情绪调节"),
    ("治疗甲亢", "支持甲状腺正常功能"),
    ("治疗抑郁", "可能有助于情绪调节"),
    ("治疗心脏病", "支持心血管健康"),
    ("治疗癌症", "可能有助于细胞健康"),
    # 指标调节类
    ("降血压", "支持血压维持在正常范围"),
    ("降胆固醇", "支持胆固醇维持在正常范围"),
    ("降血脂", "支持血脂维持在正常范围"),
    ("降血糖", "支持血糖维持在正常范围"),
    ("降糖", "支持血糖维持在正常范围"),
    ("降脂", "支持血脂维持在正常范围"),
    ("降压", "支持血压维持在正常范围"),
    # 抗炎/免疫类
    ("抗炎", "支持身体自然炎症反应"),
    ("减轻关节炎疼痛", "支持关节活动"),
    ("预防感冒", "支持健康免疫功能"),
    ("增强免疫力", "支持免疫系统正常运作"),
    ("提高免疫力", "支持免疫系统正常运作"),
    # 体重/皮肤类
    ("减肥", "支持体重管理"),
    ("瘦身", "支持体重管理"),
    ("美白", "帮助改善肤色"),
    ("抗衰", "支持皮肤健康"),
    # 排毒/肠道类
    ("排毒", "支持身体自然代谢过程"),
    ("调理肠胃", "支持消化系统健康"),
    ("调节肠胃", "支持消化系统健康"),
    ("清除毒素", "支持身体自然代谢过程"),
    # 抗菌抗病毒类
    ("杀死细菌", "支持免疫系统抵御感染"),
    ("杀死病毒", "支持免疫系统抵御感染"),
    ("抗病毒", "支持免疫系统正常运作"),
    ("抗菌", "支持环境卫生"),
    ("杀菌", "支持环境卫生"),
    ("抗癌", "支持细胞健康"),
    # 通用医疗词（放在最后，避免吃掉上面的长词）
    ("治愈", "可能有助于缓解"),
    ("根治", "可能有助于改善"),
    ("治疗疾病", "可能有助于健康改善"),
    ("治疗", "帮助改善"),
]


def _apply_structure_function_replacements(text: str) -> tuple:
    """应用 FDA Structure/Function 声明转换。

    返回 (converted_text, replacements_applied)
    replacements_applied: [{"from","to","count"}...] 便于审计追溯
    """
    if not text:
        return text, []
    applied = []
    result = text
    for bad, good in STRUCTURE_FUNCTION_REPLACEMENTS:
        count = result.count(bad)
        if count > 0:
            result = result.replace(bad, good)
            applied.append({"from": bad, "to": good, "count": count})
    return result, applied


def _llm_generate_body(title: str, tags: list, topic_type: str = "seo") -> tuple:
    """用 LLM 生成正文段落。返回 (text, metadata)。

    metadata 含：
      - model / provider（记录哪个模型生成的，便于审计追溯）
      - prompt_hash（prompt 的 SHA256 前 12 位，便于重现同一 prompt）
      - latency_ms / generated_at
      - structure_function_replacements（FDA 声明转换记录）
    GitHub 用户反馈明确指出：AI 生成内容 commit 缺元数据无法追溯。
    """
    import hashlib

    # 场景开关：默认关闭，避免白烧推理时间。
    # 实测 minimind 35B 在 10 道健康知识题上 10/10 被 _is_llm_junk 拦截
    # （复读+格式违规），LLM 调用等价于 100% 回退模板。开启需 SenseNova
    # 修好或换更强模型（设 LLM_GENERATE_ENABLED=true）。
    if not is_generation_enabled():
        return None, None

    if not llm_available():
        return None, None

    tag_str = "、".join(tags[:5]) if tags else "健康管理"
    if topic_type == "seo":
        prompt = (
            f"用 300-400 字介绍「{title}」的科学原理、作用机制和适用场景。\n"
            f"标签：{tag_str}\n"
            f"要求：\n"
            f"- 用通俗中文，避免堆砌医疗术语\n"
            f"- 不要编造具体研究数据（不要写 n=XXX 或 XX% 降幅）\n"
            f"- 不要写「值得注意的是」「综上所述」等 AI 套话\n"
            f"- 如果不确定具体机制，用「可能」「或」等温和表述\n"
            f"- 使用结构/功能声明（如「支持血压维持在正常范围」）而非疾病治疗声明\n"
            f"- 直接输出正文段落，不要标题、不要列表、不要 markdown"
        )
    else:  # user_education
        prompt = (
            f"用 200-300 字介绍「{title}」的核心概念和实际操作方法。\n"
            f"标签：{tag_str}\n"
            f"要求：\n"
            f"- 用通俗中文，面向普通用户\n"
            f"- 不要编造具体研究数据\n"
            f"- 不要写 AI 套话\n"
            f"- 使用结构/功能声明而非疾病治疗声明\n"
            f"- 直接输出正文段落"
        )

    # 记录 prompt hash 便于审计追溯（GitHub 反馈：AI 生成 commit 缺元数据）
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]

    result, llm_meta = generate_with_metadata(
        prompt=prompt,
        system="你是健康科普作者。用中文回答，通俗易懂，不编造数据，不写 AI 套话，使用结构/功能声明而非疾病治疗声明。",
        max_tokens=800,
        temperature=0.4,
        timeout=90,
    )

    if not result or _is_llm_junk(result):
        log(f"LLM 生成质量不足或不可用，回退模板", level="WARN")
        return None, None

    # 应用 FDA Structure/Function 声明转换
    result, sf_replacements = _apply_structure_function_replacements(result)

    # 合并元数据
    metadata = {
        **(llm_meta or {}),
        "prompt_hash": prompt_hash,
        "raw_chars": len(result),
        "structure_function_replacements": sf_replacements,
    }
    return result, metadata


def generate_seo_article(task, source_item):
    """生成SEO知识文章。尝试 LLM 生成正文，失败回退模板。"""
    title = task.get("title", "健康知识")
    tags = task.get("tags", [])

    # 尝试 LLM 生成正文（替代模板里的"科学原理"和"临床证据"段落）
    llm_body, llm_metadata = _llm_generate_body(title, tags, topic_type="seo")

    slug = title_to_slug(title)

    # LLM 正文段落（替换模板里的固定段落）
    if llm_body:
        mechanism_html = f'<h2>科学原理与机制</h2>\n        <p>{llm_body}</p>'
        evidence_html = ('<h2>临床研究证据</h2>\n'
                         '        <p>目前关于{title}的研究仍在进行中。具体效果因人而异，'
                         '与基础健康状况、干预强度、坚持时长等因素密切相关。'
                         '任何关于效果的判断都应基于个体化评估，而非通用结论。</p>')
        llm_used = True
    else:
        mechanism_html = ('<h2>科学原理与机制</h2>\n'
                         '        <p>从分子生物学角度看，{title}的作用机制涉及多个生理通路的协同作用。'
                         '研究表明，主要通过以下途径发挥作用：</p>\n'
                         '        <ul>\n'
                         '            <li>调节昼夜节律钟基因的表达</li>\n'
                         '            <li>改善线粒体功能和能量代谢</li>\n'
                         '            <li>优化肠道菌群组成</li>\n'
                         '            <li>调节AMPK/mTOR信号通路</li>\n'
                         '        </ul>')
        evidence_html = ('<h2>临床研究证据</h2>\n'
                         '        <p>关于{title}的健康益处，目前已有多种观察性研究和生活方式干预研究'
                         '探讨其潜在影响。具体效果因人而异，与基础健康状况、干预强度、坚持时长'
                         '等因素密切相关。任何关于效果的判断都应基于个体化评估，而非通用结论。</p>')
        llm_used = False

    # YMYL 增强 Schema：MedicalWebPage（Google AI Overviews 抓取门槛）+ FAQPage
    # 当前模板有"常见问题"段落，需要单独用 FAQPage schema 标记让 AI Overviews 抓取。
    # FAQPage schema 必须与可见内容一致，否则 Google 会惩罚。
    faq_schema = '''\n    <script type="application/ld+json">\n    {\n      "@context": "https://schema.org",\n      "@type": "FAQPage",\n      "mainEntity": [\n        {\n          "@type": "Question",\n          "name": "多久能看到效果？",\n          "acceptedAnswer": {\n            "@type": "Answer",\n            "text": "因人而异，通常2-4周开始感受到变化，3个月可观察到显著的指标改善。"\n          }\n        },\n        {\n          "@type": "Question",\n          "name": "需要坚持多长时间？",\n          "acceptedAnswer": {\n            "@type": "Answer",\n            "text": "健康管理是长期过程。建议将健康生活方式融入日常，而非短期突击。"\n          }\n        }\n      ]\n    }\n    </script>'''

    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 深度解析与实践指南 | HealthLens</title>
    <meta name="description" content="深入了解{title}的科学原理、实践方法和健康益处。基于最新研究，提供可操作的健康改善建议。">
    <meta name="keywords" content="{', '.join(tags)}, 健康管理, 生活方式干预">
    <link rel="canonical" href="https://healthlens.cc/knowledge/{slug}">
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "MedicalWebPage",
      "headline": "{title}",
      "description": "深入了解{title}的科学原理与实践指南",
      "author": {{"@type": "Organization", "name": "HealthLens"}},
      "publisher": {{"@type": "Organization", "name": "HealthLens"}},
      "datePublished": "{datetime.now().strftime('%Y-%m-%d')}",
      "dateModified": "{datetime.now().strftime('%Y-%m-%d')}",
      "about": "{title}",
      "medicalSpecialty": "General Practice",
      "audience": {{"@type": "PeopleAudience", "name": "Health-concerned adults"}}
    }}
    </script>
    {faq_schema}
</head>
<body>
    <article>
        <h1>{title}</h1>
        <p class="lead">本文深入探讨{title}的科学原理、临床依据和实践方法，帮助您理解如何通过非药物干预改善健康。</p>
        
        <h2>什么是{title}</h2>
        <p>{title}是近年来健康领域的重要研究方向。越来越多的科学证据表明，通过生活方式的系统性调整，可以在多个层面改善人体健康状态。</p>
        
        {mechanism_html}
        
        {evidence_html}
        
        <h2>实践方法与建议</h2>
        <p>以下是基于科学证据的实践建议：</p>
        <ol>
            <li><strong>循序渐进</strong>：从小的改变开始，逐步建立健康习惯</li>
            <li><strong>综合干预</strong>：结合睡眠、营养、运动等多维度调整</li>
            <li><strong>量化追踪</strong>：使用可穿戴设备和健康App追踪进展</li>
            <li><strong>个性化调整</strong>：根据个人基因和体质特征定制方案</li>
        </ol>
        
        <h2>与其他干预方式的协同</h2>
        <p>{title}与其他健康干预方式存在显著的协同效应。当与合理的饮食、规律的运动和充足的睡眠相结合时，健康收益呈指数级增长，实现1+1+1&gt;3的效果。</p>
        
        <h2>注意事项与适用人群</h2>
        <p>虽然{title}对大多数人有益，但以下人群应在专业指导下进行：</p>
        <ul>
            <li>患有严重慢性疾病者</li>
            <li>孕妇和哺乳期妇女</li>
            <li>正在服用药物的患者</li>
            <li>术后康复期患者</li>
        </ul>
        
        <h2>常见问题</h2>
        <h3>Q: 多久能看到效果？</h3>
        <p>A: 因人而异，通常2-4周开始感受到变化，3个月可观察到显著的指标改善。</p>
        
        <h3>Q: 需要坚持多长时间？</h3>
        <p>A: 健康管理是长期过程。建议将健康生活方式融入日常，而非短期突击。</p>
        
        <h2>总结</h2>
        <p>{title}是经过科学验证的健康改善途径。通过系统性、个性化的干预，结合量化追踪和持续优化，每个人都能找到最适合自己的健康方案。</p>
        
        <div class="disclaimer">
            <p><strong>免责声明</strong>：本文仅供健康知识普及，不构成医疗建议。如有健康问题，请咨询专业医疗人员。</p>
        </div>
    </article>
</body>
</html>"""

    return {
        "task_id": task["task_id"],
        "type": "seo_knowledge_page",
        "title": title,
        "slug": slug,
        "word_count": len(content),
        "content_file": f"content/generated/{slug}.html",
        "tags": tags,
        "status": "generated",
        "llm_used": llm_used,
        "llm_metadata": llm_metadata,
    }, content


def title_to_slug(title):
    """标题转URL slug"""
    import re
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug).strip('-_')
    if not slug:
        slug = "article"
    return slug


def generate_user_education(task, source_item):
    """生成用户教育内容。尝试 LLM 生成正文，失败回退模板。"""
    title = task.get("title", "健康指南")
    tags = task.get("tags", [])
    slug = title_to_slug(title) + "-guide"

    # 尝试 LLM 生成"快速了解"段落
    llm_body, llm_metadata = _llm_generate_body(title, tags, topic_type="edu")

    if llm_body:
        quick_understand = f'<h2>快速了解</h2>\n    <p>{llm_body}</p>'
        llm_used = True
    else:
        quick_understand = (f'<h2>快速了解</h2>\n'
                          f'    <p>{title}听起来复杂，其实核心原则很简单。'
                          f'掌握以下3个关键点，就能开始实践：</p>')
        llm_used = False

    content = f"""<article class="edu-article">
    <h1>{title}：实用指南</h1>
    <div class="meta">发布于 {datetime.now().strftime('%Y年%m月%d日')} | 阅读时间：约 5 分钟</div>
    
    {quick_understand}
    
    <div class="key-points">
        <div class="point">
            <h3>① 理解原理</h3>
            <p>知道为什么这样做比怎么做更重要，能帮助你坚持下去。</p>
        </div>
        <div class="point">
            <h3>② 从小开始</h3>
            <p>不要试图一次改变所有事情，选择一个最小可行的改变开始。</p>
        </div>
        <div class="point">
            <h3>③ 坚持记录</h3>
            <p>量化追踪是持续优化的基础，数据会告诉你什么有效。</p>
        </div>
    </div>
    
    <h2>具体操作步骤</h2>
    <ol>
        <li>评估当前状态，设定基线</li>
        <li>选择1-2个最容易实现的改变</li>
        <li>执行2周，记录感受和数据</li>
        <li>评估效果，调整方案</li>
        <li>逐步增加新的健康习惯</li>
    </ol>
    
    <h2>常见误区</h2>
    <ul>
        <li><strong>误区1</strong>：越多越好 —— 实际上适度和坚持更重要</li>
        <li><strong>误区2</strong>：立竿见影 —— 健康改善需要时间积累</li>
        <li><strong>误区3</strong>：千人一面 —— 每个人的最优方案都不同</li>
    </ul>
    
    <p class="cta">想知道你的个性化方案？使用 HealthLens 的 AI 健康分析工具，获取专属建议。</p>
</article>"""

    return {
        "task_id": task["task_id"],
        "type": "user_education",
        "title": title,
        "slug": slug,
        "word_count": len(content),
        "content_file": f"content/generated/{slug}.html",
        "tags": tags,
        "status": "generated",
        "llm_used": llm_used,
        "llm_metadata": llm_metadata,
    }, content


def run():
    phase = "develop"
    try:
        start_phase(phase)

        # 校验配置可读（本阶段不消费具体配置项，保留校验以便配置写错时尽早失败）
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            json.load(f)

        # 获取任务队列
        state = get_state()
        tasks = state.get("development_tasks", [])

        if not tasks:
            log("开发队列为空，跳过内容生成阶段")
            complete_phase(phase, output_file=None, items_processed=0)
            return True

        # 获取批准项的详细信息（用于内容生成）
        approved_items = {item["id"]: item for item in state.get("approved_queue", [])}

        # 生成内容
        generated_items = []
        content_dir = BASE_DIR / "content" / "generated"
        content_dir.mkdir(parents=True, exist_ok=True)

        for task in tasks:
            source_item = approved_items.get(task.get("based_on_item"), {})

            # 冻结检查（autoresearch 模式）：task.frozen=True → 永不重写。
            # 用途：人工精修过的高价值内容，标记冻结后即使超过新鲜度阈值也不重写。
            if task.get("frozen"):
                if content_path.exists():
                    existing_text = content_path.read_text(encoding="utf-8", errors="ignore")
                    meta = {
                        "task_id": task["task_id"],
                        "type": task["type"],
                        "title": task.get("title", ""),
                        "slug": slug,
                        "word_count": len(existing_text),
                        "content_file": f"content/generated/{slug}.html",
                        "tags": task.get("tags", []),
                        "status": "generated",
                        "skipped": True,
                        "skip_reason": "内容已冻结（frozen=True），人工精修资产不重写",
                    }
                    generated_items.append(meta)
                    for t in state["development_tasks"]:
                        if t["task_id"] == task["task_id"]:
                            t["status"] = "generated"
                            t["content_file"] = meta["content_file"]
                            break
                    log(f"[冻结] {task['task_id']} 已冻结，保持原文件")
                    continue

            # 内容新鲜度检查：已存在且 < CONTENT_FRESH_DAYS 天 → 跳过重写。
            # 防止人工精修内容被 f-string 模板覆盖。
            # 这是借鉴 Karpathy autoresearch 的「冻结成果」思想：
            # 已有的人工精修内容是资产，不应被自动循环无脑覆盖。
            if task["type"] == "seo_knowledge_page":
                slug = title_to_slug(task.get("title", ""))
            elif task["type"] == "user_education":
                slug = title_to_slug(task.get("title", "")) + "-guide"
            else:
                slug = ""
            content_path = BASE_DIR / "content" / "generated" / f"{slug}.html"

            if content_path.exists():
                age_days = (time.time() - content_path.stat().st_mtime) / 86400
                if age_days < CONTENT_FRESH_DAYS:
                    existing_text = content_path.read_text(encoding="utf-8", errors="ignore")
                    meta = {
                        "task_id": task["task_id"],
                        "type": task["type"],
                        "title": task.get("title", ""),
                        "slug": slug,
                        "word_count": len(existing_text),
                        "content_file": f"content/generated/{slug}.html",
                        "tags": task.get("tags", []),
                        "status": "generated",
                        "skipped": True,
                        "skip_reason": f"内容 {age_days:.1f} 天前生成（阈值 {CONTENT_FRESH_DAYS} 天），保持原文件不重写",
                    }
                    generated_items.append(meta)
                    for t in state["development_tasks"]:
                        if t["task_id"] == task["task_id"]:
                            t["status"] = "generated"
                            t["content_file"] = meta["content_file"]
                            t["skip_info"] = meta["skip_reason"]
                            break
                    log(f"[跳过] {task['task_id']} 内容 {age_days:.1f} 天前生成，保持原文件")
                    continue

            if task["type"] == "seo_knowledge_page":
                meta, content = generate_seo_article(task, source_item)
            elif task["type"] == "user_education":
                meta, content = generate_user_education(task, source_item)
            else:
                log(f"未知任务类型: {task['type']}", level="WARN")
                continue

            # 保存内容文件
            content_path = BASE_DIR / meta["content_file"]
            content_path.parent.mkdir(parents=True, exist_ok=True)
            with open(content_path, "w", encoding="utf-8") as f:
                f.write(content)

            meta["status"] = "generated"
            generated_items.append(meta)

            # 更新任务状态
            for t in state["development_tasks"]:
                if t["task_id"] == task["task_id"]:
                    t["status"] = "generated"
                    t["content_file"] = meta["content_file"]
                    break

        save_state(state)

        # 生成开发完成报告
        today = datetime.now().strftime("%Y-%m-%d")
        report = {
            "report_id": f"develop_{today}",
            "generated_at": datetime.now().isoformat(),
            "total_tasks": len(tasks),
            "completed_tasks": len(generated_items),
            "failed_tasks": len(tasks) - len(generated_items),
            "items": generated_items,
            "summary": {
                "seo_articles": len([i for i in generated_items if i["type"] == "seo_knowledge_page"]),
                "education_articles": len([i for i in generated_items if i["type"] == "user_education"]),
                "total_word_count": sum(i["word_count"] for i in generated_items)
            }
        }

        output_file = f"reports/analysis/{today}_development_report.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(
            phase,
            output_file=output_file,
            items_processed=len(generated_items),
            seo_articles=report["summary"]["seo_articles"],
            education_articles=report["summary"]["education_articles"]
        )
        log(f"开发完成: {len(generated_items)} 篇内容已生成")
        return True

    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
