"""
阶段5：质量测试
对生成的内容进行质量检查：医疗用语扫描、Schema标记验证、链接有效性、字数检查
输出：test_report.json
"""
import sys
import json
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import start_phase, complete_phase, fail_phase, get_state, save_state, BASE_DIR, log


# 医疗风险关键词，分两级：
#   HIGH   — 出现即 fail，内容不得上线。这些是《广告法》《互联网诊疗
#            管理办法》《医疗广告管理办法》明确禁止的绝对化用语或越界
#            表述，健康信息平台一旦上线就可能构成违法医疗广告。
#   MEDIUM — 出现标 warning，提示人工复核。
# 此前两级混用同一 warning 等级，导致「治愈 / 根治 / 包治 / 100%」这类
# 硬违规词也能通过测试进 deploy（phase_6 认领 test_warning），
# 正是 2026-09 两篇内容被迫人工重写的根因——检测到了但不阻断。
MEDICAL_HIGH_RISK_TERMS = [
    ("治愈",      "严禁使用'治愈'，建议用'改善'或'帮助'"),
    ("根治",      "严禁使用'根治'，建议用'缓解'或'调节'"),
    ("特效",      "严禁使用'特效'，建议用'可能有助于'"),
    ("包治",      "严禁使用'包治'类绝对化用语"),
    ("药到病除",  "严禁使用夸大效果的用语"),
    ("100%",      "严禁使用百分比绝对化表述"),
    ("一定有效",  "严禁绝对化承诺"),
    ("诊断",      "非医疗平台不应提供诊断服务"),
    ("处方",      "非医疗平台不应涉及处方"),
    ("治疗疾病",  "严禁使用'治疗疾病'，建议用'健康调理'或'生活方式干预'替代"),
    ("根治疾病",  "严禁使用'根治疾病'类绝对化表述"),
    ("完全治愈",  "严禁使用'完全治愈'"),
    ("包治百病",  "严禁使用'包治百病'类夸大表述"),
    ("无副作用",  "严禁使用'无副作用'类绝对化承诺"),
    ("零风险",    "严禁使用'零风险'类绝对化承诺"),
    ("永久有效",  "严禁使用'永久有效'类绝对化承诺"),
    ("一次见效",  "严禁使用'一次见效'类夸大表述"),
    ("立竿见影",  "严禁使用'立竿见影'类夸大表述"),
    # ↓ 2026-09-19 增补：抗衰老夸大词。
    # 缺口来源：吕垣澄 OSK 部分重编程、表观遗传时钟等前沿条目，
    # 最容易被写成"逆转衰老/返老还童"标题，而旧词表对此完全无感——
    # 检测到了才拦得住，检测不到等于门禁不存在。
    ("逆转衰老",  "严禁使用'逆转衰老'类绝对化表述，建议改为'支持健康衰老'"),
    ("返老还童",  "严禁使用'返老还童'类夸大表述"),
    ("逆龄",      "严禁使用'逆龄'类夸大表述"),
    ("永葆青春",  "严禁使用'永葆青春'类夸大表述"),
    ("冻龄",      "严禁使用'冻龄'类夸大表述"),
    ("换血回春",  "严禁使用'换血回春'类未经验证的夸大表述"),
    # ↓ 2026-09-19 增补：抗癌治疗功效声称。
    # 缺口来源：青蛙肠道菌 Ewingella americana 等肿瘤免疫前沿条目。
    # 《广告法》第十七条：非医疗/药品/医疗器械广告不得涉及疾病治疗功能。
    ("杀死癌细胞", "严禁使用'杀死癌细胞'类疾病治疗功效声称"),
    ("消灭肿瘤",   "严禁使用'消灭肿瘤'类疾病治疗功效声称"),
    ("肿瘤消失",   "严禁使用'肿瘤消失'类疗效声称"),
    ("攻克癌症",   "严禁使用'攻克癌症'类绝对化表述"),
    ("抗癌神药",   "严禁使用'抗癌神药'类夸大表述"),
]

# 中风险词：出现标 warning，提示人工复核，但不阻断上线。
MEDICAL_MEDIUM_RISK_TERMS = [
    ("疗效",     "建议用'效果'或'改善'替代'疗效'"),
    ("临床证明", "建议核实并标注具体研究来源"),
    ("专家推荐", "建议核实并标注具体专家来源"),
    # ↓ 2026-09-19 增补：单字面本身可能出现在合法的"机制研究"语境里
    # （如"剪接失调与抗癌机制的基础研究"），故不硬 fail，只提示人工复核。
    ("抗癌",     "非医疗平台不应作疾病治疗功效声称，建议改为'肿瘤相关基础研究'并标注实验阶段"),
    ("防癌",     "非医疗平台不应作疾病预防声称，建议改为'与风险因素相关的研究'"),
    ("抗衰老",   "建议改为'支持健康衰老'，且不得作任何干预承诺"),
]

