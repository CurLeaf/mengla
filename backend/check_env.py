"""
检查环境变量是否正确加载
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).resolve().parent / ".env"
print(f"加载 .env 文件: {env_path}")
print(f"文件存在: {env_path.exists()}")
print()

load_dotenv(env_path)

# 检查关键环境变量
print("=" * 80)
print("环境变量检查")
print("=" * 80)

vars_to_check = [
    "MONGO_URI",
    "MONGO_DB",
    "REDIS_URI",
    "COLLECT_SERVICE_URL",
    "COLLECT_SERVICE_API_KEY",
    "APP_BASEURL",
    "MENGLA_WEBHOOK_URL",
]

for var in vars_to_check:
    value = os.getenv(var)
    if value:
        # 隐藏 API Key 的部分内容
        if "KEY" in var or "SECRET" in var:
            display_value = value[:20] + "..." if len(value) > 20 else value
        else:
            display_value = value
        print(f"✓ {var:30s} = {display_value}")
    else:
        print(f"✗ {var:30s} = (未设置)")

print("=" * 80)

# 特别检查 MENGLA_WEBHOOK_URL
webhook_url = os.getenv("MENGLA_WEBHOOK_URL")
if webhook_url:
    print(f"\n✓ Webhook URL 已配置: {webhook_url}")
    if "localhost" in webhook_url or "127.0.0.1" in webhook_url:
        print("  ⚠ 警告：使用 localhost，远程采集服务无法访问！")
    else:
        print("  ✓ 使用公网地址，远程采集服务可以访问")
else:
    print("\n✗ MENGLA_WEBHOOK_URL 未配置")
    print("  将使用 APP_BASEURL + /api/webhook/mengla-notify")
    app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
    print(f"  实际 webhook: {app_base}/api/webhook/mengla-notify")
    print("  ⚠ 警告：远程采集服务无法访问 localhost！")
