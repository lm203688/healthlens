"""国标 2.0 闸门测试

覆盖：
- 配置加载（正常/文件缺失/格式错误）
- 条款检查（mandatory 通过/不通过, optional 通过/不通过）
- 文档检查（完整文档/缺失章节/空文档）
- 总分计算（mandatory 扣分/optional 扣分/满分/0 分）
- fail-closed（闸门异常时返回 passed=False）
- API 端点（standards/check/clauses/compliance-report）
- 边界值（空文档/超长文档/特殊字符）
- 免责声明存在性
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.core.compliance import gb2001
from app.core.compliance.gb2001 import (
    ClauseResult,
    NationalStandardError,
    StandardGateResult,
    check_clause,
    check_document,
    check_document_on_file,
    get_global_disclaimer,
    get_standard,
    load_standards,
    reload_config,
)
from app.lib.national_standard_gate import (
    build_compliance_report,
    get_standard_detail,
    list_available_standards,
    list_clauses,
    run_national_standard_gate,
)


# ── 测试夹具 ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reload_config():
    """每个测试前清空缓存，避免相互污染。"""
    reload_config()
    yield
    reload_config()


def _make_full_doc() -> str:
    """构造一份完整覆盖所有 9 条款的文档。"""
    lines = [
        "# 健康管理服务文档",
        "",
        "## 4.1 范围",
        "本文档适用于健康管理服务的适用范围声明。",
        "",
        "## 5.1 目的和范围",
        "明确健康管理服务的目的和适用边界。",
        "",
        "## 5.2 规范性引用文件",
        "本文件引用 GB/T 19001 和 ISO 14001。",
        "",
        "## 5.3 术语和定义",
        "术语定义准确一致，参考国家标准。",
        "",
        "## 6 总则",
        "本文件规定健康管理服务的总则性要求。",
        "",
        "## 7 管理体系要求",
        "本文件规定健康管理服务的管理体系要求。",
        "",
        "## 8 运行要求",
        "本文件规定健康管理服务的运行要求。",
        "",
        "## 9 绩效评价",
        "本文件规定健康管理服务的绩效评价方法。",
        "",
        "## 10 改进",
        "本文件规定健康管理服务的持续改进机制。",
        "",
        "免责声明：本文件为健康管理服务文档提供结构化参考，"
        "非医疗诊断标准，不构成法律或监管合规声明。",
    ]
    return "\n".join(lines)


# ── 1. 配置加载 ─────────────────────────────────────────────────

class TestLoadStandards:
    def test_load_standards_returns_list(self):
        standards = load_standards()
        assert isinstance(standards, list)
        assert len(standards) >= 1

    def test_first_standard_id(self):
        standards = load_standards()
        assert standards[0]["id"] == "GB/T 20001.10-2014"

    def test_first_standard_has_clauses(self):
        standards = load_standards()
        assert isinstance(standards[0]["clauses"], list)
        assert len(standards[0]["clauses"]) == 9

    def test_get_standard_returns_dict(self):
        s = get_standard("GB/T 20001.10-2014")
        assert s["id"] == "GB/T 20001.10-2014"
        assert "clauses" in s
        assert "disclaimer" in s

    def test_get_standard_unknown_raises(self):
        with pytest.raises(NationalStandardError):
            get_standard("GB/T 99999.0-9999")

    def test_missing_config_fails_closed(self, tmp_path, monkeypatch):
        """配置缺失 → 抛 NationalStandardError（fail-closed）。"""
        missing = tmp_path / "not_exist.json"
        monkeypatch.setattr(gb2001, "CONFIG_PATH", missing)
        reload_config()
        with pytest.raises(NationalStandardError):
            load_standards()

    def test_malformed_json_fails_closed(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(gb2001, "CONFIG_PATH", bad)
        reload_config()
        with pytest.raises(NationalStandardError):
            load_standards()

    def test_empty_standards_raises(self, tmp_path, monkeypatch):
        bad = tmp_path / "empty.json"
        bad.write_text('{"standards": []}', encoding="utf-8")
        monkeypatch.setattr(gb2001, "CONFIG_PATH", bad)
        reload_config()
        with pytest.raises(NationalStandardError):
            load_standards()

    def test_missing_standards_key_raises(self, tmp_path, monkeypatch):
        bad = tmp_path / "no_standards.json"
        bad.write_text('{"version": "v1.0"}', encoding="utf-8")
        monkeypatch.setattr(gb2001, "CONFIG_PATH", bad)
        reload_config()
        with pytest.raises(NationalStandardError):
            load_standards()


# ── 2. 条款检查 ─────────────────────────────────────────────────

class TestCheckClause:
    def test_mandatory_clause_pass(self):
        clause = {
            "id": "4.1",
            "title": "范围",
            "requirement": "适用范围声明",
            "priority": "mandatory",
            "check_method": "text_presence",
        }
        r = check_clause("本文件适用范围声明覆盖健康管理服务。", clause)
        assert r.passed is True
        assert r.priority == "mandatory"

    def test_mandatory_clause_fail(self):
        clause = {
            "id": "5.2",
            "title": "规范性引用文件",
            "requirement": "引用文件完整且有效",
            "priority": "mandatory",
            "check_method": "text_presence",
        }
        r = check_clause("这是一段完全无关的文字。", clause)
        assert r.passed is False

    def test_optional_clause_pass(self):
        clause = {
            "id": "9",
            "title": "绩效评价",
            "requirement": "绩效评价方法",
            "priority": "optional",
            "check_method": "text_presence",
        }
        r = check_clause("绩效评价方法包括用户满意度反馈。", clause)
        assert r.passed is True
        assert r.priority == "optional"

    def test_optional_clause_fail(self):
        clause = {
            "id": "10.5",
            "title": "纠正措施",
            "requirement": "纠正措施闭环",
            "priority": "optional",
            "check_method": "text_presence",
        }
        r = check_clause("这是一段无关的文字。", clause)
        assert r.passed is False

    def test_empty_doc_fails(self):
        clause = {
            "id": "4.1",
            "title": "范围",
            "requirement": "适用范围声明",
            "priority": "mandatory",
            "check_method": "text_presence",
        }
        r = check_clause("", clause)
        assert r.passed is False
        assert "空" in r.message or "empty" in r.message

    def test_clause_id_match_passes(self):
        """条款 ID 出现在文档中即视为通过。"""
        clause = {
            "id": "7.1",
            "title": "领导作用",
            "requirement": "领导作用",
            "priority": "mandatory",
            "check_method": "text_presence",
        }
        r = check_clause("7.1 本章节说明领导作用。", clause)
        assert r.passed is True

    def test_unknown_check_method_fails_closed(self):
        clause = {
            "id": "6",
            "title": "总则",
            "requirement": "总则",
            "priority": "mandatory",
            "check_method": "unknown_method",
        }
        r = check_clause("总则", clause)
        assert r.passed is False
        assert "未知" in r.message

    def test_structure_check_pass(self):
        clause = {
            "id": "6",
            "title": "总则",
            "requirement": "总则",
            "priority": "mandatory",
            "check_method": "structure_check",
        }
        r = check_clause("# 6 总则\n\n本文件总则。", clause)
        assert r.passed is True

    def test_reference_check_pass(self):
        clause = {
            "id": "5.2",
            "title": "规范性引用文件",
            "requirement": "引用文件完整且有效",
            "priority": "mandatory",
            "check_method": "reference_check",
        }
        r = check_clause("本文件引用 GB/T 19001-2016 和 ISO 14001。", clause)
        assert r.passed is True

    def test_reference_check_fail(self):
        clause = {
            "id": "5.2",
            "title": "规范性引用文件",
            "requirement": "引用文件完整且有效",
            "priority": "mandatory",
            "check_method": "reference_check",
        }
        r = check_clause("本文件没有任何引用标识。", clause)
        assert r.passed is False


# ── 3. 文档检查（check_document） ──────────────────────────────

class TestCheckDocument:
    def test_full_doc_passes(self):
        doc = _make_full_doc()
        result = check_document(doc)
        assert result.passed is True
        assert result.score == 100
        assert result.mandatory_passed == result.mandatory_total
        assert result.optional_passed == result.optional_total

    def test_empty_doc_fails(self):
        result = check_document("")
        assert result.passed is False
        assert result.score == 0
        assert result.critical_issues

    def test_missing_optional_only_passes(self):
        """缺少 optional 条款：passed 仍为 True（只要 mandatory 齐全）。"""
        doc = _make_full_doc()
        # 去掉 optional 条款（9、10）
        for token in ("9 绩效评价", "绩效评价", "10 改进", "持续改进"):
            doc = doc.replace(token, "XX")
        result = check_document(doc)
        # optional 缺失不影响 passed
        assert result.passed is True
        assert result.optional_passed < result.optional_total
        assert result.optional_total >= 2

    def test_missing_mandatory_fails(self):
        doc = _make_full_doc()
        # 破坏 mandatory 条款 5.2 的 ID 与关键词匹配
        doc = doc.replace("5.2", "X.X")
        doc = doc.replace("规范性引用文件", "YY")
        doc = doc.replace("引用文件完整且有效", "YY")
        result = check_document(doc)
        assert result.passed is False
        assert result.mandatory_passed < result.mandatory_total

    def test_unknown_standard_id_fail_closed(self):
        result = check_document("任意文本", standard_id="GB/T 99999.0-9999")
        assert result.passed is False
        assert result.score == 0
        assert any("gate_config_error" in s for s in result.critical_issues)

    def test_result_has_disclaimer(self):
        result = check_document(_make_full_doc())
        assert "不构成" in result.disclaimer

    def test_result_shape(self):
        result = check_document(_make_full_doc())
        assert result.standard_id == "GB/T 20001.10-2014"
        assert result.standard_title
        assert isinstance(result.clause_results, list)
        assert len(result.clause_results) == 9


# ── 4. 总分计算 ─────────────────────────────────────────────────

class TestScoreCalculation:
    def test_full_score(self):
        result = check_document(_make_full_doc())
        assert result.score == 100

    def test_mandatory_penalty_is_20(self):
        doc = _make_full_doc()
        doc = doc.replace("5.2", "X.X")
        doc = doc.replace("规范性引用文件", "YYY")
        doc = doc.replace("引用文件完整且有效", "YYY")
        result = check_document(doc)
        # 1 个 mandatory 不通过 → -20
        assert result.score == 80

    def test_optional_penalty_is_5(self):
        doc = _make_full_doc()
        doc = doc.replace("10 改进", "XX")
        doc = doc.replace("持续改进机制", "XX")
        result = check_document(doc)
        # 1 个 optional 不通过 → -5
        assert result.score == 95

    def test_score_clamped_to_zero(self):
        """空文档 → 0 分（不出现负数）。"""
        result = check_document("")
        assert result.score == 0
        assert result.score >= 0

    def test_all_optional_missing(self):
        """两个 optional 都缺失：注意 clause id 是 '9'/'10'，
        单字符匹配可能被 GB/T 19001 里的数字误命中，
        因此需要把包含这些数字的引用行一并删除。
        """
        doc = _make_full_doc()
        for token in ("9 绩效评价", "绩效评价方法", "10 改进", "持续改进机制",
                      "GB/T 19001", "ISO 14001", "GB/T 1"):
            doc = doc.replace(token, "ZZ")
        result = check_document(doc)
        # 2 个 optional 缺失 → -10
        assert result.score == 90


# ── 5. fail-closed ─────────────────────────────────────────────

class TestFailClosed:
    def test_gate_internal_error_returns_failed(self):
        """check_document 内部异常 → 返回 passed=False（不抛出）。"""
        with patch.object(
            gb2001, "get_standard", side_effect=RuntimeError("boom")
        ):
            result = check_document("任意文本")
        assert result.passed is False
        assert result.score == 0
        assert any("gate_internal_error" in s for s in result.critical_issues)

    def test_config_missing_returns_failed_not_raise(self, tmp_path, monkeypatch):
        """配置文件缺失 → check_document 返回 passed=False 而不是抛异常。"""
        missing = tmp_path / "not_exist.json"
        monkeypatch.setattr(gb2001, "CONFIG_PATH", missing)
        reload_config()
        result = check_document("任意文本")
        assert result.passed is False
        assert result.score == 0
        assert result.critical_issues

    def test_run_national_standard_gate_catches_exception(self):
        """run_national_standard_gate 顶层异常 → success=False, passed=False。"""
        import asyncio
        from app.lib import national_standard_gate as g

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        with patch.object(g, "check_document", side_effect=_boom):
            result = asyncio.run(run_national_standard_gate("任意文本"))
        assert result["success"] is False
        assert result["passed"] is False
        assert result["not_clinical"] is True
        assert "disclaimer" in result and result["disclaimer"]


# ── 6. 文件入口 ─────────────────────────────────────────────────

class TestFileEntry:
    def test_check_document_on_file(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text(_make_full_doc(), encoding="utf-8")
        result = check_document_on_file(f)
        assert result.passed is True
        assert result.score == 100

    def test_check_document_on_missing_file(self, tmp_path):
        with pytest.raises(NationalStandardError):
            check_document_on_file(tmp_path / "nope.md")

    def test_check_document_on_file_empty(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        result = check_document_on_file(f)
        assert result.passed is False


# ── 7. 边界值 ───────────────────────────────────────────────────

class TestEdgeCases:
    def test_very_long_doc(self):
        doc = _make_full_doc() + ("\n" + "无关填充文字。" * 5000)
        result = check_document(doc)
        assert result.passed is True
        assert result.score == 100

    def test_special_chars(self):
        doc = _make_full_doc() + "\n" + "<script>alert(1)</script>" * 10
        result = check_document(doc)
        assert result.passed is True

    def test_unicode_special_chars(self):
        doc = _make_full_doc() + "\n" + "αβγδ🎯" * 5
        result = check_document(doc)
        assert result.passed is True

    def test_case_insensitive_match(self):
        doc = "范围 5.1 目的和范围 GB/T 规范性引用文件 术语和定义 6 总则 管理体系要求 8 运行要求 9 绩效评价 10 改进"
        result = check_document(doc)
        assert result.passed is True


# ── 8. 免责声明 ─────────────────────────────────────────────────

class TestDisclaimer:
    def test_global_disclaimer_exists(self):
        d = get_global_disclaimer()
        assert "不构成" in d
        assert "健康管理" in d or "结构化参考" in d

    def test_standard_disclaimer_exists(self):
        s = get_standard("GB/T 20001.10-2014")
        assert "不构成" in s["disclaimer"]

    def test_list_available_standards_disclaimer(self):
        stds = list_available_standards()
        assert stds
        for s in stds:
            assert "disclaimer" in s

    def test_run_gate_response_has_disclaimer(self):
        import asyncio
        result = asyncio.run(run_national_standard_gate(_make_full_doc()))
        assert "disclaimer" in result
        assert "不构成" in result["disclaimer"]

    def test_build_compliance_report_has_disclaimer(self):
        report = build_compliance_report()
        assert "disclaimer" in report
        assert "not_clinical" in report and report["not_clinical"] is True

    def test_result_disclaimer_never_empty(self):
        """所有 check_document 结果都带 disclaimer（fail-closed 也带）。"""
        r1 = check_document(_make_full_doc())
        r2 = check_document("")
        r3 = check_document("任意", standard_id="GB/T 99999.0-9999")
        for r in (r1, r2, r3):
            assert r.disclaimer


# ── 9. lib 层接口 ───────────────────────────────────────────────

class TestLibIntegration:
    def test_list_available_standards_shape(self):
        stds = list_available_standards()
        assert isinstance(stds, list) and stds
        first = stds[0]
        assert first["id"] == "GB/T 20001.10-2014"
        assert "title" in first
        assert "clause_count" in first
        assert first["clause_count"] == 9
        assert first["mandatory_count"] == 7
        assert first["optional_count"] == 2

    def test_get_standard_detail_shape(self):
        detail = get_standard_detail("GB/T 20001.10-2014")
        assert detail["id"] == "GB/T 20001.10-2014"
        assert isinstance(detail["clauses"], list)
        assert len(detail["clauses"]) == 9

    def test_list_clauses(self):
        clauses = list_clauses("GB/T 20001.10-2014")
        assert isinstance(clauses, list)
        assert len(clauses) == 9
        assert clauses[0]["id"] == "4.1"

    def test_run_gate_response_shape(self):
        import asyncio
        result = asyncio.run(run_national_standard_gate(_make_full_doc()))
        for k in (
            "success", "not_clinical", "standard_id", "passed", "score",
            "mandatory_passed", "mandatory_total",
            "optional_passed", "optional_total",
            "clause_results", "critical_issues", "warnings", "disclaimer",
        ):
            assert k in result, f"missing key {k}"
        assert result["success"] is True
        assert result["not_clinical"] is True
        assert result["passed"] is True
        assert result["score"] == 100
        assert len(result["clause_results"]) == 9

    def test_run_gate_empty_doc(self):
        import asyncio
        result = asyncio.run(run_national_standard_gate(""))
        assert result["success"] is True
        assert result["passed"] is False


# ── 10. API 端点 ────────────────────────────────────────────────

@pytest_asyncio.fixture
async def authed_client(client, test_user_token, db_session):
    """提供一个已登录的客户端：为 conftest 的 fake sub 落一条 User 记录。"""
    from app.models.user import User
    import uuid

    payload_sub = str(uuid.uuid4())
    # 与 test_user_token 使用同一 sub
    user = User(
        id=payload_sub,
        email=f"ns_{payload_sub[:8]}@healthlens.com",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {test_user_token}"}
    # 重新用真实 sub 签发一个 token
    from app.utils.security import create_access_token
    token = create_access_token({"sub": payload_sub, "email": user.email})
    headers["Authorization"] = f"Bearer {token}"
    return client, headers


@pytest.mark.asyncio
async def test_api_list_standards_public(client):
    r = await client.get("/api/v1/national-standard/standards")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["not_clinical"] is True
    assert isinstance(body["data"], list)
    assert body["data"][0]["id"] == "GB/T 20001.10-2014"
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_api_get_standard_detail_public(client):
    r = await client.get("/api/v1/national-standard/standards/GB/T%2020001.10-2014")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["id"] == "GB/T 20001.10-2014"
    assert isinstance(body["data"]["clauses"], list)


@pytest.mark.asyncio
async def test_api_get_unknown_standard_404(client):
    r = await client.get("/api/v1/national-standard/standards/GB/T%2099999.0-9999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_check_requires_auth(client):
    r = await client.post(
        "/api/v1/national-standard/check",
        json={"doc_text": _make_full_doc()},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_api_check_success(client, test_user_token, db_session):
    from app.models.user import User
    import uuid
    from app.utils.security import create_access_token

    uid = str(uuid.uuid4())
    user = User(id=uid, email=f"ns_{uid[:8]}@healthlens.com", password_hash="x", role="user")
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": uid, "email": user.email})

    r = await client.post(
        "/api/v1/national-standard/check",
        json={"doc_text": _make_full_doc()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["passed"] is True
    assert body["score"] == 100
    assert body["not_clinical"] is True


@pytest.mark.asyncio
async def test_api_check_failing_doc(client, test_user_token, db_session):
    from app.models.user import User
    import uuid
    from app.utils.security import create_access_token

    uid = str(uuid.uuid4())
    user = User(id=uid, email=f"ns_{uid[:8]}@healthlens.com", password_hash="x", role="user")
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": uid, "email": user.email})

    r = await client.post(
        "/api/v1/national-standard/check",
        json={"doc_text": "随便一段无结构的文字。"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] is False
    assert body["critical_issues"]


@pytest.mark.asyncio
async def test_api_list_clauses_public(client):
    r = await client.get("/api/v1/national-standard/clauses/GB/T%2020001.10-2014")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 9


@pytest.mark.asyncio
async def test_api_list_clauses_unknown_404(client):
    r = await client.get("/api/v1/national-standard/clauses/GB/T%2099999.0-9999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_compliance_report_requires_auth(client):
    r = await client.get("/api/v1/national-standard/compliance-report")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_api_compliance_report(client, test_user_token, db_session):
    from app.models.user import User
    import uuid
    from app.utils.security import create_access_token

    uid = str(uuid.uuid4())
    user = User(id=uid, email=f"ns_{uid[:8]}@healthlens.com", password_hash="x", role="user")
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": uid, "email": user.email})

    r = await client.get(
        "/api/v1/national-standard/compliance-report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["not_clinical"] is True
    assert "disclaimer" in body["data"]
