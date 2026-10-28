# 真实会话：一次完整的源侧调试

> 下面是一次真实执行的记录（测试租户，方案与 jobId 已做部分脱敏）。
> 用来看"每一步该期待什么、看到什么该做什么"，比读十页说明更快。

---

## 0. 起点

用户诉求：**"测试环境没守护进程，把这个方案的源侧跑通，看能不能取到客户数据。"**

方案：`QA-MCP-VERIFY-073356`（`bdb27781-…`，源=金蝶客户，目标=金蝶客户）

```bash
dh call strategy.get --args '{"strategyId":"bdb27781-…"}'
```
```jsonc
{"strategyId":"bdb27781-…","name":"QA-MCP-VERIFY-073356",
 "status":0,"status_label":"停止中","is_online":false,
 "source":{"platform":"金蝶云星空","connector":"轻易云测试金蝶","connectorId":"291b6327-…"},
 "target":{"platform":"金蝶云星空","connector":"轻易云测试金蝶","connectorId":"291b6327-…"},
 "sections":"basic"}
```

**判断**：`status=0` + `is_online=false` 是调试期常态 —— **不要**为了调试去 `start`。

---

## 1. 触发调度

```bash
dh call strategy.dispatchSource --args '{"strategyId":"bdb27781-…"}'
```
```jsonc
{"mode":"debug","jobId":"6ae13c39999899a3ba07cc15",
 "request":{"FormId":"BD_Customer",
            "FilterString":"FApproveDate>='2026-09-01 00:00:00'",
            "Limit":"100"},
 "next_step":"用 strategy.queue.job.run 执行该 jobId（无守护进程不会自动消费）"}
```

**判断**：
- `mode=debug` 说明平台知道"没人消费"，只入队；
- `request` 已经能看到过滤条件 —— 如果这里就明显过窄，后面大概率 `has_data=false`。

---

## 2. 确认入队 + 读参数

```bash
dh call strategy.queue.list --args '{"strategyId":"bdb27781-…","direction":"source"}'
# → total=1
dh call strategy.queue.job.get --args '{"strategyId":"bdb27781-…","direction":"source","jobId":"6ae13c39…"}'
```
```jsonc
{"jobId":"6ae13c39999899a3ba07cc15","status":5,"status_label":"队列中",
 "api":"executeBillQuery",
 "params":{"Limit":"100","FilterString":"FApproveDate>='2026-09-01 00:00:00'","FormId":"BD_Customer"},
 "timeline":{"created_at":"2026-10-28 08:05:06","active_time":null},
 "related_data":{"total":0,"by_status":{}},
 "next_step":"任务在队列中：用 strategy.queue.job.run 手工消费"}
```

**判断**：`params` 是真实要发出去的参数（`queue.list` 看不到，必须 `job.get`）。

---

## 3. 手工消费

```bash
dh call strategy.queue.job.run --args '{"strategyId":"bdb27781-…","direction":"source","jobId":"6ae13c39…"}'
```
```jsonc
{"executed":true,"ok":true,"has_data":true,"elapsed_ms":144,
 "status_before":5,"status_after":2,
 "rows_returned":9,"data_created":9,
 "request":{"FormId":"BD_Customer","FilterString":"FApproveDate>='2026-09-01 00:00:00'","Limit":"100"},
 "response_excerpt":"[[153568,\"QCL-001\",…],[153569,\"QCL-002\",…]]",
 "exceptions":{"total":0},
 "next_step":"源侧已取到数据。下一步通常是 strategy.dispatchTarget 推到目标端。"}
```

**判断**：`ok=true` **且** `has_data=true` —— 两者都成立才算真的取到。
`rows_returned=9` 与 `data_created=9` 一致，说明落库没被去重规则吞掉。

---

## 4. 看这次到底发了什么（证据）

