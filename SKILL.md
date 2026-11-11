---
name: datahub-mcp-ops
description: Operate, debug and implement integrations on Datahub / 轻易云 (qeasy.cloud) through its MCP endpoint — reference-first and modify-first. Use when the user mentions 轻易云 / Datahub / 数据集成 / 方案 / 队列 / 字段映射 / 重推 / 巡检 / 调试 / 抄在跑方案 / REF, or provides a strategyId, jobId or 金蝶 error message and wants it understood, fixed or verified. Covers history reference (REF) cards from the knowledge MCP and template adaptation; the manual debug loop (dispatch → read queue job → consume it → patch job params → re-run) even with no daemon; copy-first / patch-first modification instead of creating new strategies; field-contract, Chinese-label, detail-row and time-parameter checkpoints; script policy (output code only); asset tools used only to resolve ids and field facts; write verification and safe cleanup.
license: MIT
metadata:
  version: 2.2.0
  homepage: https://github.com/qeasy-cloud/datahub-mcp-ops
  capability_version: "2026-11-11"
  min_server: datahub-mcp 0.1.0
  knowledge_mcp_tools: 4
  languages: zh-CN, en
---

# Datahub MCP · 运维与实施 SKILL

> 面向 AI Agent 的**可执行**手册：不是 API 目录，而是"在什么情况下、按什么顺序、调哪个工具、看到什么该做什么"。
> 全文以中文为主，工具名/参数/错误码保持原文，便于直接复制。

**读法（渐进披露）**：本文件是入口，先读完 §0–§7（约 6 分钟）即可安全工作；
需要细节时按 §11 的索引打开 `references/` 或 `playbooks/` 中的单篇，不要一次全读。

---

## 0. 什么时候用 / 不用

| ✅ 用 | ❌ 不用 |
|---|---|
| 轻易云 / Datahub 方案的巡检、排障、重推、清理 | 金蝶 ERP 内部业务逻辑（单据审核流、成本核算） |
| **新建/修改方案**：先找在跑方案（REF），再复制/打补丁落地 | 对账算法、财务口径判定 |
| 调试"源取数 / 目标写入"链路，尤其**没有守护进程**的测试环境 | 平台源码改造（那是工程任务，不是本 SKILL） |
| 配置或修正目标端字段映射（`{{Field}}`、parser、operation） | 需要客户账号密码等人工授权的事 |
| 复制成熟方案、微调、上线前检查 | 未经确认的批量删除 |
| 写/改事件脚本前的语法校验与影响评估 | **在 SaaS 上替你保存/部署脚本**（本 SKILL 只输出代码，由人操作） |

**三个前提**（不满足就先解决，否则后面全是空转）：
1. Datahub MCP 端点可达且持有 `sh-` 开头的租户密钥（`Authorization: Bearer sh-…`）；
2. 知道目标 `strategyId`（UUID）或要新建的对象（不知道就先 `strategy.list` / 查 REF）；
3. 明确当前是**只读巡检**还是要**产生副作用**（后者必须先读 §6 安全红线）。

> **团队场景（可选但强烈建议）**：在线调用统一走团队受管入口 `python3 scripts/mcp/qeasy_mcp.py`
> （必须解析项目上下文，写操作 `--yes --reason` 四要素），**禁止** `DH_MCP_*` 直连把密钥发给任意端点。
> 命令替换表、项目上下文与写闸门见仓库根 `docs/team-binding.md`（对应团队规范 15 §4.2）。

---

## 1. 60 秒上手

