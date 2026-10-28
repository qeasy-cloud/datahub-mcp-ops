# P3 · 从需求到上线：一个集成方案的完整实施

> 对应人类实施顾问的标准流程：**谈需求 → 写方案 → 配方案 → 调试 → 上线 → 交接**。
> Agent 的差异只有两点：① 先做"可执行性侦察"再谈方案；② 每一步都留可复核的证据。

---

## 阶段 0 · 侦察（10 分钟，只读）

| 要弄清 | 怎么查 |
|---|---|
| 两端是什么系统 | `asset.platform.list` / `asset.platform.get` |
| 有没有现成连接器（哪个环境） | `asset.connector.list`（看 `env`/`host`/`dataCenter`） |
| 目标对象走哪个接口 | `asset.api.list {platformId, effect:"EXECUTE"}` |
| 源对象走哪个接口 | `asset.api.list {platformId, effect:"QUERY"}` |
| 字段要哪些、必填是什么 | `asset.api.get {apiId, includeFields:true}` + 知识 MCP（`06-knowledge-mcp.md`） |
| 有没有可复制的成熟方案 | `strategy.list`（同平台/同对象） |

**产出**：一页"可行性 + 选型"结论（接口、增量字段、幂等键、主子表形态）。
**红线**：连接器指向 `production` 时，先确认是否允许写生产（`07-security-and-limits.md` §3）。

---

## 阶段 1 · 方案设计（写给客户看）

必须明确的 8 个决策（缺一个后面就会返工）：

| # | 决策 | 常见选项 | 影响 |
|---|---|---|---|
| 1 | 同步方向 | A→B / B→A / 双向 | 双向要防自循环 |
| 2 | 触发方式 | cron 定时 / 手工 / 前置串行 | 用 `*_dispatch_condition` 做两段式 |
| 3 | 增量口径 | `modified` + 回看窗口 / `created` / 全量 | 决定"改单会不会过来" |
| 4 | 分页策略 | 平台默认 / 显式 `page_size` | 决定"会不会只取第一页" |
| 5 | 幂等键 | 业务单号 / 唯一编码 | 决定"重跑会不会出两张单" |
| 6 | 主子表形态 | 一单一条（别名 `_Flist`）/ 一单多行 | 决定 `id` 取值与对账粒度 |
| 7 | 字段映射范围 | 必填 + 业务关键字段 | 越少越稳，后续按需加 |
| 8 | 失败处理 | 重试 / 人工介入 / 反向链路 | 作废删除要有独立策略 |

**产出**：集成方案文档（对象、字段映射表、增量条件、幂等键、异常处理、验收标准）。
**技巧**：用知识 MCP 查同类案例，把"客户特殊约定"写进文档，别只写通用字段。

---

## 阶段 2 · 配置（优先复制，不要从零建）

```bash
# ① 找可复制的成熟方案（同平台 + 同对象最理想）
dh call strategy.list --args '{"search":"客户","pageSize":20}'

# ② 复制（默认不启动、保留 lastSync、副本停止且未上线）
dh call strategy.copy --args '{"strategyId":"<成熟SID>","name":"<新方案名>","count":1}'
# → {"newStrategyId":"…"}（顶层字段；detail 里也有 strategies[].strategyId）
```

```bash
# ③ 改基本信息（名称/编码/分组/cron）
dh call strategy.update --args '{"strategyId":"<新SID>","patch":{
  "name":"…","group":"…","sourceCrontab":"0 2 * * *","targetCrontab":"30 2 * * *"}}'

# ④ 改源端（过滤条件/字段白名单）
dh call strategy.source.update --args '{"strategyId":"<新SID>","patch":{ … }}'

# ⑤ 改目标端（字段映射）
dh call strategy.target.update --args '{"strategyId":"<新SID>","patch":{ … }}'
```

- 每次 `update` 都返回 `backup.historyId`/`md5` —— **记下来**。
- 只改要改的键，用 `patch`（浅合并）；`metaData` 整体替换容易丢字段。
- 改完立刻 `strategy.showConfig` 复核一次（别攒到最后）。

> 没有可复制方案时才用 `strategy.create`：`source` 必须 `effect=QUERY`、`target` 必须 `effect=EXECUTE`；
> 不给 `metaData` 会自动套用接口资产默认快照。先 `dryRun:true` 验证。

---

## 阶段 3 · 调试（核心，见 P1/P2）

```bash
dh call strategy.dbInfo --args '{"strategyId":"<SID>"}'            # 基线
# 源侧
dh call strategy.dispatchSource --args '{"strategyId":"<SID>"}'
dh call strategy.queue.job.run  --args '{"strategyId":"<SID>","direction":"source","jobId":"…"}'
# 目标侧
dh call strategy.dispatchTarget --args '{"strategyId":"<SID>"}'
dh call strategy.queue.job.get  --args '{"strategyId":"<SID>","direction":"target","jobId":"…"}'
dh call strategy.queue.job.run  --args '{"strategyId":"<SID>","direction":"target","jobId":"…","confirmWrite":true}'
```

调试顺序（别跳）：
1. 源侧取到数（`has_data=true`）；
2. 目标报文核对（`params.Model` 无 null、基础资料是对象）；
3. 目标写入成功 + **外部回查**；
4. 幂等复验（重跑变 `repeat`）；
5. 改一条源数据，验证增量能取到（`modified` 水位）；
6. 边界：空数据、单条、批量各跑一次。

---

## 阶段 4 · 上线

```bash
# ① 上线检查项（只读，不代勾）
dh call strategy.checkList --args '{"strategyId":"<SID>","direction":"source"}'
dh call strategy.checkList --args '{"strategyId":"<SID>","direction":"target"}'
#    blockingCount > 0 → 先在平台完成确认；不要用 force 蒙混

# ② 上线（≠ 启动）
dh call strategy.online --args '{"strategyId":"<SID>"}'

# ③ 启动调度
dh call strategy.start --args '{"strategyId":"<SID>"}'

# ④ 观察一个周期
dh call strategy.dbInfo --args '{"strategyId":"<SID>"}'
```

- `force=true` 可在有阻断项时强行上线（高风险，会标注 `forced` 并写审计）——**只在明确知情时用**。
- 上线后第一小时看 `log.error/fatal` 与 `queue.error`；失败率 >5% 视为异常。

---

## 阶段 5 · 交接

交付物（缺一不可）：

1. **方案清单**：`strategyId`、名称、源/目标平台与连接器、cron；
2. **字段映射表**：目标字段 ← 源字段（含 parser）；
3. **运行参数**：增量条件、分页、幂等键、`operation`；
4. **验收证据**：`run` 的关键返回（行数/状态）+ 外部回查结果；
5. **风险与回滚**：`backup.historyId`、清理方式、反向链路是否具备；
6. **运维手册**：常见报错 → 处置（引 `05-diagnostics.md`）。

模板：`../templates/strategy-blueprint.md`、`../templates/ops-report.md`。

---

## 时间盒参考

| 阶段 | 简单对象（无明细） | 复杂对象（主子表+多基础资料） |
|---|---|---|
| 侦察 | 10 min | 30 min |
| 设计 | 30 min | 2 h |
| 配置 | 20 min | 2–4 h |
| 调试 | 30 min | 半天–2 天 |
| 上线+观察 | 30 min | 1 天 |

> 复杂度的主要来源不是字段数量，而是**基础资料 parser**、**主子表形态**、**幂等键选择**。
