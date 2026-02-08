"""后台任务跟踪工具模块。

从 main.py 抽离，避免其他模块（如 panel_routes）反向导入 main 造成循环依赖。
"""
import asyncio

_bg_lock = asyncio.Lock()
_background_tasks: set[asyncio.Task] = set()


def _track_task(coro) -> asyncio.Task:
    """创建后台任务并跟踪，任务完成后自动移除引用。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def cancel_all_tracked_tasks(timeout: float = 5.0) -> int:
    """取消所有跟踪的后台任务，返回已取消数量。"""
    async with _bg_lock:
        tasks_snapshot = list(_background_tasks)
    if not tasks_snapshot:
        return 0
    for task in tasks_snapshot:
        task.cancel()
    await asyncio.wait(tasks_snapshot, timeout=timeout)
    return len(tasks_snapshot)


def get_tracked_tasks_count() -> int:
    """获取当前跟踪的后台任务数量。"""
    return len(_background_tasks)
