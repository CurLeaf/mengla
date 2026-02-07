import pytest


class TestMenglaQuery:
    """数据查询单元测试（框架占位，待模块 2 完成后补充）"""

    async def test_query_endpoint_requires_auth(self, app_client):
        """查询接口应要求认证"""
        response = await app_client.post("/api/mengla/query", json={
            "action": "high",
            "catId": "",
            "dateType": "day",
            "timest": "20250115",
        })
        # 未认证应返回 401
        assert response.status_code == 401
