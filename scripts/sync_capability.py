#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_capability.py — 能力面一致性校验（SKILL ↔ manifest ↔ 知识 MCP 契约）。

背景：官方技能包 v2.2 起把「能力面」拆成三处声明，任何一处漂移都会让 Agent 用错能力：
  - `SKILL.md` 的 frontmatter（`metadata.version` / `metadata.capability_version` / `metadata.knowledge_mcp_tools`）；
  - `SKILL.md` 正文（知识 MCP 4 工具、兼容矩阵、13 条用户反馈条款）；
  - `tools/manifest.json`（服务端生成物：`capability_version` / `tool_count`）。

本脚本是不联网的离线校验器（纯 stdlib，Python 3.9+），按 5 组规则检查并输出 PASS/FAIL 摘要。

用法：
  python scripts/sync_capability.py --check                 # 严格：manifest 落后 SKILL 即 FAIL
  python scripts/sync_capability.py --check --allow-stale-manifest
                                                            # 窗口期：manifest 落后降级为 WARN（服务端尚未发布时）
  python scripts/sync_capability.py --check -v              # 输出每条规则的明细
  python scripts/sync_capability.py --check --root <dir>    # 指定仓库根（默认脚本上一级）

退出码：0 = 无 FAIL（可有 WARN）；1 = 至少一条 FAIL；2 = 参数/环境错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# 常量：契约与提示
# --------------------------------------------------------------------------- #

KNOWLEDGE_TOOLS = (
    "knowledge_domains",
    "knowledge_search",
    "knowledge_fetch",
    "knowledge_reference",
)
KNOWLEDGE_TOOL_COUNT = len(KNOWLEDGE_TOOLS)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MANIFEST_REGEN_HINT = (
    "待服务端发布后由 `python scripts/dh.py manifest` 重生成 tools/manifest.json"
)

# 13 条用户反馈：编号 → 可接受关键词（§9.1 每行至少命中一个）
FEEDBACK_KEYWORDS: dict[int, tuple[str, ...]] = {
    1: ("REF", "在跑方案"),
    2: ("蓝图",),
    3: ("占位",),
    4: ("{{源字段}}", "裸名"),
    5: ("明细",),
    6: ("时间参数",),
    7: ("中文",),
    8: ("加工厂", "脚本"),
    9: ("静态映射",),
    10: ("create",),
    11: ("脚本",),
    12: ("连接器",),
    13: ("赛狐",),
}
FEEDBACK_SECTION = "### 9.1"
FEEDBACK_TITLE_HINT = "13 条用户反馈"


class Report:
    """收集 PASS / WARN / FAIL 三类结果并格式化输出。"""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.items: list[dict[str, Any]] = []

    def add(self, level: str, check: str, title: str, message: str, details: list[str] | None = None) -> None:
        self.items.append(
            {
                "level": level,
                "check": check,
                "title": title,
                "message": message,
                "details": details or [],
            }
        )
        tag = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[level]
        print("%s %s %s — %s" % (tag, check, title, message))
        if self.verbose and details:
            for line in details:
                print("        · %s" % line)

    @property
    def failures(self) -> int:
        return sum(1 for item in self.items if item["level"] == "FAIL")

    @property
    def warnings(self) -> int:
        return sum(1 for item in self.items if item["level"] == "WARN")

    def summary(self) -> int:
        passed = sum(1 for item in self.items if item["level"] == "PASS")
        ok = self.failures == 0
        print("")
        print(
            "RESULT: %s（%d pass / %d warn / %d fail）"
            % ("PASS" if ok else "FAIL", passed, self.warnings, self.failures)
        )
        return 0 if ok else 1


# --------------------------------------------------------------------------- #
# 解析工具
# --------------------------------------------------------------------------- #


