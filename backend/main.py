"""
MengLa Data Collector — FastAPI 入口

职责：
- 创建 FastAPI 应用
- 注册 CORS（从环境变量读取 origins）
- 挂载路由模块
- 注册全局异常处理
- 管理生命周期事件（startup / shutdown）
- 后台任务跟踪
"""
import asyncio
import logging
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 环境变量加载（最早执行，其他模块可能依赖环境变量）
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_env_path)
    except ImportError:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
for _name in ("mengla-backend", "mengla-domain", "backend.mengla_client"):
    logging.getLogger(_name).setLevel(logging.INFO)

logger = logging.getLogger("mengla-backend")

# ---------------------------------------------------------------------------
# 内部模块导入
# ---------------------------------------------------------------------------
from .api import (
    auth_routes,
    category_routes,
    mengla_routes,
    webhook_routes,
    panel_routes,
    admin_routes,
    sync_task_routes,
)
from .api.compat import compat_router
from .middleware.error_handler import register_error_handlers
from .infra.database import init_db_events
from .infra.alerting import init_default_notifiers
from .scheduler import init_scheduler
from .utils.config import validate_env

# ---------------------------------------------------------------------------
# 启动时校验环境变量
# ---------------------------------------------------------------------------
validate_env()

# ---------------------------------------------------------------------------
# 创建 FastAPI 应用
# ---------------------------------------------------------------------------
app = FastAPI(title="Industry Monitor API", version="0.2.0")

# ---------------------------------------------------------------------------
# CORS — origins 从环境变量读取，默认仅允许本地开发地址
# ---------------------------------------------------------------------------
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 注册路由模块 — 统一 /api 前缀
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_routes.router,      prefix="/auth",        tags=["认证"])
api_router.include_router(mengla_routes.router,     prefix="/data/mengla", tags=["MengLa 数据"])
api_router.include_router(category_routes.router,   prefix="/data",        tags=["类目数据"])
api_router.include_router(webhook_routes.router,    prefix="/webhook",     tags=["Webhook"])
api_router.include_router(panel_routes.router,      prefix="/panel",       tags=["面板配置"])
api_router.include_router(admin_routes.router,      prefix="/admin",       tags=["管理运维"])
api_router.include_router(sync_task_routes.router,  prefix="/sync-tasks",  tags=["同步任务"])
app.include_router(api_router)

# 旧路径兼容重定向（/panel/*, /admin/* → /api/panel/*, /api/admin/*）
app.include_router(compat_router)

# ---------------------------------------------------------------------------
# 注册全局异常处理
# ---------------------------------------------------------------------------
register_error_handlers(app)

# ---------------------------------------------------------------------------
# 数据库生命周期事件
# ---------------------------------------------------------------------------
init_db_events(app)

# ---------------------------------------------------------------------------
# 调度器
# ---------------------------------------------------------------------------
scheduler = init_scheduler()

# ---------------------------------------------------------------------------
# 后台任务跟踪（加锁保护）
# ---------------------------------------------------------------------------
_bg_lock = asyncio.Lock()
_background_tasks: set[asyncio.Task] = set()


def _track_task(coro) -> asyncio.Task:
    """创建后台任务并跟踪，任务完成后自动移除引用。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# ---------------------------------------------------------------------------
# 根路由 & 健康检查
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "Industry Monitor API running"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 生命周期事件
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _start_scheduler() -> None:
    scheduler.start()


@app.on_event("startup")
async def _init_alerting() -> None:
    """初始化告警系统"""
    init_default_notifiers()


@app.on_event("shutdown")
async def _shutdown() -> None:
    # 1. 停止 scheduler
    try:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown completed")
    except Exception as exc:
        logger.warning("Scheduler shutdown error: %s", exc)

    # 2. 取消所有跟踪的后台任务
    async with _bg_lock:
        tasks_snapshot = list(_background_tasks)
    if tasks_snapshot:
        logger.info("Cancelling %d background tasks", len(tasks_snapshot))
        for task in tasks_snapshot:
            task.cancel()
        done, pending = await asyncio.wait(tasks_snapshot, timeout=5.0)
        if pending:
            logger.warning("%d background tasks did not finish in time", len(pending))
