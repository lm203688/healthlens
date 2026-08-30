"""
demo_fusion.py —— 个性化融合引擎 v0 演示（已接入 P0 安全管线）
=====================================================================
展示：基因弱项 ∩ 古籍候选交集加权 → 个性化建议；缺基因 → is_demo 横幅；
      医学急症 → 前置红牌拦截；去医疗化/八轴红线 → 后置闸门拦截。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthlens_agent.pipeline import run_pipeline, UserProfile  # noqa: E402


def _print_result(label: str, res):
    print(f"\n=== {label} ===")
    print(f"前置闸门 passed={res.pre_result.passed} level={res.pre_result.level}")
    print(f"整体 passed={res.passed}  any_unsafe={res.any_unsafe}")
    print(f"横幅: {res.banner}")
    print(f"弱项通路: {res.weak_pathways}  | 弱项轴: {res.weak_axes}")
    n_blocked = sum(1 for r in res.recommendations if not r["gate_passed"])
    print(f"建议 {len(res.recommendations)} 条，被闸门拦截 {n_blocked} 条")
    for r in res.recommendations[:5]:
        warn = r.get("gate_warnings", [])
        print(f"  [{r['mode']}] {r['case_id']} 分={r['score']:.1f} 证据={r['evidence_level']} "
              f"gate_passed={r['gate_passed']} warn={len(warn)} | 靶向:{r['targeted_pathway']}")
        print(f"        古籍:{r['tcm_source']}")
        print(f"        基因相关:{r['gene_relevance']}")
        print(f"        处方:{r['prescription']} ｜ 监测:{r['monitor_markers']}")


def scenario_personalized():
    prof = UserProfile(
        pathway_scores={"mitochondrial": 0.32, "Circadian_CLOCK_BMAL1": 0.41,
                        "Autophagy": 0.61},
        contraindications={"低血糖"},
    )
    res = run_pipeline(user_input="最近容易疲劳、怕冷、睡不好，线粒体通路偏弱", profile=prof)
    _print_result("场景 A：有基因弱项（线粒体弱 + 昼夜弱）", res)


def scenario_demo():
    res = run_pipeline(user_input="帮我看看体质", profile=UserProfile())
    _print_result("场景 B：无基因数据（is_demo 横幅）", res)


def scenario_emergency():
    res = run_pipeline(user_input="我最近总是胸痛伴随呼吸困难")
    _print_result("场景 C：医学急症（前置红牌拦截）", res)


def scenario_overmedicalize():
    res = run_pipeline(
        user_input="给我开六味地黄丸处方治疗肾虚",
        profile=UserProfile(pathway_scores={"mitochondrial": 0.4}),
    )
    _print_result("场景 D：去医疗化请求（后置闸门）", res)


if __name__ == "__main__":
    print("HealthLens 融合引擎演示 — 已接入 P0 安全管线（前置红牌 + 后置闸门 + 运行时审计）")
    scenario_personalized()
    scenario_demo()
    scenario_emergency()
    scenario_overmedicalize()
    print("\n" + "=" * 60)
    print("提示：去医疗化 disclaimer 已由产品层统一注入，详见 fusion_engine.disclaimer()")
