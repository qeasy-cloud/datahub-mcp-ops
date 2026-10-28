# 06 · 知识 MCP：设计期知识与引用纪律

> 轻易云有**两个** MCP，别混：
>
> | | 知识 MCP（本篇） | Datahub MCP（本 SKILL 主对象） |
> |---|---|---|
> | 端点 | `https://mcp.qeasy.cloud/api/mcp` | 你的租户实例 `/api/mcp` |
> | 形态 | **无状态**（每请求自带 Key；`GET`/`DELETE` → 405） | 有状态（`Mcp-Session-Id`） |
> | 密钥 | `qk_live_…`（Agent 可 PoW 自助注册，Standard 20 次/天） | `sh-…`（租户开放中心签发） |
> | 工具 | 3 个：`knowledge_domains` / `knowledge_search` / `knowledge_fetch` | 46 个运维/实施工具 |
> | 回答 | 文档 + 可追溯引用 | 真实配置与执行结果 |
>
> **分工**：知识 MCP 回答"应该怎么配"（字段、口径、案例）；Datahub MCP 回答"现在是什么、改了会怎样"。

---

## 1. 什么时候用（省调用，也省猜）

| 该用 | 不必用（本 SKILL 已内建） |
|---|---|
| 某业务对象的**最新字段清单**（金蝶客户要哪些必填） | 平台三层元数据模型、`type`/`effect` 语义 → `01-platform-model.md` |
| 平台间**字段口径差异**（同一个"客户"怎么对） | `{{}}` 语法、parser、`operation` → `01` §3 |
| **客户案例**的特殊约定（审批流前缀、行业字段） | 调试闭环步骤 → `03-debug-loop.md` |
| 某个报错的**官方解释与推荐修法** | 金蝶常见报错对照 → `04` §6、`05` §3 |
| 增量口径的**行业惯例**（按 modified 还是 created） | 分页/增量机制 → `01` §5 |

> 原则：**机制类问题先查本 SKILL，事实类问题（字段/案例/版本）才查知识 MCP。**
> 这样能把每天的 20 次配额留给真正需要"最新事实"的问题。

---

## 2. 注册（Agent 自助，实测可用）

无状态端点：每个请求自带 `Authorization: Bearer qk_live_…`。没有 Key 时 `POST` 返回：

```json
{"jsonrpc":"2.0","id":1,"error":{"code":-32001,"message":"需要 API Key，请先注册",
 "data":{"errorKind":"authentication_required",
         "registration":{"human":"/register","agent":"/api/v1/agent-registrations",
                         "challenge":"/api/v1/agent-registrations/challenge"}}}}
```

### 2.1 三步拿到 Standard Key

```bash
# ① 取挑战（201）
curl -sX POST https://qeasy.cloud/api/v1/agent-registrations/challenge \
  -H 'Content-Type: application/json' -d '{}'
# → {"data":{"challengeId":"…","algorithm":"sha256",
#            "input":"challengeId + ':' + nonce","difficulty":18,"expiresAt":"…"}}
```

```python
# ② 算 PoW：sha256("<challengeId>:<nonce>") 的**前导零位数** ≥ difficulty
import hashlib
def bits(h):
    n = 0
    for ch in h:
        v = int(ch, 16)
        if v == 0: n += 4; continue
        n += 4 - v.bit_length(); break
    return n
nonce = next(str(i) for i in range(10_000_000)
             if bits(hashlib.sha256(f"{cid}:{i}".encode()).hexdigest()) >= 18)
```

```bash
# ③ 提交（201）。注意 nonce 必须是**字符串**
curl -sX POST https://qeasy.cloud/api/v1/agent-registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-agent","framework":"python","challengeId":"…","nonce":"123456"}'
# → {"data":{"agent":{…},
#            "mcpKey":{"prefix":"qk_live_1c26","plaintext":"qk_live_…","tier":"standard","dailyQuota":20},
#            "mcp":{"endpoint":"https://mcp.qeasy.cloud/api/mcp","protocolVersion":"2025-03-26",
#                   "config":{"mcpServers":{"qeasy-knowledge":{"url":"…","headers":{"Authorization":"Bearer …"}}}}}}}
```

