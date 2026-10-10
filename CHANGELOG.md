# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.25.0] - 2026-10-10

### Added（阶段 A：国际化重评估 P0 落地）

**A3 管辖感知 Claims 引擎**（核心）
- `app/lib/claims_engine.py`：策略加载+缓存、21 类字段别名映射、端点级开关、敏感词扫描、按法域附加免责声明、审计留痕。fail-closed：未知法域回落 EU（最严）
- `claims_policy/cn.yaml` / `us_fda.yaml` / `uk_mhra.yaml` / `au_tga.yaml` / `eu_mdr.yaml`：五法域策略文件
- 已接入端点：`/diagnosis/analyze`、`/diagnosis/results`、`/diagnosis/results/{id}`、`/genome/pgx`

**A4 区域数据驻留代码级约束**
- `app/models/user.py`：新增 `region` / `jurisdiction` 字段（默认 cn）
- `alembic/versions/006_add_region_jurisdiction.py`：迁移 + 2 个索引
- `app/lib/region_guard.py`：`X-HL-Region` 请求头 → 环境变量 → 默认区域三级优先级；`enforce_region_match()` 强制拦截跨区域读写 PII

**A2 八轴参数外置（YAML + jurisdiction 维度）**
- `config/axes/axes.yaml`：8 轴 × 6+ 指标 × 5+ 阈值，支持法域覆盖
- `app/lib/axis_config.py`：加载器（`get_thresholds` / `get_threshold` / `get_axis_config`），缓存 + 硬编码 fallback

**A1 知识/数据平面分离骨架**
- `knowledge/`：`README.md` / `__init__.py` / `loader.py` / `MANIFEST.json` / `LICENSE`
- `KnowledgeLoader`：零 FastAPI 依赖，只读文件系统，向后兼容退化到 `data/`
- 资产清单：evidence 120 条 / pathways 38 条 / tcm_entities 613 条 / axis_config v1.0

### Changed

**A5 数据质量清理**
- `data/case_evidence_db.json` v1.3：清理 4 条 I 轴残留（CASE-024/025/026/029），加"已清理"note
- `data/pathway_to_syndrome_map.json`：59→**38** 通路，删除 21 个单字符/垃圾键
- 全仓轴数统一为 A-H 八轴（消除 I/J 论文漂移）

**A6 PGx 输出合规**
- `app/api/genome.py::/pgx` 接入 Claims 引擎；EU/US/UK 下 `pgx_pathogenic_grading=false` 返回 403 而非降级放行；CN 保留完整功能

### Security（合规）
- Wellness 边界从**文案纪律**升级为**代码策略**：字段过滤 + 端点级开关 + 按法域定制免责声明
- 遵循伊利诺伊州《Wellness and Oversight for Psychological Resources Act》(2025-08-01)：免责声明不再作为合规手段
- 未知法域 fail-closed 回落 EU（最严），跨区域读写 PII 直接 403

### Dependencies
- 新增 `pyyaml>=6.0`（Claims 引擎策略加载 + 八轴阈值加载）

### Version Unification
- `pyproject.toml` / `app/config.py` APP_VERSION / `mcp-server/server.json` / `PRINCIPLES.md` / `README.md` 同步到 **v0.25.0**

## [0.24.0] - 2026-10-09

