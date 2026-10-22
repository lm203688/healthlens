"""医学报告文本解析器
从 OCR 提取的原始文本中识别检验指标名称和数值
支持中英文混合匹配
"""
import re
from loguru import logger


# 指标名称匹配规则
# key: 正则模式（匹配指标名）, value: {loinc_code, loinc_name, unit, ref_low, ref_high}
INDICATOR_PATTERNS = [
    # 血糖
    {"pattern": r"(?:空腹)?血糖|血糖\(Glucose\)|GLU|FPG|Fasting Glucose",
     "loinc_code": "2345-7", "loinc_name": "血糖(Glucose)", "unit": "mmol/L", "ref_low": 3.9, "ref_high": 6.1},
    {"pattern": r"糖化血红蛋白|HbA1c|糖化|Glycated Hemoglobin",
     "loinc_code": "4548-4", "loinc_name": "糖化血红蛋白(HbA1c)", "unit": "%", "ref_low": 4.0, "ref_high": 6.0},
    {"pattern": r"餐后血糖|餐后两小时血糖|OGTT|2hPG",
     "loinc_code": "2345-7", "loinc_name": "餐后血糖(Postprandial Glucose)", "unit": "mmol/L", "ref_low": 3.9, "ref_high": 7.8},

    # 血脂
    {"pattern": r"总胆固醇|Total Cholesterol|TC|CHOL",
     "loinc_code": "2093-3", "loinc_name": "总胆固醇(Cholesterol)", "unit": "mmol/L", "ref_low": 2.8, "ref_high": 5.2},
    {"pattern": r"甘油三酯|Triglycerides?|TG",
     "loinc_code": "2085-9", "loinc_name": "甘油三酯(Triglycerides)", "unit": "mmol/L", "ref_low": 0.3, "ref_high": 1.7},
    {"pattern": r"(?:高密度|HDL).*?胆固醇|HDL[- ]?C",
     "loinc_code": "2085-4", "loinc_name": "高密度脂蛋白胆固醇(HDL-C)", "unit": "mmol/L", "ref_low": 1.0, "ref_high": 1.9},
    {"pattern": r"(?:低密度|LDL).*?胆固醇|LDL[- ]?C",
     "loinc_code": "18262-6", "loinc_name": "低密度脂蛋白胆固醇(LDL-C)", "unit": "mmol/L", "ref_low": 0.0, "ref_high": 3.4},

    # 肝功能
    {"pattern": r"(?:谷丙转氨酶|ALT|SGPT|丙氨酸氨基转移酶)",
     "loinc_code": "2571-8", "loinc_name": "谷丙转氨酶(ALT)", "unit": "U/L", "ref_low": 0, "ref_high": 40},
    {"pattern": r"(?:谷草转氨酶|AST|SGOT|天门冬氨酸氨基转移酶)",
     "loinc_code": "1743-4", "loinc_name": "谷草转氨酶(AST)", "unit": "U/L", "ref_low": 0, "ref_high": 40},
    {"pattern": r"(?:γ-谷氨酰转肽酶|GGT|γ-GT|r-谷氨酰转肽酶)",
     "loinc_code": "2324-2", "loinc_name": "γ-谷氨酰转肽酶(GGT)", "unit": "U/L", "ref_low": 0, "ref_high": 50},
    {"pattern": r"(?:碱性磷酸酶|ALP|ALKP)",
     "loinc_code": "6768-6", "loinc_name": "碱性磷酸酶(ALP)", "unit": "U/L", "ref_low": 35, "ref_high": 105},
    {"pattern": r"(?:总胆红素|Total Bilirubin|TBIL|T-BIL)",
     "loinc_code": "1975-2", "loinc_name": "总胆红素(TBIL)", "unit": "umol/L", "ref_low": 3.4, "ref_high": 17.1},

    # 肾功能
    {"pattern": r"(?:肌酐|Creatinine|Cr|CREA)(?!.*清除)",
     "loinc_code": "6299-1", "loinc_name": "肌酐(Creatinine)", "unit": "umol/L", "ref_low": 44, "ref_high": 133},
    {"pattern": r"(?:尿素氮|BUN|Blood Urea Nitrogen|尿素)",
     "loinc_code": "3094-0", "loinc_name": "尿素氮(BUN)", "unit": "mmol/L", "ref_low": 1.7, "ref_high": 8.3},
    {"pattern": r"(?:尿酸|Uric Acid|UA|URIC)",
     "loinc_code": "14959-1", "loinc_name": "尿酸(Uric Acid)", "unit": "umol/L", "ref_low": 150, "ref_high": 420},

    # 血常规
    {"pattern": r"(?:白细胞|White Blood Cell|WBC|LEUKO)(?!.*计)",
     "loinc_code": "785-6", "loinc_name": "白细胞计数(WBC)", "unit": "10*9/L", "ref_low": 3.5, "ref_high": 9.5},
    {"pattern": r"(?:红细胞|Red Blood Cell|RBC|ERY)(?!.*计)",
     "loinc_code": "789-8", "loinc_name": "红细胞计数(RBC)", "unit": "10*12/L", "ref_low": 4.0, "ref_high": 5.5},
    {"pattern": r"(?:血红蛋白|Hemoglobin|HGB|Hb|HB)",
     "loinc_code": "718-7", "loinc_name": "血红蛋白(Hemoglobin)", "unit": "g/L", "ref_low": 130, "ref_high": 175},
    {"pattern": r"(?:血小板|Platelet|PLT|PLATE)",
     "loinc_code": "777-3", "loinc_name": "血小板计数(PLT)", "unit": "10*9/L", "ref_low": 100, "ref_high": 300},

    # 电解质
    {"pattern": r"(?:钾|Potassium|K\+|K )(?!\w)",
     "loinc_code": "2823-3", "loinc_name": "钾(K+)", "unit": "mmol/L", "ref_low": 3.5, "ref_high": 5.3},
    {"pattern": r"(?:钠|Sodium|Na\+|Na )(?!\w)",
     "loinc_code": "2951-2", "loinc_name": "钠(Na+)", "unit": "mmol/L", "ref_low": 137, "ref_high": 147},
    {"pattern": r"(?:钙|Calcium|Ca[2+]?|Ca )(?!\w)",
     "loinc_code": "17861-6", "loinc_name": "钙(Ca2+)", "unit": "mmol/L", "ref_low": 2.11, "ref_high": 2.52},
]

