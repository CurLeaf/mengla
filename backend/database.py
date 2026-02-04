from typing import Optional

from pathlib import Path

import motor.motor_asyncio
from redis import asyncio as aioredis
from fastapi import FastAPI
from dotenv import load_dotenv


MONGO_URI_DEFAULT = "mongodb://localhost:27017"
MONGO_DB_DEFAULT = "industry_monitor"
REDIS_URI_DEFAULT = "redis://localhost:6379/0"


mongo_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
mongo_db = None
redis_client: Optional[aioredis.Redis] = None


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
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(uri)
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

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await disconnect_redis()
        await disconnect_mongo()

