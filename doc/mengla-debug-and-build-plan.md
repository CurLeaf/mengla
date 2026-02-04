# 萌拉数据加载调试与项目构建规划

## 一、项目模块划分

- **Backend**：根目录下 `backend/`，Python FastAPI，端口 8000，提供 `/api/mengla/*` 等接口。
- **Frontend**：根目录下 `frontend/`，包名 `industry-monitor-frontend`，Vite + React，端口 5173，通过 `VITE_API_BASE_URL` 或默认 `http://localhost:8000` 请求后端。

两者同属一个仓库，通过根目录 `package.json` 的 `dev` 脚本或 VS Code 任务同时启动，视为一个项目的两个模块。

---

## 二、如何构建与运行

- **安装**：在仓库根目录执行一次 `pnpm install`（会安装根依赖与 workspace 内 frontend）。
- **开发**：根目录执行 `pnpm dev`，会并发启动后端（uvicorn）和前端（Vite）；或使用 VS Code 任务「Dev: Start All (hot)」先起 Docker（Mongo+Redis）、再起后端与前端。
- **注意**：后端需 Python 环境并安装 `backend/requirements.txt`；若用「Dev: Start All」，需先启动 `docker/dev/docker-compose.yml` 中的 Mongo 与 Redis。
- **前端单独构建**：根目录 `pnpm build` 仅构建 frontend；后端无单独“构建”步骤，直接运行即可。

---

## 三、服务端调试与跟踪（针对 MengLa 加载失败/长时间加载）

- **请求入口**：所有 MengLa 数据经 `POST /api/mengla/query`（及 high/hot/chance/industry-view/industry-trend）进入，由 `query_mengla_domain` 完成逻辑，可能调用采集服务（COLLECT_SERVICE_URL）、Redis、Mongo。
- **建议添加的调试点**：
  - 请求进入：记录 action、catId、dateType、timest、starRange、endRange 及请求时间。
  - 调用采集服务前/后：记录是否走缓存、是否发起 HTTP、目标 URL、耗时。
  - 轮询 Redis/等待 webhook：记录轮询次数、已等待时长、是否超时。
  - 返回前：记录 source（cache/mongo/collect）、响应体大小或条数、总耗时。
  - 异常分支：对超时、连接错误、5xx 记录完整异常类型与 message，便于与前端报错对应。
- **长时间加载与失败**：后端当前有 504（query timeout）、503（采集不可达）、500（其它异常）；前端有 30 秒 fetch 超时。调试时需区分：后端是否已收到请求、是否卡在采集/Redis/数据库、是否在超时前返回。

---

## 四、Docker 下 Redis / MongoDB 日志追踪

Redis、Mongo 使用 Docker 时，可通过容器日志与 Redis MONITOR 对照后端行为。详见 **doc/docker-logs-and-tracing.md**。根目录提供：`pnpm docker:up`、`pnpm docker:logs`、`pnpm docker:logs:redis`、`pnpm docker:logs:mongo`。

---

## 五、同时查看后端与前端信息

- **后端**：看启动 uvicorn 的终端输出；若需更细粒度，可配置 Python logging 将 `mengla-backend`、`mengla-domain`、`mengla_client` 等 logger 输出到控制台并设置 DEBUG 或 INFO。
- **前端**：浏览器打开前端页面（如 5173），使用开发者工具 Network 查看对 8000 端口的请求（状态码、耗时、请求/响应体）；Console 查看前端打印的错误或 `[MengLa] 请求失败` 等日志。
- **对照方式**：用一次操作触发一条 MengLa 请求，在后端日志中根据时间戳与 action/catId 找到对应请求，在 Network 中找到同一请求，对比状态码、响应 body 与后端日志中的 source 与异常信息，即可判断是网络、超时、还是后端逻辑/依赖问题。

---

## 六、架构如何调整

- **定位**：本仓库为单 repo、双模块——backend（Python）与 frontend（Node）并列，根目录只做编排，不写业务。
- **模块边界**：backend 仅暴露 HTTP API（含 `/api/mengla/*`），前端通过环境变量或默认 `http://localhost:8000` 访问；除 CORS 与接口契约外，两者无构建期耦合。
- **脚本统一**：根目录保留一条主入口 `pnpm dev`（并发起 backend + frontend）；可增加 `dev:backend`、`dev:frontend` 便于单模块调试；`build` 只构建 frontend，backend 无需构建步骤。
- **Workspace**：pnpm workspace 仅包含 `frontend`；backend 由 Python 管理，不加入 packages，在文档与脚本中显式称为「backend 模块」即可。
- **开发体验**：VS Code 任务与根目录 `pnpm dev` 二选一、行为一致（都是先依赖服务 Docker 可选、再起两模块）；前端任务里启动 frontend 时建议用 `pnpm --filter industry-monitor-frontend dev` 与根脚本一致，避免 cwd 和脚本语义分歧。
- **扩展**：若以后新增模块（如其它前端或 BFF），继续在根目录下新建目录，并在根 `package.json` 的 dev/build 中显式列出；backend 与 frontend 的目录名与端口约定保持不变，便于文档与脚本复用。

---

## 七、后续实施顺序建议

1. 在 backend 为 MengLa 相关接口与 `query_mengla_domain` 增加上述调试日志（不改业务逻辑）。
2. 确认根目录 `pnpm dev` 与 VS Code 任务能稳定同时起 backend + frontend，且前端能访问 8000。
3. 复现“无法加载”或“长时间加载”场景，同时抓后端日志与前端 Network/Console，按时间戳与 action 对照分析。
4. 若需更长时间复现，可临时调大前端超时或后端 MENGLA_TIMEOUT_SECONDS，并在日志中记录超时发生点。
