"""
skills/ — HealthLens Skill 方法学工程框架

借鉴 Hunter/AgentPit 的 "SKILL = methodology" 模式：
- 每个 Skill 是一个目录：SKILL.md（方法论描述）+ run.py（可执行逻辑）+ test.py（可选测试）
- Skill 由 SkillRegistry 动态发现、加载、执行
- 支持 user-skills/ 目录供用户/社区扩展

Skill 目录结构：
  skills/
  ├── scaffold.py          # Skill 加载与执行框架
  ├── <skill_name>/
  │   ├── SKILL.md         # 方法论描述（Agent 读取的指导文档）
  │   ├── run.py           # 可执行入口（def run(**kwargs) -> dict）
  │   └── test.py          # 可选：pytest 测试
  └── user-skills/         # 用户自定义 Skill（运行时注入）

SKILL.md 规范：
  # <Skill 名称>
  > 一句话描述

  ## 输入
  - <参数名>：<类型> - <说明>

  ## 输出
  - <字段名>：<类型> - <说明>

  ## 方法论
  <方法论描述，Agent 据此理解何时调用此 Skill>

  ## 前置依赖
  - <依赖项>

  ## 示例
  ```
  python run.py --arg value
  ```
"""
from .scaffold import SkillRegistry, SkillManifest, load_skill, discover_skills

__all__ = [
    "SkillRegistry",
    "SkillManifest",
    "load_skill",
    "discover_skills",
]

__version__ = "0.1.0"
