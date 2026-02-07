# API 路由架构重构方案

> **目标：** 统一路由前缀、消除前后端路由冲突、建立分层认证模型、提升健壮性和可维护性  
> **日期：** 2026-02-07  
> **预估工时：** 2-3 天（含前后端联调）

---

## 一、当前架构问题

### 1.1 路由前缀混乱

当前后端 45 个路由散布在三套前缀下，语义重叠且无统一管理：

```
/api/*      → 业务 API + 同步任务（20 个端点）
/panel/*    → 面板配置（5 个端点）
/admin/*    → 管理运维（20 个端点）
```

所有路由在各自文件中**硬编码完整路径**，`include_router` 未使用 `prefix` 参数，无法集中管理。

### 1.2 前后端路由冲突

前端 SPA 页面路由 `/admin` 与后端 API 前缀 `/admin/*` 冲突：

- Vite 开发代理拦截 `/admin` 页面请求，转发给后端 → 返回 404
- Nginx 生产配置中 `location /admin/` 也可能误匹配
- 当前用 `/admin/`（尾部斜杠）做临时规避，不够健壮

### 1.3 认证体系不一致

| 认证方式 | 端点数 | 说明 |
|----------|--------|------|
| `require_auth`（JWT） | 11 | 普通业务 API |
| `require_panel_admin`（仅检查开关） | 25 | 管理 API，**不验证 JWT** |
| 无认证 | 9 | 登录、webhook、以及遗漏的管理接口 |

**关键漏洞：**

- `require_panel_admin` **只检查环境变量开关**，不验证 JWT token，任何人都可以调用管理 API
- `/admin/mengla/status`、`/admin/backfill` 无任何认证
- Webhook 无签名校验

### 1.4 代理配置冗余

Vite 和 Nginx 都需要维护三个代理前缀（`/api`、`/panel`、`/admin`），每增加一个新前缀就要改三处配置。

---

## 二、目标架构

### 2.1 统一前缀：所有 API 收归 `/api/` 下

```
/api/auth/*           → 认证（登录、token 管理）
/api/data/*           → 业务数据查询（mengla、categories）
/api/webhook/*        → 外部回调
/api/panel/*          → 面板配置（原 /panel/*）
/api/admin/*          → 管理运维（原 /admin/*）
/api/sync-tasks/*     → 同步任务日志
/health               → 健康检查（无前缀）
```

**收益：**

- 前后端路由空间完全隔离，SPA 路由自由命名
- Vite / Nginx 只需代理 `/api/` 一个前缀
- 路由文件中只写相对路径，前缀由 `include_router(prefix=...)` 集中管理

### 2.2 三层认证模型

```
┌──────────────────────────────────────────────────────────┐
│                      Nginx / Vite 代理                    │
│              只代理 /api/* 和 /health                      │
└─────────────────────────┬────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │      FastAPI App       │
              └───────────┬───────────┘
                          │
          ┌───────────────┼───────────────────┐
          │               │                   │
    ┌─────▼─────┐  ┌──────▼──────┐  ┌────────▼────────┐
    │  公开层    │  │  用户层      │  │  管理员层        │
    │  无认证    │  │  require_auth│  │  require_admin   │
    │           │  │  (JWT)       │  │  (JWT + 开关)    │
    ├───────────┤  ├─────────────┤  ├─────────────────┤
    │ /auth/    │  │ /data/*     │  │ /admin/*        │
    │   login   │  │ /api/panel/ │  │ /sync-tasks/*   │
    │ /health   │  │   config GET│  │ /panel/* (写)   │
    │ /webhook/*│  │             │  │                 │
    └───────────┘  └─────────────┘  └─────────────────┘
```

**`require_admin` = JWT 认证 + 面板开关检查**，解决当前 `require_panel_admin` 不验证 token 的问题。

### 2.3 后端路由注册方式

