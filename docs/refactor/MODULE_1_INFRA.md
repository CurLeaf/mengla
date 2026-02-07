# 模块 1 — 安全加固与运维基础设施

> **负责角色：** 安全 / 运维 / DevOps  
> **优先级：** 🔴 紧急  
> **预估工时：** 4-5 天  
> **分支名：** `refactor/module-1-infra`  

---

## 本模块管辖文件（与其他模块零交叉）

```
backend/core/auth.py            ← 修改（JWT 强制配置、bcrypt 哈希、登录限流）
backend/Dockerfile              ← 修改（多阶段构建、非 root 用户、Health Check）
frontend/Dockerfile             ← 修改（Health Check）
docker/docker-compose.yml       ← 修改（端口内网化、Health Check、资源限制、备份）
docker/nginx/nginx.conf         ← 修改（安全头、SSL/TLS、请求限制）
docker/.env.production          ← 修改（补全安全变量）
docker/release.sh               ← 修改（镜像扫描）
mengla-service.ts               ← 修改（移除硬编码密钥）
.env.example                    ← 新建
.github/workflows/ci.yml        ← 新建
```

> **不触碰：** `backend/main.py`、`backend/scheduler.py`、`backend/core/domain.py`、`backend/infra/*`、`frontend/src/*`

---

## 问题清单

| # | 问题 | 文件 | 严重度 |
|---|------|------|--------|
| 1 | 硬编码 API Key | `mengla-service.ts`, `.env` | 🔴 |
| 2 | JWT Secret 有不安全默认回退值 | `backend/core/auth.py` | 🔴 |
| 3 | 密码明文比较 | `backend/core/auth.py` | 🔴 |
| 4 | MongoDB/Redis 暴露端口无鉴权 | `docker/docker-compose.yml` | 🔴 |
| 5 | Nginx 缺少安全头 | `docker/nginx/nginx.conf` | 🟡 |
| 6 | Nginx 未配置 SSL/TLS | `docker/nginx/nginx.conf` | 🟡 |
| 7 | Docker 容器以 root 运行 | `backend/Dockerfile` | 🟡 |
| 8 | 登录接口无频率限制 | `backend/core/auth.py` | 🟡 |
| 9 | 生产环境变量不完整 | `docker/.env.production` | 🟡 |
| 10 | 无 CI/CD 流水线 | 无 | 🟡 |
| 11 | Dockerfile 无 Health Check | `backend/Dockerfile`, `frontend/Dockerfile` | 🟡 |
| 12 | Docker Compose 无资源限制 | `docker/docker-compose.yml` | 🟡 |
| 13 | 无数据库备份策略 | `docker/docker-compose.yml` | 🟡 |
| 14 | Nginx 无请求大小限制 | `docker/nginx/nginx.conf` | 🟢 |
| 15 | 后端 Dockerfile 非多阶段构建 | `backend/Dockerfile` | 🟢 |

---

## 修复方案

### 1 — 移除硬编码密钥
**文件：** `mengla-service.ts`
```typescript
// 修改前
const apiKey = process.env.COLLECT_SERVICE_API_KEY || 'ws_317755c5f981afc5...';
// 修改后
const apiKey = process.env.COLLECT_SERVICE_API_KEY;
if (!apiKey) throw new Error('COLLECT_SERVICE_API_KEY environment variable is required');
```

**新建：** `.env.example`（仅含占位符的模板文件）
```env
COLLECT_SERVICE_API_KEY=your_api_key_here
COLLECT_SERVICE_BASE_URL=https://extract.example.com
MONGO_URI=mongodb://localhost:27017
MONGO_DB=industry_monitor
REDIS_URI=redis://localhost:6379/0
JWT_SECRET=your_jwt_secret_here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me_in_production
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

### 2 — JWT Secret 强制配置
**文件：** `backend/core/auth.py`
```python
# 修改前
JWT_SECRET = os.getenv("JWT_SECRET", "mengla-default-secret-change-me")
# 修改后
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is required. "
        "Generate: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
