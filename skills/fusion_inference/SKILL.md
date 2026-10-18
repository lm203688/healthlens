# 融合推理

> HealthLens 核心融合引擎的方法论封装。执行"古籍候选 ∩ 基因弱项通路"交集判定，输出八轴评分 + 个性化建议。

## 输入
- gene_scores: dict[str, float] - 基因弱项通路得分（如 {"mitochondrial": 0.32}）
- text_profile: str - 用户症状/体质描述文本
- tcm_profile: dict | None - 中医体质数据
- contraindications: set[str] - 禁忌症

## 输出
- weak_pathways: list[str] - 弱项通路
- weak_axes: list[str] - 弱项轴
- recommendations: list[dict] - 个性化建议（含 prescription / monitor_markers / evidence_level）
- fusion_score: float - 融合置信度
- disclaimer: str - 免责声明

## 方法论
1. **古籍候选提取**：调用 tcm_text_mining Skill 从用户文本抽取症状—治法—方药
2. **基因弱项映射**：将基因通路得分通过 `tcm_pathway_map.json` 别名消歧归一化
3. **交集判定**：古籍候选涉及的轴/通路 ∩ 基因弱项通路 → 核心干预点
4. **融合推荐**：对每个核心干预点生成个性化建议（食疗/非药物/方剂/生活方式）
5. **去医疗化校验**：每条建议通过 post_gate 校验，确保非医疗诊断
6. **LLM 增强**（可选）：如果 `USE_LLM=1` 且模型可用，用 LLM 对结果做语义润色

## 前置依赖
- Python 3.12+
- `skills/tcm_text_mining` Skill
- `data/tcm_pathway_map.json`
- `data/case_evidence_db.json`

## 示例
```bash
python skills/fusion_inference/run.py \
  --text "疲劳怕冷，线粒体偏弱" \
  --gene mitochondrial:0.32,circadian:0.41
```
