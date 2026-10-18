"""
multimodal_probe.py — 多模态八轴倾向速判原型（演示入口）

生产逻辑位于 healthlens_agent/multimodal.py（视觉工具箱 + RAG 接地 + 自校正）。

  python tools/multimodal_probe.py --image-desc "舌淡红、苔薄白、面色萎黄、体态乏力"
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthlens_agent.multimodal import main  # noqa: E402


if __name__ == "__main__":
    main()
