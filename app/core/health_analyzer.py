"""健康数据分析引擎
Phase 1: 基础指标异常检测
Phase 2: 多维度综合分析
"""
from dataclasses import dataclass

@dataclass
class AnalysisResult:
    summary: str
    abnormal_items: list[dict]
    risk_factors: list[str]
    recommendations: list[str]

class HealthAnalyzer:
    def analyze_observations(self, observations: list[dict]) -> AnalysisResult:
        """分析健康指标，检测异常值"""
        abnormal_items = []
        for obs in observations:
            value = obs.get("value_numeric")
            low = obs.get("reference_range_low")
            high = obs.get("reference_range_high")
            if value is not None and (low is not None or high is not None):
                is_abnormal = False
                if low is not None and value < low:
                    is_abnormal = True
                if high is not None and value > high:
                    is_abnormal = True
                if is_abnormal:
                    low_str = str(low) if low is not None else ""
                    high_str = str(high) if high is not None else ""
                    abnormal_items.append({
                        "name": obs.get("loinc_name", "Unknown"),
                        "code": obs.get("loinc_code"),
                        "value": value,
                        "unit": obs.get("value_unit"),
                        "range": f"{low_str}-{high_str}",
                        "low": low,
                        "high": high,
                    })

        # 基于异常指标生成风险因子和建议
        risk_factors = []
        for item in abnormal_items:
            name = item["name"]
            value = item["value"]
            low = item.get("low")
            high = item.get("high")

            # 判断偏移程度以区分 high / borderline
            level = "borderline"
            detail = f"{name} 为 {value}{item['unit']}，参考范围 {item['range']}"

            if low is not None and high is not None:
                range_width = high - low
                if value < low:
                    deviation = (low - value) / range_width if range_width > 0 else 0
                else:
                    deviation = (value - high) / range_width if range_width > 0 else 0
                if deviation > 0.5:
                    level = "high"
                    detail = f"{name} 为 {value}{item['unit']}，参考范围 {item['range']}，明显偏离正常范围"
                else:
                    detail = f"{name} 为 {value}{item['unit']}，参考范围 {item['range']}，轻度偏离"
            elif high is not None and value > high:
                deviation = (value - high) / high if high > 0 else 0
                if deviation > 0.3:
                    level = "high"
                    detail = f"{name} 为 {value}{item['unit']}，参考范围上限 {high}，明显偏高"

            risk_factors.append({"factor": name, "level": level, "detail": detail})

        # 基于异常数量生成分级建议
        abnormal_count = len(abnormal_items)
        if abnormal_count == 0:
            recommendations = ["各项指标均在正常范围内，请继续保持健康的生活方式。"]
        elif abnormal_count <= 2:
            recommendations = [
                f"有 {abnormal_count} 项指标存在轻度异常，建议定期（1-3个月）复查。",
                "保持规律作息、均衡饮食和适量运动。",
                "如指标持续异常，请及时就医咨询。",
            ]
        else:
            recommendations = [
                f"有 {abnormal_count} 项指标异常，部分指标明显偏离正常范围，建议尽快就医。",
                "请携带近期体检报告前往医院相关科室做进一步检查。",
                "就医前避免剧烈运动和饮酒，确保检查结果准确。",
            ]

        return AnalysisResult(
            summary=f"共分析 {len(observations)} 项指标，{len(abnormal_items)} 项异常",
            abnormal_items=abnormal_items,
            risk_factors=risk_factors,
            recommendations=recommendations,
        )
