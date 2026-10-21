"""M03 P0-2：三处数据源集合一致性锁死。

背景（task #133）：

三个集合在**跨语言**（Python 后端 + JSX 前端）和**跨命名空间**（source_type 是集成标识符
vs OW provider.id 是品牌 slug）的边界上漂移，任何一处增删不同步，用户就会遇到：

- 前端画出图标但后端 add_connection 返回 400（ALLOWED_SOURCE_TYPES 缺项）
- 后端 OW_PROVIDERS 增项但前端图标显示不出 emoji
- 新增 provider.id 意外和 ALLOWED_SOURCE_TYPES 命名空间撞车

本测试在**不引入前端 Node 依赖**的前提下，通过正则解析 WearableDevices.jsx 的
``PROVIDER_ICONS`` 常量、直接 import 后端两个模块常量，做三层强一致校验。

三层集合语义：

1. ``ALLOWED_SOURCE_TYPES`` —— 集成标识符命名空间（``huawei_health`` / ``apple_health`` /
   ``open_wearables`` 等）。
2. ``OW_PROVIDERS[*].id`` —— Open Wearables 品牌 slug 命名空间（``garmin`` / ``oura`` /
   ``google_health`` 等）。
3. 前端 ``PROVIDER_ICONS`` keys —— 必须精确等于 ``OW_PROVIDERS[*].id``，否则 UI 展示与后端
   可用设备不一致。

双入口重叠（withings / google_health）是**有意为之**：这些品牌既有自己独立的 OAuth 集成，
也挂在 Open Wearables 下面。测试把这个交集显式锁死，防止有人误以为要"去重"。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ICON_MAP_PATH = REPO_ROOT / "frontend" / "src" / "components" / "WearableDevices.jsx"


# ---------------------------------------------------------------------------
# 集合提取
# ---------------------------------------------------------------------------

def _load_backend_sets() -> tuple[set[str], list[dict], set[str]]:
    """从后端模块取三个真实集合，避免测试里复制字面量。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.api import connections  # type: ignore[import-not-found]

    return (
        set(connections.ALLOWED_SOURCE_TYPES),
        list(connections.OW_PROVIDERS),
        {p["id"] for p in connections.OW_PROVIDERS},
    )


