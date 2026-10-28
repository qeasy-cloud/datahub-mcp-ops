# Tool 验收矩阵（58 个）

由 `tools/manifest.json` 生成，**不要手改**：服务端工具集变化后重新生成本表，并在最后一列记录验收结果。

| # | Tool | 风险 | 主要参数 | 备注 |
|---|---|---|---|---|
| 1 | `asset.api.get` |  |  |  |
| 2 | `asset.api.list` |  |  |  |
| 3 | `asset.connector.get` |  |  |  |
| 4 | `asset.connector.list` |  |  |  |
| 5 | `asset.platform.get` |  |  |  |
| 6 | `asset.platform.list` |  |  |  |
| 7 | `audit.search` |  |  |  |
| 8 | `exception.search` |  |  |  |
| 9 | `mapping.category.create` |  |  | 需二次确认 |
| 10 | `mapping.category.delete` |  |  | 需二次确认 |
| 11 | `mapping.category.get` |  |  |  |
| 12 | `mapping.category.list` |  |  |  |
| 13 | `mapping.category.update` |  |  | 需二次确认 |
| 14 | `mapping.relation.create` |  |  | 需二次确认 |
| 15 | `mapping.relation.delete` |  |  | 需二次确认 |
| 16 | `mapping.relation.import` |  |  | 需二次确认 |
| 17 | `mapping.relation.list` |  |  |  |
| 18 | `mapping.relation.update` |  |  | 需二次确认 |
| 19 | `mapping.resolve` |  |  |  |
| 20 | `mapping.usage` |  |  |  |
| 21 | `script.create` |  |  | 需二次确认 |
| 22 | `script.delete` |  |  | 需二次确认 |
| 23 | `script.get` |  |  |  |
| 24 | `script.list` |  |  |  |
| 25 | `script.validate` |  |  |  |
| 26 | `script.write` |  |  | 需二次确认 |
| 27 | `strategy.checkList` |  |  |  |
| 28 | `strategy.config.rollback` |  |  | 需二次确认 |
| 29 | `strategy.copy` |  |  | 需二次确认 |
| 30 | `strategy.create` |  |  | 需二次确认 |
| 31 | `strategy.data.clean` |  |  | 需二次确认 |
| 32 | `strategy.data.cleanAll` |  |  | 需二次确认 |
| 33 | `strategy.data.import` |  |  | 需二次确认 |
| 34 | `strategy.data.search` |  |  |  |
| 35 | `strategy.data.setStatus` |  |  | 需二次确认 |
| 36 | `strategy.dbInfo` |  |  |  |
| 37 | `strategy.dbResetStatus` |  |  | 需二次确认 |
| 38 | `strategy.dispatchSource` |  |  | 需二次确认 |
| 39 | `strategy.dispatchTarget` |  |  | 需二次确认 |
| 40 | `strategy.get` |  |  |  |
| 41 | `strategy.list` |  |  |  |
| 42 | `strategy.log.search` |  |  |  |
| 43 | `strategy.offline` |  |  | 需二次确认 |
| 44 | `strategy.online` |  |  | 需二次确认 |
| 45 | `strategy.queue.clean` |  |  | 需二次确认 |
| 46 | `strategy.queue.job.get` |  |  |  |
| 47 | `strategy.queue.job.run` |  |  | 需二次确认 |
| 48 | `strategy.queue.job.update` |  |  | 需二次确认 |
| 49 | `strategy.queue.list` |  |  |  |
| 50 | `strategy.showConfig` |  |  |  |
| 51 | `strategy.source.update` |  |  | 需二次确认 |
| 52 | `strategy.start` |  |  | 需二次确认 |
| 53 | `strategy.stop` |  |  | 需二次确认 |
| 54 | `strategy.target.update` |  |  | 需二次确认 |
| 55 | `strategy.update` |  |  | 需二次确认 |

## 负例（每个安全边界都要有一条）

| # | 场景 | 期望 |
|---|---|---|
| 1 | 缺少 `strategyId` / `categoryId` | 入参校验失败，不执行 |
| 2 | 非法 24 位 id（`mapping.*`、`queue.job.*`） | `invalid_mapping_id` / 参数错误 |
| 3 | 跨租户 strategyId | 404 / 租户边界拒绝 |
| 4 | 只读密钥调用写工具 | `scope_denied` |
| 5 | 破坏性工具不带令牌（confirm/guarded 档） | `confirm_required` + precheck |
| 6 | 令牌重放 | `confirmation_token_invalid` |
| 7 | 影响面 > 阈值（full 档） | 仍要求令牌（`impact_exceeds_threshold`） |
| 8 | 删除仍被引用的静态映射分类 | `mapping_category_in_use` |
| 9 | 同一分类下重复 `a_value` | `mapping_relation_duplicate` |
| 10 | 写入未定义字段 | `unknown_field` / 参数错误 |
| 11 | 对运行中的方案做清理 | `strategy_running` 拒绝 |

## 验收记录

| 版本 | 日期 | 正例 | 负例 | 备注 |
|---|---|---|---|---|
| 2.0.0 | 2026-10-28 | 39 | 11 | M1/M2 回归（101 条 HTTP 断言 + PHPUnit） |
| 2.1.0 | 2026-10-28 | 58 | 11 | 新增 12 个 mapping 工具；`qa-mapping.php` 38 条断言全绿 |
