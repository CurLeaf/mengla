# 项目整体运行逻辑与运行流畅性分析

本文档描述萌拉数据采集项目从前端到后端、再到 Mongo/Redis/采集服务的完整运行逻辑，以及如何配置与优化才能达到「运行流畅、符合目标」的体验。

---

## 一、目标与约束

- **业务目标**：前端能稳定、较快地看到行业总览、蓝海/热销/潜力等萌拉数据；依赖 Mongo + Redis 做缓存，减少对采集服务的实时依赖，实现「有缓存则秒出、无缓存再异步拉取」的体验。
- **约束**：采集结果为异步（托管任务执行完成后通过 webhook 回写）；webhook 必须被采集服务能访问到的 URL，否则「无缓存」请求会一直等 webhook 直至超时。

---

## 二、整体数据流（单次 MengLa 查询）

```
前端 POST /api/mengla/query (action + catId + dateType + timest/starRange/endRange)
    ↓
后端 query_mengla_domain()
    ↓
1) 查 MongoDB（按 action 对应集合 + granularity + period_key(s) + params_hash）
    → 命中则返回 (data, source=mongo)，并可选回填 Redis（单点）
    → 未命中 ↓
2) 仅单点接口：查 Redis（mengla:{action}:{granularity}:{period_key}:{params_hash}）
    → 命中则返回 (data, source=redis)
    → 未命中 ↓
3) 调采集服务：POST /api/managed-tasks/{id}/execute，body 含 webhookUrl
    → 拿到 executionId，轮询 Redis key：mengla:exec:{executionId}
    → 采集完成后，采集服务 POST 到 webhookUrl，后端写入 Redis 上述 key
    → 轮询到后落库 Mongo（+ 单点回写 Redis），返回 (data, source=fresh)
    → 若 webhook 一直未到：后端默认等 3600 秒后 504，前端 3 分钟超时先 abort
```

- **趋势接口**（industryTrendRange）：只走 1）Mongo；不走 Redis。若 Mongo 全量或部分命中则直接返回；否则走 3），等 webhook（按天落多文档）。
- **单点接口**（high / hot / chance / industryViewV2）：走 1）→ 2）→ 3），命中任一层即返回。

---

## 三、前端请求与依赖

- **入口**：React Query 驱动，`queryMengla()` 统一请求 `POST /api/mengla/query`。
- **行业总览**：两个请求并行，**任一失败即整页报「加载萌拉数据失败」**。
  - `overviewTrendQuery`：action=industryTrendRange，依赖 primaryCatId + trendRangeStart + trendRangeEnd。
  - `overviewViewQuery`：action=industryViewV2，依赖 primaryCatId + distributionTimest。
- **蓝海/热销/潜力**：各一个 useQuery，依赖 primaryCatId + period + timest。
- **共同前提**：未选类目（primaryCatId 为空）时，上述请求 `enabled: false`，不会发请求。
- **超时**：前端单次请求 3 分钟超时；后端等 webhook 默认 3600 秒。

---

## 四、后端与外部依赖

- **MongoDB**：持久化各 action 的按粒度、period_key、params_hash 的文档；趋势按天多文档，单点单文档。
- **Redis**：  
  - 单点接口的查询缓存：`mengla:{action}:{granularity}:{period_key}:{params_hash}`。  
  - 采集结果临时存储：`mengla:exec:{executionId}`，由 webhook 写入，轮询读到后落 Mongo 并可选回写参数缓存。
- **采集服务**（COLLECT_SERVICE_URL）：托管任务「萌啦数据采集」执行后，对后端提供的 webhookUrl 发起 POST，body 含 executionId 与 result/resultData。
- **Webhook 可达性**：webhookUrl 默认由 APP_BASEURL（或 MENGLA_WEBHOOK_URL）拼出。若后端仅跑在本地（localhost），采集服务无法访问该 URL，则「无缓存」请求永远等不到 webhook，只能超时。

---

## 五、定时与异步补齐

