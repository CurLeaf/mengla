from pydantic import BaseModel
from typing import Any, Optional


class ApiResponse(BaseModel):
    """统一成功响应格式"""
    success: bool = True
    data: Any = None
    message: str = "ok"


class ApiError(BaseModel):
    """统一错误响应格式"""
    success: bool = False
    error: str
    message: str
    detail: Optional[str] = None
