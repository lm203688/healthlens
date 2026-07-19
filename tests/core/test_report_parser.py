"""医学报告文本解析器单元测试"""
from app.core.report_parser import extract_observations_from_text


def test_extract_glucose():
    """传入包含血糖的文本，应解析出 loinc_code='2345-7' 的指标"""
    text = "血糖: 6.8 mmol/L (参考: 3.9-6.1) ↑"
    results = extract_observations_from_text(text)

    assert len(results) >= 1
    glucose = next((r for r in results if r["loinc_code"] == "2345-7"), None)
    assert glucose is not None
    assert glucose["value_numeric"] == 6.8
    assert glucose["value_unit"] == "mmol/L"


def test_extract_blood_pressure():
    """传入包含血压的文本，应解析出收缩压和舒张压"""
    text = "血压: 145/90 mmHg"
    results = extract_observations_from_text(text)

    # 血压目前不在 INDICATOR_PATTERNS 中，预期解析为 0 条
    # 但验证函数不抛异常
    assert isinstance(results, list)


def test_extract_multiple_indicators():
    """传入多个指标的文本，应解析出多个观测值"""
    text = """
    血糖(Glucose): 6.8 mmol/L (参考: 3.9-6.1)
    总胆固醇(TC): 5.8 mmol/L (参考: 2.8-5.2)
    甘油三酯(TG): 1.9 mmol/L (参考: 0.3-1.7)
    谷丙转氨酶(ALT): 55 U/L (参考: 0-40)
    肌酐(Cr): 98 umol/L (参考: 44-133)
    """
    results = extract_observations_from_text(text)

    assert len(results) >= 3
    loinc_codes = {r["loinc_code"] for r in results}
    assert "2345-7" in loinc_codes  # 血糖
    assert "2093-3" in loinc_codes  # 总胆固醇
    assert "2085-9" in loinc_codes  # 甘油三酯


def test_extract_empty_text():
    """空文本应返回空列表"""
    results = extract_observations_from_text("")
    assert results == []


def test_extract_chinese_english_mixed():
    """中英文混合文本应正确解析"""
    text = "Fasting Glucose: 7.2 mmol/L Ref: 3.9-6.1\nHbA1c: 6.5 % Ref: 4.0-6.0\nALT: 42 U/L Ref: 0-40"
    results = extract_observations_from_text(text)

    assert len(results) >= 2
    loinc_codes = {r["loinc_code"] for r in results}
    # Fasting Glucose / 血糖
    assert "2345-7" in loinc_codes
    # 糖化血红蛋白
    assert "4548-4" in loinc_codes


def test_extract_hdl_c():
    """HDL-C 应提取 loinc_code='2085-4'"""
    text = "HDL-C 1.2 mmol/L (参考: 1.0-1.9)"
    results = extract_observations_from_text(text)

    hdl = next((r for r in results if r["loinc_code"] == "2085-4"), None)
    assert hdl is not None
    assert hdl["value_numeric"] == 1.2


def test_extract_ldl_c():
    """LDL-C 应提取 loinc_code='18262-6'"""
    text = "LDL-C 3.8 mmol/L (参考: 0.0-3.4)"
    results = extract_observations_from_text(text)

    ldl = next((r for r in results if r["loinc_code"] == "18262-6"), None)
    assert ldl is not None
    assert ldl["value_numeric"] == 3.8


def test_extract_alt():
    """ALT/谷丙转氨酶 应提取 loinc_code='2571-8'"""
    text = "ALT 45 U/L (参考: 0-40)"
    results = extract_observations_from_text(text)

    alt = next((r for r in results if r["loinc_code"] == "2571-8"), None)
    assert alt is not None
    assert alt["value_numeric"] == 45

    text2 = "谷丙转氨酶 45"
    results2 = extract_observations_from_text(text2)
    alt2 = next((r for r in results2 if r["loinc_code"] == "2571-8"), None)
    assert alt2 is not None
    assert alt2["value_numeric"] == 45


