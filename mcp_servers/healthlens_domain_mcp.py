#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HealthLens 领域 MCP 服务器 (Tools/Action 层)

零依赖 stdio MCP 服务器：把 HealthLens 后端 REST API 暴露为可被 agent 调用的工具。
与 aoci-healthlens（只读认知层）互补——本服务器提供"可行动"的领域工具。

免 token 即可用：pulse_interpret / agent_pulse / axes_meta / axes_evidence
需登录 token 才可用（HL_API_TOKEN 或本地缓存文件）：
    axes_assess / axes_project / bioage_assess / checkin_create / checkin_summary

配置（环境变量）：
  HL_API_BASE        后端基址，默认 https://healthlens.cc
  HL_API_TOKEN       Bearer token（用于需登录的工具）
  HL_API_TOKEN_FILE  token 文件路径（可选，优先级低于 HL_API_TOKEN）
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("HL_API_BASE", "https://healthlens.cc").rstrip("/")
SERVER_NAME = "healthlens-domain"
SERVER_VERSION = "0.1.0"

_TOKEN = None  # lazily loaded


def _load_token():
    global _TOKEN
    if _TOKEN is not None:
        return _TOKEN
    t = os.environ.get("HL_API_TOKEN")
    if t:
        _TOKEN = t.strip()
        return _TOKEN
    fp = os.environ.get("HL_API_TOKEN_FILE")
    if not fp:
        fp = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", ".workbuddy", "cache", "hl_domain_token.txt",
        )
    try:
        with open(fp, "r", encoding="utf-8") as f:
            _TOKEN = f.read().strip()
    except Exception:
        _TOKEN = ""
    return _TOKEN


def _http(method, path, body=None, auth=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "HealthLens-Domain-MCP/0.1")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", "Bearer " + auth)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace"), r.status, None
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace"), e.code, None
    except Exception as e:  # noqa: BLE001
        return None, 0, str(e)


def _fmt(raw):
    if raw is None:
        return raw
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except Exception:
        return raw


def _require_auth():
    tok = _load_token()
    if not tok:
        return (
            "⚠️ 该工具需要 HealthLens 登录 token。\n"
            "请二选一：\n"
            "  1) 设置环境变量 HL_API_TOKEN=你的JWT；或\n"
            "  2) 把 token 写入 healthlens/.workbuddy/cache/hl_domain_token.txt\n"
            "（token 从 healthlens.cc 登录后，浏览器 DevTools → Application → Local Storage 复制 JWT）\n"
            "免登录工具（pulse_interpret / agent_pulse / axes_meta / axes_evidence）无需 token。"
        )
    return None


# --------------------------------------------------------------------------
# tool handlers
# --------------------------------------------------------------------------

