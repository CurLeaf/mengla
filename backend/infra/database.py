from typing import Optional, List
from pathlib import Path
import logging

import motor.motor_asyncio
from pymongo import IndexModel, ASCENDING
from redis import asyncio as aioredis
from fastapi import FastAPI
from dotenv import load_dotenv


logger = logging.getLogger("mengla-database")

MONGO_URI_DEFAULT = "mongodb://localhost:27017"
MONGO_DB_DEFAULT = "industry_monitor"
REDIS_URI_DEFAULT = "redis://localhost:6379/0"

# 统一集合名称
MENGLA_DATA_COLLECTION = "mengla_data"

mongo_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
mongo_db = None
redis_client: Optional[aioredis.Redis] = None


# ==============================================================================
# MongoDB 索引定义
# ==============================================================================
def get_mengla_data_indexes() -> List[IndexModel]:
    """获取 mengla_data 集合的索引定义"""
    return [
        # 主查询索引（唯一）：action + cat_id + granularity + period_key
        IndexModel(
            [
                ("action", ASCENDING),
                ("cat_id", ASCENDING),
                ("granularity", ASCENDING),
                ("period_key", ASCENDING),
            ],
            unique=True,
            name="idx_main_query",
        ),
        # 类目维度查询
        IndexModel(
            [("cat_id", ASCENDING), ("created_at", ASCENDING)],
            name="idx_cat_time",
        ),
        # 跨类目聚合
        IndexModel(
            [
                ("action", ASCENDING),
                ("granularity", ASCENDING),
                ("period_key", ASCENDING),
            ],
            name="idx_action_period",
        ),
        # TTL 自动清理索引
        IndexModel(
            [("expired_at", ASCENDING)],
            expireAfterSeconds=0,
            name="idx_ttl_expired",
        ),
        # 增量同步
        IndexModel(
            [("updated_at", ASCENDING)],
            name="idx_updated",
        ),
    ]


async def ensure_indexes() -> None:
    """确保所有索引已创建"""
    if mongo_db is None:
        logger.warning("MongoDB not connected, skipping index creation")
        return
    
    # 1. 新统一集合的索引
    collection = mongo_db[MENGLA_DATA_COLLECTION]
    indexes = get_mengla_data_indexes()
    
    try:
        # 获取现有索引
        existing_indexes = set()
        async for idx in collection.list_indexes():
            existing_indexes.add(idx.get("name", ""))
        
        # 创建缺失的索引
        for idx in indexes:
            idx_name = idx.document.get("name", "")
            if idx_name and idx_name not in existing_indexes:
                try:
                    await collection.create_indexes([idx])
                    logger.info(f"Created index: {idx_name}")
                except Exception as e:
                    logger.warning(f"Failed to create index {idx_name}: {e}")
        
        logger.info(f"Index check completed for collection: {MENGLA_DATA_COLLECTION}")
    except Exception as e:
        logger.error(f"Error ensuring indexes: {e}")


def _mask_uri(uri: str) -> str:
    """Hide password in URI for logging."""
    if "@" in uri and "://" in uri:
        pre, rest = uri.split("://", 1)
        if "@" in rest:
            creds, host = rest.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{pre}://{user}:****@{host}"
        return f"{pre}://****@{rest.split('@', 1)[-1]}"
    return uri


async def connect_to_mongo(uri: str, db_name: str) -> None:
    global mongo_client, mongo_db
    # 单节点 MongoDB（非副本集）不支持 retryable writes，必须显式关闭
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(uri, retryWrites=False)
    mongo_db = mongo_client[db_name]
    import logging
    logging.getLogger("mengla-backend").info(
        "[DB] Mongo connected uri=%s db=%s", _mask_uri(uri), db_name
    )


async def disconnect_mongo() -> None:
    global mongo_client, mongo_db
    if mongo_client:
        mongo_client.close()
    mongo_client = None
    mongo_db = None


async def connect_to_redis(uri: str) -> None:
    global redis_client
    redis_client = aioredis.from_url(uri, encoding="utf-8", decode_responses=True)
    import logging
    logging.getLogger("mengla-backend").info(
        "[DB] Redis connected uri=%s", _mask_uri(uri)
    )


async def disconnect_redis() -> None:
    global redis_client
    if redis_client:
        await redis_client.close()
    redis_client = None


def init_db_events(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        import os

        # 加载项目根目录下的 .env 文件（如果存在）
        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(dotenv_path=env_path, override=False)

        mongo_uri = os.getenv("MONGO_URI", MONGO_URI_DEFAULT)
        mongo_db_name = os.getenv("MONGO_DB", MONGO_DB_DEFAULT)
        redis_uri = os.getenv("REDIS_URI", REDIS_URI_DEFAULT)

        await connect_to_mongo(mongo_uri, mongo_db_name)
        await connect_to_redis(redis_uri)
        
        # 确保索引已创建
        await ensure_indexes()

        # 清理上次服务重启时残留的 RUNNING 状态同步任务
        from ..core.sync_task_log import cleanup_stale_running_tasks
        await cleanup_stale_running_tasks()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await disconnect_redis()
        await disconnect_mongo()


def get_mengla_collection():
    """获取统一的 mengla_data 集合"""
    if mongo_db is None:
        raise RuntimeError("MongoDB not connected")
    return mongo_db[MENGLA_DATA_COLLECTION]

