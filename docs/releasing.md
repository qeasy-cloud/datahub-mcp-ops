# Releasing & repository metadata

Maintainer notes. Everything GitHub asks for when publishing this repository lives here so it can be
reviewed in a PR instead of disappearing into a web form.

---

## 1. Repository identity

**Name**: `datahub-mcp-ops`
**Remote**: `git@github.com:qeasy-cloud/datahub-mcp-ops.git`
**Website**: `https://www.qeasy.cloud`
**Visibility**: public · **License**: MIT

### Description (GitHub "About", ≤350 chars)

> An executable playbook that teaches AI agents to operate Datahub (轻易云) through its MCP endpoint: daemon-free job debugging, field-mapping repair for Kingdee, static value mapping, write verification, diagnostics and safe cleanup. Zero-dependency CLI, docs-as-tests CI.

Length: 265 characters.

Alternative, shorter (135 chars):

> Teach AI agents to operate Datahub (轻易云) over MCP: debug jobs without a daemon, fix mappings, verify writes.

### Topics (max 20, lowercase, hyphenated)

```
mcp  model-context-protocol  ai-agents  agent-skills  datahub  qeasy  ipaas
integration-platform  kingdee  erp-integration  runbook  diagnostics  llm-tools
observability  automation  python  devops  api-integration
```

Pick 16–18; keep `mcp`, `ai-agents`, `agent-skills`, `datahub`, `ipaas`, `kingdee` first — those are the
high-intent searches.

### Social preview

- Image: `docs/assets/banner.svg` → export to **1280×640 PNG** (GitHub requires raster).
- Text on the image: title, one-line promise, the repo path, `qeasy.cloud`.
- Settings → General → Social preview → upload.

### Recommended repository settings

| Setting | Value | Why |
|---|---|---|
| Issues | on, with templates | bug reports are the main feedback channel |
| Discussions | on (Q&A + Show and tell) | keeps issues for defects |
| Wiki | off | docs live in the repo and are CI-checked |
| Projects | off (until needed) | roadmap lives in README |
| Allow merge commits | off | squash-only history reads better |
| Branch protection on `main` | require PR + `validate` check | docs-as-tests only works if enforced |
| Dependabot | on (`.github/dependabot.yml`) | keeps Actions pinned versions fresh |
| Private vulnerability reporting | on | matches `SECURITY.md` |

---

## 2. Labels

| Label | Color | Use |
|---|---|---|
| `bug` | `#d73a4a` | documentation or script is wrong |
| `enhancement` | `#a2eeef` | new diagnostic / playbook / example |
| `tool-contract` | `#5319e7` | tool schema or manifest changed |
| `docs` | `#0075ca` | prose only |
| `good first issue` | `#7057ff` | single file, clear scope |
| `needs-tenant` | `#fbca04` | requires a live tenant to verify |
| `security` | `#b60205` | never used publicly; see SECURITY.md |

---

## 3. Release procedure

```bash
# 1. version + changelog
#    SKILL.md: metadata.version
#    CHANGELOG.md: new section (Keep a Changelog)
#    CITATION.cff: version + date-released

# 2. refresh generated artefacts
python scripts/dh.py manifest > tools/manifest.json

# 3. gates
python scripts/validate_skill.py -v                 # 11 checks（结构/链接/工具名/密钥）
python scripts/sync_capability.py --check -v        # 能力面：frontmatter/知识 MCP 4 工具/manifest/13 条反馈
python -m compileall -q scripts
python scripts/smoke_test.py --expect-tools 58      # needs a tenant; read-only

# 4. rebuild the distributable (optional, CI does it on tag)
#    Windows: robocopy the skill directory, then Compress-Archive (see the repo install notes)

# 5. publish
git add -A && git commit -m "chore(release): v2.0.0"
git tag -a v2.0.0 -m "v2.0.0"
git push origin main --tags
```

### 发布前能力面校验（Capability surface check）

`scripts/sync_capability.py` 是**离线**一致性门禁（纯 stdlib，CI 与实际发布共用），检查 5 组规则：

| 组 | 规则 |
|---|---|
| a | `SKILL.md` frontmatter：`metadata.version`、`metadata.capability_version`、`metadata.knowledge_mcp_tools` 存在且格式正确 |
| b | `references/09-knowledge-ref.md` 存在且含 `knowledge_reference`；`SKILL.md` 的知识 MCP 工具面恰为 4 个 |
| c | `tools/manifest.json` 的 `capability_version` / `tool_count` 与 `SKILL.md` 兼容矩阵一致；manifest 落后于 SKILL 目标版本时按模式处理 |
| d | `SKILL.md` 不得残留「3 个工具」或缺少 `knowledge_reference` 的知识工具三元组 |
| e | 13 条用户反馈条款在 `§9.1` 可定位（编号 + 关键词 13/13） |

```bash
# 发布/CI 正常态（manifest 已按服务端最新能力重新生成）
python scripts/sync_capability.py --check -v

# 窗口期（服务端尚未发布 SKILL 目标能力，manifest 允许暂时落后）
python scripts/sync_capability.py --check --allow-stale-manifest -v
```

