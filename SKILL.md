---
name: datahub-mcp-ops
description: >
  Operate, debug and implement integrations on Datahub / 轻易云 (qeasy.cloud) through its
  MCP endpoint: inspect strategies, connectors and API assets; run the manual debug loop
  (dispatch → read queue job → consume it → patch job params → re-run) even when no daemon
  is running; diagnose field-mapping and Kingdee (金蝶) batchSave failures; verify writes;
  clean up safely. Use when the user mentions 轻易云 / Datahub / 数据集成 / 方案 / 队列 /
  字段映射 / 重推 / 巡检 / 调试, or provides a strategyId, jobId or 金蝶 error message and
  wants it understood, fixed or verified.
license: MIT
metadata:
  version: 2.1.0
  homepage: https://github.com/qeasy-cloud/datahub-mcp-ops
  capability_version: "2026-10-28"
  min_server: datahub-mcp 0.1.0
  languages: zh-CN, en
---

# Datahub MCP · 运维与实施 SKILL

> 面向 AI Agent 的**可执行**手册：不是 API 目录，而是"在什么情况下、按什么顺序、调哪个工具、看到什么该做什么"。
> 全文以中文为主，工具名/参数/错误码保持原文，便于直接复制。

**读法（渐进披露）**：本文件是入口，先读完 §0–§6（约 5 分钟）即可安全工作；
需要细节时按 §9 的索引打开 `references/` 或 `playbooks/` 中的单篇，不要一次全读。

---

## 0. 什么时候用 / 不用

| ✅ 用 | ❌ 不用 |
|---|---|
| 轻易云 / Datahub 方案的巡检、排障、重推、清理 | 金蝶 ERP 内部业务逻辑（单据审核流、成本核算） |
| 调试"源取数 / 目标写入"链路，尤其**没有守护进程**的测试环境 | 对账算法、财务口径判定 |
| 配置或修正目标端字段映射（`{{Field}}`、parser、operation） | 平台源码改造（那是工程任务，不是本 SKILL） |
| 复制成熟方案、微调、上线前检查 | 需要客户账号密码等人工授权的事 |
| 写/改事件脚本前的语法校验与影响评估 | 未经确认的批量删除 |

**三个前提**（不满足就先解决，否则后面全是空转）：
1. MCP 端点可达且持有 `sh-` 开头的租户密钥（`Authorization: Bearer sh-…`）；
2. 知道目标 `strategyId`（UUID），不知道就先 `strategy.list`；
3. 明确当前是**只读巡检**还是要**产生副作用**（后者必须先读 §5 安全红线）。

---

## 1. 60 秒上手

```bash
# ① 客户端（零依赖，Python 3.9+；也可用任意 MCP 客户端）
python scripts/dh.py doctor                     # 检查端点/密钥/协议版本
python scripts/dh.py tools                      # 列出 58 个工具（按域分组）

# ② 我是谁、能干什么
python scripts/dh.py call meta.whoami
python scripts/dh.py call meta.capabilities

# ③ 找到方案并体检
python scripts/dh.py call strategy.list --args '{"search":"客户","pageSize":5}'
python scripts/dh.py call strategy.dbInfo --args '{"strategyId":"<SID>"}'
```

环境变量（推荐写入 shell profile，**不要提交到仓库**）：

```bash
export DH_MCP_URL="http://127.0.0.1:5200/api/mcp"   # 或客户的 https 端点
export DH_MCP_KEY="sh-..."                          # 租户；泄露即等于交出该租户的读写权
```

没有密钥？→ `references/07-security-and-limits.md` §1（含如何申请、如何判断 scope 不足）。

> 若客户端不是本 SKILL 自带的脚本，把 `tools/mcp-config.example.json` 里的
> `mcpServers` 片段粘到 Claude Code / Cursor / VS Code / Cline 的配置里即可（见 `docs/clients.md`）。

---

## 2. 心智模型（先记住这 12 行）

```
租户 lessee ─┬─ 平台 platform（适配器定义，如 Kingdee.Cloud）
             ├─ 连接器 connector（host / 数据中心 / 账号 / app_secret）
             ├─ 接口资产 api_asset（executeBillQuery、batchSave…）
             └─ 方案 strategy（一次集成任务）  ← 你 90% 的操作对象
                   ├─ 源端 source：connector + api + meta_data（取数参数 + 响应字段）
                   ├─ 目标端 target：connector + api + meta_data（写入参数 + 字段映射）
                   └─ 调度 crontab：source / target 各一个

运行链（记住这条链，排障就是找"哪一段断了"）：
  调度 → 源端取数 → 数据条目 ADATA → 源队列 SJOB → 目标队列 TJOB → 目标写入 → 日志 LOG
                                    ↘ 异常队列 ThrowableStorage（真正的"错误"在这里）
```

