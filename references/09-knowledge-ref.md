# 09 · 知识 MCP 与历史在跑方案参考（REF）

> 本篇解决一个具体问题：**"新方案怎么配"的第一手依据从哪来**。
> 默认答案不是接口资产、不是从空白模板，而是**同平台、同对象、正在跑的历史方案**——
> 先找到在跑方案（REF 组卡），取回可复制模板，逐项适配后再落地。
>
> 知识 MCP 是**只读、无租户**的全局知识面；真正读写的仍是租户 Datahub MCP（见 `07-security-and-limits.md`）。
> 团队场景的在线调用入口与写闸门见 [docs/team-binding.md](../docs/team-binding.md)。

---

## 1. 两个 MCP 的分工（先分清，否则后面全是错位）

| | **知识 MCP**（本篇） | **Datahub MCP**（本 SKILL 主对象） |
|---|---|---|
| 端点 | `https://www.qeasy.cloud/api/mcp`（无状态，`GET`/`DELETE` → 405 属正常） | 你的租户实例 `/api/mcp`（有状态，`Mcp-Session-Id`） |
| 密钥 | `qk_…`（Agent 可 PoW 自助注册；Standard 20 次/天） | `sh-…`（租户开放中心签发，按租户隔离） |
| 工具 | **4 个**：`knowledge_domains` / `knowledge_search` / `knowledge_fetch` / `knowledge_reference` | 58 个运维/实施工具 |
| 回答 | 官方知识 + **在跑方案组卡** + 可追溯 `citation` | 现在是什么、改了会怎样、执行结果 |
| 能写吗 | ❌ 永远只读 | ✅（受 scope/信任级别/confirmWrite 约束） |

**结论**：知识 MCP 回答"**应该怎么配、别人怎么配的**"；Datahub MCP 回答"**现在是什么、改了会怎样**"。
两者都不替代写闸门：写操作仍只走租户 MCP（`strategy.*` 等），`confirmWrite`/`--yes --reason` 不能省。

---

## 2. 四个工具：什么时候用哪个

| 工具 | 用途 | 计费 | 关键点 |
|---|---|---|---|
| `knowledge_domains` | 库统计 / 域与平台分面 / 身份 | **免费** | 长流程前先调用，确认可用平台与配额 |
| `knowledge_search` | 语义+关键词检索知识文档（K1/K2/K3） | 计费（缓存 HIT 免费） | 查"机制/字段口径/案例"；data-integration 可用 `scenario`（S1/S2/S3）与 `category`（K1/K2/K3）硬过滤 |
| `knowledge_fetch` | 按 `citation` 取正文 / 取模板 | 计费 | 模板传 `format:"json"` 拿结构化 `source/target/scripts`；大文档用 `maxChars` 分段 |
| **`knowledge_reference`** | **查历史在跑方案组卡（REF）** | 计费（同 search） | **新方案第一步**；返回组卡 + 质量信号 + `templateCitation` |

> **成本纪律**：Standard 20 次/天；`knowledge_reference` 与 `knowledge_search` 同样计费；
> 完整缓存 HIT 不占配额。批量检索先收敛参数，别逐条试。

---

## 3. `knowledge_reference`：参数与语义

所有参数皆可选，但**至少给一个维度**（否则报参数错误）：

