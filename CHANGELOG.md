# Changelog

All notable changes to this skill package are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-11-11

Reference-first（REF：抄在跑方案）成为一等能力；修改优先（copy + patch）；执行绑定与 13 条用户反馈条款落地；
脚本政策改为"只输出代码"；字段契约/中文字段/明细行/时间参数四类检查点进入主流程。

### Added

- **`references/09-knowledge-ref.md`**：知识 MCP 4 工具、`knowledge_reference` 参数与组卡质量信号
  （`finished/errorRate/active/lastSyncDays/score/runningCount/evidenceGrade/objectType/topStrategies/templateCitation`）、
  `knowledge_fetch`（`format:"json"`/`maxChars`）、模板适配 9 项、空结果降级阶梯、**2026-11-11 实测坑**
  （目标侧 `interface` 过滤失效、上游 code 不归一、`sortBy` 不可靠、`gaps` 未实现、摘要字段省略等）。
- **`references/10-script-patterns.md`**：事件加工厂 5 个可复用模式（补字段/明细重组/报文补值/值翻译/写入前校验）
  + 事件选择表 + "Agent 只输出代码"交付格式。
- **`docs/team-binding.md`**：团队执行绑定——`dh.py` → `qeasy_mcp.py` 命令替换表、项目上下文、写前四要素、
  禁止 `DH_MCP_*` 直连。
- **`SKILL.md` 新章节**：§3「REF 优先 + 修改优先」（REF 四步、`copy`→`patch`、create 最后手段）、
  四类落地检查点（create 覆盖/脚本丢失、字段契约、明细行、中文字段/时间参数）、
  脚本与资产政策、团队执行绑定、§9.1「13 条用户反馈对应条款」自检表。
- **`docs/release-notes/v2.2.0.md`**；README/README.zh-CN 新增 REF/修改优先特性与 team-binding 说明。

### Changed

- `SKILL.md` frontmatter：单行 description（避免块标量在各宿主解析差异）；`version` → 2.2.0；
  `capability_version` → `2026-11-11`；新增 `knowledge_mcp_tools: 4`。
- 知识 MCP：3 → **4 工具**（补 `knowledge_reference`）；端点以 `https://www.qeasy.cloud/api/mcp` 为准
  （`mcp.qeasy.cloud` 为备用入口）。
- `playbooks/p3-new-integration.md`：阶段 0 先 REF 再租户内样板再资产；阶段 2 改为 copy/patch 优先，
  增加「create 覆盖 meta_data」「create 不复制脚本」「字段检查点」。
- `playbooks/p2`、`playbooks/p4`：脚本相关内容改为"只读核对 + 只输出代码，由人保存"。
- `references/01`：新增 §5.3.1「请求时间参数最小集」；§7 脚本政策改为只输出代码；§13 增 REF 入口。
- `references/02`：`strategy.create` 增覆盖/脚本警告；新增 `strategy.patch` 行与兼容说明；速查表增 REF/patch。
- `references/04`：五步配方改为 REF → copy/patch 优先；§2.1 规则 3 → 6 条（明细容器裸名/子字段前缀/中文 label/时间参数）；
  §8 自检清单同步。
- `references/06`：4 工具契约 + `knowledge_reference` 节 + REF 优先组合模式 + 0 候选纪律。
- `references/08`：新增 F1–F5 反模式（不查 REF 直接配 / create 代替修改 / Agent 保存脚本 / 资产当配置起点 / 时间参数全放）。
- `docs/faq.md`、`examples/prompts.md`、`examples/session-source-debug.md`：增 REF 示例与空结果处理；
  新增 patch 兼容、团队绑定、脚本政策 FAQ。
- `docs/clients.md` 兼容矩阵、`docs/releasing.md` 发布模板、`templates/README.md` 工具数表述同步到 58。

### Fixed

- 文档里"知识 MCP 3 个工具"的过时表述（现为 4 个）。
- 发布模板中的 "46 tools" / "10 checks" / "8 checks (46 tools)" 过时数字。
- `strategy.create` 文档未提示"传入 meta_data 也可能被资产默认快照覆盖"的问题。

### Notes

