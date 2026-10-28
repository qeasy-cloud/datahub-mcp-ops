#!/usr/bin/env python3
"""validate_skill.py - offline consistency checks for this skill package.

Runs in CI and before a release. No network, no third-party packages.

Checks
  1. required files exist
  2. SKILL.md frontmatter is valid (name/description/license/version)
  3. tools/manifest.json is well-formed and self-consistent
  4. every manifest tool is documented, and no doc references an unknown tool
  5. relative links (markdown + backticked paths) resolve
  6. no credential-looking strings
  7. no empty files

Exit code 0 = pass, 1 = failures found.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CITATION.cff",
    "references/01-platform-model.md",
    "references/02-tool-catalog.md",
    "references/03-debug-loop.md",
    "references/04-write-recipe.md",
    "references/05-diagnostics.md",
    "references/06-knowledge-mcp.md",
    "references/07-security-and-limits.md",
    "references/08-anti-patterns.md",
    "playbooks/p1-debug-source.md",
    "playbooks/p2-debug-target-write.md",
    "playbooks/p3-new-integration.md",
    "playbooks/p4-ops-and-cleanup.md",
    "examples/prompts.md",
    "examples/session-source-debug.md",
    "scripts/dh.py",
    "scripts/validate_skill.py",
    "scripts/smoke_test.py",
    "scripts/configure_github.py",
    "tools/manifest.json",
    "tools/manifest.schema.json",
    "tools/mcp-config.example.json",
    "docs/clients.md",
    "docs/architecture.md",
    "docs/faq.md",
    "docs/releasing.md",
    "docs/release-notes/v2.0.0.md",
    "docs/assets/banner.svg",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/workflows/validate.yml",
    ".github/workflows/release.yml",
]

SKILL_DIRS = ("references/", "playbooks/", "examples/", "scripts/", "tools/", "docs/", "templates/")

SECRET_PATTERNS = [
    (re.compile(r"\bsh-[A-Za-z0-9+/=_\-]{24,}"), "looks like a Datahub MCP key"),
    (re.compile(r"\bqk_live_[A-Za-z0-9]{8,}"), "looks like a knowledge MCP key"),
    (re.compile(r"app_secret\"\s*:\s*\"[^\"<]{8,}"), "app_secret with a value"),
    (re.compile(r"Bearer\s+sh-[A-Za-z0-9+/=_\-]{20,}"), "bearer token literal"),
]

TOOL_RE = re.compile(r"\b(?:strategy|asset|script|audit|meta|exception)\.[a-z][A-Za-z0-9]*(?:\.[a-z][A-Za-z0-9]*)+")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
IMG_SRC_RE = re.compile(r"<img[^>]+src=\"([^\"]+)\"")
BACKTICK_PATH_RE = re.compile(
    r"`((?:%s)[^`\s]*?\.(?:md|json|py|cff))`" % "|".join(re.escape(d) for d in SKILL_DIRS)
)

failures: List[str] = []
notes: List[str] = []


def fail(message: str) -> None:
    failures.append(message)


def read(path: str) -> str:
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as handle:
        return handle.read()


def walk_markdown() -> List[str]:
    found = []
    for base, _dirs, files in os.walk(ROOT):
        if ".git" in base or ".github" in base:
            continue
        for name in files:
            if name.endswith(".md"):
                found.append(os.path.relpath(os.path.join(base, name), ROOT).replace(os.sep, "/"))
    return sorted(found)


# --------------------------------------------------------------------------- #
# 1-2. files + frontmatter
# --------------------------------------------------------------------------- #
def check_files() -> None:
    for rel in REQUIRED_FILES:
        if not os.path.exists(os.path.join(ROOT, rel)):
            fail("missing required file: %s" % rel)
            continue
        if os.path.getsize(os.path.join(ROOT, rel)) == 0:
            fail("empty file: %s" % rel)


def parse_frontmatter(text: str) -> Dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    data: Dict[str, str] = {}
    current = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z_][\w-]*:", line) and not line.startswith(" "):
            key, _, value = line.partition(":")
            current = key.strip()
            data[current] = value.strip()
        elif current and line.startswith(" "):
            data[current] = (data.get(current, "") + " " + line.strip()).strip()
    return data


def check_skill() -> None:
    text = read("SKILL.md")
    front = parse_frontmatter(text)
    if not front:
        fail("SKILL.md: missing YAML frontmatter")
        return
    name = front.get("name", "")
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        fail("SKILL.md: name must be kebab-case, got %r" % name)
    if name != os.path.basename(ROOT):
        fail("SKILL.md: name %r != directory %r" % (name, os.path.basename(ROOT)))
    description = front.get("description", "").strip().strip(">").strip()
    if len(description) < 80:
        fail("SKILL.md: description too short (%d chars)" % len(description))
    if len(description) > 1024:
        fail("SKILL.md: description exceeds 1024 chars (%d)" % len(description))
    if not front.get("license"):
        fail("SKILL.md: missing license")
    version = re.search(r"version:\s*([0-9]+\.[0-9]+\.[0-9]+)", text)
    if not version:
        fail("SKILL.md: metadata.version must be semver")
    if len(text.splitlines()) > 500:
        fail("SKILL.md: %d lines (>500) - move detail into references/" % len(text.splitlines()))
    notes.append("SKILL.md: %d lines, description %d chars" % (len(text.splitlines()), len(description)))


# --------------------------------------------------------------------------- #
# 3. manifest
# --------------------------------------------------------------------------- #
def check_manifest() -> Dict[str, Dict[str, object]]:
    try:
        manifest = json.loads(read("tools/manifest.json"))
    except json.JSONDecodeError as exc:
        fail("tools/manifest.json: invalid JSON (%s)" % exc)
        return {}
    tools = manifest.get("tools") or []
    by_name: Dict[str, Dict[str, object]] = {}
    for tool in tools:
        name = tool.get("name")
        if not name:
            fail("manifest: tool without name")
            continue
        if name in by_name:
            fail("manifest: duplicate tool %s" % name)
        by_name[name] = tool
        for key in ("risk", "description", "properties"):
            if key not in tool:
                fail("manifest: %s missing %s" % (name, key))
    declared = manifest.get("tool_count")
    meta = manifest.get("meta_tools") or []
    if declared != len(tools) + (len(meta) if meta else 3):
        fail(
            "manifest: tool_count=%s but tools=%d meta=%d"
            % (declared, len(tools), len(meta) if meta else 3)
        )
    if manifest.get("business_tool_count") != len(tools):
        fail("manifest: business_tool_count mismatch")
    notes.append("manifest: %d tools, %s" % (len(tools), manifest.get("capability_version")))
    return by_name


# --------------------------------------------------------------------------- #
# 4. doc <-> manifest consistency
# --------------------------------------------------------------------------- #
def check_tool_coverage(by_name: Dict[str, Dict[str, object]]) -> None:
    if not by_name:
        return
    catalog = read("references/02-tool-catalog.md")
    missing = [name for name in by_name if name not in catalog]
    if missing:
        fail("references/02-tool-catalog.md: %d tools undocumented: %s"
             % (len(missing), ", ".join(sorted(missing)[:6])))

    known = set(by_name) | {"meta.whoami", "meta.capabilities", "meta.enums"}
    unknown: Dict[str, str] = {}
    for rel in walk_markdown():
        text = read(rel)
        for match in TOOL_RE.finditer(text):
            token = match.group(0).rstrip(".")
            if token.count(".") < 2:
                continue
            if token in known:
                continue
            if token.endswith(".md") or token.endswith(".json"):
                continue
            unknown.setdefault(token, rel)
    if unknown:
        preview = ", ".join("%s (%s)" % (k, v) for k, v in sorted(unknown.items())[:8])
        fail("doc references unknown tool names: %s" % preview)
    notes.append("tool coverage: %d manifest tools all documented" % len(by_name))


# --------------------------------------------------------------------------- #
# 5. links
# --------------------------------------------------------------------------- #
def check_links() -> None:
    broken: List[str] = []
    for rel in walk_markdown():
        base = os.path.dirname(os.path.join(ROOT, rel))
        text = read(rel)
        targets = [m.group(1) for m in LINK_RE.finditer(text)]
        targets += [m.group(1) for m in IMG_SRC_RE.finditer(text)]
        targets += [
            m.group(1) for m in BACKTICK_PATH_RE.finditer(text)
        ]
        for target in targets:
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0].split("?", 1)[0]
            if not clean:
                continue
            # Placeholders and citations from other services are not repo paths.
            if any(token in clean for token in ("...", "\u2026", "<", "*")):
                continue
            resolved = os.path.normpath(os.path.join(base, clean))
            if os.path.exists(resolved):
                continue
            # Docs often show repo-root-relative commands (`scripts/dh.py`) from a
            # subdirectory; accept that form too.
            root_relative = os.path.normpath(os.path.join(ROOT, clean.lstrip("./")))
            if os.path.exists(root_relative):
                continue
            broken.append("%s -> %s" % (rel, target))
    if broken:
        fail("broken links (%d): %s" % (len(broken), "; ".join(broken[:6])))
    else:
        notes.append("links: all relative links resolve")


# --------------------------------------------------------------------------- #
# 6-7. secrets
# --------------------------------------------------------------------------- #
def check_i18n() -> None:
    """Both READMEs must exist and link to each other (GitHub language switcher)."""
    en = read("README.md")
    zh = read("README.zh-CN.md")
    if "README.zh-CN.md" not in en:
        fail("README.md: missing link to README.zh-CN.md")
    if "README.md" not in zh:
        fail("README.zh-CN.md: missing link back to README.md")
    if "qeasy.cloud" not in en or "qeasy.cloud" not in zh:
        fail("README: project website link missing")
    for label, text in (("README.md", en), ("README.zh-CN.md", zh)):
        if len(text.splitlines()) < 80:
            fail("%s: too thin for a public repo (%d lines)" % (label, len(text.splitlines())))
    notes.append("i18n: README + README.zh-CN cross-linked")


def check_secrets() -> None:
    hits: List[str] = []
    for rel in walk_markdown() + ["scripts/dh.py", "tools/mcp-config.example.json"]:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        text = read(rel)
        for pattern, label in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                snippet = match.group(0)
                if "<" in snippet or "..." in snippet or "YOUR" in snippet.upper():
                    continue
                hits.append("%s: %s (%s)" % (rel, label, snippet[:12] + "..."))
    if hits:
        fail("possible secrets: %s" % "; ".join(hits[:5]))
    else:
        notes.append("secrets: none detected")


def main(argv: List[str]) -> int:
    verbose = "-v" in argv or "--verbose" in argv
    print("validating skill package at %s" % ROOT)
    check_files()
    check_skill()
    by_name = check_manifest()
    check_tool_coverage(by_name)
    check_links()
    check_i18n()
    check_secrets()

    if verbose:
        for note in notes:
            print("  . %s" % note)
    if failures:
        print("\nFAILED (%d)" % len(failures))
        for item in failures:
            print("  x %s" % item)
        return 1
    print("\nOK - %d checks passed" % (5 + len(notes)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
