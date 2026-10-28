# 02 · Tool 目录（46 个：43 业务 + 3 meta）

> 机器可读清单：`../tools/manifest.json`（由服务端代码生成，CI 校验文档一致性）。
> 命名：`域.对象.动作`。风险：🟢 `read` / 🟡 `write` / 🟠 `ops` / 🔴 `destructive`。
> **"需确认"列**：✅ 表示该工具受二次确认机制约束（信任级别为 `confirm`/`guarded` 时，或影响面超阈值时，
> 首次调用只返回 `precheck` + `confirmationToken`，需带令牌二次调用）。
>
> 通用约定：分页参数 `currentPage`（从 1 开始）+ `pageSize`（≤100）；`strategyId` 均为 UUID；
> `jobId` 为 24 位十六进制；业务错误统一 `{ok:false, code, reason, suggestion, kb}`。

---

## 1. meta（3，无需 scope）

| Tool | 用途 | 关键返回 |
|---|---|---|
| `meta.whoami` | 当前密钥身份 | `lesseeId` / `userId` / `trust` / `mode` / `scopes` |
| `meta.capabilities` | 能力面（**先调这个判断能不能干**） | `tool_count` / 每工具 `callable`（按 scope 与 mode 计算）/ `all_scopes` |
| `meta.enums` | 枚举字典（状态语义词、风险级别…） | `dataStatus` / `strategyStatus` / `logStatus` / `risks` |

> **坑**：`meta.capabilities` 的 `callable` 是"当前密钥能不能调"，不是"服务端有没有"。
> 发现工具不可用先看这里，别急着报 bug。

---

## 2. asset（6，🟢 `asset:read`，全局目录，无租户数据）

| Tool | 用途 | 关键入参 |
|---|---|---|
| `asset.platform.list` | 平台目录（金蝶云星空、旺店通…） | `search` / `status` / 分页 |
| `asset.platform.get` | 平台详情 + 接口资产数 + 可选应用清单 | `platformId` / `includeApps` |
| `asset.connector.list` | **本租户**连接器（含环境/地址/数据中心/操作者，部分脱敏） | `platformId` / `keyword` / 分页 |
| `asset.connector.get` | 连接器详情 + 被多少方案引用 + `credentialsConfigured` | `connectorId` |
| `asset.api.list` | 接口资产目录（**用 `effect` 选读写**：`QUERY` 源 / `EXECUTE` 目标） | `platformId` / `effect` / `search` |
| `asset.api.get` | 接口资产详情：请求/响应字段清单 + 示例 | `apiId` / `includeFields` |

> **坑 1**：`platform` / `api` 是**全局目录**，不分租户；`connector` 才分租户。
> **坑 2**：`asset.api.get` 字段清单最多 300 条，超出用 `omitted` 计数标注——**别以为字段就这么多**。
> **坑 3**：连接器**永不返回** `app_secret`；只有 `credentialsConfigured`（true/false）。

---

## 3. strategy 只读（8，🟢 `strategy:read`）

### `strategy.list`
按名称/状态/分组/平台筛方案。返回 `strategyId`、`status`+`status_label`、`is_online`、
`source/target`（`platform`/`connector` 名称 + `platformId`/`connectorId`）、`sourceCrontab`/`targetCrontab`。

- `search` 支持**名称模糊**与 **strategyId 前缀**。
- `pageSize` 上限 100（要更多就翻页，不要试图一次拉全）。

### `strategy.get`
方案详情。**默认 `sections=basic`**：只给头部 + `meta_summary`（api/type/effect/formId/字段数/`meta_bytes`）。
需要完整 `meta_data` 时显式传 `sections=source|target|all`。

- 单条 `all` 实测约 40KB；`basic` 约 1.6KB。**先 basic，再决定要不要拉全量**。
- `meta_summary.meta_bytes` 可用来判断"配置有多大"。

### `strategy.showConfig`
读源/目标端完整元数据（`direction` 必填）。**改配置前的标准动作**。
凭据字段以 `***` 脱敏。

### `strategy.dbInfo`
**巡检第一步**：一次调用看清整体健康度。

