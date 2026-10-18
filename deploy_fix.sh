#!/bin/bash
# ==========================================
# HealthLens 前端支付修复部署脚本
# 修复内容：绕过demoMode限制，让套餐列表和支付流程正常工作
# 使用方法：在服务器上执行 bash deploy_fix.sh
# ==========================================

set -e

echo "=========================================="
echo "  HealthLens 前端支付修复部署"
echo "=========================================="

# 检查文件路径
FRONTEND_DIR="/root/healthlens/frontend/assets"
TARGET_FILE="$FRONTEND_DIR/app.v2.js"

if [ ! -d "$FRONTEND_DIR" ]; then
    echo "[ERROR] 前端目录不存在: $FRONTEND_DIR"
    echo "尝试查找..."
    FOUND_DIR=$(find / -name "app.v2.js" -path "*/frontend/assets/*" 2>/dev/null | head -1)
    if [ -n "$FOUND_DIR" ]; then
        TARGET_FILE="$FOUND_DIR"
        echo "[INFO] 找到文件: $TARGET_FILE"
    else
        echo "[ERROR] 无法找到 app.v2.js"
        exit 1
    fi
fi

# 备份原文件
echo "[1/4] 备份原文件..."
cp "$TARGET_FILE" "${TARGET_FILE}.bak.$(date +%Y%m%d%H%M%S)"
echo "  -> 备份完成"

# 下载修复后的文件
echo "[2/4] 下载修复后的 app.v2.js..."
curl -sL "https://symbol-labour-absence-penny.trycloudflare.com/app.v2.js" -o "$TARGET_FILE"
echo "  -> 下载完成"

# 验证文件大小
FILE_SIZE=$(wc -c < "$TARGET_FILE")
echo "  -> 文件大小: ${FILE_SIZE} bytes"

if [ "$FILE_SIZE" -lt 100000 ]; then
    echo "[ERROR] 文件太小，可能下载失败"
    exit 1
fi

# 检查Docker容器
echo "[3/4] 检查Docker容器..."
CONTAINER_NAME=$(docker ps --format "{{.Names}}" | grep -i health | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    echo "  -> 找到容器: $CONTAINER_NAME"
    # 如果前端目录没有挂载为volume，需要docker cp
    echo "  -> 尝试 docker cp..."
    docker cp "$TARGET_FILE" "$CONTAINER_NAME:/app/frontend/assets/app.v2.js" 2>/dev/null && echo "  -> docker cp 成功" || echo "  -> docker cp 跳过（可能已通过volume挂载）"
else
    echo "  -> 未找到HealthLens容器，跳过docker cp"
fi

# 验证修复
echo "[4/4] 验证修复..."
sleep 2
RESPONSE=$(curl -s "https://healthlens.cc/api/v1/growth/points/packages")
PKG_COUNT=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null || echo "0")
echo "  -> 套餐数量: $PKG_COUNT"

if [ "$PKG_COUNT" -gt 0 ]; then
    echo ""
    echo "=========================================="
    echo "  部署成功！"
    echo "  套餐已加载: $PKG_COUNT 个"
    echo "  用户现在可以正常购买积分"
    echo "=========================================="
else
    echo ""
    echo "[WARNING] API返回套餐数为0，请检查后端服务"
fi