**只记三个 ID**：`strategyId`（方案，UUID）、`jobId`（队列任务，24 位十六进制）、`dataId`（数据条目）。
**三个"状态"不要混**：方案 `status`（0 停 / 1 运行 / 9 删除）、`is_online`（上线）、队列/数据 `status`（5 队列 / 2 完成 / 3 错误 / 0 等待…）。
细节（字段表、Mongo 集合命名、状态枚举）→ `references/01-platform-model.md`

---

## 3. 核心工作流：人工调试闭环（无守护进程也能跑）

> 这是本 SKILL 存在的最重要理由。顾问在测试环境的常态是：**方案不启动、守护进程不开**，
> 靠"手工触发 → 手工消费 → 改参数重试"把链路调通。MCP 已完整支持这六步。

| # | 人类动作 | MCP 调用 | 判读 |
|---|---|---|---|
| 1 | 配源端元数据 | `strategy.get {sections:"source"}` / `strategy.source.update` | 默认 `basic` 不含 `meta_data`，要显式传 |
| 2 | 触发一次调度 | **`strategy.dispatchSource`** | 停止态**也放行**，返回 `mode=debug` + `jobId` + 组装好的请求 |
| 3 | 查请求队列 | `strategy.queue.list {direction:"source"}` | 拿 `jobId`（不是业务编号 `number`） |
| 4 | 手工执行消费 | **`strategy.queue.job.run`** | `ok`=执行成功；`has_data`=是否取到数据（两者不同！） |
| 5 | 看报错 → 改**任务参数**再跑 | `queue.job.get` → `queue.job.update` → `queue.job.run {force:true}` | **先别改元数据**；`previous` 可回滚 |
| 6 | 调通后回写元数据 | `strategy.source.update` / `strategy.target.update` | 有 `config.rollback` 兜底 |

目标侧同理，但多一道硬门槛：

```bash
# 目标侧会真实写外部 ERP：必须显式确认，信任级别不能豁免
python scripts/dh.py call strategy.dispatchTarget --args '{"strategyId":"<SID>"}'          # → jobId
python scripts/dh.py call strategy.queue.job.get  --args '{"strategyId":"<SID>","direction":"target","jobId":"<TID>"}'
python scripts/dh.py call strategy.queue.job.run  --args '{"strategyId":"<SID>","direction":"target","jobId":"<TID>","confirmWrite":true}'
```

**判读口诀**（背下来，能省一半来回）：

- `ok=true, has_data=false` → 不是"成功"，是**没取到数**：过滤条件过窄，或源系统空响应（平台把空响应当"完成"）。→ 用 `queue.job.update` 放宽 `FilterString` 重跑，或 `log.search(level=debug)` 看响应体。
- `skipped=already_finished` → 任务已结束没重跑，需要 `force=true`。
- `exception.search` 为 0 但 `dbInfo` 有 fatal → 先看日志文本是否 `0x_debug_` 开头：**那是调试留痕，不是错误**（老环境的历史数据）。
- 平台内"已写入" ≠ 外部系统已入库 → **必须回查**（`executeBillQuery` 按单号查）。

完整分步（含读取请求/响应正文、错误恢复）→ `playbooks/p1-debug-source.md`、`playbooks/p2-debug-target-write.md`、`references/03-debug-loop.md`

---

## 4. 工具地图（58 个：55 业务 + 3 meta）

> 全量入参/返回/坑 → `references/02-tool-catalog.md`；机器可读清单 → `tools/manifest.json`。
> 命名规律：`域.对象.动作`；风险等级 🟢read / 🟡write / 🟠ops / 🔴destructive。

| 域 | 工具 |
|---|---|
| **meta**（3） | `whoami` `capabilities` `enums` |
| **asset**（6，全局只读） | `platform.list` `platform.get` `connector.list` `connector.get` `api.list` `api.get` |
| **strategy 读**（8） | `list` `get` `showConfig` `dbInfo` `queue.list` `queue.job.get` `log.search` `data.search` |
| **strategy 调试**（5） | `dispatchSource` `dispatchTarget` `queue.job.run` `queue.job.update` `exception.search` |
| **strategy 写**（6） | `create` `copy` `update` `source.update` `target.update` `config.rollback` |
| **strategy 生命周期**（5） | `start` `stop` `online` `offline` `checkList` |
| **strategy 数据/清理**（6） | `data.import` `data.setStatus` `dbResetStatus` `data.clean` `queue.clean` `data.cleanAll` |
| **mapping 静态映射**（12） | 分类 `category.list/get/create/update/delete` · 关系 `relation.list/create/update/delete/import` · `resolve` `usage` |
| **script**（6） | `list` `get` `validate` `create` `write` `delete` |
| **audit**（1） | `search` |