- `log`：`record/notice/success/error/fatal` + **`debug`**（调试留痕，**不是错误**）
- `data`：`await/repeat/finished/error/fkc/queue`
- `source_queue` / `target_queue`：`queue/error/finished`
- `last_run`：最近一次 SJOB/TJOB（`jobId/direction/status/ok/rows_returned/active_time/api`）
- `observations`：**已经过判读的建议**（真实错误→`exception.search`；调试留痕→`log.search(level=debug)`；积压→`queue.job.run`）

### `strategy.queue.list`
查源/目标队列。`direction` 必填。⭐⭐ **返回的 `params` 是空的**（列表接口不返回参数）——
要看参数必须用 `queue.job.get`。

### `strategy.queue.job.get`
**单条任务的完整信息**：`params`（真正发出/将要发出的请求体）、`status`+`status_label`、`api`、
`timeline`（入队/开始/结束/耗时）、`ids_count`、`related_data`（关联数据状态分布）、
`exceptions`、`next_step`。

- `params` 会做深度裁剪（`trimDeep`）：数组保留结构，超长字符串截断。
- `direction` 必须与 job 实际方向一致，否则 `job_not_found`。

### `strategy.log.search`
读 `<sid>_LOG` 正文。`level`：`debug/record/notice/success/error/fatal/all`，**默认排除 debug**。

- 想看"这次到底发了什么请求/回了什么"→ `level=debug` + `jobId`。
- 默认排除 debug 是刻意的：调试留痕量大且不是错误。
- `includeContent=true` 才返回 `content`（请求/响应/连接信息）。

### `strategy.data.search`
查数据条目。`status` 只收**语义词**（`await/error/queue/finished/repeat/unhandle/continue/fkc`）。

- `number` / `dataId` 精确匹配；`pageSize` ≤100。

### `strategy.checkList`
上线检查项（`direction` 必填）。返回是否已确认、哪些是阻断项。
**只读**——不会替你勾选；`blockingCount>0` 时 `online` 会被拒绝（除非 `force`）。

---

## 4. strategy 调试（5）—— 无守护进程的主力

### `strategy.dispatchSource`（🟠 ops，✅ 需确认）
手工触发源端调度：调用源接口取数并生成源队列任务。返回 `mode`（`debug`/`scheduled`）、`jobId`、
`request`（组装后的请求）、`next_step`。

- **方案停止态也放行**（调试期常态）：此时只入队、不会自动消费。
- 需要旧语义（必须运行中）→ `requireRunning=true`。
- **`request` 是"将要发出的报文"**，是核对映射的最快证据。

### `strategy.dispatchTarget`（🟠 ops，✅ 需确认）
手工触发目标端调度：把数据推入目标队列。同样停止态可用。
**入队 ≠ 已写入外部系统**，真正写在 `queue.job.run` 时。

### `strategy.queue.job.run`（🟠 ops，✅ 需确认）⭐ 核心
同步执行一条队列任务。返回：`executed`、`ok`、**`has_data`**、`elapsed_ms`、`status_before/after`、
`rows_returned`、`data_created`、`request`、`response_excerpt`、`exceptions`、`next_step`。

| 参数 | 语义 |
|---|---|
| `force` | 默认 `false`：已完成/已失败任务不重复执行（`skipped=already_finished\|already_failed`）；重跑传 `true`（注意幂等） |
| `confirmWrite` | `direction=target` **必须为 true**，否则 `external_write_unconfirmed`；信任级别不能豁免 |

**判读**：
- `ok=true, has_data=true` → 成功且有数据。
- `ok=true, has_data=false` → **执行成功但没取到数**（过滤条件过窄 / 源系统空响应）。平台把空响应当"完成"。
- `ok=false` → 看 `exceptions` + `log.search(level=error,fatal)`。

### `strategy.queue.job.update`（🟠 ops，✅ 需确认）⭐ 核心
改任务参数（`params`）后重跑，**不改元数据**的调试方式。

