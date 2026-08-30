"""fusion_inference 测试"""
import sys
sys.path.insert(0, ".")
from skills.fusion_inference.run import run

r = run(
    gene_scores={"mitochondrial": 0.32},
    text_profile="最近容易疲劳、怕冷、睡不好",
)
assert "weak_pathways" in r
assert "weak_axes" in r
assert "recommendations" in r
assert len(r["recommendations"]) > 0, "应有推荐"
print(f"✓ 弱项通路: {r['weak_pathways']}")
print(f"✓ 弱项轴: {r['weak_axes']}")
print(f"✓ 推荐数: {len(r['recommendations'])}")
print("ALL FUSION_INFERENCE TESTS PASSED")