# Schema.org 必需字段
REQUIRED_SCHEMA_FIELDS = [
    "@context",
    "@type",
    "headline",
    "description",
    "author",
    "datePublished",
]

# 语境判定（2026-09-19 新增）
# --------------------------
# 起因：把新词补进门禁后做全量回归，发现 57 个内容文件里有 32 个命中既有
# HIGH 词（诊断 / 处方 / 100% / 立竿见影）。逐条查上下文，**32 处全部为
# 误伤**，且第一类是最坏的一种——门禁在罚平台自己的合规免责声明：
#   ① 否定语境：「不构成医学诊断」「不能下 SNP 级处方」「而非处方」
#      「效果不会立竿见影」「尚未作为常规诊断工具」
#   ② CSS 数值：`width:100%` / `height:100%` 落在 <style> 块内被当正文命中
#   ③ 反例清单：「误区2：立竿见影」「❌ "基因检测=定制线粒体处方"」——
#      编辑明确标注为"错误说法"的条目
#   ④ 数据表数值：「活性 100%」「CC（野生型）100%」——中性测量值
#   ⑤ 引文语境：《饮膳正要》金髓煎「……返老还童」属古籍引用
#   ⑥ FAQ 问句：「外泌体能诊断疾病吗？」是提问，不是平台声称
# 误伤后果：这些页面一旦重新进入管线即被判 needs_manual_review，内容生产
# 静默停摆，且告警指向错误方向（让人去改免责声明）。故做五处机械修正。
#
# 分级策略（关键）：不给所有线索用同一个窗口。
#   显式编辑标记（❌ / 误区 / 禁忌…）语义无歧义——出现即断言"其后是反例"，
#   可用较宽窗口（EXPLICIT_WINDOW=24）。
#   弱否定词（不 / 非 / 尚未…）本身可能出现在无关句子里，窗口必须收紧
#   （NEG_WINDOW=12），否则会吞掉真实功效声称——例如放宽后会误放过
#   "我们不做过度承诺。产品可根治失眠。"
# 只有"引号外 + 无否定/反例线索 + 非问句"的出现才按 HIGH 阻断，
# 即平台自己做的绝对化功效声称一个都不会漏。
_STRIP_BLOCKS = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)

_QUOTE_PAIRS = [("「", "」"), ("『", "』"), ("“", "”"), ("《", "》")]
# 刻意不收直引号："..."。HTML 属性（class="x"）也用直引号，若纳入判定，
# 任何位于属性之后的词都会被当成"处于引号内"而误降级，等于全局削弱门禁。

# 显式编辑标记：语义无歧义，用宽窗口
EXPLICIT_MARKERS = ("❌", "✗", "误区", "禁忌", "不推荐", "错误说法", "常见误解")
EXPLICIT_WINDOW = 24
# 弱否定线索：用窄窗口，避免吞掉真实声称
NEGATION_CUES = (
    "不", "非", "勿", "禁止", "严禁", "避免", "而非", "并非",
    "不能", "不会", "不得", "不应", "无法", "尚未", "还没",
)
NEG_WINDOW = 12

# 需要"功效上下文"才计为 HIGH 的词：单字面本身可能是中性测量值。
# 「100%」在中性语境里是数据（活性 100%），在功效语境里才是绝对化承诺
# （"有效率达 100%"）。故只在 ±EFFICACY_WINDOW 内出现功效词时才计 HIGH；
# 否则整条跳过（连 MEDIUM 都不进，避免把数据表刷成噪声）。
CONTEXT_REQUIRED_TERMS = {"100%"}
EFFICACY_WORDS = (
    "有效", "疗效", "治愈", "改善", "成功率", "见效", "康复",
    "逆转", "保证", "搞定", "解决", "根治", "人人", "彻底",
)
EFFICACY_WINDOW = 20


# 分句边界：否定线索只在"同一句内"生效，不允许跨句赦免。
# 实测反例（2026-09-19）：「我们不做过度承诺。产品可根治失眠。」——按 12 字
# 窗口，前一句的「不做」会把后一句的「根治」也赦免掉。窗口再窄也只是缓解，
# 真正的修法是遇到句号/分号/逗号/换行就截断，让线索回到它所在的分句。
# 刻意**不含** `>`：实际 HTML 形如 `<li><strong>误区2</strong>：立竿见影`，
# 若把 `>` 当边界，「误区」标记会被 <strong> 截掉，反例清单又变回误伤。
# 正确做法是先把标签整体剥离（见 _TAG_RE），而不是拿标签当分句符。
_SENT_BOUNDARY = "。！？；!?;\n，,"
_TAG_RE = re.compile(r"<[^>]+>")


def _after_last_boundary(s: str) -> str:
    """截取最后一个分句边界之后的部分。"""
    last = -1
    for ch in _SENT_BOUNDARY:
        p = s.rfind(ch)
        if p > last:
            last = p
    return s[last + 1:] if last >= 0 else s


