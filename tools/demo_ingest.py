"""
demo_ingest.py —— 硬件适配器 v0 端到端演示（零依赖、立即可跑）
生成一份「模拟可穿戴导出 CSV」→ CSVFileAdapter → 八轴样本 → 轴聚合。
证明标准化层（八轴映射器）在真实 OAuth 之前就能跑通。
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "lib"))
from biometric_ingest import CSVFileAdapter, summarize_by_axis, AXIS_NAMES  # noqa: E402

HERE = os.path.dirname(__file__)
SAMPLE_CSV = os.path.join(HERE, "_sample_wearable.csv")


def make_sample_csv():
    rows = [
        # date, resting_hr, hrv_rmssd, sleep_efficiency, sleep_midpoint, vo2max, body_weight, eating_window
        ["2026-08-10", 62, 48, 88, "03:10", 41.2, 70.5, 11],
        ["2026-08-11", 60, 52, 90, "03:05", 41.5, 70.3, 10],
        ["2026-08-12", 58, 55, 92, "02:58", 41.9, 70.1, 9],
        ["2026-08-13", 59, 53, 91, "03:00", 42.0, 69.9, 9],
    ]
    with open(SAMPLE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "resting_hr", "hrv_rmssd", "sleep_efficiency",
                    "sleep_midpoint", "vo2max", "body_weight", "eating_window"])
        w.writerows(rows)


def main():
    make_sample_csv()
    adapter = CSVFileAdapter(SAMPLE_CSV, source="demo_wearable")
    samples = adapter.fetch()
    print(f"[OK] 解析样本 {len(samples)} 条")
    print("\n--- 前 6 条八轴样本 ---")
    for s in samples[:6]:
        print(f"  {s.ts[:10]} | 轴{s.axis}({AXIS_NAMES[s.axis]}) | {s.marker}={s.value}{s.unit} | {s.source}")

    agg = summarize_by_axis(samples)
    print("\n--- 八轴覆盖（样本数） ---")
    for a in agg:
        print(f"  轴{a} {AXIS_NAMES[a]:<8}: {agg[a]}")

    covered = [a for a in agg if agg[a] > 0]
    print(f"\n[结论] 本次模拟数据覆盖 {len(covered)}/8 轴；"
          f"无数据的轴（需真实硬件/组学）：{','.join(x for x in agg if agg[x] == 0) or '无'}")
    print("[注] 华为/Apple/CGM/EEG 适配器 fetch() 待 OAuth；field_map() 已定义，接入后即可同构产出样本。")


if __name__ == "__main__":
    main()
