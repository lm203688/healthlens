"""Schrödinger 计算化学套件适配层（需自备商业许可）

这不是「数据库连接器」，而是**本地/远程作业执行适配器**。它只做三件事：

  1. 探测：本机（或 SSH 目标）是否装了套件、哪些模块可用、许可是否就绪；
  2. 执行：把模块名 + 参数翻译成命令行，跑作业，收集产物；
  3. 诚实降级：没装 / 无许可 / 模块不存在 → 抛 `license_unavailable` 或
     `not_implemented`，**绝不返回编造的对接分数或自由能**。

为什么必须这么设计：
    计算化学的数值一旦造假，下游（结合能、ADMET、FEP）会连锁失真，且很难被
    肉眼发现。本项目历史上已经吃过「静默 except 吞掉 axis scorer」的亏
    （见 fusion_engine 的 fail-loud 改造），这里不再重犯。

配置（环境变量，任一为空则该能力不可用）：
    SCHRODINGER          套件安装根目录（如 /opt/schrodinger/2024-4）
    SCHRODINGER_SSH      远程主机（如 user@gpu-node），留空则本机执行
    SCHRODINGER_LICENSE  许可服务器地址（可选，仅用于展示）

注意：许可与模块可用性受厂商授权约束，本适配层不做任何绕过。
"""
from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.connectors.reference.base import ReferenceError, ReferenceSource, SourceCapability


@dataclass(frozen=True)
class CaddModule:
    key: str
    binary: str
    label: str
    purpose: str
    needs_license: bool = True


#: 模块 → 可执行文件。键名与官方命令行一致，便于排查。
MODULES: dict[str, CaddModule] = {
    "prepwizard": CaddModule("prepwizard", "prepwizard", "PrepWizard", "蛋白准备：加氢、补缺失原子/loop、优化质子化"),
    "ligprep": CaddModule("ligprep", "ligprep", "LigPrep", "配体准备：3D 构象生成、电离态、互变异构"),
    "epik": CaddModule("epik", "epik", "Epik", "pKa 与质子化状态预测"),
    "glide": CaddModule("glide", "glide", "Glide", "分子对接：HTVS / SP / XP"),
    "prime_mmgbsa": CaddModule("prime_mmgbsa", "prime_mmgbsa", "Prime MM-GBSA", "结合自由能重打分"),
    "desmond": CaddModule("desmond", "desmond", "Desmond", "GPU 分子动力学模拟"),
    "qikprop": CaddModule("qikprop", "qikprop", "QikProp", "ADMET 性质预测"),
    "sitemap": CaddModule("sitemap", "sitemap", "SiteMap", "结合位点识别与打分"),
    "watermap": CaddModule("watermap", "watermap", "WaterMap", "水分子热力学分析"),
    "fep_plus": CaddModule("fep_plus", "run_fep", "FEP+", "自由能微扰（相对结合自由能）"),
    "structconvert": CaddModule("structconvert", "structconvert", "StructConvert", "结构格式互转（PDB/SDF/MAE）"),
}