# 数值提取正则: 匹配指标名附近的数字（包括小数）
VALUE_PATTERN = re.compile(
    r'(?:[-—:]?\s*'           # 可能的分隔符
    r'(?:[:>＝]\s*)?'         # 可能的等号/冒号
    r'(\d+\.?\d*)'            # 数值
    r'\s*'                     # 空格
    r'(?:mmol/L|umol/L|U/L|g/L|10\*9/L|10\*12/L|%|10\^9/L|10\^12/L|fL|pg|pmol/L)?)'  # 可选单位
)


def extract_observations_from_text(text: str) -> list[dict]:
    """从 OCR 文本中提取结构化指标数据"""
    observations = []
    seen_codes = set()

    for indicator in INDICATOR_PATTERNS:
        pattern = indicator["pattern"]
        matches = list(re.finditer(pattern, text, re.IGNORECASE))

        if not matches:
            continue

        for match in matches:
            loinc_code = indicator["loinc_code"]
            if loinc_code in seen_codes:
                continue

            # 在匹配位置附近提取数值
            start = max(0, match.start())
            end = min(len(text), match.end() + 80)
            context = text[start:end]

            value_match = VALUE_PATTERN.search(context[match.start() - start:])
            if not value_match:
                # 尝试更宽松的搜索
                value_match = VALUE_PATTERN.search(context)
            if not value_match:
                continue

            value = float(value_match.group(1))
            unit = indicator["unit"]

            # 尝试提取参考范围
            ref_low = indicator["ref_low"]
            ref_high = indicator["ref_high"]
            ref_match = re.search(
                r'(?:参考|正常|Reference|Ref)[:：]?\s*[\(（]?\s*(\d+\.?\d*)\s*[-—~～至]\s*(\d+\.?\d*)\s*[\)）]?',
                context,
                re.IGNORECASE,
            )
            if ref_match:
                try:
                    ref_low = float(ref_match.group(1))
                    ref_high = float(ref_match.group(2))
                except (ValueError, IndexError):
                    pass

            observations.append({
                "loinc_code": loinc_code,
                "loinc_name": indicator["loinc_name"],
                "value_numeric": value,
                "value_unit": unit,
                "reference_range_low": ref_low,
                "reference_range_high": ref_high,
            })
            seen_codes.add(loinc_code)
            break  # 每个指标只取第一个匹配

    logger.info(f"Report parser: extracted {len(observations)} observations from text")
    return observations


