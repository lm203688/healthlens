"""HealthLens 知识平面加载器（A1 骨架）

**核心命题**：知识平面与数据平面彻底解耦。
本加载器**只读文件系统**，不依赖数据库、Redis、JWT、用户会话。
知识平面可独立打包、独立分发、独立版本化。

**设计约束**：
- 只用标准库 + PyYAML（无 FastAPI/SQLAlchemy/redis 依赖）
- 所有加载函数返回 Python 原生 dict/list，不返回 ORM 对象
- 加载失败时返回空 dict/list（fail-safe），不 raise
- 无写操作，只读
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field


@dataclass
class KnowledgeAssets:
    """知识资产快照（加载后内存中的完整状态）。"""
    version: str = "unknown"
    manifest: dict = field(default_factory=dict)
    evidence_cases: list[dict] = field(default_factory=list)
    pathway_to_syndrome: dict = field(default_factory=dict)
    tcm_entities: dict = field(default_factory=dict)
    axis_meta: dict = field(default_factory=dict)
    axis_thresholds: dict = field(default_factory=dict)
    mcp_tools: list[dict] = field(default_factory=list)


def _find_root() -> Path:
    """定位仓库根目录（从当前文件向上 2 层）。"""
    here = Path(__file__).resolve()
    return here.parent.parent  # knowledge/ -> repo_root


class KnowledgeLoader:
    """知识平面统一加载器。

    Args:
        base_dir: 知识平面根目录。默认使用仓库根目录。
        strict: True 时加载失败 raise；False 时返回空结构（默认）。
    """

    def __init__(self, base_dir: str | Path | None = None, strict: bool = False):
        self.strict = strict
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            self.base_dir = _find_root()
        self._cache: dict[str, Any] = {}

    def load_manifest(self) -> dict:
        """加载 MANIFEST.json（版本清单）。"""
        if "manifest" in self._cache:
            return self._cache["manifest"]
        path = self.base_dir / "knowledge" / "MANIFEST.json"
        if not path.exists():
            if self.strict:
                raise FileNotFoundError(f"MANIFEST not found: {path}")
            self._cache["manifest"] = {"version": "unknown"}
            return self._cache["manifest"]
        try:
            with open(path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            self._cache["manifest"] = manifest
            return manifest
        except Exception as e:
            if self.strict:
                raise
            self._cache["manifest"] = {"version": "unknown", "error": str(e)}
            return self._cache["manifest"]

    def load_evidence(self) -> list[dict]:
        """加载 case_evidence_db.json 的 cases 列表。"""
        if "evidence" in self._cache:
            return self._cache["evidence"]
        # 优先 knowledge/ 副本，退化到 data/（向后兼容）
        for candidate in [
            self.base_dir / "knowledge" / "evidence" / "case_evidence_db.json",
            self.base_dir / "data" / "case_evidence_db.json",
        ]:
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    cases = data.get("cases", [])
                    self._cache["evidence"] = cases
                    return cases
                except Exception:
                    if self.strict:
                        raise
        self._cache["evidence"] = []
        return self._cache["evidence"]

    def load_pathway_map(self) -> dict:
        """加载 pathway_to_syndrome_map.json 的 pathways dict。"""
        if "pathways" in self._cache:
            return self._cache["pathways"]
        for candidate in [
            self.base_dir / "knowledge" / "tcm_entities" / "pathway_to_syndrome.json",
            self.base_dir / "data" / "pathway_to_syndrome_map.json",
        ]:
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    pathways = data.get("pathways", {})
                    self._cache["pathways"] = pathways
                    return pathways
                except Exception:
                    if self.strict:
                        raise
        self._cache["pathways"] = {}
        return self._cache["pathways"]

    def load_axis_config(self, jurisdiction: str = "cn") -> dict:
        """加载八轴阈值配置（含 jurisdiction 覆盖）。"""
        if "axis_config" in self._cache:
            return self._cache["axis_config"]
        try:
            import yaml
            path = self.base_dir / "config" / "axes" / "axes.yaml"
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            merged = {}
            for k, v in raw.items():
                if k.startswith("axis_") and isinstance(v, dict):
                    merged[k] = {
                        "label": v.get("label"),
                        "concept": v.get("concept"),
                        "proxy": v.get("proxy"),
                        "thresholds": {},
                    }
                    for metric, vals in v.get("thresholds", {}).items():
                        if isinstance(vals, dict) and "default" in vals:
                            merged[k]["thresholds"][metric] = dict(vals["default"])
            overrides = raw.get("jurisdiction_overrides", {}).get(jurisdiction, {})
            for axis_key, axis_overrides in overrides.items():
                if axis_key in merged and isinstance(axis_overrides, dict):
                    for metric, vals in axis_overrides.get("thresholds", {}).items():
                        if metric in merged[axis_key]["thresholds"] and isinstance(vals, dict):
                            merged[axis_key]["thresholds"][metric].update(vals)
            self._cache["axis_config"] = merged
            return merged
        except Exception:
            if self.strict:
                raise
            self._cache["axis_config"] = {}
            return self._cache["axis_config"]

    def load_tcm_entities(self) -> dict:
        """加载 tcm_structured/ 目录的实体索引（若存在）。"""
        if "tcm" in self._cache:
            return self._cache["tcm"]
        entities = {}
        for candidate in [
            self.base_dir / "knowledge" / "tcm_entities" / "tcm_structured",
            self.base_dir / "data" / "tcm_structured",
        ]:
            if candidate.exists() and candidate.is_dir():
                try:
                    for f in candidate.iterdir():
                        if f.is_file() and f.suffix == ".json":
                            with open(f, "r", encoding="utf-8") as fp:
                                entities[f.stem] = json.load(fp)
                except Exception:
                    pass
                break
        self._cache["tcm"] = entities
        return entities

    def snapshot(self) -> KnowledgeAssets:
        """加载所有知识资产到内存快照。"""
        return KnowledgeAssets(
            version=self.load_manifest().get("version", "unknown"),
            manifest=self.load_manifest(),
            evidence_cases=self.load_evidence(),
            pathway_to_syndrome=self.load_pathway_map(),
            tcm_entities=self.load_tcm_entities(),
            axis_meta={},
            axis_thresholds=self.load_axis_config(),
            mcp_tools=[],
        )

    def stats(self) -> dict:
        """返回知识平面当前统计（供 health check 用）。"""
        return {
            "version": self.load_manifest().get("version", "unknown"),
            "evidence_cases": len(self.load_evidence()),
            "pathway_count": len(self.load_pathway_map()),
            "tcm_entity_files": len(self.load_tcm_entities()),
            "axis_config_loaded": bool(self.load_axis_config()),
            "base_dir": str(self.base_dir),
        }


_default_loader: KnowledgeLoader | None = None


def get_loader(base_dir: str | Path | None = None) -> KnowledgeLoader:
    """获取默认 KnowledgeLoader 单例。"""
    global _default_loader
    if _default_loader is None:
        _default_loader = KnowledgeLoader(base_dir=base_dir)
    return _default_loader


def reset_loader() -> None:
    """清空默认加载器单例（测试用）。"""
    global _default_loader
    _default_loader = None
