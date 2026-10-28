# Contributing

Thanks for helping make Datahub integrations easier for agents and humans.

## 贡献什么最有价值

| 类型 | 说明 |
|---|---|
| **新的"症状 → 判据 → 处置"** | 真实排障中出现、现有 `05-diagnostics.md` 未覆盖的 |
| **脱敏的真实会话** | 一次完整调用序列 + 关键返回（放 `examples/`） |
| **平台机制修正** | 与 `references/01-platform-model.md` 冲突的新证据（附来源） |
| **工具契约更新** | 服务端升级后 `tools/manifest.json` 与文档不一致 |
| **反模式** | 你踩过、并且能说清"为什么错/应该怎么做"的坑 |
| **脚本/校验改进** | `dh.py`、`validate_skill.py`、CI |

不要提交：真实密钥、客户数据、内部主机名、未脱敏的 `app_secret`、整段生产日志。

## 开发流程

```bash
git clone https://github.com/qeasy-cloud/datahub-mcp-ops.git
cd datahub-mcp-ops

# 1. 改动后先跑离线校验（不需要网络/密钥）
python scripts/validate_skill.py -v

# 2. 若服务端能力有变化，刷新清单
python scripts/dh.py manifest > tools/manifest.json

# 3. 有测试端点时跑只读冒烟
export DH_MCP_URL=... DH_MCP_KEY=...
python scripts/smoke_test.py --expect-tools 46
```

## 文档规范

1. **一个文件一个主题**：`references/` 讲机制与契约，`playbooks/` 讲步骤，`examples/` 讲实例。
2. **可执行**：每个建议后面给出具体调用；避免"要注意""建议检查"这类无动作表述。
3. **判据优先**：写"怎么判断"而不是"可能是什么"。
4. **标注来源**：机制性结论写来源（如 `domains/04-runtime-chain.md` §2）；实测结论附返回片段。
5. **链接用相对路径**：`references/03-debug-loop.md`，CI 会检查可达性。
6. **命令统一用 `dh.py`**；需要 JSON 时优先 `--param`（跨平台不会踩引号坑）。
7. **不写密钥**：示例用 `<YOUR_KEY>` / `${DH_MCP_KEY}`。

## Commit / PR

- 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)：
  `docs(diagnostics): add 金蝶 empty-response case`、`feat(scripts): dh.py --param`
- 一个 PR 只做一件事；文档改动附"为什么"。
- PR 模板会要求你勾选：已跑 `validate_skill.py`、无密钥泄露、链接可达。
- 通过 DCO（`git commit -s`）表示你有权提交该内容。

## 版本与发布

- SemVer：破坏性文档结构变更 / 工具契约变更 → major；新增章节/剧本 → minor；修正 → patch。
- 发布时更新 `CHANGELOG.md` 与 `SKILL.md` 的 `metadata.version`，CI 会校验两者一致（人工 review）。
- 打 tag `vX.Y.Z` 后由 `.github/workflows/validate.yml` 产出可分发压缩包（见 Release）。

## 行为准则

参与即表示同意 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。