要点：
- **`plaintext` 只出现一次**，拿到就存进密钥管理，不要写进仓库/日志/回答。
- `difficulty` 可能变化（实测 18 位 ≈ 26 万次哈希，0.1–0.3 秒）；算法以 `algorithm` 字段为准。
- 人类走 `/register`，自动获 Key，不需要 PoW。

---

## 3. 三个工具的契约（实测）

### 3.1 `knowledge_domains`
列出可见域与身份。无入参。返回结构化 + 文本，文本形如：

```
691 visible documents / 82 atoms; 6 domains / 2 standards / 0 platform topics.
- data-integration / product（86 篇）: iPaaS data integration platform: operation manuals…
Your identity: standard. Your access: public knowledge only.
```

> 用途：**先确认自己的档位能看到什么**（Standard 只有 public 知识；平台手册/客户案例需授权）。

### 3.2 `knowledge_search`
```jsonc
// in
{"query":"金蝶 客户 基础资料 batchSave 字段映射","limit":3}
// out（structuredContent）
{"hits":[{"docId":"…","title":"金蝶云星空 · 客户 · 写入",
          "excerpt":"[平台] 金蝶云星空 (Kingdee.Cloud) [对象] 客户 (BD_Customer) [方向] 写入…",
          "score":0.896,"scoreBreakdown":{"vector":0.966,"keyword":0.6,"rrf":1},
          "matchedOn":["vector","keyword"],"product":"data-integration","type":"product",
          "citation":"docs/knowledge/objects/kingdee-cloud/BD_Customer.write.md",
          "url":null,"visibility":"public"}],
 "page":{…},"retrieval":{…},"quota":{"remaining":18,"resetAt":"2026-10-28T16:00:00.000Z"}}
```

- `citation` 是**路径字符串**（不是对象），它是 `knowledge_fetch` 的入参。
- 看 `quota.remaining` 控制调用节奏（Standard 20/天）。

### 3.3 `knowledge_fetch`
```jsonc
// in
{"citation":"docs/knowledge/objects/kingdee-cloud/BD_Customer.write.md"}
// out
{"citation":"…","content":"# 金蝶云星空 · 客户 · 写入 …","docId":"…","docMeta":{…},
 "found":true,"granularity":"doc","product":"data-integration","title":"…",
 "type":"product","url":null,"visibility":"public"}
```

---

## 4. 引用纪律（写给人类看的报告必须遵守）

1. **引用到文档级**：给出 `citation` 路径 + 标题；不要只写"知识库说"。
2. **区分来源**：`知识 MCP`（官方文档） / `本 SKILL`（蒸馏） / `实测`（你的调用结果）三者要标清楚。
3. **时效声明**：知识库有 `as_of`；引用超过 30 天的结论要注明日期。
4. **不搬运全文**：`content` 可能很长，回答里只摘与结论相关的 1–3 句。
5. **冲突优先实测**：文档与租户实际不符时，以实际接口资产/配置为准，并在报告里写明差异。

---

## 5. 两个组合模式

### 5.1 设计期 → 落地期
```
knowledge_search("金蝶 销售订单 写入 必填字段")
  → knowledge_fetch(对象卡)            得到字段清单与 parser 要求
  → asset.api.get(租户接口资产)        核对该租户的实际字段
  → strategy.target.update             按实际字段改映射
  → dispatchTarget / job.run           验证
```

### 5.2 报错 → 官方解释 → 修复
```
exception.search / log.search           拿到原始报错
  → knowledge_search("金蝶 组织内编码唯一")  确认是否为幂等命中
  → 若为幂等 → 不改；若为映射问题 → 04-write-recipe.md 对应行
```

---

## 6. 不要做的事

- ❌ 把知识 MCP 当"配置读取"用（它看不到你的租户数据）。
- ❌ 用知识库的字段清单**直接**配方案而不核对 `asset.api.get`（版本/二开差异会导致"字段不存在"）。
- ❌ 把 `plaintext` Key 写进代码、示例、issue 或报告。
- ❌ 在高频循环里调用 `knowledge_search`（20 次/天，先用本 SKILL 的机制篇过滤掉机制类问题）。
