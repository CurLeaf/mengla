"""
统一诊断工具

整合了环境检查、数据检查、服务连接检查等功能。

运行方法：
  python -m backend.scripts.diagnose           # 完整诊断
  python -m backend.scripts.diagnose env       # 仅检查环境变量
  python -m backend.scripts.diagnose data      # 仅检查数据
  python -m backend.scripts.diagnose services  # 仅检查服务连接
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ==============================================================================
# 环境变量检查
# ==============================================================================
def check_env_vars(verbose: bool = True) -> dict:
    """检查环境变量"""
    if verbose:
        print("\n" + "=" * 80)
        print("环境变量检查")
        print("=" * 80)
    
    vars_config = {
        "MONGO_URI": {"default": "mongodb://localhost:27017", "required": True},
        "MONGO_DB": {"default": "industry_monitor", "required": True},
        "REDIS_URI": {"default": "redis://localhost:6379/0", "required": True},
        "COLLECT_SERVICE_URL": {"default": "", "required": True},
        "COLLECT_SERVICE_API_KEY": {"default": "", "required": True, "secret": True},
        "APP_BASEURL": {"default": "http://localhost:8000", "required": False},
        "MENGLA_WEBHOOK_URL": {"default": "", "required": False},
        "MENGLA_TIMEOUT_SECONDS": {"default": "3600", "required": False},
    }
    
    results = {}
    all_ok = True
    
    for var, config in vars_config.items():
        value = os.getenv(var, config["default"])
        is_set = bool(value)
        is_ok = is_set or not config["required"]
        
        results[var] = {
            "value": value,
            "is_set": is_set,
            "is_ok": is_ok,
            "required": config["required"],
        }
        
        if verbose:
            if is_set:
                if config.get("secret"):
                    display = value[:10] + "..." + value[-5:] if len(value) > 15 else "***"
                else:
                    display = value
                print(f"✓ {var:30s} = {display}")
            else:
                status = "✗" if config["required"] else "○"
                print(f"{status} {var:30s} = (未设置)")
        
        if config["required"] and not is_set:
            all_ok = False
    
    # Webhook 特别提示
    webhook_url = os.getenv("MENGLA_WEBHOOK_URL")
    if verbose:
        if webhook_url:
            print(f"\n提示: 使用外部 Webhook: {webhook_url}")
            if "localhost" in webhook_url or "127.0.0.1" in webhook_url:
                print("  ⚠ 警告：localhost 地址，远程采集服务无法访问！")
        else:
            app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
            print(f"\n提示: 使用本地 Webhook: {app_base}/api/webhook/mengla-notify")
    
    results["_all_ok"] = all_ok
    return results


# ==============================================================================
# 数据检查
# ==============================================================================
async def check_data(verbose: bool = True) -> dict:
    """检查 MongoDB 数据"""
    if verbose:
        print("\n" + "=" * 80)
        print("MongoDB 数据检查")
        print("=" * 80)
    
    from backend.infra import database
    
    results = {"collections": {}, "_all_ok": False}
    
    try:
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
        
        await database.connect_to_mongo(mongo_uri, mongo_db_name)
        
        if database.mongo_db is None:
            if verbose:
                print("✗ 数据库未连接")
            return results
        
        # 检查各集合
        collections = [
            ("mengla_data", "统一数据集合"),
            ("crawl_jobs", "爬取任务"),
            ("crawl_subtasks", "爬取子任务"),
        ]
        
        if verbose:
            print(f"\n{'集合名':<30s} {'数量':>10s}   {'描述'}")
            print("-" * 80)
        
        total_count = 0
        for coll_name, desc in collections:
            try:
                coll = database.mongo_db[coll_name]
                count = await coll.count_documents({})
                total_count += count
                
                results["collections"][coll_name] = {
                    "count": count,
                    "description": desc,
                }
                
                if verbose:
                    print(f"{coll_name:<30s} {count:>10,d}   {desc}")
                    
                    if count > 0:
                        # 显示最新数据时间
                        latest = await coll.find_one(sort=[("created_at", -1)])
                        if latest and "created_at" in latest:
                            print(f"  └─ 最新: {latest.get('created_at')}")
            except Exception as e:
                results["collections"][coll_name] = {"error": str(e)}
                if verbose:
                    print(f"{coll_name:<30s} {'错误':>10s}   {e}")
        
        if verbose:
            print("-" * 80)
            print(f"{'总计':<30s} {total_count:>10,d}")
        
        results["total_count"] = total_count
        results["_all_ok"] = True
        
        await database.disconnect_mongo()
        
    except Exception as e:
        if verbose:
            print(f"✗ 数据检查失败: {e}")
        results["error"] = str(e)
    
    return results


# ==============================================================================
# 服务连接检查
# ==============================================================================
async def check_redis(verbose: bool = True) -> dict:
    """检查 Redis 连接"""
    if verbose:
        print("\n" + "=" * 80)
        print("Redis 连接检查")
        print("=" * 80)
    
    from backend.infra import database
    
    results = {"connected": False, "read_write": False}
    
    try:
        redis_uri = os.getenv("REDIS_URI", "redis://localhost:6379/0")
        if verbose:
            print(f"连接: {redis_uri}")
        
        await database.connect_to_redis(redis_uri)
        
        if database.redis_client is None:
            if verbose:
                print("✗ Redis 连接失败")
            return results
        
        results["connected"] = True
        
        # 测试读写
        test_key = "mengla:test:diagnose"
        await database.redis_client.set(test_key, "ok", ex=10)
        value = await database.redis_client.get(test_key)
        
        if value == "ok":
            results["read_write"] = True
            await database.redis_client.delete(test_key)
            if verbose:
                print("✓ Redis 连接成功，读写正常")
        else:
            if verbose:
                print("✗ Redis 读写失败")
        
        await database.disconnect_redis()
        
    except Exception as e:
        results["error"] = str(e)
        if verbose:
            print(f"✗ Redis 连接失败: {e}")
            print("  提示: 请确保 Redis 正在运行")
    
    results["_all_ok"] = results["connected"] and results["read_write"]
    return results


async def check_mongo(verbose: bool = True) -> dict:
    """检查 MongoDB 连接"""
    if verbose:
        print("\n" + "=" * 80)
        print("MongoDB 连接检查")
        print("=" * 80)
    
    from backend.infra import database
    
    results = {"connected": False, "read_write": False}
    
    try:
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
        if verbose:
            print(f"连接: {mongo_uri}/{mongo_db_name}")
        
        await database.connect_to_mongo(mongo_uri, mongo_db_name)
        
        if database.mongo_db is None:
            if verbose:
                print("✗ MongoDB 连接失败")
            return results
        
        results["connected"] = True
        
        # 测试读写
        test_coll = database.mongo_db["_test_diagnose"]
        await test_coll.insert_one({"test": "ok"})
        doc = await test_coll.find_one({"test": "ok"})
        await test_coll.delete_many({})
        
        if doc:
            results["read_write"] = True
            if verbose:
                print("✓ MongoDB 连接成功，读写正常")
        else:
            if verbose:
                print("✗ MongoDB 读写失败")
        
        await database.disconnect_mongo()
        
    except Exception as e:
        results["error"] = str(e)
        if verbose:
            print(f"✗ MongoDB 连接失败: {e}")
            print("  提示: 请确保 MongoDB 正在运行")
    
    results["_all_ok"] = results["connected"] and results["read_write"]
    return results


async def check_fastapi(verbose: bool = True) -> dict:
    """检查 FastAPI 服务"""
    if verbose:
        print("\n" + "=" * 80)
        print("FastAPI 服务检查")
        print("=" * 80)
    
    results = {"running": False}
    
    try:
        import httpx
        app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
        health_url = f"{app_base}/health"
        if verbose:
            print(f"检查: {health_url}")
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(health_url)
        
        if resp.status_code == 200:
            results["running"] = True
            if verbose:
                print("✓ FastAPI 服务正在运行")
                print(f"  Webhook: {app_base}/api/webhook/mengla-notify")
        else:
            if verbose:
                print(f"✗ FastAPI 服务响应异常: {resp.status_code}")
                
    except Exception as e:
        results["error"] = str(e)
        if verbose:
            print(f"✗ FastAPI 服务未运行")
            print("  启动命令: uvicorn backend.main:app --reload")
    
    results["_all_ok"] = results["running"]
    return results


async def check_collect_service(verbose: bool = True) -> dict:
    """检查采集服务连接"""
    if verbose:
        print("\n" + "=" * 80)
        print("采集服务连接检查")
        print("=" * 80)
    
    results = {"connected": False, "task_found": False}
    
    try:
        import httpx
        base_url = os.getenv("COLLECT_SERVICE_URL", "http://localhost:3001")
        api_key = os.getenv("COLLECT_SERVICE_API_KEY", "")
        url = f"{base_url}/api/managed-tasks"
        if verbose:
            print(f"检查: {url}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                params={"page": 1, "limit": 10},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        
        if resp.status_code == 200:
            results["connected"] = True
            data = resp.json()
            tasks = data.get("data", {}).get("tasks", [])
            
            if verbose:
                print(f"✓ 采集服务连接成功，共 {len(tasks)} 个任务")
            
            # 查找"萌啦数据采集"任务
            for task in tasks:
                if task.get("name") == "萌啦数据采集":
                    results["task_found"] = True
                    results["task_id"] = task.get("id")
                    if verbose:
                        print(f"✓ 找到'萌啦数据采集'任务 (ID: {task.get('id')})")
                    break
            
            if not results["task_found"] and verbose:
                print("✗ 未找到'萌啦数据采集'任务")
                print(f"  可用任务: {', '.join(t.get('name', '?') for t in tasks)}")
        else:
            if verbose:
                print(f"✗ 采集服务响应异常: {resp.status_code}")
                
    except Exception as e:
        results["error"] = str(e)
        if verbose:
            print(f"✗ 采集服务连接失败: {e}")
            print("  提示: 检查网络、VPN 或采集服务配置")
    
    results["_all_ok"] = results["connected"] and results["task_found"]
    return results


# ==============================================================================
# 完整诊断
# ==============================================================================
async def run_full_diagnose() -> dict:
    """运行完整诊断"""
    print("=" * 80)
    print("萌拉数据采集系统 - 完整诊断")
    print("=" * 80)
    
    results = {}
    
    # 1. 环境变量
    results["env"] = check_env_vars()
    
    # 2. Redis
    results["redis"] = await check_redis()
    
    # 3. MongoDB
    results["mongo"] = await check_mongo()
    
    # 4. FastAPI
    results["fastapi"] = await check_fastapi()
    
    # 5. 采集服务
    results["collect"] = await check_collect_service()
    
    # 6. 数据
    results["data"] = await check_data()
    
    # 总结
    print("\n" + "=" * 80)
    print("诊断总结")
    print("=" * 80)
    
    checks = [
        ("ENV", results["env"]["_all_ok"]),
        ("REDIS", results["redis"]["_all_ok"]),
        ("MONGO", results["mongo"]["_all_ok"]),
        ("FASTAPI", results["fastapi"]["_all_ok"]),
        ("COLLECT", results["collect"]["_all_ok"]),
        ("DATA", results["data"]["_all_ok"]),
    ]
    
    all_ok = all(ok for _, ok in checks)
    
    for name, ok in checks:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")
    
    print("=" * 80)
    
    if all_ok:
        print("\n✓ 所有检查通过！系统可正常运行。")
    else:
        print("\n✗ 部分检查失败，请根据上述提示修复问题。")
        print("\n常见解决方案：")
        print("  1. 启动 Redis: redis-server")
        print("  2. 启动 MongoDB: mongod")
        print("  3. 启动 FastAPI: uvicorn backend.main:app --reload")
    
    print("=" * 80)
    
    return results


# ==============================================================================
# 主入口
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="萌拉数据采集系统诊断工具")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["env", "data", "services", "full"],
        default="full",
        help="诊断命令: env(环境变量), data(数据), services(服务), full(完整)",
    )
    
    args = parser.parse_args()
    
    if args.command == "env":
        check_env_vars()
    elif args.command == "data":
        asyncio.run(check_data())
    elif args.command == "services":
        async def check_services():
            await check_redis()
            await check_mongo()
            await check_fastapi()
            await check_collect_service()
        asyncio.run(check_services())
    else:
        asyncio.run(run_full_diagnose())


if __name__ == "__main__":
    main()
