# 01 · 平台机制：运行时、元数据、取值与幂等

> **这一篇的作用**：把"轻易云集成平台到底怎么跑"压缩成 Agent 可直接使用的一页知识，
> 让你**不必每次去查知识 MCP** 就能读懂配置、判断故障、写出正确的字段映射。
>
> 来源：本仓库 `service/docs/knowledge/domains/*`（2026-10-26 版，该系列由源码 + 5,271 条在跑方案实测交叉验证）。
> 每节末尾标注了源文档，需要更深的证据链再回查。**蒸馏不替代原文**：涉及具体平台的字段名/端点差异时，
> 仍应用知识 MCP 查最新对象卡（见 `06-knowledge-mcp.md`）。

---

## 0. 三句话定位

1. 平台在**两个系统之间搬数据**，把"搬"拆成可观测的步骤：调度 → 取数 → 落地 → 入队 → 写入 → 日志。
2. 一条方案（`strategy`）的能力 **不来自接口资产**，而来自元数据里的**字段集 × 过滤条件 × 字段映射 × 脚本**。
3. 平台负责"写"，**不负责"撤"**：源单作废/删除/反审核，目标单不会自动跟着变。

---

## 1. 三层元数据模型（配错的根因都在这三层之间错位）

```
① 接口资产 dp_api_asset           业务对象身份 + 协议模板（平台维护，全租户共享）
   └ other_request：FormId=SAL_SaleOrder、默认 FilterString、分页、FieldKeys={{MAIN_REQUEST}}
   └ request / response：字段目录（金蝶单接口可达 200+ 字段）
                 ↓ 实例化（方案创建时**一次性快照**）
② 方案元数据 meta_data           业务参数：选哪些字段、覆盖什么值（source / target 各一份）
                 ↓ 运行时求值
③ 适配器 adapter                 求值 + 组装真实报文 + 解析响应（按平台硬编码）
```

**三条最常踩的推论**

| 现象 | 真实原因 |
|---|---|
| 找不到 `FormId` 在哪填 | `FormId` 属于**接口资产**，不在方案元数据里；方案只在需要覆盖时才在 `otherRequest` 出现 |
| 改了接口资产默认值，老方案没生效 | `meta_data` 是**快照**，不随资产变更回灌；要么重开方案，要么直接改 meta_data |
| 同名 `api` 在不同平台行为完全不同 | `api` 只是接口 code，语义由**适配器**解释 |

> 源：`domains/01-metadata-model.md` §2、`domains/06-metadata-reuse.md`

---

## 2. `meta_data` 字段全表（读配置时按这张表看）

| 字段 | 含义 | 坑 |
|---|---|---|
| `api` | 接口 code（SDK 第一参数）。金蝶 `batchSave`/`executeBillQuery` | 不是 URL，不是方法名 |
| `type` | **双重历史语义**，见 §2.1 | **不可用来判断读写** |
| `effect` | 新资产代的读写方向（`QUERY`/`EXECUTE`） | 只有新资产才有 |
| `method` | HTTP 动词（SDK 第三参数） | 与 `operation.method` 同名不同义 |
| `id` / `number` | 主键 / 单号的取值路径，落 `ADATA.id` / `ADATA.number` | 空串会让去重与回查失效 |
| `pagination.pageSize` | 每页条数 | 只有 `pageSize` 被消费 |
| `request[]` | 主请求参数树 | 源端=查询参数/FieldKeys；目标端=写入字段 |
| `otherRequest[]` | 附加参数树，与 `request` **合并**进请求体 | 金蝶 `FormId`/`Operation`/`FilterString`/`Limit` 都在这 |
| `response[]` | 响应字段树 | 源端=取哪些列；目标端=回写哪些列 |
| `otherResponse[]` | **按位置约定**的 4 个槽位，见 §2.2 | 缺项直接报错 |
| `idCheck` | **ADATA 落库去重开关**，默认 `true` | 与目标写入无关，别乱改（§1.3） |
| `buildModel` | `true` 时按 `response[]` 重建 content 再落库 | 实测仅 3–4% 方案开启 |
| `autoFillResponse` | `true` 且 `response[]` 为空时，用首条响应反推字段并**回写 meta_data** | 源端 47.5% 方案开启（"自动识别字段"） |
| `operation` | 目标端取行策略，见 §3.4 | 批量写入必须配 |