def _in_quotation(content: str, idx: int) -> bool:
    """判断 idx 位置是否落在成对的引号 / 书名号对内。"""
    for lq, rq in _QUOTE_PAIRS:
        open_at = content.rfind(lq, 0, idx)
        if open_at == -1:
            continue
        close_at = content.find(rq, open_at + 1)
        if close_at == -1:
            continue
        if open_at < idx < close_at:
            return True
    return False


def _in_negation(content: str, idx: int) -> bool:
    """判断 idx 前是否存在否定线索（均限同一句内；显式标记允许更宽）。"""
    wide = _after_last_boundary(content[max(0, idx - EXPLICIT_WINDOW):idx])
    if any(m in wide for m in EXPLICIT_MARKERS):
        return True
    narrow = _after_last_boundary(content[max(0, idx - NEG_WINDOW):idx])
    return any(cue in narrow for cue in NEGATION_CUES)


def _in_question(content: str, idx: int, term_len: int) -> bool:
    """判断命中词是否紧跟问句语气词——「…能诊断疾病吗？」是提问而非声称。"""
    tail = content[idx + term_len: idx + term_len + 4]
    return ("吗" in tail) or ("？" in tail) or ("?" in tail)


def _contextual(content: str, idx: int, term: str) -> bool:
    """命中位置是否处于可解释语境（引文 / 否定 / 反例 / 问句）。"""
    return (
        _in_quotation(content, idx)
        or _in_negation(content, idx)
        or _in_question(content, idx, len(term))
    )


def _has_efficacy_context(content: str, idx: int) -> bool:
    """命中位置 ±EFFICACY_WINDOW 内是否存在功效词（用于 CONTEXT_REQUIRED_TERMS）。"""
    left = content[max(0, idx - EFFICACY_WINDOW):idx]
    right = content[idx: idx + EFFICACY_WINDOW]
    return any(w in left or w in right for w in EFFICACY_WORDS)


def check_medical_terms(content):
    """检查医疗风险用语，按 HIGH / MEDIUM 分级返回。

    返回 dict:
      {
        "high":  [{"term","count","suggestion"}...],      # 高风险，出现即 fail
        "medium":[{"term","count","suggestion",...}...],  # 中风险，标 warning
        "has_high": bool,
        "scan_scope": str,   # 扫描口径说明（供 reviewer 判读）
      }
    降级规则：命中位置全部处于引文 / 否定 / 反例 / 问句语境 → 只进 medium。
    只要有一处落在"引号外且无任何语境线索"，仍按 HIGH 阻断。
    """
    scan_text = _TAG_RE.sub(" ", _STRIP_BLOCKS.sub(" ", content))
    high, medium = [], []
    for term, suggestion in MEDICAL_HIGH_RISK_TERMS:
        positions = []
        start = 0
        while True:
            i = scan_text.find(term, start)
            if i == -1:
                break
            positions.append(i)
            start = i + len(term)
        if not positions:
            continue
        if term in CONTEXT_REQUIRED_TERMS:
            # 无功效语境的出现视为中性测量值，整条跳过
            positions = [i for i in positions if _has_efficacy_context(scan_text, i)]
            if not positions:
                continue
        outside = [i for i in positions if not _contextual(scan_text, i, term)]
        if outside:
            high.append({
                "term": term,
                "count": len(outside),
                "suggestion": suggestion,
                "severity": "high",
            })
        else:
            medium.append({
                "term": term,
                "count": len(positions),
                "suggestion": suggestion + "（命中位置均在引文/否定/反例/问句语境内，降级为人工复核）",
                "severity": "medium",
                "demoted_from": "high",
            })
    for term, suggestion in MEDICAL_MEDIUM_RISK_TERMS:
        n = scan_text.count(term)
        if n:
            medium.append({
                "term": term,
                "count": n,
                "suggestion": suggestion,
                "severity": "medium",
            })
    return {
        "high": high,
        "medium": medium,
        "has_high": len(high) > 0,
        "scan_scope": (
            "已剥离 <style>/<script>；引文/否定/反例/问句语境降级 MEDIUM；"
            "100% 仅在功效语境计入"
        ),
    }


def check_schema_markup(content):
    """检查 Schema.org 结构化数据"""
    issues = []
    
    # 检查是否有 JSON-LD
    if "application/ld+json" not in content:
        issues.append({
            "field": "json_ld",
            "status": "missing",
            "message": "缺少 Schema.org JSON-LD 标记"
        })
        return issues
    
    # 提取 JSON-LD 内容
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.DOTALL)
    if not match:
        issues.append({"field": "json_ld", "status": "invalid", "message": "JSON-LD 格式错误"})
        return issues
    
    try:
        data = json.loads(match.group(1).strip())
        for field in REQUIRED_SCHEMA_FIELDS:
            if field not in data:
                issues.append({
                    "field": field,
                    "status": "missing",
                    "message": f"缺少必需字段: {field}"
                })
    except json.JSONDecodeError as e:
        issues.append({"field": "json_ld", "status": "invalid", "message": f"JSON解析失败: {e}"})
    
    return issues


