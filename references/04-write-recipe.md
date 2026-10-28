# 04 · 写入配方：让目标端真正写进去

> 目标：把"数据已经在平台里"变成"目标系统确实多了一张单"。
> 这一篇只讲**目标端**（`target`）。源端取数见 `03-debug-loop.md`，机制见 `01-platform-model.md`。
>
> 前提认知：**字段映射不是"填字段名"，而是"写取值表达式"**。
> `"FBillNo"` 会被当常量；只有 `"{{FBillNo}}"` 才会去数据里取值。

---

## 1. 五步配方（按顺序做，别跳）

```
① 选接口     asset.api.list {platformId, effect:"EXECUTE"}       ← 写入接口
② 读模板     asset.api.get  {apiId, includeFields:true}           ← 必填字段 + FormId
③ 看现状     strategy.showConfig {strategyId, direction:"target"} ← 当前 meta_data
④ 改映射     strategy.target.update {patch:{…}}                   ← 只改要改的部分
⑤ 闭环验证   dispatchTarget → queue.job.get → queue.job.run {confirmWrite:true} → 回查
```

> 第 ①–② 步用知识 MCP 补充"这个对象到底要哪些字段"更快（见 `06-knowledge-mcp.md`），
> 但**以租户实际接口资产为准**（不同版本/二开字段不同）。

---

## 2. 目标端 `meta_data` 的最小可用形态

```jsonc
{
  "api": "batchSave",              // 写入接口 code
  "method": "POST",
  "type": "WebAPI",                // 协议类型；不要用 type 判断方向
  "effect": "EXECUTE",             // 新资产代才有；方向以"挂在 target"为准
  "id": "FBillNo",                 // 主键取值路径（落 ADATA.id）
  "number": "FBillNo",             // 单号取值路径（落 ADATA.number）
  "otherRequest": [                // 与 request 合并进请求体
    { "field": "FormId", "value": "SAL_SaleOrder" },
    { "field": "Operation", "value": "" },              // 可选：金蝶操作（提交/审核）
    { "field": "IsAutoSubmitAndAudit", "value": "false" }
  ],
  "request": [                     // 写入字段：每个 value 都必须是 {{}} 或常量
    { "field": "FBillNo",   "value": "{{FBillNo}}" },
    { "field": "FDate",     "value": "{{FDate|date}}" },
    { "field": "FCustId",   "value": "{{FCustId}}",
      "parser": { "name": "ConvertObjectParser", "params": "FNumber" } },
    { "field": "FSaleOrderEntry", "value": "_Flist" }   // 明细数组走这个"别名"
  ],
  "otherResponse": [               // 4 个位置槽，目标端至少 2 项
    "Result.ResponseStatus.IsSuccess",
    "true"
  ],
  "operation": {                   // 批量写入才需要
    "method": "batchArraySave",
    "rowsKey": "array",
    "rows": "1"
  }
}
```

### 2.1 三个必须记住的规则

| 规则 | 说明 |
|---|---|
| **`{{}}` vs 裸名** | `"{{FBillNo}}"` 取值；`"FBillNo"` 是常量（撞上系统变量名还会被替换） |
| **基础资料必带 parser** | 组织/客户/物料/币别等字段：`ConvertObjectParser` + `params=FNumber`（或对方要求的编码类型） |
| **明细是"别名"** | 金蝶主子表用 `"FSaleOrderEntry": "_Flist"`（把数据里的明细数组挂上去），不是逐行映射 |

### 2.2 `otherResponse` 位置槽（缺就报"其它响应参数没有定义接口状态参数"）

| 下标 | 含义 | 目标端典型值 |
|---|---|---|
| `[0]` | 状态字段路径 | `Result.ResponseStatus.IsSuccess` |
| `[1]` | 成功值 | `true` |
| `[2]` | 数据字段路径（可选） | `Result.ResponseStatus.SuccessEntitys` |
| `[3]` | 页码字段（可选，源端翻页用） | — |

---

## 3. 三种写入形态，选对了少踩一半坑

| 形态 | 何时用 | `operation` |
|---|---|---|
| 逐行单条 | 数据量小、要精确控制每条结果 | 缺省 |
| `batchArraySave` | 金蝶批量保存（最常见） | `{"method":"batchArraySave","rowsKey":"array","rows":"1"}` |
| `merge` | 一单多行要拼成 `{header, body, bodyName}` | `{"method":"merge", …}` |

