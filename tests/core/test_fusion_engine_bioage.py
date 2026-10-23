"""八轴融合引擎 × 代谢-炎症轴 集成测试（研发路线三期 P2-1）

验证：体检指标驱动的代谢-炎症轴正确接入八轴匹配，且不污染 is_demo 三态。
确定性、零外部依赖。
"""
import pytest

from app.lib.fusion_engine import (
    UserProfile,
    recommend,
    AXIS_KEY,
    AXIS_LABEL,
    BIOAGE_AXIS_MAP,
    BIOAGE_WEAK_THRESHOLD,
)


# 全异常画像：血糖/HbA1c/CRP/腰围/血脂/血压/BMI 均超标
POOR_BIOMARKERS = {
    "glucose": 8.5, "hba1c": 8.0, "hs_crp": 8.0, "waist_cm": 105.0,
    "hdl": 0.8, "triglycerides": 3.5, "sbp": 165.0, "bmi": 32.0,
}
# 全正常画像
HEALTHY_BIOMARKERS = {
    "glucose": 5.0, "hba1c": 5.2, "hs_crp": 0.8, "waist_cm": 78.0,
    "hdl": 1.6, "triglycerides": 1.1, "sbp": 115.0, "bmi": 22.0,
}


def test_axis_key_and_label():
    """轴标识稳定，供上层/前端引用。"""
    assert AXIS_KEY == "metabolic_inflammatory"
    assert AXIS_LABEL == "代谢-炎症轴"
    assert BIOAGE_AXIS_MAP == {"F", "A"}


def test_poor_biomarkers_flag_axis_weak():
    """代谢-炎症轴分偏低 → 映射到 F/A 参与个性化匹配，has_bioage=True。"""
    profile = UserProfile(chrono_age=45, is_male=True, biomarkers=POOR_BIOMARKERS)
    out = recommend(profile, top_k=3)

    assert out["has_bioage"] is True
    assert out["bioage"] is not None
    assert out["bioage"]["axis_score"] < BIOAGE_WEAK_THRESHOLD
    assert out["bioage"]["axis_weak"] is True
    # 映射轴进入弱项轴集合
    assert BIOAGE_AXIS_MAP.issubset(set(out["weak_axes"]))
    assert set(out["bioage"]["mapped_axes"]) == BIOAGE_AXIS_MAP


def test_healthy_biomarkers_not_weak():
    """指标健康 → 轴分高，不把 F/A 标为弱项（避免误伤匹配）。"""
    profile = UserProfile(chrono_age=40, is_male=True, biomarkers=HEALTHY_BIOMARKERS)
    out = recommend(profile, top_k=3)

    assert out["has_bioage"] is True
    assert out["bioage"]["axis_score"] >= BIOAGE_WEAK_THRESHOLD
    assert out["bioage"]["axis_weak"] is False
    assert not BIOAGE_AXIS_MAP.issubset(set(out["weak_axes"]))


def test_bioage_does_not_pollute_has_gene():
    """关键：体检指标驱动的个性化不得被误报为基因/组学个性化。"""
    profile = UserProfile(chrono_age=45, biomarkers=POOR_BIOMARKERS)
    out = recommend(profile, top_k=3)

    assert out["has_gene"] is False          # 无基因数据
    assert out["has_bioage"] is True         # 但有体检指标
    assert "代谢-炎症轴" in out["banner"]      # 横幅如实说明是体检指标驱动


def test_no_data_still_demo_banner():
    """无任何数据 → 仍是完整 is_demo 示例横幅。"""
    out = recommend(UserProfile(), top_k=3)
    assert out["has_gene"] is False
    assert out["has_bioage"] is False
    assert out["bioage"] is None
    assert out["axis_scores"] == {}
    assert out["banner"].startswith("is_demo")


def test_gene_only_no_bioage():
    """仅基因数据 → has_gene=True，bioage 不参与。

    P0-1（2026-10-23）：has_gene 语义收紧——关键词推断的 weak_axes 不再冒充
    基因证据，只有显式标注为基因来源（gene_axes）或通路得分 <0.5（pathway_scores）
    才算基因数据。此测试因此改用 gene_axes 表达"确实来自基因"。
    """
    out = recommend(UserProfile(weak_axes={"D"}, gene_axes={"D"}), top_k=3)
    assert out["has_gene"] is True
    assert out["has_bioage"] is False
    assert out["bioage"] is None
    assert out["has_axis_hypothesis"] is False


def test_weak_axes_without_gene_marker_not_claims_gene():
    """P0-1 核心断言：仅传 weak_axes（无 gene_axes/pathway_scores）不应冒充基因证据。

    这是 2026-10-22 产品评估报告中定位到的最严重语义错位——
    上游 Planner 把"疲劳"关键词映射到 A 轴后传入 weak_axes，
    旧代码因此把 has_gene 置 True，导致：
      (1) banner 不显示"未提供基因数据"的免责
      (2) 推荐条目 gene_relevance 冒充"基因交集"
    """
    out = recommend(UserProfile(weak_axes={"A", "B"}, symptoms=["疲劳", "易感冒"]), top_k=5)
    assert out["has_gene"] is False, "关键词推断的轴不得冒充基因证据"
    assert out["has_axis_hypothesis"] is True, "应如实标注这是轴假设"
    assert out["has_bioage"] is False
    # banner 必须显式提示"未提供基因数据"，杜绝用户误以为拿到"基因定制"
    assert out["banner"] is not None and "未提供基因/组学数据" in out["banner"]
    # 每条个性化推荐都带 gene_source=False，前端据此不渲染"基因交集"文案
    personalized = [r for r in out["recommendations"] if r["mode"] == "personalized"]
    assert personalized, "至少要有一条 personalized 建议才能验证"
    for r in personalized:
        assert r["gene_source"] is False
        assert "基因交集" not in r.get("gene_relevance_display", "")


def test_gene_axes_marks_gene_source_true():
    """显式 gene_axes 或 pathway_scores 通路 <0.5 时，推荐条目标 gene_source=True。"""
    out = recommend(UserProfile(pathway_scores={"mitochondrial": 0.3}), top_k=5)
    assert out["has_gene"] is True
    personalized = [r for r in out["recommendations"] if r["mode"] == "personalized"]
    assert any(r["gene_source"] is True for r in personalized)


def test_bioage_output_shape_and_honesty():
    """输出结构与诚实标注：not_clinical=True + method 说明 + axis_scores。"""
    profile = UserProfile(chrono_age=45, biomarkers=POOR_BIOMARKERS)
    out = recommend(profile, top_k=3)
    ba = out["bioage"]

    for key in ("axis_key", "axis_label", "chrono_age", "bio_age",
                "delta", "axis_score", "axis_weak", "band",
                "mapped_axes", "not_clinical", "method", "markers"):
        assert key in ba, f"missing {key}"
    assert ba["not_clinical"] is True
    assert ba["bio_age"] > ba["chrono_age"]          # 异常画像生物学年龄应偏老
    assert len(ba["markers"]) == 8                    # 8 项标志物全量返回
    # S0-3：axis_scores 统一为 dict 结构（与 A-H 轴一致），bioage 轴以
    # {"axis","score","measured",...} 形式注入；数值在 ["score"] 字段。
    assert AXIS_KEY in out["axis_scores"]
    assert out["axis_scores"][AXIS_KEY]["score"] == ba["axis_score"]
    assert out["axis_scores"][AXIS_KEY]["measured"] is True