- **定时任务**（APScheduler）：  
  - 每日 2:10：`run_mengla_granular_jobs`，按日/月/季/年颗粒度对 5 个 action 做补齐（走 query_mengla_domain，命中缓存则跳过，未命中则触发采集）。  
  - 每约 4 分钟（含抖动）：`run_crawl_queue_once`，消费历史补录队列，执行少量子任务。
- **补录接口**：`POST /admin/backfill` 可指定日期范围与接口，后台跑 backfill，结果同样经 Mongo/Redis 落库。

---

## 六、运行流畅的前提与瓶颈

| 环节 | 流畅条件 | 常见瓶颈 |
|------|----------|----------|
| 前端首屏/总览 | 多数请求命中 Mongo 或 Redis，快速返回 | 未选类目不发请求；总览两个请求任一超时即整页失败 |
| 趋势（行业总览） | Mongo 中有请求范围内全部或部分日期（已支持部分命中） | 范围大（如 30 天）且缺很多天时，此前会走采集；部分命中已改为直接返回已有天数 |
| 单点（view / high / hot / chance） | Mongo 或 Redis 有对应 period_key + params_hash | 无缓存时走采集，依赖 webhook |
| 采集 + webhook | webhookUrl 对采集服务可达；采集任务按时完成并回调 | 本地 backend 时 webhook 不可达，无缓存请求必超时 |
| 定时/补录 | 定时任务与补录持续把近期数据写入 Mongo | 未跑或间隔长时，缓存覆盖率低，首屏易走采集 |

---

## 七、如何使运行流畅、符合目标

1. **优先让请求命中缓存（Mongo，单点再加 Redis）**  
   - 保证定时任务每日执行（2:10 的 granular jobs + 约 4 分钟一次的队列消费）。  
   - 需要历史或近期完整区间时，使用 `POST /admin/backfill` 按范围补录，把数据写入 Mongo（趋势按天、单点按粒度）。  
   - 这样大部分访问应走 Mongo/Redis，响应在百毫秒级，符合「异步化、有缓存则秒出」的目标。

2. **确保 webhook 对采集服务可达**  
   - 后端部署在采集服务能访问的地址（公网或内网），并配置 `APP_BASEURL` 或 `MENGLA_WEBHOOK_URL` 为该地址。  
   - 本地开发时，若无公网/内网 URL，应依赖已有 Mongo/Redis 数据或先做补录，避免依赖「实时采集 + webhook」才能出数。

3. **行业总览不因趋势缺几天就整页失败**  
   - 已实现趋势「部分命中」：Mongo 中只有范围内部分日期时，也合并返回，不再因缺几天就走采集、等 webhook、超时。详见 `doc/overview-data-load-analysis.md`。  
   - 可选：前端根据响应头 `X-MengLa-Trend-Partial` 展示「已显示 X/Y 天」等提示，避免误读为指标为 0。

4. **前端体验**  
   - 已选类目后再请求；总览两个请求并行，单次超时 3 分钟；可保持现有「部分数据先出」的策略。  
   - 可选：总览下趋势与区间分块 loading/error，避免一个失败拖死整页（需改前端逻辑）。

5. **运维与排查**  
   - 使用 `doc/docker-logs-and-tracing.md` 中的 Docker 日志与 Redis MONITOR 观察 Mongo/Redis/采集与 webhook 是否正常。  
   - 后端日志中的 `[MengLa] response ... source=mongo|redis|fresh` 与 `MengLa Mongo partial (trend)` 可用来确认命中情况与是否走采集。

---

## 八、简要结论

- **运行逻辑**：前端发 MengLa 查询 → 后端先 Mongo、再 Redis（仅单点）、再采集 → 采集结果经 webhook 写 Redis，后端轮询后落 Mongo 并返回。  
- **流畅目标**：通过定时任务与补录把数据提前写入 Mongo（及单点 Redis），使多数请求命中缓存；webhook 仅在对采集服务可达时用于「补漏」。  
- **与现有文档关系**：行业总览拉不出数据的原因与部分命中策略见 `doc/overview-data-load-analysis.md`；Docker 与日志追踪见 `doc/docker-logs-and-tracing.md`；本稿从整体运行逻辑与流畅性角度做统一说明。
