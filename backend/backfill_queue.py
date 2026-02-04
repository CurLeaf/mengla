"""
基于队列的并发历史数据补录
使用全局锁确保同一时间只有一个请求发送到采集服务
多个worker可以并发处理不同的任务，但实际请求是串行的

运行方法：
  # 创建队列任务
  python -m backend.backfill_queue create --years 2
  python -m backend.backfill_queue create --start 2023-01-01 --end 2024-12-31
  
  # 启动worker（建议3-5个，虽然请求串行但可以并发处理其他逻辑）
  python -m backend.backfill_queue worker --workers 3
  
  # 查看队列状态
  python -m backend.backfill_queue status
  
  # 取消任务
  python -m backend.backfill_queue cancel <job_id>
  
注意：
  - 采集服务限制：同一时间只能有一个请求
  - 使用全局锁确保请求串行执行
  - 多个worker可以提高任务调度效率
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import database
from backend.category_utils import get_top_level_cat_ids
from backend.mengla_crawl_queue import (
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
from backend.mengla_domain import query_mengla_domain
from backend.period_utils import period_to_date_range


# 全局请求锁：确保同一时间只有一个请求发送到采集服务
REQUEST_LOCK = asyncio.Lock()


async def create_jobs_for_all_categories(
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
    print("\n现在可以启动worker来处理任务：")
    print("  python -m backend.backfill_queue worker --workers 5")
    print("\n查看任务状态：")
    print("  python -m backend.backfill_queue status")
    print("=" * 80)


async def run_worker(
    worker_id: int,
    sleep_min: float = 1.0,
    sleep_max: float = 3.0,
    max_retries: int = 3,
):
    """单个worker，从队列中取任务并执行"""
    print(f"[Worker {worker_id}] 启动")
    
    processed = 0
    failed = 0
    
    while True:
        try:
            # 获取下一个任务
            job = await get_next_job()
            if not job:
                print(f"[Worker {worker_id}] 没有待处理任务，等待...")
                await asyncio.sleep(10)
                continue
            
            job_id = job["_id"]
            
            # 设置任务为运行中
            if job["status"] == JOB_PENDING:
                await set_job_running(job_id)
            
            config = job.get("config") or {}
            cat_id = config.get("catId", "") or ""
            extra = config.get("extra") or {}
            
            # 获取待处理的子任务（批量处理）
            subtasks = await get_pending_subtasks(job_id, limit=10)
            
            if not subtasks:
                # 检查任务是否完成
                await finish_job_if_done(job_id)
                continue
            
            # 处理子任务
            for sub in subtasks:
                sub_id = sub["_id"]
                action = sub.get("action", "")
                gran = sub.get("granularity", "day")
                period_key = sub.get("period_key", "")
                attempts = sub.get("attempts", 0)
                
                # 检查重试次数
                if attempts >= max_retries:
                    await set_subtask_failed(sub_id, f"超过最大重试次数 {max_retries}")
                    await inc_job_stats(job_id, completed_delta=0, failed_delta=1)
                    failed += 1
                    continue
                
                await set_subtask_running(sub_id)
                
                try:
                    # 使用全局锁确保同一时间只有一个请求
                    async with REQUEST_LOCK:
                        # 执行采集
                        if action == "industryTrendRange":
                            start_range, end_range = period_to_date_range(gran, period_key)
                            date_type = {
                                "day": "DAY",
                                "month": "MONTH",
                                "quarter": "QUARTERLY_FOR_YEAR",
                                "year": "YEAR",
                            }.get(gran, "DAY")
                            
                            await query_mengla_domain(
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
                            await query_mengla_domain(
                                action=action,
                                product_id="",
                                catId=cat_id,
                                dateType=gran,
                                timest=period_key,
                                starRange="",
                                endRange="",
                                extra=extra,
                            )
                        
                        # 请求完成后休眠，避免请求过快
                        await asyncio.sleep(random.uniform(sleep_min, sleep_max))
                    
                    await set_subtask_success(sub_id)
                    await inc_job_stats(job_id, completed_delta=1, failed_delta=0)
                    processed += 1
                    
                    if processed % 10 == 0:
                        print(f"[Worker {worker_id}] 已处理 {processed} 个任务，失败 {failed} 个")
                    
                except Exception as e:
                    error_msg = str(e)
                    await set_subtask_failed(sub_id, error_msg)
                    await inc_job_stats(job_id, completed_delta=0, failed_delta=1)
                    failed += 1
                    print(f"[Worker {worker_id}] ✗ 任务失败: {action}/{gran}/{period_key} - {error_msg}")
            
            # 检查任务是否完成
            await finish_job_if_done(job_id)
            
        except KeyboardInterrupt:
            print(f"\n[Worker {worker_id}] 收到中断信号，退出...")
            break
        except Exception as e:
            print(f"[Worker {worker_id}] ✗ 处理出错: {e}")
            await asyncio.sleep(5)


async def run_workers(num_workers: int, sleep_min: float, sleep_max: float):
    """启动多个worker并发处理（使用全局锁确保请求串行）"""
    print("=" * 80)
    print(f"启动 {num_workers} 个Worker（请求串行执行）")
    print("=" * 80)
    
    # 连接数据库
    print("\n连接数据库...")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    redis_uri = os.getenv("REDIS_URI", "redis://localhost:6380/0")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    await database.connect_to_redis(redis_uri)
    print("✓ 数据库连接成功")
    
    print(f"\n启动 {num_workers} 个worker（请求通过全局锁串行执行）...")
    print("按 Ctrl+C 停止\n")
    
    # 创建worker任务
    workers = [
        asyncio.create_task(run_worker(i + 1, sleep_min, sleep_max))
        for i in range(num_workers)
    ]
    
    try:
        # 等待所有worker完成
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


async def show_status():
    """显示队列状态"""
    print("=" * 80)
    print("队列状态")
    print("=" * 80)
    
    # 连接数据库
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    
    if database.mongo_db is None:
        print("✗ 数据库未连接")
        return
    
    # 统计任务状态
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
    
    # 显示正在运行的任务详情
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
            failed = stats.get("failed", 0)
            progress = (completed / total * 100) if total > 0 else 0
            
            print(f"  Job {job_id}:")
            print(f"    类目: {cat_id}")
            print(f"    进度: {completed}/{total} ({progress:.1f}%)")
            print(f"    失败: {failed}")
    
    await database.disconnect_mongo()
    print("\n" + "=" * 80)


async def cancel_job(job_id_str: str):
    """取消任务"""
    from bson import ObjectId
    
    print(f"取消任务: {job_id_str}")
    
    # 连接数据库
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
    
    # 更新任务状态
    result = await database.mongo_db[CRAWL_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": JOB_CANCELLED, "updated_at": datetime.utcnow()}},
    )
    
    if result.modified_count > 0:
        print("✓ 任务已取消")
    else:
        print("✗ 任务不存在或已完成")
    
    await database.disconnect_mongo()


def main():
    parser = argparse.ArgumentParser(description="基于队列的历史数据补录")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # create 命令
    create_parser = subparsers.add_parser("create", help="创建队列任务")
    create_parser.add_argument("--start", type=str, help="起始日期 yyyy-MM-dd")
    create_parser.add_argument("--end", type=str, help="结束日期 yyyy-MM-dd")
    create_parser.add_argument("--days", type=int, help="最近N天")
    create_parser.add_argument("--months", type=int, help="最近N个月")
    create_parser.add_argument("--years", type=int, help="最近N年")
    create_parser.add_argument(
        "--actions",
        nargs="+",
        default=["high", "hot", "chance", "industryViewV2", "industryTrendRange"],
        choices=["high", "hot", "chance", "industryViewV2", "industryTrendRange"],
        help="要采集的接口",
    )
    create_parser.add_argument(
        "--granularities",
        nargs="+",
        default=["day", "month", "quarter", "year"],
        choices=["day", "month", "quarter", "year"],
        help="要采集的颗粒度",
    )
    
    # worker 命令
    worker_parser = subparsers.add_parser("worker", help="启动worker处理任务")
    worker_parser.add_argument("--workers", type=int, default=3, help="并发worker数量")
    worker_parser.add_argument("--sleep-min", type=float, default=1.0, help="最小休眠时间（秒）")
    worker_parser.add_argument("--sleep-max", type=float, default=3.0, help="最大休眠时间（秒）")
    
    # status 命令
    subparsers.add_parser("status", help="查看队列状态")
    
    # cancel 命令
    cancel_parser = subparsers.add_parser("cancel", help="取消任务")
    cancel_parser.add_argument("job_id", type=str, help="任务ID")
    
    args = parser.parse_args()
    
    if args.command == "create":
        # 计算时间范围
        if args.start and args.end:
            start_date = args.start
            end_date = args.end
        elif args.days:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=args.days)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = end_date.strftime("%Y-%m-%d")
        elif args.months:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=args.months * 30)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = end_date.strftime("%Y-%m-%d")
        elif args.years:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=args.years * 365)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = end_date.strftime("%Y-%m-%d")
        else:
            # 默认近两年
            end_date = datetime.now()
            start_date = end_date - timedelta(days=730)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = end_date.strftime("%Y-%m-%d")
        
        asyncio.run(
            create_jobs_for_all_categories(
                start_date=start_date,
                end_date=end_date,
                actions=args.actions,
                granularities=args.granularities,
            )
        )
    
    elif args.command == "worker":
        asyncio.run(run_workers(args.workers, args.sleep_min, args.sleep_max))
    
    elif args.command == "status":
        asyncio.run(show_status())
    
    elif args.command == "cancel":
        asyncio.run(cancel_job(args.job_id))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
