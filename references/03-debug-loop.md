# 03 · 调试闭环：从"没数据"到"确实写进去了"

> 适用：测试/客户环境**没有守护进程**（方案启动也不产生队列、队列不会被自动消费），
> 或调试期**故意不开自动运行**。这是顾问调集成的常态，也是本 SKILL 的核心场景。
>
> 一句话：**不要靠"启动方案等 cron"来调试**。用手工触发 + 手工消费，把每一段单独验证。

---

## 0. 六步对照（人类 UI → MCP）

| # | 人类动作 | MCP 调用 | 你得到什么 |
|---|---|---|---|
| 1 | 配源端元数据 | `strategy.get {sections:"source"}` / `strategy.source.update` | 当前配置（默认 `basic` 不含 `meta_data`） |
| 2 | 点「调度一次」 | `strategy.dispatchSource` | `mode=debug` + `jobId` + **组装后的请求** |
| 3 | 查请求队列 | `strategy.queue.list {direction:"source"}` | 队列条目（`params` 被抹掉，只有状态） |
| 4 | 点「执行」 | `strategy.queue.job.run` | `ok` / `has_data` / 行数 / 请求 / 响应摘要 |
| 5 | 看报错 → 改**任务参数**再跑 | `queue.job.get` → `queue.job.update` → `queue.job.run {force:true}` | 改前/改后参数、可回滚 |
| 6 | 调通后回写元数据 | `strategy.source.update` / `target.update` | 备份句柄（可 `config.rollback`） |

> **第 5 步是关键**：先改任务参数验证假设，**不要**一上来改元数据。
> 元数据改动影响后续所有调度，任务参数只影响这一条。

---

## 1. 源侧：完整可跑序列

```bash
# ① 现状（basic 足够，别一上来拉 40KB）
dh call strategy.get --args '{"strategyId":"<SID>"}'

# ② 触发（停止态也可用）
dh call strategy.dispatchSource --args '{"strategyId":"<SID>"}'
# → {"mode":"debug","jobId":"6ae1…","request":{"FormId":"BD_Customer","FilterString":"…","Limit":"100"},
#    "next_step":"…strategy.queue.job.run…"}

# ③ 看队列（确认真的入队了）
dh call strategy.queue.list --args '{"strategyId":"<SID>","direction":"source"}'

# ④ 看任务参数（列表看不到，必须 get）
dh call strategy.queue.job.get --args '{"strategyId":"<SID>","direction":"source","jobId":"6ae1…"}'

# ⑤ 手工消费
dh call strategy.queue.job.run --args '{"strategyId":"<SID>","direction":"source","jobId":"6ae1…"}'
# → {"ok":true,"has_data":true,"rows_returned":9,"data_created":9,"status_after":2,
#    "request":{…},"response_excerpt":"[[153568,\"QCL-001\",…]]","next_step":"…"}
```

### 1.1 判读表（这一张表决定下一步）

| 返回 | 含义 | 下一步 |
|---|---|---|
| `ok=true, has_data=true` | 取到数并落库 | 目标侧，或回写元数据 |
| `ok=true, has_data=false` | **执行成功但没取到数** | ①`log.search(level=debug, jobId)` 看响应体；②`queue.job.update` 放宽 `FilterString`（如清空或放大时间窗）→ `run {force:true}` |
| `ok=false` + `exceptions` | 真失败 | `log.search(level=error,fatal)` + `exception.search`；按 `05-diagnostics.md` 定位 |
| `skipped=already_finished` | 没执行（任务已结束） | 需要重跑传 `force=true` |
| `skipped=already_failed` | 没执行（任务已失败） | 同样要 `force=true`（先确认已修好） |
| `code=external_write_unconfirmed` | 目标侧缺确认 | 加 `confirmWrite=true` |

> **`ok` 与 `has_data` 必须分开看**：平台把"源系统返回空"当作**完成**（不是错误），
> 只看状态会把"什么都没取到"误判成成功。这是本 SKILL 反复强调的第一坑。

### 1.2 改参数重跑（顾问最常用）

```bash
# 放宽过滤（merge 只改给定键；返回 previous 可直接回滚）
dh call strategy.queue.job.update --args '{
  "strategyId":"<SID>","direction":"source","jobId":"6ae1…",
  "params":{"FilterString":""},"status":"await"}'

# 强制重跑
dh call strategy.queue.job.run --args '{
  "strategyId":"<SID>","direction":"source","jobId":"6ae1…","force":true}'
```

约束与细节：
- 方案**运行中**默认拒绝改参数（防守护进程并发）；确认无并发再 `allowRunning=true`。
- `params` 是**整棵参数树**：`FormId`/`FilterString`/`Limit`/分页键都在里面；`merge` 模式下只覆盖你给的键。
- 改完会清掉该任务的旧异常——所以"改完再跑"看到的是本次结果，不会串上次的错。
- **调通后**把验证过的参数回写到元数据：`strategy.source.update {patch:{…}}`，
  保留返回的 `backup.historyId`，出问题用 `strategy.config.rollback` 回滚。

