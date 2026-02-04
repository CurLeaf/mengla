"""
采集所有一级类目的近一年数据
从 类目.json 读取所有一级类目（如：住宅和花园、服装、美容和卫生等）
为每个类目采集近一年的数据（包括日、月、季、年粒度）
"""
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).resolve().parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import database
from backend.category_utils import get_top_level_cat_ids, get_all_categories
from backend.mengla_domain import query_mengla_domain
from backend.mengla_indexes import ensure_mengla_indexes
from backend.period_utils import period_keys_in_range


async def collect_all_categories_one_year():
    """采集所有一级类目的近一年数据"""
    print("=" * 80)
    print("采集所有一级类目的近一年数据")
    print("=" * 80)
    
    # 1. 连接数据库
    print("\n[1/6] 连接数据库...")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB", "industry_monitor")
    redis_uri = os.getenv("REDIS_URI", "redis://localhost:6380/0")
    
    await database.connect_to_mongo(mongo_uri, mongo_db_name)
    await database.connect_to_redis(redis_uri)
    print("✓ 数据库连接成功")
    
    # 检查 webhook 配置
    webhook_url = os.getenv("MENGLA_WEBHOOK_URL")
    if webhook_url:
        print(f"\n✓ 使用外部 Webhook: {webhook_url}")
        print("  外部 webhook 服务需要能访问本地 Redis (localhost:6380)")
    else:
        app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
        local_webhook = f"{app_base}/api/webhook/mengla-notify"
        print(f"\n⚠ 使用本地 Webhook: {local_webhook}")
        print("  " + "=" * 76)
        print("  ⚠ 重要：必须先启动 FastAPI 服务才能接收 webhook 回调！")
        print("  " + "=" * 76)
        print("  请在另一个终端运行：")
        print(f"    uvicorn backend.main:app --reload --port 8000")
        print("  " + "=" * 76)
        
        # 检查 FastAPI 是否运行
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{app_base}/health")
                if resp.status_code == 200:
                    print("  ✓ FastAPI 服务已运行，可以继续")
                else:
                    print("  ✗ FastAPI 服务响应异常")
                    print("  建议：先启动 FastAPI 再运行此脚本")
        except Exception:
            print("  ✗ FastAPI 服务未运行")
            print("  建议：先启动 FastAPI 再运行此脚本")
            print("\n是否继续？(y/n): ", end="")
            choice = input().strip().lower()
            if choice != 'y':
                print("已取消")
                await database.disconnect_redis()
                await database.disconnect_mongo()
                return
        print()
    
    # 2. 确保唯一索引存在
    print("\n[2/6] 创建唯一索引...")
    await ensure_mengla_indexes()
    print("✓ 唯一索引已创建（防止数据重复）")
    
    # 3. 加载所有一级类目
    print("\n[3/6] 加载所有一级类目...")
    try:
        all_categories = get_all_categories()
        cat_ids = get_top_level_cat_ids()
        
        print(f"✓ 成功加载 {len(cat_ids)} 个一级类目")
        print("\n一级类目列表：")
        for i, cat in enumerate(all_categories[:10], 1):  # 显示前10个
            cat_name_cn = cat.get("catNameCn", "")
            cat_name_ru = cat.get("catName", "")
            cat_id = cat.get("catId", "")
            print(f"  {i}. {cat_name_cn} ({cat_name_ru}) - ID: {cat_id}")
        
        if len(all_categories) > 10:
            print(f"  ... 还有 {len(all_categories) - 10} 个类目")
        
    except Exception as e:
        print(f"✗ 加载类目失败: {e}")
        await database.disconnect_redis()
        await database.disconnect_mongo()
        return
    
    # 4. 计算时间范围（近一年）
    print("\n[4/6] 计算时间范围...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 近一年
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    print(f"  起始日期: {start_str}")
    print(f"  结束日期: {end_str}")
    
    # 采集日、月、季、年粒度数据
    granularities = ["day", "month", "quarter", "year"]
    # 普通接口：逐个时间点请求
    normal_actions = ["high", "hot", "chance", "industryViewV2"]
    # 趋势接口：只请求一次范围
    range_actions = ["industryTrendRange"]
    
    # 计算任务量
    total_tasks = 0
    for gran in granularities:
        keys = period_keys_in_range(gran, start_str, end_str)
        print(f"  {gran}: {len(keys)} 个时间点")
        # 普通接口：类目数 × 接口数 × 时间点数
        total_tasks += len(cat_ids) * len(normal_actions) * len(keys)
    
    # 趋势接口：类目数 × 粒度数 × 1（只请求一次范围）
    total_tasks += len(cat_ids) * len(granularities) * len(range_actions)
    
    print(f"\n  总任务数: {total_tasks:,} 个")
    print(f"  - 普通接口（逐时间点）: {len(cat_ids) * len(normal_actions) * sum(len(period_keys_in_range(g, start_str, end_str)) for g in granularities):,} 个")
    print(f"  - 趋势接口（范围请求）: {len(cat_ids) * len(granularities) * len(range_actions):,} 个")
    print(f"  预计耗时: {total_tasks * 90 / 3600:.2f} 小时（按每任务平均1.5分钟计算）")
    print(f"  说明: 每个新任务间隔 1-2 分钟，模仿真人操作")
    
    # 5. 用户确认
    print("\n[5/6] 确认采集...")
    print("  即将为以下类目采集数据：")
    for cat in all_categories[:5]:
        print(f"    - {cat.get('catNameCn', '')} (ID: {cat.get('catId', '')})")
    if len(all_categories) > 5:
        print(f"    ... 还有 {len(all_categories) - 5} 个类目")
    
    print("\n是否开始采集？(y/n): ", end="")
    choice = input().strip().lower()
    if choice != 'y':
        print("已取消")
        await database.disconnect_redis()
        await database.disconnect_mongo()
        return
    
    # 6. 开始采集
    print("\n[6/6] 开始采集数据...")
    print("=" * 80)
    
    completed = 0
    failed = 0
    skipped = 0
    
    try:
        for i, cat_id in enumerate(cat_ids, 1):
            # 获取类目名称
            cat_name = ""
            for cat in all_categories:
                if str(cat.get("catId")) == str(cat_id):
                    cat_name = cat.get("catNameCn", cat.get("catName", ""))
                    break
            
            print(f"\n[{i}/{len(cat_ids)}] 处理类目: {cat_name} (ID: {cat_id})")
            
            # 1. 处理普通接口（逐时间点请求）
            for action in normal_actions:
                print(f"  接口: {action}")
                
                for gran in granularities:
                    keys = period_keys_in_range(gran, start_str, end_str)
                    
                    for period_key in keys:
                        try:
                            # 调用采集函数（会自动检查MongoDB/Redis，避免重复）
                            print(f"    → {gran}/{period_key} - 开始采集...")
                            
                            data, source = await query_mengla_domain(
                                action=action,
                                product_id="",
                                catId=cat_id,
                                dateType=gran,
                                timest=period_key,
                                starRange="",
                                endRange="",
                                extra=None,
                                timeout_seconds=120,  # 2分钟超时
                            )
                            
                            completed += 1
                            
                            if source == "mongo":
                                skipped += 1
                                print(f"    ✓ {gran}/{period_key} - 已存在（跳过）")
                            elif source == "redis":
                                print(f"    ✓ {gran}/{period_key} - Redis缓存命中")
                            else:
                                print(f"    ✓ {gran}/{period_key} - 采集成功（新数据）")
                                wait_seconds = random.uniform(60, 120)  # 1-2 分钟
                                wait_minutes = wait_seconds / 60
                                print(f"    ⏳ 等待 {wait_minutes:.1f} 分钟后继续下一个任务...")
                                await asyncio.sleep(wait_seconds)
                            
                            if completed % 10 == 0:
                                print(f"\n    📊 进度: 完成 {completed}/{total_tasks}, 失败 {failed}, 跳过 {skipped}\n")
                            
                        except TimeoutError as e:
                            failed += 1
                            print(f"    ✗ {gran}/{period_key} - 超时: {e}")
                            print(f"       提示: 请确保 FastAPI 服务正在运行以接收 webhook")
                        except Exception as e:
                            failed += 1
                            print(f"    ✗ {gran}/{period_key} - 失败: {e}")
            
            # 2. 处理趋势接口（范围请求）
            for action in range_actions:
                print(f"  接口: {action} (范围请求)")
                
                for gran in granularities:
                    try:
                        print(f"    → {gran}/{start_str}~{end_str} - 开始采集范围数据...")
                        
                        data, source = await query_mengla_domain(
                            action=action,
                            product_id="",
                            catId=cat_id,
                            dateType=gran,
                            timest="",  # 范围请求不需要单个时间点
                            starRange=start_str,
                            endRange=end_str,
                            extra=None,
                            timeout_seconds=120,
                        )
                        
                        completed += 1
                        
                        if source == "mongo":
                            skipped += 1
                            print(f"    ✓ {gran} 范围数据 - 已存在（跳过）")
                        elif source == "redis":
                            print(f"    ✓ {gran} 范围数据 - Redis缓存命中")
                        else:
                            print(f"    ✓ {gran} 范围数据 - 采集成功（新数据）")
                            wait_seconds = random.uniform(60, 120)  # 1-2 分钟
                            wait_minutes = wait_seconds / 60
                            print(f"    ⏳ 等待 {wait_minutes:.1f} 分钟后继续下一个任务...")
                            await asyncio.sleep(wait_seconds)
                        
                        if completed % 10 == 0:
                            print(f"\n    📊 进度: 完成 {completed}/{total_tasks}, 失败 {failed}, 跳过 {skipped}\n")
                        
                    except TimeoutError as e:
                        failed += 1
                        print(f"    ✗ {gran} 范围数据 - 超时: {e}")
                    except Exception as e:
                        failed += 1
                        print(f"    ✗ {gran} 范围数据 - 失败: {e}")
        
        print("\n✓ 采集完成")
        
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断采集")
    except Exception as e:
        print(f"\n\n✗ 采集出错: {e}")
        import traceback
        traceback.print_exc()
    
    # 7. 关闭连接
    print("\n关闭数据库连接...")
    await database.disconnect_redis()
    await database.disconnect_mongo()
    print("✓ 已关闭连接")
    
    # 8. 统计结果
    print("\n" + "=" * 80)
    print("采集统计")
    print("=" * 80)
    print(f"  成功: {completed:,} 个")
    print(f"  失败: {failed:,} 个")
    print(f"  跳过（已存在）: {skipped:,} 个")
    print(f"  总计: {completed + failed:,} 个")
    print("=" * 80)
    print("\n现在可以检查 MongoDB，应该有 5 个集合：")
    print("  - mengla_high_reports (蓝海)")
    print("  - mengla_hot_reports (热销)")
    print("  - mengla_chance_reports (潜力)")
    print("  - mengla_view_reports (行业区间)")
    print("  - mengla_trend_reports (行业趋势)")
    print("\n每个集合都有唯一索引 (granularity, period_key, params_hash)")
    print("确保数据不会重复！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(collect_all_categories_one_year())