_PROVIDER_ICONS_RE = re.compile(
    r"PROVIDER_ICONS\s*=\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_ICON_PAIR_RE = re.compile(r"(?P<key>[A-Za-z_][\w-]*)\s*:\s*['\"]")


def _load_frontend_provider_icons() -> set[str]:
    """从 WearableDevices.jsx 提取 PROVIDER_ICONS 的 keys。

    用正则而不是执行 JS，避免测试机强依赖 node/npm。匹配 ``provider_id: '...'`` 形式，
    忽略多行续行和注释。
    """
    if not FRONTEND_ICON_MAP_PATH.exists():
        pytest.fail(
            f"前端 PROVIDER_ICONS 映射文件不存在：{FRONTEND_ICON_MAP_PATH}",
            pyfuncargs=None,  # pragma: no cover
        )
    text = FRONTEND_ICON_MAP_PATH.read_text(encoding="utf-8")

    match = _PROVIDER_ICONS_RE.search(text)
    if not match:
        pytest.fail(
            f"未在 {FRONTEND_ICON_MAP_PATH} 中匹配到 PROVIDER_ICONS 常量",
            pyfuncargs=None,
        )

    return set(_ICON_PAIR_RE.findall(match.group("body")))


# ---------------------------------------------------------------------------
# 字面集合快照（防止集合无意识漂移）
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def source_sets():
    allowed, ow_providers, ow_ids = _load_backend_sets()
    frontend_keys = _load_frontend_provider_icons()
    return {
        "allowed": allowed,
        "ow_providers": ow_providers,
        "ow_ids": ow_ids,
        "frontend_icons": frontend_keys,
    }


def test_allowed_source_types_snapshot(source_sets):
    """ALLOWED_SOURCE_TYPES 集合显式锁死。新增/删除项必须显式改这一行。"""
    expected = {
        "huawei_health",
        "apple_health",
        "withings",
        "xiaomi_health",
        "hospital_lis",
        "open_wearables",
        "google_health",
    }
    actual = source_sets["allowed"]
    assert actual == expected, (
        f"ALLOWED_SOURCE_TYPES 漂移。\n"
        f"  期望: {sorted(expected)}\n"
        f"  实际: {sorted(actual)}\n"
        f"  新增: {sorted(actual - expected)}\n"
        f"  缺失: {sorted(expected - actual)}\n"
        f"  → 若是有意的扩充，请同步更新本测试期望值 + 检查 OW_PROVIDERS/前端 PROVIDER_ICONS。"
    )


def test_ow_providers_ids_snapshot(source_sets):
    """OW_PROVIDERS ids 集合显式锁死。"""
    expected = {
        "garmin",
        "oura",
        "whoop",
        "polar",
        "suunto",
        "strava",
        "fitbit",
        "ultrahuman",
        "withings",
        "google_health",
    }
    actual = source_sets["ow_ids"]
    assert actual == expected, (
        f"OW_PROVIDERS[*].id 漂移。\n"
        f"  期望: {sorted(expected)}\n"
        f"  实际: {sorted(actual)}\n"
        f"  新增: {sorted(actual - expected)}\n"
        f"  缺失: {sorted(expected - actual)}\n"
        f"  → 请同步更新前端 WearableDevices.jsx 的 PROVIDER_ICONS 常量。"
    )


# ---------------------------------------------------------------------------
# 结构完整性
# ---------------------------------------------------------------------------

def test_ow_providers_no_duplicate_ids(source_sets):
    """同一 provider.id 不允许重复（前端 select 会 key 冲突）。"""
    ids = [p["id"] for p in source_sets["ow_providers"]]
    dupes = {x for x in ids if ids.count(x) > 1}
    assert not dupes, f"OW_PROVIDERS 出现重复 id: {sorted(dupes)}"


def test_ow_providers_schema_fields(source_sets):
    """每条 OW_PROVIDER 必须四字段齐全（前端渲染依赖 name/icon/type 三字段）。"""
    required = {"id", "name", "type", "icon"}
    for p in source_sets["ow_providers"]:
        keys = set(p.keys())
        assert required <= keys, (
            f"OW_PROVIDER 缺字段：id={p.get('id')!r}，实际字段={sorted(keys)}，缺少 {sorted(required - keys)}"
        )
        for k in ("id", "name"):
            assert isinstance(p[k], str) and p[k], f"OW_PROVIDER[{p.get('id')!r}].{k} 不能为空"


# ---------------------------------------------------------------------------
# 跨语言一致性（后端 vs 前端）
# ---------------------------------------------------------------------------

def test_frontend_icons_match_ow_providers(source_sets):
    """前端 PROVIDER_ICONS keys 必须精确等于 OW_PROVIDERS[*].id。

    方向 A：前端不能画出后端不认识的 provider（否则点击连接后端 400）。
    方向 B：后端新增 provider 但前端没画图标（用户看不到新设备）。
    """
    frontend = source_sets["frontend_icons"]
    backend = source_sets["ow_ids"]
    only_frontend = sorted(frontend - backend)
    only_backend = sorted(backend - frontend)
    assert not only_frontend, (
        f"前端 PROVIDER_ICONS 出现后端 OW_PROVIDERS 没有的 provider：{only_frontend}。"
        f"后端连不上这些设备。"
    )
    assert not only_backend, (
        f"后端 OW_PROVIDERS 有 provider 但前端 PROVIDER_ICONS 缺图标：{only_backend}。"
        f"用户看不到这些新设备。"
    )


# ---------------------------------------------------------------------------
# 语义一致性（跨命名空间）
# ---------------------------------------------------------------------------

def test_open_wearables_is_canonical_aggregate(source_sets):
    """``open_wearables`` 是 OW 系列的集成标识符，必须在 ALLOWED_SOURCE_TYPES 里。"""
    assert "open_wearables" in source_sets["allowed"], (
        "缺 'open_wearables' —— OW 系列设备的统一入口标识符不存在，前端所有 OW 连接会 400。"
    )
    assert "open_wearables" not in source_sets["ow_ids"], (
        "'open_wearables' 不能同时出现在 OW_PROVIDERS ids 里 —— 它是集成 slug，不是品牌 slug。"
    )


def test_dual_entry_overlap_locked(source_sets):
    """双入口重叠（withings / google_health）是**有意为之**。

    这两个品牌既有独立 OAuth 集成（在 ALLOWED_SOURCE_TYPES 里），也挂在 Open Wearables
    下面（在 OW_PROVIDERS ids 里）。测试锁死这个交集，防止有人误判为冗余而删掉。
    """
    actual_overlap = sorted(source_sets["ow_ids"] & source_sets["allowed"])
    expected_overlap = sorted({"google_health", "withings"})
    assert actual_overlap == expected_overlap, (
        f"双入口重叠集合漂移。\n"
        f"  期望: {expected_overlap}\n"
        f"  实际: {actual_overlap}\n"
        f"  → 若新增了独立 OAuth 集成，请同步更新本测试的 expected_overlap。\n"
        f"  → 若从 OW 移除某 provider，请同步更新 OW_PROVIDERS 快照测试。"
    )


def test_ow_only_providers_reachable_via_open_wearables(source_sets):
    """非重叠的 OW provider（garmin/oura/whoop/... 等）只能靠 ``open_wearables`` 接入。

    这个不变量隐含在 add_connection 的代码路径里：连接 OW provider 时，body.source_type
    必须是 'open_wearables'，不是 provider.id。若有人误以为 provider.id 也是合法
    source_type，用户会 400。
    """
    open_wearables_bridge = source_sets["allowed"] & {"open_wearables"}
    assert open_wearables_bridge == {"open_wearables"}
    ow_only = sorted(source_sets["ow_ids"] - source_sets["allowed"])
    assert ow_only, "OW_PROVIDERS 应至少有若干只走 open_wearables 桥接的 provider"
    # 这些 provider 只能通过 'open_wearables' 接入 —— 由上面 open_wearables_bridge 保证
    # 这里仅做存在性 sanity check，防 CI 空跑


def test_no_namespace_collision_beyond_dual_entry(source_sets):
    """除双入口重叠外，两个命名空间不应有意重叠。

    ALLOWED_SOURCE_TYPES 是 snake_case 集成标识符（huawei_health / apple_health /
    hospital_lis 等），OW_PROVIDERS[*].id 是品牌 slug。若新增 provider.id 意外和
    某个 ALLOWED_SOURCE_TYPES 命名冲突（例如给 Apple 单独开个 OW 入口叫 'apple_health'），
    会同时通过 body.source_type 和 OW provider 两个路径都能创建连接，数据归属不确定。
    """
    overlap = source_sets["ow_ids"] & source_sets["allowed"]
    allowed_overlap = {"google_health", "withings"}
    unexpected = sorted(overlap - allowed_overlap)
    assert not unexpected, (
        f"发现未在双入口清单中的命名空间冲突：{unexpected}。\n"
        f"  ALLOWED_SOURCE_TYPES 与 OW_PROVIDERS[*].id 不应在双入口清单之外重叠。\n"
        f"  → 若是有意新增双入口，请同步 test_dual_entry_overlap_locked。"
    )
