"""
清除 MongoDB 与 Redis 中本项目使用的数据。
用法（在项目根目录）：
  python -m backend.clear_storage
"""
from pathlib import Path
import asyncio
import os

# 加载 backend/.env
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path)

MONGO_URI_DEFAULT = "mongodb://localhost:27017"
MONGO_DB_DEFAULT = "industry_monitor"
REDIS_URI_DEFAULT = "redis://localhost:6379/0"


async def clear_mongo():
    import motor.motor_asyncio
    uri = os.getenv("MONGO_URI", MONGO_URI_DEFAULT)
    db_name = os.getenv("MONGO_DB", MONGO_DB_DEFAULT)
    client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    try:
        await client.drop_database(db_name)
        print(f"MongoDB: 已删除整个数据库 {db_name}（所有集合与数据已清空）")
    except Exception as e:
        print(f"MongoDB: 删除数据库失败: {e}")
    finally:
        client.close()


async def clear_redis():
    from redis import asyncio as aioredis
    uri = os.getenv("REDIS_URI", REDIS_URI_DEFAULT)
    client = aioredis.from_url(uri, encoding="utf-8", decode_responses=True)
    try:
        await client.flushdb()
        print("Redis: 已清空当前 DB 所有数据")
    except Exception as e:
        print(f"Redis: 清空失败: {e}")
    finally:
        await client.aclose()


async def main():
    print("开始清除 MongoDB 与 Redis...")
    await clear_mongo()
    await clear_redis()
    print("完成。")


if __name__ == "__main__":
    asyncio.run(main())
