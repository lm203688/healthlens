"""
fusion_pipeline.py — HealthLens 融合安全管线（演示入口）

生产逻辑位于 healthlens_agent/pipeline.py（GOAI 借鉴落地：两道安全闸门 + 运行时审计
直接接入真实融合引擎 app/lib/fusion_engine.recommend()）。

本文件仅作命令行演示入口，保持向下兼容：
  python tools/fusion_pipeline.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthlens_agent.pipeline import demo  # noqa: E402


if __name__ == "__main__":
    demo()