`request[]` 每项：

| 键 | 作用 | 说明 |
|---|---|---|
| `field` | 参数名 / 写入键 | 目标端就是金蝶字段名 `FBillNo` |
| `type` | `string/int/float/bool/date/datetime/timestamp/array/object` | `buildModel=true` 时按此强转 |
| `value` | 默认值或取值表达式 | 源端常 `{{LAST_SYNC_TIME\|datetime}}`；目标端常 `{{源字段}}` |
| `parent_id` | 树父指针 | 仅用于拼 `children` |
| `key` / `physicalModel` / `formModel` / `tableModel` | **运行时不消费**，纯 UI | 别把业务逻辑写在这 |

### 2.1 `type` 的双重语义（务必按此判断）

- **旧资产代**（`dh_platform_api`）：`type` 恰好等于 `QUERY`/`EXECUTE`，看起来像方向。
- **新资产代**（`dp_api_asset`）：`type` 是**协议类型**（`WebAPI`/`RESTful`/`SQL`/`WebService`），方向另存 `effect`。

> **规则**：判断"这是查询还是写入"只看它挂在 `source` 还是 `target`；
> 判断协议看接口资产的 `type`；判断读写看接口资产的 `effect`。
> **永远不要用 `meta_data.type` 判断方向。**

实测分布（4,303 条在跑方案）：源端 `QUERY` 2,813 / `WebAPI` 1,352；目标端 `EXECUTE` 2,395 / `WebAPI` 1,579。

### 2.2 `otherResponse` 的四个位置槽（硬约定，缺就报错）

| 下标 | 含义 | 缺失后果 |
|---|---|---|
| `[0]` | 状态字段路径 | 源端需 ≥3 项、目标端需 ≥2 项，否则报`其它响应参数没有定义接口状态参数` |
| `[1]` | 成功值 | 同上 |
| `[2]` | 数据字段路径 | 同上 |
| `[3]` | 页码/翻页字段名 | 缺则翻页判断失效 |

### 2.3 `idCheck`：保持默认 `true`，不要"修"它

它是 **ADATA 落库去重开关**，与目标写入无关：

| `idCheck` | ADATA 落库行为 |
|---|---|
| `true`（默认） | 纯插入，同一 `id` 会落多行 |
| `false` | 按 `id` 更新已有行（upsert） |

金蝶目标写入路径**不读**它（`dispatch()` 只读 `api`/`operation`/`delay`）。
"重跑会不会出两张单"不看它，看**业务唯一键**：目标端用稳定单号，重复时金蝶报"编码唯一/已存在"，
适配器记为 `repeat` 而不是 `error`——那是幂等在生效。

> 源：`domains/01-metadata-model.md` §3–§6

---

## 3. 取值、转换与取行（"配了但不生效"的第一现场）

### 3.1 `{{ }}` 语法

```
{{key|format|default}}      // key 支持 1–4 层嵌套 a.b.c；取不到→null→default 兜底
```

| format | 作用 |
|---|---|
| `datetime` | 转 `Y-m-d H:i:s` |
| `date` | 转日期 |
| `intval` | 强制整数 |
| `number` | 字符串转数值 |
| `round` | 四舍五入 |
| `implode` / `explode` | 数组/字符串互转 |
| `longText` | 长文本处理 |

**两个真实风险**：
1. **裸名也会被替换**：平台先做 `{{}}` 解析，再做 `str_replace(变量名 → 值)`。
   目标端字段若恰好叫 `CURRENT_TIME` / `LAST_WRITE_TIME`，会被**静默替换成时间值**。
2. **不要依赖求值顺序**：源码里两处读法互相冲突。需要"先替换再计算"时，落地成字段，别在一个表达式里叠两层语义。

### 3.2 系统变量（源端可用；`LAST_WRITE_TIME` 仅目标端）

| 变量 | 含义 | 备注 |
|---|---|---|
| `LAST_SYNC_TIME` | 上次同步时间（增量起点） | 最常用（`\|datetime` 1,740 处） |
| `LAST_WRITE_TIME` | 上次写入时间 | **仅目标端**；源端恒为 0 |
| `CURRENT_TIME` | 本次调度时间 | |
| `MAX_QUERY_RETRISE` | 来自方案 `max_retries` | |
| `MAX_DATA_ID` | 已处理最大 id（默认 0） | |
| `DAYS_AGO_*` / `HOURE_AGO_*` / `MINUTE_AGO_*` | 相对时间 | 名字带平台拼写 `HOURE` |
| `PAGINATION_START_PAGE` / `_START_ROW` / `_PAGE_SIZE` | 分页三件套 | `PAGE_SIZE` 默认 100 |

