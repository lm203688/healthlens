# HealthLens 知识平面（Knowledge Plane）

**架构原则**：知识平面 = 全球化 / 无 PII / 可开源可独立分发
数据平面 = 区域化 / 含 PII / 永不出境

本目录是知识平面的独立分发单元，可脱离数据库单独打包分发。

## 目录结构

```
knowledge/
├── README.md                        # 本文件
├── __init__.py                      # 包标识
├── loader.py                        # 统一加载器（无 PII 依赖）
├── MANIFEST.json                    # 知识资产清单 + 版本
├── LICENSE                          # 知识平面独立许可证（MIT）
│
├── evidence/                        # 120 条带 DOI 证据
│   ├── case_evidence_db.json
│   └── index.json                   # 证据索引（按通路/轴/证候）
│
├── tcm_entities/                    # 613 条古籍实体
│   ├── tcm_structured/              # 实体库（药材/方剂/证候）
│   └── pathway_to_syndrome.json     # 通路-证候映射（59→38 条）
│
├── axes/                            # 八轴定义与阈值
│   ├── axes.yaml                    # 参数配置（含 jurisdiction 维度）
│   └── AXIS_META.json               # 八轴元数据
│
├── mcp_tools/                       # MCP 工具清单
│   └── tools.json                   # 可被外部 Agent 调用的工具
│
└── terminology/                     # 术语映射（多语言）
    ├── zh_en_terms.json             # 中文-英文-拼音-拉丁学名
    └── who_ist_mapping.json         # WHO International Standard Terminologies
```

## 使用方式

```python
from knowledge.loader import KnowledgeLoader

# 本地加载（默认从当前目录）
k = KnowledgeLoader()
evidence = k.load_evidence()          # 120 条证据
pathways = k.load_pathway_map()       # 38 条通路映射
tcm = k.load_tcm_entities()           # 613 条古籍实体
axes = k.load_axis_config("cn")       # 按法域加载轴配置

# 从远程 / CDN 加载（未来支持）
k = KnowledgeLoader(base_url="https://cdn.healthlens.cc/knowledge/v1.0/")
```

## 分发方式

- **本地嵌入**：直接 `pip install healthlens` 附带知识平面（当前默认）
- **CDN 独立分发**：`knowledge/v1.0/` 目录独立托管，无 PII、可缓存
- **数据集发布**：HuggingFace / Zenodo 发布带 DOI 的开放数据
- **MCP 工具集成**：`mcp-server/` 独立发布为 `healthlens-mcp` 包

## 与数据平面的边界

**绝不做的事**：
- ❌ 知识平面不包含任何用户 PII
- ❌ 知识平面不调用用户数据库
- ❌ 知识平面不写业务日志
- ❌ 知识平面不依赖 JWT / 会话

**允许做的事**：
- ✅ 全球 CDN 分发（无跨境合规风险）
- ✅ MIT / CC-BY 开源（学术引用护城河）
- ✅ 独立版本化（knowledge/v1.0/v1.1/...）
- ✅ 被 MCP / A2A / AG-UI 直接调用

## 版本策略

- `MANIFEST.json` 记录所有知识资产的独立版本
- 版本号遵循 SemVer：`major.minor.patch`
- Major = 破坏性变更（字段删除/重命名）
- Minor = 新增证据/实体（向后兼容）
- Patch = 修正数据（不改变结构）

## 阶段 A1 落地范围（2026-10-10）

**已完成**：
- ✅ `knowledge/` 目录结构建立
- ✅ `MANIFEST.json` 清单
- ✅ `loader.py` 统一加载器（无 PII 依赖）
- ✅ 从 `data/` 复制到 `knowledge/` 的知识资产清单化
- ✅ `knowledge/README.md` 说明架构

**未做**（阶段 B 范畴）：
- ⏸️ CDN 独立托管（需要 Cloudflare / AWS 部署）
- ⏸️ HuggingFace / Zenodo 数据集发布（B5 事项）
- ⏸️ 术语国际化 `terminology/` 完整填充（B4 事项）
