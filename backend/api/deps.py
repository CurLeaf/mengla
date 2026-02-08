"""路由共享依赖项"""
import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.auth import verify_token

logger = logging.getLogger("mengla-backend")

_bearer_scheme = HTTPBearer(auto_error=False)


def _panel_admin_enabled() -> bool:
    v = os.getenv("ENABLE_PANEL_ADMIN", "").strip().lower()
    if v:
        return v in ("1", "true", "yes")
    # 非 production 环境下默认开启管理中心，便于本地开发
    env = os.getenv("ENV", "").strip().lower()
    return env != "production"


async def require_webhook_signature(request: Request) -> None:
    """
    Webhook 签名校验依赖（HMAC-SHA256）。
    请求方需在 Header 中携带 X-Signature-256，值为 sha256=<hex_digest>。
    密钥从环境变量 WEBHOOK_SECRET 读取；若未配置则跳过校验（开发模式）。
    """
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if not secret:
        logger.warning("WEBHOOK_SECRET not set, skipping webhook signature verification")
        return

    signature_header = request.headers.get("X-Signature-256", "")
    if not signature_header:
        raise HTTPException(status_code=403, detail="Missing X-Signature-256 header")

    body = await request.body()
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


async def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    管理员认证 = JWT 验证 + 面板开关检查。
    1. 验证面板管理开关是否启用
    2. 验证 JWT token 有效性
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
