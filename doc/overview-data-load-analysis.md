# 行业总览无法拉取数据的原因与处理

## 一、行业总览用到的接口

行业总览同时依赖两个请求，**只要有一个失败或超时，就会显示「加载萌拉数据失败」**：

| 请求 | action | 用途 | 后端 Mongo 集合 |
|------|--------|------|-----------------|
| 趋势 | industryTrendRange | 趋势图（更新日期/月/季/年 范围） | mengla_trend_reports |
| 区间 | industryViewV2 | 分布/区间数据（单时间点） | mengla_view_reports |

两者都会先查 Mongo，再查 Redis（仅单点），最后才走采集服务。

---

## 二、为什么 Mongo 有数据仍拉不出

### 1. 趋势接口是「全量命中」才走 Mongo

- 前端默认「更新日期」会要 **最近 30 天** 的区间（例如 2026-01-05～2026-02-03），即 30 个 `period_key`（20260105, 20260106, …, 20260203）。
- 后端逻辑是：**只有这 30 天的文档在 Mongo 里全部存在且 params_hash 一致时**，才认为 Mongo 命中并直接返回。
- 只要 **少任意一天**，就不会走 Mongo，会去调采集服务 → 等 webhook 写 Redis → 超时 → 前端报错。

所以：Mongo 里「有」趋势数据，但若 **没有覆盖请求的每一天**，行业总览仍然会走采集并超时，表现为拉不出数据。

### 2. 趋势接口没有用 Redis

- 代码里只有 **非趋势** 的单点查询才会查 Redis（high / hot / chance / industryViewV2）。
- industryTrendRange 是「多 key、按范围」查询，**只查 Mongo，不查 Redis**，所以 Redis 解决不了趋势拉不出的问题。

### 3. 区间接口容易命中

- industryViewV2 是 **单时间点** 查询（一个 period_key），Mongo 里有一条就能命中，所以日志里常看到 `MengLa Mongo hit: collection=mengla_view_reports`。
- 若你确认 Mongo 有数据，多半是 **view 已命中**，而 **trend 未全量命中**，导致整体仍报错。

---

## 三、已做的后端改动（部分命中即返回）

- 在 `backend/mengla_domain.py` 中，趋势查询（industryTrendRange）逻辑已调整：
  - **全量命中**：范围内每一天在 Mongo 都有文档时，行为不变，直接合并返回。
  - **部分命中**：若 Mongo 里只有范围内 **部分日期** 的文档，也会用这些文档合并成 `industryTrendRange.data` 并返回（source 仍为 mongo），不再因「差几天」就去走采集、导致超时。
- 日志中会看到 `MengLa Mongo partial (trend): requested=N found=M`，表示请求了 N 个日期、命中了 M 个。
- 这样行业总览在 Mongo 有部分趋势数据时就能先出图；缺失日期可后续通过补录或采集补全。

---

## 四、部分命中是否符合业务与展示意义

**业务需求**：行业总览要能「看到一段时间内的趋势」。  
**部分命中**：请求 30 天，只返回 Mongo 里有的 25 天数据。

- **是否符合业务**：符合。用户看到的是「有数据的那几天的真实趋势」，比一直加载失败或报错更符合「先能看、再补全」的需求；缺失日期可后续通过补录/采集补全。
- **展示意义**：趋势图按「有数据的日期」描点连线，每个点都是真实数据，没有造假。缺的日期在图上相当于「没有点」，曲线可能中间断档，这是如实反映「这些天暂无数据」。
- **建议**：若希望用户不误解为「指标在那几天为 0」，前端可在**部分命中**时做轻量提示（例如「已显示 25/30 天数据，部分日期暂无数据」）。后端已为趋势部分命中增加响应头 `X-MengLa-Trend-Partial: requested,found`，前端可根据该头显示提示（可选）。

---

## 五、你可做的排查与优化

1. **看 Mongo 里趋势覆盖了哪些天**  
   在 `mengla_trend_reports` 中按 `granularity: "day"`、你的 `catId` 查 `period_key`，看是否覆盖了前端请求的 30 天（或你选的范围）。

2. **先缩小范围验证**  
   在前端把「更新日期」范围改成最近 7 天，或改用「月榜/季榜/年榜」（单月/单季/单年的 key 少，更容易全量命中）。

3. **若希望缺数据时也能通过采集补全**  
   需保证采集服务的 webhook 能访问到你当前后端的公网/内网地址（不能是 localhost），否则缺的日期会一直等 webhook 超时。

4. **确认类目已选**  
   行业总览的两个请求都依赖 `primaryCatId`；未选类目时请求不会发，界面会一直空或 loading。

5. **响应头说明（趋势部分命中时）**  
   - `X-MengLa-Source`: 恒有，值为 `mongo` / `redis` / `fresh`。  
   - `X-MengLa-Trend-Partial`: 仅当 action 为 industryTrendRange 且为部分命中时存在，值为 `requested,found`（例如 `30,25`），前端可用来展示「已显示 25/30 天」等提示。需在 CORS 的 `Access-Control-Expose-Headers` 中暴露该头才能在前端读取。
