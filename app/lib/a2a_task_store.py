"""A2A v1.0.1 Task 内存存储（L0 协议对齐层）。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「A2A v1.0.1 SendMessage / GetTask / CancelTask / ListTasks JSON-RPC 端点」。

定位：
- **薄内存态容器**：仅做任务记录 + 状态机守卫，不做业务判断。
- **SCREAMING_SNAKE_CASE 状态**：SUBMITTED / WORKING / COMPLETED / FAILED /
  CANCELED / INPUT_REQUIRED，严格对齐 A2A v1.0.1 spec。
- **fail-loud 状态转移**：非法转移抛 `InvalidTaskTransitionError`，不静默降级。
- **TTL 清理**：默认 24 小时，惰性（每次读写触发）+ 主动 `purge_expired`。

**生产部署提示**：本模块是纯内存实现，多副本部署会丢失跨副本任务可见性，
重启会清空全部任务。生产环境应接入 DB / Redis 做后端，替换策略：
  1. 复用 `A2ATask` dataclass 作为持久化 schema（字段 camelCase 稳定）。
  2. `TaskStore` 的公开方法（`create_task` / `get_task` / `list_tasks` /
     `update_status` / `add_artifact` / `cancel_task` / `purge_expired`）
     保留同签名接口，注入持久化适配器即可，无需改 `app/api/a2a.py`。

Wellness 平台术语纪律：本模块只管理 agent task 元数据，不做健康判断。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable


# ─────────────────────────── 状态枚举 ───────────────────────────

class TaskState(str, enum.Enum):
    """A2A v1.0.1 TaskState 枚举（SCREAMING_SNAKE_CASE）。

    来源：https://google.github.io/A2A/specification/v1.0.1/#taskstate
    """

    SUBMITTED = "SUBMITTED"
    WORKING = "WORKING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    INPUT_REQUIRED = "INPUT_REQUIRED"


# 终态：到达后不可再转移
TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}
)

# 可取消状态：CancelTask 只允许从这些状态出发
CANCELABLE_STATES: frozenset[TaskState] = frozenset(
    {TaskState.SUBMITTED, TaskState.WORKING}
)

# 合法状态转移表：{from_state: {allowed_to_states}}
VALID_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUBMITTED: frozenset(
        {
            TaskState.WORKING,
            TaskState.INPUT_REQUIRED,
            TaskState.CANCELED,
            TaskState.FAILED,
        }
    ),
    TaskState.WORKING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.INPUT_REQUIRED,
            TaskState.FAILED,
            TaskState.CANCELED,
        }
    ),
    TaskState.INPUT_REQUIRED: frozenset(
        {TaskState.WORKING, TaskState.CANCELED, TaskState.FAILED}
    ),
    # 终态：无合法出边
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELED: frozenset(),
}


class InvalidTaskTransitionError(Exception):
    """非法任务状态转移。

    触发场景（fail-loud，不静默降级）：
    - 从终态出发（COMPLETED / FAILED / CANCELED）
    - 从非可取消状态调 CancelTask
    - 转移到状态机表中未定义的边

    属性：
        from_state: 当前状态
        to_state:   目标状态
        task_id:    涉及的 task ID（若已知）
    """

    def __init__(
        self,
        from_state: TaskState,
        to_state: TaskState,
        task_id: str | None = None,
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.task_id = task_id
        detail = (
            f"illegal task transition: {from_state.value} -> {to_state.value}"
        )
        if task_id:
            detail += f" (taskId={task_id})"
        super().__init__(detail)


# ─────────────────────────── A2ATask dataclass ───────────────────────────

@dataclass
class A2ATask:
    """单个 A2A 任务（camelCase 字段严格对齐 A2A v1.0.1 wire format）。

    字段说明：
        taskId:         任务唯一 ID（客户端可指定，否则服务端生成 UUID）
        contextId:      会话上下文 ID（把多个 task 串成一段会话）
        status:         当前状态（TaskState 枚举）
        statusMessage:  当前状态的自由文本消息（可空）
        artifacts:      任务产出的 artifacts 数组（如 MCP 工具返回结果）
        history:       状态迁移历史，每次 update_status 追加一条
                       `{"state": ..., "timestamp": ..., "statusMessage": ...}`
        createdAt:     ISO8601 UTC 创建时间
        updatedAt:     ISO8601 UTC 最后更新时间
    """

    taskId: str
    contextId: str
    status: TaskState = TaskState.SUBMITTED
    statusMessage: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    createdAt: str = ""
    updatedAt: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为 A2A v1.0.1 Task 结构（camelCase 字段）。"""
        return {
            "taskId": self.taskId,
            "contextId": self.contextId,
            "status": {
                "state": self.status.value,
                "message": self.statusMessage,
            },
            "artifacts": self.artifacts,
            "history": self.history,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }


