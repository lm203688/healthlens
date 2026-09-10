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
    """仅基因数据 → has_gene=True，bioage 不参与。"""
    out = recommend(UserProfile(weak_axes={"D"}), top_k=3)
    assert out["has_gene"] is True
    assert out["has_bioage"] is False
    assert out["bioage"] is None


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
    assert out["axis_scores"][AXIS_KEY] == ba["axis_score"]
