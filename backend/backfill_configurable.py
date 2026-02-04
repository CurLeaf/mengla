"""
可配置的历史数据补录脚本
支持：
- 自定义时间范围
- 选择接口和颗粒度
- 选择类目
- 断点续传
- 进度保存

运行方法：
  python -m backend.backfill_configurable --help
  python -m backend.backfill_configurable --days 30 --actions high hot --granularities day month
  python -m backend.backfill_configurable --start 2023-01-01 --end 2024-12-31
"""
import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import database
from backend.category_utils import get_top_level_cat_ids
from backend.mengla_domain import query_mengla_domain
from backend.period_utils import period_keys_in_range, period_to_date_range


# 进度文件路径
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
    补录历史数据
    
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
    redis_uri = os.getenv("REDIS_URI", "redis://localhost:6380/0")
    
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
                                await query_mengla_domain(
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
                                await query_mengla_domain(
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


def main():
    parser = argparse.ArgumentParser(description="历史数据补录脚本")
    
    # 时间范围
    parser.add_argument("--start", type=str, help="起始日期 yyyy-MM-dd")
    parser.add_argument("--end", type=str, help="结束日期 yyyy-MM-dd")
    parser.add_argument("--days", type=int, help="最近N天（与start/end互斥）")
    parser.add_argument("--months", type=int, help="最近N个月（与start/end互斥）")
    parser.add_argument("--years", type=int, help="最近N年（与start/end互斥）")
    
    # 接口和颗粒度
    parser.add_argument(
        "--actions",
        nargs="+",
        default=["high", "hot", "chance", "industryViewV2", "industryTrendRange"],
        choices=["high", "hot", "chance", "industryViewV2", "industryTrendRange"],
        help="要采集的接口",
    )
    parser.add_argument(
        "--granularities",
        nargs="+",
        default=["day", "month", "quarter", "year"],
        choices=["day", "month", "quarter", "year"],
        help="要采集的颗粒度",
    )
    
    # 类目
    parser.add_argument("--cat-ids", nargs="+", help="指定类目ID（默认所有一级类目）")
    
    # 其他选项
    parser.add_argument("--no-resume", action="store_true", help="不使用断点续传")
    parser.add_argument("--sleep-min", type=float, default=1.0, help="最小休眠时间（秒）")
    parser.add_argument("--sleep-max", type=float, default=3.0, help="最大休眠时间（秒）")
    parser.add_argument("--clear-progress", action="store_true", help="清除进度文件")
    
    args = parser.parse_args()
    
    # 清除进度
    if args.clear_progress:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print(f"✓ 已清除进度文件: {PROGRESS_FILE}")
        return
    
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
    
    # 获取类目
    if args.cat_ids:
        cat_ids = args.cat_ids
    else:
        try:
            cat_ids = get_top_level_cat_ids()
        except Exception as e:
            print(f"⚠ 加载类目失败: {e}")
            cat_ids = [""]
    
    # 执行
    asyncio.run(
        backfill_data(
            start_date=start_date,
            end_date=end_date,
            actions=args.actions,
            granularities=args.granularities,
            cat_ids=cat_ids,
            resume=not args.no_resume,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
        )
    )


if __name__ == "__main__":
    main()