### Changed (P0-4：伪 China-PAR 替换为"自评风险量表"表述)
- `app/core/risk_engine.py`：`ASCVDRiskEngine` / `DiabetesRiskEngine` 改名为**自评量表**（透明启发式，非 China-PAR/CDRS Cox 系数与 S0(t)），`MetabolicSyndromeEngine` 保留 CDS 五项真实阈值
- `RiskAssessmentResult` 新增 `disclaimer` 字段；`risk_type` 从 `"ascvd"`/`"diabetes"` 改为 `"ascvd_self_assess"`/`"diabetes_self_assess"`（`metabolic_syndrome` 保持不变）
- `assess_all()` 返回字典 key 同步改为 `ascvd_self_assess`/`diabetes_self_assess`/`metabolic_syndrome`
- `app/api/dashboard.py` `POST /risk-assessment` 响应新增全局 `disclaimer` 字段与每条 assessment 的 `references`/`disclaimer`，避免前端把倾向百分比误读为 10 年 ASCVD 概率
- `healthlens_agent/mcp_server.py` `hl_risk_assess` 描述改为自评量表口径，返回体带 `risk_type`/`references`/`disclaimer`
- 文档同步改口径：`README.md`、`CHANGELOG.md`、`docs/HealthLens_产品技术白皮书.md`、`healthlens/README.md`、`healthlens/CHANGELOG.md` — 全部去掉"China-PAR 模型""10 年心血管事件概率"表述
- 测试同步：`tests/core/test_risk_engine.py`、`tests/api/test_dashboard.py` 更新 `risk_type` 断言

### Security (合规)
- 对外表述统一为"自评风险量表"（`self_assessment_scale`），禁止再宣称"China-PAR 模型""10 年 ASCVD 风险预测"（P0-4 验收标准）
- 自评倾向百分比明确标注为**无量纲 0-100 指数**（非概率），disclaimer 明确"不构成诊断或治疗建议"

## [0.2.0-mcp] - 2026-09-24

### Added
- **HealthLens MCP Server (v0.2)**: 分层 MCP Server，安全默认暴露 L1+L2（无个人数据），L3（个性化）需 `HL_MCP_EXPOSE_PRIVATE=1` 环境变量
- **6 个 L1+L2 公开 tool**：`hl_health_check`、`hl_search_knowledge`、`hl_get_axis_detail`、`hl_get_wellness_article`、`hl_suggest_general_diet`、`hl_suggest_general_motion`
- **4 个 L3 私有 tool**（默认关闭）：`hl_fusion_engine`、`hl_risk_assess`、`hl_tcm_constitution`、`hl_evidence_grade`
- **MCP 分发元数据**：`mcp-server/server.json`（Registry schema）、`README.md`（安装+使用）、`.mcp.json`（客户端配置模板）、`LICENSE`、`test_install.sh`（验证脚本）
- **设计文档**：`docs/healthlens-mcp-design.md`（分层策略、数据边界、GDPR 影响、部署方案、注册市场清单）
- **上架指南**：`docs/mcp-marketplace-submission.md`（Glama/Registry/Smithery/mcp.so/PulseMCP 提交步骤 + 监控指标 + 回滚方案）
- **CLI 支持**：`python -m healthlens_agent mcp --demo / --jsonrpc / --tools`（JSON-RPC stdio fallback）
- **GDPR 免责声明**：每个 tool 描述嵌入 "not medical advice" 声明

### Changed
- `healthlens_agent/__main__.py`：转发 `mcp` 子命令参数给 `mcp_server`
- `healthlens_agent/mcp_server.py`：从扁平 tool 列表重构为分层注册表（L1/L2/L3）

### Security
- L1+L2 默认暴露，L3 关闭（`HL_MCP_EXPOSE_PRIVATE=0`）
- 每个 tool 明确标注数据边界（"No personal data" / "GDPR Art. 9"）
- 红线清单：checkin 记录、账号密码、中医处方判定、诊断输出永不通过 MCP 暴露

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
- 慢病风险自评量表: ASCVD（自评，非 China-PAR）+ 糖尿病（自评，非 CDRS）+ 代谢综合征（CDS 五项真实阈值）
- 健康管理: 目标 -> 进度 -> 依从性 -> 仪表盘
- 报告解析器: 22 种中英文体检指标正则匹配
- TCM 方剂库: 15 味中药, 方剂搜索引擎
- 数据连接器: 华为健康/Apple Health/Withings/小米/医院 LIS (Phase 1 Mock)
- Celery 异步任务: OCR/分析/诊断
- 通知服务: 数据库持久化

[0.7.0]: https://github.com/your-org/healthlens/releases/tag/v0.7.0
[0.8.2]: https://github.com/your-org/healthlens/releases/tag/v0.8.2
