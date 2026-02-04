"""
清除 MongoDB 与 Redis 中本项目使用的数据。

用法（在项目根目录）：
  python -m backend.scripts.clear_storage
  python -m backend.scripts.clear_storage --confirm  # 跳过确认
"""
from pathlib import Path
import argparse
import asyncio
import os

# 加载项目根目录 .env
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_env_path)
    except ImportError:
        pass

MONGO_URI_DEFAULT = "mongodb://localhost:27017"
MONGO_DB_DEFAULT = "industry_monitor"
REDIS_URI_DEFAULT = "redis://localhost:6379/0"


async def clear_mongo(verbose: bool = True):
    """清除 MongoDB 数据"""
    import motor.motor_asyncio
    uri = os.getenv("MONGO_URI", MONGO_URI_DEFAULT)
    db_name = os.getenv("MONGO_DB", MONGO_DB_DEFAULT)
    
    if verbose:
        print(f"MongoDB: 连接 {uri}")
    
    client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    try:
        await client.drop_database(db_name)
        if verbose:
            print(f"MongoDB: 已删除数据库 {db_name}")
    except Exception as e:
        if verbose:
            print(f"MongoDB: 删除失败: {e}")
        raise
    finally:
        client.close()


async def clear_redis(verbose: bool = True):
    """清除 Redis 数据"""
    from redis import asyncio as aioredis
    uri = os.getenv("REDIS_URI", REDIS_URI_DEFAULT)
    
    if verbose:
        print(f"Redis: 连接 {uri}")
    
    client = aioredis.from_url(uri, encoding="utf-8", decode_responses=True)
    try:
        await client.flushdb()
        if verbose:
            print("Redis: 已清空当前 DB")
    except Exception as e:
        if verbose:
            print(f"Redis: 清空失败: {e}")
        raise
    finally:
        await client.aclose()


async def main(skip_confirm: bool = False):
    """主函数"""
    print("=" * 60)
    print("清除存储数据")
    print("=" * 60)
    print(f"MongoDB: {os.getenv('MONGO_URI', MONGO_URI_DEFAULT)}")
    print(f"数据库:  {os.getenv('MONGO_DB', MONGO_DB_DEFAULT)}")
    print(f"Redis:   {os.getenv('REDIS_URI', REDIS_URI_DEFAULT)}")
    print("=" * 60)
    
    if not skip_confirm:
        print("\n⚠️  警告：此操作将删除所有数据！")
        confirm = input("确认清除？(输入 yes 继续): ").strip().lower()
        if confirm != "yes":
            print("已取消")
            return
    
    print("\n开始清除...")
    await clear_mongo()
    await clear_redis()
    print("\n✓ 清除完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清除存储数据")
    parser.add_argument("--confirm", action="store_true", help="跳过确认直接执行")
    args = parser.parse_args()
    
    asyncio.run(main(skip_confirm=args.confirm))