def parse_frontmatter(text: str) -> dict[str, str]:
    """最小 frontmatter 解析器：支持顶层 key 与一层 `metadata:` 嵌套；忽略块标量续行。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    data: dict[str, str] = {}
    section: str | None = None
    skip_continuation = False
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            # 顶层 key
            key, sep, value = line.partition(":")
            if not sep:
                section = None
                skip_continuation = False
                continue
            section = key.strip()
            value = value.strip()
            if value in (">", "|", ">-", "|-"):
                # 块标量：后续缩进行是内容，不是 key
                data[section] = ""
                skip_continuation = True
                continue
            skip_continuation = False
            data[section] = _unquote(value)
            data["__has__" + section] = "1"
            continue
        # 缩进行：只有 metadata 下的键值对有意义
        indented = line.strip()
        if section == "metadata" and not skip_continuation:
            key, sep, value = indented.partition(":")
            if sep:
                data["metadata." + key.strip()] = _unquote(value.strip())
        # 其它缩进行（块标量/列表）忽略
    return data


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def extract_section(text: str, heading_prefix: str) -> str:
    """取某个 `##`/`###` 标题下到下一个同级或更高级标题之间的正文。"""
    lines = text.splitlines()
    level = len(heading_prefix) - len(heading_prefix.lstrip("#"))
    start = None
    for index, line in enumerate(lines):
        if line.startswith(heading_prefix):
            start = index + 1
            break
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if re.match(r"^#{1,%d}\s" % level, line):
            break
        body.append(line)
    return "\n".join(body)


def find_capability_dates(text: str) -> set[str]:
    """从兼容矩阵的表格行里抽 capability 日期（只认 `|` 开头的表格行，避免正文提及造成误判）。"""
    dates: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        dates.update(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", stripped))
    return dates


def protocol_knowledge_tokens(text: str) -> set[str]:
    """抽取正文里出现的知识 MCP 工具名（排除 metadata key `knowledge_mcp_tools`）。"""
    found = set(re.findall(r"\bknowledge_[a-z][a-z_]*\b", text))
    return {token for token in found if token != "knowledge_mcp_tools"}


# --------------------------------------------------------------------------- #
# 5 组校验（a–e）
# --------------------------------------------------------------------------- #


def check_frontmatter(skill_text: str, report: Report) -> dict[str, str]:
    """a) SKILL.md frontmatter 必填字段与格式。"""
    front = parse_frontmatter(skill_text)
    problems: list[str] = []
    version = front.get("metadata.version", "")
    capability = front.get("metadata.capability_version", "")
    try:
        knowledge_count = int(front.get("metadata.knowledge_mcp_tools", ""))
    except ValueError:
        knowledge_count = -1

    if not version:
        problems.append("缺少 metadata.version")
    elif not SEMVER_RE.match(version):
        problems.append("metadata.version 不是 x.y.z：%r" % version)
    if not capability:
        problems.append("缺少 metadata.capability_version")
    elif not DATE_RE.match(capability):
        problems.append("metadata.capability_version 不是 YYYY-MM-DD：%r" % capability)
    if knowledge_count == -1:
        problems.append("缺少或非法 metadata.knowledge_mcp_tools：%r" % front.get("metadata.knowledge_mcp_tools"))
    elif knowledge_count != KNOWLEDGE_TOOL_COUNT:
        problems.append(
            "metadata.knowledge_mcp_tools=%d，契约要求 %d" % (knowledge_count, KNOWLEDGE_TOOL_COUNT)
        )

    details = [
        "version=%s" % (version or "<缺失>"),
        "capability_version=%s" % (capability or "<缺失>"),
        "knowledge_mcp_tools=%s" % (knowledge_count if knowledge_count != -1 else "<缺失>"),
    ]
    if problems:
        report.add("FAIL", "a.", "SKILL.md frontmatter", "；".join(problems), details)
    else:
        report.add("PASS", "a.", "SKILL.md frontmatter", "必填字段齐全且格式正确", details)
    return front


def check_knowledge_contract(root: Path, skill_text: str, front: dict[str, str], report: Report) -> None:
    """b) references/09 存在且含 knowledge_reference；SKILL 声明 4 个知识工具。"""
    problems: list[str] = []
    details: list[str] = []

    ref_path = root / "references" / "09-knowledge-ref.md"
    if not ref_path.is_file():
        problems.append("缺少 references/09-knowledge-ref.md")
        details.append(str(ref_path))
    else:
        ref_text = ref_path.read_text(encoding="utf-8")
        if "knowledge_reference" not in ref_text:
            problems.append("references/09-knowledge-ref.md 未出现 knowledge_reference")
        details.append("references/09 = %d chars" % len(ref_text))

    tokens = protocol_knowledge_tokens(skill_text)
    missing = [tool for tool in KNOWLEDGE_TOOLS if tool not in tokens]
    unexpected = sorted(tokens - set(KNOWLEDGE_TOOLS))
    if missing:
        problems.append("SKILL.md 缺少知识 MCP 工具：%s" % ", ".join(missing))
    if unexpected:
        problems.append("SKILL.md 出现未知知识 MCP 工具名：%s" % ", ".join(unexpected))
    try:
        declared = int(front.get("metadata.knowledge_mcp_tools", ""))
    except ValueError:
        declared = -1
    if declared != KNOWLEDGE_TOOL_COUNT:
        problems.append(
            "SKILL.md 声明的知识 MCP 工具数 %r != %d" % (front.get("metadata.knowledge_mcp_tools"), KNOWLEDGE_TOOL_COUNT)
        )
    details.append("SKILL.md 知识工具：%s" % (", ".join(sorted(tokens)) or "<无>"))

    if problems:
        report.add("FAIL", "b.", "知识 MCP 4 工具契约", "；".join(problems), details)
    else:
        report.add(
            "PASS",
            "b.",
            "知识 MCP 4 工具契约",
            "references/09 存在且 4 工具齐全（含 knowledge_reference）",
            details,
        )


def check_manifest(
    root: Path,
    skill_text: str,
    front: dict[str, str],
    report: Report,
    allow_stale: bool,
) -> None:
    """c) manifest 的 capability_version / tool_count 与 SKILL 兼容矩阵一致。"""
    problems: list[str] = []
    details: list[str] = []
    manifest_path = root / "tools" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError:
        report.add("FAIL", "c.", "manifest ↔ SKILL 兼容矩阵", "缺少 tools/manifest.json", [str(manifest_path)])
        return
    except json.JSONDecodeError as exc:
        report.add("FAIL", "c.", "manifest ↔ SKILL 兼容矩阵", "tools/manifest.json 不是合法 JSON：%s" % exc)
        return

    manifest_cap = str(manifest.get("capability_version") or "")
    tool_count = manifest.get("tool_count")
    business_count = manifest.get("business_tool_count")
    meta_tools = manifest.get("meta_tools") or []
    tools = manifest.get("tools") or []
    if not DATE_RE.match(manifest_cap):
        problems.append("manifest.capability_version 非法：%r" % manifest_cap)
    if not isinstance(tool_count, int) or tool_count <= 0:
        problems.append("manifest.tool_count 缺失或非法：%r" % tool_count)
    else:
        if isinstance(business_count, int) and business_count != len(tools):
            problems.append(
                "manifest.business_tool_count=%d 但 tools 数组有 %d 条" % (business_count, len(tools))
            )
        if tool_count != len(tools) + len(meta_tools):
            problems.append(
                "manifest.tool_count=%d != tools(%d) + meta_tools(%d)"
                % (tool_count, len(tools), len(meta_tools))
            )
    details.append(
        "manifest: capability=%s / tool_count=%s / generated_at=%s"
        % (manifest_cap or "<缺失>", tool_count, manifest.get("generated_at", "<缺失>"))
    )

    # 与 SKILL 兼容矩阵一致性（§10 版本与兼容）
    compat = extract_section(skill_text, "## 10. 版本与兼容") or extract_section(skill_text, "## 版本与兼容")
    target_cap = front.get("metadata.capability_version", "")
    dates = find_capability_dates(compat)
    if not compat:
        problems.append("SKILL.md 缺少「版本与兼容」章节")
    else:
        if manifest_cap and manifest_cap not in dates:
            problems.append("兼容矩阵未列出 manifest.capability_version=%s" % manifest_cap)
        if target_cap and target_cap not in dates:
            problems.append("兼容矩阵未列出 SKILL 目标 capability_version=%s" % target_cap)
        if isinstance(tool_count, int) and str(tool_count) not in compat:
            problems.append("兼容矩阵未声明工具总数 %d" % tool_count)
        details.append("兼容矩阵 capability 日期：%s" % (", ".join(sorted(dates)) or "<无>"))

    # SKILL §5 工具地图标题里的工具总数
    match = re.search(r"工具地图[（(]\s*(\d+)\s*个", skill_text)
    if not match:
        problems.append("SKILL.md 未找到「工具地图（N 个…）」标题")
    elif isinstance(tool_count, int) and int(match.group(1)) != tool_count:
        problems.append("SKILL 工具地图声明 %s 个，manifest.tool_count=%d" % (match.group(1), tool_count))

    # manifest 新鲜度：落后 / 领先。落后是"窗口期"维度，不能掩盖其它结构性问题。
    stale_message = ""
    if DATE_RE.match(manifest_cap) and DATE_RE.match(target_cap):
        if manifest_cap < target_cap:
            stale_message = "tools/manifest.json 落后：%s < SKILL %s" % (manifest_cap, target_cap)
        elif manifest_cap > target_cap:
            problems.append(
                "SKILL 目标 capability_version=%s 落后于 manifest=%s（先更新 SKILL 再发布）"
                % (target_cap, manifest_cap)
            )

    if problems:
        report.add("FAIL", "c.", "manifest ↔ SKILL 兼容矩阵", "；".join(problems), details)
    elif stale_message:
        if allow_stale:
            report.add(
                "WARN",
                "c.",
                "manifest ↔ SKILL 兼容矩阵",
                stale_message
                + "（--allow-stale-manifest 已降级为 WARN）→ "
                + MANIFEST_REGEN_HINT,
                details,
            )
        else:
            report.add(
                "FAIL",
                "c.",
                "manifest ↔ SKILL 兼容矩阵",
                stale_message + "；服务端发布后需重生成：" + MANIFEST_REGEN_HINT,
                details,
            )
    else:
        report.add(
            "PASS",
            "c.",
            "manifest ↔ SKILL 兼容矩阵",
            "capability 与工具总数一致（manifest=%s / %s tools）" % (manifest_cap, tool_count),
            details,
        )


def check_stale_phrases(skill_text: str, report: Report) -> None:
    """d) SKILL.md 不得残留「3 个工具」与缺 knowledge_reference 的三元组。"""
    problems: list[str] = []
    details: list[str] = []

    for pattern in ("3 个工具", "三个工具", "3 tools"):
        hits = [number for number, line in enumerate(skill_text.splitlines(), 1) if pattern in line]
        if hits:
            problems.append("命中旧表述「%s」：第 %s 行" % (pattern, ", ".join(map(str, hits))))

    # 三元组：knowledge_domains 所在行（及后两行）必须有 knowledge_reference
    lines = skill_text.splitlines()
    triple_hits: list[str] = []
    for index, line in enumerate(lines):
        if "knowledge_domains" not in line:
            continue
        window = "\n".join(lines[index : index + 3])
        if "knowledge_reference" not in window:
            triple_hits.append("第 %d 行" % (index + 1))
    if triple_hits:
        problems.append("知识工具三元组缺 knowledge_reference：%s" % ", ".join(triple_hits))

    hit_count = len(re.findall(r"\bknowledge_reference\b", skill_text))
    details.append("SKILL.md knowledge_reference 出现 %d 次" % hit_count)
    if problems:
        report.add("FAIL", "d.", "SKILL.md 无旧工具表述", "；".join(problems), details)
    else:
        report.add("PASS", "d.", "SKILL.md 无旧工具表述", "无「3 个工具」/三元组残留", details)


def find_heading_line(text: str, heading_prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(heading_prefix):
            return line
    return ""


def check_feedback_clauses(skill_text: str, report: Report) -> None:
    """e) 13 条反馈条款在 §9.1 可定位（编号 + 关键词）。"""
    section = extract_section(skill_text, FEEDBACK_SECTION)
    if not section:
        report.add("FAIL", "e.", "13 条反馈条款", "SKILL.md 缺少 %s 章节" % FEEDBACK_SECTION)
        return

    rows: dict[int, str] = {}
    for line in section.splitlines():
        match = re.match(r"^\|\s*(\d{1,2})\s*\|(.*)\|\s*$", line)
        if match:
            rows[int(match.group(1))] = match.group(2)

    missing = sorted(set(range(1, 14)) - set(rows))
    weak = sorted(
        number
        for number, words in FEEDBACK_KEYWORDS.items()
        if number in rows and not any(word in rows[number] for word in words)
    )
    heading = find_heading_line(skill_text, FEEDBACK_SECTION)
    title_note = ""
    if FEEDBACK_TITLE_HINT not in heading:
        title_note = "（提示：§9.1 标题未出现「%s」字样）" % FEEDBACK_TITLE_HINT
    details = [
        "§9.1 标题：%s" % (heading.strip() or "<缺失>"),
        "找到 %d/13 条：%s" % (len(rows), ", ".join(map(str, sorted(rows))) or "<无>"),
    ]
    problems: list[str] = []
    if missing:
        problems.append("缺少条目：%s" % ", ".join(map(str, missing)))
    if weak:
        problems.append("条目关键词缺失：%s" % ", ".join(map(str, weak)))
    if problems:
        report.add("FAIL", "e.", "13 条反馈条款", "；".join(problems), details)
    else:
        report.add("PASS", "e.", "13 条反馈条款", "13/13 可定位且关键词齐全" + title_note, details)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def run(root: Path, allow_stale: bool, verbose: bool) -> int:
    report = Report(verbose=verbose)
    skill_path = root / "SKILL.md"
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        print("[FAIL] 无法读取 SKILL.md：%s" % exc)
        return 1

    print("能力面校验（sync_capability.py）— %s" % ("--allow-stale-manifest" if allow_stale else "严格模式"))
    print("repo: %s" % root)
    print("")
    front = check_frontmatter(skill_text, report)
    check_knowledge_contract(root, skill_text, front, report)
    check_manifest(root, skill_text, front, report, allow_stale)
    check_stale_phrases(skill_text, report)
    check_feedback_clauses(skill_text, report)
    return report.summary()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="能力面一致性校验：SKILL.md ↔ tools/manifest.json ↔ 知识 MCP 契约（离线、纯 stdlib）",
        epilog="示例：python scripts/sync_capability.py --check --allow-stale-manifest -v",
    )
    parser.add_argument("--check", action="store_true", help="执行校验（默认动作；保留以表达语义）")
    parser.add_argument(
        "--allow-stale-manifest",
        action="store_true",
        help="manifest 落后 SKILL capability_version 时降级为 WARN（服务端尚未发布的窗口期使用）",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="输出每条规则的明细")
    parser.add_argument("--root", default="", help="仓库根目录（默认取脚本上一级）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    if not (root / "SKILL.md").is_file():
        print("错误：%s 不是技能包根目录（缺少 SKILL.md）" % root, file=sys.stderr)
        return 2
    if not args.check:
        print("提示：未指定 --check，按默认动作执行校验。", file=sys.stderr)
    return run(root, args.allow_stale_manifest, args.verbose)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
