import pytest


class TestAuthAPI:
    """认证 API 测试：登录、Token 鉴权"""

    async def test_login_success(self, app_client):
        """正确的用户名密码应返回 200 和 token"""
        response = await app_client.post("/api/auth/login", json={
            "username": "testadmin",
            "password": "testpass123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["username"] == "testadmin"

    async def test_login_wrong_password(self, app_client):
        """错误密码应返回 401"""
        response = await app_client.post("/api/auth/login", json={
            "username": "testadmin",
            "password": "wrong"
        })
        assert response.status_code == 401

    async def test_login_wrong_username(self, app_client):
        """错误用户名应返回 401"""
        response = await app_client.post("/api/auth/login", json={
            "username": "wronguser",
            "password": "testpass123"
        })
        assert response.status_code == 401

    async def test_protected_route_without_token(self, app_client):
        """未携带 token 访问受保护路由应返回 401"""
        response = await app_client.get("/api/auth/me")
        assert response.status_code == 401

    async def test_protected_route_with_token(self, app_client, auth_headers):
        """携带有效 token 访问受保护路由应返回 200"""
        response = await app_client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testadmin"

    async def test_protected_route_with_invalid_token(self, app_client):
        """携带无效 token 应返回 401"""
        headers = {"Authorization": "Bearer invalid-token-string"}
        response = await app_client.get("/api/auth/me", headers=headers)
        assert response.status_code == 401