def enrich_observations_with_dictionary(
    observations: list[dict],
    stratum: str = "adult_male",
) -> list[dict]:
    """把 OCR 抽出的 observations 补一层「指标词典归一化」字段。

    每个 observation 原地附加（若可解析）：
      - canonical_slug:   词典 slug（如 "glucose"）
      - canonical_name_cn: 词典中文名
      - canonical_name_en: 词典英文名
      - canonical_loinc:   词典 LOINC（可能覆盖 OCR 猜的）
      - canonical_unit:    SI 单位
      - canonical_value:   换算到 SI 单位的数值（若可换算）
      - unit_factor:       换算因子
      - ref_range_canonical: {"low": ..., "high": ...}（按 stratum）
      - in_range:          bool
      - level:             "low" | "normal" | "high"

    未命中词典 / 单位无法识别时只附加 `normalized: false, reason: "..."`，
    其他字段保持 None —— **绝不静默丢弃原 observations**。

    设计要点：
      - fail-soft：任何单条解析失败不影响整批返回
      - 词典不可用（YAML 缺失/损坏）时整体降级为「原样返回 + 全部 normalized=false」
      - wellness 边界：level/in_range 只作 wellness 参考，前端展示时必须携 disclaimer
    """
    from app.utils.indicator_dict import (
        IndicatorDictError,
        STRATA,
        get_entry,
        is_loinc_code,
        load_dictionary,
        normalize_reference_range,
        resolve_name,
    )

    # stratum 非法回退到默认（不抛异常，OCR pipeline 层不做输入校验）
    if stratum not in STRATA:
        stratum = "adult_male"

    try:
        _ = load_dictionary()
    except IndicatorDictError as e:
        logger.warning(f"indicator dictionary unavailable, skip enrichment: {e}")
        for obs in observations:
            obs["normalized"] = False
            obs["normalize_reason"] = f"dictionary_unavailable: {e}"
        return observations

    resolved_count = 0
    for obs in observations:
        try:
            # 1) 名称或 LOINC 解析
            name = obs.get("loinc_name") or obs.get("name") or ""
            # loinc_name 通常是 "血糖(Glucose)" 这种中英夹拼，剥括号后取中文或英文部分
            name_candidates = [name]
            if "(" in name and name.endswith(")"):
                inner = name[name.find("(") + 1 : -1]
                outer = name[: name.find("(")].strip()
                if outer:
                    name_candidates.insert(0, outer)
                if inner:
                    name_candidates.insert(1, inner)

            resolved = None
            for candidate in name_candidates:
                resolved = resolve_name(candidate)
                if resolved:
                    break
            if resolved is None:
                # 尝试用 loinc_code 直查（可能 OCR 猜的 code 与词典一致）
                loinc = obs.get("loinc_code")
                if loinc and is_loinc_code(str(loinc)):
                    data = load_dictionary()
                    for slug, entry in data["indicators"].items():
                        code = entry.get("loinc_code")
                        codes = code if isinstance(code, list) else [code]
                        if str(loinc) in [str(c) for c in codes]:
                            resolved = {
                                "slug": slug,
                                "name_en": entry["name_en"],
                                "name_cn": entry["name_cn"],
                                "loinc_code": code,
                                "unit_si": entry["unit_si"],
                            }
                            break

            if resolved is None:
                obs["normalized"] = False
                obs["normalize_reason"] = "unknown_indicator"
                continue

            entry = get_entry(resolved["slug"])
            obs["canonical_slug"] = resolved["slug"]
            obs["canonical_name_cn"] = resolved["name_cn"]
            obs["canonical_name_en"] = resolved["name_en"]
            # 词典 LOINC 若与 OCR 猜的不同，以词典为准（更权威）
            obs["canonical_loinc"] = resolved["loinc_code"]
            obs["canonical_unit"] = resolved["unit_si"]

            # 2) 单位换算
            value = obs.get("value_numeric")
            unit = obs.get("value_unit")
            unit_alt = entry.get("unit_alt", {}) if entry else {}
            factor = None
            if isinstance(value, (int, float)) and unit:
                for k, v in unit_alt.items():
                    if k == unit:
                        factor = v
                        break
                if factor is None:
                    from app.utils.indicator_dict import _normalize_unit
                    target = _normalize_unit(str(unit))
                    for k, v in unit_alt.items():
                        if _normalize_unit(k) == target:
                            factor = v
                            break

            if factor is not None and isinstance(value, (int, float)):
                canonical_value = float(value) * factor
                obs["canonical_value"] = canonical_value
                obs["unit_factor"] = factor
                # 3) 参考区间 + level
                try:
                    ref = normalize_reference_range(
                        resolved["slug"], canonical_value, stratum
                    )
                    obs["ref_range_canonical"] = ref["ref_range"]
                    obs["in_range"] = ref["in_range"]
                    obs["level"] = ref["level"]
                    obs["normalized"] = True
                    resolved_count += 1
                    continue
                except IndicatorDictError:
                    pass
            else:
                obs["canonical_value"] = None
                obs["unit_factor"] = None

            # 单位或数值缺失但名称匹配，仍返回部分归一化字段
            obs["ref_range_canonical"] = None
            obs["in_range"] = None
            obs["level"] = None
            obs["normalized"] = True
            obs["normalize_reason"] = "partial_no_unit_conversion"
            resolved_count += 1

        except Exception as e:  # noqa: BLE001
            # 单条异常不能阻塞整批；fail-soft
            obs["normalized"] = False
            obs["normalize_reason"] = f"error: {e}"

    logger.info(
        f"indicator_dict enrichment: {resolved_count}/{len(observations)} observations enriched (stratum={stratum})"
    )
    return observations