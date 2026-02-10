"""
统一补录模块

包含两种补录方式：
1. 简单补录（single）：直接串行执行，支持断点续传
2. 队列补录（queue）：使用 MongoDB 队列，支持多 worker

运行方法：
  # 简单补录
  python -m backend.backfill single --days 30
  python -m backend.backfill single --start 2024-01-01 --end 2024-12-31

  # 队列补录
  python -m backend.backfill queue create --years 1
  python -m backend.backfill queue worker --workers 3
  python -m backend.backfill queue status
  python -m backend.backfill queue cancel <job_id>
"""
import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.infra import database
from backend.utils.category import get_top_level_cat_ids
from backend.core.domain import query_mengla
from backend.utils.period import period_keys_in_range, period_to_date_range
from backend.core.queue import (
    CRAWL_JOBS,
    CRAWL_SUBTASKS,
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    SUB_FAILED,
    SUB_PENDING,
    SUB_RUNNING,
    SUB_SUCCESS,
    create_crawl_job,
    finish_job_if_done,
    get_next_job,
    get_pending_subtasks,
    inc_job_stats,
    set_job_running,
    set_subtask_failed,
    set_subtask_running,
    set_subtask_success,
)


# ==============================================================================
# 进度管理（简单补录用）
# ==============================================================================
PROGRESS_FILE = Path(__file__).parent / "backfill_progress.json"


