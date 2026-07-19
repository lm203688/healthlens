#!/bin/bash
# ============================================================
# HealthLens ECS 部署脚本 (华为云)
# Usage:
#   ./scripts/deploy.sh              # 生产部署 (docker-compose.yml + docker-compose.prod.yml)
#   ./scripts/deploy.sh --dev        # 开发部署 (docker-compose.yml only)
#   ./scripts/deploy.sh --rollback   # 回滚到上一版本
# ============================================================
set -euo pipefail

# --- Config ---
COMPOSE_FILES="-f docker-compose.yml"
ENV_FILE=".env"
BACKUP_DIR="/opt/healthlens/backups"
HEALTH_TIMEOUT=120        # 秒
HEALTH_INTERVAL=3

# --- Parse args ---
MODE="prod"
for arg in "$@"; do
    case "$arg" in
        --dev)      MODE="dev" ;;
        --rollback) MODE="rollback" ;;
        --help|-h)
            echo "Usage: $0 [--dev|--rollback|--help]"
            exit 0 ;;
    esac
done

if [ "$MODE" = "prod" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.prod.yml"
    ENV_FILE=".env.production"
fi

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Prerequisites ---
check_prerequisites() {
    info "检查部署前置条件..."

    if ! command -v docker &> /dev/null; then
        error "Docker 未安装，请先安装 Docker Engine"
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        error "docker compose 未安装"
        exit 1
    fi

    if [ ! -f "$ENV_FILE" ]; then
        warn "$ENV_FILE 不存在"
        if [ -f ".env.example" ]; then
            cp .env.example "$ENV_FILE"
            warn "已从 .env.example 创建 $ENV_FILE，请编辑配置后重新运行"
        fi
        exit 1
    fi

    info "前置条件检查通过"
}

# --- Backup ---
backup_before_deploy() {
    mkdir -p "$BACKUP_DIR"
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
    mkdir -p "$BACKUP_PATH"

    info "备份数据库..."
    docker compose exec -T db pg_dump -U "${DB_USER:-healthlens}" "${DB_NAME:-healthlens}" \
        > "$BACKUP_PATH/db_dump.sql" 2>/dev/null || warn "数据库备份失败（可能首次部署）"

    cp "$ENV_FILE" "$BACKUP_PATH/"
    info "备份已保存到 $BACKUP_PATH"

    # 保留最近 10 个备份
    ls -dt "$BACKUP_DIR"/backup_* 2>/dev/null | tail -n +11 | xargs rm -rf 2>/dev/null || true
}

# --- Health Check ---
wait_for_healthy() {
    local service=$1
    local url=$2
    local elapsed=0

    info "等待 $service 就绪..."
    while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            info "$service 就绪 (${elapsed}s)"
            return 0
        fi
        sleep $HEALTH_INTERVAL
        elapsed=$((elapsed + HEALTH_INTERVAL))
    done

    error "$service 在 ${HEALTH_TIMEOUT}s 内未就绪"
    return 1
}

check_redis() {
    local elapsed=0
    info "等待 Redis 就绪..."
    while [ $elapsed -lt 30 ]; do
        if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
            info "Redis 就绪 (${elapsed}s)"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    error "Redis 在 30s 内未就绪"
    return 1
}

# --- Deploy ---
deploy() {
    info "=========================================="
    info "HealthLens 部署开始 (mode: $MODE)"
    info "=========================================="

    check_prerequisites
    backup_before_deploy

    # 停止旧容器
    info "停止旧容器..."
    docker compose $COMPOSE_FILES down --remove-orphans 2>/dev/null || true

    # 拉取最新镜像（生产环境）
    if [ "$MODE" = "prod" ]; then
        if [ -n "${IMAGE_TAG:-}" ]; then
            info "拉取镜像 $IMAGE_TAG..."
            docker compose $COMPOSE_FILES pull web worker 2>/dev/null || true
        fi
    fi

    # 构建（本地部署或无远程镜像时）
    info "构建 Docker 镜像..."
    docker compose $COMPOSE_FILES build web

    # 启动服务
    info "启动服务..."
    docker compose $COMPOSE_FILES --env-file "$ENV_FILE" up -d

    # 健康检查
    check_redis
    wait_for_healthy "PostgreSQL" "http://localhost:8000/health"

    # 数据库迁移
    info "运行数据库迁移..."
    docker compose $COMPOSE_FILES exec -T web alembic upgrade head || warn "Alembic 迁移失败，请手动检查"

    # 种子数据（首次部署创建 admin 用户）
    if docker compose exec -T web python -c "from app.database import *; from app.models.user import User; print('ok')" 2>/dev/null; then
        docker compose $COMPOSE_FILES exec -T web python scripts/seed_admin.py 2>/dev/null || true
    fi

    # 验证
    info "=========================================="
    info "部署验证"
    info "=========================================="
    echo ""

    API_RESPONSE=$(curl -sf http://localhost:${HTTP_PORT:-80}/health 2>/dev/null || echo "")
    if [ -n "$API_RESPONSE" ]; then
        info "API 服务: OK"
        echo "  响应: $API_RESPONSE"
    else
        error "API 服务: 异常（检查 nginx/web 日志）"
    fi

    # 服务状态
    docker compose $COMPOSE_FILES ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true

    echo ""
    info "=========================================="
    info "部署完成!"
    info "=========================================="
    if [ "$MODE" = "prod" ]; then
        echo "  API:     https://${DOMAIN:-localhost}"
        echo "  MinIO:   https://${DOMAIN:-localhost}:9000 (内部访问)"
        echo "  Nginx:   http://localhost:${HTTP_PORT:-80} / https://localhost:${HTTPS_PORT:-443}"
    else
        echo "  API:     http://localhost:8000"
        echo "  API Docs: http://localhost:8000/docs"
        echo "  MinIO:   http://localhost:9000 (Console: 9001)"
    fi
    echo ""
}

# --- Rollback ---
rollback() {
    LATEST_BACKUP=$(ls -dt "$BACKUP_DIR"/backup_* 2>/dev/null | head -1)
    if [ -z "$LATEST_BACKUP" ]; then
        error "没有可用的备份"
        exit 1
    fi

    warn "回滚到 $LATEST_BACKUP"
    docker compose $COMPOSE_FILES down --remove-orphans
    docker compose $COMPOSE_FILES up -d

    # 恢复数据库（仅在确认后）
    read -p "是否恢复数据库备份？[y/N] " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        docker compose exec -T db psql -U "${DB_USER:-healthlens}" -d "${DB_NAME:-healthlens}" \
            < "$LATEST_BACKUP/db_dump.sql"
        info "数据库已恢复"
    fi
}

# --- Main ---
cd "$(dirname "$0")/.."

case "$MODE" in
    deploy)   deploy ;;
    rollback) rollback ;;
    *)         deploy ;;
esac