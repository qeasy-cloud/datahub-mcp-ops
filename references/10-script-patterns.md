# 10 · 事件加工脚本模式（Agent 只输出代码，由人保存）

> **政策（2026-11-11 决策）**
> - SaaS：`script.create` / `script.write` / `script.delete` 从 MCP 可见面移除（保留 `script.list` / `script.get` / `script.validate`）。
> - 私有化：由部署方配置开关放开，**默认关**。
> - `strategy.copy` 复制同租户**既有**脚本 = 平台既有行为，**不算 Agent 新增**，保留。
> - 因此本 SKILL 的脚本职责是：**选对事件 → 输出可校验的代码 → 说明由人保存/部署 → 给出验证步骤**。
>   不替用户 `script.create`，也不声称"已保存"。团队场景的写闸门见 `../docs/team-binding.md`。

---

## 1. 先选事件：14 个里只有 5 个真会触发

> 写在不触发的事件上：代码永远不执行、**界面也不报错**（生产已踩过 30 条）。机制细节 → `01-platform-model.md` §7。

| 事件 | 时机 | 异常语义 | 典型用途 |
|---|---|---|---|
| `AfterSourceInvoke(&$response, $adapter)` | 源接口返回后、写落地数据前 | **向上抛 → 整个作业失败并重试** | 源数据清洗/补字段/统一类型（主力） |
| `AfterSourceResponseSuccess(&$response, $adapter)` | 响应落库后 | 抛出 → 重试 | 落地后补关联数据 |
| `AfterTargetGenerate(&$params, $ids)` | 目标队列插入前，**可改写请求参数** | **空 catch 吞掉，不写日志** | 目标报文补值/结构调整（字段级补值最佳位置） |
| `BeforeTargetInvoke(&$request, $adapter, $job)` | 调用目标前 | 被吞 | 最后一道报文校验 |
| `AfterTargetInvoke(&$response, $adapter, $job)` | 目标响应处理后 | 被吞 | 结果记录/对账（**不能用来撤销**） |

**死事件**（无调用方，别写）：`AfterSourceDispatch`、`BeforeSourceInvoke`、`BeforeSourceJobInsert`、
`AfterSourceResponseFail`、`BeforeTargetDispatch`、`AfterTargetResponseSuccess/Fail` 等。

---

## 2. 三条硬规则

1. `run()` 是唯一约定方法；**没有接口/基类/返回值约定**。类名会被替换成 `SFNS_<md5(strategyId+event)>`，`class AfterSourceInvoke` 只是占位名。
2. **源端只在"这条数据确实不该继续"时 `throw`**，否则会重试到 `max_retries`，队列堆积。
3. **目标端事件异常被静默吞掉**：要阻断必须 `return` / 直接改写 `$params` / 写入前校验；别指望日志告诉你失败。

---

## 3. 五个可复用模式

> 代码为**骨架**：变量名/字段名按实际接口替换；保存前必须 `script.validate` 通过。
> **值翻译优先用静态映射（`mapping.*`）**，脚本只留给真正的规则计算。

### 模式 1 · 源数据补字段（AfterSourceInvoke）

适合：源接口返回里缺一个目标端要的字段，但能从已有字段推导。

```php
<?php
class AfterSourceInvoke
{
    public function run(&$response, $adapter)
    {
        // $response 是源接口返回；按实际结构取行数组
        $rows = $response['data']['list'] ?? $response['data'] ?? [];
        foreach ($rows as &$row) {
            // 例：仓库 id 缺失时按名称映射补齐
            if (empty($row['warehouse_id']) && !empty($row['warehouse_name'])) {
                $row['warehouse_id'] = $this->warehouseIdByName($row['warehouse_name']);
            }
        }
        unset($row);
        $response['data']['list'] = $rows;
        return $response;
    }

    private function warehouseIdByName($name)
    {
        // 建议：改成静态映射或配置表查询，避免硬编码
        $map = ['默认仓' => 'WH001'];
        return $map[$name] ?? '';
    }
}
```

**检查点**：补值失败要不要 `throw`？只有"这条数据继续下去必错"才抛；否则留空让目标端报必填更可控。

### 模式 2 · 明细行重组（AfterSourceInvoke / AfterTargetGenerate）

适合：源明细字段名与目标明细结构不一致，或需要过滤无效行。