```bash
# ① 客户端（零依赖，Python 3.9+；也可用任意 MCP 客户端）
python scripts/dh.py doctor                     # 检查端点/密钥/协议版本
python scripts/dh.py tools                      # 列出 58 个工具（按域分组）

# ② 我是谁、能干什么
python scripts/dh.py call meta.whoami
python scripts/dh.py call meta.capabilities     # 含 tool_count 与 x-capability-version

# ③ 找到方案并体检
python scripts/dh.py call strategy.list --args '{"search":"客户","pageSize":5}'
python scripts/dh.py call strategy.dbInfo --args '{"strategyId":"<SID>"}'

# ④ 新方案：先查历史在跑方案（REF），不要从空白/资产开始
#    通过 MCP 客户端调用知识 MCP 的 knowledge_reference（4 工具之一；不属 Datahub MCP）
#    {"sourcePlatform":"…","targetPlatform":"…","object":"<FormId>","limit":5}
#    知识 MCP 与 Datahub MCP 是两个端点/两把 Key，详见 §8 与 references/09-knowledge-ref.md
```

环境变量（推荐写入 shell profile，**不要提交到仓库**）：

```bash
export DH_MCP_URL="http://127.0.0.1:5200/api/mcp"   # 或客户的 https 端点
export DH_MCP_KEY="sh-..."                          # 租户；泄露即等于交出该租户的读写权
```

没有密钥？→ `references/07-security-and-limits.md` §1（含如何申请、如何判断 scope 不足）。
知识 MCP（`qk_…`，查 REF/字段/案例）与 Datahub MCP 的分工见 §8 与 `references/09-knowledge-ref.md`。

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

参考层（不是第四层元数据，是"可运行样本"）：
  历史在跑方案组卡（知识 MCP knowledge_reference）→ 可复制模板 meta_data → 适配后落到你的租户

运行链（记住这条链，排障就是找"哪一段断了"）：
  调度 → 源端取数 → 数据条目 ADATA → 源队列 SJOB → 目标队列 TJOB → 目标写入 → 日志 LOG
                                    ↘ 异常队列 ThrowableStorage（真正的"错误"在这里）
