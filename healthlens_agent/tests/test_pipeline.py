"""融合安全管线测试（接入真实 fusion_engine）。"""

from healthlens_agent.pipeline import UserProfile, run_pipeline


def test_pipeline_halts_emergency():
    res = run_pipeline(user_input="我最近总是胸痛伴随呼吸困难")
    assert res.passed is False
    assert res.pre_result.passed is False
    assert res.banner and "急救" in res.banner


def test_pipeline_normal_run():
    res = run_pipeline(
        user_input="最近容易疲劳、怕冷、睡不好",
        profile=UserProfile(
            pathway_scores={"mitochondrial": 0.32, "Circadian_CLOCK_BMAL1": 0.41}
        ),
    )
    assert res.passed is True
    assert res.any_unsafe is False
    assert len(res.recommendations) > 0
    # 每条建议都有 gate_passed 字段
    assert all("gate_passed" in r for r in res.recommendations)


def test_pipeline_is_demo_banner():
    res = run_pipeline(user_input="帮我看看体质", profile=UserProfile())
    assert res.banner and "is_demo" in res.banner


def test_pipeline_to_dict():
    res = run_pipeline(
        user_input="最近疲劳",
        profile=UserProfile(pathway_scores={"mitochondrial": 0.4}),
    )
    d = res.to_dict()
    assert "passed" in d and "disclaimer" in d
