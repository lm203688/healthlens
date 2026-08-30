"""tcm_text_mining 测试"""
import sys
sys.path.insert(0, ".")
from skills.tcm_text_mining.run import run

# 测试1：症状抽取
r = run(text="患者面色萎黄，神疲乏力，舌淡苔白，脉细弱")
assert len(r["entities"]) > 0, f"应为0: {r['entities']}"
assert "B" in [e["source_axis"] for e in r["entities"]], "应含气血轴"
print("✓ 测试1 通过：症状抽取")

# 测试2：轴评分
r2 = run(text="长期失眠、焦虑、情绪低落")
assert r2["axis_mapping"].get("D", 0) > 0, "应含阴阳轴"
assert r2["axis_mapping"].get("G", 0) > 0, "应含神轴"
print("✓ 测试2 通过：轴评分")

# 测试3：置信度
r3 = run(text="补气养血，用四君子汤加四物汤")
assert r3["confidence"] > 0.0, "置信度应>0"
assert len(r3["raw_evidence"]) > 0
print("✓ 测试3 通过：置信度")

print("ALL TCM_TEXT_MINING TESTS PASSED")
