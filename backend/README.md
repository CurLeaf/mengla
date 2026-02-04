# Backend 结构

```
backend/
├── core/              # 核心业务逻辑
│   ├── domain.py      # 数据采集核心逻辑
│   ├── client.py      # 采集服务客户端
│   ├── types.py       # 数据类型定义
│   └── queue.py       # 爬取队列管理
│
├── infra/             # 基础设施
│   ├── database.py    # 数据库连接
│   ├── cache.py       # 三级缓存
│   ├── resilience.py  # 重试/熔断
│   ├── logger.py      # 结构化日志
│   ├── metrics.py     # 指标收集
│   └── alerting.py    # 告警规则
│
├── utils/             # 工具函数
│   ├── config.py      # 配置中心
│   ├── period.py      # 时间周期工具
│   ├── category.py    # 类目工具
│   └── dashboard.py   # 面板配置
│
├── tools/             # 独立工具
│   ├── backfill.py    # 数据补录
│   ├── mock_source.py # 模拟数据源
│   ├── diagnose.py    # 诊断工具
│   └── clear_storage.py # 清理存储
│
├── main.py            # FastAPI 入口
├── scheduler.py       # 定时任务
├── category.json      # 类目配置
├── panel_config.json  # 面板配置
├── requirements.txt   # 依赖清单
└── Dockerfile         # Docker 配置
```

## 使用方式

```bash
# 启动 FastAPI 服务
uvicorn backend.main:app --reload

# 诊断
python -m backend.tools.diagnose

# 数据补录
python -m backend.tools.backfill single --days 30
python -m backend.tools.backfill queue create --years 1
python -m backend.tools.backfill queue worker --workers 3

# 模拟数据源
python -m uvicorn backend.tools.mock_source:app --port 3001

# 清理存储
python -m backend.tools.clear_storage
```