def t_pulse_interpret(args):
    features = args.get("features") or {}
    if not features:
        return "❌ features 不能为空（需传入 hl.pulse.* 特征键值）。", True
    raw, status, err = _http("POST", "/api/v1/pulse/interpret",
                             {"features": features, "user_ref": args.get("user_ref")})
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_agent_pulse(args):
    body = {"user_ref": args["user_ref"], "days": int(args.get("days", 7))}
    raw, status, err = _http("POST", "/api/v1/agent/pulse", body)
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_axes_meta(args):
    raw, status, err = _http("GET", "/api/v1/axes/meta")
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_axes_evidence(args):
    cid = args["case_id"]
    raw, status, err = _http("GET", f"/api/v1/axes/evidence/{cid}")
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_axes_assess(args):
    msg = _require_auth()
    if msg:
        return msg, False
    body = {
        "chrono_age": int(args["chrono_age"]),
        "is_male": bool(args.get("is_male", True)),
        "pathway_scores": args.get("pathway_scores") or {},
        "weak_axes": args.get("weak_axes") or [],
        "contraindications": args.get("contraindications") or [],
        "top_k": int(args.get("top_k", 8)),
    }
    for k in ("glucose", "hba1c", "hs_crp", "waist_cm", "hdl", "triglycerides", "sbp", "bmi"):
        if args.get(k) is not None:
            body[k] = float(args[k])
    raw, status, err = _http("POST", "/api/v1/axes/assess", body, auth=_load_token())
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_axes_project(args):
    msg = _require_auth()
    if msg:
        return msg, False
    body = {
        "baseline_scores": args.get("baseline_scores") or {},
        "weak_axes": args.get("weak_axes") or [],
        "checkin_energy": args.get("checkin_energy"),
        "checkin_digestion": args.get("checkin_digestion"),
        "checkin_sleep": args.get("checkin_sleep"),
        "levers": args.get("levers") or [],
        "weeks": int(args.get("weeks", 12)),
        "lever_scale": float(args.get("lever_scale", 1.0)),
    }
    raw, status, err = _http("POST", "/api/v1/axes/project", body, auth=_load_token())
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_bioage_assess(args):
    msg = _require_auth()
    if msg:
        return msg, False
    body = {"chrono_age": int(args["chrono_age"]), "is_male": bool(args.get("is_male", True))}
    for k in ("glucose", "hba1c", "hs_crp", "waist_cm", "hdl", "triglycerides", "sbp", "bmi"):
        if args.get(k) is not None:
            body[k] = float(args[k])
    raw, status, err = _http("POST", "/api/v1/axes/bioage", body, auth=_load_token())
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_checkin_create(args):
    msg = _require_auth()
    if msg:
        return msg, False
    body = {
        "energy_score": int(args["energy_score"]),
        "digestion_score": int(args["digestion_score"]),
        "sleep_score": int(args["sleep_score"]),
        "note": args.get("note"),
    }
    raw, status, err = _http("POST", "/api/v1/checkin", body, auth=_load_token())
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


def t_checkin_summary(args):
    msg = _require_auth()
    if msg:
        return msg, False
    window = int(args.get("window", 10))
    raw, status, err = _http("GET", f"/api/v1/checkin/summary?window={window}", auth=_load_token())
    if err:
        return f"❌ 调用失败: {err}", True
    if status >= 400:
        return f"❌ HTTP {status}: {raw}", True
    return _fmt(raw), False


