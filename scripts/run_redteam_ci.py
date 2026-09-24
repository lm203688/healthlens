#!/usr/bin/env python3
"""CI 入口：运行确定性医疗安全红队评测。

对应产品完整性报告 P1「garak/promptfoo 进 CI」——
把 healthlens_agent/redteam_eval.py 的四轴（robustness/privacy/bias/hallucination）
对抗评测接入 GitHub Actions，作为合并门禁之一。

- 默认走「确定性闸门评测」（零外呼、零成本）：仅校验护栏前置/后置捕获率。
- 若设置环境变量 HL_JUDGE_*（LLM judge 推理后端），可切到 LLM 模式做深层偏见评测。
- overall_pass=False（存在遗漏用例）时退出码 1，阻断合并；报告同时落盘为 JSON 供归档。

用法：
    python scripts/run_redteam_ci.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 让仓库根进入 sys.path，支持 `import healthlens_agent`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from healthlens_agent.redteam_eval import run_eval, save_report  # noqa: E402


def main() -> int:
    report = run_eval()  # 无 generate → 确定性模式

    out_dir = ROOT / "reports" / "redteam"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_report(report, str(out_dir / "redteam_report.json"))

    print(report.render_markdown())
    print(
        f"\n[CI] 确定性闸门评测完成: overall_pass={report.overall_pass}, "
        f"已知缺口 {len(report.gap_cases)} 项, "
        f"待LLM {sum(a.needs_llm for a in report.axes.values())} 项"
    )

    if not report.overall_pass:
        print("[CI] ❌ 红队评测存在遗漏用例，判定为失败，阻断合并。")
        return 1

    print("[CI] ✅ 红队评测通过（已评测项无遗漏；已知缺口与待LLM项已诚实上报，非失败）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
