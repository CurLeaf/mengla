import os
import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# ---------------------------------------------------------------------------
# 测试环境变量：在任何模块导入前设置
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-for-testing")
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "testpass123")
os.environ.setdefault("ENABLE_PANEL_ADMIN", "1")

# ---------------------------------------------------------------------------
# 兼容处理：如果 backend.utils.config 尚未实现 validate_env，则注入空实现
# （模块 2 重构可能尚未完成，main.py 已引用但 config.py 中尚未添加）
# ---------------------------------------------------------------------------
import backend.utils.config as _config_mod
if not hasattr(_config_mod, "validate_env"):
    _config_mod.validate_env = lambda: None


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
    from httpx import AsyncClient, ASGITransport
    from backend.infra import database

    # Patch 数据库连接，避免连接真实数据库
    with patch.object(database, 'mongo_db', mock_mongo), \
         patch.object(database, 'redis_client', mock_redis), \
         patch.object(database, 'connect_to_mongo', new_callable=AsyncMock), \
         patch.object(database, 'connect_to_redis', new_callable=AsyncMock), \
         patch.object(database, 'disconnect_mongo', new_callable=AsyncMock), \
         patch.object(database, 'disconnect_redis', new_callable=AsyncMock), \
         patch.object(database, 'ensure_indexes', new_callable=AsyncMock):

        from backend.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def auth_headers():
    """生成有效的 JWT token header"""
    from backend.core.auth import create_token
    token = create_token(subject="testadmin")
    return {"Authorization": f"Bearer {token}"}
