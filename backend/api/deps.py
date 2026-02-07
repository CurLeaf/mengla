"""路由共享依赖项"""
import os
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.auth import verify_token

_bearer_scheme = HTTPBearer(auto_error=False)


def _panel_admin_enabled() -> bool:
    v = os.getenv("ENABLE_PANEL_ADMIN", "").strip().lower()
    if v:
        return v in ("1", "true", "yes")
    # 非 production 环境下默认开启管理中心，便于本地开发
    env = os.getenv("ENV", "").strip().lower()
    return env != "production"


async def require_panel_admin() -> None:
    """Dependency: raise 403 if panel admin APIs are disabled (non-dev).
    已废弃，请使用 require_admin。"""
    if not _panel_admin_enabled():
        raise HTTPException(
            status_code=403,
            detail="Panel admin is disabled. Set ENABLE_PANEL_ADMIN=1 to enable.",
        )


async def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    管理员认证 = JWT 验证 + 面板开关检查。
    同时解决两个问题：
    1. 当前 require_panel_admin 不验证 JWT
    2. 生产环境需要显式启用面板
    """
    # 1. 检查面板开关
    if not _panel_admin_enabled():
        raise HTTPException(
            status_code=403,
            detail="Panel admin is disabled. Set ENABLE_PANEL_ADMIN=1 to enable.",
        )
    # 2. 验证 JWT token
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证凭证")
    return verify_token(credentials.credentials)
