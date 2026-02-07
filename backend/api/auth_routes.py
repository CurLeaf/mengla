"""认证相关路由：登录、生成 Token、验证身份"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import (
    authenticate_user,
    create_api_token,
    create_token,
    require_auth,
)

router = APIRouter(tags=["Auth"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class GenerateTokenRequest(BaseModel):
    label: str = "api"
    expires_hours: int | None = 24 * 365  # 默认 1 年，None 表示永久


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.post("/login")
async def login(body: LoginRequest):
    """登录接口：验证用户名密码，返回 JWT token"""
    if not authenticate_user(body.username, body.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(subject=body.username)
    return {"token": token, "username": body.username}


@router.post("/generate-token", dependencies=[Depends(require_auth)])
async def generate_api_token_endpoint(body: GenerateTokenRequest):
    """生成长期 API Token（需要先登录）"""
    token = create_api_token(label=body.label, expires_hours=body.expires_hours)
    return {"token": token, "label": body.label, "expires_hours": body.expires_hours}


@router.get("/me", dependencies=[Depends(require_auth)])
async def auth_me(payload: dict = Depends(require_auth)):
    """验证当前 token 是否有效，返回用户信息"""
    return {"username": payload.get("sub"), "payload": payload}
