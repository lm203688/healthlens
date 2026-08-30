"""
bench_pipeline.py — HealthLens 融合管线评测 harness（演示入口）

生产逻辑位于 healthlens_agent/benchmark.py（GOAI 七维度行为评测 + launch-risk score）。

  python tools/bench_pipeline.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthlens_agent.benchmark import main  # noqa: E402


if __name__ == "__main__":
    main()