def check_links(content):
    """检查链接有效性（基本检查）"""
    issues = []
    # 提取所有链接
    links = re.findall(r'href=["\'](.*?)["\']', content)
    
    broken_patterns = ["#", "javascript:", "mailto:"]
    valid_links = [l for l in links if not any(l.startswith(p) for p in broken_patterns)]
    
    # 检查空链接
    empty_links = [l for l in links if l in ["", "#"]]
    if empty_links:
        issues.append({
            "type": "empty_links",
            "count": len(empty_links),
            "message": f"发现 {len(empty_links)} 个空链接"
        })
    
    return issues, len(valid_links)


def check_word_count(content, min_words=800):
    """检查字数"""
    # 简单的中文字数统计
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    english_words = len(re.findall(r'[a-zA-Z]+', content))
    total = chinese_chars + english_words
    
    if total < min_words:
        return False, total, f"字数不足: {total}/{min_words}"
    return True, total, "OK"


def check_seo_basics(content, title=""):
    """基础SEO检查"""
    issues = []
    
    # 检查 title
    if not re.search(r'<title>.+</title>', content):
        issues.append({"item": "title_tag", "status": "fail", "message": "缺少title标签"})
    
    # 检查 meta description
    if 'name="description"' not in content and "name='description'" not in content:
        issues.append({"item": "meta_description", "status": "fail", "message": "缺少meta description"})
    
    # 检查 H1
    h1_count = len(re.findall(r'<h1[ >]', content))
    if h1_count == 0:
        issues.append({"item": "h1_tag", "status": "fail", "message": "缺少H1标签"})
    elif h1_count > 1:
        issues.append({"item": "h1_tag", "status": "warning", "message": f"多个H1标签: {h1_count}个"})
    
    # 检查图片 alt
    images = re.findall(r'<img[^>]*>', content)
    no_alt = [img for img in images if 'alt=' not in img and "alt=" not in img]
    if no_alt:
        issues.append({"item": "image_alt", "status": "warning", "message": f"{len(no_alt)} 张图片缺少alt属性"})

    return issues


# ---------- 内容真实性审计（2026-09-17 新增）----------
# 实证：Phase 4 模板里硬编码 "n=59,078 全因死亡风险降低64%" 虚假引用，
# 5 篇 SEO 内容都含同一句编造数据。这种"看起来像研究引用、实际是模板占位"
# 的内容会直接欺骗读者并伤害品牌可信度。以下检查不阻断部署，只标 warning，
# 目的是让人类 reviewer 知道哪篇需要人工精修。


def check_fake_citations(content):
    """检测模板里硬编码的虚假研究引用。

    模式：具体样本量 n= + 具体百分比降幅 + 年份。这是典型的模板编造数据，
    因为真实研究引用的样本量/百分比不会在 5 篇文章里完全一致。
    """
    issues = []
    # n=59,078 / n=12,345 这类具体样本量
    for m in re.finditer(r'n=\d{2,3},\d{3}', content):
        issues.append({"type": "fake_sample_size", "match": m.group(0)})
    # "降低XX%" 与具体年份绑定
    for m in re.finditer(r'(降低|减少|提升)了?\s*\d{1,3}%', content):
        ctx = content[max(0, m.start() - 30):m.end() + 10]
        if re.search(r'\d{4}年', ctx):
            issues.append({"type": "fake_percentage_with_year", "match": m.group(0),
                           "context": ctx.strip()[:60]})
    # "大型队列研究" / "随机对照试验" 但没有具体来源（DOI/JAMA 等）
    for term in ["大型队列研究", "随机对照试验", "Meta 分析", "荟萃分析"]:
        if term in content and "doi" not in content.lower() and "jama" not in content.lower():
            issues.append({"type": "study_claim_without_source", "term": term})
    return issues


