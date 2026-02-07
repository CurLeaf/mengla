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
echo "[1/6] Building backend image..."
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
echo "[2/6] Building nginx (frontend) image..."
echo "========================================="
docker build \
    -f "${ROOT_DIR}/frontend/Dockerfile" \
    -t "${NGINX_IMAGE}:latest" \
    -t "${NGINX_IMAGE}:${VERSION}" \
    "${ROOT_DIR}"

echo "Nginx build complete."

# ---------------------------------------------------------------------------
# Step 3: 镜像安全扫描（可选，若 trivy/docker scout 不可用则跳过）
# ---------------------------------------------------------------------------
echo "========================================="
echo "[3/6] Scanning images for vulnerabilities..."
echo "========================================="
if command -v trivy &> /dev/null; then
    echo "Using trivy for scanning..."
    trivy image --severity HIGH,CRITICAL "${BACKEND_IMAGE}:latest" || echo "⚠️ Backend image scan found issues (non-blocking)"
    trivy image --severity HIGH,CRITICAL "${NGINX_IMAGE}:latest" || echo "⚠️ Nginx image scan found issues (non-blocking)"
elif docker scout version &> /dev/null 2>&1; then
    echo "Using docker scout for scanning..."
    docker scout cves "${BACKEND_IMAGE}:latest" --only-severity critical,high || echo "⚠️ Backend image scan found issues (non-blocking)"
    docker scout cves "${NGINX_IMAGE}:latest" --only-severity critical,high || echo "⚠️ Nginx image scan found issues (non-blocking)"
else
    echo "⚠️ No scanner available (trivy / docker scout). Skipping image scan."
fi

# ---------------------------------------------------------------------------
# Step 4: 推送镜像
# ---------------------------------------------------------------------------
echo "========================================="
echo "[4/6] Pushing backend images..."
echo "========================================="
docker push "${BACKEND_IMAGE}:latest"
docker push "${BACKEND_IMAGE}:${VERSION}"

echo "========================================="
echo "[5/6] Pushing nginx images..."
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
