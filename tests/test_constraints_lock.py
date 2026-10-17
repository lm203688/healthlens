"""D2/H2 依赖锁定验证（2026-10-17）

10-16 全面评估报告 H2：「无 lock/constraints 文件，requirements 全 >= 无上界」
→ 三个月后装出的不是同一个系统，Zenodo DOI 的 "reproducible" 承诺被架空。

本测试守住三个不变量：
1. constraints.txt 存在且非空
2. requirements.txt 的每个直接依赖都能在 constraints.txt 中找到 `==` 精确锁定
3. constraints.txt 内没有 `>=` / `<=` / `~=` 等范围运算符（必须是 == 精确锁定）

失败含义：依赖锁定被打破，Zenodo 复现承诺失效——立即阻塞 CI。
"""
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS_PATH = REPO_ROOT / "constraints.txt"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"


def _strip_comments(line: str) -> str:
    """去掉行首空白 + 行尾 # 注释，保留 inline 空格后的注释剔除。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    # 保留 == 前内容（含行尾注释前的空白）
    if " #" in line:
        line = line.split(" #")[0].strip()
    return line


def _parse_specs(text: str) -> dict[str, str]:
    """解析 pip 格式的依赖声明，返回 {name: spec_string}。"""
    specs = {}
    for raw in text.splitlines():
        line = _strip_comments(raw)
        if not line:
            continue
        # 去掉 pip options 行
        if line.startswith("-"):
            continue
        # 找到分隔符（== / >= / <= / ~= / > / < / !=）
        # 优先匹配 == 精确锁定
        m = re.match(r"^([A-Za-z0-9_.\-]+)[\s]*==\s*([^,;\s]+)", line)
        if m:
            name, ver = m.group(1).lower(), m.group(2)
            specs[name] = f"=={ver}"
            continue
        # 允许 >=（仅 requirements.txt 允许）
        m = re.match(r"^([A-Za-z0-9_.\-]+)[\s]*>=\s*([^,;\s]+)", line)
        if m:
            name, ver = m.group(1).lower(), m.group(2)
            specs[name] = f">={ver}"
            continue
    return specs


@pytest.mark.parametrize(
    "target_file", [CONSTRAINTS_PATH, REQUIREMENTS_PATH],
    ids=["constraints.txt", "requirements.txt"],
)
def test_lock_file_exists(target_file: Path):
    """requirements.txt 与 constraints.txt 必须同时存在。"""
    assert target_file.exists(), f"{target_file.name} 不存在——依赖锁定失效"
    content = target_file.read_text(encoding="utf-8")
    assert len(content.strip()) > 50, f"{target_file.name} 内容过短，可能为空壳"


def test_constraints_exact_pins_only():
    """constraints.txt 必须全部使用 == 精确锁定，禁止范围运算符。

    存在 >= / ~= / <= 等即视为「半锁定」，等同未锁定。
    """
    content = CONSTRAINTS_PATH.read_text(encoding="utf-8")
    specs = _parse_specs(content)

    violations = {}
    for raw in content.splitlines():
        line = _strip_comments(raw)
        if not line or line.startswith("-"):
            continue
        # 检查是否有非 == 的范围运算符
        for op in (">=", "<=", "~=", "!=", ">", "<"):
            # 排除 == 之后的 =（如 ==1.0）
            if op in line:
                # 找到 op 位置
                idx = line.find(op)
                # 确认不是 == 的第二个 =
                if op == "=" and idx > 0 and line[idx - 1] == "=":
                    continue
                # 检查 op 前是否有 =（即 == 之后）
                prev_char = line[idx - 1] if idx > 0 else ""
                if op in ("=", ">=", "<=") and prev_char == "=":
                    continue
                if op in (">=", "<=") or (op == "~=") or (op == "!="):
                    violations[line] = op
                    break

    assert not violations, (
        f"constraints.txt 应全部使用 == 精确锁定，发现范围运算符：\n"
        + "\n".join(f"  {line!r} 含 {op!r}" for line, op in violations.items())
    )


def test_all_requirements_locked():
    """requirements.txt 中每个直接依赖都能在 constraints.txt 中找到 == 精确锁定。"""
    req_specs = _parse_specs(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    con_specs = _parse_specs(CONSTRAINTS_PATH.read_text(encoding="utf-8"))

    missing = []
    for name, req_spec in sorted(req_specs.items()):
        if name not in con_specs:
            missing.append((name, req_spec, "not in constraints.txt"))
        elif not con_specs[name].startswith("=="):
            missing.append((name, req_spec, f"not exact pin: {con_specs[name]}"))

    assert not missing, (
        f"以下 requirements.txt 依赖在 constraints.txt 中未被精确锁定：\n"
        + "\n".join(f"  {name}: req={r}  con_state={c}" for name, r, c in missing)
    )


def test_no_range_ops_in_constraints():
    """严格扫描 constraints.txt：不允许出现 >= / ~= / <= 等范围运算符。"""
    text = CONSTRAINTS_PATH.read_text(encoding="utf-8")
    # 逐行扫描（跳注释与空行）
    bad = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comments(raw)
        if not line or line.startswith("-"):
            continue
        # 检测范围运算符（排除 == 中的第二个 =）
        # 用正则匹配独立的范围运算符
        if re.search(r"~=", line):
            bad.append((lineno, "tilde-equal", line))
        elif re.search(r"(?<!=)>=(?!>)", line):
            bad.append((lineno, "greater-equal", line))
        elif re.search(r"(?<!=)<=", line):
            bad.append((lineno, "less-equal", line))
        elif re.search(r"(?<![=])!=(?!=)", line):
            bad.append((lineno, "not-equal", line))
    assert not bad, (
        f"constraints.txt 中发现范围运算符（应全部使用 ==）：\n"
        + "\n".join(f"  line {ln}: [{op}] {line}" for ln, op, line in bad)
    )


def test_requirements_all_have_lower_bounds():
    """requirements.txt 必须为每个直接依赖声明下界（>= X.Y.Z）。

    否则 pip 会选到任意版本，破坏可复现性。
    """
    text = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    missing_lower = []
    for raw in text.splitlines():
        line = _strip_comments(raw)
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # 允许 [extras]，如 sqlalchemy[asyncio]>=2.0
        if not re.match(r"^[A-Za-z0-9_.\-]+(\[[^\]]+\])?\s*>=\s*[\d.]+", line):
            missing_lower.append(line)
    assert not missing_lower, (
        f"requirements.txt 中以下依赖缺少 >= 下界：\n"
        + "\n".join(f"  {line}" for line in missing_lower)
    )


def test_constraints_file_is_current_relative_to_requirements():
    """requirements.txt 中的每个包名都必须出现在 constraints.txt 中（防止锁文件滞后）。"""
    req_names = set(_parse_specs(REQUIREMENTS_PATH.read_text(encoding="utf-8")).keys())
    con_names = set(_parse_specs(CONSTRAINTS_PATH.read_text(encoding="utf-8")).keys())
    # requirements 中的所有包必须在 constraints 中
    missing = req_names - con_names
    # 允许 extras 名差异（如 sqlalchemy[asyncio] vs SQLAlchemy），做一次宽松匹配
    missing_lower = {n.split("[")[0] for n in missing}
    con_lower = {n for n in con_names}
    missing_lower = missing_lower - con_lower
    assert not missing_lower, (
        f"requirements.txt 中的以下包未在 constraints.txt 中锁定：{sorted(missing_lower)}\n"
        "→ 生成新 constraints：pip freeze > constraints.txt"
    )