**退出码**：`0` = 无 FAIL（可有 WARN）；`1` = 至少一条 FAIL；`2` = 参数/环境错误。

**何时必须去掉 `--allow-stale-manifest`**：服务端发布 `SKILL.md` 声明的 `metadata.capability_version`
（当前为 `2026-11-11`，含 `strategy.patch`），并用 `python scripts/dh.py manifest > tools/manifest.json`
重新生成清单之后。流程顺序固定：**先服务端发布能力 → 再重生成 manifest → 再去掉窗口参数**；
否则会长期掩盖"文档能力面领先于服务端"的漂移。

> 注意：`--allow-stale-manifest` 只降级「manifest 落后」这一种失败；frontmatter、知识 MCP、
> 反馈条款、旧表述等其它规则的 FAIL 不会因此被忽略。

### First push (empty remote)

```bash
gh repo create qeasy-cloud/datahub-mcp-ops --public \
  --description "An executable playbook that teaches AI agents to operate Datahub (轻易云) through its MCP endpoint: daemon-free job debugging, field-mapping repair for Kingdee, static value mapping, write verification, diagnostics and safe cleanup. Zero-dependency CLI, docs-as-tests CI." \
  --homepage "https://www.qeasy.cloud" \
  --license MIT

git remote add origin git@github.com:qeasy-cloud/datahub-mcp-ops.git
git push -u origin main

gh repo edit qeasy-cloud/datahub-mcp-ops --add-topic mcp,model-context-protocol,ai-agents,agent-skills,datahub,qeasy,ipaas,integration-platform,kingdee,erp-integration,runbook,diagnostics,python,automation,devops
```

Tagging triggers `.github/workflows/validate.yml` (validation + archive artifact) **and**
`.github/workflows/release.yml`, which publishes the GitHub Release using `docs/release-notes/<tag>.md`
and attaches `datahub-mcp-ops-<tag>.zip`. No personal access token is needed for that step.

If a release already exists, the workflow only refreshes the asset (`--clobber`), so re-running is safe.

## 3.1 One-command repository configuration

Everything the web UI asks for can be applied through the API, idempotently:

```bash
export GITHUB_TOKEN=...        # classic PAT with `repo` (or `public_repo`) + admin on this repo
python scripts/configure_github.py --dry-run    # see what would change
python scripts/configure_github.py              # apply: visibility, About, topics, features,
                                                # vuln reporting, labels, branch protection,
                                                # close bogus dependabot PRs, publish release
```

`--only visibility,about,topics` applies a subset. Every step prints `ok` or `!!` and the script exits
non-zero if any step failed (usually a token-permission problem).

---

## 4. Release notes template

```markdown
## vX.Y.Z — YYYY-MM-DD

**Capability baseline**: datahub-mcp 0.1.0 / x-capability-version 2026-11-11 / 58 tools (+ `strategy.patch`)

### Highlights
- <one line per user-visible change>

### Added
### Changed      <!-- include behaviour changes that affect existing callers -->
### Fixed
### Removed

### Upgrade notes
- <what breaks, what to do>   (link docs/clients.md §4.3 when relevant)

### Verification
- `validate_skill.py` — 11 checks
- `smoke_test.py` — 8 checks against a read-only tenant (58 tools)
- `--filter Mcp` unit suite — 274 tests (server side)
```

### v2.2.0 release notes (ready to paste)

> 完整版本写在 [`docs/release-notes/v2.2.0.md`](release-notes/v2.2.0.md)；发布时把该文件内容粘贴到
> GitHub Release（`release.yml` 会自动读取 `docs/release-notes/<tag>.md`）。摘要：

```markdown
## v2.2.0 — 2026-11-11

**Capability baseline**: datahub-mcp 0.1.0 / x-capability-version 2026-11-11 / 58 tools (+ `strategy.patch`)
knowledge MCP: 4 tools

### Highlights
- Reference-first: knowledge_reference cards → template → adapt → copy/patch
- Modify-first: strategy.patch (server ≥ 2026-11-11) replaces "create a new strategy to change a field"
- Checkpoints: create-overwrite/scripts, field contract, detail rows, Chinese labels, time-parameter minimum
- Script policy: agents output code only; copy keeps existing scripts
- Team execution binding: dh.py → qeasy_mcp.py replacement table, no DH_MCP_* direct calls

### Verification
- validate_skill.py — 11 checks
- smoke_test.py — 8 checks (58 tools, read-only)
- grep knowledge_reference — > 0 across SKILL/references/playbooks/examples/docs
```

---

## 5. Post-publish checklist

- [ ] About description + website + topics set
- [ ] Social preview uploaded (1280×640)
- [ ] Issues/Discussions on, Wiki off
- [ ] Branch protection requires `validate`
- [ ] Private vulnerability reporting on
- [ ] `vX.Y.Z` release published with notes from `docs/release-notes/<tag>.md`
- [ ] Repository added to the org profile README
- [ ] Link from `https://www.qeasy.cloud/mcp` back to this repository
