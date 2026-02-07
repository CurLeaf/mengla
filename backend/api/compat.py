"""临时兼容旧路径 — 307 重定向到新 /api/* 前缀

步骤 3 前端更新完毕并验证无误后，可删除此文件并移除 main.py 中的注册。
"""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

compat_router = APIRouter(tags=["兼容-即将废弃"])


@compat_router.api_route(
    "/panel/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    include_in_schema=False,
)
async def panel_compat(path: str, request: Request):
    """将旧 /panel/* 请求 307 重定向到 /api/panel/*"""
    query = str(request.query_params)
    url = f"/api/panel/{path}"
    if query:
        url = f"{url}?{query}"
    return RedirectResponse(url=url, status_code=307)


@compat_router.api_route(
    "/admin/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    include_in_schema=False,
)
async def admin_compat(path: str, request: Request):
    """将旧 /admin/* 请求 307 重定向到 /api/admin/*"""
    query = str(request.query_params)
    url = f"/api/admin/{path}"
    if query:
        url = f"{url}?{query}"
    return RedirectResponse(url=url, status_code=307)
