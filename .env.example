# HealthLens 环境配置模板
# 复制此文件为 .env 或 .env.production 并填入实际值

# 应用
APP_NAME=HealthLens
# 注意：不要在此配置 APP_VERSION。
# 版本单一真源是 pyproject.toml 的 [project].version，由 app/core/version.py 读取，
# 并由 tests/core/test_version.py 断言 CHANGELOG 顶部版本与之一致。
# 若在 .env 中设置 APP_VERSION，pydantic-settings 会静默覆盖真源值，造成版本漂移。
DEBUG=false

# 数据库 (PostgreSQL + TimescaleDB)
DB_HOST=db
DB_PORT=5432
DB_USER=healthlens
DB_PASSWORD=CHANGE_ME_STRONG_DB_PASSWORD
DB_NAME=healthlens
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis (缓存 + Celery Broker)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT}/0
CELERY_BROKER_URL=redis://${REDIS_HOST}:${REDIS_PORT}/1
CELERY_RESULT_BACKEND=redis://${REDIS_HOST}:${REDIS_PORT}/2

# JWT
JWT_SECRET_KEY=CHANGE_ME_RANDOM_64_CHAR_STRING
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# MinIO (对象存储)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=CHANGE_ME_MINIO_ACCESS_KEY
MINIO_SECRET_KEY=CHANGE_ME_MINIO_SECRET_KEY
MINIO_BUCKET=healthlens
MINIO_SECURE=false

# OCR 引擎 (mock / tesseract / paddleocr)
OCR_ENGINE=paddleocr
OCR_LANGUAGE=chi_sim+eng

# CORS (生产环境应设为具体域名 JSON 数组)
CORS_ORIGINS=["https://your-domain.com"]

# 日志
LOG_LEVEL=INFO

# ------------------------------------------------------------------
# 品牌原生连接器 OAuth2 凭据（S1-5）
# 全部留空 → 连接器 fail-loud 拒服务，绝不返回 mock（反骨架化原则）。
# 填齐 client_id / client_secret / redirect_uri 即接通，无需改代码。
# ------------------------------------------------------------------
WITHINGS_CLIENT_ID=
WITHINGS_CLIENT_SECRET=
WITHINGS_REDIRECT_URI=https://healthlens.cc/api/v1/connections/withings/callback

HUAWEI_HEALTH_CLIENT_ID=
HUAWEI_HEALTH_CLIENT_SECRET=
HUAWEI_HEALTH_REDIRECT_URI=https://healthlens.cc/api/v1/connections/huawei/callback

XIAOMI_HEALTH_CLIENT_ID=
XIAOMI_HEALTH_CLIENT_SECRET=
XIAOMI_HEALTH_REDIRECT_URI=https://healthlens.cc/api/v1/connections/xiaomi/callback