```python
# backend/main.py

from fastapi import APIRouter

# 创建 /api 总路由器
api_router = APIRouter(prefix="/api")

api_router.include_router(auth_routes.router,      prefix="/auth",       tags=["认证"])
api_router.include_router(data_routes.router,       prefix="/data",       tags=["数据查询"])
api_router.include_router(webhook_routes.router,    prefix="/webhook",    tags=["Webhook"])
api_router.include_router(panel_routes.router,      prefix="/panel",      tags=["面板配置"])
api_router.include_router(admin_routes.router,      prefix="/admin",      tags=["管理运维"])
api_router.include_router(sync_task_routes.router,  prefix="/sync-tasks", tags=["同步任务"])

app.include_router(api_router)
```

路由文件中只写**相对路径**：

```python
# auth_routes.py（改造前）
@router.post("/api/auth/login")

# auth_routes.py（改造后）
@router.post("/login")          # 前缀 /api/auth 由 include_router 提供
```

---

## 三、路由映射表（改造前 → 改造后）

### 3.1 认证路由 `/api/auth/*`（不变）

| 改造前 | 改造后 | 方法 | 认证 |
|--------|--------|------|------|
| `/api/auth/login` | `/api/auth/login` | POST | 公开 |
| `/api/auth/generate-token` | `/api/auth/generate-token` | POST | `require_auth` |
| `/api/auth/me` | `/api/auth/me` | GET | `require_auth` |

### 3.2 数据查询路由 `/api/data/*`（合并 mengla + category）

| 改造前 | 改造后 | 方法 | 认证 |
|--------|--------|------|------|
| `/api/mengla/query` | `/api/data/mengla/query` | POST | `require_auth` |
| `/api/mengla/high` | `/api/data/mengla/high` | POST | `require_auth` |
| `/api/mengla/hot` | `/api/data/mengla/hot` | POST | `require_auth` |
| `/api/mengla/chance` | `/api/data/mengla/chance` | POST | `require_auth` |
| `/api/mengla/industry-view` | `/api/data/mengla/industry-view` | POST | `require_auth` |
| `/api/mengla/industry-trend` | `/api/data/mengla/industry-trend` | POST | `require_auth` |
| `/api/categories` | `/api/data/categories` | GET | `require_auth` |
| `/api/industry/daily` | `/api/data/industry/daily` | GET | `require_auth` |

### 3.3 Webhook 路由 `/api/webhook/*`（不变，加签名校验）

| 改造前 | 改造后 | 方法 | 认证 |
|--------|--------|------|------|
| `/api/webhook/mengla-notify` | `/api/webhook/mengla-notify` | GET | 公开 |
| `/api/webhook/mengla-notify` | `/api/webhook/mengla-notify` | POST | `require_webhook_sig` |

### 3.4 面板配置路由 `/api/panel/*`（从 `/panel` 迁移）

| 改造前 | 改造后 | 方法 | 认证 |
|--------|--------|------|------|
| `/panel/config` | `/api/panel/config` | GET | 公开 |
| `/panel/config` | `/api/panel/config` | PUT | `require_admin` |
| `/panel/tasks` | `/api/panel/tasks` | GET | `require_admin` |
| `/panel/tasks/{id}/run` | `/api/panel/tasks/{id}/run` | POST | `require_admin` |
| `/panel/data/fill` | `/api/panel/data/fill` | POST | `require_admin` |

### 3.5 管理运维路由 `/api/admin/*`（从 `/admin` 迁移）