def check_template_placeholders(content):
    """检测 f-string 未替换的占位符。

    模板里如果还有 {xxx} 形式的未替换占位符（除 JSON-LD 里的 { "xxx" } 外），
    说明生成逻辑漏了一个变量。
    """
    issues = []
    # 跳过 JSON-LD 区块（那里的 {} 是 JSON 语法）
    text = re.sub(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>', '', content, flags=re.DOTALL)
    # 找 {xxx} 形式的未替换占位符
    for m in re.finditer(r'\{([a-zA-Z_][a-zA-Z0-9_]{2,30})\}', text):
        issues.append({"type": "unreplaced_placeholder", "match": m.group(0)})
    return issues


# ---------- FDA Fair Balance 收益/风险平衡检查（2026-09-18 新增）----------
# 依据：FDA 2025-09-09 关闭 "adequate provision" loophole，收益陈述
# 必须与风险提示同页呈现（equally prominent）。市场数据：88% 头部药品
# 广告不符合 fair balance 要求。此前 Phase 5 只做高风险词阻断，
# 但"讲了一堆好处没讲风险"这种隐性违规没检测到。
# 本检查不阻断部署，只标 warning——让 reviewer 知道哪篇需要补风险提示。

# 收益词（benefit claims）：堆砌会导致收益陈述过重
BENEFIT_TERMS = [
    "改善", "提升", "增强", "帮助", "优化", "促进", "支持", "有效",
    "明显", "显著", "理想", "完美", "强大", "卓越", "突破", "奇迹",
    "神奇", "快速", "轻松", "简单", "便捷", "全面", "系统", "权威",
    "专业", "领先", "先进", "创新", "顶级", "高端", "极致", "终极",
    "最好", "最佳", "最优", "首选", "第一",
]

# 风险/限制词（risk disclosures）：应伴随收益陈述同页出现
RISK_TERMS = [
    "不适", "副作用", "限制", "注意", "咨询医生", "咨询专业",
    "可能", "风险", "警示", "禁忌", "不良反应", "警告", "谨慎",
    "慎重", "评估", "个体差异", "因人而异", "专业指导", "医疗人员",
    "健康风险", "健康隐患", "不适反应", "不适感", "过敏反应",
    "敏感", "不耐受", "慎用", "禁忌人群", "不适用",
]


def check_fair_balance(content):
    """检查收益陈述与风险提示的平衡（FDA Fair Balance）。

    判定规则：
    - 收益词/风险词比 > 3:1 → warning（收益陈述过重）
    - 字数 > 500 且 风险词 = 0 → warning（完全没风险提示）
    - 字数 <= 500 且 风险词 = 0 → 跳过（短内容可能不需要）

    返回 dict:
      {"status": "pass"|"warning",
       "benefit_count": int, "risk_count": int,
       "ratio": float,
       "benefit_terms": [top 5 收益词],
       "risk_terms": [top 5 风险词],
       "message": str}
    """
    # 统计收益词（去重计数，避免同一词被算多次）
    benefit_hits = {}
    for term in BENEFIT_TERMS:
        c = content.count(term)
        if c > 0:
            benefit_hits[term] = c
    benefit_count = sum(benefit_hits.values())

    # 统计风险词
    risk_hits = {}
    for term in RISK_TERMS:
        c = content.count(term)
        if c > 0:
            risk_hits[term] = c
    risk_count = sum(risk_hits.values())

    # 字数（粗略）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    content_length = chinese_chars

    # 判定
    issues = []
    ratio = benefit_count / max(risk_count, 1)

    if risk_count == 0 and content_length > 500:
        issues.append("完全缺少风险提示词（FDA Fair Balance 要求）")
    elif ratio > 3:
        issues.append(f"收益陈述/风险提示比 {ratio:.1f}:1 超过 3:1，收益陈述过重")

    # 取 top 5 显示
    top_benefits = sorted(benefit_hits.items(), key=lambda x: -x[1])[:5]
    top_risks = sorted(risk_hits.items(), key=lambda x: -x[1])[:5]

    return {
        "status": "warning" if issues else "pass",
        "benefit_count": benefit_count,
        "risk_count": risk_count,
        "ratio": round(ratio, 2),
        "top_benefit_terms": [{"term": t, "count": c} for t, c in top_benefits],
        "top_risk_terms": [{"term": t, "count": c} for t, c in top_risks],
        "issues": issues,
        "message": "；".join(issues) if issues else "收益/风险陈述基本平衡",
    }


# ---------- YMYL 增强 Schema 检查（2026-09-18 新增）----------
# Google AI Overviews 抓取医疗 YMYL 内容要求：
# - MedicalWebPage schema（医疗内容专用类型）
# - FAQPage schema（如页面有 FAQ 段落，必须用 FAQPage 结构化标记）
# 当前模板有"常见问题"段落但只用了 Article schema，无法被 AI Overviews 抓取。
# 本检查不阻断部署，只标 warning——提示 Phase 4 模板需升级。


def check_ymyl_schema(content, content_type="seo_knowledge_page"):
    """检查 Google YMYL E-E-A-T 要求的 Schema 是否齐全。

    检查项：
    - 是否有 MedicalWebPage schema（医疗内容专用）
    - 是否有 FAQPage schema（页面有 FAQ 段落时必需）
    - 是否有 author 署名（E-E-A-T 里的 Expertise）
    - 是否有 dateModified（内容新鲜度信号）
    - 是否有 publisher（组织信任标记）
    """
    issues = []

    # 提取所有 JSON-LD
    jsonld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        content, re.DOTALL,
    )
    all_types = []
    all_data = []
    for block in jsonld_blocks:
        try:
            data = json.loads(block.strip())
            all_data.append(data)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "@type" in item:
                        all_types.append(item["@type"])
            elif isinstance(data, dict) and "@type" in data:
                all_types.append(data["@type"])
        except json.JSONDecodeError:
            pass

    # 检查 MedicalWebPage
    if content_type == "seo_knowledge_page":
        if "MedicalWebPage" not in all_types:
            issues.append({
                "type": "missing_medical_webpage_schema",
                "severity": "warning",
                "message": "缺少 MedicalWebPage schema（Google AI Overviews 抓取门槛）",
                "found_types": all_types,
            })

    # 检查 FAQPage（页面有 FAQ 段落时必需）
    has_faq_section = bool(
        re.search(r'<h2[^>]*>.*?(常见问题|FAQ|问答).*?</h2>', content, re.IGNORECASE)
        or re.search(r'<h3[^>]*>Q:', content)
        or 'question' in content.lower() and 'answer' in content.lower()
    )
    if has_faq_section and "FAQPage" not in all_types:
        issues.append({
            "type": "missing_faqpage_schema",
            "severity": "warning",
            "message": "页面有 FAQ 段落但缺少 FAQPage schema（AI Overviews 抓取门槛）",
            "found_types": all_types,
        })

    # 检查 E-E-A-T 字段（author / publisher / dateModified）
    for data in all_data:
        if isinstance(data, dict) and data.get("@type") in ("Article", "MedicalWebPage"):
            if not data.get("author"):
                issues.append({
                    "type": "missing_author",
                    "severity": "warning",
                    "message": "缺少 author 字段（E-E-A-T Expertise 信号）",
                })
            if not data.get("publisher"):
                issues.append({
                    "type": "missing_publisher",
                    "severity": "warning",
                    "message": "缺少 publisher 字段（Trust 信号）",
                })
            if not data.get("dateModified"):
                issues.append({
                    "type": "missing_dateModified",
                    "severity": "warning",
                    "message": "缺少 dateModified（内容新鲜度信号）",
                })
            break

    return issues