- `strategy.patch` 于服务端 capability **≥ `2026-11-11`** 可用；旧服务端用 `update`/`source.update`/`target.update`
  等价改写（见 `references/02` §5 兼容矩阵）。
- `tools/manifest.json` 是服务端生成物：**本版未手编工具列表**；待服务端部署 `2026-11-11` 后由
  `python scripts/dh.py manifest` 重新生成。
- 脚本写入能力在 SaaS 可见面移除（保留 `list/get/validate`）；私有化由部署方开关放开（默认关）。

### Verification

- `python scripts/validate_skill.py -v` — 11 checks passed
- `grep -rn "knowledge_reference"` — > 0（SKILL/refs/playbooks/examples/docs 均命中）
- `python scripts/smoke_test.py` — 在线只读冒烟（本机未持租户 Key，未运行；CI/使用者环境补跑）

## [2.1.0] - 2026-10-28

Static value mapping（静态映射，资源中心 → 静态映射资源）成为一等能力：
服务端新增 12 个 `mapping.*` 工具（39 → 46 → **58**），SKILL 补齐机制、工具、诊断与反模式。

### Added

- **12 个新工具**（scope：`mapping:read` / `mapping:write`，只读档位含 `mapping:read`）
  - 分类：`mapping.category.list/get/create/update/delete`
  - 对照：`mapping.relation.list/create/update/delete/import`（批量 upsert，≤500 行，支持 `dryRun`）
  - 判据：`mapping.resolve`（与运行时同一语义试算）、`mapping.usage`（反查引用 + 孤儿引用）
- **`mapping.category.get`**：一次给出样本、是否有 `*` 兜底、被哪些方案字段引用、可复制的挂载片段。
- **`mapping.usage`**：扫描全部方案 `meta_data`，输出方案/方向/字段/方向，并检测"引用了已删分类"的孤儿引用。
- **`strategy.queue.job.get {rawParams:true}`**：返回不折叠的 `params`——排查字段映射时能看到最终报文（默认仍折叠）。
- 文档：`references/01` §3.7（机制与**生效位置不对称**）、`references/02` §10（12 工具 + 典型串联）、
  `references/05` §2.1（"映射配了没生效"六步判据）、`references/08` C7/C8、`SKILL.md` §4.1。

### Fixed

- `mapping.relation.delete` 误把分类集合当关系集合查询（`list($relations) = collections()` 取错返回值）。
- `mapping.*` 的值参数只接受 string，Agent 传 `1`/`100` 会被入参校验拒绝；现接受数字/布尔并统一转字符串。
- 删除分类仍被方案引用时，现在**在发确认令牌之前**直接拒绝（`mapping_category_in_use`），不再让人先拿令牌再被拒。

### Verification

- `qa-mapping.php`：**38 条断言全绿**，含端到端运行时证明——
  目标端 `FName` 配 `MAPTEST → 映射后名称` 后 `dispatchTarget`，`queue.job.get {rawParams:true}`
  的报文里 `FName = 映射后名称`，且不再出现常量 `MAPTEST`。
- PHPUnit `--filter Mcp`：265 passed / 9 skipped（tool 计数与 scope 预设同步到 58 / 11）。

## [2.0.0] - 2026-10-28

Major rewrite against **`datahub-mcp 0.1.0` / `x-capability-version 2026-10-28` (46 tools)**.
The v1.x line documented 39 tools and had no daemon-free debug loop.

### Added

- **`references/01-platform-model.md`** — 平台机制蒸馏（元数据三层模型、取值/parser、
  运行时链与存储、分页/增量、幂等、事件脚本、元数据复用）。来源为平台知识库
  `domains/01,02,03,04,06,08,09,10,11,12`，用于**减少对知识 MCP 的请求压力**。
- **7 个新工具的完整文档**：`strategy.queue.job.get` / `.run` / `.update`、
  `strategy.log.search`、`script.validate`、`asset.connector.list` / `.get`。
- **`references/03-debug-loop.md`** — 无守护进程的六步调试闭环（源侧 + 目标侧 + 判读表）。
- **`references/06-knowledge-mcp.md`** — 公开知识 MCP 的实测契约：无状态端点、
  PoW 注册（`challengeId:nonce`、difficulty、nonce 必须为字符串）、3 个工具、
  `citation` 为路径字符串、引用纪律。
