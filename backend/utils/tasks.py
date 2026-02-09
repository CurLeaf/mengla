"""后台任务跟踪工具模块。

从 main.py 抽离，避免其他模块（如 panel_routes）反向导入 main 造成循环依赖。

注意：asyncio 是单线程协作式调度，set 的 add/discard 操作不会被中途打断，
因此 _track_task（同步函数）中的 add 和 done_callback 中的 discard 是安全的。
Lock 仅用于保护 cancel_all_tracked_tasks 中的快照 + 批量取消流程。
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
    cancelled = 0
    for task in tasks_snapshot:
        if not task.done():
            task.cancel()
            cancelled += 1
    if tasks_snapshot:
        await asyncio.wait(tasks_snapshot, timeout=timeout)
    return cancelled


def get_tracked_tasks_count() -> int:
    """获取当前跟踪的后台任务数量。"""
    return len(_background_tasks)
