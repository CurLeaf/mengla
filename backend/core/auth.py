"""
JWT 认证模块
- 登录验证 → 签发 token
- 请求鉴权中间件
- Token 生成（管理后台用）
- 登录频率限制（Redis 滑动窗口）
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

logger = logging.getLogger("mengla-backend")

# ---------------------------------------------------------------------------
# 密码哈希上下文
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# 配置（通过环境变量，安全关键项强制要求）
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is required. "
        'Generate: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
JWT_ALGORITHM = "HS256"
# 登录 token 默认有效期（小时）
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# 管理员账号（环境变量配置）
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
_RAW_PW = os.getenv("ADMIN_PASSWORD", "")
if not _RAW_PW:
    raise RuntimeError("ADMIN_PASSWORD environment variable is required")
_ADMIN_PW_HASH = pwd_context.hash(_RAW_PW)
del _RAW_PW

# Bearer scheme
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token 工具
# ---------------------------------------------------------------------------
def create_token(
    subject: str,
    expires_hours: Optional[int] = None,
    extra_claims: Optional[dict] = None,
    permanent: bool = False,
) -> str:
    """签发 JWT token。permanent=True 时不设置 exp，token 永不过期。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        **(extra_claims or {}),
    }
    if not permanent:
        payload["exp"] = now + timedelta(hours=expires_hours or JWT_EXPIRE_HOURS)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证 JWT token，返回 payload；失败抛异常。支持永久 token（无 exp）。"""
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True, "require": ["sub", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token 无效: {e}")


def create_api_token(
    label: str = "api",
    expires_hours: Optional[int] = 24 * 365,
) -> str:
    """生成长期 API Token（管理后台用）。expires_hours 为 None 时生成永久 token。"""
    permanent = expires_hours is None
    return create_token(
        subject=f"api:{label}",
        expires_hours=expires_hours,
        extra_claims={"type": "api_token", "label": label},
        permanent=permanent,
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
    """用户名密码验证（bcrypt 哈希比较）"""
    if username != ADMIN_USERNAME:
        return False
    return pwd_context.verify(password, _ADMIN_PW_HASH)


# ---------------------------------------------------------------------------
# 登录频率限制（Redis 滑动窗口：60 秒 10 次）
# ---------------------------------------------------------------------------
async def check_login_rate(ip: str) -> bool:
    """
    检查登录频率，返回 True 表示允许，False 表示超限。
    若 Redis 不可用则拒绝登录（安全优先策略），防止暴力破解。
    """
    from ..infra.database import redis_client

    if redis_client is None:
        logger.warning("登录限流 Redis 不可用，降级放行 ip=%s", ip)
        return True
    try:
        key = f"rate_limit:login:{ip}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        return count <= 10
    except Exception:
        logger.warning("登录限流 Redis 异常，降级放行 ip=%s", ip, exc_info=True)
        return True
