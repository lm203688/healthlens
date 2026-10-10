"""PII 识别与脱敏测试（唯一实现：app/utils/pii_sanitizer.py）

重点覆盖：
  - 校验位判定（身份证 GB 11643 / 银行卡 Luhn）—— 这是相对旧版纯正则的核心改进
  - 误报控制：订单号、日期串不应被当成身份证/银行卡
  - 出站脱敏：sanitize 后原文中的 PII 必须消失
  - 审计委托：runtime_audit.scan_sensitive 与 pii_sanitizer 保持一致
"""
import pytest

from app.utils.pii_sanitizer import (
    backend_info,
    contains_pii,
    detect_pii,
    detect_pii_fields,
    find_pii,
    sanitize,
    sanitize_deep,
)

# 有效身份证（校验位正确）
VALID_ID = "11010519491231002X"
# 校验位被改坏的同构串
INVALID_ID = "110105194912310021"

# 通过 Luhn 的测试卡号（业界通用测试号）
VALID_CARD = "4111111111111111"
INVALID_CARD = "4111111111111112"


class TestRuleLayer:
    def test_cn_mobile(self):
        assert "phone" in detect_pii("我的手机是 13812345678，方便联系")

    def test_mobile_not_matched_inside_longer_digit_run(self):
        assert "phone" not in detect_pii("订单号 11381234567890")

    def test_email(self):
        assert "email" in detect_pii("联系 zhang.san+hl@example.com.cn 谢谢")

    def test_id_card_valid_checksum(self):
        assert "id_card" in detect_pii(f"身份证 {VALID_ID}")

    def test_id_card_bad_checksum_rejected(self):
        """校验位不对的 18 位数字不应被当成身份证（旧版正则会误报）。"""
        assert "id_card" not in detect_pii(f"参考编号 {INVALID_ID}")

    def test_bank_card_luhn(self):
        assert "bank_card" in detect_pii(f"卡号 {VALID_CARD}")

    def test_bank_card_bad_luhn_rejected(self):
        assert "bank_card" not in detect_pii(f"流水号 {INVALID_CARD}")

    def test_passport(self):
        assert "passport" in detect_pii("护照号 E12345678")

    def test_wechat_wxid(self):
        assert "wechat" in detect_pii("微信 wxid_ab12cd34ef 加我")

    def test_qq_with_label(self):
        assert "qq" in detect_pii("QQ：123456789")

    def test_bare_number_is_not_qq(self):
        """无标签的裸数字不识别为 QQ，避免误伤普通数值。"""
        assert "qq" not in detect_pii("体重 123456 克")

    def test_cn_plate(self):
        assert "cn_plate" in detect_pii("车牌 京A12345")


class TestSanitize:
    def test_all_pii_removed(self):
        raw = f"我叫张三，手机 13812345678，身份证 {VALID_ID}，邮箱 a@b.com"
        out = sanitize(raw)
        assert "13812345678" not in out
        assert VALID_ID not in out
        assert "a@b.com" not in out
        assert "[PHONE]" in out and "[ID_CARD]" in out and "[EMAIL]" in out

    def test_clean_text_unchanged(self):
        raw = "今天睡眠质量不错，想了解黄芪的食养用法。"
        assert sanitize(raw) == raw

    def test_non_str_passthrough(self):
        assert sanitize(None) is None
        assert sanitize(123) == 123

    def test_idempotent(self):
        raw = "手机 13812345678"
        once = sanitize(raw)
        assert sanitize(once) == once

    def test_contains_pii(self):
        assert contains_pii("身份证 " + VALID_ID) is True
        assert contains_pii("没有敏感信息") is False


class TestSanitizeDeep:
    def test_nested(self):
        data = {
            "user": {"phone": "13812345678", "notes": ["邮箱 a@b.com", "正常文本"]},
            "count": 3,
        }
        out = sanitize_deep(data)
        assert out["user"]["phone"] == "[PHONE]"
        assert out["user"]["notes"][0] == "邮箱 [EMAIL]"
        assert out["user"]["notes"][1] == "正常文本"
        assert out["count"] == 3
        # 原对象不被修改
        assert data["user"]["phone"] == "13812345678"

    def test_tuple_preserved(self):
        out = sanitize_deep(("13812345678",))
        assert isinstance(out, tuple)
        assert out[0] == "[PHONE]"


class TestFindPii:
    def test_offsets_and_text(self):
        text = "手机 13812345678 结束"
        hits = find_pii(text)
        assert hits, "应至少命中一条"
        h = hits[0]
        assert text[h["start"]:h["end"]] == h["text"]

    def test_no_overlapping_hits(self):
        hits = find_pii("身份证 " + VALID_ID)
        spans = [(h["start"], h["end"]) for h in hits]
        for i in range(1, len(spans)):
            assert spans[i][0] >= spans[i - 1][1], "命中区间不应重叠"


class TestFieldHeuristic:
    def test_detect_fields(self):
        found = detect_pii_fields({"user_name": "x", "phone": "y", "age": 1})
        assert "user_name" in found
        assert "phone" in found
        assert "age" not in found


class TestAuditDelegation:
    """runtime_audit 必须复用同一实现，不能再各留一套正则。"""

    def test_scan_sensitive_delegates(self):
        from app.services.runtime_audit import scan_sensitive

        assert scan_sensitive("手机 13812345678") == detect_pii("手机 13812345678")

    def test_scan_sensitive_empty(self):
        from app.services.runtime_audit import scan_sensitive

        assert scan_sensitive("") == []


class TestBackendInfo:
    def test_shape(self):
        info = backend_info()
        assert info["rule_layer"] is True
        assert isinstance(info["rule_types"], list) and info["rule_types"]
        assert isinstance(info["presidio_available"], bool)
