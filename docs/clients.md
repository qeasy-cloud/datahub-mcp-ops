# 客户端接入与兼容性

> 本 SKILL 的 `scripts/dh.py` 是"零依赖兜底"；如果你已经在用 Claude Code / Cursor / VS Code / Cline，
> 直接把配置粘过去即可。两种方式可以并存。

---

## 1. 三种接入方式

| 方式 | 适合 | 优点 | 代价 |
|---|---|---|---|
| `scripts/dh.py` | 任何环境、CI、脚本化 | 零依赖、可脚本、可 `manifest` 生成清单 | 需要 Python 3.9+ |
| 客户端原生 MCP 配置 | 日常对话式使用 | Agent 自动发现 58 个工具 | 需要客户端支持 Streamable HTTP |
| 平台 UI / REST | 人工核对、浏览器调试 | 直观 | 不是 Agent 路径；REST 会返回明文凭据 |

### 1.1 `dh.py`（推荐作为兜底与 CI）

```bash
export DH_MCP_URL="https://<HOST>/api/mcp"
export DH_MCP_KEY="sh-..."
python scripts/dh.py doctor
```

### 1.2 MCP 客户端配置

把 `../tools/mcp-config.example.json` 里对应片段粘到客户端配置：

- **Claude Code / Claude Desktop**：`mcpServers.datahub`（HTTP 直连；桌面版可用 `mcp-remote` 桥接）。
- **Cursor**：`~/.cursor/mcp.json` 的 `mcpServers`。
- **VS Code（Copilot / Continue）**：`servers` 段（`"type": "http"`）。
- **Cline**：MCP Servers → Remote / HTTP。

关键字段：
```jsonc
{"type":"http","url":"https://<HOST>/api/mcp",
 "headers":{"Authorization":"Bearer ${DH_MCP_KEY}"}}
```

### 1.3 环境变量注入

| 客户端 | 变量写法 |
|---|---|
| Claude Code / Desktop | `${DH_MCP_KEY}`（由客户端展开） |
| VS Code | `${env:DH_MCP_KEY}` |
| Cursor / Cline | 多数版本支持 `${env:...}`；不支持就直接填（仅本机配置，勿提交） |

---

## 2. 传输细节（自己实现客户端时看这里）

| 项 | 值 |
|---|---|
| 协议 | MCP Streamable HTTP + JSON-RPC 2.0 |
| 协议版本 | `2025-06-18`（服务端会协商） |
| 端点 | `POST /api/mcp` |
| 会话 | 有状态：`initialize` 响应头带 `Mcp-Session-Id`，后续请求必须回传 |
| SSE | 服务端可能返回 `text/event-stream`，需按 `data:` 行解析 |
| 认证 | `Authorization: Bearer sh-…`（缺失/失效 → 401） |
| 限流 | 120 次/分钟/密钥（`429` + `Retry-After`） |

最小请求序列：

```
POST initialize           → 记录 Mcp-Session-Id
POST notifications/initialized
POST tools/list
POST tools/call {"name":"…","arguments":{…}}
```

> 公开知识 MCP 是**另一套**：`https://mcp.qeasy.cloud/api/mcp`，无状态（GET/DELETE → 405），
> 每请求自带 `qk_live_…`，工具只有 3 个。别把两者混用。

---

## 3. Windows 下的三个坑

1. **内联 JSON 被 shell 吞引号**：`--args '{"a":"b"}'` 在 PowerShell 里可能变成 `{a:b}`。
   → 用 `--param a=b`，或 `--args @args.json`。
2. **控制台编码**：旧版 PowerShell 默认按 ANSI 解码子进程输出，中文会花。
   ```powershell
   [Console]::OutputEncoding = [Text.Encoding]::UTF8
   $OutputEncoding = [Console]::OutputEncoding
   ```
   `dh.py` 已强制 UTF-8 输出并带 ASCII 兜底。
3. **代理环境变量**：本机测试时清掉代理，否则 `127.0.0.1` 可能被转发。
   ```powershell
   $env:http_proxy=''; $env:https_proxy=''; $env:HTTP_PROXY=''; $env:HTTPS_PROXY=''
   ```

---

## 4. 兼容矩阵

### 4.1 服务端能力版本

| 能力版本 | 工具数 | 关键差异 | 本 SKILL |
|---|---|---|---|
| `2026-10-26` | 39 | 无 `queue.job.*` / `log.search` / `script.validate` / `connector.*` | v1.x（已归档） |
| `2026-10-28` | 46 | 新增 7 个；`get` 默认 `basic`；dispatch 停止态放行；预演+熔断 | v2.0.0 |
| `2026-10-28`（含静态映射） | **58** | 新增 12 个 `mapping.*`；`queue.job.get` 支持 `rawParams` | **v2.1.0（当前）** |

> 用 `meta.capabilities` 的 `tool_count` 快速判断服务端版本；
> 与 `tools/manifest.json` 的 `capability_version` 对比即可知道文档是否过期。

### 4.2 只读档位下的行为

| 场景 | `read_only` | `standard` | `full` |
|---|---|---|---|
| `strategy.list/get/dbInfo/log.search` | ✅ | ✅ | ✅ |
| `exception.search` | ✅（需 `exception:read`） | ✅ | ✅ |
| `audit.search` | ❌（敏感读，不在只读档） | ✅ | ✅ |
| `dispatch*` / `queue.job.run` | ❌ | ✅（需确认） | ✅ |
| `data.clean` 等破坏性 | ❌ | ✅（需令牌） | ✅（超阈值仍需令牌） |
| `script.*` | ❌ | ❌（需 `script:*`） | ✅（且需管理员） |

### 4.3 旧版本行为差异（升级时注意）

| 行为 | 旧（≤39 工具） | 新（46 工具） |
|---|---|---|
| `strategy.get` | 总是返回完整 `meta_data`（~40KB） | 默认 `sections=basic`；要全量显式传 |
| `dispatchSource`（停止态） | `strategy_not_running` | 放行，回传 `jobId` + `mode=debug` |
| 破坏性操作 `trust=full` | 直接执行、无预演 | 执行但返回 `precheck`；超阈值强制令牌 |
| 带 `confirmationToken` | `full` 档静默忽略 | 一律校验核销（重放被拒） |
| `script.create` 返回 | `compiled:true` 不可信 | `file_written` + `syntax_ok`（落库前 `php -l`） |
| 调试日志 | 记为 FATAL | 记为 `debug`（`dbInfo.log.debug`） |

---

## 5. 常见连接问题

| 现象 | 原因 | 处置 |
|---|---|---|
| `401 需要 API Key` | 密钥缺失/被吊销/格式错 | 重新签发；确认前缀是 `sh-` |
| `405` | 对端点发了 GET/DELETE | 只用 `POST`（知识 MCP 也是这样） |
| `tools/list` 返回的工具比文档少 | scope 不足或 `read_only` | `meta.capabilities` 看 `callable` |
| 每次调用都 401，但 `doctor` 通过 | 客户端没回传 `Mcp-Session-Id` | 用 `dh.py` 或检查客户端实现 |
| 调用超时 | 单个任务同步执行可能较慢（目标写入） | 提高超时（`DH_MCP_TIMEOUT`），或先 `queue.job.get` 确认规模 |
| 中文乱码 | 控制台编码 | 见 §3.2 |