# ─────────────────────────── TaskStore ───────────────────────────

class TaskStore:
    """A2A 任务内存存储。

    线程安全：所有公开方法内部持锁；写操作是原子的（create + 首次状态转移
    在一个临界区内完成）。读操作（get / list）在锁内拷贝，返回的 dict 是
    深拷贝，调用方可安全修改而不影响 store。

    TTL 语义：
    - 默认 24 小时（86400 秒）
    - 惰性清理：每次 `get_task` / `list_tasks` 会先跑一次 `purge_expired`
    - 主动清理：`purge_expired()` 可被 cron / worker 调用
    - TTL 从 `createdAt` 起算（不是 updatedAt），保证长任务不会永久续命

    幂等：
    - `create_task(taskId="X")`：如 X 已存在直接返回已有 task，不重复创建
    - `create_task()`（无 ID）：每次生成新 UUID，永不幂等
    """

    def __init__(self, ttl_seconds: float = 86400.0) -> None:
        self._tasks: dict[str, A2ATask] = {}
        self._created_at_monotonic: dict[str, float] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = float(ttl_seconds)

    # ── 内部工具 ──

    @staticmethod
    def _iso_now() -> str:
        """ISO8601 UTC 时间戳（毫秒精度，Z 结尾）。"""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _purge_locked(self) -> None:
        """锁内清理过期 task。调用方必须已持锁。"""
        if self._ttl_seconds <= 0:
            return
        now = time.monotonic()
        expired: list[str] = []
        for tid, created in self._created_at_monotonic.items():
            if (now - created) >= self._ttl_seconds:
                expired.append(tid)
        for tid in expired:
            self._tasks.pop(tid, None)
            self._created_at_monotonic.pop(tid, None)

    # ── 创建 / 读取 ──

    def create_task(
        self,
        *,
        taskId: str | None = None,
        contextId: str | None = None,
        statusMessage: str | None = None,
    ) -> A2ATask:
        """创建新任务。

        Args:
            taskId:    客户端提供的 ID（可选）。已存在则幂等返回。
            contextId: 上下文 ID（可选）。不传则复用 taskId 作为 contextId。
            statusMessage: 初始状态消息（可选）。

        Returns:
            新建（或已存在）的 A2ATask。首次创建时会自动写入 history[0]。

        Raises:
            ValueError: 幂等命中但 contextId 不一致（视为冲突）。
        """
        now = self._iso_now()
        with self._lock:
            self._purge_locked()

            # 客户端未提供 ID → 生成 UUID
            effective_task_id = taskId or uuid.uuid4().hex
            effective_context_id = contextId or effective_task_id

            # 幂等命中
            existing = self._tasks.get(effective_task_id)
            if existing is not None:
                if existing.contextId != effective_context_id:
                    raise ValueError(
                        f"taskId collision: {effective_task_id} exists with "
                        f"contextId={existing.contextId!r}, "
                        f"got {effective_context_id!r}"
                    )
                return existing

            task = A2ATask(
                taskId=effective_task_id,
                contextId=effective_context_id,
                status=TaskState.SUBMITTED,
                statusMessage=statusMessage,
                createdAt=now,
                updatedAt=now,
            )
            task.history.append(
                {
                    "state": task.status.value,
                    "timestamp": now,
                    "statusMessage": statusMessage,
                }
            )
            self._tasks[task.taskId] = task
            self._created_at_monotonic[task.taskId] = time.monotonic()
            return task

    def get_task(self, taskId: str) -> A2ATask | None:
        """按 ID 取任务（不存在返回 None，不抛异常）。"""
        with self._lock:
            self._purge_locked()
            task = self._tasks.get(taskId)
            return task

    def list_tasks(
        self,
        *,
        contextId: str | None = None,
        status: TaskState | str | None = None,
        limit: int = 50,
    ) -> list[A2ATask]:
        """列出任务，支持按 contextId / status 过滤。

        Args:
            contextId: 只返回该上下文内的 task
            status:    只返回指定状态的 task（接受 TaskState 枚举或字符串）
            limit:     最多返回多少条（上限 50，A2A v1.0.1 硬约束）

        Returns:
            按 createdAt 倒序（新在前）排列的 A2ATask 列表。

        Raises:
            ValueError: limit 超出 [1, 50] 范围，或 status 值非法。
        """
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        capped = min(limit, 50)

        # 归一化 status
        parsed_status: TaskState | None = None
        if status is not None:
            if isinstance(status, TaskState):
                parsed_status = status
            else:
                try:
                    parsed_status = TaskState(str(status))
                except ValueError:
                    raise ValueError(f"invalid status: {status!r}") from None

        with self._lock:
            self._purge_locked()
            results: list[A2ATask] = []
            for task in self._tasks.values():
                if contextId is not None and task.contextId != contextId:
                    continue
                if parsed_status is not None and task.status != parsed_status:
                    continue
                results.append(task)
            # 新在前
            results.sort(key=lambda t: t.createdAt, reverse=True)
            return results[:capped]

    # ── 状态转移 ──

    def update_status(
        self,
        taskId: str,
        new_state: TaskState,
        statusMessage: str | None = None,
    ) -> A2ATask:
        """转移任务状态。

        Args:
            taskId:        目标 task ID
            new_state:     目标状态
            statusMessage: 该状态的消息（可选，传入则覆盖）

        Returns:
            更新后的 A2ATask。

        Raises:
            KeyError:                    task 不存在
            InvalidTaskTransitionError: 非法转移
            TypeError:                   new_state 不是 TaskState
        """
        if not isinstance(new_state, TaskState):
            raise TypeError(
                f"new_state must be TaskState, got {type(new_state).__name__}"
            )
        with self._lock:
            self._purge_locked()
            task = self._tasks.get(taskId)
            if task is None:
                raise KeyError(f"task not found: {taskId}")

            from_state = task.status
            if from_state == new_state:
                # 幂等：状态相同则不视为非法转移，但仍记录消息（若变更）
                if statusMessage is not None and statusMessage != task.statusMessage:
                    task.statusMessage = statusMessage
                    task.updatedAt = self._iso_now()
                    task.history.append(
                        {
                            "state": task.status.value,
                            "timestamp": task.updatedAt,
                            "statusMessage": statusMessage,
                        }
                    )
                return task

            allowed = VALID_TRANSITIONS.get(from_state, frozenset())
            if new_state not in allowed:
                raise InvalidTaskTransitionError(
                    from_state=from_state,
                    to_state=new_state,
                    task_id=taskId,
                )

            task.status = new_state
            if statusMessage is not None:
                task.statusMessage = statusMessage
            task.updatedAt = self._iso_now()
            task.history.append(
                {
                    "state": task.status.value,
                    "timestamp": task.updatedAt,
                    "statusMessage": task.statusMessage,
                }
            )
            return task

    # ── Artifact ──

    def add_artifact(self, taskId: str, artifact: dict[str, Any]) -> A2ATask:
        """追加 artifact 到任务。

        Raises:
            KeyError: task 不存在
            TypeError: artifact 不是 dict
        """
        if not isinstance(artifact, dict):
            raise TypeError(f"artifact must be a dict, got {type(artifact).__name__}")
        with self._lock:
            self._purge_locked()
            task = self._tasks.get(taskId)
            if task is None:
                raise KeyError(f"task not found: {taskId}")
            task.artifacts.append(artifact)
            task.updatedAt = self._iso_now()
            return task

    # ── 取消 ──

    def cancel_task(
        self,
        taskId: str,
        statusMessage: str | None = None,
    ) -> A2ATask:
        """取消任务（仅 SUBMITTED / WORKING 可取消）。

        Raises:
            KeyError:                    task 不存在
            InvalidTaskTransitionError: 当前状态不在 CANCELABLE_STATES
        """
        with self._lock:
            self._purge_locked()
            task = self._tasks.get(taskId)
            if task is None:
                raise KeyError(f"task not found: {taskId}")
            if task.status not in CANCELABLE_STATES:
                raise InvalidTaskTransitionError(
                    from_state=task.status,
                    to_state=TaskState.CANCELED,
                    task_id=taskId,
                )
            # 释放锁让 update_status 自己获取（RLock 允许重入，但为语义清晰显式调用）
        return self.update_status(taskId, TaskState.CANCELED, statusMessage=statusMessage)

    # ── 清理 ──

    def purge_expired(self) -> int:
        """主动清理过期任务，返回被清理的数量。"""
        with self._lock:
            if self._ttl_seconds <= 0:
                return 0
            now = time.monotonic()
            expired: list[str] = []
            for tid, created in self._created_at_monotonic.items():
                if (now - created) >= self._ttl_seconds:
                    expired.append(tid)
            for tid in expired:
                self._tasks.pop(tid, None)
                self._created_at_monotonic.pop(tid, None)
            return len(expired)

    def __len__(self) -> int:
        with self._lock:
            self._purge_locked()
            return len(self._tasks)

    def __iter__(self) -> Iterable[A2ATask]:
        with self._lock:
            self._purge_locked()
            return iter(list(self._tasks.values()))


__all__ = [
    "TaskState",
    "A2ATask",
    "TaskStore",
    "InvalidTaskTransitionError",
    "TERMINAL_STATES",
    "CANCELABLE_STATES",
    "VALID_TRANSITIONS",
]
