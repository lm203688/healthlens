# HealthLens 健康全景平台

> 跨生态健康数据聚合 → AI 双轨诊断(西医+中医) → 精准治疗 → 古籍知识库 → 基因组学

[![Tests](https://github.com/lm203688/healthlens/actions/workflows/ci.yml/badge.svg)](https://github.com/lm203688/healthlens/actions)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

## 项目状态

**v0.9.0** — 产品化迭代完成

- 前端 MVP：Vite + React，6 页面（仪表盘/评估/体质/报告/知识库/AI 对话）
- 3 个 Seed Skill：古籍文本挖掘 + 融合推理 + 证据分级
- LLM 增强：`USE_LLM=1` 时本地 Ollama qwen3.8 对个人化处方做语义润色
- MCP Server：5 个工具暴露为 MCP 协议（JSON-RPC 模式可用）
- CI 全启用：agent-lib-test + skills-test + lint-and-test + docker-build

- 140+ 文件，25 张数据库表，75+ API 端点，15 个路由模块
- 174 个测试全绿 (pytest-asyncio, 23s)
- 完整 RBAC 权限 + 安全加固 + 生产就绪
- 中医古籍书目库：701 部已入库（488 部标注作者与朝代，按本草/方剂/医经/针灸等 9 类索引）
- 其中 2 部已完成实体级结构化，产出 613 条药物/功效/原文引证记录

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + SQLAlchemy 2.0 async + Pydantic 2 |
| 数据库 | PostgreSQL 16 + TimescaleDB |
| 缓存/队列 | Redis 7 + Celery 5 |
| OCR | PaddleOCR (生产) / TesseractOCR / MockOCR (开发) |
| 对象存储 | MinIO |
| 监控 | Prometheus + RequestMetricsMiddleware |
| 部署 | Docker Compose + Nginx + GitHub Actions CI/CD |

## 快速开始

### 本地开发

```powershell
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境变量
Copy-Item .env.example .env
# 编辑 .env 填入数据库/Redis/JWT 配置

# 3. 启动 API 服务
.\scripts\dev.bat

# 4. 启动 Celery Worker (另开终端)
.\scripts\worker.bat
```

访问 http://localhost:8000/docs 查看 API 文档

### Docker 部署 (开发环境)

```bash
cp .env.example .env
docker compose up -d
docker compose exec web alembic upgrade head
docker compose exec web python scripts/seed_admin.py
```

### 生产部署

```bash
# 使用部署脚本 (自动备份 + 健康检查 + 回滚)
./scripts/deploy.sh

# 或手动
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d
```

## 核心功能

### 西医链路
1. **报告上传** — PDF/图片 → OCR 解析 → 22 种指标自动提取
2. **健康指标** — LOINC 标准存储，趋势分析，异常检测
3. **AI 诊断** — 规则引擎：7 种异常 → ICD-11 映射 → 诊断建议
4. **处方系统** — 医生开具处方 + 处方管理 CRUD
5. **FHIR 导出** — R5 标准 Bundle (Patient + Observation + DiagnosticReport)

### 中医链路
1. **九种体质** — 中华中医药学会标准评分算法
2. **AI 辨证** — 6 种证型匹配
3. **方剂推荐** — 经典方剂 + 加减化裁
4. **舌象分析** — 颜色直方图 → 舌色/苔色/辨证
5. **中药配送** — 订单管理 + 状态机

### 中医古籍知识库 (v0.8.2 新增)
- **食疗推荐** — 基于《食疗本草》《食疗方》的 15 个经典食疗方
- **非药物治疗** — 穴位按压/推拿/八段锦/起居调养/四季饮食
- **综合调理方案** — 体质分析 + 食疗 + 非药物 + 膳食指南
- **古籍书目库** — 701 部中医古籍分类索引（书名/作者/朝代/年份/类目，均取自语料原始标注）
- **数据导入** — `tools/parse_classical_books.py` 解析语料元数据 → `tools/gen_books_sql.py` 生成幂等 SQL 入库
- **结构化抽取** — 确定性规则抽取古籍实体（`rule_extract`），输出含原文引证的 JSON，避免 LLM 幻觉

### 慢病风险评估
- **ASCVD 风险** — China-PAR 模型，10 年心血管事件概率
- **糖尿病风险** — 中国糖尿病风险评分 (CDRS)
- **代谢综合征** — CDS 标准，5 项指标诊断

### 健康管理
- **健康仪表盘** — 总览/关键指标/趋势分析/风险概览
- **健康目标** — 目标设定/进度追踪/完成度统计
- **通知中心** — 站内通知/健康提醒/用药提醒
- **用药依从性** — 服药计划/记录/依从率统计

## API 端点

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth/*` | 注册/登录/刷新/角色管理 |
| 健康档案 | `/api/v1/profiles/*` | CRUD |
| 报告管理 | `/api/v1/records/*` | 上传/列表/删除 |
| 健康指标 | `/api/v1/observations/*` | 创建/批量/趋势/汇总 |
| 西医诊断 | `/api/v1/diagnosis/*` | 分析/结果/审核 |
| 处方 | `/api/v1/medications/*` | 推荐/开具/历史/处方管理 |
| 中医 | `/api/v1/tcm/*` | 体质/舌象/辨证/方剂/订单 |
| **中医古籍** | `/api/v1/knowledge/*` | **食疗/非药物/调理方案/古籍** |
| 基因组 | `/api/v1/genome/*` | 上传/解读/PGx 报告 |
| 数据连接 | `/api/v1/connections/*` | CRUD/同步 |
| 报告 | `/api/v1/reports/*` | 健康摘要/FHIR 导出 |
| 仪表盘 | `/api/v1/dashboard/*` | 总览/趋势/风险评估 |
| 健康目标 | `/api/v1/goals/*` | CRUD/进度/统计 |
| 通知中心 | `/api/v1/notifications/*` | 列表/已读/删除 |
| 用药依从性 | `/api/v1/adherence/*` | 计划/记录/统计 |
| **智能体** | `/api/v1/agent/*` | **融合安全管线 / 四角色 Agent 团队** |

## 智能体能力库（healthlens_agent）

把 GOAI 榜单头部项目的可借鉴能力（MedAssist 前置红牌、LabGuard typed guard IR、
Codenotary 运行时遥测、DataFlow-Agent 可复现 DAG、EyeAgent 多模态工具箱）落地为一个
**无重型依赖、可独立测试**的 Python 包 `healthlens_agent/`。它直接接入真实融合引擎
`app/lib/fusion_engine.py`，不依赖 FastAPI，可在本地/CI 中独立运行与测试。

| 模块 | 能力 |
|------|------|
| `safety` | 安全闸门：前置红牌（医学急症拦截）+ 后置去医疗化/八轴红线/证据断链 |
| `audit` | 运行时行为遥测：七类异常（敏感信息/越界/未授权外呼/递归失控/注入/异常工具/超额） |
| `pipeline` | 融合安全管线：两道闸门 + 审计 接入真实融合引擎 |
| `team` | 四角色 Agent：Planner/Executor/Critic/Referee |
| `benchmark` | GOAI 七维度行为评测 + launch-risk score |
| `flow` | 可复现融合 DAG pipeline |
| `multimodal` | 多模态八轴倾向速判原型（舌/面/体态） |

命令行：

```bash
python -m healthlens_agent                 # 运行全部演示
python -m healthlens_agent pipeline         # 融合安全管线
python -m healthlens_agent team             # 四角色 Agent 团队
python -m healthlens_agent bench            # GOAI 七维评测 + launch-risk
python -m healthlens_agent flow --input "最近疲劳怕冷" --gene mitochondrial:0.32
python -m healthlens_agent probe --image-desc "舌淡红、苔薄白、面色萎黄"
```

HTTP 入口（已接入 FastAPI，`try/except` 守卫注册，能力不可用时自动跳过）：
- `POST /api/v1/agent/fusion` — 融合安全管线
- `POST /api/v1/agent/team` — 四角色 Agent 团队

测试（不依赖 FastAPI，可在精简环境运行）：

```bash
pytest healthlens_agent/tests -v
```

## 前端（frontend/）

Vite + React 构建的单页应用，接入后端 75+ API 端点。

| 页面 | 路由 | 功能 |
|------|------|------|
| 仪表盘 | `/` | 总览/弱项轴/融合评分/慢病风险 |
| 健康评估 | `/assess` | 症状输入 + 基因弱项 → 融合引擎 → 个性化建议 |
| 中医体质 | `/tcm` | 8 题问卷 → 体质分析 + 建议 |
| 健康报告 | `/reports` | 报告数据展示 |
| 知识库 | `/knowledge` | 全文检索/食疗方/非药物疗法 |
| AI 对话 | `/agent` | 四角色 Agent 团队对话界面 |

```bash
cd frontend
npm install
npm run dev          # 开发：http://localhost:3000（自动代理 /api 到后端）
npm run build        # 生产构建 → frontend/dist/
npm run preview      # 预览生产构建
```

## Skills 体系（skills/）

借鉴 Hunter/AgentPit SKILL 架构（SKILL.md + run.py + test.py），3 个 Seed Skill：

| Skill | 方法论 | 命令 |
|-------|--------|------|
| `tcm_text_mining` | 古籍文本→症状/治法/方药实体抽取+轴映射 | `python skills/tcm_text_mining/run.py --text "..."` |
| `fusion_inference` | 古籍候选 ∩ 基因弱项→八轴评分+建议 | `python skills/fusion_inference/run.py --text "..." --gene "mitochondrial:0.32"` |
| `evidence_grading` | L1/L2/L3 证据分级+置信度评分 | `python skills/evidence_grading/run.py --recs '[...]` |

```bash
python skills/scaffold.py list    # 列出所有 Skill
python skills/scaffold.py test tcm_text_mining   # 测试 Skill
```

## MCP Server

5 个工具通过 MCP 协议暴露，供外部 Agent/Copilot 调用：

- `fusion_engine` — 八轴融合推理
- `evidence_grade` — 证据分级 L1/L2/L3
- `risk_assess` — 慢病风险评估
- `tcm_constitution` — 中医体质分析
- `knowledge_search` — 古籍知识库搜索

```bash
python -m healthlens_agent mcp    # 启动 MCP Server（JSON-RPC 模式）
# 如需标准 MCP 协议：pip install mcp
```

## Skill 注册表 API

通过 `healthlens_agent/skills.py` 将 `skills/` 目录下的所有 Skill 暴露为 API：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/skills` | GET | 列出所有 Skill 元信息 |
| `/api/v1/skills/{name}` | GET | 获取单个 Skill 详情（SKILL.md 内容） |
| `/api/v1/skills/{name}/run` | POST | 执行指定 Skill |
| `/api/v1/skills/{name}/test` | POST | 运行 Skill 的 test.py |

## 自动化管线 API

对接 `auto-pipeline/scripts/phase_1~8` 的 8 阶段自动化管线：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/pipeline/phases` | GET | 列出所有管线阶段 |
| `/api/v1/pipeline/status` | GET | 管线运行状态 |
| `/api/v1/pipeline/phase/{id}/run` | POST | 执行单个阶段（支持 dry_run） |
| `/api/v1/pipeline/run-all` | POST | 依次执行全部 8 阶段 |

## 数据连接器

5 个外部数据源连接器（Apple Health / 华为健康 / 小米运动健康 / Withings / 医院 LIS），
统一抽象在 `app/connectors/`，通过 `app/api/connectors_public.py` 暴露。
所有同步输出经过 `app/core/desensitize.py` 脱敏网关（mask/pseudonymize/anonymize 三级）。

## 合规与同意

`/api/v1/compliance/*` 端点覆盖：
- 4 份政策（隐私/条款/数据处理/未成年人保护）的版本化管理
- 用户同意记录与查询
- 生产环境合规红线

## 配置中心

`data/healthlens_config.json` 集中管理所有可调参数：
八轴定义与阈值 / 融合公式 / 风险阈值 / 安全红牌规则 / LLM 配置 / Skill 配置 / 审计配置。
支持环境变量覆盖：`HL_CONFIG_SECTION_KEY=value`。

## 数据库初始化

```bash
python tools/db_init.py --all       # 完整初始化（schema + seed + 案例扩展）
python tools/db_init.py --cases 120 # 将验证案例从 24 扩展到 120
```

## LLM 增强

`USE_LLM=1` 时，融合引擎调用本地 Ollama 模型对处方文本做个人化语义增强。失败静默回退到规则引擎。

```bash
USE_LLM=1 HEALTHLENS_LLM_MODEL=qwen3.8 python -m healthlens_agent pipeline
```

## CI

`.github/workflows/ci.yml` 包含 4 个 job：

| Job | 内容 |
|-----|------|
| `lint-and-test` | ruff + mypy + pytest tests/（全量后端） |
| `docker-build` | Docker 镜像构建 |
| `agent-lib-test` | ruff + pytest healthlens_agent/（无 FastAPI 依赖） |
| `skills-test` | 3 个 Seed Skill 的 test.py |

## 安全特性

- **RBAC 三级权限** — patient / doctor / admin
- **JWT + Refresh Token** — 短期 access + 长期 refresh
- **密码强度校验** — 至少 8 位，含字母和数字
- **认证限流** — 注册/登录 5 次/分钟 (slowapi)
- **Token 加密存储** — Fernet 对称加密 OAuth tokens
- **生产环境校验** — 不安全密钥拒绝启动
- **请求 ID 追踪** — X-Request-ID 全链路追踪
- **全局异常处理** — 统一 500 响应格式，生产环境隐藏堆栈
- **Prometheus 监控** — /metrics 端点暴露请求指标
- **数据库索引** — 15 个索引优化高频查询

## 监控

```bash
# 健康检查
curl http://localhost:8000/health

# Prometheus 指标
curl http://localhost:8000/metrics
```

指标包括：HTTP 请求计数/延迟、OCR 任务、Celery 队列、DB 连接池

## 配置

关键环境变量 (`.env`):

```bash
OCR_ENGINE=mock              # mock(开发) / tesseract / paddleocr(生产)
DB_HOST=localhost
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret   # 生产环境必须为随机 64 字符
CORS_ORIGINS=["http://localhost:3000"]
LOG_LEVEL=INFO
```

## 测试

```bash
# 全量测试（需安装 FastAPI 等后端依赖）
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=app --cov-report=term-missing

# 仅 API 测试
pytest tests/api/ -v

# 仅引擎测试
pytest tests/core/ -v

# 智能体能力库测试（无需 FastAPI，精简环境即可运行）
pytest healthlens_agent/tests -v
```

## 部署架构

```
                    +--------+
                    | Nginx  |  (HTTPS, Rate Limit, Security Headers)
                    +---+----+
                        |
              +---------+---------+
              |                   |
         +----+----+         +----+----+
         | Web API |         | Worker  |  (Celery)
         |FastAPI  |        +----+----+
         +----+----+             |
              |             +----+----+
         +----+----+        |  Redis  |
         |PostgreSQL|       +----+----+
         |TimescaleDB|     +----+----+
         +----+----+        |  MinIO  |
              |            +---------+
         +----+----+
         |Prometheus|
         +---------+
```

## 项目文档

- [CHANGELOG.md](CHANGELOG.md) — 版本变更记录
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — 发布说明
- [Makefile](Makefile) — 一键操作 (make dev/test/build/deploy)

## License

Proprietary — All rights reserved.
