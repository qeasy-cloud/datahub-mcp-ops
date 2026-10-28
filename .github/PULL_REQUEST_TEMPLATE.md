## What changed

<!-- one paragraph; link the issue if any -->

## Type

- [ ] 文档修正（错/过时/歧义）
- [ ] 新增诊断条目 / 剧本 / 示例
- [ ] 工具契约更新（`tools/manifest.json`）
- [ ] 脚本 / CI
- [ ] 破坏性变更（需要 major 版本）

## Checklist

- [ ] `python scripts/validate_skill.py -v` 通过
- [ ] 若有服务端能力变化：已重新生成 `tools/manifest.json`
- [ ] 没有密钥、客户数据、内网地址（CI 会扫描，但请自查）
- [ ] 新增的链接都是相对路径且可达
- [ ] `SKILL.md` 的 `metadata.version` 已按 SemVer 更新（如适用）
- [ ] `CHANGELOG.md` 已记录（用户可见的变化）

## Evidence

<!-- 脱敏后的返回片段 / 文档来源 / 复现步骤 -->

```jsonc
// before / after（仅关键字段）
```
