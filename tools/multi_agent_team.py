"""
multi_agent_team.py — HealthLens 四角色 Agent 团队（演示入口）

生产逻辑位于 healthlens_agent/team.py（Planner/Executor/Critic/Referee 四角色分离）。

  python tools/multi_agent_team.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthlens_agent.team import demo  # noqa: E402


if __name__ == "__main__":
    demo()