- **`references/08-anti-patterns.md`** — 18 条反模式（调试/配置/运维/安全/表达）。
- **`playbooks/`** — 4 个可执行剧本：源侧调试、目标端写入、从需求到上线、批量运维与收尾。
- **`examples/session-source-debug.md`** — 一次真实会话（含真实返回片段与判读）。
- **`tools/manifest.json` + `manifest.schema.json`** — 由服务端代码生成的机器可读清单；
  CI 校验"文档提到的工具都真实存在"。
- **`scripts/validate_skill.py`** — 离线校验：必需文件、frontmatter、清单一致性、
  链接可达、密钥泄露。
- **`scripts/dh.py`** — 重写为零依赖 CLI：`doctor`/`tools`/`call`/`manifest`/`raw`，
  支持 SSE、`Mcp-Session-Id`、429 退避、`--param`（绕开 Windows 引号问题）、
  UTF-8 输出兜底。
- **`scripts/smoke_test.py`** — 在线只读冒烟（握手/工具/身份/读调用）。
- 开源项目配套：`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`、`CITATION.cff`、
  `.github/`（CI + issue/PR 模板）、`docs/clients.md`、`docs/faq.md`。

### Changed

- **`strategy.get`** 默认 `sections=basic`（约 1.6KB），完整 `meta_data` 需显式传
  `sections=source|target|all`（单条约 40KB）。文档与示例同步调整。
- **`strategy.dispatchSource/Target`** 在方案停止态**放行**（返回 `mode=debug` + `jobId`），
  旧语义用 `requireRunning=true`。调试剧本据此重写。
- **破坏性操作**：`precheck` 对所有信任级别返回；影响面 >1000 行时即使 `full` 也强制
  `confirmationToken`；携带令牌一律校验核销（重放被拒）。
- **调试日志**：`00/01/02_debug_*` 由 `FATAL` 改为 `LogStatus::DEBUG`；
  `dbInfo` 拆出 `log.debug`，并新增 `last_run`。
- **`script.create`** 返回 `file_written` / `syntax_ok`（落库前 `php -l`），
  `compiled` 语义降级为"文件已写"。
- 文风统一为"症状 → 判据 → 处置"，命令示例统一用 `dh.py`。

### Removed

- v1.x 的 12 篇重叠参考（`01-mental-model` … `12-knowledge-base`）被合并/重写为 8 篇。
- 旧的 Python 客户端（`dh_mcp.py`，27KB）由 `scripts/dh.py` 取代。
- 旧的 `quickstart` 示例由 `playbooks/p1-debug-source.md` 与 `examples/prompts.md` 取代。

### Fixed

- 文档里"`strategy.get` 总是返回完整元数据"的过时描述。
- Windows 下内联 JSON 被 shell 吞引号、控制台中文乱码两类可用性问题。
- Dependabot 会提出**不存在的** action 大版本（`checkout@v7` / `setup-python@v7` /
  `upload-artifact@v7`，实际为 v4/v5/v4）。现已在 `.github/dependabot.yml` 中忽略
  `semver-major`，并提供 `scripts/configure_github.py` 一键关闭这类 PR。

### Tooling

- `.github/workflows/release.yml`：打 tag 即用仓库自带的 `GITHUB_TOKEN` 发布 Release 并附 zip
  （无需 PAT），说明来自 `docs/release-notes/<tag>.md`。
- `scripts/configure_github.py`：可见性/About/topics/features/漏洞上报/labels/分支保护/
  关闭无效 PR/发布 Release，一条命令、幂等、支持 `--dry-run`。

## [1.2.0] - 2026-10-26

### Added

- 扩展能力文档：资产目录、生命周期、数据导入、脚本、审计。
- `07-portability.md`（跨部署迁移）、`12-knowledge-base.md`（知识库预留）。

### Changed

- 对齐 39 工具（25 核心 + 14 扩展）。

## [1.0.0] - 2026-10-25

### Added

- 首个可分发版本：心智模型、工具参考、安全与运维、Playbook、诊断、字段映射、
  运行生命周期、策略元数据、事件脚本、Python 客户端、模板。