```

**只记三个 ID**：`strategyId`（方案，UUID）、`jobId`（队列任务，24 位十六进制）、`dataId`（数据条目）。
**三个"状态"不要混**：方案 `status`（0 停 / 1 运行 / 9 删除）、`is_online`（上线）、队列/数据 `status`（5 队列 / 2 完成 / 3 错误 / 0 等待…）。
细节（字段表、Mongo 集合命名、状态枚举）→ `references/01-platform-model.md`

**资产工具的定位**：`asset.*` 只用于**解析 id 与字段事实**（platformId/connectorId/apiId/FormId/字段清单），
**不是配置起点**。配置起点是 REF 组卡与在跑方案（`references/09-knowledge-ref.md`）。

---

## 3. 核心工作流 A：新建/修改方案（REF 优先 + 修改优先）

> 这是本 SKILL 2.2 的默认姿势：**先找在跑方案，再改，不新建**。
> 详细参数、质量信号判读、实测坑 → `references/09-knowledge-ref.md`；完整实施流程 → `playbooks/p3-new-integration.md`。

### 3.1 REF 优先（四步，缺一步就不要落地）

| # | 动作 | 判据 |
|---|---|---|
| 1 | `knowledge_reference` 检索同平台/同对象在跑方案组卡（至少一个维度；标识符优先） | 有组卡，或「检索式 + 0 refs」记录 |
| 2 | 按质量信号选卡（抽 2–3 张比对，不只看第一条） | `active=true`、`errorRate` 低、`finished` 多、`evidenceGrade` 高、`topStrategies` 业务语义一致 |
| 3 | `knowledge_fetch(templateCitation)` 取可复制模板（大模板落盘，不整段读入） | 拿到源+目标 `meta_data`（脚本可能为空）；记录 `templateCitation` |
| 4 | 模板适配 9 项（平台对/对象/接口 `effect`/适配器借壳 R013/分页增量/字段契约/脱敏/脚本 review/差异留痕） | 差异清单成形，字段以**租户资产/实测**为准 |

**空结果不是失败**：按 §8.3 降级阶梯走（换标识符 → 放宽维度 → 租户内 `strategy.list` 同对象在跑方案 →
资产默认快照），并记录检索式与降级路径；**禁止编造案例**。

### 3.2 修改优先：`copy` → `patch`，`create` 是最后手段

| 场景 | 用什么 | 说明 |
|---|---|---|
| 租户内已有同平台/同对象在跑方案 | **`strategy.copy`** | 默认停止、未上线；含源/目标元数据与**既有事件脚本**（复制既有脚本不算 Agent 新增，政策见 §3.4） |
| 已有方案要改少量字段（名称/调度/adapter/某几个 meta_data 字段） | **`strategy.patch`**（服务端 capability ≥ `2026-11-11`） | 一次调用按虚拟文档路径改；RFC7386 语义（对象深合并、**数组整替**、`null` 删除）+ `dryRun` + 备份/回滚；旧工具（`update`/`source.update`/`target.update`）仍可用，等价写法见 `references/02-tool-catalog.md` §5 |
| 无样板、且 REF 与租户内都没有可参考方案 | `strategy.create` | **最后手段**：不传 `metaData` 会套资产默认快照；**传了也可能被平台覆盖** → 见 §3.3 检查点 |

**红线**：不是自己建的方案，先 `strategy.copy` 副本再改；生产方案改动必须有人确认与回滚点。

### 3.3 落地检查点（四类，逐项过）

**① create 覆盖与脚本丢失（反馈 10、11）**

- `strategy.create` 之后必须 `strategy.get {sections:"all"}` 核对：字段数、`response` 数量、分页参数是否与预期一致；
- 若被资产默认快照覆盖（如 response 17 → 73、分页字段重复）→ 立即用 `source.update` / `target.update` **整份写回**并留证据；
- `strategy.create` **不会复制事件脚本**：必须 `script.list` 核对，缺失按 §3.4 输出代码由人补（或 `strategy.copy` 从源方案复制既有脚本）。

**② 字段契约（反馈 1、2）**

- 目标字段范围 = **蓝图/字段清单（`field-contract.json`）为上限**；接口资产的字段目录只作候选，**不得把资产全量字段直接灌入**；
- 每个字段标注来源（模板 `templateCitation` / 资产 `路径#锚点`）；目标有、来源没有 → 登记**字段缺口**；
- 目标端每个 `value` 必须是 `{{源字段}}` 或显式常量（裸字段名 = 常量，见 §7 排障树）。

**③ 明细行（反馈 5）**

- 容器字段：`"field": "<明细容器>", "value": "_Flist"` 这类**裸数组名**（不带 `{{ }}`）；
- 子字段：`{{<源数组名>.<子字段>}}`，前缀必须与容器一致；容器名/前缀不一致 = 明细静默丢失；
- 一单一条 vs 一单多行：`id` 取 `FBillNo`/`FID` 还是行 ID，决定对账粒度（`references/01-platform-model.md` §10）。

**④ 中文字段与时间参数（反馈 7、6）**

- 每个 `request[]` / `response[]` 字段补 `label`（中文业务名，不是英文原样）；资产没有中文时由 Agent 翻译；
- 时间参数只保留**增量水位成对参数**（如 `modified_start/end` 或 `start/end` 一组 + 回看窗口）；
  **不要**把 created/modified/多个时间字段全塞进请求（多组并存时明确说明为什么需要）。

### 3.4 脚本政策与资产政策（用户方向 2026-11-11 拍板）

| 能力 | 政策 |
|---|---|
| `strategy.copy` 复制同租户**既有**脚本 | ✅ 允许（平台既有行为，不算 Agent 新增） |
| Agent **新增/保存/部署**脚本 | ❌ 不做：SaaS 从可见面移除 `script.create/write/delete`（保留 `list/get/validate`）；私有化由部署方配置开关，默认关 |
| 脚本产出方式 | ✅ **只输出代码**：给出事件选择、完整 PHP 片段、`script.validate` 通过的证据、由人保存/部署的操作步骤 |
| `asset.*`（6 个） | ✅ 保留可见，但只用于**解析 id 与字段事实**（platform/connector/api/FormId/字段清单）；不作为配置起点 |

