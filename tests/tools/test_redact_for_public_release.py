"""脱敏发布工具回归测试（S2-4 许可审计 · 方案 A）。

历史事故（2026-10-13，commit 49f80ea0de）
-----------------------------------------
`STRIP_MAP["classical_slices.json"]["fields"]` 只配了 `["passage", "efficacy"]`，
漏掉了同样承载上游逐字引文的 `citation`（60/613 条、995 字）。更糟的是
`_emit` 的校验**只按 STRIP_MAP 自身核对**，配置漏项时必然通过——所以缺陷
静默通过了校验并被推到远端，而提交信息还声称剥离了 7 个字段（假声明）。

本测试锁定三条防线，缺一即失败：
1. **字段处置完整性**：源数据里每个字段必须明确归入 剥离 / 经复核保留 /
   HealthLens 自撰 三者之一。新增任何未分类字段 => 测试失败。
   （这就是拦住 `citation` 的那条：它当时属于「无人认领」。）
2. **独立黑名单**：不依赖 STRIP_MAP，任何上游逐字字段出现在产物中 => 失败。
3. **空转检测**：STRIP_MAP 配置的字段必须在源中真实存在。

以及一条事故复现：把 STRIP_MAP 改回当年的错误配置，必须被拦下。
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "redact_for_public_release.py"
SRC = REPO / "data"

# --- 字段处置白名单：与 tools/redact_for_public_release.py 的语义对齐。 ---
# 允许保留在产物中的 HealthLens 自撰 / 短书目元数据。
# type/name/property 为药名与四气五味等事实性短元数据，与 classical_slices 中
# 经复核保留的 entity/property 同属一类；evidence_level 为 HealthLens 自撰分级。
HEALTHLENS_OWN = {
    "classical_slices.json": {
        "slice_id",
        "evidence_level",
        "axis_hint",
        "axis_hint_secondary",
        "axis_label",
        "matched_keywords",
        "axis_confidence",
        "axis_method",
        "needs_expert_review",
    },
    "tcm_structured": {"type", "name", "property", "evidence_level"},
}


def _load_tool() -> object:
    spec = importlib.util.spec_from_file_location("_redact_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def tool() -> object:
    """每次测试全新加载模块，避免 --keep-verbatim 之类的 globals 污染。"""
    return _load_tool()


def _slices_of(src: Path) -> list[dict]:
    doc = json.loads(src.read_text(encoding="utf-8"))
    return doc["slices"]


def _entities_of(src: Path) -> list[dict]:
    doc = json.loads(src.read_text(encoding="utf-8"))
    return doc["entities"]


class TestFieldDispositionCompleteness:
    """防线 1：源里每个字段都必须有明确处置，不许「无人认领」。"""

    def test_classical_slices_every_field_classified(self, tool):
        src = SRC / "classical_slices.json"
        fields = {k for s in _slices_of(src) for k in s}
        stripped = set(tool.STRIP_MAP["classical_slices.json"]["fields"])
        retained = set(tool.REVIEWED_RETAINED["classical_slices.json"])
        own = HEALTHLENS_OWN["classical_slices.json"]
        unclassified = fields - stripped - retained - own
        assert not unclassified, (
            f"classical_slices.json 存在未分类字段 {sorted(unclassified)}：\n"
            f"必须在 STRIP_MAP（剥离）/ REVIEWED_RETAINED（复核保留）/ "
            f"HEALTHLENS_OWN（自撰）三者中明确其一。\n"
            f"历史教训：citation 曾因无人分类而随产物公开发布。"
        )

    def test_tcm_structured_every_field_classified(self, tool):
        stripped = set(tool.TCM_STRUCTURED_FIELDS)
        own = HEALTHLENS_OWN["tcm_structured"]
        for src in sorted((SRC / "tcm_structured").glob("*.json")):
            fields = {k for e in _entities_of(src) for k in e}
            unclassified = fields - stripped - own
            assert not unclassified, (
                f"{src.name} 存在未分类字段 {sorted(unclassified)}：必须明确处置。"
            )

    def test_citation_is_not_just_overlooked_again(self, tool):
        """事故锚点：citation 必须被剥离，不得退回到当年的错误配置。"""
        fields = set(tool.STRIP_MAP["classical_slices.json"]["fields"])
        assert "citation" in fields, (
            "classical_slices.json 的 citation 字段承载上游逐字引文"
            "（《太平御览》等），必须在剥离列表中。"
        )
        assert "citation" in tool.UPSTREAM_VERBATIM_FIELDS


class TestIndependentBlacklist:
    """防线 2：校验器不得只按自己的配置核对，须有独立黑名单兜底。"""

    def test_blacklist_superset_of_stripped(self, tool):
        stripped = set(tool.STRIP_MAP["classical_slices.json"]["fields"])
        assert stripped <= set(tool.UPSTREAM_VERBATIM_FIELDS), (
            "STRIP_MAP 声明剥离的字段必须都在独立黑名单内，否则黑名单不是兜底。"
        )

    def test_guard_catches_the_historical_accident(self, tool):
        """把 STRIP_MAP 改回当年漏配 citation 的状态，必须被硬断言拦下。"""
        tool.STRIP_MAP["classical_slices.json"]["fields"] = ["passage", "efficacy"]
        with pytest.raises(AssertionError, match="STRIP_MAP 漏项"):
            tool.redact_classical_slices(write=False)

    def test_guard_catches_any_surviving_verbatim_field(self, tool):
        """黑名单里的字段只要残留在产物中就必须中断，无论配置怎么声明。"""
        for victim in sorted(tool.UPSTREAM_VERBATIM_FIELDS):
            if victim not in {"passage", "efficacy", "citation"}:
                continue  # source_quote 属于 tcm_structured，不在本来源
            fields = ["passage", "efficacy", "citation"]
            fields.remove(victim)
            tool.STRIP_MAP["classical_slices.json"]["fields"] = list(fields)
            with pytest.raises(AssertionError) as exc:
                tool.redact_classical_slices(write=False)
            assert victim in str(exc.value), (
                f"漏剥 {victim} 时断言信息未点名该字段，排查时会误导。"
            )

    def test_correct_config_passes(self, tool):
        """对照组：正确配置不应被误拦。"""
        stat = tool.redact_classical_slices(write=False)
        assert stat["leaked_fields"] == 0


class TestInertConfigDetection:
    """防线 3：配置了剥离、源里却不存在的字段 => 记录空转告警。

    空转本身不构成泄漏（没剥等于没泄漏），因此是告警而非中断——
    断言中断曾误伤跨来源黑名单字段（source_quote 不属于 classical_slices）。
    """

    def test_inert_field_is_reported_not_fatal(self, tool):
        tool.STRIP_MAP["classical_slices.json"]["fields"].append("nonexistent_field")
        stat = tool.redact_classical_slices(write=False)
        assert "nonexistent_field" in stat["inert_fields"]
        assert stat["leaked_fields"] == 0

    def test_cross_source_field_not_false_positive(self, tool):
        """黑名单是跨来源并集，引用其它来源的字段不该被当成空转。"""
        fields = sorted(
            set(tool.STRIP_MAP["classical_slices.json"]["fields"])
            | set(tool.UPSTREAM_VERBATIM_FIELDS)
        )
        tool.STRIP_MAP["classical_slices.json"]["fields"] = fields
        stat = tool.redact_classical_slices(write=False)
        assert stat["leaked_fields"] == 0

    def test_all_configured_fields_exist_in_source(self, tool):
        """反向锚点：当前配置不得有空转项（防止静默配置漂移）。"""
        stat = tool.redact_classical_slices(write=False)
        assert stat["inert_fields"] == [], (
            f"STRIP_MAP 配置了源中不存在的字段 {stat['inert_fields']}，"
            "剥离为空转，请修正配置。"
        )


class TestEndToEndOutput:
    """端到端：写盘产物的逐字字段必须全部清零，且不得改动源文件。"""

    def test_output_contains_no_upstream_verbatim_fields(self, tool, tmp_path):
        tool.OUT_ROOT = tmp_path  # 不碰仓库内的 data/publishable/
        stat = tool.redact_classical_slices(write=True)
        dest = tmp_path / "classical_slices.json"
        assert dest.is_file(), "脱敏产物未写出"

        slices = json.loads(dest.read_text(encoding="utf-8"))["slices"]
        for rec in slices:
            leaked = set(rec) & set(tool.UPSTREAM_VERBATIM_FIELDS)
            assert not leaked, (
                f"产物记录 {rec.get('slice_id')} 含上游逐字字段 {sorted(leaked)}"
            )

        # 反证：源里确实有内容，产物里应为 0。防止「源本来就没有」导致的空通过。
        src = _slices_of(SRC / "classical_slices.json")
        assert sum(1 for s in src if s.get("citation")) > 0, (
            "源数据已不含 citation，无法证明脱敏有效——请核对源文件。"
        )
        assert sum(1 for s in slices if s.get("citation")) == 0
        assert stat["verbatim_chars_removed"] > 0
        assert len(slices) == len(src)

    def test_source_files_never_modified(self, tool, tmp_path):
        """脱敏必须是只读派生：跑完源文件字节与哈希不变。"""
        import hashlib

        before = {
            str(p): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in [SRC / "classical_slices.json"]
            + sorted((SRC / "tcm_structured").glob("*.json"))
        }
        tool.OUT_ROOT = tmp_path
        tool.redact_classical_slices(write=True)
        for name, st in tool.redact_tcm_structured(write=True).items():
            assert st["leaked_fields"] == 0
        after = {
            str(p): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in [SRC / "classical_slices.json"]
            + sorted((SRC / "tcm_structured").glob("*.json"))
        }
        assert before == after, "脱敏过程修改了源数据文件，违反只读派生约定"

    def test_record_counts_preserved(self, tool, tmp_path):
        """脱敏不得丢记录，只剥字段。"""
        tool.OUT_ROOT = tmp_path
        tool.redact_classical_slices(write=True)
        out = json.loads((tmp_path / "classical_slices.json").read_text(encoding="utf-8"))
        assert len(out["slices"]) == len(_slices_of(SRC / "classical_slices.json"))

    def test_notice_declares_retained_bibliographic(self, tool, tmp_path):
        """保留的书目字段必须在产物里显式声明理由，不得伪装成「已剥离」。"""
        tool.OUT_ROOT = tmp_path
        tool.redact_classical_slices(write=True)
        notice = json.loads(
            (tmp_path / "classical_slices.json").read_text(encoding="utf-8")
        )["meta"]["redaction_notice"]
        assert notice["retained_bibliographic"], "产物未声明保留的书目字段"
        assert notice.get("retained_bibliographic_rationale"), (
            "保留了书目字段却未写入理由，无法供下游自查许可风险"
        )
        for f in notice["retained_bibliographic"]:
            assert f not in notice["fields_stripped"], (
                f"{f} 同时被列入剥离与保留，声明自相矛盾"
            )

    def test_keep_verbatim_still_strips_citation(self, tool, tmp_path):
        """--keep-verbatim 只放宽 efficacy，逐字引文一个都不放。

        注意：efficacy 必须通过 AUTHORIZED_RETENTION 显式授权，
        而不是靠从剥离列表里删掉来「绕」过黑名单——后者会让黑名单失去意义。
        """
        tool.STRIP_MAP["classical_slices.json"]["fields"] = ["passage", "citation"]
        tool.TCM_STRUCTURED_FIELDS = ["source_quote"]
        tool.AUTHORIZED_RETENTION = {"efficacy"}
        tool.OUT_ROOT = tmp_path
        tool.redact_classical_slices(write=True)
        slices = json.loads(
            (tmp_path / "classical_slices.json").read_text(encoding="utf-8")
        )["slices"]
        assert all("citation" not in s for s in slices)
        assert all("passage" not in s for s in slices)
        # 授权保留的字段确实被保留，且 notice 里自我声明了例外
        assert any("efficacy" in s for s in slices), "efficacy 应被授权保留"
        notice = json.loads(
            (tmp_path / "classical_slices.json").read_text(encoding="utf-8")
        )["meta"]["redaction_notice"]
        assert notice["authorized_retention"] == ["efficacy"]

    def test_authorization_cannot_exempt_non_verbatim_field(self, tool):
        """AUTHORIZED_RETENTION 只能收敛于黑名单，不能当绕过黑名单的后门。"""
        tool.AUTHORIZED_RETENTION = {"slice_id"}  # 自撰字段，不该走授权通道
        with pytest.raises(AssertionError, match="非上游逐字字段"):
            tool.redact_classical_slices(write=False)

    def test_keep_verbatim_via_cli_wires_authorization(self, tool, tmp_path):
        """CLI 的 --keep-verbatim 必须真正接通授权集合（接线正确性）。"""
        tool.OUT_ROOT = tmp_path
        rc = tool.main(["--keep-verbatim", "--check"])
        assert rc == 0
        fields = tool.STRIP_MAP["classical_slices.json"]["fields"]
        assert tool.AUTHORIZED_RETENTION == {"efficacy"}, (
            "--keep-verbatim 未设置 AUTHORIZED_RETENTION，黑名单会误拦 efficacy"
        )
        assert "efficacy" not in fields, "已授权的字段不应同时出现在剥离列表中"
        assert "citation" in fields, "逐字引文 citation 在任何模式下都必须剥离"
        assert "passage" in fields, "逐字摘录 passage 在任何模式下都必须剥离"

    def test_strip_bibliographic_mode(self, tool, tmp_path):
        """最保守模式：书目元数据也一并剥离。"""
        for rel, bib in list(tool.REVIEWED_RETAINED.items()):
            tool.STRIP_MAP.setdefault(rel, {"container": "entities", "fields": []})
            tool.STRIP_MAP[rel]["fields"] = list(
                dict.fromkeys(tool.STRIP_MAP[rel]["fields"] + bib)
            )
        tool.OUT_ROOT = tmp_path
        tool.redact_classical_slices(write=True)
        slices = json.loads(
            (tmp_path / "classical_slices.json").read_text(encoding="utf-8")
        )["slices"]
        for f in ("book", "author", "dynasty", "entity", "entity_type", "property"):
            assert all(f not in s for s in slices), f"{f} 应在最保守模式下被剥离"
        # 自撰字段必须仍在，否则脱敏过度、可用性归零。
        assert all("slice_id" in s and "axis_hint" in s for s in slices)