| 改造前 | 改造后 | 方法 | 认证 |
|--------|--------|------|------|
| `/admin/mengla/status` | `/api/admin/mengla/status` | POST | **`require_admin`** ⚠️ 补认证 |
| `/admin/mengla/enqueue-full-crawl` | `/api/admin/mengla/enqueue-full-crawl` | POST | `require_admin` |
| `/admin/backfill` | `/api/admin/backfill` | POST | **`require_admin`** ⚠️ 补认证 |
| `/admin/scheduler/status` | `/api/admin/scheduler/status` | GET | `require_admin` |
| `/admin/scheduler/pause` | `/api/admin/scheduler/pause` | POST | `require_admin` |
| `/admin/scheduler/resume` | `/api/admin/scheduler/resume` | POST | `require_admin` |
| `/admin/tasks/cancel-all` | `/api/admin/tasks/cancel-all` | POST | `require_admin` |
| `/admin/data/purge` | `/api/admin/data/purge` | POST | `require_admin` |
| `/admin/metrics` | `/api/admin/metrics` | GET | `require_admin` |
| `/admin/metrics/latency` | `/api/admin/metrics/latency` | GET | `require_admin` |
| `/admin/alerts` | `/api/admin/alerts` | GET | `require_admin` |
| `/admin/alerts/history` | `/api/admin/alerts/history` | GET | `require_admin` |
| `/admin/alerts/check` | `/api/admin/alerts/check` | POST | `require_admin` |
| `/admin/alerts/silence` | `/api/admin/alerts/silence` | POST | `require_admin` |
| `/admin/cache/stats` | `/api/admin/cache/stats` | GET | `require_admin` |
| `/admin/cache/warmup` | `/api/admin/cache/warmup` | POST | `require_admin` |
| `/admin/cache/clear-l1` | `/api/admin/cache/clear-l1` | POST | `require_admin` |
| `/admin/circuit-breakers` | `/api/admin/circuit-breakers` | GET | `require_admin` |
| `/admin/circuit-breakers/reset` | `/api/admin/circuit-breakers/reset` | POST | `require_admin` |
| `/admin/system/status` | `/api/admin/system/status` | GET | `require_admin` |

### 3.6 同步任务路由 `/api/sync-tasks/*`（不变）

| 改造前 | 改造后 | 方法 | 认证 |
|--------|--------|------|------|
| `/api/sync-tasks/today` | `/api/sync-tasks/today` | GET | `require_admin` |
| `/api/sync-tasks/{log_id}` | `/api/sync-tasks/{log_id}` | GET | `require_admin` |
| `/api/sync-tasks/{log_id}/cancel` | `/api/sync-tasks/{log_id}/cancel` | POST | `require_admin` |
| `/api/sync-tasks/{log_id}` | `/api/sync-tasks/{log_id}` | DELETE | `require_admin` |

---

## 四、认证层改造

### 4.1 新增 `require_admin` 依赖

```python
# backend/api/deps.py

async def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    管理员认证 = JWT 验证 + 面板开关检查。
    同时解决两个问题：
    1. 当前 require_panel_admin 不验证 JWT
    2. 生产环境需要显式启用面板
    """
    # 1. 检查面板开关
    if not _panel_admin_enabled():
        raise HTTPException(403, "Panel admin is disabled")
    
    # 2. 验证 JWT token
    if credentials is None:
        raise HTTPException(401, "未提供认证凭证")
    return verify_token(credentials.credentials)
```

### 4.2 Webhook 签名校验

```python
# backend/api/deps.py

async def require_webhook_signature(request: Request) -> None:
    """
    校验外部回调的 HMAC 签名。
    Header: X-Webhook-Signature: sha256=<hex_digest>
    """
    api_key = os.getenv("COLLECT_SERVICE_API_KEY", "")
    if not api_key:
        return  # 未配置则跳过（开发环境）
    
    signature = request.headers.get("X-Webhook-Signature", "")
    body = await request.body()
    expected = "sha256=" + hmac.new(
        api_key.encode(), body, hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid webhook signature")
```

### 4.3 生产环境配置

在 `docker/.env.production` 中添加：

```env
# 显式启用管理面板（必须设置，否则管理 API 不可用）
ENABLE_PANEL_ADMIN=1
```

---

## 五、代理配置简化

### 5.1 Vite 开发代理（改造后）

```typescript
// frontend/vite.config.mts
proxy: {
  "/api": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
  "/health": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
}
// 只需要两条规则，不再有 /panel、/admin 代理
// 前端 SPA 路由 /admin、/panel 等不会被拦截
```

### 5.2 Nginx 生产配置（改造后）