```bash
dh call strategy.log.search --args '{
  "strategyId":"bdb27781-…","level":"debug","jobId":"6ae13c39…","includeContent":true}'
```
```jsonc
{"rows":[
  {"level":"DEBUG","level_key":"debug","is_debug":true,"text":"00_debug_建立连接","content":{…}},
  {"level":"DEBUG","is_debug":true,"text":"01_debug_请求参数",
   "content":{"request":{"FormId":"BD_Customer","FilterString":"…","Limit":"100"}}},
  {"level":"DEBUG","is_debug":true,"text":"02_debug_响应参数",
   "content":{"response":"[[153568,\"QCL-001\",…]]"}}],
 "total":3}
```

**判断**：三条留痕齐全 = 整个调用链完整走完。
注意它们是 `DEBUG` 而不是 `ERROR/FATAL` —— 不要被 `dbInfo` 的 fatal 计数误导。

---

## 5. 验证落地

```bash
dh call strategy.data.search --args '{"strategyId":"bdb27781-…","pageSize":5}'
# → total=9
```

**判断**：`total` 与 `rows_returned` 对得上 → 源侧完成。

---

## 6. 目标侧（到护栏为止）

```bash
dh call strategy.dispatchTarget --args '{"strategyId":"bdb27781-…"}'
# → {"mode":"debug","jobId":"6ae13b3a663ba76f860e5f03", …}

dh call strategy.queue.job.get --args '{
  "strategyId":"bdb27781-…","direction":"target","jobId":"6ae13b3a…"}'
# → params 里有 Model（真正要写的报文）

dh call strategy.queue.job.run --args '{
  "strategyId":"bdb27781-…","direction":"target","jobId":"6ae13b3a…"}'
```
```jsonc
{"ok":false,"code":"external_write_unconfirmed",
 "reason":"目标侧写入需要显式确认。",
 "suggestion":"本操作会把数据真实写入外部系统（如金蝶 batchSave），不可通过本平台回滚。确认无误后请带 confirmWrite=true 再次调用。"}
```

**判断**：护栏生效。**这一步刻意停住**——是否真写，需要人来决定（本例只验证到"能写"）。

---

## 7. 收尾

```bash
dh call strategy.data.clean  --args '{"strategyId":"bdb27781-…"}'
dh call strategy.queue.clean --args '{"strategyId":"bdb27781-…"}'
dh call strategy.dbInfo      --args '{"strategyId":"bdb27781-…"}'
```
```jsonc
{"data":{"await":0,"repeat":0,"finished":0,"error":0,"fkc":0,"queue":0},
 "source_queue":{"queue":0,"error":0,"finished":0},
 "target_queue":{"queue":0,"error":0,"finished":0},
 "log":{"record":0,"notice":0,"success":0,"error":0,"fatal":0,"debug":12}}
```

**判断**：数据与队列归零；`debug=12` 是本次调试留下的留痕（4 次调用 × 3 条），**不是错误**。

---

## 复盘：这次为什么一次就通了

| 做对的 | 说明 |
|---|---|
| 没有 `start` 方案 | 调试期不需要调度器，手工触发更可控 |
| 先看 `request` 再执行 | 过滤条件在 `dispatchSource` 就可见，提前发现"可能取不到" |
| 用 `has_data` 而不是 `ok` | 避免把"空响应"当成功 |
| 读 `log.search(level=debug)` | 拿到真实报文，而不是猜 |
| 目标侧停在护栏前 | 外部写入不可回滚，必须人工点头 |

## 如果当时 `has_data=false`

```bash
dh call strategy.queue.job.update --args '{
  "strategyId":"bdb27781-…","direction":"source","jobId":"6ae13c39…",
  "params":{"FilterString":""},"status":"await"}'
dh call strategy.queue.job.run --args '{
  "strategyId":"bdb27781-…","direction":"source","jobId":"6ae13c39…","force":true}'
```
→ 实测把 `FilterString` 清空后，取到 **100 行**（`Limit` 上限）。
这就是"先改任务参数、别改元数据"的价值：30 秒验证了"是过滤条件的问题"。