### 3.3 三个指令前缀

| 前缀 | 行为 | 风险 |
|---|---|---|
| `_function <mysql expr>` | 把后半段当 MySQL 表达式执行（`select <expr> as v`） | **SQL 注入面**；失败时**不报错**，而是把去掉前缀的表达式文本当值写入，极难排查。写进方案前必须单独验证 |
| `_mongoQuery <collectionId> findField=… where={…}` | 跨方案取数 | 依赖目标集合已有数据（两段式前提） |
| `_findCollection …` | 跨方案取集合 | 同上 |

实测普及度：`_function` 出现在 1,259 个方案；`_findCollection` 653；`_mongoQuery` 519。

### 3.4 parser 转换器：只有 7 个（硬编码 switch，没有类/注册表）

| name | 作用 | params |
|---|---|---|
| `ConvertObjectParser` | 标量 → `{params: value}`，**金蝶基础资料专用** | `FNumber`/`FSTAFFNUMBER`/`FName`… |
| `StringToArray` | `explode(params ?: '!e-d', value)` | 分隔符 `,` `\|` `、` |
| `ArrayToString` | `implode(params, value)` | 分隔符（源端拼 `FieldKeys` 也用它） |
| `ConvertJson` | 去换行后 `json_decode` | — |
| `ConvertTwoStageObjectParser` | 两层 `{p1:{p2:value}}` | `params1`/`params2` |
| `K3WiseHeiHuCustomParser` | 黑湖 `[{keyName,keyValue}]` | — |
| `workflowRequestTableFields` | 泛微明细 | — |

两条规则：
- parser 在 `_mapping` / `_isdefault` **之后**执行（"先兜默认值、再转对象"顺序固定）。
- 金蝶侧大小写不敏感（`FNumber`/`FNUMBER` 都有），**写文档统一 `FNumber`**。

### 3.5 `operation`：目标端取行策略（只有 3 种在跑方案出现过）

| `method` | 行为 | 实测 |
|---|---|---|
| *(缺省)* | 逐行单条写入 | 3,211 |
| `batchArraySave` | 取 `rows` 条，包成 `{rowsKey: [content…]}` | 750 |
| `merge` | 按 `field` 聚合同组记录，拼 `header/body/bodyName` | 342 |

- 金蝶 `batchArraySave` 必须 `"rowsKey":"array"`；`rows:1` 是最稳的生产组合。
- **三个 `method` 别混**：`dp_api_asset.method`=HTTP 动词、`meta_data.api`=接口名、`operation.method`=取行策略。

### 3.6 `{{源字段}}` vs 裸字符串（空 Model 的头号原因）

| 写法 | 行为 |
|---|---|
| `"{{FBillNo}}"` | 从当前数据条目 `content` 取值；取不到→`null`→`default`→仍空则被丢弃 |
| `"FBillNo"` | **不查记录**，原样当常量写出（撞上系统变量名会被替换） |

看起来"字段都填了"，实际全是常量 → 写出去是空 `Model`，金蝶报"没有数据需要保存"。

> 源：`domains/02-value-and-transform.md`

---

## 4. 运行时链：数据从哪来、卡在哪

```
crontab(source/target)
  → dispatcher-N（一进程一 DISPATCHER_NUM）
  → StrategyRepository::findRunning(dispatcher_num=N)      只装自己那份方案
  → dispatch:datahub {id} --source|--target --asyn
  → handleSourceDispatch:  适配器实例化 → 前置条件检查 → 求值 → <sid>_SJOB 入队
  → handleSourceJob:       connect → invoke → 钩子 → handleResponse
                           → 校验 otherResponse → DataStorage::insertOne → <sid>_ADATA
  → handleTargetDispatch:  DataStorage::fetch(operation) → 求值+parser → <sid>_TJOB 入队
  → handleTargetJob:       Before/After 钩子 → invoke → 解析响应 → 按 response[] 回写主键
```

### 4.1 存储对象（Mongo 库名 `LESSEE_<lesseeId>`，每方案一套集合）

