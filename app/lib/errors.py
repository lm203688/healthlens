"""HealthLens L4/L0 共享错误类型。

引用报告《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4：
「重型库（xgrammar/langfuse/ragas/biomni/pyjson-canonicalize）全部 optional，
未装时 HealthLensUnavailableEngine。」

本模块只定义异常类，不含任何业务逻辑。所有 L4/L0 adapter 在未装依赖时
统一抛出 HealthLensUnavailableEngine，让上层 API 可以映射到
503 Service Unavailable 或返回结构化错误体，fail-loud 而不是静默降级。
"""

from __future__ import annotations


class HealthLensUnavailableEngine(RuntimeError):
    """重型 optional 依赖未安装时抛出。

    属性：
        engine:  未安装的模块名（例如 "xgrammar"、"ragas"、"biomni"）
        hint:    安装建议（例如 "pip install healthlens[xgrammar]"）
    """

    def __init__(self, engine: str, *, hint: str = "") -> None:
        self.engine = engine
        self.hint = hint
        super().__init__(
            f"HealthLens {engine!r} engine unavailable. Install hint: {hint or 'pip install ' + engine}"
        )


class HealthLensAuditFailure(RuntimeError):
    """协议审计发现违规时可选抛出（默认不抛，只报事实）。

    run_full_audit(strict=True) 时，如果任一检查项 fail 且 severity=error
    则抛出本异常。默认 run_full_audit() 只返回报告 dict，不抛异常。
    """

    def __init__(self, report: dict) -> None:
        self.report = report
        super().__init__(f"Protocol audit failed: {self._summary()}")

    def _summary(self) -> str:
        fails = []
        for section, body in self.report.items():
            if isinstance(body, dict):
                for check, item in body.items():
                    if isinstance(item, dict) and item.get("status") == "fail":
                        fails.append(f"{section}.{check}")
        return "; ".join(fails[:10]) or "unknown"
