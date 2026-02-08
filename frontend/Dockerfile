# ---- Stage 1: Build ----
# 构建上下文为项目根目录（pnpm workspace monorepo）
FROM node:20-alpine AS build

WORKDIR /app

RUN corepack enable

# 先复制依赖文件，利用 Docker 缓存
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY frontend/package.json frontend/

# 安装全部 workspace 依赖（确保 hoisted 依赖正确解析）
RUN pnpm install --frozen-lockfile

# 复制前端源码
COPY frontend/ frontend/

# 构建时注入 API 地址为空，让前端使用相对路径（由 Nginx 代理）
ENV VITE_API_BASE_URL=""
RUN pnpm --filter industry-monitor-frontend build

# ---- Stage 2: Serve with Nginx ----
FROM nginx:alpine

# 移除默认配置（由 docker-compose volume 挂载 nginx.conf）
RUN rm /etc/nginx/conf.d/default.conf

# 复制构建产物到 Nginx 静态目录
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
