"""重型科学计算库统一异常 —— L1-1（2026-10-15）

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L1-1

内核原则：HealthLens 保持零第三方重型依赖（dowhy / pymc / econml / flwr /
torch 等）。当某个重型库不可用且被调用时，adapter 抛出本异常，让上层明确
告知"该能力不可用，需安装 .[science] extra"——绝不静默降级产出「看起来正常」
的结果。

统一字段：
    engine_name      —— 逻辑引擎名（如 "dowhy" / "pymc"）
    required_package —— 需要装的 pip 包（如 "dowhy"）
    pip_command      —— 一键安装命令（含 science extra）
"""
from __future__ import annotations


class HealthLensUnavailableEngine(RuntimeError):
    """重型科学计算引擎不可用（未安装或加载失败）。

    设计要点：
    - 继承 RuntimeError 而非 ImportError：让上层（API、bandit、聚合器）
      可以在同一个 try 里区分"引擎缺失"与"输入错误"。
    - 三个字段全部在消息里重复出现，方便日志 / HTTP 错误响应直接 str(exc) 落
      到前端，用户一眼知道怎么装。
    """

    def __init__(
        self,
        engine_name: str,
        required_package: str,
        extra_hint: str | None = None,
        detail: str | None = None,
    ):
        self.engine_name = engine_name
        self.required_package = required_package
        self.pip_command = (
            f"pip install -e '.[{extra_hint}]'" if extra_hint else f"pip install {required_package}"
        )
        msg = (
            f"重型引擎 {engine_name!r} 不可用（缺少 {required_package!r}）。"
            f"请安装：{self.pip_command}"
        )
        if detail:
            msg += f" | 详情：{detail}"
        super().__init__(msg)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"HealthLensUnavailableEngine(engine_name={self.engine_name!r}, "
            f"required_package={self.required_package!r})"
        )