def load_progress():
    """加载进度"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed": [], "failed": [], "last_update": None}


def save_progress(progress):
    """保存进度"""
    progress["last_update"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def is_completed(progress, task_key):
    """检查任务是否已完成"""
    return task_key in progress.get("completed", [])


def mark_completed(progress, task_key):
    """标记任务完成"""
    if task_key not in progress.get("completed", []):
        progress["completed"].append(task_key)


def mark_failed(progress, task_key, error):
    """标记任务失败"""
    progress.setdefault("failed", []).append({"task": task_key, "error": str(error)})


# ==============================================================================
# 简单补录（串行执行，支持断点续传）
# ==============================================================================
async def backfill_data(
    start_date: str,
    end_date: str,
    actions: list[str],
    granularities: list[str],
    cat_ids: list[str],
    resume: bool = True,
    sleep_min: float = 1.0,
    sleep_max: float = 3.0,
):
    """
    补录历史数据（API 调用接口）
    
    Args:
        start_date: 起始日期 yyyy-MM-dd
        end_date: 结束日期 yyyy-MM-dd
        actions: 接口列表，如 ["high", "hot"]
        granularities: 颗粒度列表，如 ["day", "month"]
        cat_ids: 类目ID列表
        resume: 是否断点续传
        sleep_min: 最小休眠时间（秒）
        sleep_max: 最大休眠时间（秒）
    """
    print("=" * 80)
    print("历史数据补录")
    print("=" * 80)
    
    # 1. 连接数据库
    print("\n[1/4] 连接数据库...")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    redis_uri = os.getenv("REDIS_URI", "redis://localhost:6379/0")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    await database.connect_to_redis(redis_uri)
    print("✓ 数据库连接成功")
    
    # 2. 加载进度
    progress = load_progress() if resume else {"completed": [], "failed": []}
    if resume and progress.get("completed"):
        print(f"\n✓ 加载进度: 已完成 {len(progress['completed'])} 个任务")
    
    # 3. 计算任务
    print("\n[2/4] 计算任务...")
    print(f"  时间范围: {start_date} ~ {end_date}")
    print(f"  接口: {', '.join(actions)}")
    print(f"  颗粒度: {', '.join(granularities)}")
    print(f"  类目数: {len(cat_ids)}")
    
    # 计算各颗粒度的 period_key
    period_keys_map = {}
    for gran in granularities:
        keys = period_keys_in_range(gran, start_date, end_date)
        period_keys_map[gran] = keys
        print(f"  {gran}: {len(keys)} 个时间点")
    
    # 4. 执行采集
    print("\n[3/4] 开始采集...")
    print("=" * 80)
    
    completed = 0
    failed = 0
    skipped = 0
    
    try:
        for cat_id in cat_ids:
            print(f"\n类目: {cat_id}")
            
            for action in actions:
                print(f"  接口: {action}")
                
                if action == "industryTrendRange":
                    # 趋势接口：按年范围查询
                    year_keys = period_keys_map.get("year", [])
                    for year in year_keys:
                        start_year = f"{year}-01-01"
                        end_year = f"{year}-12-31"
                        
                        for gran in granularities:
                            task_key = f"{cat_id}|{action}|{gran}|{year}"
                            
                            if is_completed(progress, task_key):
                                skipped += 1
                                continue
                            
                            date_type = {
                                "day": "DAY",
                                "month": "MONTH",
                                "quarter": "QUARTERLY_FOR_YEAR",
                                "year": "YEAR",
                            }.get(gran, "DAY")
                            
                            try:
                                await query_mengla(
                                    action=action,
                                    product_id="",
                                    catId=cat_id,
                                    dateType=date_type,
                                    timest="",
                                    starRange=start_year,
                                    endRange=end_year,
                                    extra=None,
                                )
                                completed += 1
                                mark_completed(progress, task_key)
                                
                                if completed % 10 == 0:
                                    save_progress(progress)
                                    print(f"    进度: 完成 {completed}, 失败 {failed}, 跳过 {skipped}")
                                
                                await asyncio.sleep(random.uniform(sleep_min, sleep_max))
                            except Exception as e:
                                failed += 1
                                mark_failed(progress, task_key, str(e))
                                print(f"    ✗ 失败: {task_key} - {e}")
                else:
                    # 非趋势接口：按时间点逐个采集
                    for gran in granularities:
                        period_keys = period_keys_map.get(gran, [])
                        print(f"    {gran}: {len(period_keys)} 个时间点")
                        
                        for i, period_key in enumerate(period_keys):
                            task_key = f"{cat_id}|{action}|{gran}|{period_key}"
                            
                            if is_completed(progress, task_key):
                                skipped += 1
                                continue
                            
                            try:
                                await query_mengla(
                                    action=action,
                                    product_id="",
                                    catId=cat_id,
                                    dateType=gran,
                                    timest=period_key,
                                    starRange="",
                                    endRange="",
                                    extra=None,
                                )
                                completed += 1
                                mark_completed(progress, task_key)
                                
                                if completed % 50 == 0:
                                    save_progress(progress)
                                    print(f"      进度: {i + 1}/{len(period_keys)}, 完成 {completed}, 失败 {failed}, 跳过 {skipped}")
                                
                                await asyncio.sleep(random.uniform(sleep_min, sleep_max))
                            except Exception as e:
                                failed += 1
                                mark_failed(progress, task_key, str(e))
        
        print("\n✓ 采集完成")
        
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断，保存进度...")
        save_progress(progress)
    except Exception as e:
        print(f"\n\n✗ 采集出错: {e}")
        import traceback
        traceback.print_exc()
        save_progress(progress)
    
    # 5. 保存最终进度
    save_progress(progress)
    
    # 6. 关闭连接
    print("\n[4/4] 关闭连接...")
    await database.disconnect_redis()
    await database.disconnect_mongo()
    print("✓ 已关闭连接")
    
    # 7. 统计
    print("\n" + "=" * 80)
    print("采集统计")
    print("=" * 80)
    print(f"  成功: {completed:,}")
    print(f"  失败: {failed:,}")
    print(f"  跳过: {skipped:,}")
    print(f"  总计: {completed + failed + skipped:,}")
    print(f"  进度文件: {PROGRESS_FILE}")
    print("=" * 80)


# ==============================================================================
# 队列补录（多 worker 并发）
# ==============================================================================
REQUEST_LOCK = asyncio.Lock()


async def queue_create(
    start_date: str,
    end_date: str,
    actions: list[str],
    granularities: list[str],
):
    """为所有一级类目创建队列任务"""
    print("=" * 80)
    print("创建队列任务")
    print("=" * 80)
    
    # 连接数据库
    print("\n[1/3] 连接数据库...")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    print("✓ 数据库连接成功")
    
    # 获取类目
    print("\n[2/3] 加载类目...")
    try:
        cat_ids = get_top_level_cat_ids()
        print(f"✓ 成功加载 {len(cat_ids)} 个一级类目")
    except Exception as e:
        print(f"✗ 加载类目失败: {e}")
        cat_ids = [""]
    
    # 创建任务
    print("\n[3/3] 创建队列任务...")
    print(f"  时间范围: {start_date} ~ {end_date}")
    print(f"  接口: {', '.join(actions)}")
    print(f"  颗粒度: {', '.join(granularities)}")
    print(f"  类目数: {len(cat_ids)}")
    
    job_ids = []
    for i, cat_id in enumerate(cat_ids, 1):
        try:
            job_id = await create_crawl_job(
                start_date=start_date,
                end_date=end_date,
                granularities=granularities,
                actions=actions,
                cat_id=cat_id,
                extra=None,
            )
            job_ids.append(job_id)
            print(f"  [{i}/{len(cat_ids)}] 创建任务: 类目 {cat_id}, Job ID: {job_id}")
        except Exception as e:
            print(f"  [{i}/{len(cat_ids)}] ✗ 创建失败: 类目 {cat_id}, 错误: {e}")
    
    await database.disconnect_mongo()
    
    print("\n" + "=" * 80)
    print(f"✓ 成功创建 {len(job_ids)} 个队列任务")
    print("\n启动worker来处理任务：")
    print("  python -m backend.backfill queue worker --workers 5")
    print("\n查看任务状态：")
    print("  python -m backend.backfill queue status")
    print("=" * 80)


async def _run_worker(
    worker_id: int,
    sleep_min: float = 1.0,
    sleep_max: float = 3.0,
    max_retries: int = 3,
):
    """单个worker"""
    print(f"[Worker {worker_id}] 启动")
    
    processed = 0
    failed = 0
    
    while True:
        try:
            job = await get_next_job()
            if not job:
                print(f"[Worker {worker_id}] 没有待处理任务，等待...")
                await asyncio.sleep(10)
                continue
            
            job_id = job["_id"]
            
            if job["status"] == JOB_PENDING:
                await set_job_running(job_id)
            
            config = job.get("config") or {}
            cat_id = config.get("catId", "") or ""
            extra = config.get("extra") or {}
            
            subtasks = await get_pending_subtasks(job_id, limit=10)
            
            if not subtasks:
                await finish_job_if_done(job_id)
                continue
            
            for sub in subtasks:
                sub_id = sub["_id"]
                action = sub.get("action", "")
                gran = sub.get("granularity", "day")
                period_key = sub.get("period_key", "")
                attempts = sub.get("attempts", 0)
                
                if attempts >= max_retries:
                    await set_subtask_failed(sub_id, f"超过最大重试次数 {max_retries}")
                    await inc_job_stats(job_id, completed_delta=0, failed_delta=1)
                    failed += 1
                    continue
                
                await set_subtask_running(sub_id)
                
                try:
                    async with REQUEST_LOCK:
                        if action == "industryTrendRange":
                            start_range, end_range = period_to_date_range(gran, period_key)
                            date_type = {
                                "day": "DAY",
                                "month": "MONTH",
                                "quarter": "QUARTERLY_FOR_YEAR",
                                "year": "YEAR",
                            }.get(gran, "DAY")
                            
                            await query_mengla(
                                action=action,
                                product_id="",
                                catId=cat_id,
                                dateType=date_type,
                                timest="",
                                starRange=start_range,
                                endRange=end_range,
                                extra=extra,
                            )
                        else:
                            await query_mengla(
                                action=action,
                                product_id="",
                                catId=cat_id,
                                dateType=gran,
                                timest=period_key,
                                starRange="",
                                endRange="",
                                extra=extra,
                            )
                        
                        await asyncio.sleep(random.uniform(sleep_min, sleep_max))
                    
                    await set_subtask_success(sub_id)
                    await inc_job_stats(job_id, completed_delta=1, failed_delta=0)
                    processed += 1
                    
                    if processed % 10 == 0:
                        print(f"[Worker {worker_id}] 已处理 {processed} 个，失败 {failed} 个")
                    
                except Exception as e:
                    await set_subtask_failed(sub_id, str(e))
                    await inc_job_stats(job_id, completed_delta=0, failed_delta=1)
                    failed += 1
                    print(f"[Worker {worker_id}] ✗ {action}/{gran}/{period_key} - {e}")
            
            await finish_job_if_done(job_id)
            
        except KeyboardInterrupt:
            print(f"\n[Worker {worker_id}] 收到中断信号，退出...")
            break
        except Exception as e:
            print(f"[Worker {worker_id}] ✗ 处理出错: {e}")
            await asyncio.sleep(5)


async def queue_worker(num_workers: int, sleep_min: float, sleep_max: float):
    """启动多个worker"""
    print("=" * 80)
    print(f"启动 {num_workers} 个Worker")
    print("=" * 80)
    
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    redis_uri = os.getenv("REDIS_URI", "redis://localhost:6379/0")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    await database.connect_to_redis(redis_uri)
    print("✓ 数据库连接成功")
    
    print(f"\n启动 {num_workers} 个worker...")
    print("按 Ctrl+C 停止\n")
    
    workers = [
        asyncio.create_task(_run_worker(i + 1, sleep_min, sleep_max))
        for i in range(num_workers)
    ]
    
    try:
        await asyncio.gather(*workers)
    except KeyboardInterrupt:
        print("\n\n收到中断信号，停止所有worker...")
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        await database.disconnect_redis()
        await database.disconnect_mongo()
        print("\n✓ 已关闭连接")


async def queue_status():
    """显示队列状态"""
    print("=" * 80)
    print("队列状态")
    print("=" * 80)
    
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    
    if database.mongo_db is None:
        print("✗ 数据库未连接")
        return
    
    jobs_coll = database.mongo_db[CRAWL_JOBS]
    subtasks_coll = database.mongo_db[CRAWL_SUBTASKS]
    
    print("\n任务统计：")
    for status in [JOB_PENDING, JOB_RUNNING, JOB_COMPLETED, JOB_FAILED, JOB_CANCELLED]:
        count = await jobs_coll.count_documents({"status": status})
        print(f"  {status}: {count}")
    
    print("\n子任务统计：")
    for status in [SUB_PENDING, SUB_RUNNING, SUB_SUCCESS, SUB_FAILED]:
        count = await subtasks_coll.count_documents({"status": status})
        print(f"  {status}: {count}")
    
    print("\n正在运行的任务：")
    cursor = jobs_coll.find({"status": JOB_RUNNING}).sort("created_at", 1)
    jobs = await cursor.to_list(length=10)
    
    if not jobs:
        print("  无")
    else:
        for job in jobs:
            job_id = job["_id"]
            config = job.get("config", {})
            stats = job.get("stats", {})
            cat_id = config.get("catId", "")
            total = stats.get("total_subtasks", 0)
            completed = stats.get("completed", 0)
            failed_count = stats.get("failed", 0)
            progress_pct = (completed / total * 100) if total > 0 else 0
            
            print(f"  Job {job_id}:")
            print(f"    类目: {cat_id}")
            print(f"    进度: {completed}/{total} ({progress_pct:.1f}%)")
            print(f"    失败: {failed_count}")
    
    await database.disconnect_mongo()
    print("\n" + "=" * 80)


async def queue_cancel(job_id_str: str):
    """取消任务"""
    from bson import ObjectId
    
    print(f"取消任务: {job_id_str}")
    
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    
    if database.mongo_db is None:
        print("✗ 数据库未连接")
        return
    
    try:
        job_id = ObjectId(job_id_str)
    except Exception:
        print("✗ 无效的Job ID")
        await database.disconnect_mongo()
        return
    
    result = await database.mongo_db[CRAWL_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": JOB_CANCELLED, "updated_at": datetime.utcnow()}},
    )
    
    if result.modified_count > 0:
        print("✓ 任务已取消")
    else:
        print("✗ 任务不存在或已完成")
    
    await database.disconnect_mongo()


# ==============================================================================
# CLI 入口
# ==============================================================================
def _parse_date_range(args):
    """解析时间范围参数"""
    if args.start and args.end:
        return args.start, args.end
    elif args.days:
        end_date = datetime.now() - timedelta(days=1)
        start_date = end_date - timedelta(days=args.days - 1)
    elif args.months:
        end_date = datetime.now() - timedelta(days=1)
        start_date = end_date - timedelta(days=args.months * 30)
    elif args.years:
        end_date = datetime.now() - timedelta(days=1)
        start_date = end_date - timedelta(days=args.years * 365)
    else:
        # 默认近两年
        end_date = datetime.now() - timedelta(days=1)
        start_date = end_date - timedelta(days=730)
    
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="萌拉数据补录工具")
    subparsers = parser.add_subparsers(dest="mode", help="补录模式")
    
    # single 模式
    single_parser = subparsers.add_parser("single", help="简单补录（串行执行）")
    single_parser.add_argument("--start", type=str, help="起始日期 yyyy-MM-dd")
    single_parser.add_argument("--end", type=str, help="结束日期 yyyy-MM-dd")
    single_parser.add_argument("--days", type=int, help="最近N天")
    single_parser.add_argument("--months", type=int, help="最近N个月")
    single_parser.add_argument("--years", type=int, help="最近N年")
    single_parser.add_argument(
        "--actions", nargs="+",
        default=["high", "hot", "chance", "industryViewV2", "industryTrendRange"],
        help="要采集的接口",
    )
    single_parser.add_argument(
        "--granularities", nargs="+",
        default=["day", "month", "quarter", "year"],
        help="要采集的颗粒度",
    )
    single_parser.add_argument("--cat-ids", nargs="+", help="指定类目ID")
    single_parser.add_argument("--no-resume", action="store_true", help="不使用断点续传")
    single_parser.add_argument("--sleep-min", type=float, default=1.0, help="最小休眠（秒）")
    single_parser.add_argument("--sleep-max", type=float, default=3.0, help="最大休眠（秒）")
    single_parser.add_argument("--clear-progress", action="store_true", help="清除进度文件")
    
    # queue 模式
    queue_parser = subparsers.add_parser("queue", help="队列补录（多worker）")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_cmd", help="队列命令")
    
    # queue create
    create_parser = queue_subparsers.add_parser("create", help="创建队列任务")
    create_parser.add_argument("--start", type=str, help="起始日期")
    create_parser.add_argument("--end", type=str, help="结束日期")
    create_parser.add_argument("--days", type=int, help="最近N天")
    create_parser.add_argument("--months", type=int, help="最近N个月")
    create_parser.add_argument("--years", type=int, help="最近N年")
    create_parser.add_argument("--actions", nargs="+",
        default=["high", "hot", "chance", "industryViewV2", "industryTrendRange"])
    create_parser.add_argument("--granularities", nargs="+",
        default=["day", "month", "quarter", "year"])
    
    # queue worker
    worker_parser = queue_subparsers.add_parser("worker", help="启动worker")
    worker_parser.add_argument("--workers", type=int, default=3, help="worker数量")
    worker_parser.add_argument("--sleep-min", type=float, default=1.0)
    worker_parser.add_argument("--sleep-max", type=float, default=3.0)
    
    # queue status
    queue_subparsers.add_parser("status", help="查看队列状态")
    
    # queue cancel
    cancel_parser = queue_subparsers.add_parser("cancel", help="取消任务")
    cancel_parser.add_argument("job_id", type=str, help="任务ID")
    
    args = parser.parse_args()
    
    if args.mode == "single":
        if args.clear_progress:
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
                print(f"✓ 已清除进度文件: {PROGRESS_FILE}")
            return
        
        start_date, end_date = _parse_date_range(args)
        
        cat_ids = args.cat_ids
        if not cat_ids:
            try:
                cat_ids = get_top_level_cat_ids()
            except Exception:
                cat_ids = [""]
        
        asyncio.run(backfill_data(
            start_date=start_date,
            end_date=end_date,
            actions=args.actions,
            granularities=args.granularities,
            cat_ids=cat_ids,
            resume=not args.no_resume,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
        ))
    
    elif args.mode == "queue":
        if args.queue_cmd == "create":
            start_date, end_date = _parse_date_range(args)
            asyncio.run(queue_create(start_date, end_date, args.actions, args.granularities))
        elif args.queue_cmd == "worker":
            asyncio.run(queue_worker(args.workers, args.sleep_min, args.sleep_max))
        elif args.queue_cmd == "status":
            asyncio.run(queue_status())
        elif args.queue_cmd == "cancel":
            asyncio.run(queue_cancel(args.job_id))
        else:
            queue_parser.print_help()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
