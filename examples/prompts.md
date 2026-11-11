# 可直接复制的提示词

> 用法：把"用户说"整段粘给你的 Agent；"期望首步"是它应该先做什么（用来检查它是否真的读了本 SKILL）。
> 变量用 `<SID>` / `<TID>` / `<jobId>` 表示，替换成真实值。

---

## 1. 上手 / 侦察

**用户说**
```
我是第一次接触这个 Datahub 租户。先告诉我：我这把密钥能干什么、这个租户有哪些方案、
哪些方案最近在报错。不要改任何东西。
```
**期望首步**：`meta.whoami` → `meta.capabilities` → `strategy.list` → 对报错方案 `strategy.dbInfo`。

---

**用户说**
```
帮我体检一下这个方案 <SID>，用一句话告诉我它现在健不健康，然后给证据。
```
**期望首步**：`strategy.dbInfo`（一次调用看日志/数据/队列/last_run）；必要时再 `log.search`。

---

## 2. 调试源侧

**用户说**
```
测试环境没有守护进程。帮我把 <SID> 的源侧跑通：手工触发一次、执行掉、告诉我取到几条。
如果没取到，先改任务参数再试，别改元数据。
```
**期望首步**：`dispatchSource` → `queue.list` → `queue.job.get` → `queue.job.run`；
`has_data=false` 时 `queue.job.update`（放宽 `FilterString`）→ `run {force:true}`。

---

**用户说**
```
<jobId> 这次到底发给源系统什么、返回了什么？我要看原始报文。
```
**期望首步**：`log.search {level:"debug", jobId, includeContent:true}`，读 `content.request`/`content.response`。

---

## 3. 目标端写入

**用户说**
```
数据已经取到了，帮我推到金蝶。先别写，把要发出去的报文给我看。
```
**期望首步**：`dispatchTarget` → `queue.job.get {direction:"target"}` → **停下来**展示 `params.Model`，
明确说"未写入"。**不应**直接 `run`。

---

**用户说**
```
报文没问题，可以写测试账套。写完帮我确认单号 <NO> 在不在，以及有没有重复。
```
**期望首步**：`queue.job.run {direction:"target", confirmWrite:true}` → 回查（`data.search` / 外部查询）
→ `run {force:true}` 验证幂等变 `repeat`。

---

**用户说**
```
金蝶报"格式错误，不能转换为字典类型"，怎么改？
```
**期望首步**：定位是哪个字段（`queue.job.get` 看 `params.Model`），判断是否基础资料缺
`ConvertObjectParser`；给出 `target.update` 的 `patch` 方案，并说明如何验证。

---

## 4. 排障

**用户说**
```
这个方案昨天还好，今天数据不增了。帮我定位到具体哪一段断了。
```
**期望首步**：`strategy.dbInfo`（看 `last_run`/队列/错误）→ 按 `05-diagnostics.md` §1 分支取证；
先判断"有没有消费者/是否被前置条件卡住/是否过滤条件变了"。

---

**用户说**
```
dbInfo 说 fatal=3，但 exception.search 一条都没有，是不是系统坏了？
```
**期望首步**：检查日志文本是否 `0x_debug_` 开头（老版本把调试留痕写成 FATAL）；
给出"这不是错误"的判据，并用 `log.search {level:"debug"}` 展示真实内容。

---

## 5. 新建方案

**用户说**
```
客户要把金蝶的客户资料同步到 CRM。先别配，给我一页可行性：用哪个接口、增量怎么取、
幂等键用什么、有没有可复制的现成方案。
```
**期望首步**：**先 REF**——`knowledge_reference`（`object=BD_Customer` 或平台对 + `query`）
找同平台/同对象在跑方案组卡 → 读 `quality` 选卡并记 `templateCitation`；
再 `strategy.list` 看本租户样板；最后才用 `asset.*` 解析接口 id 与字段事实。
输出选型结论（含参考方案证据或「检索式 + 0 refs + 降级路径」），**不动手**。

