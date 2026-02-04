"""
模拟数据源服务入口

启动方式：
  python -m backend.scripts.mock_source
  
或者直接使用原模块：
  python -m uvicorn backend.mock_data_source:app --port 3001 --reload
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def main():
    import uvicorn
    print("=" * 60)
    print("启动模拟数据源服务")
    print("=" * 60)
    print("服务地址: http://localhost:3001")
    print()
    print("API 端点:")
    print("  GET  /api/status/processing  - 获取处理状态")
    print("  GET  /api/status/queue       - 获取队列状态")
    print("  GET  /health                 - 健康检查")
    print("=" * 60)
    print()
    
    uvicorn.run(
        "backend.mock_data_source:app",
        host="0.0.0.0",
        port=3001,
        reload=True,
    )


if __name__ == "__main__":
    main()