> 脚本事件选择与"14 个事件只有 5 个真会触发"的机制 → `references/01-platform-model.md` §7；
> 加工厂脚本模式（补字段/明细拆分/值翻译/失败兜底/幂等键）→ `references/10-script-patterns.md`。

---

## 4. 核心工作流 B：人工调试闭环（无守护进程也能跑）

> 顾问在测试环境的常态是：**方案不启动、守护进程不开**，
> 靠"手工触发 → 手工消费 → 改参数重试"把链路调通。MCP 已完整支持这六步。

| # | 人类动作 | MCP 调用 | 判读 |
|---|---|---|---|
| 0 | **先比对在跑方案**（REF / 租户内同对象） | `knowledge_reference` → `knowledge_fetch`，或 `strategy.list` | 与参照**不一致处即嫌疑点**；模板不是答案，逐项解释差异 |
| 1 | 配源端元数据 | `strategy.get {sections:"source"}` / `strategy.source.update` | 默认 `basic` 不含 `meta_data`，要显式传 |
| 2 | 触发一次调度 | **`strategy.dispatchSource`** | 停止态**也放行**，返回 `mode=debug` + `jobId` + 组装好的请求 |
| 3 | 查请求队列 | `strategy.queue.list {direction:"source"}` | 拿 `jobId`（不是业务编号 `number`） |
| 4 | 手工执行消费 | **`strategy.queue.job.run`** | `ok`=执行成功；`has_data`=是否取到数据（两者不同！） |
| 5 | 看报错 → 改**任务参数**再跑 | `queue.job.get` → `queue.job.update` → `queue.job.run {force:true}` | **先别改元数据**；`previous` 可回滚 |
| 6 | 调通后回写元数据 | `strategy.patch`（capability ≥ 2026-11-11）或 `strategy.source.update` / `strategy.target.update` | 有 `config.rollback` 兜底 |

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

## 5. 工具地图（58 个：55 业务 + 3 meta）

> 全量入参/返回/坑 → `references/02-tool-catalog.md`；机器可读清单 → `tools/manifest.json`。
> 命名规律：`域.对象.动作`；风险等级 🟢read / 🟡write / 🟠ops / 🔴destructive。

| 域 | 工具 |
|---|---|
| **meta**（3） | `whoami` `capabilities` `enums` |
| **asset**（6，全局只读） | `platform.list` `platform.get` `connector.list` `connector.get` `api.list` `api.get` |
| **strategy 读**（8） | `list` `get` `showConfig` `dbInfo` `queue.list` `queue.job.get` `log.search` `data.search` |
| **strategy 调试**（5） | `dispatchSource` `dispatchTarget` `queue.job.run` `queue.job.update` `exception.search` |
| **strategy 写**（6） | `create` `copy` `update` `source.update` `target.update` `config.rollback`（+ 服务端 capability ≥ `2026-11-11` 的 `strategy.patch`，见 §10） |
| **strategy 生命周期**（5） | `start` `stop` `online` `offline` `checkList` |
| **strategy 数据/清理**（6） | `data.import` `data.setStatus` `dbResetStatus` `data.clean` `queue.clean` `data.cleanAll` |
| **mapping 静态映射**（12） | 分类 `category.list/get/create/update/delete` · 关系 `relation.list/create/update/delete/import` · `resolve` `usage` |
| **script**（6） | `list` `get` `validate` `create` `write` `delete`（SaaS 可见面仅前 3 个，见 §3.4） |
| **audit**（1） | `search` |

