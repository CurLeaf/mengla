# MengLa 数据采集系统 — 重构修复方案总览

> **项目定位：** 外部数据采集与管理系统，为内部业务系统提供行业数据  
> **文档生成日期：** 2026-02-07  
> **状态标记：** 🔴 紧急 | 🟡 重要 | 🟢 改进  

---

## 模块索引

共 **4 个模块**，按文件归属严格划分，**各模块涉及的文件完全不交叉**，可由不同人员/团队独立并行推进。

| 模块 | 文档 | 负责角色 | 优先级 | 分支名 | 预估工时 |
|------|------|----------|--------|--------|----------|
| **1 — 安全加固与运维基础设施** | [MODULE_1_INFRA.md](refactor/MODULE_1_INFRA.md) | 安全/运维/DevOps | 🔴 紧急 | `refactor/module-1-infra` | 4-5 天 |
| **2 — 后端架构重构** | [MODULE_2_BACKEND.md](refactor/MODULE_2_BACKEND.md) | 后端开发 | 🟡 重要 | `refactor/module-2-backend` | 6-8 天 |
| **3 — 前端重构与体验优化** | [MODULE_3_FRONTEND.md](refactor/MODULE_3_FRONTEND.md) | 前端开发 | 🟡 重要 | `refactor/module-3-frontend` | 5-6 天 |
| **4 — 测试体系建设** | [MODULE_4_TESTING.md](refactor/MODULE_4_TESTING.md) | 全员 | 🟡 重要 | `refactor/module-4-testing` | 持续推进 |

---

## 文件归属分配（零交叉保证）

```
┌─────────────────────────────────────────────────────────────────┐
│ 模块 1 — 安全与运维                                              │
│                                                                  │
│  backend/core/auth.py          (JWT/bcrypt/限流)                 │
│  backend/Dockerfile            (多阶段/非root/HealthCheck)       │
│  frontend/Dockerfile           (HealthCheck)                     │
│  docker/docker-compose.yml     (端口/Health/资源限制/备份)        │
│  docker/nginx/nginx.conf       (安全头/SSL/请求限制)              │
│  docker/.env.production        (环境变量补全)                     │
│  docker/release.sh             (镜像扫描)                        │
│  mengla-service.ts             (移除硬编码密钥)                   │
│  .env.example                  (新建)                            │
│  .github/workflows/ci.yml     (新建)                             │
├─────────────────────────────────────────────────────────────────┤
│ 模块 2 — 后端架构                                                │
│                                                                  │
│  backend/main.py               (路由拆分/CORS/异常处理)          │
│  backend/api/                  (新建 — 路由模块)                  │
│  backend/middleware/           (新建 — 错误中间件)                │
│  backend/scheduler.py          (统一采集/配置化/重试)             │
│  backend/core/domain.py        (并发锁/去重安全)                  │
│  backend/core/queue.py         (原子claim)                       │
│  backend/infra/cache.py        (计数器安全)                       │
│  backend/infra/alerting.py     (有界历史)                         │
│  backend/infra/metrics.py      (自动过期)                         │
│  backend/utils/config.py       (间隔配置/环境校验)                │
├─────────────────────────────────────────────────────────────────┤
│ 模块 3 — 前端重构                                                │
│                                                                  │
│  frontend/src/**               (所有前端源码)                     │
│  frontend/package.json         (添加 sonner 依赖)                │
├─────────────────────────────────────────────────────────────────┤
│ 模块 4 — 测试体系                                                │
│                                                                  │
│  tests/                        (新建 — 整个测试目录)              │
│  requirements-dev.txt          (新建)                            │
│  pyproject.toml                (新建)                            │
│  frontend/vitest.config.ts     (新建)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 各模块核心内容

### 模块 1 — 安全加固与运维基础设施（15 项）
移除硬编码密钥、JWT Secret 强制配置、密码 bcrypt 哈希、数据库端口内网化、Nginx 安全头与 SSL、
容器非 root 运行、登录频率限制、生产环境变量补全、CI/CD 流水线、Docker Health Check、
容器资源限制、数据库备份策略、后端多阶段 Dockerfile、Nginx 请求限制

### 模块 2 — 后端架构重构（17 项）
main.py 路由拆分为 6 个模块、统一错误响应格式、统一异常处理中间件、CORS 环境变量化、
Pydantic 模型集中管理、IN_FLIGHT 并发锁、后台任务安全化、Queue 原子 claim、
缓存计数器安全化、告警历史有界化、指标自动过期、去重删除安全化、
4 个采集函数合并为 1 个、采集间隔配置化、定时任务失败重试、启动环境变量校验

### 模块 3 — 前端重构与体验优化（13 项）
三排名页面提取公共 RankPage 组件、PeriodDataManager 拆分子组件、useCategoryState 改用 React Query、
sync-task-api 修复 authFetch、清理废弃组件、常量集中管理、alert() 替换为 sonner Toast、
SPA 路由跳转修复、全局 ErrorBoundary、路由级代码分割、ARIA 无障碍标签、
React.memo 优化、确认弹窗改进

### 模块 4 — 测试体系建设（5 项）
pytest + vitest 框架搭建、后端 Mock fixture（mongomock/fakeredis）、
认证/缓存/周期单元测试、API 集成测试、前端组件测试

---

## 模块依赖关系

```
         ┌─────────────────┐
         │    模块 1        │  安全与运维（无依赖，最先启动）
         │    🔴 紧急       │
         └───────┬─────────┘
                 │
       ┌─────────┼──────────┐
       ▼                    ▼
┌─────────────┐   ┌─────────────┐
│   模块 2     │   │   模块 3     │   ← 可完全并行
│   后端架构   │   │   前端重构   │
│   🟡 重要    │   │   🟡 重要    │
└──────┬──────┘   └─────────────┘
       │
       ▼
┌─────────────┐
│   模块 4     │   测试（框架可提前搭建，用例在 2/3 之后编写）
│   持续推进   │
└─────────────┘
```

---

## 推荐执行顺序

| 阶段 | 模块 | 并行方式 | 预估周期 |
|------|------|----------|----------|
| **第一阶段** | 模块 1（安全与运维） | 独立 | 第 1 周 |
| **第二阶段** | 模块 2 + 模块 3 + 模块 4 框架搭建 | 三线并行 | 第 2-3 周 |
| **第三阶段** | 模块 4 用例补全 | 独立 | 第 3-4 周 |

---

## 协作规范

1. **分支策略：** 每个模块独立分支（见上表），文件不交叉，零合并冲突
2. **向后兼容：** 模块 2 路由拆分时保持 API 路径不变，避免破坏前端调用
3. **灰度发布：** 模块 1 的 Docker 改动应先在 staging 环境验证
4. **文档同步：** 每个模块完成后更新对应文档中的检查清单
5. **Code Review：** 安全相关（模块 1）改动必须双人 Review
6. **合并顺序：** 模块 1 → （模块 2 / 模块 3 并行）→ 模块 4
