"""
HealthLens 闭环工作流 - 状态管理器
统一管理 pipeline_state.json，所有阶段脚本通过此模块读写状态
"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATE_FILE = BASE_DIR / "pipeline_state.json"
LOG_DIR = BASE_DIR / "logs"

PHASES = ["collect", "analyze", "decide", "develop", "test", "deploy"]


def get_state():
    """读取当前 pipeline 状态"""
    if not STATE_FILE.exists():
        return _init_state()
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    """保存 pipeline 状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _init_state():
    """初始化全新的 pipeline 状态"""
    state = {
        "pipeline_id": datetime.now().strftime("W%W-%Y"),
        "created_at": datetime.now().isoformat(),
        "status": "idle",
        "current_phase": None,
        "phases": {},
        "approved_queue": [],
        "watch_queue": [],
        "rejected_items": [],
        "deployment_history": [],
        "feedback_metrics": {}
    }
    for phase in PHASES:
        state["phases"][phase] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "output_file": None,
            "items_processed": 0,
            "error": None
        }
    save_state(state)
    return state


def start_phase(phase_name, **kwargs):
    """标记阶段开始"""
    state = get_state()
    # 自动创建缺失的阶段（支持反馈闭环等自定义阶段）
    if phase_name not in state["phases"]:
        state["phases"][phase_name] = {
            "status": "pending", "started_at": None, "completed_at": None,
            "output_file": None, "items_processed": 0, "error": None
        }

    state["phases"][phase_name]["status"] = "running"
    state["phases"][phase_name]["started_at"] = datetime.now().isoformat()
    state["current_phase"] = phase_name
    state["status"] = f"running_{phase_name}"

    for key, value in kwargs.items():
        if key not in state["phases"][phase_name]:
            state["phases"][phase_name][key] = value

    save_state(state)
    log(f"阶段 {phase_name} 开始")
    return state


def complete_phase(phase_name, output_file=None, items_processed=0, **kwargs):
    """标记阶段完成"""
    state = get_state()
    state["phases"][phase_name]["status"] = "completed"
    state["phases"][phase_name]["completed_at"] = datetime.now().isoformat()
    state["phases"][phase_name]["output_file"] = output_file
    state["phases"][phase_name]["items_processed"] = items_processed
    state["phases"][phase_name]["error"] = None  # 清除之前的错误记录

    for key, value in kwargs.items():
        state["phases"][phase_name][key] = value

    # # 确定下一个阶段（仅A线主流程有下一阶段）
    next_phase = None
    if phase_name in PHASES:
        idx = PHASES.index(phase_name)
        if idx < len(PHASES) - 1:
            next_phase = PHASES[idx + 1]
        else:
            state["status"] = "completed"
            state["current_phase"] = None

    save_state(state)
    log(f"阶段 {phase_name} 完成: {items_processed} 项, 输出: {output_file}")
    return state, next_phase


def fail_phase(phase_name, error_msg):
    """标记阶段失败"""
    state = get_state()
    if phase_name not in state["phases"]:
        state["phases"][phase_name] = {
            "status": "pending", "started_at": None, "completed_at": None,
            "output_file": None, "items_processed": 0, "error": None
        }
    state["phases"][phase_name]["status"] = "failed"
    state["phases"][phase_name]["error"] = error_msg
    state["phases"][phase_name]["completed_at"] = datetime.now().isoformat()
    state["status"] = f"failed_{phase_name}"
    save_state(state)
    log(f"阶段 {phase_name} 失败: {error_msg}", level="ERROR")
    return state


def get_phase_output(phase_name):
    """读取某阶段的输出文件内容"""
    state = get_state()
    output_file = state["phases"].get(phase_name, {}).get("output_file")
    if not output_file:
        return None
    file_path = BASE_DIR / output_file
    if not file_path.exists():
        return None
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def log(message, level="INFO"):
    """写入日志"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"[{level}] {message}")


def reset_pipeline():
    """重置整个 pipeline（用于新一周）"""
    state = get_state()
    # 归档旧状态
    archive_file = BASE_DIR / f"archive_{state['pipeline_id']}.json"
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    # 初始化新状态
    return _init_state()


def is_phase_ready(phase_name):
    """检查某阶段是否可以开始（前置阶段已完成）"""
    state = get_state()
    idx = PHASES.index(phase_name)

    if idx == 0:
        # 第一阶段总是可以开始
        return state["phases"][phase_name]["status"] == "pending"

    prev_phase = PHASES[idx - 1]
    return state["phases"][prev_phase]["status"] == "completed" and \
           state["phases"][phase_name]["status"] == "pending"


def get_next_runnable_phase():
    """获取下一个可以运行的阶段"""
    for phase in PHASES:
        if is_phase_ready(phase):
            return phase
    return None