def _llm_audit(content: str, title: str) -> list:
    """用 LLM 做深度审计（InkOS 审计员模式）。

    检查维度：AI 味、事实一致性、可读性、重复段落。
    返回建议列表（不阻断部署）。LLM 不可用或场景开关关闭时返回空列表。

    场景开关 LLM_AUDIT_ENABLED 默认 False：实测 minimind 35B 审计建议
    全是复读（"细胞毒性是…细胞毒性是…"），reviewer 看到的都是垃圾。
    启用需换更强模型（设 LLM_AUDIT_ENABLED=true）。本地启发式检查
    （check_ai_smell / check_fake_citations / check_fair_balance 等）
    不受开关影响，始终运行。
    """
    from llm_client import generate as llm_generate, is_available as llm_available, is_audit_enabled

    if not is_audit_enabled():
        return []

    if not llm_available():
        return []

    # 截断到前 1500 字，避免超长 context
    snippet = content[:1500]
    prompt = (
        f"审计以下健康科普文章，找出需要改进的地方。\n"
        f"标题：{title}\n"
        f"正文片段：\n{snippet}\n\n"
        f"检查维度：\n"
        f"1. AI 味：是否有「值得注意的是」「综上所述」「在当今」「深入探讨」等套话\n"
        f"2. 事实一致性：是否有自相矛盾或明显错误的表述\n"
        f"3. 可读性：是否有过长句子、术语堆砌\n"
        f"4. 重复度：是否有重复段落或套话复读\n\n"
        f"要求：\n"
        f"- 每条建议不超过 30 字\n"
        f"- 只列具体改进点，不要总结\n"
        f"- 如果文章质量没问题，回复'无'\n"
        f"- 直接输出建议，用换行分隔，不要编号"
    )

    result = llm_generate(
        prompt=prompt,
        system="你是内容质量审计员。严格、简洁，只列具体改进点。",
        max_tokens=500,
        temperature=0.1,
        timeout=60,
    )
    if not result:
        return []

    # 解析建议，过滤噪音（markdown 标题、复读段落、过长建议）
    notes = []
    for line in result.strip().split("\n"):
        line = line.strip().lstrip("0123456789.-) ")
        if not line or line == "无" or len(line) < 5:
            continue
        # 过滤 markdown 标题行
        if line.startswith("#"):
            continue
        # 过滤过长建议（LLM 复读段落）
        if len(line) > 50:
            continue
        notes.append(line)
    return notes[:5]


