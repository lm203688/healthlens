"""管线健壮性回归测试。

覆盖曾出现的"虚假成功"类缺陷，防止复发：
- 阶段 ID 与实际脚本目录语义错位
- dry_run 形同虚设（恒返回 skipped，无法巡检）
- 阶段输出被截断到 500 字符，截碎结构化 JSON 报告
- 弃用别名静默执行到语义不符的阶段
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from healthlens_agent.pipeline_registry import (  # noqa: E402
    DATA_PHASE_ID_MAP,
    DEPRECATED_ALIASES,
    resolve_phase_id,
)


def test_phase_ids_match_script_directories():
    """阶段 ID 必须与 auto-pipeline/scripts 目录语义一致。

    此前 ID 用旧数据管线命名（clean/sync/...），与目录（analyze/decide/...）
    错位，导致调用 'constitution' 实际执行 phase_5_test。
    """
    from healthlens_agent.auto_pipeline import PHASES

    for phase_id, number in DATA_PHASE_ID_MAP.items():
        assert PHASES[number] == f"phase_{number}_{phase_id}", (
            f"阶段 ID '{phase_id}' 与目录 '{PHASES[number]}' 语义不一致"
        )


def test_deprecated_aliases_resolve_with_warning():
    """旧别名必须解析到正确阶段，并带弃用警告，不能静默执行。"""
    for old_id, expected in DEPRECATED_ALIASES.items():
        canonical, warning = resolve_phase_id(old_id)
        assert canonical == expected
        assert warning is not None
        assert old_id in warning
        assert expected in warning


def test_canonical_ids_have_no_warning():
    """规范 ID 不应产生弃用警告。"""
    for phase_id in DATA_PHASE_ID_MAP:
        canonical, warning = resolve_phase_id(phase_id)
        assert canonical == phase_id
        assert warning is None


def test_output_limit_preserves_json_reports():
    """输出保留上限必须足够容纳结构化 JSON 报告。

    此前固定截断到最后 500 字符，截碎了 phase_7/8 的 JSON 报告，
    导致上层 json.loads 失败。
    """
    from healthlens_agent.auto_pipeline import OUTPUT_LIMIT, _truncate_output

    assert OUTPUT_LIMIT > 500, "上限过小会截碎 JSON 报告"
    payload = "x" * 5000
    assert _truncate_output(payload) == payload, "未超限不应截断"
    assert _truncate_output(None) == ""


def test_truncate_annotates_when_exceeded():
    """超限时截断并标注，避免静默丢失信息。"""
    from healthlens_agent.auto_pipeline import OUTPUT_LIMIT, _truncate_output

    payload = "y" * (OUTPUT_LIMIT + 100)
    result = _truncate_output(payload)
    assert len(result) < len(payload)
    assert "截断" in result


def test_preflight_detects_syntax_error(tmp_path, monkeypatch):
    """静态预检必须能检出脚本语法错误。"""
    import healthlens_agent.auto_pipeline as ap

    scripts_dir = tmp_path / "scripts"
    phase_dir = scripts_dir / "phase_1_collect"
    phase_dir.mkdir(parents=True)
    (phase_dir / "run.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    monkeypatch.setattr(ap, "AUTO_PIPELINE_DIR", scripts_dir)

    result = ap.preflight(1)
    assert result["ok"] is False
    assert any("语法错误" in e for e in result["errors"])


def test_preflight_detects_missing_script(tmp_path, monkeypatch):
    """缺少 run.py 必须被预检判为失败。"""
    import healthlens_agent.auto_pipeline as ap

    monkeypatch.setattr(ap, "AUTO_PIPELINE_DIR", tmp_path / "nonexistent")

    result = ap.preflight(1)
    assert result["ok"] is False
    assert result["errors"]


def test_dry_run_performs_real_preflight():
    """dry_run 必须执行真实预检，而非恒返回 skipped。

    此前 dry_run 直接 return skipped，完全无法用于健康巡检。
    """
    from healthlens_agent.auto_pipeline import run_phase

    result = run_phase(1, dry_run=True)
    assert result["status"] != "skipped", "dry_run 不应再形同虚设"
    assert result["status"] == "ok"
    assert result.get("dry_run") is True
    assert "preflight" in result
    assert result["preflight"]["ok"] is True


def test_all_phases_pass_preflight():
    """全部 8 个阶段的脚本都应通过静态预检。"""
    from healthlens_agent.auto_pipeline import PHASES, preflight

    for phase_id in PHASES:
        result = preflight(phase_id)
        assert result["ok"] is True, f"阶段 {phase_id} 预检失败: {result['errors']}"