| 集合/表 | 内容 | 关键字段 |
|---|---|---|
| `<sid>_ADATA` | 落地数据条目 | `id / number / content / status / response / source_job_id / target_job_id` |
| `<sid>_SJOB` / `<sid>_TJOB` | 源/目标调用队列 | `api / params / ids / retries / history / SDK` |
| `<sid>_LOG` | 运行日志 | `text / content / status / created_at` |
| `dh_exchange_strategy_throwable` | 调度级异常（MySQL） | `strategy_id / throwable / type / jobid` |
| `dh_exchange_strategy_error_jobs` | 队列异常（MySQL） | 含 `time_consuming` |

> `*_source_ck` / `*_target_ck` 是"上线前检查项"，**不是运行数据**。

### 4.2 状态位（排障最先看）

| `DataStatus` | 含义 | 通常意味着 |
|---|---|---|
| 0 | AWAIT | 待处理（正常排队） |
| 2 | FINISHED | 成功 |
| 3 | ERROR | 失败，看 `result[].problem` |
| 5 | QUEUE | 已入目标队列，等写入 |
| 6 | — | **跳过调度**（该条不再被调度），不是"分页中间态" |

`LogStatus`：0 RECORD / 1 NOTICE / 2 SUCCESS / 3 ERROR / 4 FATAL / **5 DEBUG**（2026-10 起用于调试留痕）。

### 4.3 三个"启动了但不动"的原因

| 原因 | 判据 | 处置 |
|---|---|---|
| `dispatcher_num` 与容器内实际 dispatcher 编号不匹配 | 方案只被编号相同的那条 `dispatcher-N` 装载 | 核对编号，或调整方案归属 |
| 没有消费者（测试环境不开守护进程） | 队列有 job，status 一直 5/0 | `strategy.queue.job.run` 手工消费 |
| 前置方案未完成 | `*_dispatch_condition` 里对方仍在工作，300 秒后重投 | 等，或临时摘掉前置条件 |

### 4.4 重试：指数退避，最长约 25 小时

`max_retries` 注入为 `MAX_QUERY_RETRISE`；`reQueue()` 退避序列 **20s → 300s → 3600s → 14400s → 72000s**。
超限写 `MAX_RETRIES` FATAL。

- 默认拉满 ≈ **25 小时**才彻底放弃；
- `max_retries=3` ≈ **65 分钟**（20+300+3600 秒）。

> 含义：**坏数据会在队列里躺很久**。调试期先 `queue.job.run` 拿到即时结果，别等退避。

> 源：`domains/04-runtime-chain.md` §2–§5

---

## 5. 分页与增量：取全、取新、可回填

### 5.1 "取不到"先分类

| 现象 | 先看 | 常见原因 |
|---|---|---|
| 第一页有、后面没有 | `page_index`/`page_size`/`pageNo`/`offset` | 从 0 还是 1 开始；参数放错位置 |
| 每页都只有 100 条 | 平台默认上限 | 没显式传 `page_size`，或传了被截断 |
| 总数对、明细少 | 主子表分页 | 主表分页了，明细没按主表 id 回查 |
| 新单有、改单没有 | 增量字段 | 只按 `created` 取，没按 `modified` |
| 补推后重复 | 幂等键 | 补推窗口与已推窗口重叠，目标没 upsert |

### 5.2 分页三件事

1. **起点**：0 还是 1，各平台不同——查接口资产，不要凭记忆。
2. **位置**：可能在 URL query、`request[]`、或 `otherRequest`；**放错不报错，只会一直返回第一页**。
3. **终止**：不要只靠"返回条数 < page_size"；优先 `total`/`has_next`，没有就按空页停。

### 5.3 增量水位

| 水位 | 适用 | 风险 |
|---|---|---|
| `created` | 只追加不改单 | 改单永远不过來 |
| `modified` | 大多数 ERP/电商 | 时区/精度不一致，边界漏单 |
| 自增 id / 游标 | 支持游标的接口 | 删除/反审核不出现 |
| 全量覆盖 | 小表、可重算 | 量大、覆盖目标人工修改 |

**推荐**：`modified` + **回看窗口 5–15 分钟** + 目标按业务主键 upsert。回看窗口防"源系统提交晚"，重复靠幂等消化。

### 5.4 补推/回填

