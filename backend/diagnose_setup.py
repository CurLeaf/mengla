"""
诊断脚本：检查测试环境是否正确配置
"""
import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    print("⚠ python-dotenv 未安装，跳过 .env 加载")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_env_vars():
    """检查环境变量"""
    print("\n" + "=" * 80)
    print("1. 环境变量检查")
    print("=" * 80)
    
    required_vars = {
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DB": "industry_monitor",
        "REDIS_URI": "redis://localhost:6380/0",
        "COLLECT_SERVICE_URL": "https://extract.b.nps.qzsyzn.com",
        "COLLECT_SERVICE_API_KEY": "",
        "APP_BASEURL": "http://localhost:8000",
    }
    
    all_ok = True
    for var, default in required_vars.items():
        value = os.getenv(var, default)
        if not value:
            print(f"✗ {var}: 未设置")
            all_ok = False
        elif var == "COLLECT_SERVICE_API_KEY":
            # 隐藏 API Key
            masked = value[:10] + "..." + value[-10:] if len(value) > 20 else "***"
            print(f"✓ {var}: {masked}")
        else:
            print(f"✓ {var}: {value}")
    
    webhook_url = os.getenv("MENGLA_WEBHOOK_URL")
    if webhook_url:
        print(f"⚠ MENGLA_WEBHOOK_URL: {webhook_url}")
        print(f"  提示: 使用外部 webhook，请确保该服务可访问本地 Redis (localhost:6380)")
    else:
        print(f"✓ MENGLA_WEBHOOK_URL: 未设置（使用本地 webhook）")
    
    return all_ok


async def check_redis():
    """检查 Redis 连接"""
    print("\n" + "=" * 80)
    print("2. Redis 连接检查")
    print("=" * 80)
    
    try:
        from backend import database
        redis_uri = os.getenv("REDIS_URI", "redis://localhost:6380/0")
        print(f"连接: {redis_uri}")
        
        await database.connect_to_redis(redis_uri)
        
        if database.redis_client is None:
            print("✗ Redis 连接失败")
            return False
        
        # 测试读写
        test_key = "mengla:test:diagnose"
        await database.redis_client.set(test_key, "ok", ex=10)
        value = await database.redis_client.get(test_key)
        
        if value == "ok":
            print("✓ Redis 连接成功，读写正常")
            await database.redis_client.delete(test_key)
            await database.disconnect_redis()
            return True
        else:
            print("✗ Redis 读写失败")
            await database.disconnect_redis()
            return False
            
    except Exception as e:
        print(f"✗ Redis 连接失败: {e}")
        print(f"  提示: 请确保 Redis 正在运行")
        print(f"  启动命令: redis-server --port 6380")
        return False


async def check_mongo():
    """检查 MongoDB 连接"""
    print("\n" + "=" * 80)
    print("3. MongoDB 连接检查")
    print("=" * 80)
    
    try:
        from backend import database
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        mongo_db = os.getenv("MONGO_DB", "industry_monitor")
        print(f"连接: {mongo_uri}/{mongo_db}")
        
        await database.connect_to_mongo(mongo_uri, mongo_db)
        
        if database.mongo_db is None:
            print("✗ MongoDB 连接失败")
            return False
        
        # 测试读写
        test_coll = database.mongo_db["_test_diagnose"]
        await test_coll.insert_one({"test": "ok"})
        doc = await test_coll.find_one({"test": "ok"})
        await test_coll.delete_many({})
        
        if doc:
            print("✓ MongoDB 连接成功，读写正常")
            await database.disconnect_mongo()
            return True
        else:
            print("✗ MongoDB 读写失败")
            await database.disconnect_mongo()
            return False
            
    except Exception as e:
        print(f"✗ MongoDB 连接失败: {e}")
        print(f"  提示: 请确保 MongoDB 正在运行")
        print(f"  启动命令: mongod")
        return False


async def check_fastapi():
    """检查 FastAPI 服务"""
    print("\n" + "=" * 80)
    print("4. FastAPI 服务检查")
    print("=" * 80)
    
    try:
        import httpx
        app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
        health_url = f"{app_base}/health"
        print(f"检查: {health_url}")
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(health_url)
            
        if resp.status_code == 200:
            print("✓ FastAPI 服务正在运行")
            print(f"  Webhook URL: {app_base}/api/webhook/mengla-notify")
            return True
        else:
            print(f"✗ FastAPI 服务响应异常: {resp.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ FastAPI 服务未运行: {e}")
        print(f"  提示: 请在另一个终端启动 FastAPI")
        print(f"  启动命令: uvicorn backend.main:app --reload --port 8000")
        print(f"  或使用脚本: .\\start_test.ps1 (PowerShell) 或 start_test.bat (CMD)")
        return False


async def check_collect_service():
    """检查采集服务连接"""
    print("\n" + "=" * 80)
    print("5. 采集服务连接检查")
    print("=" * 80)
    
    try:
        import httpx
        base_url = os.getenv("COLLECT_SERVICE_URL", "http://localhost:3001")
        api_key = os.getenv("COLLECT_SERVICE_API_KEY", "")
        url = f"{base_url}/api/managed-tasks"
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
            data = resp.json()
            tasks = data.get("data", {}).get("tasks", [])
            print(f"✓ 采集服务连接成功，共 {len(tasks)} 个托管任务")
            
            # 查找"萌啦数据采集"任务
            mengla_task = None
            for task in tasks:
                if task.get("name") == "萌啦数据采集":
                    mengla_task = task
                    break
            
            if mengla_task:
                print(f"✓ 找到"萌啦数据采集"任务 (ID: {mengla_task.get('id')})")
                return True
            else:
                print(f"✗ 未找到"萌啦数据采集"任务")
                print(f"  可用任务: {', '.join(t.get('name', '?') for t in tasks)}")
                return False
        else:
            print(f"✗ 采集服务响应异常: {resp.status_code}")
            print(f"  响应: {resp.text[:200]}")
            return False
            
    except Exception as e:
        print(f"✗ 采集服务连接失败: {e}")
        print(f"  提示: 请检查网络连接、VPN 或防火墙设置")
        return False


async def main():
    print("=" * 80)
    print("测试环境诊断")
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
    
    # 总结
    print("\n" + "=" * 80)
    print("诊断总结")
    print("=" * 80)
    
    all_ok = all(results.values())
    
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"{status} {name.upper()}")
    
    print("=" * 80)
    
    if all_ok:
        print("\n✓ 所有检查通过！可以运行测试脚本：")
        print("  python -m backend.test_one_month")
    else:
        print("\n✗ 部分检查失败，请根据上述提示修复问题")
        print("\n常见问题：")
        print("  1. Redis 未运行 → redis-server --port 6380")
        print("  2. MongoDB 未运行 → mongod")
        print("  3. FastAPI 未运行 → uvicorn backend.main:app --reload --port 8000")
        print("  4. 采集服务不可达 → 检查网络、VPN")
    
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
