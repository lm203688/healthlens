"""A2A 联邦 demo：HealthLens + Mock External Agent 互操作。

**为什么需要这个 demo**：
- `app/api/a2a.py` 是 HealthLens 的 A2A server（入站），接受外部 agent 调用。
- `app/lib/a2a_client.py` 是 HealthLens 的 A2A client（出站），用于调用外部 agent。
- 本脚本模拟一次完整的 A2A federation：HealthLens 发起 SendMessage →
  Mock External Agent 收到 → Mock External Agent 执行逻辑 → Mock External Agent
  返回结果 → HealthLens 通过 GetTask 拿到结果。

**协议对齐**：严格遵循 A2A v1.0.1 JSON-RPC，包括：
- 端点：`POST /a2a`
- 方法：SendMessage / GetTask
- 状态机：SUBMITTED → WORKING → COMPLETED
- 错误码：-32001 task not found, -32002 invalid transition 等

**运行方式**：
```bash
# 直接运行，起两个本地 agent 互调
python tests/a2a_demo.py

# pytest 运行（带 coverage）
python -m pytest tests/a2a_demo.py -v
```

**输出示例**：
```
=== HealthLens (client) → Mock External Agent (server) ===
[client] send_message: "What wellness tips do you have?"
[server] received: contextId="ctx-demo", parts=[{"kind":"text","text":"..."}]
[server] created task: task-abc123 → working → completed
[client] get_task(task_id="task-abc123")
=== Response ===
{
  "taskId": "task-abc123",
  "contextId": "ctx-demo",
  "status": {"state": "COMPLETED", "message": "ok"},
  "artifacts": [...],
  "history": [...]
}
```

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-18)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.lib.a2a_client import A2AClient
from app.lib.a2a_mock_server import MockA2AServer


def demo_federation() -> None:
    """主函数：HealthLens client 调用 Mock External Agent，展示完整往返。"""
    print("=== A2A 联邦 Demo: HealthLens → Mock External Agent ===\n")

    # Mock External Agent 响应逻辑：收到消息后生成一个 wellness tip
    def mock_wellness_responder(message: dict[str, Any]) -> dict[str, Any]:
        parts = message.get("parts", [])
        text = " ".join(
            p.get("text", "") for p in parts
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ).strip()
        if text:
            return {
                "wellness_tip": f"Based on your query '{text}', here's a tip: Stay hydrated and take breaks.",
                "source": "Mock External Agent",
                "timestamp": time.time(),
            }
        return {"wellness_tip": "General wellness tip: Maintain a balanced diet and regular exercise."}

    # 启动 Mock External Agent（模拟第三方 wellness 平台）
    with MockA2AServer(responder=mock_wellness_responder) as server:
        print(f"[server] Mock External Agent listening at {server.url}")

        # HealthLens 作为 client 调用外部 agent
        client = A2AClient(server.url, timeout_s=10.0)
        context_id = "ctx-demo"
        task_id = "task-wellness-demo"

        # 1. SendMessage
        print(f"[client] send_message (contextId={context_id}, taskId={task_id})")
        message = {
            "parts": [
                {"kind": "text", "text": "What wellness tips do you have for someone who works long hours?"}
            ]
        }
        try:
            result = client.send_message(
                message=message,
                context_id=context_id,
                task_id=task_id,
                status_message="User seeking wellness advice",
            )
            print(f"[client] got immediate response: {result['status']['state']}")
        except Exception as e:
            print(f"[client] ERROR: {e}")
            return

        # 2. Wait a moment for async completion（模拟真实异步场景）
        time.sleep(0.1)

        # 3. GetTask（获取完整结果，包括 artifact）
        print(f"[client] get_task(taskId={task_id})")
        try:
            task = client.get_task(task_id)
        except Exception as e:
            print(f"[client] ERROR: {e}")
            return

        # 4. 展示结果
        print("\n=== Response ===")
        print(json.dumps(task, indent=2, ensure_ascii=False))

        # 5. 验证关键字段
        print("\n=== Validation ===")
        assert task["status"]["state"] == "COMPLETED"
        assert task["contextId"] == context_id
        assert task["taskId"] == task_id
        assert len(task["artifacts"]) == 1
        artifact = task["artifacts"][0]
        assert artifact["name"] == "mock_response"
        assert "wellness_tip" in artifact["parts"][0]["data"]
        print("✅ All validations passed!")

        # 6. ListTasks（验证任务列表）
        print("\n=== ListTasks ===")
        list_result = client.list_tasks(context_id=context_id, limit=10)
        print(f"Found {list_result['totalCount']} tasks in context {context_id}:")
        for t in list_result["tasks"]:
            print(f"  - {t['taskId']}: {t['status']['state']}")


def demo_error_handling() -> None:
    """演示错误处理：无效 taskId → A2A_JSON_RPC_ERROR -32001"""
    print("\n=== Error Handling Demo ===")

    with MockA2AServer() as server:
        client = A2AClient(server.url, timeout_s=5.0)

        try:
            client.get_task("nonexistent-task-id")
        except Exception as e:
            print(f"Expected error: {type(e).__name__}: {e}")
            # 应该抛 A2AJsonRpcError with code -32001
            assert "task not found" in str(e)


def demo_cancel_task() -> None:
    """演示 CancelTask：从 SUBMITTED 取消任务"""
    print("\n=== CancelTask Demo ===")

    with MockA2AServer() as server:
        client = A2AClient(server.url, timeout_s=5.0)

        # 先创建一个任务（保持 SUBMITTED 状态）
        result = client.send_message(
            message={"parts": [{"kind": "text", "text": "long running task"}]},
            context_id="ctx-cancel-demo",
            task_id="task-cancel-demo",
        )
        task_id = result["taskId"]
        print(f"Created task {task_id} (status: {result['status']['state']})")

        # 立即取消
        canceled = client.cancel_task(task_id, reason="User canceled")
        print(f"Cancel response: {canceled['status']['state']}")
        assert canceled["status"]["state"] == "CANCELED"

        # 再取消一次（应该报错）
        try:
            client.cancel_task(task_id)
        except Exception as e:
            print(f"Second cancel error (expected): {e}")
            assert "invalid task transition" in str(e)


if __name__ == "__main__":
    demo_federation()
    demo_error_handling()
    demo_cancel_task()
    print("\n=== Demo completed successfully! ===")