**只有 6 个是"不可逆"的**：`data.clean`、`queue.clean`、`data.cleanAll`、`script.delete`、`data.setStatus`、`mapping.category.delete`（连带删全部对照关系）。其余都能回滚或重跑。

**2026-10-28 新增的 7 个**：`strategy.queue.job.get/run/update`、`strategy.log.search`、`script.validate`、`asset.connector.list/get`。
它们解决的是"看得见 / 跑得动 / 改得了"：读任务参数、手工消费、改参重跑、读日志正文、脚本自检、连接器详情。

**v2.1.0 新增的 12 个 `mapping.*`**：静态映射是"值翻译表"（一个源值 → 一个目标值，`*` 行做兜底）。
两系统对接时 `1/2/0` → `男/女/未知`、`发票类型` → 金蝶编码，几乎每个方案都会用到。详见 §5.1。

### 5.1 静态映射怎么用（一句话 + 三个必须知道的坑）

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

## 6. 六条安全红线（违反会造成真实损失）

1. **只动自己的方案**：`strategyId` 不是自己建的 → 先 `strategy.copy` 一份副本再改；不要直接改客户生产方案。
2. **清理前必须 `stop`**：`data.clean / queue.clean / data.cleanAll` 要求方案停止且未上线；**删除不可恢复**。先 `dryRun:true` 看影响面。
3. **影响面 > 1000 行会强制二次确认**：即使密钥是 `full` 档也要 `confirmationToken`；这不是故障，是熔断。
4. **目标侧写入必须 `confirmWrite:true`**：会真实写外部 ERP，不可通过平台回滚；写完必须回查。
5. **凭据不出现在回答里**：MCP 出参已脱敏；**REST 会明文返回 `app_secret`**，不要落盘、不要贴日志、不要写进报告。
6. **限流 120 次/分钟/密钥**：批量巡检控制在 100/分钟以内；触发 `429` 按 `Retry-After` 等待，不要重试风暴。

**团队场景追加两条**（详见 `docs/team-binding.md`）：
7. **在线调用只走受管入口** `qeasy_mcp.py`（项目→profile→租户绑定 + 审计）；**禁止** `DH_MCP_*` 直连。
8. **写前四要素**：对象 / 范围 / 影响 / 回滚 说清楚，`--yes --reason` 齐全；`confirmWrite` 不可绕过。

补充（信任级别/scope/租户边界/审计）→ `references/07-security-and-limits.md`

---

## 7. 排障决策树（先定位"哪一段断了"）

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

**配置本身对不对**（不是链路问题）：先和 REF/同对象在跑方案比对 `api/effect/分页/parser/明细/字段`
→ 静态检查 `references/04-write-recipe.md` §8 自检清单 → 再改。

完整"症状 → 判据 → 处置"字典（含金蝶错误码对照）→ `references/05-diagnostics.md`

---

## 8. 与知识 MCP 组合（设计期知识 + 执行期操作）

轻易云还有一个**公开知识 MCP**，与 Datahub MCP 互补：

| | 知识 MCP | Datahub MCP（本 SKILL 主对象） |
|---|---|---|
| 端点 | `https://www.qeasy.cloud/api/mcp`（无状态；`mcp.qeasy.cloud` 为备用入口） | 租户实例 `/api/mcp` |
| 状态 | **无状态**（每请求自带 Key，GET/DELETE 405） | 有状态（`Mcp-Session-Id`） |
| 认证 | `qk_…`（Agent 可 PoW 自助注册，Standard 20 次/天） | `sh-…`（租户开放中心签发） |
| 工具 | **4 个**：`knowledge_domains` / `knowledge_search` / `knowledge_fetch` / `knowledge_reference` | 58 个运维/实施工具（+ 新版 `strategy.patch`） |
| 用途 | **设计期**：抄在跑方案（REF）、字段怎么填、增量口径、失败模式、客户案例 | **落地期**：读配置、改配置、跑任务、验结果 |

