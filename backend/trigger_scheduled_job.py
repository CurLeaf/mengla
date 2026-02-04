"""
手动触发定时任务，用于测试
运行方法：python -m backend.trigger_scheduled_job
"""
import asyncio
import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.scheduler import run_mengla_granular_jobs
from backend import database
import os


async def main():
    print("=" * 60)
    print("手动触发萌拉定时任务（模拟凌晨 2:10 执行）")
    print("=" * 60)
    
    # 1. 连接数据库
    print("\n[1/3] 连接 MongoDB 和 Redis...")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    redis_uri = os.getenv("REDIS_URI", "redis://localhost:6380/0")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    await database.connect_to_redis(redis_uri)
    print("✓ 数据库连接成功")
    
    # 2. 执行定时任务
    print("\n[2/3] 执行萌拉定时任务...")
    print("这将采集 5 个接口 × 4 种颗粒度 × N 个类目的数据")
    print("预计需要几分钟时间，请耐心等待...\n")
    
    try:
        await run_mengla_granular_jobs()
        print("\n✓ 定时任务执行完成")
    except Exception as e:
        print(f"\n✗ 定时任务执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. 关闭连接
    print("\n[3/3] 关闭数据库连接...")
    await database.disconnect_redis()
    await database.disconnect_mongo()
    print("✓ 已关闭连接")
    
    print("\n" + "=" * 60)
    print("完成！现在检查 MongoDB，应该有 5 个集合：")
    print("  - mengla_high_reports (蓝海)")
    print("  - mengla_hot_reports (热销)")
    print("  - mengla_chance_reports (潜力)")
    print("  - mengla_view_reports (行业区间)")
    print("  - mengla_trend_reports (行业趋势)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