def test_content_item(item):
    """测试单个内容项"""
    content_path = BASE_DIR / item["content_file"]
    
    if not content_path.exists():
        return {
            "task_id": item["task_id"],
            "status": "failed",
            "error": f"文件不存在: {item['content_file']}",
            "checks": {}
        }
    
    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    checks = {}
    
    # 1. 医疗用语检查（分级：HIGH 出现即 fail，MEDIUM 标 warning）
    medical_result = check_medical_terms(content)
    high_count = len(medical_result["high"])
    medium_count = len(medical_result["medium"])
    if high_count:
        medical_status = "fail"
    elif medium_count:
        medical_status = "warning"
    else:
        medical_status = "pass"
    checks["medical_terms"] = {
        "status": medical_status,
        "high_count": high_count,
        "medium_count": medium_count,
        "details": (medical_result["high"] + medical_result["medium"])[:5],
        "suggestion": (
            "存在高风险医疗用语，内容不得上线。请替换为'改善'、'帮助'、"
            "'可能有助于'等温和表述，并去除绝对化承诺。"
            if high_count else
            ("存在中风险用语，建议人工复核。" if medium_count else "无医疗风险用语")
        ),
    }
    
    # 2. Schema标记检查
    if item["type"] == "seo_knowledge_page":
        schema_issues = check_schema_markup(content)
        checks["schema_markup"] = {
            "status": "pass" if len(schema_issues) == 0 else "fail",
            "issues_found": len(schema_issues),
            "details": schema_issues
        }
    
    # 3. 链接检查
    link_issues, valid_link_count = check_links(content)
    checks["links"] = {
        "status": "pass" if len(link_issues) == 0 else "warning",
        "valid_links": valid_link_count,
        "issues": link_issues
    }
    
    # 4. 字数检查
    wc_ok, word_count, wc_msg = check_word_count(content)
    checks["word_count"] = {
        "status": "pass" if wc_ok else "fail",
        "count": word_count,
        "message": wc_msg
    }
    
    # 5. SEO基础检查
    if item["type"] == "seo_knowledge_page":
        seo_issues = check_seo_basics(content)
        checks["seo_basics"] = {
            "status": "pass" if len(seo_issues) == 0 else "warning",
            "issues_found": len(seo_issues),
            "details": seo_issues
        }

    # 6. 虚假引用检测（不阻断，只 warning —— 让人类知道哪篇要精修）
    fake_issues = check_fake_citations(content)
    checks["fake_citations"] = {
        "status": "pass" if not fake_issues else "warning",
        "issues_found": len(fake_issues),
        "details": fake_issues[:5],
        "note": "模板硬编码的虚假研究引用（如 n=59,078），不阻断部署但建议人工精修"
    }

    # 7. 模板占位符检测（不阻断，warning）
    ph_issues = check_template_placeholders(content)
    checks["template_placeholders"] = {
        "status": "pass" if not ph_issues else "warning",
        "issues_found": len(ph_issues),
        "details": ph_issues[:5],
        "note": "f-string 未替换的 {xxx} 占位符"
    }

    # 8. LLM 深度审计（InkOS 审计员模式，不阻断，仅输出建议）
    llm_notes = _llm_audit(content, item.get("title", ""))
    checks["llm_audit"] = {
        "status": "pass" if not llm_notes else "warning",
        "issues_found": len(llm_notes),
        "notes": llm_notes[:10],
        "note": "LLM 深度审计建议（AI 味/事实一致性/可读性），不阻断部署"
    }

    # 9. FDA Fair Balance 收益/风险平衡检查（2025-09-09 新规，不阻断，warning）
    fb_result = check_fair_balance(content)
    checks["fair_balance"] = {
        "status": fb_result["status"],
        "benefit_count": fb_result["benefit_count"],
        "risk_count": fb_result["risk_count"],
        "ratio": fb_result["ratio"],
        "top_benefit_terms": fb_result["top_benefit_terms"],
        "top_risk_terms": fb_result["top_risk_terms"],
        "message": fb_result["message"],
        "note": "FDA Fair Balance 检查（收益/风险陈述平衡），不阻断部署"
    }

    # 10. YMYL 增强 Schema 检查（Google AI Overviews 抓取门槛，不阻断，warning）
    ymyl_issues = check_ymyl_schema(content, item.get("type", ""))
    checks["ymyl_schema"] = {
        "status": "pass" if not ymyl_issues else "warning",
        "issues_found": len(ymyl_issues),
        "details": ymyl_issues,
        "note": "Google YMYL E-E-A-T Schema 检查（MedicalWebPage/FAQPage/author），不阻断部署"
    }

    # 综合判定
    # 设计原则：
    # - 只有 fail 检查阻断上线（medical_terms HIGH / word_count / schema_markup 基础）
    # - warning 检查（fake_citations / llm_audit / fair_balance / ymyl_schema / medical_terms MEDIUM）
    #   仅记录在 checks 里供 reviewer 参考，不改变 overall。
    # 此前综合判定把 warning 也算进 overall，导致 warning 内容变成 test_warning 状态，
    # Phase 6 只认 test_passed → 内容无法上线。这正是 2026-09-17 记录的
    # "质量把关形同虚设"的反面：现在质量把关太严，正常内容也卡住。
    # 正确做法：fail 阻断，warning 提示，reviewer 看 checks 决定要不要精修。
    fail_checks = [name for name, c in checks.items() if c.get("status") == "fail"]
    warning_checks = [name for name, c in checks.items() if c.get("status") == "warning"]

    if fail_checks:
        overall = "failed"
    else:
        overall = "passed"

    return {
        "task_id": item["task_id"],
        "title": item.get("title", ""),
        "type": item.get("type", ""),
        "status": overall,
        "checks": checks,
        "fail_checks": fail_checks,
        "warning_checks": warning_checks,
        "warnings_count": len(warning_checks),
        "needs_review": len(warning_checks) > 0,
        "review_notes": [
            f"{name}: {checks[name].get('message') or checks[name].get('note', '')}"
            for name in warning_checks
        ],
    }


