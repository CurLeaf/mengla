# 项目评审报告

> **日期：** 2026-02-07  
> **范围：** 前端 + 后端 + 配置部署  
> **状态标记：** `[ ]` 待修复 · `[x]` 已完成

---

## 一、安全问题（紧急）

### 1.1 Webhook 缺少签名校验

- **文件：** `backend/api/webhook_routes.py`
- **问题：** `POST /api/webhook/mengla-notify` 端点没有任何认证，任何人都可以伪造回调注入数据
- **方案：** `ROUTE_REFACTOR_PLAN.md` 第 4.2 节已设计了 `require_webhook_signature` 依赖，需实现
- [ ] 在 `deps.py` 中实现 `require_webhook_signature`（HMAC-SHA256 签名校验）
- [ ] 在 webhook POST 路由上添加该依赖

### 1.2 登录接口缺少频率限制

- **文件：** `backend/api/auth_routes.py`、`backend/core/auth.py`
- **问题：** `check_login_rate()` 函数已实现但未在 `/login` 端点中调用，容易被暴力破解
- [ ] 在 `POST /api/auth/login` 路由中调用 `check_login_rate()`

### 1.3 JWT 永久 Token 风险

- **文件：** `backend/core/auth.py`
- **问题：** 支持 `permanent=True` 的永久 Token，默认过期时间 `24*365` 小时（1 年），Token 泄露风险高
- [ ] 移除永久 Token 或限制最大过期时间
- [ ] 设置合理的默认过期时间（如 7 天）

---

## 二、代码质量（高优先级）

### 2.1 前端 `API_BASE` 重复定义

- **问题：** `API_BASE` 在 5 个 service 文件中各自重复定义，只有 `sync-task-api.ts` 正确从 `constants.ts` 导入
- **涉及文件：**
  - `frontend/src/services/auth.ts`
  - `frontend/src/services/category-api.ts`
  - `frontend/src/services/mengla-api.ts`
  - `frontend/src/services/mengla-admin-api.ts`
  - `frontend/src/services/panel-config-api.ts`
- [ ] 统一从 `constants.ts` 导入 `API_BASE`，删除各文件中的重复定义

### 2.2 App.tsx 硬编码 API 路径

- **文件：** `frontend/src/App.tsx:72-93`
- **问题：** 采集按钮直接拼接 URL 调用 `authFetch`，未使用 service 层函数
- **示例：**

  ```typescript
  const resp = await authFetch(`${API_BASE}/api/panel/tasks/mengla_granular_force/run`, { method: "POST" });
  ```

- [ ] 提取到 `mengla-admin-api.ts` 中的 service 函数，保持 API 调用集中管理

### 2.3 scheduler.py 的异常捕获过宽

- **文件：** `backend/scheduler.py`（4 处）
- **问题：** `except BaseException` 会意外捕获 `SystemExit`，应使用更精确的写法
- [ ] 将 `except BaseException` 改为 `except (Exception, asyncio.CancelledError)`

### 2.4 调度任务无重叠防护

- **文件：** `backend/scheduler.py`
- **问题：** `run_period_collect()` 等任务未检查是否有同类型任务正在运行，可能重复启动
- [ ] 启动任务前调用 `get_running_task_by_task_id()` 检查，避免重叠执行

---

## 三、前端问题（中优先级）

### 3.1 TokenPage 使用数组索引作为 key

- **文件：** `frontend/src/pages/TokenPage.tsx:146`
- **问题：** 使用 `idx` 作为 React key，列表更新时可能出现渲染异常
- [ ] 改用稳定唯一标识（如 `item.token` 的哈希值）

### 3.2 `useMenglaQuery.ts` 使用 `any` 类型

- **文件：** `frontend/src/hooks/useMenglaQuery.ts:114`
- **问题：** `Record<string, any>` 类型不安全
- [ ] 替换为具体类型或 `unknown` 配合类型守卫

