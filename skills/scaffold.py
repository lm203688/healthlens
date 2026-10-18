"""
skills/scaffold.py — Skill 加载、发现、执行框架

借鉴自 Hunter/AgentPit 的 SKILL 架构：
- Skill = 目录（SKILL.md + run.py）
- SkillRegistry 负责发现、加载、缓存
- 支持 user-skills/ 热加载（不重启即可注册新 Skill）
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SKILL_DIR = Path(__file__).resolve().parent
USER_SKILL_DIR = SKILL_DIR / "user-skills"
HEALTHLENS_ROOT = SKILL_DIR.parent


@dataclass
class SkillManifest:
    """Skill 元信息，从 SKILL.md 解析。"""

    name: str
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    methodology: str = ""
    dependencies: list[str] = field(default_factory=list)
    has_run: bool = False
    has_test: bool = False
    path: Path = field(default_factory=Path)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "dependencies": self.dependencies,
            "has_run": self.has_run,
            "has_test": self.has_test,
            "path": str(self.path),
        }

    @classmethod
    def from_dir(cls, skill_dir: Path) -> "SkillManifest":
        """从 SKILL.md 解析 Manifest。"""
        manifest = cls(name=skill_dir.name, path=skill_dir)

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            text = skill_md.read_text(encoding="utf-8")
            lines = text.splitlines()

            # 标题行 → description
            for line in lines:
                if line.startswith("# "):
                    manifest.description = line[2:].strip()
                    break

            # ## 输入
            in_section = False
            for line in lines:
                if line.startswith("## 输入"):
                    in_section = True
                    continue
                if in_section and line.startswith("## "):
                    break
                if in_section and line.strip().startswith("- "):
                    manifest.inputs.append(line.strip()[2:].strip())

            # ## 输出
            out_section = False
            for line in lines:
                if line.startswith("## 输出"):
                    out_section = True
                    continue
                if out_section and line.startswith("## "):
                    break
                if out_section and line.strip().startswith("- "):
                    manifest.outputs.append(line.strip()[2:].strip())

            # ## 方法论
            meth_section = False
            meth_lines: list[str] = []
            for line in lines:
                if line.startswith("## 方法论"):
                    meth_section = True
                    continue
                if meth_section and line.startswith("## "):
                    break
                if meth_section:
                    meth_lines.append(line)
            manifest.methodology = "\n".join(meth_lines).strip()

            # ## 前置依赖
            dep_section = False
            for line in lines:
                if line.startswith("## 前置依赖"):
                    dep_section = True
                    continue
                if dep_section and line.startswith("## "):
                    break
                if dep_section and line.strip().startswith("- "):
                    manifest.dependencies.append(line.strip()[2:].strip())

        manifest.has_run = (skill_dir / "run.py").exists()
        manifest.has_test = (skill_dir / "test.py").exists()

        return manifest


class SkillRegistry:
    """Skill 注册表。发现、加载、执行 Skill。"""

    def __init__(self, user_skills_dir: Path | None = None):
        self._manifests: dict[str, SkillManifest] = {}
        self._runners: dict[str, Callable[..., dict]] = {}
        self._user_dir: Path = user_skills_dir or USER_SKILL_DIR

    def discover(self, extra_dirs: list[Path] | None = None) -> list[SkillManifest]:
        """扫描技能目录，返回所有 Manifest 列表。"""
        dirs_to_scan: list[Path] = [SKILL_DIR]
        if self._user_dir.exists():
            dirs_to_scan.append(self._user_dir)
        if extra_dirs:
            dirs_to_scan.extend(extra_dirs)

        seen: set[Path] = set()
        for base in dirs_to_scan:
            if not base.exists():
                continue
            for entry in sorted(base.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name in ("__pycache__", "user-skills"):
                    continue
                if entry.resolve() in seen:
                    continue
                seen.add(entry.resolve())

                if not (entry / "SKILL.md").exists() and not (entry / "run.py").exists():
                    continue

                try:
                    manifest = SkillManifest.from_dir(entry)
                    self._manifests[manifest.name] = manifest
                except Exception:
                    continue

        return list(self._manifests.values())

    def list(self) -> list[SkillManifest]:
        if not self._manifests:
            self.discover()
        return list(self._manifests.values())

    def get(self, name: str) -> SkillManifest | None:
        if name not in self._manifests:
            self.discover()
        return self._manifests.get(name)

    def load_runner(self, name: str) -> Callable[..., dict] | None:
        """加载 Skill 的 run.py，返回 run(**kwargs) 函数。"""
        if name in self._runners:
            return self._runners[name]

        manifest = self.get(name)
        if not manifest or not manifest.has_run:
            return None

        run_path = manifest.path / "run.py"
        spec = importlib.util.spec_from_file_location(f"skill_{name}_run", run_path)
        if spec is None or spec.loader is None:
            return None

        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"skill_{name}_run"] = mod
        spec.loader.exec_module(mod)

        runner = getattr(mod, "run", None)
        if runner is None:
            return None

        self._runners[name] = runner
        return runner

    def execute(self, name: str, **kwargs: Any) -> dict:
        """执行 Skill。"""
        runner = self.load_runner(name)
        if runner is None:
            raise RuntimeError(f"Skill '{name}' 未找到或无 run.py")
        return runner(**kwargs)

    def test(self, name: str, verbose: bool = False) -> dict:
        """运行 Skill 的 test.py（如果存在），返回测试结果。"""
        manifest = self.get(name)
        if not manifest or not manifest.has_test:
            return {"status": "no_test", "name": name}

        test_path = manifest.path / "test.py"
        try:
            result = subprocess.run(
                [sys.executable, str(test_path)],
                capture_output=True,
                text=True,
                cwd=str(HEALTHLENS_ROOT),
                timeout=60,
            )
            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "name": name,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "name": name}
        except Exception as exc:
            return {"status": "error", "name": name, "error": str(exc)}

    def export_json(self) -> str:
        """导出所有 Skill 元信息为 JSON。"""
        return json.dumps(
            [m.to_dict() for m in self.list()],
            ensure_ascii=False,
            indent=2,
        )


# 全局默认注册表
_registry = SkillRegistry()


def discover_skills() -> list[SkillManifest]:
    return _registry.discover()


def load_skill(name: str) -> SkillManifest | None:
    return _registry.get(name)


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HealthLens Skill 管理")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出所有 Skill")
    sub.add_parser("show", help="显示 Skill 详情").add_argument("name")
    sub.add_parser("test", help="运行 Skill 测试").add_argument("name")
    sub.add_parser("export", help="导出 JSON")

    args = parser.parse_args()

    if args.cmd == "list":
        manifests = _registry.list()
        print(f"共 {len(manifests)} 个 Skill：\n")
        for m in manifests:
            run_mark = "✓" if m.has_run else "─"
            test_mark = "✓" if m.has_test else "─"
            print(f"  [{run_mark}][{test_mark}] {m.name:25s} {m.description}")
        print()

    elif args.cmd == "show":
        m = _registry.get(args.name)
        if not m:
            print(f"Skill '{args.name}' 不存在")
            sys.exit(1)
        skill_md = m.path / "SKILL.md"
        if skill_md.exists():
            print(skill_md.read_text(encoding="utf-8"))
        else:
            print(json.dumps(m.to_dict(), ensure_ascii=False, indent=2))

    elif args.cmd == "test":
        result = _registry.test(args.name, verbose=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "export":
        print(_registry.export_json())

    else:
        parser.print_help()