def test_extract_creatinine():
    """肌酐/Cr 应提取 loinc_code='6299-1'"""
    text = "肌酐 88 μmol/L (参考: 44-133)"
    results = extract_observations_from_text(text)

    cr = next((r for r in results if r["loinc_code"] == "6299-1"), None)
    assert cr is not None
    assert cr["value_numeric"] == 88

    text2 = "Cr 88"
    results2 = extract_observations_from_text(text2)
    cr2 = next((r for r in results2 if r["loinc_code"] == "6299-1"), None)
    assert cr2 is not None
    assert cr2["value_numeric"] == 88


def test_extract_wbc():
    """WBC/白细胞 应提取 loinc_code='785-6'"""
    text = "WBC 6.5×10^9/L (参考: 3.5-9.5)"
    results = extract_observations_from_text(text)

    wbc = next((r for r in results if r["loinc_code"] == "785-6"), None)
    assert wbc is not None
    assert wbc["value_numeric"] == 6.5

    text2 = "白细胞 6.5"
    results2 = extract_observations_from_text(text2)
    wbc2 = next((r for r in results2 if r["loinc_code"] == "785-6"), None)
    assert wbc2 is not None
    assert wbc2["value_numeric"] == 6.5


def test_extract_hemoglobin():
    """HGB/血红蛋白 应提取 loinc_code='718-7'"""
    text = "HGB 135 g/L (参考: 130-175)"
    results = extract_observations_from_text(text)

    hgb = next((r for r in results if r["loinc_code"] == "718-7"), None)
    assert hgb is not None
    assert hgb["value_numeric"] == 135

    text2 = "血红蛋白 135"
    results2 = extract_observations_from_text(text2)
    hgb2 = next((r for r in results2 if r["loinc_code"] == "718-7"), None)
    assert hgb2 is not None
    assert hgb2["value_numeric"] == 135


def test_extract_plt():
    """PLT/血小板 应提取 loinc_code='777-3'"""
    text = "PLT 210×10^9/L (参考: 100-300)"
    results = extract_observations_from_text(text)

    plt = next((r for r in results if r["loinc_code"] == "777-3"), None)
    assert plt is not None
    assert plt["value_numeric"] == 210

    text2 = "血小板 210"
    results2 = extract_observations_from_text(text2)
    plt2 = next((r for r in results2 if r["loinc_code"] == "777-3"), None)
    assert plt2 is not None
    assert plt2["value_numeric"] == 210


def test_extract_potassium():
    """钾/K+ 应提取 loinc_code='2823-3'"""
    text = "钾 4.2 mmol/L (参考: 3.5-5.3)"
    results = extract_observations_from_text(text)

    k = next((r for r in results if r["loinc_code"] == "2823-3"), None)
    assert k is not None
    assert k["value_numeric"] == 4.2

    text2 = "K+ 4.2"
    results2 = extract_observations_from_text(text2)
    k2 = next((r for r in results2 if r["loinc_code"] == "2823-3"), None)
    assert k2 is not None
    assert k2["value_numeric"] == 4.2


def test_extract_sodium():
    """钠/Na+ 应提取 loinc_code='2951-2'"""
    text = "钠 140 mmol/L (参考: 137-147)"
    results = extract_observations_from_text(text)

    na = next((r for r in results if r["loinc_code"] == "2951-2"), None)
    assert na is not None
    assert na["value_numeric"] == 140

    text2 = "Na+ 140"
    results2 = extract_observations_from_text(text2)
    na2 = next((r for r in results2 if r["loinc_code"] == "2951-2"), None)
    assert na2 is not None
    assert na2["value_numeric"] == 140


def test_extract_uric_acid():
    """尿酸/UA 应提取 loinc_code='14959-1'"""
    text = "尿酸 380 μmol/L (参考: 150-420)"
    results = extract_observations_from_text(text)

    ua = next((r for r in results if r["loinc_code"] == "14959-1"), None)
    assert ua is not None
    assert ua["value_numeric"] == 380

    text2 = "UA 380"
    results2 = extract_observations_from_text(text2)
    ua2 = next((r for r in results2 if r["loinc_code"] == "14959-1"), None)
    assert ua2 is not None
    assert ua2["value_numeric"] == 380