class SchrodingerCADD(ReferenceSource):
    SOURCE = "schrodinger"
    DISPLAY_NAME = "Schrödinger CADD Suite"
    BASE_URL = ""
    REQUIRES_KEY = True
    DEFAULT_TTL = 0.0

    def __init__(self, root: str | None = None, ssh_host: str | None = None) -> None:
        super().__init__()
        self.root = Path(root or os.getenv("SCHRODINGER", "")).expanduser() if (root or os.getenv("SCHRODINGER")) else None
        self.ssh_host = (ssh_host or os.getenv("SCHRODINGER_SSH", "")).strip() or None

    # -- 探测 ---------------------------------------------------------------
    def installed(self) -> bool:
        return bool(self.root and self.root.is_dir())

    def _binary_path(self, module: CaddModule) -> Path | None:
        if not self.root:
            return None
        candidate = self.root / module.binary
        if candidate.exists():
            return candidate
        # 部分模块在 utilities/ 或 run 下
        for sub in ("utilities", "bin"):
            alt = self.root / sub / module.binary
            if alt.exists():
                return alt
        return None

    def available_modules(self) -> list[dict[str, Any]]:
        rows = []
        for key, module in MODULES.items():
            path = self._binary_path(module)
            rows.append(
                {
                    "key": key,
                    "label": module.label,
                    "purpose": module.purpose,
                    "installed": path is not None,
                    "path": str(path) if path else None,
                }
            )
        return rows

    def license_present(self) -> bool:
        """粗粒度许可探测。

        不解析许可内容（厂商格式不公开且随版本变化），只看两件事：
          - 是否配置了许可服务器地址；
          - 套件目录下是否存在 license 相关文件。
        结论只作为提示，真正判定交给实际作业（作业失败会明确报错）。
        """
        if os.getenv("SCHRODINGER_LICENSE"):
            return True
        if not self.root:
            return False
        for name in ("license", "licenses", "license.txt"):
            if (self.root / name).exists():
                return True
        return False

    async def capabilities(self) -> dict[str, Any]:
        modules = self.available_modules()
        installed_count = sum(1 for m in modules if m["installed"])
        return {
            "installed": self.installed(),
            "root": str(self.root) if self.root else None,
            "ssh_host": self.ssh_host,
            "license_hint": self.license_present(),
            "modules": modules,
            "installed_module_count": installed_count,
            "usable": self.installed() and installed_count > 0,
            "note": (
                "需自备 Schrödinger 商业许可；本适配层不做任何绕过，"
                "未安装或无许可时一律报 license_unavailable"
            ),
            "source": self.SOURCE,
        }

    # -- 执行 ---------------------------------------------------------------
    async def run_job(
        self,
        module_key: str,
        args: list[str],
        *,
        workdir: str | None = None,
        timeout_s: float = 3600.0,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """执行一个 CADD 作业。

        只有 `capabilities()["usable"]` 为真时才允许调用；否则抛
        `license_unavailable`，避免上层拿到空结果误以为是「算出来是 0」。
        """
        module = MODULES.get(module_key)
        if module is None:
            raise ReferenceError(
                "not_implemented", self.SOURCE, f"未知模块 {module_key!r}；可用：{sorted(MODULES)}"
            )
        if not self.installed():
            raise ReferenceError(
                "license_unavailable",
                self.SOURCE,
                "未检测到 Schrödinger 安装（设置 SCHRODINGER 环境变量指向安装根目录）",
            )
        binary = self._binary_path(module)
        if binary is None:
            raise ReferenceError(
                "license_unavailable",
                self.SOURCE,
                f"模块 {module.key} 的可执行文件不存在（可能未授权该模块）",
            )

        workdir_path = Path(workdir).expanduser() if workdir else None
        if workdir_path and not workdir_path.is_dir():
            raise ReferenceError("invalid_input", self.SOURCE, f"workdir 不存在: {workdir_path}")

        if self.ssh_host:
            cmd = ["ssh", self.ssh_host, str(binary), *args]
        else:
            cmd = [str(binary), *args]

        merged_env = {**os.environ, **(env or {})}
        started = asyncio.get_event_loop().time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir_path) if workdir_path else None,
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ReferenceError("license_unavailable", self.SOURCE, f"无法启动 {binary}: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise ReferenceError(
                "timeout", self.SOURCE, f"{module.label} 超过 {timeout_s}s 未完成，已终止"
            ) from exc

        elapsed = round(asyncio.get_event_loop().time() - started, 2)
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            # 许可类失败最常见，单独归类，便于上层给出"请检查许可"的提示
            lowered = (out_text + err_text).lower()
            code = "license_unavailable" if any(
                k in lowered for k in ("license", "licensing", "no such feature")
            ) else "upstream_error"
            raise ReferenceError(
                code,
                self.SOURCE,
                f"{module.label} 退出码 {proc.returncode}: {err_text[:400] or out_text[:400]}",
            )

        return {
            "module": module.key,
            "label": module.label,
            "command": cmd,
            "workdir": str(workdir_path) if workdir_path else None,
            "elapsed_s": elapsed,
            "returncode": proc.returncode,
            "stdout_tail": out_text[-4000:],
            "stderr_tail": err_text[-2000:],
            "artifacts": _list_artifacts(workdir_path),
            "source": self.SOURCE,
        }

    # -- 契约 ---------------------------------------------------------------
    async def health(self) -> dict[str, Any]:
        caps = await self.capabilities()
        if not caps["usable"]:
            raise ReferenceError("license_unavailable", self.SOURCE, "套件未安装或模块不可用")
        return {"status": "ok", "modules": caps["installed_module_count"]}

    def capability(self) -> SourceCapability:
        return SourceCapability(
            source=self.SOURCE,
            display_name=self.DISPLAY_NAME,
            base_url="(local / ssh)",
            requires_key=True,
            key_present=self.installed(),
            operations=["capabilities", "run_job"],
            rate_limit="受许可并发数约束",
            notes="需自备商业许可；无许可时报 license_unavailable，绝不伪造数值",
        )


def _list_artifacts(workdir: Path | None, limit: int = 40) -> list[dict[str, Any]]:
    if not workdir or not workdir.is_dir():
        return []
    files = []
    for path in sorted(workdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            files.append({"name": path.name, "size_bytes": path.stat().st_size})
        if len(files) >= limit:
            break
    return files
