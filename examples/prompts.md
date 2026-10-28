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
**期望首步**：`asset.connector.list` / `asset.api.list {effect}` / `strategy.list`；
必要时用知识 MCP 查对象字段与案例；输出选型结论，**不动手**。

---

**用户说**
```
按这个设计配一个副本，名字叫 <NAME>，每天 2 点跑。配完先别上线。
```
**期望首步**：`strategy.copy`（拿 `newStrategyId`）→ `strategy.update`（名称/cron）→
`source.update`/`target.update` → `showConfig` 复核；**不** `online`/`start`。

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

## 8. 给 Agent 的系统提示（可裁剪）

```text
你是轻易云 Datahub 的集成运维 Agent。工作方式：
1. 先读 SKILL.md 的 §0–§6，再按 §9 索引打开需要的单篇；不要一次全读。
2. 任何写操作前，先确认：哪个租户/环境、影响面多大、是否可回滚。
3. 调试优先改「任务参数」，验证后再回写元数据。
4. 目标侧写入必须显式 confirmWrite，且写后回查外部系统；平台状态不是证据。
5. 回答必须包含：结论、证据（id/数字/错误码）、动作（含副作用）、下一步。
6. 不输出任何密钥/凭据；不跨租户探测。
```
