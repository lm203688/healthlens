# HealthLens 健康全景平台

> 跨生态健康数据聚合 → AI 双轨诊断(西医+中医) → 精准治疗 → 古籍知识库 → 基因组学

[![Tests](https://github.com/lm203688/healthlens/actions/workflows/ci.yml/badge.svg)](https://github.com/lm203688/healthlens/actions)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

## 项目状态

**v0.8.2** — Phase 1 全面完成 + 中医古籍知识库集成

- 140+ 文件，25 张数据库表，75+ API 端点，15 个路由模块
- 174 个测试全绿 (pytest-asyncio, 23s)
- 完整 RBAC 权限 + 安全加固 + 生产就绪
- 集成 701 本中医古籍，提供食疗与非药物治疗推荐

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
- **古籍书目库** — 701 本中医古籍分类索引
- **数据导入** — 自动解析 txt 古籍文件入库

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
# 全量测试
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=app --cov-report=term-missing

# 仅 API 测试
pytest tests/api/ -v

# 仅引擎测试
pytest tests/core/ -v
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