- `mode=merge`（默认，只覆盖给定键）/ `replace`（整体替换）。
- 返回 `previous`（被覆盖前的旧值，可直接回滚）+ `updated`（实际改动的键）+ `status_before/after`。
- 方案运行中默认拒绝（防与守护进程并发改同一任务）；确认无并发再传 `allowRunning=true`。
- 参数白名单：键名不得以 `$` 开头、不得含 `.`；深度 ≤3、键数 ≤200、体积 ≤64KB（防 NoSQL 注入）。
- 改完会清该任务的旧异常，避免"上次的错"被当成本次结果。

### `exception.search`（🟢 `exception:read`）
检索租户的同步异常记录（方案/接口/业务编号/dataId/时间窗）。
**它是"结论"，不是"过程"**：只有真正失败的作业会进异常队列；调试留痕不在里面。

---

## 5. strategy 写（6，🟡 `strategy:write`，均 ✅ 需确认）

| Tool | 用途 | 关键点 |
|---|---|---|
| `strategy.update` | 改基本信息 + 调度（名称/编码/分组/优先级/cron/生效时间/lastSync/maxRetries） | 返回 `before/after/changed`；`dryRun` 可预演；**不改**运行状态与源/目标配置 |
| `strategy.source.update` | 改源端元数据 | 写前自动备份 → 返回 `backup.historyId`/`md5`；`metaData`（整体）与 `patch`（浅合并）二选一 |
| `strategy.target.update` | 改目标端元数据 | 同上；**字段映射改这里** |
| `strategy.config.rollback` | 回滚到历史快照 | 需 `historyId` + `md5`；回滚前会再给当前配置打一份快照（回滚也可回滚） |
| `strategy.create` | 按蓝图新建方案 | `source` 必须 `effect=QUERY`、`target` 必须 `effect=EXECUTE`；不给 `metaData` 时自动套用接口资产默认快照；`dryRun` 可预演 |
| `strategy.copy` | 复制方案（含源/目标元数据与脚本） | 单次 ≤10；默认不启动、保留 `lastSync`、副本为停止且未上线；`dryRun` 只返回计划 |

> **首选姿势**：`strategy.copy` 复制成熟方案 → 在副本上 `strategy.update`/`source.update`/`target.update` →
> `checkList` → `online`。比 `strategy.create` 从空白配 200 个字段稳得多（见 `01-platform-model.md` §8）。

---

## 6. strategy 生命周期（5，🟠 `strategy:ops`，均 ✅ 需确认）

| Tool | 用途 | 注意 |
|---|---|---|
| `strategy.start` | 启动调度（cron 生效） | 启动前自动备份源/目标配置；幂等 |
| `strategy.stop` | 停止调度 | **清理类操作的前置条件**；幂等 |
| `strategy.online` | 置为已上线 | 默认先查 check-list，有未确认项 → `check_list_blocked`；`force=true` 可跳过（高风险，会标注 `forced` 并写审计）。**上线 ≠ 启动** |
| `strategy.offline` | 置为未上线 | `stopFirst=true`（默认）会先停止，避免"已下线但仍在产数据" |
| `strategy.checkList` | 读上线检查项 | 只读，不代勾 |

---

## 7. strategy 数据与清理（6）

| Tool | 风险 | 用途 | 关键点 |
|---|---|---|---|
| `strategy.data.import` | 🟡 write ✅ | 向源数据集合导入 JSON 行（不自动写目标） | 单次 ≤1000 行、≤1MB；行内禁 `$` 开头键；`duplicatePolicy=skip\|error`；`autoDispatchTarget=true` 才会立即触发目标调度（需 ops 权限） |
| `strategy.data.setStatus` | 🟠 ops ✅ | 改指定数据条目状态 | **只收语义词**；`await`=重新推送、`unhandle`=丢弃。**不要传裸数字**（0 与 2 的语义与直觉相反） |
| `strategy.dbResetStatus` | 🟠 ops ✅ | 把**所有**数据重置为等待 + 清目标异常队列 | 全量操作，影响面大 |
| `strategy.data.clean` | 🔴 destructive ✅ | 清空数据条目（保留日志与队列） | 要求停止且未上线；**不可恢复**；先 `dryRun` |
| `strategy.queue.clean` | 🔴 destructive ✅ | 清空源/目标队列 + 数据重置 | 同上 |
| `strategy.data.cleanAll` | 🔴 destructive ✅ | 清空日志 + 数据 + 双队列 | 破坏性最强 |

