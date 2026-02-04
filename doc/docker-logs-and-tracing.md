# Docker 下 Redis / MongoDB 日志追踪与排查

## 一、使用本仓库 Docker 时的约定

- 编排文件：`docker/dev/docker-compose.yml`
- 容器名：`mengla-dev-redis`、`mengla-dev-mongodb`
- 宿主机端口：MongoDB `27017`，Redis **6380**（容器内 6379）

后端跑在宿主机时，需让应用连到 Docker 暴露的端口，例如在项目根目录建 `.env`：

- `MONGO_URI=mongodb://localhost:27017`
- `MONGO_DB=industry_monitor`
- `REDIS_URI=redis://localhost:6380/0`

启动后端后，控制台会打出实际使用的 Mongo/Redis 连接地址（密码已脱敏），可与 Docker 端口对照。

---

## 二、查看 Docker 日志

在仓库根目录执行（需已 `docker compose up -d`）：

| 命令 | 说明 |
|------|------|
| `pnpm docker:logs` | 同时跟踪 Redis + MongoDB 容器日志 |
| `pnpm docker:logs:redis` | 仅 Redis 容器 |
| `pnpm docker:logs:mongo` | 仅 MongoDB 容器 |

或直接用 Docker：

- 所有服务：`docker compose -f docker/dev/docker-compose.yml logs -f`
- Redis：`docker compose -f docker/dev/docker-compose.yml logs -f redis`
- MongoDB：`docker compose -f docker/dev/docker-compose.yml logs -f mongodb`

Redis 默认只打连接/断线等少量日志；要看每次命令需用下面「实时看 Redis 命令」。

---

## 三、实时看 Redis 命令（排查 webhook 是否写入）

采集结果经 webhook 写入 Redis 的 key：`mengla:exec:{executionId}`；后端轮询该 key 直到有值或超时。

在宿主机执行：

```bash
docker exec -it mengla-dev-redis redis-cli MONITOR
```

会持续打印当前 Redis 收到的每条命令（SET/GET 等）及 key 名。触发一次萌拉请求后：

- 若能看到 `SET mengla:exec:xxx`，说明 webhook 已回调并写入，可再查后端是否连的是同一 Redis（端口 6380）。
- 若一直只有 `GET mengla:exec:xxx` 没有对应 `SET`，说明 webhook 未到或写到了别的 Redis。

---

## 四、常见问题与处理

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 后端报 Redis/Mongo 连接失败 | Docker 未起或端口不对 | `pnpm docker:up`，确认 `.env` 里 `REDIS_URI=redis://localhost:6380/0`、`MONGO_URI=mongodb://localhost:27017` |
| 前端一直“加载萌拉数据失败”，后端在轮询 | webhook 未回调或回调到错误地址 | 采集服务需能访问到后端的 webhook URL。若后端在本地，设 `APP_BASEURL` 或 `MENGLA_WEBHOOK_URL` 为可被采集服务访问的地址（如内网/公网 URL），或先依赖 Mongo/Redis 已有缓存 |
| Redis MONITOR 里只有 GET 没有 SET | 采集服务未回调或回调到别的 Redis | 确认采集侧配置的 webhook 指向当前后端，且后端 `REDIS_URI` 指向 Docker Redis（6380） |
| Mongo 有数据但接口仍慢/超时 | 命中 Mongo 的请求会直接返回；未命中的走采集+webhook | 看后端日志 `[MengLa] response ... source=mongo` 表示命中；`collect_start` 后长时间无 `collect_done` 多为等 webhook |

---

## 五、启动顺序建议

1. 先起 Docker：`pnpm docker:up`（或 `docker compose -f docker/dev/docker-compose.yml up -d`）
2. 再起应用：`pnpm dev`
3. 需排查时开另一终端：`pnpm docker:logs` 或 `docker exec -it mengla-dev-redis redis-cli MONITOR`
