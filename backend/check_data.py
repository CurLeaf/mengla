"""
检查 MongoDB 中已有的数据
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import database


async def check_data():
    print("=" * 80)
    print("检查 MongoDB 数据")
    print("=" * 80)
    
    # 连接数据库
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    print("✓ 数据库连接成功\n")
    
    collections = [
        ("mengla_high_reports", "蓝海Top行业"),
        ("mengla_hot_reports", "热销Top行业"),
        ("mengla_chance_reports", "潜力Top行业"),
        ("mengla_view_reports", "行业区间"),
        ("mengla_trend_reports", "行业趋势"),
    ]
    
    print("数据统计：")
    print("-" * 80)
    
    for coll_name, desc in collections:
        coll = database.mongo_db[coll_name]
        count = await coll.count_documents({})
        print(f"{desc:20s} ({coll_name:25s}): {count:6d} 条")
        
        if count > 0:
            # 显示最新的一条数据
            latest = await coll.find_one(sort=[("created_at", -1)])
            if latest:
                print(f"  最新数据: {latest.get('granularity')}/{latest.get('period_key')} "
                      f"(创建于 {latest.get('created_at')})")
    
    print("-" * 80)
    
    await database.disconnect_mongo()


if __name__ == "__main__":
    asyncio.run(check_data())
