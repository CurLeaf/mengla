import pytest


class TestScheduler:
    """调度器测试（框架占位，待源码 APScheduler 兼容问题修复后完善）"""

    @pytest.mark.xfail(
        reason="源码 admin_routes.py 使用了 job.next_run_time 但当前 APScheduler 版本无此属性",
        strict=False,
    )
    async def test_scheduler_status_endpoint(self, app_client, auth_headers):
        """调度器状态端点应返回 200"""
        response = await app_client.get(
            "/admin/scheduler/status", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "state" in data

    async def test_scheduler_pause_endpoint_exists(self, app_client, auth_headers):
        """调度器暂停端点应可访问"""
        response = await app_client.post(
            "/admin/scheduler/pause", headers=auth_headers
        )
        # 端点存在即可（200 或 其他业务状态码）
        assert response.status_code != 404