```nginx
server {
    listen 80;
    server_name _;

    # ---------- 安全头 ----------
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # ---------- 唯一的 API 代理规则 ----------
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /health {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
    }

    # ---------- 前端 SPA ----------
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ---------- Gzip ----------
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    gzip_min_length 256;
}
```

从 4 条代理规则简化为 **2 条**，彻底消除前后端路由冲突风险。

---

## 六、前端改动清单

### 6.1 API 调用路径更新

| 文件 | 改造前 | 改造后 |
|------|--------|--------|
| `services/auth.ts` | `/api/auth/login` | 不变 |
| `services/sync-task-api.ts` | `/api/sync-tasks/*` | 不变 |
| `services/mengla-admin-api.ts` | `/panel/tasks`, `/admin/scheduler/*` | `/api/panel/tasks`, `/api/admin/scheduler/*` |
| `services/panel-config-api.ts` | `/panel/config` | `/api/panel/config` |
| `App.tsx` | `/panel/tasks/...` | `/api/panel/tasks/...` |
| `components/AdminCenter/DataSourceTaskManager.tsx` | `/admin/scheduler/*` | `/api/admin/scheduler/*` |

**改动规律：** 只需要给 `/panel/*` 和 `/admin/*` 调用加上 `/api` 前缀。`/api/*` 的调用不用改。

### 6.2 Vite 代理配置

移除 `/panel` 和 `/admin/` 两条代理，只保留 `/api` 和 `/health`。

---

## 七、后端改动清单

### 7.1 文件级改动

| 文件 | 改动内容 |
|------|----------|
| `backend/main.py` | 改用 `APIRouter(prefix="/api")` 集中注册路由 |
| `backend/api/deps.py` | 新增 `require_admin`、`require_webhook_signature` |
| `backend/api/auth_routes.py` | 路径去掉 `/api/auth` 前缀，改为相对路径 |
| `backend/api/category_routes.py` | 路径去掉 `/api` 前缀，合并到 data_routes 或保持独立 |
| `backend/api/mengla_routes.py` | 路径去掉 `/api/mengla` 前缀 |
| `backend/api/panel_routes.py` | 路径去掉 `/panel` 前缀，`require_panel_admin` → `require_admin` |
| `backend/api/admin_routes.py` | 路径去掉 `/admin` 前缀，无认证接口补 `require_admin` |
| `backend/api/sync_task_routes.py` | 路径去掉 `/api/sync-tasks` 前缀，`require_panel_admin` → `require_admin` |

### 7.2 `main.py` 改造示意

```python
from fastapi import APIRouter

# ---- 创建统一 API 路由器 ----
api_router = APIRouter(prefix="/api")

api_router.include_router(auth_routes.router,      prefix="/auth",       tags=["认证"])
api_router.include_router(mengla_routes.router,     prefix="/data/mengla",tags=["MengLa 数据"])
api_router.include_router(category_routes.router,   prefix="/data",       tags=["类目数据"])
api_router.include_router(webhook_routes.router,    prefix="/webhook",    tags=["Webhook"])
api_router.include_router(panel_routes.router,      prefix="/panel",      tags=["面板配置"])
api_router.include_router(admin_routes.router,      prefix="/admin",      tags=["管理运维"])
api_router.include_router(sync_task_routes.router,  prefix="/sync-tasks", tags=["同步任务"])

app.include_router(api_router)

# ---- 根路由（不在 /api 下）----
@app.get("/")
async def root():
    return {"message": "Industry Monitor API"}

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 八、迁移策略

### 8.1 分步执行，保持兼容

为避免一次性改动导致前后端联调困难，建议分 3 步执行：

```
步骤 1 (30min)  ──→  步骤 2 (2h)  ──→  步骤 3 (1h)
 认证层加固          后端路由迁移         前端 + 代理配置
                   + 旧路径重定向          清理旧重定向
