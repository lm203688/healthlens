"""evidence_grading 测试"""
import sys
sys.path.insert(0, ".")
from skills.evidence_grading.run import run

recs = [
    {"name": "四君子汤", "prescription": "补气健脾", "tcm_source": "《太平惠民和剂局方》"},
    {"name": "六味地黄丸", "tcm_source": "《小儿药证直诀》"},
    {"name": "某疗法", "tcm_source": ""},
]

r = run(recommendations=recs)
assert r["graded"]
assert r["summary"]
print(f"✓ 分级结果: {r['summary']}")
for g in r["graded"]:
    assert g["evidence_level"] in ("L1", "L2", "L3"), f"异常等级: {g['evidence_level']}"
    print(f"  [{g['evidence_level']}] {g['name']} conf={g['confidence']}")
print("ALL EVIDENCE_GRADING TESTS PASSED")
