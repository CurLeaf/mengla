"""
JWT 认证模块
- 登录验证 → 签发 token
- 请求鉴权中间件
- Token 生成（管理后台用）
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("mengla-backend")

# ---------------------------------------------------------------------------
# 配置（通过环境变量）
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "mengla-default-secret-change-me")
JWT_ALGORITHM = "HS256"
# 登录 token 默认有效期（小时）
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# 管理员账号（环境变量配置）
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Bearer scheme
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token 工具
# ---------------------------------------------------------------------------
def create_token(
    subject: str,
    expires_hours: Optional[int] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """签发 JWT token"""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=expires_hours or JWT_EXPIRE_HOURS)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": exp,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证 JWT token，返回 payload；失败抛异常"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token 无效: {e}")


def create_api_token(
    label: str = "api",
    expires_hours: int = 24 * 365,
) -> str:
    """生成长期 API Token（管理后台用）"""
    return create_token(
        subject=f"api:{label}",
        expires_hours=expires_hours,
        extra_claims={"type": "api_token", "label": label},
    )


# ---------------------------------------------------------------------------
# FastAPI 依赖
# ---------------------------------------------------------------------------
async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    路由依赖：验证 Authorization: Bearer <token>
    返回 token payload（含 sub, iat, exp 等）
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证凭证")
    return verify_token(credentials.credentials)


def authenticate_user(username: str, password: str) -> bool:
    """简单用户名密码验证（环境变量配置）"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD
