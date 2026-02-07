import pytest


class TestCategoriesAPI:
    """分类 API 测试（框架占位，待模块 2 完成后补充）"""

    async def test_categories_returns_list(self, app_client, auth_headers):
        """分类接口应返回列表"""
        response = await app_client.get("/api/categories", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_categories_requires_auth(self, app_client):
        """分类接口应要求认证"""
        response = await app_client.get("/api/categories")
        assert response.status_code == 401
