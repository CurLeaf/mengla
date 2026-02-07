#!/bin/bash

# 使脚本在遇到任何错误时自动退出
set -e

# 错误处理
error_handler() {
    local exit_code=$?
    local line_no=$1
    echo "Error on line $line_no. Exit code: $exit_code"
    exit $exit_code
}
trap 'error_handler $LINENO' ERR

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
REGISTRY="docker.cnb.cool/qzsyzn/docker"
BACKEND_IMAGE="${REGISTRY}/mengla-backend"
NGINX_IMAGE="${REGISTRY}/mengla-nginx"
VERSION=$(date +%Y%m%d%H%M)

export DOCKER_BUILDKIT=1

# 项目根目录（脚本在 docker/ 下，退一级）
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ---------------------------------------------------------------------------
# Step 1: 构建后端镜像
# ---------------------------------------------------------------------------
echo "========================================="
echo "[1/4] Building backend image..."
echo "========================================="
docker build \
    -f "${ROOT_DIR}/backend/Dockerfile" \
    -t "${BACKEND_IMAGE}:latest" \
    -t "${BACKEND_IMAGE}:${VERSION}" \
    "${ROOT_DIR}/backend"

echo "Backend build complete."

# ---------------------------------------------------------------------------
# Step 2: 构建前端 + Nginx 镜像（多阶段：node build → nginx 托管）
# ---------------------------------------------------------------------------
echo "========================================="
echo "[2/4] Building nginx (frontend) image..."
echo "========================================="
docker build \
    -f "${ROOT_DIR}/frontend/Dockerfile" \
    -t "${NGINX_IMAGE}:latest" \
    -t "${NGINX_IMAGE}:${VERSION}" \
    "${ROOT_DIR}"

echo "Nginx build complete."

# ---------------------------------------------------------------------------
# Step 3: 推送镜像
# ---------------------------------------------------------------------------
echo "========================================="
echo "[3/4] Pushing backend images..."
echo "========================================="
docker push "${BACKEND_IMAGE}:latest"
docker push "${BACKEND_IMAGE}:${VERSION}"

echo "========================================="
echo "[4/4] Pushing nginx images..."
echo "========================================="
docker push "${NGINX_IMAGE}:latest"
docker push "${NGINX_IMAGE}:${VERSION}"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "========================================="
echo "Release complete!"
echo "  Version:  ${VERSION}"
echo "  Backend:  ${BACKEND_IMAGE}:${VERSION}"
echo "  Nginx:    ${NGINX_IMAGE}:${VERSION}"
echo "========================================="
