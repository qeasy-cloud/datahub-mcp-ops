# P1 · 跑通源侧取数（无守护进程）

> 目标：让"源系统 → 平台"这一段稳定产出数据条目。
> 预计 5–10 分钟；只读 + 一次 `queue.job.run`（不写外部系统）。

---

## 前置检查（30 秒）

```bash
dh call meta.whoami                      # 有 strategy:read / strategy:ops 吗
dh call strategy.get --args '{"strategyId":"<SID>"}'
```

- `status=0` + `is_online=false` → **正常**，调试期就该这样。
- 若 `status=1`（运行中）且你不想干扰调度 → 先 `strategy.stop`（会记审计）。

---

## 步骤

### 1. 触发一次调度

```bash
dh call strategy.dispatchSource --args '{"strategyId":"<SID>"}'
```

期望：
```jsonc
{"mode":"debug","jobId":"6ae1…",
 "request":{"FormId":"BD_Customer","FilterString":"FApproveDate>='2026-09-01'","Limit":"100"},
 "next_step":"…strategy.queue.job.run…"}
```

✅ 检查点：`jobId` 是 24 位十六进制；`request` 里的过滤条件符合预期。
❌ 若 `code=strategy_not_running` → 你传了 `requireRunning=true`，去掉。
❌ 若 `request.FilterString` 明显过窄（如只查今天）→ 先记住，第 3 步可能要放宽。

### 2. 确认入队 + 看参数

```bash
dh call strategy.queue.list --args '{"strategyId":"<SID>","direction":"source"}'
dh call strategy.queue.job.get --args '{"strategyId":"<SID>","direction":"source","jobId":"6ae1…"}'
```

✅ `queue.list` 里能看到该 job；`job.get` 里 `params` 有内容。
❌ `queue.list` 空 → 调度没真的入队（检查方案配置 / 是否被前置条件卡住）。

### 3. 手工消费

```bash
dh call strategy.queue.job.run --args '{"strategyId":"<SID>","direction":"source","jobId":"6ae1…"}'
```

按结果分支：

| 结果 | 动作 |
|---|---|
| `ok=true, has_data=true` | 进第 5 步 |
| `ok=true, has_data=false` | 进第 4 步（放宽条件） |
| `ok=false` | 看 `exceptions` → `log.search(level:error,fatal)` → `05-diagnostics.md` §1 |
| `skipped=already_finished` | 加 `force=true` |

### 4. 没取到数：先改参数，不改元数据

```bash
# 放宽或清空过滤条件，并把状态打回 await
dh call strategy.queue.job.update --args '{
  "strategyId":"<SID>","direction":"source","jobId":"6ae1…",
  "params":{"FilterString":""},"status":"await"}'

dh call strategy.queue.job.run --args '{
  "strategyId":"<SID>","direction":"source","jobId":"6ae1…","force":true}'
```

✅ `update` 返回的 `previous` 保存好（这就是回滚值）。
❌ 若仍 `has_data=false` → 看响应正文：

```bash
dh call strategy.log.search --args '{
  "strategyId":"<SID>","level":"debug","jobId":"6ae1…","includeContent":true}'
```

- `content.response` 是 `[]`/空 → 源系统确实没有符合条件的数据（换条件或确认业务口径）。
- `content.response` 有数据但 `rows_returned=0` → 字段/解析问题（看 `otherResponse` 路径）。

### 5. 验证落地

```bash
dh call strategy.data.search --args '{"strategyId":"<SID>","pageSize":5}'
```

✅ `total` 与 `rows_returned` 对得上。
❌ `total=0` 但 `rows_returned>0` → 落库去重/`id` 字段问题（`01-platform-model.md` §2.3）。

### 6. 回写元数据（可选，推荐）

调试通过后，把验证过的参数写回元数据，避免下次又手改：

```bash
dh call strategy.source.update --args '{
  "strategyId":"<SID>","patch":{"otherRequest":[{"field":"FilterString","value":""}]}}'
# 记下 backup.historyId / md5
```

---

## 完成标准

- [ ] `dispatchSource` 返回 `jobId` 且 `queue.list` 能看到
- [ ] `queue.job.run` 返回 `ok=true, has_data=true`
- [ ] `data.search` 的 `total` 与 `rows_returned` 一致
- [ ] （可选）参数已回写元数据，且有 `backup.historyId`

## 收尾

保留数据给目标侧用（P2），或清理：

```bash
dh call strategy.data.clean --args '{"strategyId":"<SID>","dryRun":true}'
```
