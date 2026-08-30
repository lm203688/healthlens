"""四角色 Agent 团队测试。"""

from healthlens_agent.team import planner, team_run


def test_team_halts_emergency():
    res = team_run("我最近总是胸痛伴随呼吸困难")
    assert res["referee"]["decision"] == "HALT"


def test_team_pass_normal():
    res = team_run("最近容易疲劳、怕冷、睡不好，线粒体通路偏弱")
    assert res["referee"]["decision"] == "PASS"
    assert res["execution"]["rec_count"] > 0
    assert res["critic"]["score"] >= 60


def test_planner_infers_axes():
    plan = planner("我最近疲劳、失眠、焦虑")
    assert "A" in plan.axes  # 疲劳
    assert "D" in plan.axes  # 失眠
    assert "G" in plan.axes  # 焦虑
