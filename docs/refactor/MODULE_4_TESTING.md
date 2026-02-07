# 模块 4 — 测试体系建设

> **负责角色：** 全员（后端为主、前端配合）  
> **优先级：** 🟡 重要  
> **预估工时：** 持续推进，初始框架 3 天  
> **分支名：** `refactor/module-4-testing`  

---

## 本模块管辖文件（与其他模块零交叉）

```
tests/                               ← 新建（整个测试目录）
  ├── conftest.py                    ← Mock fixture 总集
  ├── backend/
  │   ├── __init__.py
  │   ├── test_auth.py               ← 认证 API 测试
  │   ├── test_categories.py         ← 分类 API 测试
  │   ├── test_mengla_query.py       ← 数据查询单元测试
  │   ├── test_cache.py              ← 缓存逻辑测试
  │   ├── test_period.py             ← 周期计算测试
  │   ├── test_scheduler.py          ← 调度器测试
  │   └── test_api_integration.py    ← API 集成测试
  ├── frontend/
  │   ├── setup.ts                   ← Vitest 初始化
  │   ├── RankPage.test.tsx          ← 排名页测试
  │   ├── AuthGuard.test.tsx         ← 鉴权守卫测试
  │   └── Toast.test.tsx             ← Toast 组件测试
requirements-dev.txt                 ← 新建（测试依赖）
pyproject.toml                       ← 新建（pytest 配置）
frontend/vitest.config.ts            ← 新建（Vitest 配置）
```

> **不触碰：** `backend/*`（源码）、`frontend/src/*`（源码）、`docker/*`  
> **说明：** 本模块仅新增文件，不修改任何已有源码文件，因此与其他模块完全不冲突。  
> 建议在模块 2/3 完成后编写测试，但框架搭建可提前进行。

---

## 问题清单

| # | 问题 | 严重度 |
|---|------|--------|
| 1 | 零测试覆盖 | 🟡 |
| 2 | 无后端测试框架 | 🟡 |
| 3 | 无前端测试框架 | 🟡 |
| 4 | 无 Mock 基础设施（MongoDB、Redis） | 🟡 |
| 5 | 关键路径（认证、缓存、周期）无单元测试 | 🟡 |

---

## 搭建方案

### 一、后端测试框架

#### 1.1 安装依赖
**新建：** `requirements-dev.txt`
```txt
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=5.0
httpx>=0.27
mongomock-motor>=0.0.29
fakeredis[aioredis]>=2.21
```

#### 1.2 pytest 配置
**新建：** `pyproject.toml`
```toml
[tool.pytest.ini_options]
testpaths = ["tests/backend"]
asyncio_mode = "auto"
python_files = "test_*.py"
python_functions = "test_*"
addopts = "--cov=backend --cov-report=term-missing --cov-fail-under=30"
```

#### 1.3 Mock Fixture 总集
**新建：** `tests/conftest.py`
```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def mock_mongo():
    """使用 mongomock-motor 提供内存 MongoDB"""
    from mongomock_motor import AsyncMongoMockClient
    client = AsyncMongoMockClient()
    db = client["test_industry_monitor"]
    yield db
    client.close()

@pytest.fixture
async def mock_redis():
    """使用 fakeredis 提供内存 Redis"""
    import fakeredis.aioredis
    redis = fakeredis.aioredis.FakeRedis()
    yield redis
    await redis.flushall()
    await redis.aclose()

@pytest.fixture
async def app_client(mock_mongo, mock_redis):
    """带 mock 依赖的 FastAPI 测试客户端"""
    from backend.infra import database
    
    # Patch 数据库连接
    with patch.object(database, 'mongo_db', mock_mongo), \
         patch.object(database, 'redis_client', mock_redis):
        from backend.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

@pytest.fixture
def auth_headers():
    """生成有效的 JWT token header"""
    import os
    os.environ.setdefault("JWT_SECRET", "test-secret-for-testing")
    os.environ.setdefault("ADMIN_USERNAME", "testadmin")
    os.environ.setdefault("ADMIN_PASSWORD", "testpass123")
    
    from backend.core.auth import create_access_token
    token = create_access_token({"sub": "testadmin"})
    return {"Authorization": f"Bearer {token}"}
```

#### 1.4 后端单元测试示例

**`tests/backend/test_auth.py`:**
```python
import pytest

class TestAuthAPI:
    async def test_login_success(self, app_client):
        response = await app_client.post("/auth/login", json={
            "username": "testadmin",
            "password": "testpass123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, app_client):
        response = await app_client.post("/auth/login", json={
            "username": "testadmin",
            "password": "wrong"
        })
        assert response.status_code == 401

    async def test_protected_route_without_token(self, app_client):
        response = await app_client.get("/admin/scheduler/status")
        assert response.status_code == 401

    async def test_protected_route_with_token(self, app_client, auth_headers):
        response = await app_client.get("/admin/scheduler/status", headers=auth_headers)
        assert response.status_code == 200
```

