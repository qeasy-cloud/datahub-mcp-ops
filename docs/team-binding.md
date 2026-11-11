# 团队执行绑定（Team Binding）—— 本 SKILL 在团队内怎么跑

> 本 SKILL 的示例默认用自带的零依赖 CLI `scripts/dh.py` + `DH_MCP_URL` / `DH_MCP_KEY` 环境变量，
> 这是**个人/实验环境**的最短路径。团队成员在**项目交付**场景必须走团队受管入口，
> 否则会绕过「项目→实例→租户」绑定、写闸门与审计。
>
> 规则来源：团队仓库《规范 15 · 官方技能包与执行绑定》**§4.2（命令替换与执行绑定）**、§5（写闸门）；
> 技能侧对应 `datahub-connect`。**本文件只做命令对照，不替代规范。**

---

## 1. 两条硬规则

1. **在线调用只走**团队受管 CLI `qeasy_mcp.py`（或受管兼容壳 `dh.py`，位于团队仓库 `scripts/mcp/` 下），
   且必须能解析出项目上下文（`--project <项目>`，或在 `projects/<项目>/` 内执行）。
2. **禁止 `DH_MCP_*` 直连**：不设 `DH_MCP_URL`/`DH_MCP_KEY` 去跑在线调用；不把租户 Key 交给任意端点；
   Key 只从团队 `keys.py` 管理的本机密钥库解析。密钥永不打印、永不入库、永不进对话。

**为什么**：`sh-…` Key 是"某租户某用户"的身份投影。直连等于把密钥发给当前端点，无法校验
"这个项目该不该用这个租户/这个环境"，也无法留下"谁在什么时候改了什么"的本地审计。

---

## 2. 命令替换表

| 本 SKILL 示例（个人/实验） | 团队场景（必须） | 说明 |
|---|---|---|
| `python scripts/dh.py doctor` | `python3 scripts/mcp/qeasy_mcp.py doctor --project <项目>` | 绑定/登记/密钥/握手/身份一次体检 |
| `python scripts/dh.py tools` | `python3 scripts/mcp/qeasy_mcp.py tools --project <项目>` | 工具清单（按域） |
| `python scripts/dh.py call <tool> --args '{…}'` | `python3 scripts/mcp/qeasy_mcp.py call <tool> --args '{…}' --project <项目>` | 只读调用 |
| 同上 + 写操作 | 同上 **再加** `--yes --reason "对象=…;范围=…;影响=…;回滚=…"` | 写闸门四要素 |
| `python scripts/dh.py call strategy.queue.job.run {direction:"target"…}` | 同上，参数里 `confirmWrite=true` | 真实写外部系统，不可绕过 |
| `python scripts/dh.py manifest` | `python3 scripts/mcp/qeasy_mcp.py manifest --project <项目>` | 机器可读工具清单（版本比对） |
| `python scripts/dh.py ref …` / 知识 MCP 调用 | `python3 scripts/mcp/knowledge.py ref\|search\|fetch\|domains\|doctor` | 知识 MCP 无租户、只读；不需要项目绑定，但同样只读 |
| 原生 `mcp__qeasy-knowledge__knowledge_*` 工具不可用/旧缓存 | `python3 scripts/mcp/knowledge.py …` | 只读兜底，口径相同 |

> 需要原样跑上游命令时，用团队受管兼容壳 `python3 scripts/mcp/dh.py …`：它拒绝 `--url/--key`
> 与 `DH_MCP_*`，复用同一套闸门与审计。

---

## 3. 项目上下文怎么给

| 方式 | 示例 | 说明 |
|---|---|---|
| 显式参数（推荐） | `--project 瘦吧-吉客云对接金蝶云星空` 或 `--project SB-JKY-KD` | 目录名或项目代码都可 |
| 当前目录推断 | `cd projects/<项目>/ && python3 scripts/mcp/qeasy_mcp.py …` | 只读任务可省略 `--project`，但写操作仍强制绑定 |
| 显式不绑定 | `--unbound` | 仅只读可用；写操作仍会要求确认 |

规则：
- 项目必须在其 `项目说明.md` 的 `mcp_profiles` 里**声明**要用的 profile；不允许跨项目借用 profile；
- 多 profile 时必须显式指定 `--profile`；
- `binding` 子命令（不联网）可以先确认"这个项目会解析到哪个实例/租户/环境"：
  `python3 scripts/mcp/qeasy_mcp.py binding --project <项目>`。

---

## 4. 写前四要素（缺一不可）

任何**有副作用**的调用（改配置、跑目标任务、清理、重置状态），`--reason` 必须写清：

```
对象=…（租户/方案 strategyId/环境）
范围=…（改哪些字段/哪些数据、多少条、是否影响他人）
影响=…（外系统是否会产生真实单据、是否可回滚）
回滚=…（backup.historyId、或反向链路、或"不可回滚，已知悉"）
```

配合：
- 破坏性操作先 `dryRun:true` 或小样本（≤5 条）验证；
- 目标端真实写入必须 `confirmWrite=true`、写后**回查外部系统**；
- 每次调用落本地审计（`python3 scripts/mcp/qeasy_mcp.py audit` 可查）。

---

## 5. 与本 SKILL 其它章节的关系

| 场景 | 本 SKILL 章节 | 团队侧入口 |
|---|---|---|
| 排障调试闭环 | §4 | `qeasy_mcp.py call … --project` |
| REF 抄在跑方案 | §3.1 / `references/09-knowledge-ref.md` | `knowledge.py ref/fetch`（只读） |
| 新建/修改方案 | §3.2/§3.3 | `qeasy_mcp.py call strategy.copy/patch … --yes --reason` |
| 脚本 | §3.4 / `references/10-script-patterns.md` | Agent 只输出代码（SaaS 不开放脚本写） |
| 安全与限流 | §6 | 只读任务不持写 scope；限流 120/分钟，批量压到 100 以内 |

---

## 6. 常见错误与判定

| 现象 | 原因 | 处置 |
|---|---|---|
| `No such file or directory: scripts/dh.py` | 团队仓库没有 `scripts/dh.py`（那是本 SKILL 自带脚本，路径相对本仓库） | 用团队仓库的 qeasy_mcp.py（在其仓库根执行）或受管兼容壳 dh.py |
| `--url`/`--key` 被拒绝 | 受管入口不接受明文端点与明文 Key | 改用 profile + `keys.py`；不要试图绕过 |
| `write_requires_project_context` 类似错误 | 写操作没给项目上下文 | 补 `--project` 或 `cd projects/<项目>/` |
| 知识 MCP 工具列表是旧的（只有 3 个） | 宿主 MCP 连接缓存未刷新 | 用 `knowledge.py ref/fetch` 只读兜底；或重启宿主连接 |
| 审计里查不到某次调用 | 调用走了直连/其它客户端 | 团队内不允许；补齐绑定后重跑并留痕 |
