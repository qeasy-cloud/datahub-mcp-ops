# P4 · 批量运维与安全收尾

> 两类高频任务：**批量体检/重推**（read-heavy）和**收尾清理**（destructive）。
> 都要控节奏（限流 120/分钟）与影响面（不可恢复）。

---

## 1. 批量体检（巡检一个租户）

### 1.1 拿清单

```bash
dh call strategy.list --args '{"pageSize":100,"currentPage":1}'
# 大于 100 个方案 → 翻页；不要试图一次拉全
```

### 1.2 逐个体检（每方案 1 次调用）

```bash
dh call strategy.dbInfo --args '{"strategyId":"<SID>"}'
```

按 `observations` 与 `last_run` 分类：

| 分类 | 判据 | 下一步 |
|---|---|---|
| 健康 | `log.error/fatal=0`、队列 0、`last_run.ok=true` | 记录即可 |
| 无消费者 | 队列有 job，`status` 长期 5/0 | 有人工调试需求时 `queue.job.run` |
| 真失败 | `log.error/fatal>0` 或 `last_run.ok=false` | `log.search(level:error,fatal)` + `exception.search` |
| 积压 | `queue.error` 高 | 见 §2 批量重推 |
| 空转 | `data` 全 0 且 `last_run` 为空 | 确认是否该启动 |

**节奏**：42 个方案 ≈ 43 次调用，1 分钟内跑完没问题；
超过 100 个就分批（每批 50 个，间隔 30 秒），避免 `429`。

### 1.3 输出一页体检报告

```markdown
## 巡检结果（<租户> / <日期>）
- 方案总数：N（运行中 X / 停止 Y / 已上线 Z）
- 健康：A   无消费者：B   真失败：C   积压：D   空转：E
- 需要人工处理（按优先级）：
  1. <方案名> (<SID>)：<症状> → <建议动作>
```

模板：`../templates/ops-report.md`。

---

## 2. 批量重推（把错误数据打回队列）

### 2.1 圈定范围（先取证，再动手）

```bash
dh call strategy.data.search --args '{"strategyId":"<SID>","status":"error","pageSize":100}'
dh call exception.search --args '{"strategyId":"<SID>","pageSize":50}'
```

✅ 确认是"同一类失败"（同一报错、同一字段）→ 值得批量重推。
❌ 混杂多种错误 → 先分类，别一把梭。

### 2.2 批量打回等待

```bash
# 方式一：按 dataId 精确（推荐，影响面可控）
dh call strategy.data.setStatus --args '{
  "strategyId":"<SID>","dataIds":["<id1>","<id2>"],"status":"await"}'

# 方式二：整体重置（影响面大，慎用）
dh call strategy.dbResetStatus --args '{"strategyId":"<SID>"}'
```

### 2.3 重推并验证

```bash
dh call strategy.dispatchTarget --args '{"strategyId":"<SID>"}'
dh call strategy.queue.job.get  --args '{"strategyId":"<SID>","direction":"target","jobId":"…"}'
dh call strategy.queue.job.run  --args '{"strategyId":"<SID>","direction":"target","jobId":"…","confirmWrite":true}'
dh call strategy.dbInfo --args '{"strategyId":"<SID>"}'
```

✅ 期望：`error` 计数下降，`repeat` 上升（幂等命中），不出现新错。
❌ `error` 不降 → 先修根因（映射/数据），不要反复重推。

### 2.4 补推窗口（历史数据）

- 按**业务日期**圈范围，不要用创建时间；
- 与已推窗口做差集，或按单号查目标是否已存在；
- 保持同一幂等键；补完抽样回查（源单号 → 目标单号 → 明细行数）。

---

## 3. 安全收尾（清理）

### 3.1 前置条件

| 条件 | 检查 |
|---|---|
| 方案已停止 | `strategy.get` 返回 `status=0`，否则 `strategy.stop` |
| 未上线 | `is_online=false`，否则 `strategy.offline` |
| 影响面已知 | `dryRun` 返回的 `precheck` |
| 有人同意 | 生产/客户环境必须 |

### 3.2 顺序（不可颠倒）

```bash
# ① 预演
dh call strategy.queue.clean --args '{"strategyId":"<SID>","dryRun":true}'
dh call strategy.data.clean  --args '{"strategyId":"<SID>","dryRun":true}'

# ② 执行（>1000 行会要求确认令牌；按返回提示带 confirmationToken 再调一次）
dh call strategy.queue.clean --args '{"strategyId":"<SID>"}'
dh call strategy.data.clean  --args '{"strategyId":"<SID>"}'

# ③ 复核归零
dh call strategy.dbInfo --args '{"strategyId":"<SID>"}'
```

- `data.cleanAll` 会连日志一起清（破坏性最强）——除非要"彻底重置"，否则别用。
- **外部系统已写入的单据不会消失**，需要单独处理（反向链路/人工）。
- 调试用的临时方案建议 `offline` 保留，不要试图删除（平台无删方案工具）。

### 3.3 清理后的状态

期望 `dbInfo`：

```jsonc
{"data":{"await":0,"repeat":0,"finished":0,"error":0,"fkc":0,"queue":0},
 "source_queue":{"queue":0,"error":0,"finished":0},
 "target_queue":{"queue":0,"error":0,"finished":0}}
```

---

## 4. 脚本资产维护

```bash
dh call script.list --args '{"strategyId":"<SID>"}'
dh call script.validate --args '{"script":"<?php …"}'
dh call script.get   --args '{"strategyId":"<SID>","scriptId":"…"}'
```

- 改脚本前先 `get` 读现状；`write` 会自动备份（返回 `backup`）。
- **只改真正会触发的事件**（14 个里只有 5 个）——见 `../references/01-platform-model.md` §7。
- 删除脚本要求方案未上线未运行，且备份失败会中止。

---

## 5. 收尾检查清单

- [ ] 该停的停了（`status=0`），该下线的下线了（`is_online=false`）
- [ ] 测试数据/队列按约定清理，`dbInfo` 归零
- [ ] 外部系统里写入的测试单据已登记（不会因平台清理消失）
- [ ] 临时密钥/临时方案已登记到交接文档
- [ ] 报告里有：结论、证据（id/数字/错误码）、动作（含副作用）、下一步
