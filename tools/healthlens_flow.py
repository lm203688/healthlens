"""
healthlens_flow.py — HealthLens 可复现融合 DAG pipeline（演示入口）

生产逻辑位于 healthlens_agent/flow.py（算子 + DAG 执行器，真实调用融合引擎）。

  python tools/healthlens_flow.py --input "最近容易疲劳怕冷" --gene mitochondrial:0.32
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthlens_agent.flow import main  # noqa: E402


if __name__ == "__main__":
    main()
