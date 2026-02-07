import pytest

from backend.infra.cache import L1Cache


class TestL1Cache:
    """L1 本地缓存单元测试（纯内存，无外部依赖）"""

    @pytest.fixture
    def cache(self):
        """创建一个干净的 L1Cache 实例"""
        return L1Cache(max_size=100, ttl=300)

    async def test_set_and_get(self, cache):
        """设置缓存后应能读取到相同数据"""
        await cache.set("high", "cat001", "day", "20250115", {"value": 42})
        result = await cache.get("high", "cat001", "day", "20250115")
        assert result == {"value": 42}

    async def test_cache_miss(self, cache):
        """未设置的 key 应返回 None"""
        result = await cache.get("high", "cat001", "day", "nonexistent")
        assert result is None

    async def test_different_keys_isolated(self, cache):
        """不同 key 的缓存应互不影响"""
        await cache.set("high", "cat001", "day", "20250115", "data_a")
        await cache.set("hot", "cat002", "month", "202501", "data_b")

        result_a = await cache.get("high", "cat001", "day", "20250115")
        result_b = await cache.get("hot", "cat002", "month", "202501")
        assert result_a == "data_a"
        assert result_b == "data_b"

    async def test_overwrite(self, cache):
        """重复设置同一 key 应覆盖旧值"""
        await cache.set("high", "cat001", "day", "20250115", "old")
        await cache.set("high", "cat001", "day", "20250115", "new")
        result = await cache.get("high", "cat001", "day", "20250115")
        assert result == "new"

    async def test_delete(self, cache):
        """删除后应读取不到数据"""
        await cache.set("high", "cat001", "day", "20250115", "data")
        await cache.delete("high", "cat001", "day", "20250115")
        result = await cache.get("high", "cat001", "day", "20250115")
        assert result is None

    async def test_clear(self, cache):
        """清空缓存后所有 key 都应无法读取"""
        await cache.set("high", "cat001", "day", "20250115", "data1")
        await cache.set("hot", "cat002", "month", "202501", "data2")
        await cache.clear()

        result1 = await cache.get("high", "cat001", "day", "20250115")
        result2 = await cache.get("hot", "cat002", "month", "202501")
        assert result1 is None
        assert result2 is None

    async def test_stats_hit_and_miss(self, cache):
        """统计信息应正确反映命中和未命中次数"""
        await cache.set("high", "cat001", "day", "20250115", "data")

        # 1 次命中
        await cache.get("high", "cat001", "day", "20250115")
        # 1 次未命中
        await cache.get("high", "cat001", "day", "nonexistent")

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1
