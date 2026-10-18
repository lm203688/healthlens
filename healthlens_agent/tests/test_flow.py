"""可复现 DAG pipeline 测试。"""

from healthlens_agent.flow import Storage, run_flow


def test_run_flow_produces_report():
    storage = run_flow(
        inputs={
            "user_input": "最近容易疲劳、怕冷、睡不好",
            "gene_data": {"mitochondrial": 0.32, "Circadian_CLOCK_BMAL1": 0.41},
        }
    )
    report = storage.read("report")
    assert report is not None
    assert report["has_gene"] is True
    assert len(report["recommendations"]) > 0
    assert "grade" in report


def test_run_flow_storage_api():
    s = Storage()
    s.write("k", 1)
    assert s.read("k") == 1
