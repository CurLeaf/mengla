"""
路由模块汇总

通过 include_router 注册到 FastAPI 应用。
"""
from . import (
    auth_routes,
    category_routes,
    mengla_routes,
    webhook_routes,
    panel_routes,
    admin_routes,
    sync_task_routes,
)

__all__ = [
    "auth_routes",
    "category_routes",
    "mengla_routes",
    "webhook_routes",
    "panel_routes",
    "admin_routes",
    "sync_task_routes",
]