**只有 6 个是"不可逆"的**：`data.clean`、`queue.clean`、`data.cleanAll`、`script.delete`、`data.setStatus`、`mapping.category.delete`（连带删全部对照关系）。其余都能回滚或重跑。

**2026-10-28 新增的 7 个**：`strategy.queue.job.get/run/update`、`strategy.log.search`、`script.validate`、`asset.connector.list/get`。
它们解决的是"看得见 / 跑得动 / 改得了"：读任务参数、手工消费、改参重跑、读日志正文、脚本自检、连接器详情。

**v2.1.0 新增的 12 个 `mapping.*`**：静态映射是"值翻译表"（一个源值 → 一个目标值，`*` 行做兜底）。
两系统对接时 `1/2/0` → `男/女/未知`、`发票类型` → 金蝶编码，几乎每个方案都会用到。详见 §4.1。

### 4.1 静态映射怎么用（一句话 + 三个必须知道的坑）

标准动作：`mapping.category.create` → `mapping.relation.import` 批量灌对照 →
把返回的 `categoryId` 挂到字段的 `mapping.target` → `mapping.resolve` 单值试算 →
`mapping.usage` 反查"到底哪些方案在用"。

挂载形态（写在 `meta_data.request[]` / `response[]` 的字段项上）：

```json
{ "field": "FName", "value": "{{FName}}", "mapping": { "target": "<categoryId>", "direction": "positive" } }
```

| 坑 | 现象 | 处置 |
|---|---|---|
| **未命中不报错** | "映射配了但没生效" | 没有精确行且无 `a_value="*"` 兜底行时，平台**原值直通**；用 `mapping.resolve` 看 `matched` |
| **生效位置不对称** | 源端字段挂了映射没反应 | 目标端（Execute）顶层字段生效；源端（Query）**只有 object/array 子项**生效，顶层标量不生效 |
| **删分类连带删表** | 删完方案开始输出原值 | 仍被引用时工具直接拒绝（`mapping_category_in_use`），要删必须显式 `force=true` |

反向翻译（目标值 → 源值）用 `direction: "reverse"`；同一分类两个方向共用一张表（`a_value` ↔ `b_value`）。

---

## 5. 六条安全红线（违反会造成真实损失）

1. **只动自己的方案**：`strategyId` 不是自己建的 → 先 `strategy.copy` 一份副本再改；不要直接改客户生产方案。
2. **清理前必须 `stop`**：`data.clean / queue.clean / data.cleanAll` 要求方案停止且未上线；**删除不可恢复**。先 `dryRun:true` 看影响面。
3. **影响面 > 1000 行会强制二次确认**：即使密钥是 `full` 档也要 `confirmationToken`；这不是故障，是熔断。
4. **目标侧写入必须 `confirmWrite:true`**：会真实写外部 ERP，不可通过平台回滚；写完必须回查。
5. **凭据不出现在回答里**：MCP 出参已脱敏；**REST 会明文返回 `app_secret`**，不要落盘、不要贴日志、不要写进报告。
6. **限流 120 次/分钟/密钥**：批量巡检控制在 100/分钟以内；触发 `429` 按 `Retry-After` 等待，不要重试风暴。

补充（信任级别/scope/租户边界/审计）→ `references/07-security-and-limits.md`

---

## 6. 排障决策树（先定位"哪一段断了"）

```
数据不增？
├─ 方案 status=0？ ────────────────→ 调试期正常。dispatch 后手工 queue.job.run
├─ 源队列有 job 但不动？ ──────────→ 无守护进程：queue.job.run 消费；有守护：查 worker
├─ job ok 但 has_data=false？ ─────→ 过滤条件/空响应：放宽 FilterString 重跑
├─ job status=3？ ─────────────────→ log.search(level=error,fatal) + exception.search
└─ 日志只有 begin_ ？ ─────────────→ 队列未被消费

数据有但不写目标？
├─ 目标队列空？ ───────────────────→ dispatchTarget（+ confirmWrite 消费）
├─ 目标 job params.Model 里全是空？ → 没有字段映射：target.update 补 {{Field}}
├─ 报"格式错误，不能转换为字典类型" → 基础资料字段缺 ConvertObjectParser
├─ 报"没有数据需要保存" ───────────→ 所有字段被清空/无映射
└─ 报"组织内编码唯一" ─────────────→ 幂等命中，数据变 repeat 不是错误

写进去但不确定？
└─ 必须回查外部系统（executeBillQuery 按单号）；平台 status 不是证据
```

