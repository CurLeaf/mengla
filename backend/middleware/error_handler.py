"""
全局异常处理中间件

提供统一的错误响应格式：
{
    "success": false,
    "error": "ERROR_TYPE",
    "message": "人类可读的消息"
}
"""
import logging

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

logger = logging.getLogger("mengla-backend")


def register_error_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用"""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """请求参数校验失败"""
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "detail": str(exc),
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """业务值错误"""
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": str(exc),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """HTTP 异常：保留原状态码，结构化输出"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": "HTTP_ERROR",
                "message": exc.detail or "HTTP error",
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        """未捕获异常：500 + 结构化 JSON（隐藏堆栈）"""
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": "Internal server error",
            },
        )