1. 先停目标写入或切影子表；2. 按**业务日期**（不是创建时间）圈范围；
3. 与已推窗口做差集，或按单号查目标是否已存在；4. 保持同一幂等键，不生成新单号；
5. 抽样回查：源单号 → 目标单号 → 目标明细行数。

> 源：`domains/11-pagination-and-incremental.md`

---

## 6. 幂等：三种正确做法、三种错误做法

| 做法 | 说明 | 落点 |
|---|---|---|
| ✅ 源端稳定业务键 + **源端** `idCheck=false` | 查询结果按 `id` upsert，同一单不重复落 ADATA | `DataStorage` |
| ✅ 目标端先查后写 | `executeBillQuery` 按单号查存在性，再决定 save/batchSave | 方案级设计 |
| ✅ 前置条件串行 | `target_dispatch_condition` 保证 A 落地后 B 才开始（平台原生两段式） | `*_dispatch_condition` |
| ❌ 靠 cron 频率"错开" | 上游一延迟就重复 | — |
| ❌ 源端 `idCheck=true` 又跑多次 | 同一 `id` 落多行，必然重复发送 | — |
| ❌ 脚本里 `array_push` 累积 | 重跑翻倍 | 见 §7 |

### 6.1 自循环（写回自己）

判定三步：① 源平台 = 目标平台且 `FormId`/接口相同；② 目标写入后 `FModifyDate` 变化 → 下次增量捞回自己写的单；③ 源端过滤没有排除标记。
止损：源端过滤加"来源≠本平台"、写入时打标、或目标端不回写会触发增量的字段。

> 生产实测：`金蝶云星空 → 金蝶云星空` 有 47 条在跑方案，全部需要人工确认是否自循环。

---

## 7. 事件脚本：14 个事件，只有 5 个真有触发点

> **先看这张表再写脚本**——平台里有 9 个事件写了也**永远不执行**，界面无报错（生产已有 30 条脚本踩坑）。

| 事件 | 时机 | 异常语义 |
|---|---|---|
| `AfterSourceInvoke(&$response, $adapter)` | `invoke()` 返回后、写落地数据前 | **向上抛 → 整个作业失败并重试**（主力） |
| `AfterSourceResponseSuccess(&$response, $adapter)` | 响应落库后 | 抛出 → 重试 |
| `AfterTargetGenerate(&$params, $ids)` | 目标队列插入前，**可改写请求参数**（字段级补值最佳位置） | **空 catch 吞掉，不写日志**（主力） |
| `BeforeTargetInvoke(&$request, $adapter, $job)` | 调用目标前 | 被吞 |
| `AfterTargetInvoke(&$response, $adapter, $job)` | 目标响应处理后 | 被吞 |

**死事件**（无调用方）：`AfterSourceDispatch`、`BeforeSourceInvoke`、`BeforeSourceJobInsert`、
`AfterSourceResponseFail`、`BeforeTargetDispatch`、`AfterTargetResponseSuccess/Fail` 等。

写脚本的三条硬规则：
1. `run()` 是唯一约定方法，**没有接口/基类/返回值约定**；类名会被替换成 `SFNS_<md5(strategyId+event)>`，`class AfterSourceInvoke` 只是占位名。
2. **源端只在"这条数据确实不该继续"时 throw**，否则会重试到 `max_retries`，队列堆积。
3. **目标端异常被静默吞掉**：要阻断必须 `return` 或直接改写 `$params`；别指望日志能告诉你失败了。

写之前先用 `script.validate` 做语法校验（`php -l`），再 `script.create`。

> 源：`domains/03-event-scripts.md`

---

## 8. 元数据复用：能力 = 端点 × 字段集 × 过滤 × 映射 × 脚本

```
能力 = 端点（接口资产给） × 字段集（request/response） × 过滤条件 × 字段映射 × 脚本
       └─ 几乎不变 ─┘      └────────── 每条方案都不一样 ──────────┘
```

- **接口资产少 ≠ 能力弱**：小满 24 个端点支撑 1,128 条方案（47 条/资产）；金蝶 514 个资产/1,723 条（3.4 条/资产）。
- 差异点全在元数据：同一端点，**挑哪些 `response[]`**、**用什么时间字段做增量**，就是另一条方案、另一种语义。
- **对象身份在哪，档案就怎么建**：在资产里（金蝶 `FormId`）→ 按资产；在路径里（`/v1/{对象}/*`）→ 按端点；在参数里 → 必须逐端点看 meta_data。

