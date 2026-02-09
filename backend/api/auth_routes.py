"""认证相关路由：登录、生成 Token、验证身份"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..core.auth import (
    authenticate_user,
    check_login_rate,
    create_api_token,
    create_token,
    require_auth,
)

logger = logging.getLogger("mengla-backend")

router = APIRouter(tags=["Auth"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

    def __init__(self, **data):
        super().__init__(**data)
        if not self.username or len(self.username.strip()) < 2:
            raise ValueError("用户名至少需要 2 个字符")
        if len(self.username) > 50:
            raise ValueError("用户名不能超过 50 个字符")
        if not self.password or len(self.password) < 4:
            raise ValueError("密码至少需要 4 个字符")


class GenerateTokenRequest(BaseModel):
    label: str = "api"
    expires_hours: int | None = 24 * 365  # 默认 1 年，None 表示永久

    def __init__(self, **data):
        super().__init__(**data)
        if not self.label or len(self.label.strip()) < 2:
            raise ValueError("标签至少需要 2 个字符")
        if len(self.label) > 50:
            raise ValueError("标签不能超过 50 个字符")
        if self.expires_hours is not None:
            if self.expires_hours < 1:
                raise ValueError("有效期不能小于 1 小时")
            if self.expires_hours > 87600 * 10:  # 最多约 100 年
                raise ValueError("有效期不能超过 876000 小时")


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """登录接口：验证用户名密码，返回 JWT token"""
    client_ip = request.client.host if request.client else "unknown"

    # 频率限制（Redis 不可用时也会拒绝，详见 check_login_rate）
    if not await check_login_rate(client_ip):
        logger.warning("LOGIN_RATE_LIMITED user=%s ip=%s", body.username, client_ip)
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请 1 分钟后再试")

    if not authenticate_user(body.username, body.password):
        logger.warning("LOGIN_FAILED user=%s ip=%s", body.username, client_ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(subject=body.username.strip())
    logger.info("LOGIN_SUCCESS user=%s ip=%s", body.username, client_ip)
    return {"ok": True, "token": token, "username": body.username.strip()}


@router.post("/generate-token", dependencies=[Depends(require_auth)])
async def generate_api_token_endpoint(body: GenerateTokenRequest):
    """生成长期 API Token（需要先登录）"""
    token = create_api_token(label=body.label.strip(), expires_hours=body.expires_hours)
    return {"ok": True, "token": token, "label": body.label.strip(), "expires_hours": body.expires_hours}


@router.get("/me", dependencies=[Depends(require_auth)])
async def auth_me(payload: dict = Depends(require_auth)):
    """验证当前 token 是否有效，返回用户信息"""
    return {"ok": True, "username": payload.get("sub"), "payload": payload}
