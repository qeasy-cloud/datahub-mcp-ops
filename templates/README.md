# Templates

> 这些是**可直接改用的文件**，不是示例代码。用之前把 `<...>` 占位符换成真实值。

## `strategy-blueprint.md` — 建方案前先填这张表

在 `strategy.copy` / `strategy.create` **之前**填完。填不完就说明设计还没想清楚，
后面一定返工（尤其是增量口径与幂等键）。

## `field-mapping-customer.json` — 目标端字段映射样例

金蝶「客户」`batchSave` 的 `target.update` 参数样例。用法：

```bash
# 方式一：直接改文件里的 <strategyId> 后调用（推荐，避免 shell 引号问题）
python scripts/dh.py call strategy.target.update --args @templates/field-mapping-customer.json

# 方式二：只看不写（先确认接口字段与你的租户资产一致）
python scripts/dh.py call asset.api.get --param apiId=<API_ID> --param includeFields=true
```

使用前必须核对：

1. `<strategyId>` 换成你的方案 id；
2. `field` 名称与本租户接口资产一致（**不要把金蝶字段照搬到别的 ERP**）；
3. `parser` 是否适用于目标系统（金蝶基础资料一般 `ConvertObjectParser` + `FNumber`）；
4. `operation.rows` 的批量大小（`1` = 一条一请求，最稳）；
5. 源端没有的字段要么删掉，要么给明确常量，并记录原因。

> `request` 数组是**整份替换**：用 `patch` 只改局部，别用整份覆盖去"顺手修一个字段"。

## `ops-report.md` — 巡检 / 交接报告模板

原则：只写事实与证据路径，不写猜测（猜测必须标注）；不写完整密钥/凭据；
变更前后、目标系统验证、未决事项必须写清。

## `tool-test-matrix.md` — 新部署验收矩阵

46 个 Tool 的正例表 + 11 条负例。由 `tools/manifest.json` 生成；
服务端升级后重新生成再验。

用法：每个 Tool 至少成功调一次；破坏性类只在自己的临时方案上做；负例必须全过。