| 参数 | 说明 | 示例 |
|---|---|---|
| `sourcePlatform` / `targetPlatform` | 平台过滤，接受**路径 slug / 上游 code / 中文厂商名**（大小写不敏感） | `lingxing` / `LingXing` / `领星`；`kingdee-cloud` / `Kingdee.Cloud` / `金蝶云星空` |
| `interface` | live meta_data 的**接口名**，前缀或精确匹配 | `SAL_OUTSTOCK.read`、`batchSave`（注意：目标侧过滤有坑，见 §6） |
| `object` | 业务对象：`FormId`（如 `SAL_OUTSTOCK`），或 `api:<path>` | `SAL_OUTSTOCK`；`api:/open/api/...` |
| `field` | 配置字段名（如 `FBillTypeID`） | `FBillTypeID` |
| `query` | 策略名/接口/字段的关键词（1–500 字） | `发货结算报告 销售出库` |
| `sortBy` | `evidence`（默认，按证据等级与在跑量）/ `finished` / `recent` | 有 query 时按相关度排，`sortBy` 只做同分裁决 |
| `limit` | 1–20，默认 8 | 先 `limit:5` 看质量，再决定要不要更多 |
| `cursor` | 上次返回的 `nextCursor` 分页 | 翻页用，不要重复同一检索式 |
| `minScore` | 只抬不降的服务端相关度下限 | 噪音多时抬高 |

**返回里最重要的两个字段**：

- `object` + `objectType`：`objectType="api"` 时表示该平台对没有 FormId（对象以 `api:<path>` 表达）；
- `quality`：组卡质量信号（见 §4）——**选卡的主要依据**，不是"第一条就是最好"。

---

## 4. 组卡质量信号：怎么选卡

| 字段 | 含义 | 怎么用 |
|---|---|---|
| `finished` | 组内方案累计成功条数 | 越高越可信（万级以上为厚样本） |
| `errorRate` | 组内错误率 | 越低越好；>5% 要警惕 |
| `active` | 组内最近一次 `lastSync` 是否 ≤7 天 | 优先 `active=true`（在跑、仍在维护） |
| `lastSyncDays` | 距最近一次同步天数 | 越小越新；半年未同步的别当模板 |
| `score` | 抽样策略的原始评分（0 = 平台未评分） | 仅参考，不单独作为选型依据 |
| `runningCount` | 组内在跑方案数 | 越多说明这对平台/对象是成熟组合 |
| `evidenceGrade` | 证据等级（摘要里表现为 A/B 档） | A 档优先；B 档次之 |
| `topStrategies` | 组内代表方案名 | **点开看名字是否同业务语义**（同对象 ≠ 同业务口径） |
| `templateCitation` | 取模板的凭证 | **必须记录**（既是落地依据，也是留痕证据） |

**选卡顺序**：`active=true` → `errorRate` 低 → `finished` 多 → `evidenceGrade` 高 → `topStrategies` 与你的业务语义一致。
一次抽 **2–3 张**比对，不要只看第一张。

> 实测注意：**Markdown 摘要**只展示档位/在跑条数/finished/errorRate 等少量字段；
> `active / lastSyncDays / objectType` 等完整字段在结构化返回里（客户端 `structuredContent`）。
> 数据集成团队另有只读 CLI（团队仓库 `knowledge.py`，不在本包内）；通用做法是用任意 MCP 客户端读结构化数据。
> 选卡时优先读结构化数据。

---

## 5. 从组卡到可复制模板：`templateCitation` → `knowledge_fetch`

```jsonc
// ① 找组卡（MCP 工具调用；用你的 MCP 客户端，结构化返回便于读质量信号）
knowledge_reference {"sourcePlatform":"领星","targetPlatform":"金蝶云星空",
                     "object":"SAL_OUTSTOCK","sortBy":"evidence","limit":8}

// ② 取模板（大模板先落盘/分段，不整段读入上下文；maxChars 可分段）
knowledge_fetch {"citation":"docs/knowledge/templates/lingxing-to-kingdee-cloud/SAL_OUTSTOCK.md",
                 "format":"json"}
```

> 数据集成团队环境中有只读 CLI 可等价执行（`knowledge.py ref|fetch`，团队仓库提供，不在本包内）；
> 其它环境用任意 MCP 客户端即可。

`knowledge_fetch(templateCitation)` 两种形态：

