# FAQ

## 这个 SKILL 是什么？不是什么？

是**面向 AI Agent 的作业手册**：告诉你在这个平台上"先看什么、按什么顺序调、看到什么该做什么"。
不是 API 参考（那是 `references/02-tool-catalog.md`），不是平台源码文档，也不替代业务判断。

## 我没有平台源码，能用吗？

能。全部内容基于 MCP 工具契约 + 已公开的平台机制（`references/01-platform-model.md`）。
需要看源码才能回答的问题（如"某个适配器内部怎么拼报文"）不在范围内。

## 为什么强调"无守护进程也能调试"？

因为测试/客户环境的常态就是：**方案不启动、进程守护不开**。
这时平台不会自动产生队列、也不会自动消费。SKILL 的核心工作流（dispatch → 读队列 → 手工消费 → 改参数 → 重跑）
就是为这个场景设计的。

## 调试时我要不要先 `strategy.start`？

**不要**。`start` 只是打开 cron；没有守护进程时它不会让数据流动，还会让"这是调试还是生产"变得模糊。
调试用 `dispatchSource` + `queue.job.run`，一次一条，可控可回滚。

## `ok=true` 为什么还会"没数据"？

因为平台把"源系统返回空"当作**完成**而非错误。所以本 SKILL 一直强调看 `has_data`：
`ok` 表示"执行成功"，`has_data` 表示"真的取到东西"。

## 目标端写入为什么必须 `confirmWrite`？

因为那是**真实的外部副作用**（写进 ERP），平台无法回滚。信任级别（哪怕是 `full`）也不能豁免它——
高权限是"免于逐次确认"，不是"免于知情"。

## 写完显示成功，就算完成了吗？

不算。平台 `status=FINISHED` 只代表"报文发出去且对方返回成功"。
必须**回查外部系统**（按单号查），并核对明细行数。

## `strategy.get` 为什么看不到 `meta_data` 了？

v2 起默认 `sections=basic`（只给摘要），因为单条全量约 40KB，会把上下文挤爆。
要完整配置传 `sections=source|target|all`。

## 工具数量为什么和文档不一致？

用 `meta.capabilities` 的 `tool_count` 对比。常见原因：
① 服务端版本不同（39 / 46 / 58）；② 密钥 scope 不足；③ `read_only` 档位。
`docs/clients.md` §4 有兼容矩阵。

## 两个 MCP 有什么区别？

- **Datahub MCP**（租户端点）：58 个工具，读写你的真实数据，有状态。
- **知识 MCP**（`mcp.qeasy.cloud`）：3 个工具，只读官方知识，无状态。
前者回答"现在是什么"，后者回答"应该怎么配"。见 `references/06-knowledge-mcp.md`。

## 密钥从哪来？能自助注册吗？

- Datahub MCP：租户「开放中心」签发（`sh-…`），**不能**自助注册。
- 知识 MCP：Agent 可 PoW 自助注册（`qk_live_…`，Standard 20 次/天）。

## 密钥丢了/被吊销了怎么办？

平台只存 hash，无法找回，只能重新签发。
⚠️ 注意：在**共用同一个库**的环境跑会重建 `dh_mcp_grant` 的测试，会清空所有密钥（本仓库已加安全阀）。

## 为什么有些工具在我的密钥下不可见？

scope 不足或档位是 `read_only`。`meta.capabilities` 会给出每个工具在当前密钥下的 `callable`。

## 能不能删掉一个方案？

不能。平台没有"删除方案"的 MCP 工具，只有 `offline`（置未上线）与清理数据/队列。
这也是刻意的：删除方案属于平台管理动作，不应由 Agent 随手做。

## 能不能改连接器凭据？

不能。`asset.connector.get` 只给 `credentialsConfigured`（true/false），改凭据要去平台页面。
把"能读配置"和"能改密钥"分开是安全设计。

## 清理操作为什么要令牌？我明明是 full 档。

影响面 > 1000 行时，即使是 `full` 也会要求二次确认（`confirmation_token`）。
这是**熔断**，不是权限问题：误删 10 行和 10 万行不是同一量级的事故。`dryRun` 可以先看影响面。

## 限流是多少？批量巡检会不会撞墙？

120 次/分钟/密钥。42 个方案全量体检约 43 次调用，一分钟内没问题；
超过 100 个方案请分批（每批 50，间隔 30 秒）。

## 事件脚本写了为什么不执行？

14 个事件里只有 **5 个**真有触发点。挂在"死事件"上不会执行、也不报错。
详见 `references/01-platform-model.md` §7。

## 目标端脚本里 `throw` 为什么没反应？

目标端事件异常被**静默吞掉**（连日志都不写）。要阻断必须 `return` 或改写 `$params`。

## 为什么重跑会出现第二张单？

幂等键不稳定（用了时间戳/随机数），或目标端没有按业务单号 upsert。
正确做法见 `references/04-write-recipe.md` §5。

## 这个 SKILL 怎么验证没写错？

```bash
python scripts/validate_skill.py -v   # 离线：结构/链接/工具名/密钥
python scripts/smoke_test.py          # 在线：只读冒烟
```
CI 也会跑（`.github/workflows/validate.yml`）。

## 我能贡献吗？

可以，见 `CONTRIBUTING.md`。最有价值的贡献是**新的症状→判据→处置**条目，以及真实（脱敏）会话记录。

## 许可证？

MIT，见 `LICENSE`。
