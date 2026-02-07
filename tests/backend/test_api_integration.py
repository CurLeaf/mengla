import pytest


class TestMenglaAPI:
    """API 集成测试：Health Check、Categories、OpenAPI"""

    async def test_health_check(self, app_client):
        """健康检查端点应返回 200"""
        response = await app_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_root_endpoint(self, app_client):
        """根端点应返回运行信息"""
        response = await app_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_openapi_endpoint(self, app_client):
        """OpenAPI schema 端点应返回有效的 OpenAPI 文档"""
        response = await app_client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
        assert data["info"]["title"] == "Industry Monitor API"

    async def test_get_categories_with_auth(self, app_client, auth_headers):
        """携带 token 请求分类列表应返回 200"""
        response = await app_client.get("/api/categories", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_categories_without_auth(self, app_client):
        """未携带 token 请求分类列表应返回 401"""
        response = await app_client.get("/api/categories")
        assert response.status_code == 401