- 默认 **markdown**：清洗后的模板文档，含「§1 说明 / §2 直抄(S)–核对(V)清单 / §3–§4 源+目标两份 `meta_data` JSON / §5 脚本」；
- `format:"json"`：返回结构化 `template={source,target,scripts[]}`；`scripts:[]` 表示该模板无脚本（`scriptsNote` 说明）；
  解析问题进 `parseWarnings`（不是错误，**仍要逐字段核对**）。

**模板不是契约**：它是"某条在跑方案的配置快照（脱敏）"，字段事实源仍是
**租户实际接口资产**（`asset.api.get` / `asset.api.list`，只解析 id 与字段事实）。
模板里有、本地资产没有的字段 → 登记为**字段缺口**，不得硬套。

---

## 6. 实测坑（2026-11-11，四平台/多对象回归）

> 以下为真实回归结论，Agent 踩到后不要"换关键词再试十次"，按"处置"走。

| # | 坑 | 现象 | 处置 |
|---|---|---|---|
| 1 | **目标侧 `interface` 过滤失效** | `targetPlatform=金蝶云星空` + `interface=batchSave` → **0 命中**（过滤只匹配源侧 api） | 去掉 `interface`，改用 `object`（FormId）/`query`；确认后在留痕里写"目标侧 interface 不可用" |
| 2 | **上游 code 不归一** | `sourcePlatform=Kingdee.YXC` → 0 命中 | 用 slug（`kingdee-cloud`）或中文名（`金蝶云星空`）；平台过滤值先用 `knowledge_domains` 查 |
| 3 | **`sortBy` 排序不可靠** | `recent` 与 `finished` 返回同序（线上实现待修） | 不要依赖排序做选型；拿到 `limit:8` 后按 §4 质量信号自己排 |
| 4 | **`gaps` 契约未实现** | 0 命中时没有"哪里没有"的结构化说明 | 0 命中 ≠ 平台无覆盖；按 §7 降级并把「检索式 + 0 refs」写进证据 |
| 5 | **不传 `product` 会混语料** | `knowledge_search` 结果混入 reconciliation 文档 | data-integration 场景显式传 `product:"data-integration"` |
| 6 | **中文名能归一，但 FormId 更准** | `object=销售出库单` 可命中（✅），但同义词/别名会放大噪音 | 优先 `object=FormId`；中文名只作兜底 |
| 7 | **同对象存在 `api:` 型重复组** | 同一业务接口按 `/path` 与 `path` 两种写法各成一组 | 看 `objectType` 选 `formId` 组；`api:` 组需人工判断是否同一接口 |
| 8 | **摘要字段被省略** | MCP 文本摘要不展示 `active/lastSyncDays/objectType` | 读结构化返回/CLI `--json`，别以文本摘要为唯一依据 |

---

## 7. 空结果与权限：0 候选不是失败

`knowledge_reference` 返回空，先分三类：

| 情形 | 表现 | 含义 | 处置 |
|---|---|---|---|
| A. 维度未被覆盖 | `refs: []`、`candidateCount=0`、无 `accessHint` | 该平台对/对象没有在跑方案组卡（语料覆盖缺口） | 按下方降级阶梯；**记录检索式**，禁止编造案例 |
| B. Standard Key 不可见 | `refs: []` + `accessHint` | REF 组卡全部 restricted，Standard 档看不到（同 `-32403` 语义） | **不是 Key 失效**：申请 Authorized，或直接走租户内降级 |
| C. 参数/协议问题 | `-32602` / `-32029` / `429` / `401` | 参数非法 / 日配额 / 频控 / 鉴权 | 按错误码处置：收敛参数、等配额重置、换本机 Key |

**降级阶梯（逐层、每层留痕）**：

1. 换标识符：`object`/`interface`/`field` 用精确值再查一次（平台名换 slug/上游 code/中文名）；
2. 放宽维度：去掉 `field`，只留 `object + targetPlatform`，或只给 `query`；
3. 租户内样板：Datahub MCP `strategy.list` 找**同平台同对象在跑方案**（这是"你自己的样板"，优先级高于资产默认快照）；
4. 资产默认快照：`asset.api.get` 取字段事实 / `strategy.create` 套默认 `meta_data`（**最后手段**，需在 S3 核对并写回）；
5. 如实记录「已检索 + 0 refs + 降级路径」，标 `待确认`；**禁止编造案例或历史方案**。