### 8.1 什么时候用哪个工具

| 需求 | 工具 |
|---|---|
| 平台/域/配额心里没数 | `knowledge_domains`（免费） |
| "这个对象别人怎么配的" | **`knowledge_reference`**（组卡 + 质量信号 + `templateCitation`） |
| 取回可复制模板 | `knowledge_fetch(citation=templateCitation)`；`format:"json"` 取结构化 `source/target/scripts` |
| 机制/字段口径/案例 | `knowledge_search`（data-integration 传 `product:"data-integration"`，按 `scenario/category` 收窄） |
| 报错的官方解释 | `knowledge_search` + `knowledge_fetch` |

**推荐用法**：先 `knowledge_reference` 找同平台同对象在跑方案 → `knowledge_fetch` 取模板 →
回 Datahub MCP 适配落地 → 报告里引用 `citation` 作为证据（≥E2）。

### 8.2 REF 的质量信号与选卡

`quality`：`finished`（成功条数）、`errorRate`、`active`（近 7 天同步）、`lastSyncDays`、`score`；
组卡另有 `runningCount`、`evidenceGrade`（A/B 档）、`objectType`、`topStrategies`、`templateCitation`。
选卡：`active=true` → `errorRate` 低 → `finished` 多 → `evidenceGrade` 高 → 业务语义一致；**抽 2–3 张比对**。

### 8.3 空结果降级阶梯（逐层、每层留痕）

1. 换标识符（`object`/`interface`/`field` 精确值；平台名换 slug/上游 code/中文名）；
2. 放宽维度（去掉 `field`，只留 `object + targetPlatform`，或只给 `query`）；
3. 租户内样板：`strategy.list` 找同平台同对象在跑方案；
4. 资产默认快照（`asset.api.get` / `strategy.create`，**最后手段**，落地后必须核对写回）；
5. 如实记录「已检索 + 0 refs + 降级路径」，**禁止编造案例**。

> 注册流程、组卡字段、实测坑、权限语义（Standard 空 refs + `accessHint`、`-32403`、`-32029`）→
> `references/06-knowledge-mcp.md` 与 `references/09-knowledge-ref.md`。

---

## 9. 交付标准（Agent 输出什么才算"做完"）

任何一次任务结束，回答里必须能让人类**复核**，至少包含：

1. **结论**：一句话（成功/失败/部分成功 + 关键数字）；
2. **证据**：用到的 `strategyId` / `jobId` / 关键返回字段（`rows_returned`、`data_created`、`status_label`、错误码）；
   **采用参考方案时**：`templateCitation` 或「检索式 + 0 refs + 降级路径」；
3. **动作**：实际执行了哪些**有副作用**的调用（写配置/跑任务/清理），以及是否可回滚；
4. **下一步**：明确的可执行动作或需要人确认的点。

模板 → `templates/ops-report.md`；反例（不要这么做）→ `references/08-anti-patterns.md`

### 9.1 13 条用户反馈对应条款（交付前自检）

| # | 反馈 | 本 SKILL 条款 |
|---|---|---|
| 1 | 不参考在跑方案，总看 API 资产 | §3.1 REF 优先四步；§8.2 选卡；空结果 §8.3 |
| 2 | 字段没按蓝图，自动把接口文档字段全配上 | §3.3-② 字段契约为范围上限 |
| 3 | 无对应资产先用其他资产占位却反复询问 | §3.1 空结果降级 + `references/09` §7（占位仅限同平台通用列表资产 + `PLACEHOLDER` + 替换计划；禁止专用壳） |
| 4 | 源平台字段值没放进 `value` | §3.3-②（`{{源字段}}` vs 裸名常量）；`references/04` §2.1 |
| 5 | 明细行没加源数组名前缀 | §3.3-③；`references/04` §2.1 |
| 6 | 时间参数全塞进请求 | §3.3-④；`references/01` §5.3.1 |
| 7 | 字段没有中文说明 | §3.3-④（补 `label` 中文）；`references/04` §8 |
| 8 | 缺脚本加工厂知识库 | §3.4 脚本政策；`references/10-script-patterns.md` |
| 9 | 不会创建静态映射 | §5.1 静态映射四步 |
| 10 | `strategy.create` 覆盖 `meta_data` | §3.2/§3.3-①（create 后核对并写回） |
| 11 | 事件脚本不随 `create` 复制 | §3.3-①（`script.list` 核对） |
| 12 | 配置方案时无需管连接器内容 | §2 资产定位（连接器只读确认环境，不在方案配置阶段修改） |
| 13 | 官网找不到赛狐接口 | §8.3 空结果如实记录 + 降级（0 命中 ≠ 平台无覆盖），不编造 |

