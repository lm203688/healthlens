# goai_borrow/ — GOAI 榜单可借鉴点（研究草稿 / 已归档）

> ⚠️ **本目录为研究草稿（scratch），生产代码已迁移到 `healthlens_agent/` 包。**
> 来源项目与映射见 `../GOAI_榜单项目提取_2026-08-24.md` 与 `../GOAI_HealthLens评估与改进建议_2026-08-24.md`。

## 生产代码位置（请优先使用）

GOAI 借鉴能力已落地为可测试、可独立运行的包 `healthlens_agent/`，并经 `healthlens_agent/tests`（29 项测试）覆盖、接入 FastAPI（`/api/v1/agent/*`）、可被 CI 验证。

| 能力 | 生产实现（healthlens_agent/） | 原草稿（本目录） |
|---|---|---|
| 安全闸门 | `healthlens_agent/safety.py` | `agent_safety_gate.py` |
| 运行时审计 | `healthlens_agent/audit.py` | `runtime_audit.py` |
| 融合安全管线 | `healthlens_agent/pipeline.py` | （并入 tools/，现已迁入包） |
| 四角色 Agent | `healthlens_agent/team.py` | `multi_agent_roles.md` |
| 行为评测 | `healthlens_agent/benchmark.py` | `bench_evaluation.py` |
| 可复现 DAG | `healthlens_agent/flow.py` | `healthlens_flow.py` |
| 多模态原型 | `healthlens_agent/multimodal.py` | `multimodal_probe.md` |

## 运行方式（生产）

```bash
python -m healthlens_agent                 # 全部演示
python -m healthlens_agent pipeline | team | bench | flow | probe
pytest healthlens_agent/tests -v           # 单元测试
```

## 原草稿保留说明

本目录文件作为**溯源参考**保留，记录最初从榜单项目落地的思路；其逻辑已不在运行路径上，
后续维护请在 `healthlens_agent/` 中进行。

```bash
cd goai_borrow
python agent_safety_gate.py      # 原始骨架演示（仅参考）
python runtime_audit.py
python bench_evaluation.py
```