- 金蝶 `batchArraySave` 的 `rowsKey` 必须是 `"array"`；`rows:1` 是最稳的生产组合（先跑通再放大）。
- `rows` 太大时单条失败会拖累整批，调试期一律 `1`。

---

## 4. 闭环验证（写一次、验一次，别攒着）

```bash
dh call strategy.dispatchTarget --args '{"strategyId":"<SID>"}'
dh call strategy.queue.job.get  --args '{"strategyId":"<SID>","direction":"target","jobId":"<TID>"}'
#   ↑ 逐字段核对 params.Model：有没有 null？基础资料是不是 {FNumber:…}？明细数组有没有内容？
dh call strategy.queue.job.run  --args '{"strategyId":"<SID>","direction":"target","jobId":"<TID>","confirmWrite":true}'
```

**验收三条**（缺一条都不算"写进去了"）：

1. `run` 返回 `ok=true`，且 `status_after=2`（不是 3/5）；
2. 外部系统回查：按单号 `executeBillQuery` 能查到，且**明细行数对得上**；
3. 再跑一次同一条数据 → 应该是 `repeat`（幂等命中），**不应出现第二张单**。

> 平台内 `status=FINISHED` 只代表"报文发出去且对方返回成功"，**不代表业务已入库**。
> 金蝶"响应为空但成功"的情况真实存在，必须回查。

---

## 5. 幂等与自循环（写完必须想的两件事）

| 检查 | 做法 |
|---|---|
| **幂等键** | 目标端用稳定业务单号（`FBillNo`），不要用时间戳/随机数；重复时金蝶报"编码唯一"→ 记 `repeat` |
| **先查后写** | 高价值单据：先 `executeBillQuery` 按单号查存在性，再决定 save/batchSave |
| **自循环** | 源平台 = 目标平台且 `FormId` 相同时，写入会改 `FModifyDate` → 下次增量把自己写的单捞回来。必须加"来源≠本平台"过滤或打标 |
| **补推** | 与已推窗口做差集；保持同一幂等键；抽样回查源单号→目标单号→明细行数 |

---

## 6. 金蝶报错 → 改哪里（最常查的表）

| 报错 | 真实原因 | 改什么 |
|---|---|---|
| `格式错误，不能转换为字典类型` | 基础资料字段传了标量 | 加 `ConvertObjectParser`，`params=FNumber` |
| `没有数据需要保存` / `Model 为空` | 字段全空（裸名当常量 / 源字段名错） | 改 `{{源字段}}`，核对源数据实际键名 |
| `组织内编码唯一` / `已存在` | 幂等命中 | 不用改，确认 `repeat` 合理 |
| `基础资料字段值不存在` | 源数据编码在目标系统不存在 | 清洗源数据或先在目标建档案 |
| `必填字段不能为空` | `request` 里缺该字段 | 按接口资产补字段 |
| `金蝶写入响应数据为空` | 会话并发/空响应 | 重推一次 |
| `其它响应参数没有定义接口状态参数` | `otherResponse` 少于 2 项 | 补齐位置槽 |

更多症状（含源侧）→ `05-diagnostics.md`。

---

## 7. 改坏了怎么退

```bash
# target.update 的返回里带 backup
# {"backup":{"historyId":"…","md5":"…"}}
dh call strategy.config.rollback --args '{
  "strategyId":"<SID>","direction":"target","historyId":"…","md5":"…"}'
```

- 回滚前系统会**再给当前配置打一份快照**，所以回滚本身也可回滚。
- 只改一个字段时优先 `patch`（浅合并），不要 `metaData` 整体替换——整体替换容易丢字段。

---

## 8. 自检清单（交付前逐条打勾）

- [ ] `asset.api.list` 里该接口 `effect=EXECUTE`
- [ ] `otherRequest` 里有 `FormId`（金蝶）/ 目标系统要求的对象标识
- [ ] 每个 `request[].value` 都是 `{{}}` 或明确常量，**没有裸字段名**
- [ ] 基础资料字段都带 `ConvertObjectParser`
- [ ] 明细用别名（`_Flist` 等），不是逐行
- [ ] `operation` 与 `rowsKey` 匹配（批量写入时）
- [ ] `otherResponse` ≥2 项且路径正确
- [ ] `id`/`number` 指向真实业务键
- [ ] 跑一次成功 + 回查一致 + 重跑变 `repeat`