def run():
    phase = "test"
    try:
        start_phase(phase)
        
        # 校验配置可读（本阶段不消费具体配置项，保留校验以便配置写错时尽早失败）
        with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
            json.load(f)
        
        # 获取已生成的内容。
        # 必须同时认领 pending_test：core/self_heal.py 的 heal_failed_tasks() 会把
        # test_failed 的任务退回 pending_test 以重跑本阶段。此前这里只认 generated，
        # 两个状态机互不认识，导致自愈把任务改回一个永远没人认领的状态——
        # 任务被「重试」了一次却永久卡死，正是 self_heal.py 顶部记录的
        # 「task_edu_001 卡 8 天无重试、无告警」的根因。
        state = get_state()
        retryable = ("generated", "pending_test")
        tasks = [t for t in state.get("development_tasks", [])
                 if t.get("status") in retryable]

        if not tasks:
            log("没有待测试的内容，跳过测试阶段")
            complete_phase(phase, output_file=None, items_processed=0)
            return True
        log(f"待测试内容: {len(tasks)} 项 "
            f"(generated={sum(1 for t in tasks if t['status'] == 'generated')}, "
            f"pending_test={sum(1 for t in tasks if t['status'] == 'pending_test')})")
        
        # 测试每个内容项
        results = []
        passed = 0
        failed = 0
        warnings = 0
        
        for task in tasks:
            result = test_content_item(task)
            results.append(result)
            
            if result["status"] == "passed":
                passed += 1
                # 更新任务状态
                for t in state["development_tasks"]:
                    if t["task_id"] == task["task_id"]:
                        t["status"] = "test_passed"
                        break
            elif result["status"] == "failed":
                failed += 1
                # 区分 fail 类型：内容质量 fail vs 测试本身 fail。
                # 内容质量 fail（医疗高风险词 / 字数不足 / Schema 缺失）
                # 重试不会修复——模板生成的内容本身就有问题，必须人工介入。
                # 若标 test_failed，self_heal 会无限退回 pending_test 重跑，
                # 形成空转循环（实证：task_edu_001 曾因此卡 8 天）。
                # 标 needs_manual_review 让 self_heal 跳过重试，直接告警。
                checks = result.get("checks", {})
                is_content_quality_fail = (
                    checks.get("medical_terms", {}).get("status") == "fail"
                    or checks.get("word_count", {}).get("status") == "fail"
                    or checks.get("schema_markup", {}).get("status") == "fail"
                )
                for t in state["development_tasks"]:
                    if t["task_id"] == task["task_id"]:
                        if is_content_quality_fail:
                            t["status"] = "needs_manual_review"
                            # 记录具体 fail 原因，便于人工定位
                            reasons = []
                            for ck_name, ck_data in checks.items():
                                if ck_data.get("status") == "fail":
                                    reasons.append(f"{ck_name}={ck_data.get('message') or ck_data.get('status')}")
                            t["manual_review_reason"] = (
                                "内容质量未通过（自动重试无法修复，需人工改写）: "
                                + "; ".join(reasons)
                            )
                        else:
                            t["status"] = "test_failed"
                        break
            else:
                warnings += 1
                for t in state["development_tasks"]:
                    if t["task_id"] == task["task_id"]:
                        t["status"] = "test_warning"
                        break
        
        save_state(state)
        
        # 生成测试报告
        today = datetime.now().strftime("%Y-%m-%d")
        report = {
            "report_id": f"test_{today}",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "pass_rate": f"{round(passed/len(results)*100, 1)}%" if results else "N/A"
            },
            "check_categories": {
                "medical_terms": sum(1 for r in results if r["checks"].get("medical_terms", {}).get("status") == "pass"),
                "schema_markup": sum(1 for r in results if r["checks"].get("schema_markup", {}).get("status") == "pass"),
                "word_count": sum(1 for r in results if r["checks"].get("word_count", {}).get("status") == "pass"),
            },
            "results": results,
            "failed_items": [r for r in results if r["status"] == "failed"]
        }
        
        output_file = f"reports/analysis/{today}_test_report.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        complete_phase(
            phase,
            output_file=output_file,
            items_processed=len(results),
            passed=passed,
            failed=failed,
            warnings=warnings
        )
        log(f"测试完成: {passed}通过, {warnings}警告, {failed}失败")
        return True
        
    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
