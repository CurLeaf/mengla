"""路由共享依赖项"""
import os

from fastapi import HTTPException


def _panel_admin_enabled() -> bool:
    v = os.getenv("ENABLE_PANEL_ADMIN", "").strip().lower()
    if v:
        return v in ("1", "true", "yes")
    # 非 production 环境下默认开启管理中心，便于本地开发
    env = os.getenv("ENV", "").strip().lower()
    return env != "production"


async def require_panel_admin() -> None:
    """Dependency: raise 403 if panel admin APIs are disabled (non-dev)."""
    if not _panel_admin_enabled():
        raise HTTPException(
            status_code=403,
            detail="Panel admin is disabled. Set ENABLE_PANEL_ADMIN=1 to enable.",
        )
