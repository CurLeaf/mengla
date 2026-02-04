"""
补录脚本入口（重定向到 backend.backfill）

运行方法：
  python -m backend.scripts.backfill single --days 30
  python -m backend.scripts.backfill queue create --years 1
  python -m backend.scripts.backfill queue worker --workers 3
  python -m backend.scripts.backfill queue status
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.backfill import main

if __name__ == "__main__":
    main()