**实践含义**：新建方案时优先 `strategy.copy` 复制成熟方案再微调，而不是从空白开始配 200 个字段。

> 源：`domains/06-metadata-reuse.md`

---

## 9. 落地层与两段式（Datahub 当"中转站"）

- 平台自身可作为**目标端**（把 A 系统数据落到 Datahub）或**源端**（把落地数据再推给 B）。
- 常见编排：`A → Datahub（落地） → B`，用 `*_dispatch_condition` 做**两段式串行**：A 空闲后 B 才跑，比 cron 猜时间可靠。
- 空操作收尾（把数据标记完成但不写外部）有 1,695 条——用于"只落地不推送"的场景。

> 源：`domains/05-datahub-as-landing.md`、`domains/09-cross-strategy-query.md`

---

## 10. 主子表与数据库目标（选型用）

**主子表三种机制**（实测占比）：

| 机制 | 源端 | 目标端 | 说明 |
|---|---|---|---|
| 数组型 value（主流） | 多数 | 多数 | `FSaleOrderEntry = _Flist`（44）、`FEntity = details/list`（129）、`FSaleOrderFinance`（36） |
| `parent_id` 树 | 0.2% | 1.1% | 仅用于拼 `children` |
| `buildModel=true` | 4.0% | 3.3% | 按 `response[]` 重建 content |

- 一单一条 vs 一单多行：`id` 取 `FBillNo`/`FID` → 整单写入；取 `FEntity_FEntryID`/行号 → 每行独立（影响对账粒度）。
- `autoFillResponse` 源端 47.5% 开启（自动识别字段），目标端几乎不用。

**数据库目标**（MySQL 138 / MSSQL 33 / Hologres 20）：
列映射（MySQL 主流）vs 命名参数（MSSQL/Hologres 主流）；`limit` 常见 200/50/1；`extend_sql_N` 可一条方案写两张表。

> 源：`domains/08-master-detail.md`、`domains/10-database-target.md`

---

## 11. 作废/删除/反审核：目标端不会自动跟着变

| 源端动作 | 目标端策略 | 注意 |
|---|---|---|
| 作废 | 目标单作废/关闭，或红冲 | 目标接口不支持作废就红冲 |
| 删除 | 软删除/禁用，或保留 | 多数 ERP 不允许物理删 |
| 反审核 | 反审核 → 改 → 再审 | 常触发库存/财务回滚，必须单独验证 |

**不要做**：用"再推一次"当删除；在 `AfterTargetInvoke` 抛异常"撤销"已写入的单；正反链路共用同一幂等键。

> 源：`domains/12-reverse-and-delete.md`

---

## 12. 一份配置好不好：6 条自检

1. `api` 与接口资产 `code` 对得上，且 `effect` 与所在侧一致（源=`QUERY`、目标=`EXECUTE`）。
2. 源端 `request[]` 是**字段白名单**而非全量；`otherRequest` 里能看到 `FilterString`（增量）与分页三件套。
3. 目标端每个 `request[].value` 都是 `{{源字段}}` 或明确常量——**裸字段名会被当常量写死**。
4. 基础资料类字段（组织/客户/物料/币别）带 `ConvertObjectParser`。
5. 批量写入的目标端有 `operation.method=batchArraySave` + `rowsKey` + `rows`（`rows` 不宜过大）。
6. `id`/`number` 指向真实业务键，不是空串。

---

## 13. 这份蒸馏**不覆盖**的部分（仍需知识 MCP）

| 需要 | 去哪 |
|---|---|
| 某平台某业务对象的**最新字段清单**（如金蝶客户 18 个必填） | 知识 MCP `knowledge_search` → `knowledge_fetch`（对象卡） |
| 平台间**字段口径差异**（同一个"客户"在 A/B 系统怎么对） | 知识 MCP（mapping 类文档） |
| **客户案例**里的特殊约定（行业字段、审批流前缀） | 知识 MCP（案例库；需授权档位） |
| 平台**端点清单**（某平台支持哪些接口） | `asset.api.list` / `asset.platform.get`（租户实际资产） |
| 本文机制在**新版本**是否有变化 | 知识 MCP + `meta.capabilities` 的 `capability_version` |

> 用法与引用纪律见 `06-knowledge-mcp.md`；本文对应知识库 `domains/01,02,03,04,06,08,09,10,11,12`。