### 1.3 看"这次到底发了什么、回了什么"

```bash
dh call strategy.log.search --args '{
  "strategyId":"<SID>","level":"debug","jobId":"6ae1…","includeContent":true}'
```

三条调试留痕固定顺序：`00_debug_建立连接` → `01_debug_请求参数` → `02_debug_响应参数`。
`content.request` 是真正发出去的报文，`content.response` 是对方返回。

> 老环境若看到"`dbInfo` 报 fatal、`exception.search` 为 0"，先看日志文本是否 `0x_debug_` 开头：
> 那是历史版本把调试留痕写成了 FATAL，**不是错误**。

---

## 2. 目标侧：多一道硬门槛

```bash
# ① 触发（把待处理数据推入目标队列）
dh call strategy.dispatchTarget --args '{"strategyId":"<SID>"}'
# → {"mode":"debug","jobId":"<TID>","next_step":"…queue.job.run(direction=target, confirmWrite=true)…"}

# ② 看要发出去的报文（真正写入前唯一的人工复核点）
dh call strategy.queue.job.get --args '{
  "strategyId":"<SID>","direction":"target","jobId":"<TID>"}'
# → params.Model = {"FBillNo":"…","FName":"…","FCreateOrgId":{"FNumber":"…"}}

# ③ 真正写入（不可回滚的外部副作用）
dh call strategy.queue.job.run --args '{
  "strategyId":"<SID>","direction":"target","jobId":"<TID>","confirmWrite":true}'

# ④ 回查外部系统（平台状态不是证据）
```

### 2.1 目标侧判读

| 现象 | 含义 | 下一步 |
|---|---|---|
| `params.Model` 里字段全是 `null`/空 | 没有真正映射（裸字段名被当常量） | 改 `target.update`：`{{源字段}}` |
| 报"格式错误，不能转换为字典类型" | 基础资料字段缺 `ConvertObjectParser` | 加 parser，`params=FNumber` |
| 报"没有数据需要保存" | 字段全空，被 `removeParamsNull` 丢弃 | 检查源数据 + 映射 |
| 报"组织内编码唯一" | 幂等命中 | 数据变 `repeat`，**不是错误** |
| 报"基础资料字段值不存在" | 源数据脏（编码在目标系统不存在） | 清洗源数据或补建档案 |
| 响应为空但成功 | 金蝶会话并发/空响应 | 重推一次 |

> 目标端**异常默认被脚本层静默吞掉**（见 `01-platform-model.md` §7），
> 别指望日志里一定有错误——以外部系统回查为准。

---

## 3. 一条任务的状态机（看懂就不会瞎等）

```
status: 5 QUEUE ──run──→ 2 FINISHED（成功）
                    └──→ 3 ERROR（失败，进异常队列）
                    └──→ 5（重试排队，退避 20s→300s→3600s→14400s→72000s）
数据条目 status: 0 AWAIT → 5 QUEUE → 2 FINISHED / 3 ERROR / 6 跳过调度
```

- 手工 `run` 是**同步**的：返回时状态已定，不需要轮询。
- 守护进程消费是**异步**的：`run` 之前状态会一直是 5/0。
- 重试退避最长约 25 小时（`max_retries` 默认拉满）。**坏数据不要留在队列里等退避**，
  先 `run` 拿即时结果，或 `queue.job.update` 把 `status` 设为 `await` 再重跑。

---

## 4. 常见"跑不通"的六个原因（按出现频率排序）

| # | 原因 | 判据 | 处置 |
|---|---|---|---|
| 1 | 过滤条件过窄 | `dispatchSource` 的 `request.FilterString` 很严；`has_data=false` | 放宽/清空后重跑 |
| 2 | 没有消费者 | 队列有 job，状态不动 | `queue.job.run` |
| 3 | 分页参数放错位置 | 永远只有第一页/固定 100 条 | 查接口资产的分页键；`page_size`/`pageNo` 放 `request[]` 或 `otherRequest` |
| 4 | 增量字段选错 | 新单有、改单没有 | 用 `modified` + 回看窗口 |
| 5 | 目标缺映射 | `params.Model` 全空 | `target.update` 补 `{{}}` |
| 6 | 前置方案未完成 | `*_dispatch_condition` 卡住 | 等，或临时摘掉 |

细节与更多症状 → `05-diagnostics.md`；反例 → `08-anti-patterns.md`。

---

## 5. 收尾（调试完必须做）

```bash
dh call strategy.data.clean  --args '{"strategyId":"<SID>","dryRun":true}'   # 先看影响面
dh call strategy.data.clean  --args '{"strategyId":"<SID>"}'                 # >1000 行会要令牌
dh call strategy.queue.clean --args '{"strategyId":"<SID>","dryRun":true}'
```

- 破坏性操作要求方案**停止且未上线**（先 `strategy.stop`）。
- 调试用的临时方案建议直接 `strategy.offline` 保留，不要删（平台无删除方案的工具）。
- 收尾后 `strategy.dbInfo` 应看到 `data` 与 `source_queue/target_queue` 归零。