### 3.3 SyncTaskLogViewer 组件过大

- **文件：** `frontend/src/components/AdminCenter/SyncTaskLogViewer.tsx`（450+ 行）
- **问题：** 单文件包含 `StatusBadge`、`ProgressBar`、`TriggerBadge`、`ConfirmDialog` 等多个子组件
- [ ] 拆分为独立子组件文件，提高可维护性

---

## 四、后端问题（中优先级）

### 4.1 登录无审计日志

- **文件：** `backend/api/auth_routes.py`
- **问题：** `/login` 端点不记录登录尝试（成功/失败），缺乏安全审计
- [ ] 记录登录尝试日志，包含用户名和 IP 地址

### 4.2 sync_task_log 静默失败

- **文件：** `backend/core/sync_task_log.py`
- **问题：** `create_sync_task_log` 等函数在 `ObjectId` 无效或数据库不可用时静默返回 `None`，无 warning 日志
- [ ] 添加 `logger.warning()` 以便排查问题

### 4.3 兼容路由未清理

- **文件：** `backend/api/compat.py`、`backend/main.py`
- **问题：** 旧路径重定向（`/panel/*` → `/api/panel/*`）仍在注册，验证无误后应移除
- [ ] 确认前端所有调用已迁移到 `/api/*` 前缀
- [ ] 移除 `compat.py` 及 `main.py` 中的注册

### 4.4 `.env.production` 中 APP_BASEURL 未更新

- **文件：** `docker/.env.production`
- **问题：** `APP_BASEURL=http://localhost:8000` 仍是本地地址
- [ ] 部署时改为实际生产域名

---

## 五、配置与部署（中优先级）

### 5.1 Nginx 缺少 CSP 安全头

- **文件：** `docker/nginx/nginx.conf`
- **问题：** 已有 `X-Frame-Options`、`X-Content-Type-Options` 等头，但缺少 `Content-Security-Policy`
- [ ] 添加适当的 CSP 策略

### 5.2 面板配置 GET 无认证

- **文件：** `backend/api/panel_routes.py`
- **问题：** `GET /api/panel/config` 是公开端点，任何人可读取面板模块配置
- [ ] 确认是否需要认证保护，如果是前端初始化需要则可保持公开

### 5.3 已废弃的 `require_panel_admin` 未删除

- **文件：** `backend/api/deps.py`
- **问题：** 旧的 `require_panel_admin` 依赖已被 `require_admin` 替代，但代码仍保留
- [ ] 确认无引用后删除

---

## 六、改进建议（低优先级）

| # | 问题 | 文件 | 建议 |
|---|------|------|------|
| 6.1 | 调度器 cron 时间硬编码 | `scheduler.py:68-124` | 改为环境变量配置 |
| 6.2 | 环境变量缺少类型校验 | `utils/config.py` | `int()`/`float()` 调用加 try/except |
| 6.3 | 循环导入风险 | `panel_routes.py:140` | `_track_task` 从 `main.py` 导入，建议移到工具模块 |
| 6.4 | 请求体大小无限制 | `main.py` | 添加 FastAPI 请求大小限制中间件 |
| 6.5 | 队列 claim 竞态条件 | `core/queue.py:145-153` | 高并发时多 worker 可能领取重叠子任务 |
| 6.6 | MongoDB 操作缺少事务 | `core/domain.py:533-602` | 多文档操作应使用事务保证一致性 |

---

## 本次会话已完成的修复

| 项目 | 状态 |
|------|------|
| 侧边栏管理中心改为可折叠一级类目 | [x] 已完成 |
| 管理中心子路由（`/admin/:section`） | [x] 已完成 |
| scheduler `CancelledError` 未捕获 | [x] 已完成（待优化为更精确写法） |
| 启动时清理僵尸 RUNNING 日志 | [x] 已完成 |
| 同步日志时区转换问题 | [x] 已完成 |
