"""
数据库初始化脚本

创建 schema 表结构 + 种子数据：
1. 创建所有 ORM 模型对应的表
2. 插入默认配置（八轴定义、安全规则、风险阈值）
3. 插入示例用户（用于开发/演示）
4. 插入 100 条验证案例（合成数据）

用法：
  python tools/db_init.py            # 完整初始化
  python tools/db_init.py --schema   # 只建表
  python tools/db_init.py --seed     # 只插数据
  python tools/db_init.py --cases    # 只扩案例
"""
from __future__ import annotations
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 延迟加载 ORM（避免 FastAPI 依赖）
def _get_orm():
    import importlib.util

    db_path = ROOT / "app" / "core" / "database.py"
    if db_path.exists():
        spec = importlib.util.spec_from_file_location("hl_database", db_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["hl_database"] = mod
            spec.loader.exec_module(mod)
            return mod
    return None


# =========================================================================
# Schema 初始化（如果 ORM 可用）
# =========================================================================

def init_schema():
    orm = _get_orm()
    if orm is None:
        print("[SKIP] 无 ORM 模块 (app/core/database.py)，跳过 schema 初始化")
        return
    try:
        Base = getattr(orm, "Base", None)
        engine = getattr(orm, "engine", None)
        if Base and engine:
            Base.metadata.create_all(bind=engine)
            print("[OK] Schema 已创建")
        else:
            print("[SKIP] ORM 中无 Base 或 engine，跳过")
    except Exception as exc:
        print(f"[WARN] Schema 初始化失败: {exc}")


# =========================================================================
# 种子数据
# =========================================================================

def seed_config():
    """插入默认配置到 data/healthlens_config.json（已存在，此处验证）。"""
    config_path = ROOT / "data" / "healthlens_config.json"
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        print(f"[OK] 配置中心: {len(data.get('axes', {}))} 轴定义 + {len(data.get('safety', {}).get('red_flag_patterns', []))} 条红牌规则")
    else:
        print("[WARN] healthlens_config.json 不存在")


def seed_users():
    """插入示例用户（开发用）。"""
    users = [
        {"name": "张明", "age": 35, "gender": "M", "pathways": {"mitochondrial": 0.32, "circadian": 0.41}},
        {"name": "李丽", "age": 28, "gender": "F", "pathways": {"inflammation": 0.28, "autophagy": 0.45}},
        {"name": "王伟", "age": 52, "gender": "M", "pathways": {"senolytics": 0.22, "epigenetic_clock": 0.35}},
        {"name": "赵芳", "age": 45, "gender": "F", "pathways": {"HPA": 0.30, "serotonin": 0.38}},
    ]
    user_path = ROOT / "data" / "seed_users.json"
    user_path.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 示例用户: {len(users)} 条")


# =========================================================================
# 验证案例扩展（合成数据，24 → 100+）
# =========================================================================

_AXES = list("ABCDEFGH")
_AXIS_NAMES = {
    "A": "气化-自噬", "B": "气血-线粒体", "C": "络脉-清瘀",
    "D": "阴阳-昼夜", "E": "脏腑-神经内分泌", "F": "正邪-炎症",
    "G": "神-情志", "H": "先天-肾精",
}
_PATHWAYS = [
    "mitochondrial", "circadian", "autophagy", "inflammation",
    "senolytics", "HPA", "serotonin", "epigenetic_clock",
    "hematopoiesis", "endogenous_stem_cell_activation",
]
_TCM_SOURCES = [
    "《黄帝内经·素问》", "《伤寒论》", "《金匮要略》",
    "《神农本草经》", "《温病条辨》", "《中医内科学》",
]
_LIFE_STYLES = ["八段锦", "太极", "冥想", "正念", "散步", "瑜伽"]
_DIETS = ["低GI饮食", "地中海饮食", "八珍汤", "黄芪粥", "山药膳", "枸杞茶"]


def _generate_case(idx: int) -> dict:
    axis = random.choice(_AXES)
    pathway = random.choice(_PATHWAYS)
    score = round(random.uniform(0.15, 0.45), 2)
    symptom = f"{_AXIS_NAMES[axis]}低分({score})"

    return {
        "case_id": f"HL-{idx:04d}",
        "case_name": f"验证案例-{idx}",
        "symptom": symptom,
        "tcm_source": random.choice(_TCM_SOURCES),
        "tcm_evidence": f"古籍记载与{axis}轴相关的调治原则",
        "gene_pathway": pathway,
        "gene_relevance": score,
        "recommendation": f"通过{_LIFE_STYLES[random.randint(0, len(_LIFE_STYLES)-1)]}结合{_DIETS[random.randint(0, len(_DIETS)-1)]}改善{axis}轴",
        "evidence_level": random.choice(["L1", "L1", "L2", "L3"]),
        "axis": axis,
        "pathway": pathway,
        "confidence": round(random.uniform(0.3, 0.9), 2),
        "generated_at": datetime.now().isoformat(),
        "is_synthetic": True,
    }


def expand_cases(target_count: int = 120):
    """将验证案例从 24 扩展到 target_count（合成数据补全）。"""
    existing_path = ROOT / "data" / "case_evidence_db.json"
    if existing_path.exists():
        raw = json.loads(existing_path.read_text(encoding="utf-8"))
        # 支持两种格式：dict{"cases":[...]} 或 list
        if isinstance(raw, dict):
            existing = raw.get("cases", [])
        elif isinstance(raw, list):
            existing = raw
        else:
            existing = []
    else:
        existing = []

    existing_ids = {c.get("case_id") for c in existing if isinstance(c, dict)}
    new_cases = []
    idx = len(existing) + 1
    while len(new_cases) < target_count - len(existing):
        case = _generate_case(idx)
        if case["case_id"] not in existing_ids:
            new_cases.append(case)
        idx += 1

    merged = existing + new_cases
    if isinstance(raw, dict):
        raw["cases"] = merged
        raw.setdefault("meta", {})["total"] = len(merged)
        existing_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        existing_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 验证案例: {len(existing)} → {len(merged)} 条（新增 {len(new_cases)} 合成案例）")


# =========================================================================
# CLI
# =========================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HealthLens 数据库初始化")
    parser.add_argument("--schema", action="store_true", help="仅初始化 schema")
    parser.add_argument("--seed", action="store_true", help="仅插入种子数据")
    parser.add_argument("--cases", type=int, default=0, help="扩展验证案例数量（如 120）")
    parser.add_argument("--all", action="store_true", help="完整初始化")
    args = parser.parse_args()

    do_all = args.all or not any([args.schema, args.seed, args.cases])

    if do_all or args.schema:
        init_schema()
    if do_all or args.seed:
        seed_config()
        seed_users()
    if do_all or args.cases:
        expand_cases(args.cases or 120)