# 05 · 诊断字典：症状 → 判据 → 处置

> 用法：先按症状定位到小节，再按"判据"列**取证据**（哪次调用、看哪个字段），最后按"处置"动作。
> 不要凭直觉改配置——先拿到证据，再动手。

**取证据的三件套**（几乎所有问题都从这三个开始）：

```bash
dh call strategy.dbInfo    --args '{"strategyId":"<SID>"}'      # 整体：日志/数据/队列/最近一次
dh call strategy.queue.list --args '{"strategyId":"<SID>","direction":"source"}'
dh call strategy.log.search --args '{"strategyId":"<SID>","level":"error,fatal"}'
```

---

## 1. 数据不增加

| 判据 | 原因 | 处置 |
|---|---|---|
| `strategy.get` 返回 `status=0` 且 `is_online=false` | 调试期正常：方案没启动，也没守护进程 | `dispatchSource` + `queue.job.run`（见 `03-debug-loop.md`） |
| 队列有 job，状态长期 5/0 | **没有消费者** | `queue.job.run` 手工消费 |
| 有守护进程但不动 | `dispatcher_num` 与实际 dispatcher 编号不匹配 | 核对编号；或调整方案归属 |
| `dbInfo.data` 全 0、队列也空 | 调度根本没触发 | 查 `source_crontab`、`status`、`dispatcher_num` |
| `log.error/fatal` > 0 | 源接口报错 | `log.search(level=error,fatal)` + `exception.search` |
| 只有 `begin_` 日志 | 队列未被消费（同上） | 手工消费 |
| 前置方案在跑 | `*_dispatch_condition` 卡住，300 秒后重投 | 等；或临时摘前置条件 |

---

## 2. 数据有，但没写目标

| 判据 | 原因 | 处置 |
|---|---|---|
| 目标队列为空 | 没触发目标调度 | `dispatchTarget`（停止态可用） |
| 目标队列有 job 但不动 | 无消费者 | `queue.job.run {confirmWrite:true}` |
| `params.Model` 字段全空 | **裸字段名被当常量**（头号原因） | `target.update` 改 `{{源字段}}` |
| `params.Model` 缺必填 | 映射不全 | 按接口资产补字段 |
| 数据 `status=3` | 写入失败 | 看 `result[].problem` + `exception.search` |
| 数据 `status=6` | 被标记"跳过调度" | 确认是否人为设置；需要时 `data.setStatus {status:"await"}` |

---

## 3. 写入报错（目标侧）

| 报错文本 | 原因 | 处置 |
|---|---|---|
| `格式错误，不能转换为字典类型` | 基础资料字段传标量 | 加 `ConvertObjectParser`，`params=FNumber` |
| `没有数据需要保存` | 字段全空/被 `removeParamsNull` 丢弃 | 核对映射与源数据 |
| `组织内编码唯一` / `已存在` | 幂等命中 | 正常；确认数据变 `repeat` |
| `基础资料字段值不存在` | 源编码在目标不存在 | 清洗源数据 / 先在目标建档案 |
| `必填字段不能为空` | 缺字段 | 补 `request[]` |
| `金蝶写入响应数据为空` | 会话并发/空响应 | 重推一次 |
| `其它响应参数没有定义接口状态参数` | `otherResponse` < 2 项 | 补齐位置槽（见 `04-write-recipe.md` §2.2） |
| `SQLSTATE…` / 连接失败 | 连接器/网络 | `asset.connector.get` 看 host/环境；基础设施问题转人工 |

---

## 4. 队列堆积 / 一直重试

| 判据 | 原因 | 处置 |
|---|---|---|
| `retries` 递增、状态反复 | 有毒数据在重试 | **先修数据/参数，再 `run {force:true}`**；不要放着等退避 |
| 退避间隔越来越长 | 平台指数退避（20s→300s→3600s→14400s→72000s） | 默认拉满约 25 小时；`max_retries=3` 约 65 分钟 |
| 队列 error 计数很高 | 批量失败 | `queue.clean` 前先导出证据（`queue.list` 分页 + `log.search`） |

> 调试期一律用 `queue.job.run` 拿即时报错，**不要**把坏数据留在队列里等守护进程退避。

---

## 5. 巡检类误判（最容易浪费时间的坑）

| 症状 | 真相 | 正确读法 |
|---|---|---|
| `dbInfo.log.fatal = 3`，`exception.search` 为 0 | 调试留痕被写成 FATAL（老版本） | 看日志文本是否 `0x_debug_` 开头 → 是则**不是错误**；新版已改为 `debug` 计数 |
| `dbInfo.data.error > 0` 但 `queue` 全 0 | 历史错误数据未清理 | 看 `error` 是否还在增长；不增长即历史残留 |
| `strategy.list` 里状态"运行中"但没数据 | 运行 ≠ 有消费者；可能 `dispatcher_num` 不匹配 | 看队列与 `last_run` |
| `dispatchSource` 返回成功但队列空 | 旧版本在停止态会"假成功" | 用 `queue.list` 确认；新版停止态会真的入队并回传 `jobId` |
| `run` 返回 `ok=true` 就以为写完了 | `ok` 只表示执行成功，可能是空响应 | 必须看 `has_data` + 回查外部系统 |

**平台整体基线**（判断"正常"的参照）：累计处理 7,132 万条，失败率 ≈ **3.0%**。
单方案失败率 > 5% 才视为异常。

---

## 6. 权限 / 限流 / 协议类

| 现象 | 原因 | 处置 |
|---|---|---|
| `401` / `需要 API Key` | 密钥缺失/被吊销 | 重新签发（`references/07-security-and-limits.md` §1） |
| 工具不可见 | scope 不含该工具 | `meta.capabilities` 看 `callable`；换密钥或加 scope |
| `read_only` 模式下写操作被拒 | 密钥是只读档位 | 换 `standard`/`full`，或只做只读任务 |
| `429` + `Retry-After` | 超 120 次/分钟 | 等 `Retry-After` 秒；批量巡检压到 100/分钟以内 |
| `confirmation_token_invalid` | 令牌过期(120s)/已用/参数变了 | 不带令牌重新调用取新令牌 |
| `impact_exceeds_threshold` | 影响面超阈值 | 复核 `precheck` 后带令牌执行（不是故障） |
| `external_write_unconfirmed` | 目标侧缺 `confirmWrite` | 确认后加 `confirmWrite=true` |
| `strategy_running_guard` | 运行中改任务参数 | 先 `stop`，或 `allowRunning=true` |
| `strategy_not_running` | 传了 `requireRunning=true` | 去掉该参数 |

---

## 7. 五分钟定位流程（不知道从哪下手时用这个）

```
1. meta.whoami                      → 我是谁、什么档位
2. strategy.get {sections:basic}    → 方案存在吗、运行/上线状态
3. strategy.dbInfo                  → 日志/数据/队列/最近一次，一眼看全
4. 看 last_run：
   ├─ 没有 last_run → 从没跑过 → dispatchSource（或 dispatchTarget）
   └─ 有 last_run → 看 ok / has_data / status
5. 按 §1–§4 对应小节取证据
6. 改动作（参数优先，元数据最后），再跑一次
```

> 拿到证据再动手；每一步都要能回答"我这次调用想验证什么"。