# --------------------------------------------------------------------------
# tool catalog
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "pulse_interpret",
        "description": "脉象解读（免登录）。传入 hl.pulse.* 特征键值，返回脉象标签 + 八轴信号 + 养生参考 + 健康护栏。非医疗定位。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "features": {"type": "object", "description": "hl.pulse.* 特征键值，如 h3_h1/h5_h1/dicrotic_present 等"},
                "user_ref": {"type": "string", "description": "可选，仅用于回显的设备身份"},
            },
            "required": ["features"],
        },
        "handler": t_pulse_interpret,
    },
    {
        "name": "agent_pulse",
        "description": "按 user_ref 拉取并解读最近号脉结果（免登录）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_ref": {"type": "string", "description": "号脉设备上报时使用的 user_ref"},
                "days": {"type": "integer", "description": "回溯天数，默认 7", "default": 7},
            },
            "required": ["user_ref"],
        },
        "handler": t_agent_pulse,
    },
    {
        "name": "axes_meta",
        "description": "八轴稳态元信息（免登录）：轴标识、落点八轴、弱轴阈值、诚实边界。",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": t_axes_meta,
    },
    {
        "name": "axes_evidence",
        "description": "按 case_id 取某条八轴推荐的完整证据链（古籍经验 + 现代稳态生物学证据，免登录）。",
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "description": "案例证据 ID"}},
            "required": ["case_id"],
        },
        "handler": t_axes_evidence,
    },
    {
        "name": "axes_assess",
        "description": "八轴个性化融合推荐（需登录）。体检指标 + 可选基因/组学 → 个性化养生建议。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chrono_age": {"type": "integer", "description": "实际年龄（岁）"},
                "is_male": {"type": "boolean", "default": True},
                "glucose": {"type": "number"},
                "hba1c": {"type": "number"},
                "hs_crp": {"type": "number"},
                "waist_cm": {"type": "number"},
                "hdl": {"type": "number"},
                "triglycerides": {"type": "number"},
                "sbp": {"type": "number"},
                "bmi": {"type": "number"},
                "pathway_scores": {"type": "object"},
                "weak_axes": {"type": "array", "items": {"type": "string"}},
                "contraindications": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer", "default": 8},
            },
            "required": ["chrono_age"],
        },
        "handler": t_axes_assess,
    },
    {
        "name": "axes_project",
        "description": "迷你 Turboid 养生方案虚拟推演（需登录）。基于八轴耦合网络前向推演健康信号演化，纯虚拟非临床。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "baseline_scores": {"type": "object", "description": "各轴(字母 A-H) 0-100 基线分"},
                "weak_axes": {"type": "array", "items": {"type": "string"}},
                "checkin_energy": {"type": "integer", "minimum": 1, "maximum": 5},
                "checkin_digestion": {"type": "integer", "minimum": 1, "maximum": 5},
                "checkin_sleep": {"type": "integer", "minimum": 1, "maximum": 5},
                "levers": {"type": "array", "items": {"type": "string"}},
                "weeks": {"type": "integer", "default": 12},
                "lever_scale": {"type": "number", "default": 1.0},
            },
        },
        "handler": t_axes_project,
    },
    {
        "name": "bioage_assess",
        "description": "生物学年龄偏移与代谢-炎症轴稳态分（需登录）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chrono_age": {"type": "integer"},
                "is_male": {"type": "boolean", "default": True},
                "glucose": {"type": "number"},
                "hba1c": {"type": "number"},
                "hs_crp": {"type": "number"},
                "waist_cm": {"type": "number"},
                "hdl": {"type": "number"},
                "triglycerides": {"type": "number"},
                "sbp": {"type": "number"},
                "bmi": {"type": "number"},
            },
            "required": ["chrono_age"],
        },
        "handler": t_bioage_assess,
    },
    {
        "name": "checkin_create",
        "description": "记录一次 wellness 自测（需登录）：精力/消化/睡眠 1-5 分 + 备注。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "energy_score": {"type": "integer", "minimum": 1, "maximum": 5},
                "digestion_score": {"type": "integer", "minimum": 1, "maximum": 5},
                "sleep_score": {"type": "integer", "minimum": 1, "maximum": 5},
                "note": {"type": "string"},
            },
            "required": ["energy_score", "digestion_score", "sleep_score"],
        },
        "handler": t_checkin_create,
    },
    {
        "name": "checkin_summary",
        "description": "近 N 次自测的均值与趋势（需登录）。",
        "inputSchema": {
            "type": "object",
            "properties": {"window": {"type": "integer", "default": 10}},
        },
        "handler": t_checkin_summary,
    },
]


def _tools_list():
    return {
        "tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in TOOLS
        ]
    }


def _dispatch_call(name, arguments):
    for t in TOOLS:
        if t["name"] == name:
            try:
                text, is_error = t["handler"](arguments or {})
            except Exception as e:  # noqa: BLE001
                return {"content": [{"type": "text", "text": f"❌ 工具执行异常: {e}"}], "isError": True}
            return {"content": [{"type": "text", "text": text or "(空)"}], "isError": bool(is_error)}
    return {"content": [{"type": "text", "text": f"❌ 未知工具: {name}"}], "isError": True}


def _send(mid, result):
    out = {"jsonrpc": "2.0", "id": mid, "result": result}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_error(mid, code, message):
    out = {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            proto = msg.get("params", {}).get("protocolVersion", "2024-11-05")
            _send(mid, {
                "protocolVersion": proto,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _send(mid, {})
        elif method == "tools/list":
            _send(mid, _tools_list())
        elif method == "tools/call":
            params = msg.get("params", {})
            _send(mid, _dispatch_call(params.get("name"), params.get("arguments")))
        elif mid is not None:
            _send_error(mid, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
