"""Rubric Benchmark 校验脚本。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4
         「自建 rubric 基准」+「Judge 偏差校准」。

用途：
- 校验 data/rubric_benchmark_v1.json 结构正确性；
- 校验每条 rubric 的权重和严格 = 1.0（±1e-6）；
- 校验 5 类各 40 条（±2 容差）；
- 校验 id 全局唯一；
- 校验 reference_pattern 是有效正则；
- 校验 rubric_criteria 与 weights 长度一致；
- 输出通过/失败清单，返回非零退出码表示失败。

不引入第三方依赖。CI 可直接调用。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "data" / "rubric_benchmark_v1.json"

REQUIRED_CATEGORIES = (
    "axes_interpretation",
    "tcm_terminology",
    "claims_boundary",
    "critical_values",
    "uncertainty_expression",
)

EXPECTED_PER_CATEGORY = 40
CATEGORY_TOLERANCE = 2  # ±2
WEIGHT_TOLERANCE = 1e-6
MIN_CRITERIA = 4
MAX_CRITERIA = 12


def _check(path: Path, verbose: bool = False) -> tuple[list[str], list[str]]:
    """返回 (pass_msgs, fail_msgs)。"""
    passes: list[str] = []
    fails: list[str] = []

    if not path.is_file():
        fails.append(f"file not found: {path}")
        return passes, fails

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fails.append(f"JSON parse error: {exc}")
        return passes, fails

    if not isinstance(data, dict):
        fails.append("root must be a dict")
        return passes, fails

    items = data.get("items")
    if not isinstance(items, list):
        fails.append("'items' must be a list")
        return passes, fails

    passes.append(f"loaded {len(items)} items from {path.name}")

    # ---- id 唯一性 ----
    seen_ids: dict[str, int] = {}
    dup_ids: list[str] = []
    for it in items:
        iid = it.get("id", "")
        if iid in seen_ids:
            dup_ids.append(iid)
        else:
            seen_ids[iid] = 1
    if dup_ids:
        fails.append(f"duplicate ids: {dup_ids[:5]}")
    else:
        passes.append(f"ids unique ({len(seen_ids)})")

    # ---- 权重和 = 1.0 ----
    weight_failures: list[tuple[str, float]] = []
    for it in items:
        w = it.get("weights", {})
        if not isinstance(w, dict) or not w:
            weight_failures.append((it.get("id", "?"), 0.0))
            continue
        s = sum(float(v) for v in w.values())
        if abs(s - 1.0) > WEIGHT_TOLERANCE:
            weight_failures.append((it.get("id", "?"), s))
    if weight_failures:
        fails.append(
            f"weights sum != 1.0 for {len(weight_failures)} items; "
            f"sample: {weight_failures[:3]}"
        )
    else:
        passes.append("all items: weights sum = 1.0")

    # ---- criteria 与 weights 长度一致 ----
    len_failures: list[str] = []
    for it in items:
        crits = it.get("rubric_criteria", [])
        w = it.get("weights", {})
        if len(crits) != len(w):
            len_failures.append(
                f"{it.get('id','?')}: criteria={len(crits)} weights={len(w)}"
            )
        if len(crits) < MIN_CRITERIA or len(crits) > MAX_CRITERIA:
            len_failures.append(
                f"{it.get('id','?')}: criteria count {len(crits)} "
                f"outside [{MIN_CRITERIA},{MAX_CRITERIA}]"
            )
    if len_failures:
        fails.append(f"criteria/weights mismatch ({len(len_failures)}): {len_failures[:3]}")
    else:
        passes.append("criteria count matches weights for all items")

    # ---- 类别均衡 ----
    from collections import Counter
    cat_counts = Counter(it.get("category", "?") for it in items)
    for cat in REQUIRED_CATEGORIES:
        n = cat_counts.get(cat, 0)
        if abs(n - EXPECTED_PER_CATEGORY) > CATEGORY_TOLERANCE:
            fails.append(
                f"category {cat}: count={n}, expected {EXPECTED_PER_CATEGORY}"
                f"±{CATEGORY_TOLERANCE}"
            )
    for cat, n in cat_counts.items():
        if cat not in REQUIRED_CATEGORIES:
            fails.append(f"unexpected category {cat!r}: {n} items")
    if not any(f.startswith(f"category {c}") for c in REQUIRED_CATEGORIES for f in fails):
        passes.append(
            f"categories balanced: "
            + ", ".join(f"{c}={cat_counts.get(c,0)}" for c in REQUIRED_CATEGORIES)
        )

    # ---- reference_pattern 正则有效性 ----
    regex_failures: list[tuple[str, str]] = []
    for it in items:
        pat = it.get("reference_pattern", "")
        if not pat:
            regex_failures.append((it.get("id", "?"), "empty"))
            continue
        try:
            re.compile(pat)
        except re.error as exc:
            regex_failures.append((it.get("id", "?"), str(exc)))
    if regex_failures:
        fails.append(
            f"invalid reference_pattern for {len(regex_failures)} items; "
            f"sample: {regex_failures[:3]}"
        )
    else:
        passes.append("all reference_pattern are valid regex")

    # ---- red_flags 非空 ----
    rf_failures = [it.get("id", "?") for it in items if not it.get("red_flags")]
    if rf_failures:
        fails.append(f"missing red_flags for {len(rf_failures)}: {rf_failures[:3]}")
    else:
        passes.append("all items have red_flags")

    # ---- prompt 非空 ----
    p_failures = [it.get("id", "?") for it in items if not it.get("prompt", "").strip()]
    if p_failures:
        fails.append(f"empty prompt for {len(p_failures)}: {p_failures[:3]}")
    else:
        passes.append("all items have non-empty prompts")

    # ---- 总条数 200 ± 10 ----
    if not (190 <= len(items) <= 210):
        fails.append(f"total items {len(items)} outside [190, 210]")
    else:
        passes.append(f"total items {len(items)} in [190, 210]")

    if verbose:
        for p in passes:
            print(f"[PASS] {p}")
        for f in fails:
            print(f"[FAIL] {f}")
    return passes, fails


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate rubric benchmark JSON")
    ap.add_argument(
        "--path", type=str, default=str(DEFAULT_PATH),
        help=f"benchmark JSON path (default: {DEFAULT_PATH})",
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="verbose output")
    args = ap.parse_args()

    path = Path(args.path)
    passes, fails = _check(path, verbose=args.verbose)

    if not args.verbose:
        print(f"Rubric benchmark: {path}")
        print(f"Total items: {len(json.loads(path.read_text(encoding='utf-8'))['items'])}")
        print(f"PASS: {len(passes)}  FAIL: {len(fails)}")
        if fails:
            print("--- FAILURES ---")
            for f in fails:
                print(f"  - {f}")

    if fails:
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