完整"症状 → 判据 → 处置"字典（含金蝶错误码对照）→ `references/05-diagnostics.md`

---

## 7. 与知识 MCP 组合（设计期知识 + 执行期操作）

轻易云还有一个**公开知识 MCP**，与 Datahub MCP 互补：

| | 知识 MCP | Datahub MCP（本 SKILL 主对象） |
|---|---|---|
| 端点 | `https://mcp.qeasy.cloud/api/mcp` | 租户实例 `/api/mcp` |
| 状态 | **无状态**（每请求自带 Key，GET/DELETE 405） | 有状态（`Mcp-Session-Id`） |
| 认证 | `qk_live_…`（Agent 可 PoW 自助注册，20 次/天 public） | `sh-…`（租户开放中心签发） |
| 工具 | `knowledge_domains` / `knowledge_search` / `knowledge_fetch` | 58 个运维/实施工具 |
| 用途 | **设计期**：字段怎么填、增量口径、失败模式、客户案例 | **落地期**：读配置、改配置、跑任务、验结果 |

**推荐用法**：先用知识 MCP 查"金蝶客户写入要哪些字段/什么 parser"，再回 Datahub MCP 改映射；报告里引用返回的 `citation`（形如 `docs/knowledge/objects/…/BD_Customer.write.md`）作为证据。

注册流程（实测可用）与引用纪律 → `references/06-knowledge-mcp.md`

---

## 8. 交付标准（Agent 输出什么才算"做完"）

任何一次任务结束，回答里必须能让人类**复核**，至少包含：

1. **结论**：一句话（成功/失败/部分成功 + 关键数字）；
2. **证据**：用到的 `strategyId` / `jobId` / 关键返回字段（`rows_returned`、`data_created`、`status_label`、错误码）；
3. **动作**：实际执行了哪些**有副作用**的调用（写配置/跑任务/清理），以及是否可回滚；
4. **下一步**：明确的可执行动作或需要人确认的点。

模板 → `templates/ops-report.md`；反例（不要这么做）→ `references/08-anti-patterns.md`

---

## 9. 按任务找文档（渐进披露索引）

| 你要做的事 | 打开 |
|---|---|
| 5 分钟建立正确心智模型 | `references/01-platform-model.md` |
| 查某个工具的入参/返回/坑 | `references/02-tool-catalog.md` |
| 跑通/排查调试闭环 | `references/03-debug-loop.md` + `playbooks/p1-debug-source.md` |
| 让目标端真正写进金蝶 | `references/04-write-recipe.md` + `playbooks/p2-debug-target-write.md` |
| 报错了，想按症状定位 | `references/05-diagnostics.md` |
| 从需求到上线，完整实施一遍 | `playbooks/p3-new-integration.md` |
| 用知识 MCP 查字段/案例/口径 | `references/06-knowledge-mcp.md` |
| 安全边界、密钥、限流、审计 | `references/07-security-and-limits.md` |
| 我这样做是不是错的 | `references/08-anti-patterns.md` |
| 批量重推 / 收尾清理 | `playbooks/p4-ops-and-cleanup.md` |
| 复制现成提示词 | `examples/prompts.md` |
| 看一次真实会话长什么样 | `examples/session-source-debug.md` |
| 客户端怎么接（Claude/Cursor/VS Code） | `docs/clients.md` |
| 常见疑问 | `docs/faq.md` |

---

## 10. 版本与兼容

- 本 SKILL `2.1.0` 对应服务端 `datahub-mcp 0.1.0` / `x-capability-version 2026-10-28`（58 工具）。
- 服务端能力升级后：`python scripts/dh.py manifest > tools/manifest.json` 重新生成清单，
  再跑 `python scripts/validate_skill.py` 校验文档与工具是否仍然一致（CI 同款）。
- 兼容性说明（无状态 MCP 客户端、只读档位、旧版 39 工具的差异）→ `docs/clients.md` §兼容矩阵。