```

### 步骤 1：认证层加固（不改路由路径）

1. 在 `deps.py` 中新增 `require_admin`（JWT + 开关）
2. 给 `/admin/mengla/status`、`/admin/backfill` 补上认证
3. 生产环境 `.env.production` 加 `ENABLE_PANEL_ADMIN=1`

**不影响现有功能，可独立上线。**

### 步骤 2：后端路由迁移 + 旧路径重定向

1. 改造 `main.py` 使用 `prefix` 注册
2. 各路由文件改为相对路径
3. 添加临时重定向（兼容旧路径）：

```python
# backend/api/compat.py — 临时兼容旧路径
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

compat_router = APIRouter(tags=["兼容-即将废弃"])

@compat_router.api_route("/panel/{path:path}", methods=["GET","POST","PUT","DELETE"])
async def panel_compat(path: str):
    return RedirectResponse(url=f"/api/panel/{path}", status_code=307)

@compat_router.api_route("/admin/{path:path}", methods=["GET","POST","PUT","DELETE"])
async def admin_compat(path: str):
    return RedirectResponse(url=f"/api/admin/{path}", status_code=307)
```

**旧路径仍可用（通过 307 重定向），前端不改也不会立即 break。**

### 步骤 3：前端 + 代理配置更新

1. 批量替换前端 API 调用路径
2. 简化 Vite 代理配置
3. 更新 Nginx 配置
4. 验证无误后移除步骤 2 的兼容重定向

---

## 九、Docker / 线上部署改动

本次路由重构涉及 **4 个** Docker 相关文件的改动。其中 nginx.conf 是热挂载（volume mount），更新后重启容器即可生效，无需重新构建镜像。

### 9.1 改动文件清单

| 文件 | 改动内容 | 是否需要重新构建镜像 |
|------|----------|---------------------|
| `docker/nginx/nginx.conf` | 删除 `/panel/` 和 `/admin/` location 块 | **否**（volume 挂载，重启生效） |
| `docker/.env.production` | 新增 `ENABLE_PANEL_ADMIN=1` | **否**（环境变量，重启生效） |
| `backend/**`（路由代码） | 路由前缀改造 | **是**（需重新构建后端镜像） |
| `frontend/**`（API 调用路径） | 路径前缀更新 | **是**（需重新构建前端/nginx 镜像） |
| `docker/docker-compose.yml` | 无改动 | — |
| `docker/release.sh` | 无改动 | — |
| `backend/Dockerfile` | 无改动 | — |
| `frontend/Dockerfile` | 无改动 | — |

### 9.2 `docker/nginx/nginx.conf` 改造

改造前（4 条代理规则）：

```nginx
location /api/   { proxy_pass http://backend:8000; ... }
location /panel/ { proxy_pass http://backend:8000; ... }   # ← 删除
location /admin/ { proxy_pass http://backend:8000; ... }   # ← 删除
location /health { proxy_pass http://backend:8000; ... }
```

改造后（2 条代理规则）：

```nginx
server {
    listen 80;
    server_name _;

    # ----- 安全响应头 -----
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ----- 请求限制 -----
    client_max_body_size 10m;
    proxy_read_timeout 300s;

    # ----- 前端静态文件 -----
    root /usr/share/nginx/html;
    index index.html;

    # ----- Gzip 压缩 -----
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;

    # ----- API 反向代理（唯一入口） -----
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
    }

    # ----- SPA 路由 -----
    location / {
        try_files $uri $uri/ /index.html;
    }

    # ----- 静态资源缓存 -----
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

> **说明：** 因为 `docker-compose.yml` 中 nginx 使用 volume 挂载 `./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro`，更新此文件后只需 `docker compose restart nginx` 即可生效，**无需重新构建 nginx 镜像**。

### 9.3 `docker/.env.production` 改造

新增以下环境变量：

```env
# ---- 管理面板 ----
# 显式启用管理面板（生产环境必须设置，否则管理 API 返回 403）
ENABLE_PANEL_ADMIN=1
```

> **说明：** 当前 `require_panel_admin` 在 `ENV` 未设置时默认启用。重构后新增的 `require_admin` 会同时检查 JWT + 此开关，显式设置更安全。

### 9.4 线上部署操作步骤

```bash
# ===== 1. 本地：构建并推送新镜像 =====
cd docker
bash release.sh
# → 自动构建 mengla-backend:latest 和 mengla-nginx:latest 并推送

# ===== 2. 服务器：更新配置文件 =====
# SSH 到生产服务器
ssh your-server

cd /path/to/docker      # docker-compose.yml 所在目录

# 2a. 更新 nginx.conf（删除 /panel/ 和 /admin/ location 块）
# 可以手动编辑，或从仓库拉取最新的 nginx.conf
vi nginx/nginx.conf     # 或 scp/git pull

# 2b. 更新 .env.production（新增 ENABLE_PANEL_ADMIN=1）
echo 'ENABLE_PANEL_ADMIN=1' >> .env.production

# ===== 3. 服务器：拉取新镜像并重启 =====
docker compose pull
docker compose up -d

# ===== 4. 验证 =====
# 检查容器状态
docker compose ps

# 检查后端健康
curl http://localhost:8000/health

# 检查 API 路由（应返回 401，而非 404 或直接响应数据）
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/admin/scheduler/status
# 期望: 401

# 检查旧路径重定向（步骤 2 期间，如果启用了兼容路由）
curl -s -o /dev/null -w "%{http_code}" http://localhost/panel/config
# 兼容期间期望: 307  |  清理后期望: 404

# 检查 SPA 页面
curl -s -o /dev/null -w "%{http_code}" http://localhost/admin
# 期望: 200 (返回 index.html)
```

### 9.5 回滚方案

如果上线后出现问题，可快速回滚：

```bash
# 回滚镜像到上一个版本
docker compose pull   # 如果已改 tag，改回 :latest
# 或指定旧版本 tag：
# docker compose -f docker-compose.yml up -d --no-deps backend

# 回滚 nginx.conf（恢复 /panel/ 和 /admin/ location 块）
git checkout HEAD~1 -- nginx/nginx.conf
docker compose restart nginx

# 回滚 .env.production（移除 ENABLE_PANEL_ADMIN=1）
# 通常不需要，保留也不影响旧代码
```

> **建议：** 在执行 `release.sh` 前记录当前版本 tag（`docker images | grep mengla`），便于回滚时指定。

---

## 十、验证检查清单

### 本地开发验证

- [ ] `python -c "from backend.main import app"` 无报错
- [ ] `GET /health` → `200`
- [ ] `POST /api/auth/login` → 正常登录
- [ ] `GET /api/data/categories` → 需要 token，无 token 返回 401
- [ ] `GET /api/admin/scheduler/status` → 需要 token + 面板开关
- [ ] `GET /api/panel/config` → 公开可访问
- [ ] `PUT /api/panel/config` → 需要 token
- [ ] 旧路径 `GET /panel/config` → 307 重定向（兼容期间）
- [ ] `POST /api/admin/mengla/status` → 需要 token（已补认证）

### 前端验证

- [ ] `http://localhost:5173/admin` → SPA 页面正常加载（不被代理拦截）
- [ ] 管理中心各功能正常（任务管理、同步日志、周期数据）
- [ ] 刷新任意 SPA 页面 → 不出现 `{"detail":"Not Found"}`
- [ ] 登录 → 登出 → 重新登录流程正常

### 线上 Docker 验证

- [ ] `docker compose ps` → 全部容器 healthy
- [ ] `curl http://localhost/health` → `{"status":"ok"}`
- [ ] `curl http://localhost/api/auth/login` → 返回 422（缺参数）而非 404
- [ ] `curl http://localhost/api/admin/scheduler/status` → 返回 401 而非直接响应
- [ ] `curl http://localhost/admin` → 返回 index.html（SPA 页面，非 404）
- [ ] `docker/nginx/nginx.conf` 中不再有 `/panel/` 和 `/admin/` location 块
- [ ] `docker/.env.production` 包含 `ENABLE_PANEL_ADMIN=1`
- [ ] 浏览器访问管理中心 → 功能正常（任务触发、同步日志查看）
