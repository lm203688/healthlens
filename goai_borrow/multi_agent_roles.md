# 多 Agent 角色分离规范（借鉴 Zorost/Zorigin + HunterCode + MergePilot）

> 目标：把 HealthLens 从"单融合引擎"升级为"四角色 + 工具契约 + 引用溯源"的可信闭环，
> 同时满足 GOAI「多 Agent 协同与自主闭环」「Skill 工程与生态复用」两个维度的评审要求。

## 一、四角色（角色分离，审查者与生成者不同上下文）

| 角色 | 职责 | 借鉴 | 关键约束 |
|---|---|---|---|
| **Planner** | 拆解用户诉求 → 八轴探查计划（哪些轴、查什么证据、是否需基因/古籍/案例） | Zorost Planner | 不直接调用证据工具，只产出计划 |
| **Executor** | 按计划跑 融合/检索/计算，产出候选建议 | Zorost Executor | 所有工具走 typed tool contract，记录确定性调用日志 |
| **Critic** | **独立于 Executor 的上下文**，审查证据强度、越界、去医疗化违反 | MergePilot（审查者不同上下文降幻觉）+ Zorost Critic | 用与 Executor 不同的规则集与提示，避免自检幻觉 |
| **Referee** | 最终合规闸门 + 引用核验 + 红牌兜底（串接 agent_safety_gate） | Zorost Referee + MedAssist 红牌 | 任一 HALT 即拦截；每条结论附证据溯源 |

> 关键原则（来自 MergePilot 博客）：**写的人和审的人不能共享同一上下文**。Critic 用
> 不同 prompt + 不同规则集挑错，显著降低幻觉与遗漏——这正是单引擎自检的盲区。

## 二、工具契约（typed tool contract）

任何工具（融合、古籍检索、基因弱项查询、案例匹配、报告生成）必须满足：

```yaml
tool: evidence_lookup
input_schema:
  query: string          # 检索词
  axis: enum[A-H]        # 限定八轴
  evidence_min: enum[L1,L2,L3]
output_schema:
  hits: list[{id, source, grade, snippet}]
side_effects: none        # 只读，不写状态
deterministic_log: true   # 每次调用写入审计日志（供 runtime_audit 消费）
```

- 无 side_effect 的工具才能被 Executor 自主调用；
- 有 side_effect（如写案例库、发推送）必须由 Referee 显式批准。

## 三、引用溯源（citation-grounded，对标 EyeAgent）

每条融合建议必须带 provenance：

```json
{
  "claim": "A 轴（气化/自噬）偏弱，建议晨间光照 + 适度热量限制",
  "evidence": [
    {"type": "gene", "id": "LAMP2", "effect": "↑4.2×", "source": "D+Q 实验"},
    {"type": "tcm", "id": "黄帝内经/素问", "snippet": "……"},
    {"type": "case", "id": "case-024", "outcome": "肝脂肪↓23.7%"}
  ]
}
```

Referee 校验：声明有依据但 `evidence` 为空 → 拦截（对应 agent_safety_gate 的 EG-001）。

## 四、Skill 工程骨架（借鉴 HunterCode：方法即 Markdown + 可挂 MCP）

每个核心能力抽成一个 Skill，目录结构：

```
skills/
  fusion/
    SKILL.md          # 方法描述、适用、输入输出、注意事项
    run.py            # 确定性逻辑（封装 fusion_engine）
    test_fusion.py   # 单测：给定输入可复现
  evidence-grade/
    SKILL.md
    run.py
    test_evidence.py
  safety-gate/
    SKILL.md
    run.py            # 包装 agent_safety_gate
    test_safety.py
  tcm-pathway/
    SKILL.md
    run.py
  report-gen/
    SKILL.md
    run.py
```

`SKILL.md` 模板（Markdown 即方法，可被 LLM 与人类共读）：

```markdown
# Skill: fusion
## 用途
把「古籍候选 ∩ 基因弱项通路」融合为八轴稳态调理建议。
## 输入
用户诉求 + 可选基因弱项列表 + 可选体质/证型。
## 输出
八轴激活图 + 非用药干预候选 + 证据溯源（provenance）。
## 护栏
必须经由 safety-gate 两道闸门；不得出现诊断/处方/治愈承诺。
## 测试
`python test_fusion.py` 应 100% 复现样例融合。
```

## 五、MCP server（生态复用，借鉴 Agentero）

暴露 `healthlens-mcp` server，让外部 Agent 可调用：

- `evidence_lookup(query, axis, grade)` → 证据检索
- `fusion(user_input, gene_weak)` → 融合建议（已带安全闸门）
- `safety_check(text)` → 红牌/红线检测

这样 HealthLens 的方法学可被行业其他 Agent 复用，直接提升「Skill 工程与生态复用」「行业可复制性」。
