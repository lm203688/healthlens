"""Flower（flwr）联邦框架 Optional Adapter — HealthLens L3 联邦层

出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3 选型
      「联邦框架：Flower（flwr, Apache-2.0）已有 MONAI / Opacus 集成、
      联邦 Kaplan-Meier 示例，集成成本低。」

**核心命题**：
- Flower 是**optional**：未安装时导出 `HealthLensUnavailableEngine` 哨兵类，
  API 层与测试都不炸；装了以后一键切换。
- **不实现真实训练循环**：本文件只暴露协议接口（server/client 骨架），
  真实联邦训练必须与联调伙伴一起接入（对齐项目零依赖内核原则）。

**明确注释**：
> 「真实联邦训练需伙伴联调后接入。」本 adapter 仅提供协议占位，
> 用于验证：1) Flower 版本 API 未漂移；2) 本项目的 sufficient-stats
> 载荷能透传；3) 中心端 `HierarchicalAggregator` 能作为 aggregator callback
> 挂进 Flower 策略。

设计约束：
- 不 import flwr 顶层（避免未装时导入失败）；try/except 包裹。
- 不启用真实网络端口、不启动线程；server/client 都是纯构造。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.lib.federated.aggregation import AggregationResult, HierarchicalAggregator
from app.lib.federated.sufficient_stats import SufficientStats


# ---------------------------------------------------------------------------
# Optional 依赖装载
# ---------------------------------------------------------------------------


class HealthLensUnavailableEngine(Exception):
    """Optional 依赖（如 flwr）未安装时抛出，供调用方降级到单机仿真。"""

    def __init__(self, engine_name: str, pip_hint: str = ""):
        self.engine_name = engine_name
        self.pip_hint = pip_hint
        msg = f"Optional engine '{engine_name}' is not installed"
        if pip_hint:
            msg += f" (pip install: {pip_hint})"
        super().__init__(msg)


FLWR_AVAILABLE = False
flwr: Any = None  # 装载失败时保持 None，调用方必须判空


try:  # pragma: no cover - 依赖存在性由 monkeypatch 测试覆盖
    import flwr as _flwr  # type: ignore

    flwr = _flwr
    FLWR_AVAILABLE = True
except Exception:  # noqa: BLE001
    # 保持 flwr=None，让下方工厂函数按 optional 语义抛哨兵异常。
    pass


# ---------------------------------------------------------------------------
# Tenant 配置
# ---------------------------------------------------------------------------


@dataclass
class TenantConfig:
    """Flower client 侧的租户配置（不含任何密钥/PII）。"""

    tenant_id: str
    host: str = "0.0.0.0"
    port: int = 50000
    region: str = "cn"
    metrics_interval: int = 60
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Server / Client 骨架
# ---------------------------------------------------------------------------


def make_flower_server(
    aggregator: HierarchicalAggregator,
    strategy: str = "federated_aggregation",
    num_rounds: int = 3,
    min_available: int = 1,
) -> Any:
    """构造 Flower Server 骨架（返回 flwr.server.Server 实例）。

    说明：
    - strategy 目前仅接受 "federated_aggregation"；未来扩展时通过
      `aggregator_cb` 挂到 flwr.strategy.custom。
    - **不启动端口**：本函数只构造对象，端口/线程由部署层决定。
    - aggregator：把本项目的 HierarchicalAggregator 传入，未来在
      Flower round callback 中调用 `aggregate(stats)`。

    Raises:
        HealthLensUnavailableEngine: flwr 未安装。
    """
    if not FLWR_AVAILABLE:
        raise HealthLensUnavailableEngine("flwr", pip_hint="flwr")

    # Flower >=1.x API：flwr.server.Server(num_rounds, strategy)
    if strategy != "federated_aggregation":
        raise ValueError(f"unknown strategy: {strategy!r}")

    server = flwr.server.Server(
        config={"num_rounds": int(num_rounds), "min_available": int(min_available)}
    )
    # 通过属性把本项目 aggregator 挂到 server，供 round callback 访问
    try:
        server.aggregator = aggregator  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        pass
    return server


def make_flower_client(
    tenant_config: TenantConfig,
    aggregator: HierarchicalAggregator | None = None,
) -> Any:
    """构造 Flower Client 骨架（返回 flwr.client.Client 实例）。

    说明：
    - 不实现真实 train step；`Client.__init__` 是 no-op 占位。
    - 载荷约定：client 端在 fit() 内把 SufficientStats 通过 metrics
      通道上传，server 侧收到后交 aggregator。
    - 真实联邦训练需与联调伙伴一起接入（本函数只做协议占位）。

    Raises:
        HealthLensUnavailableEngine: flwr 未安装。
    """
    if not FLWR_AVAILABLE:
        raise HealthLensUnavailableEngine("flwr", pip_hint="flwr")

    # Flower 的 BaseClient 抽象；这里用 flwr.client.NumPyClient 作占位类型
    # 但**不**实例化（避免其构造函数要求 model 参数）。改为直接返回一个
    # 轻量 wrapper，携带 tenant_config + aggregator 供部署层调用。
    client = _HealthLensFlowerClient(
        tenant_config=tenant_config,
        aggregator=aggregator,
    )
    return client


class _HealthLensFlowerClient:
    """轻量 Flower client wrapper（占位，不实现真实训练）。

    部署时部署层应把本 wrapper 的 `send_stats(stats)` 挂到 Flower
    的 fit() 回调里；这里只暴露协议契约。
    """

    def __init__(
        self,
        tenant_config: TenantConfig,
        aggregator: HierarchicalAggregator | None,
    ):
        self.tenant_config = tenant_config
        self.aggregator = aggregator

    def send_stats(self, stats: SufficientStats) -> AggregationResult | None:
        """把本租户的充分统计量交给 aggregator（占位协议方法）。

        实际部署时，中心端会把所有客户端的 stats 汇总后统一聚合；
        这里只演示单个 payload 通过 aggregator 的路径。
        """
        if self.aggregator is None:
            return None
        return self.aggregator.aggregate([stats])