**`tests/backend/test_period.py`:**
```python
from backend.utils.period import (
    get_default_timest_for_period,
    calculate_trend_range,
)

class TestPeriodCalculation:
    def test_daily_default_timest(self):
        result = get_default_timest_for_period("day")
        assert result is not None
        assert len(result) == 10  # YYYY-MM-DD 格式

    def test_monthly_default_timest(self):
        result = get_default_timest_for_period("month")
        assert result is not None
        assert len(result) == 7   # YYYY-MM 格式

    def test_trend_range_returns_start_end(self):
        start, end = calculate_trend_range("day", months=6)
        assert start < end
```

**`tests/backend/test_cache.py`:**
```python
import pytest

class TestCacheManager:
    async def test_l1_cache_set_and_get(self, mock_redis):
        from backend.infra.cache import CacheManager
        cm = CacheManager(redis_client=mock_redis)
        
        await cm.set("test_key", {"value": 42}, ttl=60)
        result = await cm.get("test_key")
        assert result == {"value": 42}

    async def test_l1_cache_miss(self, mock_redis):
        from backend.infra.cache import CacheManager
        cm = CacheManager(redis_client=mock_redis)
        
        result = await cm.get("nonexistent")
        assert result is None

    async def test_cache_clear(self, mock_redis):
        from backend.infra.cache import CacheManager
        cm = CacheManager(redis_client=mock_redis)
        
        await cm.set("key1", "val1", ttl=60)
        await cm.clear_l1()
        result = await cm.get("key1")
        assert result is None
```

**`tests/backend/test_api_integration.py`:**
```python
import pytest

class TestMenglaAPI:
    async def test_get_categories(self, app_client):
        response = await app_client.get("/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_health_check(self, app_client):
        response = await app_client.get("/health")
        assert response.status_code == 200

    async def test_openapi_endpoint(self, app_client):
        response = await app_client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
```

---

### 二、前端测试框架

#### 2.1 安装依赖
```bash
pnpm --filter industry-monitor-frontend add -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

#### 2.2 Vitest 配置
**新建：** `frontend/vitest.config.ts`
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["../tests/frontend/setup.ts"],
    include: ["../tests/frontend/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/vite-env.d.ts", "src/main.tsx"],
    },
  },
});
```

#### 2.3 前端测试示例

**`tests/frontend/setup.ts`:**
```typescript
import "@testing-library/jest-dom/vitest";
```

**`tests/frontend/AuthGuard.test.tsx`:**
```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

// Mock auth module
vi.mock("../../frontend/src/services/auth", () => ({
  getToken: vi.fn(),
}));

import { getToken } from "../../frontend/src/services/auth";
import { AuthGuard } from "../../frontend/src/components/AuthGuard";

describe("AuthGuard", () => {
  it("redirects to login when no token", () => {
    (getToken as ReturnType<typeof vi.fn>).mockReturnValue(null);
    render(
      <MemoryRouter>
        <AuthGuard><div>Protected</div></AuthGuard>
      </MemoryRouter>
    );
    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
  });

  it("renders children when token exists", () => {
    (getToken as ReturnType<typeof vi.fn>).mockReturnValue("valid-token");
    render(
      <MemoryRouter>
        <AuthGuard><div>Protected</div></AuthGuard>
      </MemoryRouter>
    );
    expect(screen.getByText("Protected")).toBeInTheDocument();
  });
});
```

---

### 三、覆盖率目标

| 阶段 | 时间 | 后端覆盖率 | 前端覆盖率 | 重点 |
|------|------|-----------|-----------|------|
| 初始 | 第 1 周 | 30% | 20% | 认证、周期计算、Health Check |
| 中期 | 第 3 周 | 60% | 40% | 缓存、数据查询、Admin API |
| 成熟 | 第 6 周 | 80% | 60% | 调度器、边界情况、组件交互 |

---

### 四、CI 集成

> 注意：CI 流水线文件 `.github/workflows/ci.yml` 属于模块 1 管辖，  
> 本模块只需确保测试命令可用，CI 中的 `run: pytest` 和 `run: pnpm test` 由模块 1 配置。

本模块需要确保以下命令可在本地正常执行：
```bash
# 后端测试
pip install -r requirements-dev.txt
pytest --cov

# 前端测试
pnpm --filter industry-monitor-frontend test
```

---

## 检查清单

- [ ] `pytest` 能正常运行并通过
- [ ] `mongomock-motor` 和 `fakeredis` Mock 正常工作
- [ ] 认证 API 有正向 + 反向测试
- [ ] 周期计算函数有边界测试
- [ ] 缓存 set/get/clear 有测试覆盖
- [ ] Health Check 测试通过
- [ ] Vitest 前端测试能正常运行
- [ ] AuthGuard 组件有渲染测试
- [ ] 后端覆盖率 ≥ 30%
- [ ] 所有测试文件在 `tests/` 目录，未修改源码