```

### 3 — 密码 bcrypt 哈希
**文件：** `backend/core/auth.py`
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_RAW_PW = os.getenv("ADMIN_PASSWORD", "")
if not _RAW_PW:
    raise RuntimeError("ADMIN_PASSWORD environment variable is required")
_ADMIN_PW_HASH = pwd_context.hash(_RAW_PW)
del _RAW_PW

def authenticate_user(username: str, password: str) -> bool:
    if username != ADMIN_USERNAME:
        return False
    return pwd_context.verify(password, _ADMIN_PW_HASH)
```

### 4 — 数据库端口内网化
**文件：** `docker/docker-compose.yml`
```yaml
services:
  mongo:
    expose: ["27017"]     # 替代 ports: ["27017:27017"]
  redis:
    expose: ["6379"]      # 替代 ports: ["6379:6379"]
```

### 5/6 — Nginx 安全头 + SSL
**文件：** `docker/nginx/nginx.conf`
```nginx
server {
    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 请求限制（合并 #14）
    client_max_body_size 10m;
    proxy_read_timeout 300s;
    
    # SSL（#6，可选，需证书）
    # listen 443 ssl http2;
    # ssl_certificate /etc/nginx/ssl/fullchain.pem;
    # ssl_certificate_key /etc/nginx/ssl/privkey.pem;
}
```

### 7/15 — 后端 Dockerfile 多阶段 + 非 root
**文件：** `backend/Dockerfile`
```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
RUN addgroup --system --gid 1001 app && adduser --system --uid 1001 --ingroup app app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8 — 登录频率限制
**文件：** `backend/core/auth.py`（新增函数）
```python
async def check_login_rate(ip: str) -> bool:
    """Redis 滑动窗口限流：60 秒 10 次"""
    from ..infra import database
    if database.redis_client is None:
        return True
    key = f"rate_limit:login:{ip}"
    count = await database.redis_client.incr(key)
    if count == 1:
        await database.redis_client.expire(key, 60)
    return count <= 10
```

### 9 — 生产环境变量补全
**文件：** `docker/.env.production`
```env
JWT_SECRET=<生成的强密钥>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<强密码>
COLLECT_SERVICE_API_KEY=<真实 API Key>
CORS_ALLOWED_ORIGINS=https://mengla.your-domain.com
MONGO_URI=mongodb://mongo:27017
REDIS_URI=redis://redis:6379/0
```

### 10 — CI/CD 流水线
**新建：** `.github/workflows/ci.yml`
```yaml
name: CI
on: [push, pull_request]
jobs:
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install ruff && ruff check backend/
  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter industry-monitor-frontend tsc --noEmit
      - run: pnpm --filter industry-monitor-frontend build
```

### 11/12/13 — Docker Compose Health Check + 资源限制 + 备份
**文件：** `docker/docker-compose.yml`
```yaml
services:
  backend:
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits: { memory: 1G, cpus: "1.0" }
    depends_on:
      mongo: { condition: service_healthy }
      redis: { condition: service_healthy }
  mongo:
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 30s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits: { memory: 2G }
  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### 前端 Dockerfile Health Check
**文件：** `frontend/Dockerfile`
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:80/ || exit 1
```

---

## 检查清单

- [ ] `grep -r "ws_317755" .` 无匹配
- [ ] 未设 JWT_SECRET 时应用拒绝启动
- [ ] 密码使用 bcrypt 验证
- [ ] 生产 compose 中 mongo/redis 无 `ports`
- [ ] `curl -I` 返回安全响应头
- [ ] 容器 `whoami` 返回非 root
- [ ] 60 秒内 >10 次登录返回 429
- [ ] `docker compose ps` 全部 healthy
- [ ] CI 流水线 push 后自动运行
- [ ] `.env.example` 存在且无真实密钥