---

## 8. REF 与自己租户的样板：别混

| | REF（知识 MCP） | 租户内样板（Datahub MCP） |
|---|---|---|
| 范围 | 全局、跨租户、只读、无租户 | 你自己的租户 |
| 取得 | `knowledge_reference` → `templateCitation` | `strategy.list` → `strategy.get {sections:"all"}` |
| 可信度 | 有质量信号（finished/errorRate/active），但可能已旧 | 就是你在跑的配置，最贴近当前环境 |
| 用法 | **首选参考**（尤其新平台/新对象） | REF 空或 REF 与本地差异大时的**对照**；可直接 `strategy.copy` |
| 风险 | 跨环境/版本差异；模板脱敏 | 可能是别人建的/已停用的方案 |

**落地顺序**：REF 组卡（怎么配）→ 租户样板（本地实际怎么配）→ `copy`/`patch` 落地 → 字段契约与 lint → 联调回查。
模板与样板都只是输入，**写操作仍只走租户 MCP 与写闸门**。

---

## 9. 引用与留痕纪律

1. **引用**：用返回的 `citation`（如 `docs/knowledge/reference/<source>-to-<target>/<OBJECT>.md`）；
   `knowledge_fetch` 的返回也带 `citation`，取模板时记下。
2. **留痕**：采用参考方案时必须记录 `templateCitation` + 质量信号 + 检索式（含 0 结果）+ 适配差异清单（≥E2）。
3. **脱敏**：REF/模板全部按 restricted 对待；客户版材料只写结论与数量，不出现平台元数据、方案 ID、客户真名。
4. **不整段搬**：模板原文不复制进知识库/对话；只带差异字段与关键数字。
5. **不编造**：空结果就是空结果；"参考了同类项目"没有 `templateCitation` 等于没参考。

---

## 10. 版本与能力基线

| 能力 | 可用性（2026-11-11） |
|---|---|
| `knowledge_reference`（REF 组卡） | ✅ 已上线（2026-11-06 起，2026-11-07 回归） |
| `knowledge_fetch` 模板 `format:"json"` | ✅ 已上线（返回 `template={source,target,scripts[]}`，含 `scriptsNote/parseWarnings`） |
| `objectType`（`api:` 型对象） | ✅ 已上线 |
| `quality.lastSyncDays` | ✅ 已上线 |
| `gaps`（"哪里没有"结构化说明） | ❌ 未实现（用检索式 + 0 refs 留痕替代） |
| 目标侧 `interface` 过滤 | ⚠️ 失效（见 §6-1） |

> 官网能力升级后：用 `knowledge_domains`（免费）确认可见面，用 `knowledge.py tools` 对照本地 CLI 支持的工具。
> 能力版本与服务端 `x-capability-version` 的兼容说明见 [docs/clients.md](../docs/clients.md) §4。

---

## 11. 一页速查

```
新方案/新对象 → knowledge_reference(object=FormId + 平台对, limit=5~8)
             → 读 quality（active/errorRate/finished/evidenceGrade/runningCount）
             → 抽 2–3 张比 topStrategies 业务语义
             → knowledge_fetch(templateCitation)（大模板 --save）
             → 适配 9 项（平台对/对象/接口 effect/适配器借壳/分页增量/字段契约/脱敏/脚本 review/差异留痕）
             → copy 优先 / create + patch → lint → 联调 → 写目标端（confirmWrite）→ 外系统回查

0 结果 → 换标识符 → 放宽维度 → 租户内 strategy.list 同对象在跑方案 → 资产默认快照
       → 记录「检索式 + 0 refs + 降级路径」，禁止编造
```
