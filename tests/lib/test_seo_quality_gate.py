"""SEO 发布质量闸门单测（M14 P0-1）。

被测对象：``app/lib/seo_quality_gate.py`` 的纯逻辑层。
这些测试**不起数据库、不起 FastAPI**，直接调函数——闸门每条规则都必须
能独立验证，否则「闸门坏了还是绿」就无法被发现。

覆盖的核心不变式：
1. 占位内容必须被拦（批量生成器留下的草稿不可上线）。
2. 真实生成的富内容必须放行（闸门不能死锁发布流程）。
3. 医疗宣称 / 急救误导 / 免责声明缺失是安全关键 blocker。
4. fail-closed：闸门自身异常不得变成放行。
"""
import pytest

from app.lib import seo_quality_gate as g
from app.lib.seo_quality_gate import GateStatus, run_quality_gate
from app.services.seo_factory import get_factory


# ---------------------------------------------------------------------------
# 测试用内容构造器
# ---------------------------------------------------------------------------

def make_page(
    *,
    words: int = 400,
    with_h2: bool = True,
    with_meta: bool = True,
    with_canonical: bool = True,
    with_limitation: bool = True,
    extra: str = "",
) -> str:
    """构造一份"合规"的 SEO 页面骨架，按需开关各检查要素。

    注意：filler 必须是**中性文本**。若 filler 含"不构成/免责/仅供参考"等
    词，会让 limitation 检查在整页任意位置都判 PASS，使
    ``with_limitation=False`` 的分支失去区分度（闸门形同虚设）。
    """
    filler = ("健康生活方式的长期积累对整体状态有积极影响，值得持续关注。"
              * (words // 30))
    parts = [
        "<!DOCTYPE html><html><head>",
        f'<meta name="description" content="测试页面描述">' if with_meta else "",
        f'<link rel="canonical" href="https://healthlens.cc/{extra or "x"}">'
        if with_canonical
        else "",
        "</head><body>",
        "<h1>测试标题</h1>",
        f"<h2>小节一</h2><p>{filler}</p>" if with_h2 else f"<p>{filler}</p>",
        "<h2>小节二</h2><p>" + filler + "</p>" if with_h2 else "",
        '<script type="application/ld+json">'
        '{"@type": "Article", "@context": "https://schema.org"}'
        "</script>",
        '<script type="application/ld+json">'
        '{"@type": "FAQPage"}'
        "</script>",
        '<script type="application/ld+json">'
        '{"@type": "MedicalWebPage"}'
        "</script>",
        "<p>" + ("本文为养生参考，不构成医疗建议。" if with_limitation else "正文结束。")
        + "</p>",
        extra,
        "</body></html>",
    ]
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 1. 占位内容必须被拦
# ---------------------------------------------------------------------------

class TestPlaceholderBlocked:
    def test_generate_endpoint_placeholder_is_blocked(self):
        """`POST /pages/generate` 实际产出的占位页必须被闸门拦下。

        这是本轮修复的原始缺陷：该端点生成
        ``<h1>{kw}</h1><p>正在生成中...</p>`` 且 ``word_count=0``，
        修复前可被一键发布到公开站点。
        """
        html = '<h1>生姜</h1><p>正在生成中...</p>'
        result = run_quality_gate(html, slug="ginger")
        assert result.passed is False
        codes = {c.check_name for c in result.checks if c.status == GateStatus.FAIL}
        assert "word_count" in codes

    def test_placeholder_marker_blocks_even_with_long_text(self):
        """即使字数够长，占位标记也不能被字数掩盖。"""
        html = make_page(extra="<p>待补充：更多内容稍后写入</p>")
        result = run_quality_gate(html)
        assert result.passed is False

    def test_missing_limitation_blocks(self):
        html = make_page(with_limitation=False)
        result = run_quality_gate(html)
        assert result.passed is False
        fails = [c for c in result.checks if c.status == GateStatus.FAIL]
        assert any(c.check_name == "limitation" for c in fails)


# ---------------------------------------------------------------------------
# 2. 真实生成的富内容必须放行（闸门不得死锁发布）
# ---------------------------------------------------------------------------

class TestRealContentPasses:
    def test_factory_generated_page_passes(self):
        """`SeoContentFactory.generate_page()` 的真实产物必须通过闸门。

        若本测试失败，说明闸门接线后所有真实页面都无法发布——属于
        比"占位页被放行"更糟的失效模式（发布流程整体瘫痪）。
        """
        html = get_factory().generate_page(
            slug="ginger-food-medicine",
            title="生姜：传统食疗与养生参考",
            content_sections=[
                {"heading": "概述", "body": "<p>生姜是常见食材，本文仅供养生参考。</p>"},
                {"heading": "食用方式", "body": "<p>多种食用方式可供参考。</p>"},
            ],
            faq_items=[
                {"question": "生姜怎么吃？", "answer": "有多种方式，仅供参考。"}
            ],
            keywords=["生姜"],
            category="herbs",
        )
        result = run_quality_gate(html, slug="ginger-food-medicine")
        assert result.passed is True, (
            f"factory page wrongly blocked: {result.critical_issues}"
        )
        assert result.score == 100

    def test_minimal_but_complete_page_passes(self):
        html = make_page()
        result = run_quality_gate(html, slug="minimal")
        assert result.passed is True, result.critical_issues


# ---------------------------------------------------------------------------
# 3. 安全关键 blocker
# ---------------------------------------------------------------------------

class TestSafetyBlockers:
    def test_medical_claim_is_blocked(self):
        html = make_page(extra="<p>本方案可以确诊并根治糖尿病。</p>")
        result = run_quality_gate(html)
        assert result.passed is False
        fails = [c for c in result.checks if c.status == GateStatus.FAIL]
        assert any(c.check_name == "medical_claims" for c in fails)

    def test_medical_claim_in_disclaimer_context_is_allowed(self):
        """免责声明语境中引用"不构成医疗诊断"不应被误判为医疗宣称。"""
        html = make_page(
            extra="<p>本页不构成医疗诊断依据，也不替代专业医生的诊断结果。</p>"
        )
        result = run_quality_gate(html)
        claims = [c for c in result.checks if c.check_name == "medical_claims"]
        assert claims, "medical_claims check must run"
        assert claims[0].status != GateStatus.FAIL, claims[0].message

    def test_emergency_misguide_is_blocked(self):
        """建议急症患者自行处理、延误就医 = 安全关键缺陷。"""
        html = make_page(extra="<p>胸痛在家就能治，不需要去医院。</p>")
        result = run_quality_gate(html)
        assert result.passed is False
        fails = [c for c in result.checks if c.status == GateStatus.FAIL]
        assert any(c.check_name == "emergency_misguide" for c in fails)

    def test_over_promise_is_warning_not_blocker(self):
        """过度承诺是质量问题（warning），不是安全 blocker。"""
        html = make_page(extra="<p>这是效果最好的方案。</p>")
        result = run_quality_gate(html)
        assert result.passed is True
        assert any(
            c.check_name == "over_promise" and c.status == GateStatus.WARN
            for c in result.checks
        )

    def test_thin_content_warns_but_does_not_block(self):
        html = make_page(words=260)
        result = run_quality_gate(html)
        assert result.passed is True
        assert any(
            c.check_name == "word_count" and c.status == GateStatus.WARN
            for c in result.checks
        )

    def test_structure_failure_blocks(self):
        html = make_page(with_h2=False, with_meta=False, with_canonical=False)
        result = run_quality_gate(html)
        assert result.passed is False
        fails = [c for c in result.checks if c.status == GateStatus.FAIL]
        assert any(c.check_name == "structure" for c in fails)


# ---------------------------------------------------------------------------
# 4. 评分与重复检测
# ---------------------------------------------------------------------------

class TestScoringAndDedup:
    def test_duplicate_slug_is_blocked(self):
        html = make_page()
        result = run_quality_gate(html, slug="a", existing_slugs={"a"})
        assert result.passed is False
        fails = [c for c in result.checks if c.status == GateStatus.FAIL]
        assert any(c.check_name == "duplicate" for c in fails)

    def test_unique_slug_passes_duplicate_check(self):
        html = make_page()
        result = run_quality_gate(html, slug="b", existing_slugs={"a"})
        dups = [c for c in result.checks if c.check_name == "duplicate"]
        assert dups[0].status == GateStatus.PASS

    def test_score_bounds(self):
        """评分必须在 0–100 之间，且 blocker 越多分越低。"""
        good = run_quality_gate(make_page(), slug="g").score
        bad = run_quality_gate(
            '<h1>x</h1><p>正在生成中</p>', slug="b"
        ).score
        assert 0 <= good <= 100
        assert 0 <= bad <= 100
        assert good > bad

    def test_all_checks_always_run(self):
        """闸门必须报告全部检查项，不能因前一项失败就短路。"""
        result = run_quality_gate("<h1>x</h1><p>正在生成中</p>")
        names = {c.check_name for c in result.checks}
        assert names == {
            "placeholder", "word_count", "structure", "schema", "medical_claims",
            "emergency_misguide", "over_promise", "limitation", "duplicate",
        }


# ---------------------------------------------------------------------------
# 5. fail-closed：闸门坏了不能变成放行
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_empty_html_is_blocked(self):
        result = run_quality_gate("")
        assert result.passed is False

    def test_none_html_is_blocked(self):
        result = run_quality_gate(None)  # type: ignore[arg-type]
        assert result.passed is False

    def test_file_runner_reports_block_on_bad_file(self, tmp_path):
        p = tmp_path / "page.html"
        p.write_text("<h1>x</h1><p>正在生成中</p>", encoding="utf-8")
        result = g.run_quality_gate_on_file(p)
        assert result.passed is False
        assert result.checks, "file runner must return checks"
