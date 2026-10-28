# Tool 验收矩阵（46 个）

> 用途：对一个**新部署**做一次性验收。每个 Tool 至少成功调用一次；破坏性类只在自己的临时方案上做。
> 本表由 `tools/manifest.json` 生成；服务端能力升级后请重新生成（`python scripts/dh.py manifest`）。

| # | Tool | 风险 | 必填参数 | 结果 | 备注 |
|---|------|------|----------|------|------|
| 1 | `meta.whoami` | read | - |  |  |
| 2 | `meta.capabilities` | read | - |  |  |
| 3 | `meta.enums` | read | - |  |  |
| 4 | `asset.api.get` | read | apiId |  |  |
| 5 | `asset.api.list` | read | - |  |  |
| 6 | `asset.connector.get` | read | connectorId |  |  |
| 7 | `asset.connector.list` | read | - |  |  |
| 8 | `asset.platform.get` | read | platformId |  |  |
| 9 | `asset.platform.list` | read | - |  |  |
| 10 | `audit.search` | read | - |  |  |
| 11 | `exception.search` | read | - |  |  |
| 12 | `script.create` | write | strategyId, name, event, script |  | 需二次确认 |
| 13 | `script.delete` | destructive | strategyId, scriptId |  | 需二次确认 |
| 14 | `script.get` | read | strategyId |  |  |
| 15 | `script.list` | read | strategyId |  |  |
| 16 | `script.validate` | read | script |  |  |
| 17 | `script.write` | ops | strategyId, scriptId, script |  | 需二次确认 |
| 18 | `strategy.checkList` | read | strategyId, direction |  |  |
| 19 | `strategy.config.rollback` | write | strategyId, direction, historyId, md5 |  | 需二次确认 |
| 20 | `strategy.copy` | ops | strategyId |  | 需二次确认 |
| 21 | `strategy.create` | write | basic, source, target |  | 需二次确认 |
| 22 | `strategy.data.clean` | destructive | strategyId |  | 需二次确认 |
| 23 | `strategy.data.cleanAll` | destructive | strategyId |  | 需二次确认 |
| 24 | `strategy.data.import` | write | strategyId, rows |  | 需二次确认 |
| 25 | `strategy.data.search` | read | strategyId |  |  |
| 26 | `strategy.data.setStatus` | ops | strategyId, status |  | 需二次确认 |
| 27 | `strategy.dbInfo` | read | strategyId |  |  |
| 28 | `strategy.dbResetStatus` | ops | strategyId |  | 需二次确认 |
| 29 | `strategy.dispatchSource` | ops | strategyId |  | 需二次确认 |
| 30 | `strategy.dispatchTarget` | ops | strategyId |  | 需二次确认 |
| 31 | `strategy.get` | read | strategyId |  |  |
| 32 | `strategy.list` | read | - |  |  |
| 33 | `strategy.log.search` | read | strategyId |  |  |
| 34 | `strategy.offline` | ops | strategyId |  | 需二次确认 |
| 35 | `strategy.online` | ops | strategyId |  | 需二次确认 |
| 36 | `strategy.queue.clean` | destructive | strategyId |  | 需二次确认 |
| 37 | `strategy.queue.job.get` | read | strategyId, direction, jobId |  |  |
| 38 | `strategy.queue.job.run` | ops | strategyId, direction, jobId |  | 需二次确认 |
| 39 | `strategy.queue.job.update` | ops | strategyId, direction, jobId, params |  | 需二次确认 |
| 40 | `strategy.queue.list` | read | strategyId, direction |  |  |
| 41 | `strategy.showConfig` | read | strategyId, direction |  |  |
| 42 | `strategy.source.update` | write | strategyId |  | 需二次确认 |
| 43 | `strategy.start` | ops | strategyId |  | 需二次确认 |
| 44 | `strategy.stop` | ops | strategyId |  | 需二次确认 |
| 45 | `strategy.target.update` | write | strategyId |  | 需二次确认 |
| 46 | `strategy.update` | write | strategyId, patch |  | 需二次确认 |

## 负例矩阵（必须全部通过）

| # | 场景 | 期望 | 结果 |
|---|------|------|------|
| 1 | 无密钥 / 密钥失效 | JSON-RPC error，提示需要 API Key |  |
| 2 | 对端点发 GET | 405（不要返回 200 或 HTML） |  |
| 3 | 越权 strategyId | `strategy_access_denied`，且不回显对方内容 |  |
| 4 | 未知 strategyId | `strategy_not_found` |  |
| 5 | 裸数字 status | `invalid_status_word`（只收语义词） |  |
| 6 | 目标侧缺 confirmWrite | `external_write_unconfirmed` |  |
| 7 | 确认令牌重放 | `confirmation_token_invalid` |  |
| 8 | 影响面超阈值 | `impact_exceeds_threshold`，需带令牌 |  |
| 9 | 运行中改任务参数 | `strategy_running_guard` |  |
| 10 | 非法 PHP 脚本 | `script_syntax_error` + 行号 |  |
| 11 | 不存在的 jobId | `job_not_found` / `invalid_job_id` |  |
