# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.8.2] - 2026-07-20

### Added
- **RBAC 权限系统**: RoleChecker 依赖注入, require_doctor/require_admin/require_doctor_or_admin
- **处方管理**: POST/GET/GET{id}/PUT{id} 4 个 API 端点, RX 编号自动生成
- **TesseractOCR 引擎**: 完整的 pytesseract + pdf2image 实现
- **Token 加密**: Fernet 对称加密 OAuth access_token (cryptography)
- **安全启动校验**: 非 DEBUG 模式检测不安全密钥直接 SystemExit(1)
- **角色管理 API**: PUT /auth/role (仅 admin), seed_admin.py 种子脚本
- **Celery Worker 健康检查**: docker-compose.yml + docker-compose.prod.yml
- **Prometheus 监控**: /metrics 端点, RequestMetricsMiddleware (请求计数/延迟/路径归一化)
- **Docker 生产部署**: .dockerignore, 多阶段构建 (pyproject.toml), ENTRYPOINT+CMD 分离
- **Nginx 反向代理**: HTTPS 准备, 速率限制 10r/s, 安全头, 50M 上传限制
- **CI/CD 流水线**: GitHub Actions ci.yml (lint+test+build) + deploy.yml (tag 触发+自动回滚)
- **ECS 部署脚本**: --dev/--rollback 模式, Redis 正确检查, 轮询健康检查, pg_dump 备份
- **docker-compose.prod.yml**: 资源限制, 内网端口隔离, Redis 密码认证, Nginx 服务

### Fixed
- **xiaomi 连接器名称**: "xiaomi" -> "xiaomi_health" (ALLOWED_SOURCE_TYPES 与注册名称不匹配导致同步永远失败)
- **诊断审核权限**: 移除 user_id 过滤, 医生可审核所有患者诊断 (非仅自己)
- **Alembic 迁移不可用**: env.py 未导入 settings, DATABASE_URL 为空; 修复为自动从 settings 回填
- **requirements.txt 不同步**: 缺 cryptography/pytesseract/prometheus-client, 19 个包无版本约束; 全部补齐
- **分页一致性**: records/connections/genome 列表端点补齐 page/page_size/total/total_pages
- **Celery SessionLocal**: 空引用 -> 惰性工厂 (避免 SQLite 开发环境导入 psycopg2)
- **CORS 安全**: 硬编码 ["*"] -> settings.CORS_ORIGINS 可配置
- **Dashboard**: diagnosis_name AttributeError -> diagnosis_text
- **版本号统一**: pyproject.toml/config.py/.env 全部对齐 v0.8.2
- **MINIO_BUCKET**: .env.production MINIO_BUCKET_NAME -> MINIO_BUCKET (与 config.py 一致)

### Changed
- **依赖**: pyproject.toml 新增 cryptography/pytesseract/pdf2image/paddleocr/paddlepaddle/prometheus-client
- **Dockerfile**: requirements.txt -> pyproject.toml, 补全 OCR 系统库 (tesseract/libgl)
- **reports.py**: 分析报告解析返回完整指标列表 (含正常项)
- **health_analyzer**: risk_factors 区分 high/borderline 级别, 基于异常数量分级建议
- **observations**: stats 端点返回 std_dev/cv_percent/by_category

### Security
- Token 加密存储 (Fernet, SHA256 of JWT_SECRET_KEY)
- 生产环境不安全密钥拒绝启动
- RBAC 权限控制 (patient/doctor/admin 三级)
- CORS 可配置 (生产环境禁止通配符)
- Redis 密码认证 (docker-compose.prod.yml)
- Nginx 安全头 (X-Frame-Options, X-Content-Type-Options, HSTS)
- 资源限制防 OOM (CPU/Memory limits)

## [0.7.0] - 2026-07-18

### Added
- FastAPI 应用骨架 (14 路由模块, 21 数据库表)
- 西医诊断流程: 上传 -> OCR -> 异常检测 -> ICD-11 诊断 -> 处方推荐 -> FHIR 导出
- 中医辨证流程: 体质问卷 (9 种) -> AI 辨证 -> 方剂推荐 -> 配送订单 (状态机)
- 慢病风险评估: ASCVD (China-PAR) + 糖尿病 (CDRS) + 代谢综合征 (CDS)
- 健康管理: 目标 -> 进度 -> 依从性 -> 仪表盘
- 报告解析器: 22 种中英文体检指标正则匹配
- TCM 方剂库: 15 味中药, 方剂搜索引擎
- 数据连接器: 华为健康/Apple Health/Withings/小米/医院 LIS (Phase 1 Mock)
- Celery 异步任务: OCR/分析/诊断
- 通知服务: 数据库持久化

[0.7.0]: https://github.com/your-org/healthlens/releases/tag/v0.7.0
[0.8.2]: https://github.com/your-org/healthlens/releases/tag/v0.8.2