---

## 10. 版本与兼容

- 本 SKILL `2.2.0`：文档基线 = Datahub MCP `datahub-mcp 0.1.0` / `x-capability-version 2026-11-11`（58 工具 + `strategy.patch`）。
- **兼容矩阵**：

| 服务端 capability | 本 SKILL 可用性 |
|---|---|
| `2026-10-28`（58 工具） | ✅ 除 `strategy.patch` 外全部可用（用 `source.update`/`target.update` 等价写法） |
| `2026-11-11`+（58 工具 + `strategy.patch`） | ✅ 全部可用；`strategy.patch` 为修改类默认入口 |
| `2026-10-26` / 39/46 工具 | ⚠️ 部分工具不存在，按 `meta.capabilities` 的实际 `tool_count` 降级 |

- `tools/manifest.json` 是**服务端生成物**：本版发布前如服务端尚未部署 `2026-11-11`，
  manifest 仍为 `2026-10-28`，**待服务端发布后由 `python scripts/dh.py manifest` 重新生成**（不要手编工具列表）。
- 服务端能力升级后：重生成 manifest → `python scripts/validate_skill.py` 校验文档与工具一致（CI 同款）。
- 兼容性补充（无状态 MCP 客户端、只读档位、旧版 39 工具差异）→ `docs/clients.md` §4。

---

## 11. 按任务找文档（渐进披露索引）

| 你要做的事 | 打开 |
|---|---|
| 5 分钟建立正确心智模型 | `references/01-platform-model.md` |
| **抄在跑方案（REF）：检索/选卡/取模板/降级/实测坑** | **`references/09-knowledge-ref.md`** |
| 用知识 MCP 查字段/案例/口径（4 工具、注册、引用纪律） | `references/06-knowledge-mcp.md` |
| 查某个工具的入参/返回/坑（含 `strategy.patch` 兼容） | `references/02-tool-catalog.md` |
| 跑通/排查调试闭环 | `references/03-debug-loop.md` + `playbooks/p1-debug-source.md` |
| 让目标端真正写进金蝶（copy/patch 优先、字段检查点） | `references/04-write-recipe.md` + `playbooks/p2-debug-target-write.md` |
| 报错了，想按症状定位 | `references/05-diagnostics.md` |
| 从需求到上线，完整实施一遍（REF-first） | `playbooks/p3-new-integration.md` |
| 脚本只输出代码：事件选择与加工厂模式 | `references/10-script-patterns.md` |
| 团队命令替换/项目上下文/写前四要素 | `docs/team-binding.md` |
| 安全边界、密钥、限流、审计 | `references/07-security-and-limits.md` |
| 我这样做是不是错的 | `references/08-anti-patterns.md` |
| 批量重推 / 收尾清理 | `playbooks/p4-ops-and-cleanup.md` |
| 复制现成提示词 | `examples/prompts.md` |
| 看一次真实会话长什么样 | `examples/session-source-debug.md` |
| 客户端怎么接（Claude/Cursor/VS Code） | `docs/clients.md` |
| 常见疑问 | `docs/faq.md` |
