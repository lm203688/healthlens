# 中医古籍文本挖掘

> 从中医古籍原文中抽取症状—治法—方药的结构化证据，并映射到 HealthLens 八轴-通路体系。

## 输入
- text: str - 古籍原文（段落或章节）
- target_axis: str | None - 目标轴（A-H），None 表示全部
- language: str - "zh" 或 "en"（默认 "zh"）

## 输出
- entities: list[dict] - 抽取的实体列表，每项含 {symptom, treatment, formula, source_axis}
- axis_mapping: dict[str, float] - 八轴相关度评分
- confidence: float - 整体置信度 (0-1)
- raw_evidence: list[str] - 原始证据句子

## 方法论
1. **实体识别**：基于关键词规则 + 正则模式匹配中医术语（症状、治法、方名、药名）
2. **关系抽取**：识别"症状→治法"和"治法→方药"的语义关系
3. **轴映射**：将抽取的术语映射到八轴体系（A 气化/B 气血/C 络脉/D 阴阳/E 脏腑/F 正邪/G 神/H 先天）
4. **置信度评分**：基于术语频率、上下文吻合度、证据链完整性

此 Skill 是 HealthLens 古籍证据库的构建基础，对应 `data/case_evidence_db.json` 的数据来源。

## 前置依赖
- Python 3.12+
- 标准库（无需第三方依赖）

## 示例
```bash
python skills/tcm_text_mining/run.py \
  --text "患者面色萎黄，神疲乏力，舌淡苔白，脉细弱" \
  --axis B
```
