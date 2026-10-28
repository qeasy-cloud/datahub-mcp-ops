# P2 · 让目标端真正写进去（含外部副作用）

> 目标：把平台里的数据写成外部系统（如金蝶）的一张单，并**证明**它真的进去了。
> ⚠️ 本流程会产生**不可回滚的外部副作用**。执行前必须有人明确同意"可以写测试账套/生产"。

---

## 0. 安全闸门（先过三道）

| # | 检查 | 做法 |
|---|---|---|
| 1 | 写哪个环境？ | `asset.connector.get` 看 `env`（development/test/production）、`host` |
| 2 | 写什么？ | `queue.job.get` 的 `params.Model` —— **逐字段核对**，这是最后复核点 |
| 3 | 谁同意？ | 生产环境必须有人工确认；测试环境至少确认"允许写入测试账套" |

> 任何一道不过 → 停在这里，不要执行 `queue.job.run {direction:"target"}`。

---

## 1. 准备数据

```bash
# 若源侧还没跑通，先做 P1
dh call strategy.data.search --args '{"strategyId":"<SID>","status":"await","pageSize":5}'
```

✅ 至少有 1 条 `await` 数据。
❌ 全是 `error`/`finished` → 先 `data.setStatus {status:"await"}` 或重新取数。

---

## 2. 触发目标调度

```bash
dh call strategy.dispatchTarget --args '{"strategyId":"<SID>"}'
# → {"mode":"debug","jobId":"<TID>","next_step":"…queue.job.run(direction=target, confirmWrite=true)…"}
```

✅ 拿到 24 位 `jobId`。

---

## 3. 核对报文（**关键步骤**）

```bash
dh call strategy.queue.job.get --args '{
  "strategyId":"<SID>","direction":"target","jobId":"<TID>","rawParams":true}'
```

> 必须带 `rawParams:true`：默认会把深层结构折叠成 `{"__object":true,"__count":9}`，
> 看不到 `Model` 里的真实字段值，这一步就白做了。

逐项检查 `params`：

| 检查 | 通过标准 | 不通过时 |
|---|---|---|
| `FormId` | 与业务对象一致（如 `BD_Customer`/`SAL_SaleOrder`） | 改 `target.update` 的 `otherRequest` |
| `Model` 字段值 | 都是真实值，**不是 null/空串** | 改映射 `{{源字段}}` |
| **值翻译** | 如 `FSex` 已是目标系统枚举（`1/2`），不是源系统的 `男/女` | 挂静态映射：见下方「映射自检」 |
| 基础资料字段 | 形如 `{"FNumber":"…"}` | 加 `ConvertObjectParser` |
| 明细 | 数组里有内容（或本对象确实无明细） | 检查 `_Flist` 别名 |
| 单号 | 稳定业务单号（不是时间戳/随机） | 修 `id`/`number` 与映射 |

#### 映射自检（值没被翻译时按顺序做）

```bash
dh call mapping.usage    --args '{"categoryId":"<CID>"}'          # ① 真的挂上了吗（refCount>0）
dh call mapping.resolve  --args '{"categoryId":"<CID>","value":"男"}'   # ② matched 是 exact/wildcard/none
dh call mapping.relation.list --args '{"categoryId":"<CID>","search":"男"}'  # ③ 表里到底有没有这行
```

- `matched=none` → 无精确行也无 `a_value="*"` 兜底 → 运行时**原值直通、不报错**，这就是"没生效"。
- 挂在**源端顶层标量**上不会生效（源端只有 object/array 子项走映射）→ 改成挂目标端字段。
- 方向反了就加 `"direction":"reverse"`。

> 这一步就是"人类在调试面板上点开请求体看一眼"的等价物。**不要跳**。

---

## 4. 执行写入

```bash
dh call strategy.queue.job.run --args '{
  "strategyId":"<SID>","direction":"target","jobId":"<TID>","confirmWrite":true}'
```

判读：

| 返回 | 含义 | 下一步 |
|---|---|---|
| `ok=true, status_after=2` | 报文成功 | 第 5 步回查 |
| `ok=true, response_excerpt` 为空 | 对方空响应（可能成功） | **必须回查** |
| `ok=false` | 失败 | 看 `exceptions` → `04-write-recipe.md` §6 |
| `code=external_write_unconfirmed` | 没带 `confirmWrite` | 确认后重调 |

---

## 5. 回查（这一步才算"写进去了"）

按目标系统的查询接口核对：

```bash
# 例：金蝶 executeBillQuery 按单号查
dh call strategy.data.search --args '{"strategyId":"<SID>","number":"<业务单号>"}'
# 外部系统侧：用 executeBillQuery / 平台界面 / 数据库确认
```

三条都要满足：
1. 外部系统能按单号查到该单；
2. **明细行数**与源一致；
3. 关键字段（客户/日期/金额）一致。

---

## 6. 幂等复验

再跑一次同一条数据：

```bash
dh call strategy.queue.job.run --args '{
  "strategyId":"<SID>","direction":"target","jobId":"<TID>","force":true,"confirmWrite":true}'
```

✅ 期望：目标报"编码唯一/已存在"，数据变 `repeat`，**不产生第二张单**。
❌ 产生第二张单 → 幂等键不稳定（用了时间戳/随机数），回到 `04-write-recipe.md` §5。

---

## 7. 收尾

```bash
dh call strategy.dbInfo --args '{"strategyId":"<SID>"}'    # 数据/队列状态
dh call strategy.data.clean --args '{"strategyId":"<SID>","dryRun":true}'
```

- 测试数据是否清理，取决于"是否要留给客户看"。
- **外部系统里已经写入的单据不会因平台清理而消失**——需要人工在外部系统处理。

---

## 完成标准

- [ ] `params.Model` 核对通过（无 null、基础资料已转对象）
- [ ] `run {confirmWrite:true}` 返回 `ok=true`
- [ ] 外部系统按单号查得到，明细行数一致
- [ ] 重跑变 `repeat`，不产生第二张单
- [ ] 报告里写明：写了哪个环境、哪张单、如何回查

## 失败快查

| 报错 | 去哪 |
|---|---|
| 格式错误/字典类型 | `04-write-recipe.md` §6（加 parser） |
| 没有数据需要保存 | `04` §6（映射为空） |
| 组织内编码唯一 | 正常（幂等） |
| 基础资料字段值不存在 | `05-diagnostics.md` §3（源数据脏） |
| 响应为空 | 重推一次；仍空则查会话/并发 |
