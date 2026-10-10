"""HealthLens 知识平面包标识。

知识平面 = 全球化 / 无 PII / 可开源 / 可独立分发。
数据平面 = 区域化 / 含 PII / 永不出境。

这个包提供零依赖（除 PyYAML）的知识资产加载器。
"""
from knowledge.loader import (
    KnowledgeAssets,
    KnowledgeLoader,
    get_loader,
    reset_loader,
)

__version__ = "1.0.0"
__all__ = [
    "KnowledgeAssets",
    "KnowledgeLoader",
    "get_loader",
    "reset_loader",
]