**破坏性工具的执行矩阵**（重要）：

| 场景 | 行为 |
|---|---|
| 不带 `confirmationToken` | **总是**返回 `precheck`（影响面条数）；`trust=confirm/guarded` 或影响面 > `MCP_DESTRUCTIVE_MAX_ROWS`(默认 1000) 时**额外**返回 `confirmationToken` |
| 带 `confirmationToken` | 校验并核销；无效/过期/已用/参数变了 → `confirmation_token_invalid` |
| `dryRun=true` | 只返回 `precheck`，不执行 |
| 影响面超阈值（即使 `trust=full`） | 强制要求令牌，`block_reason=impact_exceeds_threshold` |

---

## 8. script（6）

| Tool | 风险 | 用途 | 关键点 |
|---|---|---|---|
| `script.list` | 🟢 | 列脚本（名称/事件/方向/状态/排序） | 源码用 `script.get` |
| `script.get` | 🟢 | 读源码 | 不传 `scriptId` 返回该方案全部脚本 |
| `script.validate` | 🟢 | **语法自检（`php -l`）**，无副作用 | 返回 `ok`/`errors[].line`/`errors[].message`；缺 `<?php` 会自动补齐再校验 |
| `script.create` | 🟡 write ✅ | 新建事件脚本 | 仅平台管理员（`user_id ≤ 1`）；同方案同事件唯一；≤64KB；**落库前 `php -l`，语法错直接拒** |
| `script.write` | 🟠 ops ✅ | 改写脚本（写前备份） | 同样先 `php -l`，失败不覆盖原脚本 |
| `script.delete` | 🔴 destructive ✅ | 删除脚本（含运行时文件） | 需方案未上线且未运行；**备份失败即中止** |

> 写脚本前务必先读 `01-platform-model.md` §7：**14 个事件里只有 5 个真会触发**，
> 目标端异常还会被静默吞掉。

---

## 9. audit（1，🟢 `audit:read`）

### `audit.search`
查本租户 MCP 调用审计（倒序分页）。`tool`/`status`/`errorCode`/`grantId`/时间窗（≤31 天）/`pageSize`≤100。

- `payload`：`none`（默认）/ `summary`（只给字段名与字节数）/ `full`（脱敏后的结构化载荷，含 `字段 → 值` 映射）。
- `includePayload=true` 等价于 `payload=full`（兼容保留）。
- 用途：**回答"谁在什么时候改了什么"**，尤其 `strategy.target.update` 的 `patch`。

---

## 10. 工具选择速查

| 我想… | 用 |
|---|---|
| 判断能不能干 | `meta.capabilities` |
| 找方案 | `strategy.list`（支持 UUID 前缀） |
| 一次看清方案健康度 | `strategy.dbInfo` |
| 看配置长什么样 | `strategy.get {sections:"source"}` / `strategy.showConfig` |
| 触发一次取数 | `strategy.dispatchSource` |
| 看任务参数 | `strategy.queue.job.get` |
| 手工跑一条任务 | `strategy.queue.job.run` |
| 改参数重跑（不动元数据） | `strategy.queue.job.update` → `queue.job.run {force:true}` |
| 看这次请求/响应正文 | `strategy.log.search {level:"debug", jobId}` |
| 定位真实失败原因 | `exception.search` + `log.search {level:"error,fatal"}` |
| 改字段映射 | `strategy.target.update`（先 `showConfig`） |
| 回滚配置 | `strategy.config.rollback` |
| 新方案（推荐） | `strategy.copy` → 改 → `checkList` → `online` |
| 重推错误数据 | `data.setStatus {status:"await"}` → `dispatchTarget` → `queue.job.run` |
| 查谁改了什么 | `audit.search {payload:"full"}` |