```php
<?php
class AfterSourceInvoke
{
    public function run(&$response, $adapter)
    {
        $rows = $response['data']['list'] ?? [];
        foreach ($rows as &$row) {
            $details = [];
            foreach (($row['details'] ?? []) as $line) {
                if (empty($line['sku'])) { continue; }          // 过滤无效行
                $details[] = [
                    'FEntity_FEntryID' => $line['line_id'],
                    'FMaterialNumber'  => $line['sku'],
                    'FQty'             => (float) $line['qty'],
                    'FWarehouseNumber' => $line['warehouse_code'],
                ];
            }
            $row['details'] = $details;                          // 容器名与子字段前缀保持一致
        }
        unset($row);
        $response['data']['list'] = $rows;
        return $response;
    }
}
```

**规则**：容器字段=裸数组名；子字段=`{{数组名.子字段}}`；两处前缀必须一致（不一致 = 明细静默丢失）。

### 模式 3 · 目标报文补值 / 改写（AfterTargetGenerate）

适合：目标端需要源数据没有的常量或系统字段（如组织、来源标记）。

```php
<?php
class AfterTargetGenerate
{
    public function run(&$params, $ids)
    {
        // $params 即将入目标队列的请求体；按实际报文结构改
        if (!isset($params['Model']['FCreateOrgId'])) {
            $params['Model']['FCreateOrgId'] = ['FNumber' => 'ORG001'];
        }
        $params['Model']['FSourceSystem'] = 'QEasy';
        return $params;
    }
}
```

**检查点**：基础资料字段必须是 `{FNumber:…}` 结构；只补"确实缺且能确定"的值，别覆盖业务字段。

### 模式 4 · 值翻译（优先静态映射，不要脚本）

| 场景 | 正确做法 |
|---|---|
| 枚举/编码对照（`1/2/0 → 男/女/未知`） | 静态映射 `mapping.*` + 字段 `mapping.target`，**不写脚本** |
| 复杂规则（区间/多字段组合/外部查表） | 脚本内 `_function` 或本模式；计算逻辑要可单测 |
| 大小写/空格/单位格式的清洗 | 脚本轻量处理，或 parser |

**为什么**：对照表进脚本后业务改一次就要改代码/发布/联调；且脚本异常会被吞，难定位。

### 模式 5 · 写入前校验与失败兜底（BeforeTargetInvoke / AfterTargetInvoke）

适合：防止脏数据写进 ERP、或记录回写结果。

```php
<?php
class BeforeTargetInvoke
{
    public function run(&$request, $adapter, $job)
    {
        $model = $request['Model'] ?? [];
        if (empty($model['FBillNo'])) {
            // 不写脏单：记录后跳过（具体"跳过"写法按平台版本核对，不要依赖抛异常）
            $request['__skip'] = true;
            return $request;
        }
        return $request;
    }
}
```

**注意**：目标端抛异常会被静默吞掉，**不要**用它做"失败撤销"；撤销走反向链路（作废/红冲）。

---

## 4. 输出与交付格式（Agent 必须给的 5 项）

1. **事件选择**：用哪个事件、为什么（对照 §1 的触发点与异常语义）；
2. **代码**：完整 PHP（含 `<?php`），字段名来自实际接口/资产，不猜测；
3. **校验证据**：`script.validate` 的返回（`ok=true`；如失败给行号与修法）；
4. **保存步骤**：由人在平台「事件加工厂」创建/粘贴/启用的步骤（SaaS 不提供 Agent 直写）；
5. **验证计划**：源侧 `dispatchSource` → `queue.job.run` 看数据是否补上；目标侧 `queue.job.get {rawParams:true}` 看报文结构；再回查。

> 复制的既有脚本要单独核对：`strategy.copy` 会复制既有脚本，但 `strategy.create` **不会**；
> 两种路径都要 `script.list` 对照源方案，缺失的按上述 5 项补。

---

## 5. 与工具/文档的关系

| 要做的事 | 工具/文档 |
|---|---|
| 读现有脚本 | `script.list` / `script.get` |
| 语法校验（唯一写前可自动做的检查） | `script.validate`（`php -l`；无副作用） |
| 新增/保存/删除脚本 | ❌ 不由 Agent 做（SaaS 不可见；私有化由部署方开关） |
| 事件机制与死事件 | `01-platform-model.md` §7 |
| 值翻译 | `mapping.*`（`02-tool-catalog.md` §10） |
| 交付证据格式 | `../templates/ops-report.md` |
