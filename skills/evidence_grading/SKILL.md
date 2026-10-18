# 证据分级

> 对 HealthLens 每条建议的证据强度进行分级评估，输出 L1/L2/L3 等级 + 引用溯源 + 置信度评分。

## 输入
- recommendations: list[dict] - 建议列表（每项含 name / prescription / tcm_source / gene_relevance）
- evidence_db_path: str | None - 证据库路径（默认 data/case_evidence_db.json）

## 输出
- graded: list[dict] - 分级后的建议列表
- summary: dict - 统计摘要（各等级数量）
- ungraded: list[str] - 无证据的建议名称

## 方法论
1. **L1（强证据）**：有系统综述/Meta 分析/指南支持 → 检查 case_evidence_db 中是否有匹配的循证记录
2. **L2（中证据）**：有 RCT/队列研究/临床试验支持 → 检查是否有临床研究引用
3. **L3（弱证据）**：仅有个案报告/古籍文献/专家经验 → 检查古籍来源
4. **无证据**：完全无引用来源 → 标记为 ungraded，建议不采纳
5. **置信度评分**：基于证据等级 × 引用数量 × 时效性，输出 0-1 分数

证据分级参考：
- Oxford CEBM 分级（Center for Evidence-Based Medicine）
-GRADE 工作组分级系统
- 中华中医药学会临床指南证据分级标准

## 前置依赖
- Python 3.12+
- `data/case_evidence_db.json`

## 示例
```bash
python skills/evidence_grading/run.py \
  --recs '[{"name":"四君子汤","tcm_source":"《太平惠民和剂局方》"}]'
```
