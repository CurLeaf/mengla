"""类目与行业数据查询路由"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import require_auth
from ..infra import database
from ..utils.category import get_all_categories

router = APIRouter(tags=["Categories"])

logger = logging.getLogger("mengla-backend")


@router.get("/api/categories", dependencies=[Depends(require_auth)])
async def get_categories():
    """
    返回类目树，数据来源于 backend/category.json。
    为避免频繁读大文件，使用简单内存缓存。
    """
    return get_all_categories()


@router.get("/api/industry/daily", dependencies=[Depends(require_auth)])
async def get_industry_daily(date: str):
    """
    示例查询接口：按天返回某个 period_key 的所有行业数据。
    查询顺序：1) MongoDB  2) Redis，命中即返回。
    """
    if database.mongo_db is None:
        raise HTTPException(status_code=500, detail="MongoDB not initialized")

    collection = database.mongo_db["industry_reports"]
    cursor = collection.find({"granularity": "day", "period_key": date})
    docs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        docs.append(doc)

    if docs:
        if database.redis_client is not None:
            await database.redis_client.set(
                f"industry:day:{date}", json.dumps(docs), ex=60 * 60 * 24
            )
        return docs

    redis_key = f"industry:day:{date}"
    if database.redis_client is not None:
        cached = await database.redis_client.get(redis_key)
        if cached:
            return json.loads(cached)

    return docs
