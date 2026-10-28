# 07 · 安全边界、密钥与限制

> 这一篇是"动手前的红线"。任何写操作/清理操作之前，先确认自己没踩到下面任何一条。

---

## 1. 密钥：两种端点、三种档位

### 1.1 两类端点

| 类型 | 端点 | 密钥前缀 | 状态 | 用途 |
|---|---|---|---|---|
| 租户 Datahub MCP | `https://<租户>/api/mcp` | `sh-…` | 有状态（`Mcp-Session-Id`） | 读写该租户的方案/数据 |
| 公开知识 MCP | `https://mcp.qeasy.cloud/api/mcp` | `qk_live_…` | 无状态 | 只读官方知识 |

**它们不通用**：`qk_` 只能查知识，`sh-` 才能动数据。

### 1.2 Datahub 密钥的三个档位

| 档位 | 能做什么 | 危险操作的确认方式 |
|---|---|---|
| `read_only` | 只读工具 | 写操作直接拒绝（`mode=read_only`） |
| `standard` | 只读 + `strategy:ops` + `audit:read` | 需 `confirmationToken` |
| `full` | 全部 9 个 scope | 默认直接执行，**但仍返回 `precheck`**；影响面 > 阈值时强制令牌 |

> 判断"我这把钥匙能干什么"：`meta.whoami`（拿到 `scopes`/`trust`/`mode`）+ `meta.capabilities`（逐工具的 `callable`）。

### 1.3 密钥拿不到 / 失效时

1. `401` + `需要 API Key` → 密钥缺失/被吊销；
2. 让租户管理员在「开放中心」重新签发（**平台不提供自助找回**，库里只存 hash）；
3. **不要**试图复用他人密钥，也不要把它写进脚本/仓库。

> ⚠️ 真实事故：在**共用同一个库**的开发环境跑会重建 `dh_mcp_grant` 的 PHPUnit 测试，
> 会**清空该环境所有 MCP 密钥**（本仓库已在测试里加了 `MCP_TEST_ALLOW_SCHEMA_RESET` 安全阀）。
> 如果你发现"昨天还能用今天全 401"，先查是不是有人跑了测试。

---

## 2. 影响面熔断（不是故障）

| 场景 | 行为 |
|---|---|
| 不带 `confirmationToken` 调用破坏性工具 | **总是**返回 `precheck`（`total_rows_to_remove` 等） |
| `trust=confirm/guarded` | 额外返回 `confirmationToken`（120 秒、一次性、绑定参数） |
| 影响面 > `MCP_DESTRUCTIVE_MAX_ROWS`（默认 **1000** 行） | **即使 `trust=full` 也强制令牌**，`block_reason=impact_exceeds_threshold` |
| 带令牌但过期/已用/参数变 | `confirmation_token_invalid` |
| 只想看不想做 | `dryRun=true` |

> 设计口径：**高权限意味着"免于逐次确认"，不是"免于知情、免于复核"**。
> 误删 10 行和误删 10 万行不是同一量级的事故。

---

## 3. 外部写入：唯一不能被信任级别豁免的操作

`strategy.queue.job.run {direction:"target"}` 会**真实写入外部 ERP**（如金蝶 `batchSave`），
平台**无法回滚**。因此：

```jsonc
{"strategyId":"…","direction":"target","jobId":"…","confirmWrite":true}  // 少了就 external_write_unconfirmed
```

- 写入前必须看 `queue.job.get` 的 `params.Model`（这是最后的人工复核点）。
- 写入后必须**回查外部系统**；平台 `status=FINISHED` 只代表报文成功。
- 高价值单据建议"先查后写"（`executeBillQuery` 按单号查存在性）。

---

## 4. 租户边界

- 所有工具都按密钥所属租户收敛；`strategyId`/`connectorId` 不属于本租户 →
  `strategy_access_denied` / `connector_not_found`（**不回显对方内容**）。
- `platform` / `api` 是**全局目录**（不分租户），`connector`/`strategy`/`data` 分租户。
- 不要用"遍历 UUID"的方式探测他人资源——会触发审计与限流，且没有正当用途。

---

## 5. 凭据卫生（最容易出事的一条）

| 通道 | 是否会返回凭据明文 |
|---|---|
| Datahub MCP | ❌ 不返回；连接器只给 `credentialsConfigured`，账号/appId 部分脱敏 |
| 公开知识 MCP | ❌ 不含租户数据 |
| **平台 REST** | ⚠️ **会明文返回 `app_secret`** |

因此：
1. 不要用 REST 拉连接器配置后落盘/贴日志/写进报告；
2. 报告里引用连接器时只写 `connectorId` / 名称 / 环境 / host（MCP 已脱敏）；
3. 截图/日志脱敏后再外发；
4. 怀疑泄露 → 让管理员在平台轮换 `app_secret`（MCP **没有**改凭据的工具，这是刻意设计）。

---

## 6. 限流与批量

- **120 次/分钟/密钥**（固定窗口）。超限 `429` + `Retry-After`。
- 批量巡检建议 ≤100 次/分钟；42 个方案全量体检约 43 次调用，安全。
- 不要并发压测；需要"扫全量"时分页（`pageSize ≤100`）+ 间隔。
- 大批量操作（导入/重推）优先"分批 + 每批验证"，不要一次性打满。

---

## 7. 审计：所有调用都可回溯

- 每次 MCP 调用写 `dh_mcp_audit`：who / tool / 参数摘要 / 结果 / 耗时 / 成败 / IP / client。
- 查询：`audit.search`；`payload=full` 可看到**结构化载荷**（含 `字段 → 值` 映射，已脱敏）。
- 典型用途：回答"谁在什么时候改了目标端映射"——`audit.search {tool:"strategy.target.update", payload:"full"}`。
- 审计**不可关闭**；`full` 档也一样。

---

## 8. 清理类操作的前置条件（违反会被拒）

| 操作 | 前置 | 不可恢复 |
|---|---|---|
| `strategy.data.clean` | 方案停止 + 未上线 | ✅ 数据条目 |
| `strategy.queue.clean` | 同上 | ✅ 双队列 + 数据状态 |
| `strategy.data.cleanAll` | 同上 | ✅ 日志 + 数据 + 队列 |
| `script.delete` | 未上线 + 未运行 + 管理员 | ✅ 脚本（会先备份，备份失败即中止） |

**标准顺序**：`strategy.stop` → `dryRun` 看影响面 → 带令牌执行 → `dbInfo` 复核归零。

---

## 9. 出事时的止损顺序

1. **停**：`strategy.stop`（阻断后续调度）；
2. **隔离**：`strategy.offline`（置未上线，避免误启动）；
3. **取证**：`log.search` + `exception.search` + `audit.search`（先留证据再改）；
4. **回滚**：配置类用 `strategy.config.rollback`；数据类不可回滚，只能重推；
5. **复盘**：把"哪一步缺了护栏"写进 `08-anti-patterns.md` 或 issue。
