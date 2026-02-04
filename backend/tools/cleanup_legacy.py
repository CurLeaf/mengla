#!/usr/bin/env python3
"""
清理旧版数据脚本

删除旧的5个独立集合（已迁移到统一集合 mengla_data）：
- mengla_high_reports
- mengla_hot_reports
- mengla_chance_reports
- mengla_view_reports
- mengla_trend_reports

同时清理 Redis 中对应的旧缓存 key。

使用方法：
    # 预览模式（不实际删除）
    python -m backend.tools.cleanup_legacy --dry-run
    
    # 执行清理
    python -m backend.tools.cleanup_legacy --confirm
    
    # 同时清理 Redis
    python -m backend.tools.cleanup_legacy --confirm --redis
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import List, Tuple

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.infra import database


# 旧集合列表
LEGACY_COLLECTIONS = [
    "mengla_high_reports",
    "mengla_hot_reports",
    "mengla_chance_reports",
    "mengla_view_reports",
    "mengla_trend_reports",
]

# 旧 Redis key 前缀
LEGACY_REDIS_PREFIXES = [
    "mengla:high:",
    "mengla:hot:",
    "mengla:chance:",
    "mengla:view:",
    "mengla:trend:",
]


async def get_collection_stats() -> List[Tuple[str, int]]:
    """获取各集合的文档数量"""
    stats = []
    if database.mongo_db is None:
        return stats
    
    for name in LEGACY_COLLECTIONS:
        try:
            coll = database.mongo_db[name]
            count = await coll.count_documents({})
            stats.append((name, count))
        except Exception as e:
            stats.append((name, -1))
            print(f"  [错误] {name}: {e}")
    
    # 新集合统计
    try:
        new_coll = database.mongo_db["mengla_data"]
        new_count = await new_coll.count_documents({})
        stats.append(("mengla_data (新)", new_count))
    except Exception as e:
        stats.append(("mengla_data (新)", -1))
    
    return stats


async def drop_legacy_collections(dry_run: bool = True) -> List[Tuple[str, bool, str]]:
    """删除旧集合"""
    results = []
    if database.mongo_db is None:
        return results
    
    for name in LEGACY_COLLECTIONS:
        try:
            if dry_run:
                results.append((name, True, "预览模式，未删除"))
            else:
                await database.mongo_db.drop_collection(name)
                results.append((name, True, "已删除"))
        except Exception as e:
            results.append((name, False, str(e)))
    
    return results


async def cleanup_legacy_redis_keys(dry_run: bool = True) -> Tuple[int, int]:
    """清理旧 Redis key"""
    if database.redis_client is None:
        return (0, 0)
    
    total_found = 0
    total_deleted = 0
    
    for prefix in LEGACY_REDIS_PREFIXES:
        try:
            # 使用 SCAN 遍历匹配的 key
            cursor = 0
            keys_to_delete = []
            
            while True:
                cursor, keys = await database.redis_client.scan(
                    cursor=cursor, 
                    match=f"{prefix}*", 
                    count=1000
                )
                keys_to_delete.extend(keys)
                if cursor == 0:
                    break
            
            total_found += len(keys_to_delete)
            
            if keys_to_delete and not dry_run:
                # 批量删除
                deleted = await database.redis_client.delete(*keys_to_delete)
                total_deleted += deleted
            elif keys_to_delete and dry_run:
                total_deleted += len(keys_to_delete)  # 预览模式，假设全部删除
                
        except Exception as e:
            print(f"  [错误] Redis prefix {prefix}: {e}")
    
    return (total_found, total_deleted)


async def main():
    parser = argparse.ArgumentParser(description="清理旧版 MengLa 数据")
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        default=True,
        help="预览模式，不实际删除（默认）"
    )
    parser.add_argument(
        "--confirm", 
        action="store_true",
        help="确认执行删除操作"
    )
    parser.add_argument(
        "--redis", 
        action="store_true",
        help="同时清理 Redis 缓存"
    )
    
    args = parser.parse_args()
    dry_run = not args.confirm
    
    print("=" * 60)
    print("MengLa 旧数据清理工具")
    print("=" * 60)
    
    if dry_run:
        print("\n[预览模式] 不会实际删除数据，使用 --confirm 执行删除\n")
    else:
        print("\n[!] 即将执行删除操作 [!]\n")
    
    # 1. 连接数据库
    print("1. 连接数据库...")
    mongo_uri = os.getenv("MONGO_URI", database.MONGO_URI_DEFAULT)
    mongo_db_name = os.getenv("MONGO_DB", database.MONGO_DB_DEFAULT)
    redis_uri = os.getenv("REDIS_URI", database.REDIS_URI_DEFAULT)
    
    try:
        await database.connect_to_mongo(mongo_uri, mongo_db_name)
        print(f"   MongoDB: {mongo_db_name} [OK]")
    except Exception as e:
        print(f"   MongoDB: 连接失败 - {e}")
        return 1
    
    if args.redis:
        try:
            await database.connect_to_redis(redis_uri)
            print(f"   Redis: 已连接 [OK]")
        except Exception as e:
            print(f"   Redis: 连接失败 - {e}")
    
    # 2. 显示当前统计
    print("\n2. 当前数据统计:")
    print("-" * 50)
    stats = await get_collection_stats()
    total_legacy_docs = 0
    for name, count in stats:
        status = f"{count:,}" if count >= 0 else "错误"
        print(f"   {name:<30} {status:>15}")
        if name != "mengla_data (新)" and count > 0:
            total_legacy_docs += count
    print("-" * 50)
    print(f"   {'旧集合总计':<30} {total_legacy_docs:>15,}")
    
    if total_legacy_docs == 0:
        print("\n[OK] 旧集合已经是空的，无需清理")
        await database.close_connections()
        return 0
    
    # 3. 删除旧集合
    print(f"\n3. {'预览' if dry_run else '执行'}删除旧集合:")
    print("-" * 50)
    results = await drop_legacy_collections(dry_run)
    for name, success, msg in results:
        status = "[OK]" if success else "[失败]"
        print(f"   {status} {name}: {msg}")
    
    # 4. 清理 Redis（可选）
    if args.redis:
        print(f"\n4. {'预览' if dry_run else '执行'}清理 Redis 缓存:")
        print("-" * 50)
        found, deleted = await cleanup_legacy_redis_keys(dry_run)
        if dry_run:
            print(f"   发现 {found:,} 个旧 key（预览模式，未删除）")
        else:
            print(f"   已删除 {deleted:,} / {found:,} 个旧 key")
    
    # 5. 完成
    print("\n" + "=" * 60)
    if dry_run:
        print("预览完成。使用 --confirm 参数执行实际删除。")
        print("\n示例：")
        print("  python -m backend.tools.cleanup_legacy --confirm")
        print("  python -m backend.tools.cleanup_legacy --confirm --redis")
    else:
        print("清理完成！")
    print("=" * 60)
    
    # 关闭连接
    if database.mongo_client:
        database.mongo_client.close()
    if database.redis_client:
        await database.redis_client.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
