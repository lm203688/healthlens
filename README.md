# HealthLens 健康全景平台

> 跨生态健康数据聚合 → AI 双轨诊断(西医+中医) → 精准治疗 → 基因编辑/长寿科技

## 项目状态

v0.8.2 — Phase 1 全面完成

- 130+ 文件，21 张数据库表，70+ API 端点
- 145 个测试全绿 (pytest-asyncio, 21s)
- 完整 RBAC 权限 + 安全加固 + 生产就绪

## 技术栈

- **后端**: FastAPI + SQLAlchemy 2.0 async + PostgreSQL + TimescaleDB
- **缓存/队列**: Redis + Celery
- **OCR**: PaddleOCR (生产) / MockOCR (开发)
- **存储**: MinIO
- **部署**: Docker Compose

## 快速开始

### 本地开发 (无 Docker)

```powershell
cd healthlens
.\scripts\dev.bat
```

访问 http://localhost:8000/docs 查看 API 文档

### Docker 部署

```bash
cp .env.example .env
docker compose up -d
```

### Celery Worker (异步任务)

```powershell
.\scripts\worker.bat
```

## 核心功能

### 西医链路
1. **报告上传** — PDF/图片 → PaddleOCR 解析 → 22 种指标自动提取
2. **健康指标** — LOINC 标准存储，趋势分析，异常检测
3. **AI 诊断** — 规则引擎：7 种异常 → ICD-11 映射 → 诊断建议
4. **处方系统** — 8 种疾病 → 药物推荐
5. **FHIR 导出** — R5 标准 Bundle

### 中医链路
1. **九种体质** — 中华中医药学会标准评分算法
2. **AI 辨证** — 6 种证型匹配
3. **方剂推荐** — 6 首经典方剂 + 加减化裁
4. **中药配送** — 订单管理 + 药房 API
5. **舌象分析** — 颜色直方图 → 舌色/苔色/辨证

### 慢病风险评估
1. **ASCVD 风险** — China-PAR 模型，10 年心血管事件概率
2. **糖尿病风险** — 中国糖尿病风险评分(CDRS)
3. **代谢综合征** — CDS 标准，5 项指标诊断

### 健康管理
1. **健康仪表盘** — 总览/关键指标/趋势分析/风险概览
2. **健康目标** — 目标设定/进度追踪/完成度统计
3. **通知中心** — 站内通知/健康提醒/用药提醒
4. **用药依从性** — 服药计划/记录/依从率统计

### 基础设施
- **基因组解析** — VCF/23andMe → PGx 基因 → 8 种药物代谢表型
- **数据连接器** — 华为/小米/Apple Health/Withings/医院 LIS
- **异步任务** — Celery OCR/分析/诊断后台化
- **通知服务** — 站内/飞书/微信/短信

## API 端点

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth/*` | 注册/登录/刷新 |
| 健康档案 | `/api/v1/profiles/*` | CRUD |
| 报告管理 | `/api/v1/records/*` | 上传/列表/删除 |
| 健康指标 | `/api/v1/observations/*` | 创建/批量/趋势/汇总 |
| 西医诊断 | `/api/v1/diagnosis/*` | 分析/结果/审核 |
| 处方 | `/api/v1/medications/*` | 推荐/开具/历史 |
| 中医 | `/api/v1/tcm/*` | 体质/舌象/辨证/方剂/订单 |
| 基因组 | `/api/v1/genome/*` | 上传/解读/PGx 报告 |
| 数据连接 | `/api/v1/connections/*` | CRUD/同步 |
| 报告 | `/api/v1/reports/*` | 健康摘要/FHIR 导出 |
| 仪表盘 | `/api/v1/dashboard/*` | 总览/趋势/风险评估 |
| 健康目标 | `/api/v1/goals/*` | CRUD/进度/统计 |
| 通知中心 | `/api/v1/notifications/*` | 列表/已读/删除 |
| 用药依从性 | `/api/v1/adherence/*` | 计划/记录/统计 |

## 配置

关键环境变量 (`.env`):

```
OCR_ENGINE=mock          # mock(开发) / paddleocr(生产)
DB_HOST=localhost
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret
```

## 测试

```bash
pytest tests/ -v
```

## 项目文档

- [HEALTHLENS_AGENDA.md](../HEALTHLENS_AGENDA.md) — 项目纲领
- [HEALTHLENS_SPEC.md](../HEALTHLENS_SPEC.md) — 技术规格
- [CLAUDEMD.md](../CLAUDEMD.md) — Agent 指令
