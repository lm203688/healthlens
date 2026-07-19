# HealthLens v0.8.2 Release Notes

## Release Summary

HealthLens 健康全景平台 v0.8.2 是 Phase 1 的完整发布版本，包含中西医融合健康管理的全部核心功能、RBAC 权限系统、生产级部署配置和 CI/CD 流水线。

**145 tests passed | 0 failed | 21 database tables | 70+ API endpoints | 14 route modules**

---

## Quick Start

### Docker Compose (推荐)

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/healthlens.git
cd healthlens

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际密码和域名

# 3. 启动服务
docker compose up -d

# 4. 数据库迁移
docker compose exec web alembic upgrade head

# 5. 创建管理员账户
docker compose exec web python scripts/seed_admin.py

# 6. 验证
curl http://localhost:8000/health
```

### 生产部署 (华为云 ECS)

```bash
# 使用部署脚本 (自动备份 + 健康检查)
./scripts/deploy.sh

# 或手动
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d
```

### 本地开发

```powershell
# Windows
.\scripts\dev.bat          # 启动 API 服务
.\scripts\worker.bat       # 启动 Celery Worker
python -m pytest tests/    # 运行测试
```

---

## Architecture

```
                    +--------+
                    | Nginx  |  (HTTPS, Rate Limit)
                    +---+----+
                        |
              +---------+---------+
              |                   |
         +----+----+         +----+----+
         | Web API |         | Worker  |  (Celery)
         | (FastAPI)|        +----+----+
         +----+----+              |
              |              +----+----+
         +----+----+         |  Redis  |
         |PostgreSQL|        +----+----+
         |TimescaleDB|      +----+----+
         +----+----+         |  MinIO  |
              |              +---------+
         +----+----+
         |Prometheus|
         +---------+
```

---

## What's New in v0.8.2

### Security
- Fernet Token 加密存储
- 生产环境不安全密钥拒绝启动
- RBAC 三级权限 (patient/doctor/admin)
- Nginx 安全头 + 速率限制

### Deployment
- Docker 多阶段构建 (.dockerignore)
- docker-compose.prod.yml (资源限制 + 内网隔离)
- Nginx 反向代理 (HTTPS 预置)
- GitHub Actions CI/CD (自动测试 + 部署 + 回滚)
- ECS 部署脚本 (备份 + 健康检查)

### Monitoring
- Prometheus /metrics 端点
- 自动请求计数和延迟采集
- 路径归一化 (UUID/ID 参数化)

### Bug Fixes
- Xiaomi 连接器名称修复
- 诊断审核权限修复
- Alembic 迁移修复
- 依赖版本同步

---

## Configuration

### Required Secrets (Production)

| Variable | Description |
|----------|-------------|
| `DB_PASSWORD` | PostgreSQL strong password |
| `JWT_SECRET_KEY` | 64-char random string |
| `MINIO_SECRET_KEY` | MinIO strong secret |
| `REDIS_PASSWORD` | Redis auth password |
| `CORS_ORIGINS` | JSON array of allowed domains |

### GitHub Actions Secrets

| Secret | Purpose |
|--------|---------|
| `REGISTRY_USERNAME` | Container registry auth |
| `REGISTRY_PASSWORD` | Container registry auth |
| `ECS_HOST` | Huawei Cloud ECS IP |
| `ECS_USER` | SSH username |
| `ECS_SSH_KEY` | SSH private key |

---

## Phase 2 Roadmap

- [ ] Deep Learning OCR (PaddleOCR fine-tuned)
- [ ] LLM-powered report interpretation
- [ ] Real data connector APIs (Huawei Health, Withings)
- [ ] WebSocket real-time notifications
- [ ] Mobile API optimization
- [ ] Kubernetes deployment
