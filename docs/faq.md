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

用 `meta.capabilities` 的 `tool_count` 与 `x-capability-version` 对比。常见原因：
① 服务端版本不同（39 / 46 / 58 / 58+patch）；② 密钥 scope 不足；③ `read_only` 档位。
`docs/clients.md` §4 有兼容矩阵。

- 本 SKILL **2.2.0** 的文档基线是 capability `2026-11-11`（58 工具 + `strategy.patch`）。
- `tools/manifest.json` 是服务端生成物：服务端发布新版后由 `python scripts/dh.py manifest` 重新生成，
  **不要手编工具列表**；旧 manifest 上看到的 capability 版本落后是正常的，以 `meta.capabilities` 为准。

## `strategy.patch` 是什么？为什么文档里有但工具列表没有？

`strategy.patch` 是 **2026-11-11 新增**的"修改已有方案"入口（按虚拟文档路径改，RFC7386 语义 + dryRun + 备份回滚），
服务端 capability **≥ `2026-11-11`** 才可用。旧服务端没有它：用 `strategy.update` / `strategy.source.update` /
`strategy.target.update` 等价改写（见 `references/02-tool-catalog.md` §5 兼容矩阵）。

## 两个 MCP 有什么区别？

- **Datahub MCP**（租户端点）：58 个工具（+ 新版 `strategy.patch`），读写你的真实数据，有状态。
- **知识 MCP**（`https://www.qeasy.cloud/api/mcp`，备用 `mcp.qeasy.cloud`）：**4 个工具**
  （`knowledge_domains` / `knowledge_search` / `knowledge_fetch` / `knowledge_reference`），只读、无租户、无状态。
前者回答"现在是什么"，后者回答"应该怎么配、别人怎么配的"。
新方案第一步是 `knowledge_reference` 找在跑方案（REF），见 `references/09-knowledge-ref.md`。

## REF（`knowledge_reference`）返回 0 条，是不是平台没有？

不一定。三种原因要分清：① 该平台对/对象没有在跑方案（覆盖缺口）；② Standard Key 看不到 restricted 组卡
（返回空 + `accessHint`，不是 Key 失效）；③ 参数/协议问题（`-32602`/`-32029`/`429`/`401`）。
处置按降级阶梯：换标识符 → 放宽维度 → 租户内 `strategy.list` 同对象在跑方案 → 资产默认快照，
并记录「检索式 + 0 refs + 降级路径」。**0 命中不等于平台无覆盖，更不能编造案例。**
详见 `references/09-knowledge-ref.md` §7。

## 为什么团队场景不能直接 `export DH_MCP_URL` / `DH_MCP_KEY`？

本 SKILL 的 `dh.py` 示例面向个人/实验环境。团队交付要求"项目→实例→租户"绑定、写闸门与审计，
在线调用统一走 `python3 scripts/mcp/qeasy_mcp.py … --project <项目>`；直连会绕过绑定与审计，
且把租户 Key 发给任意端点。命令替换表见 `docs/team-binding.md`。

## 密钥从哪来？能自助注册吗？

- Datahub MCP：租户「开放中心」签发（`sh-…`），**不能**自助注册。
- 知识 MCP：Agent 可 PoW 自助注册（`qk_live_…`，Standard 20 次/天）。

## 密钥丢了/被吊销了怎么办？

平台只存 hash，无法找回，只能重新签发。
⚠️ 注意：在**共用同一个库**的环境跑会重建 `dh_mcp_grant` 的测试，会清空所有密钥（本仓库已加安全阀）。

## 为什么有些工具在我的密钥下不可见？

scope 不足或档位是 `read_only`。`meta.capabilities` 会给出每个工具在当前密钥下的 `callable`。

## 能不能删掉一个方案？

本 SKILL 2.2.0 所覆盖的 MCP 工具里**没有**"删除方案"入口，只有 `offline`（置未上线）与清理数据/队列。
平台侧的删除默认是**软删除**（标准 API 语义），是否开放 MCP 入口另行评估；
在此之前，删除方案仍属平台管理动作，不由 Agent 随手做。

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

## 能不能让 Agent 直接帮我保存/部署脚本？

不能（2026-11-11 政策）：SaaS 从 MCP 可见面移除 `script.create/write/delete`（保留 `list/get/validate`），
私有化由部署方开关放开（默认关）。Agent **只输出代码**（事件选择 + 完整 PHP + `script.validate` 证据 +
保存步骤 + 验证计划），由人在平台保存；`strategy.copy` 复制既有脚本是平台行为，不算 Agent 新增。
详见 `references/10-script-patterns.md`。

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