---

**用户说**
```
按这个设计配一个副本，名字叫 <NAME>，每天 2 点跑。配完先别上线。
```
**期望首步**：`strategy.copy`（拿 `newStrategyId`）→ `strategy.update`（名称/cron）→
`source.update`/`target.update`（或 capability ≥ 2026-11-11 时 `strategy.patch`）→ `showConfig` 复核；
`create` 后必须核对字段/脚本；**不** `online`/`start`。

**用户说**
```
这个方案已经跑了一阵，把目标端 FName 改成中文名映射，别新建方案。
```
**期望首步**：`strategy.showConfig {direction:"target"}` 读现状 → `strategy.patch`（≥2026-11-11）或
`target.update {patch}` 只改该字段 → `showConfig` 复核 → lint/联调；**不得**用 `strategy.create` 代替修改。

---

## 6. 收尾

**用户说**
```
调试完了，把测试数据清掉，方案下线但保留。清理前先告诉我影响面。
```
**期望首步**：`stop` → `data.clean {dryRun:true}` + `queue.clean {dryRun:true}` 展示影响面 →
（确认后）带令牌执行 → `offline` → `dbInfo` 复核归零。

---

## 7. 审计

**用户说**
```
谁在什么时候改了 <SID> 的目标端映射？改了什么？
```
**期望首步**：`audit.search {tool:"strategy.target.update", payload:"full"}`，
展示 `patch` 的 `字段 → 值` 与操作者/时间。

---

## 8. 抄在跑方案（REF）

**用户说**
```
这个对象我们以前肯定做过，你先找几条在跑的方案参考一下再配，别从接口资产开始。
```
**期望首步**：`knowledge_reference`（平台对 + `object`/`interface`/`query`）→ 按 `quality` 选 2–3 张 →
`knowledge_fetch(templateCitation)`；把「检索式 + 组卡数 + 质量信号 + 差异清单」作为结论证据。

---

**用户说**
```
REF 一条都没搜到，是不是就没有？接下来怎么办？
```
**期望首步**：先分三类原因（覆盖缺口 / Standard 看不到 restricted 组卡 `accessHint` / 参数协议错误），
再按降级阶梯：换标识符 → 放宽维度 → 租户内 `strategy.list` 同对象在跑方案 → 资产默认快照；
如实记录「检索式 + 0 refs + 降级路径」，**不编造案例**。详见 `../references/09-knowledge-ref.md` §7。

---

**用户说**
```
把模板里的配置直接给我粘过来用。
```
**期望首步**：模板是"可运行配置快照"不是契约——`knowledge_fetch` 取回后逐项适配 9 项
（平台对/对象/接口 `effect`/适配器借壳 R013/分页增量/字段契约/脱敏/脚本 review/差异留痕），
字段以租户 `asset.api.get` 为准；给出差异清单，**不整段粘贴**。

---

## 9. 给 Agent 的系统提示（可裁剪）

```text
你是轻易云 Datahub 的集成运维 Agent。工作方式：
1. 先读 SKILL.md 的 §0–§7，再按 §11 索引打开需要的单篇；不要一次全读。
2. 新建/修改方案：先 REF（knowledge_reference → knowledge_fetch 模板）→ 适配 →
   copy/patch 落地；create 是最后手段。不要从接口资产开始配。
3. 任何写操作前，先确认：哪个租户/环境、影响面多大、是否可回滚；
   团队场景在线调用只走 qeasy_mcp.py（--project + --yes --reason），禁止 DH_MCP_* 直连。
4. 调试优先改「任务参数」，验证后再回写元数据。
5. 目标侧写入必须显式 confirmWrite，且写后回查外部系统；平台状态不是证据。
6. 脚本只输出代码（事件选择 + script.validate 证据 + 保存步骤），不替人保存/部署。
7. 回答必须包含：结论、证据（id/数字/错误码/REF citation）、动作（含副作用）、下一步。
8. 不输出任何密钥/凭据；不跨租户探测。
```
