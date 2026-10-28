#!/usr/bin/env python3
"""configure_github.py - apply the repository settings that git cannot.

Git can push code and tags; it cannot set the About box, topics, visibility,
labels, branch protection or a release. This script does those through the
GitHub REST API so the whole setup is reproducible and reviewable.

Usage
    export GITHUB_TOKEN=ghp_...           # classic PAT: repo + admin:repo_hook? no
                                          # needed scopes: repo (private) / public_repo,
                                          # and admin rights on the repository
    python scripts/configure_github.py --dry-run
    python scripts/configure_github.py

    # only some steps
    python scripts/configure_github.py --only visibility,about,topics
    python scripts/configure_github.py --only release,prs

Exit codes: 0 all requested steps ok - 1 at least one step failed.

The token is never printed. Every step is idempotent: running twice is safe.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

API = "https://api.github.com"
DEFAULT_REPO = "qeasy-cloud/datahub-mcp-ops"
HOMEPAGE = "https://www.qeasy.cloud"
DESCRIPTION = (
    "An executable playbook that teaches AI agents to operate Datahub (轻易云) through its MCP "
    "endpoint: daemon-free job debugging, field-mapping repair for Kingdee, write verification, "
    "diagnostics and safe cleanup. 46 tools, zero-dependency CLI, docs-as-tests CI."
)
TOPICS = [
    "mcp", "model-context-protocol", "ai-agents", "agent-skills", "datahub", "qeasy",
    "ipaas", "integration-platform", "kingdee", "erp-integration", "runbook",
    "diagnostics", "llm-tools", "observability", "automation", "python", "devops",
    "api-integration",
]
LABELS = [
    ("bug", "d73a4a", "Documentation or script is wrong"),
    ("enhancement", "a2eeef", "New diagnostic, playbook or example"),
    ("tool-contract", "5319e7", "Tool schema or generated manifest changed"),
    ("docs", "0075ca", "Prose only"),
    ("good first issue", "7057ff", "Single file, clear scope"),
    ("needs-tenant", "fbca04", "Requires a live tenant to verify"),
]
ALL_STEPS = ["visibility", "about", "topics", "features", "vuln", "labels", "protection", "prs", "release"]

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
results: List[Tuple[str, str, str]] = []


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def call(method: str, path: str, body: Optional[Dict[str, Any]] = None, dry: bool = False
         ) -> Tuple[int, Any]:
    if dry:
        return 999, {"dry_run": True, "method": method, "path": path, "body": body}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(API + path, data=data, method=method)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "datahub-mcp-ops-setup")
    if TOKEN:
        request.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw[:300]}
        return exc.code, payload
    except urllib.error.URLError as exc:
        return 0, {"message": "network: %s" % exc.reason}


def good(status: int) -> bool:
    """2xx, or the dry-run sentinel."""
    return status in (200, 201, 204, 999)


def record(step: str, ok: bool, detail: str) -> None:
    results.append((step, "ok" if ok else "FAIL", detail))
    print("[%s] %-12s %s" % ("ok" if ok else "!!", step, detail))


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def step_visibility(repo: str, dry: bool) -> None:
    status, data = call("GET", "/repos/" + repo, dry=dry)
    if not dry and status == 404:
        record("visibility", False, "repository not found or token lacks access")
        return
    private = data.get("private")
    if dry:
        record("visibility", True, "would set private=false (currently unknown in dry-run)")
        return
    if private is False:
        record("visibility", True, "already public")
        return
    status, data = call("PATCH", "/repos/" + repo, {"private": False})
    record("visibility", good(status), "now public" if good(status) else str(data.get("message")))


def step_about(repo: str, dry: bool) -> None:
    body = {
        "description": DESCRIPTION,
        "homepage": HOMEPAGE,
        "has_issues": True,
        "has_wiki": False,
        "has_projects": False,
    }
    status, data = call("PATCH", "/repos/" + repo, body, dry=dry)
    record("about", good(status), "description + homepage + issues/wiki/projects" if good(status) else str(data.get("message")))


def step_topics(repo: str, dry: bool) -> None:
    status, data = call("PUT", "/repos/%s/topics" % repo, {"names": TOPICS}, dry=dry)
    record("topics", good(status), "%d topics" % len(TOPICS) if good(status) else str(data.get("message")))


def step_features(repo: str, dry: bool) -> None:
    body = {
        "has_discussions": True,
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "delete_branch_on_merge": True,
        "allow_auto_merge": True,
    }
    status, data = call("PATCH", "/repos/" + repo, body, dry=dry)
    record("features", good(status), "discussions on / squash-only / auto-delete branches" if good(status) else str(data.get("message")))


def step_vuln(repo: str, dry: bool) -> None:
    status, data = call("PUT", "/repos/%s/private-vulnerability-reporting" % repo, {}, dry=dry)
    record("vuln", good(status), "private vulnerability reporting on" if good(status) else str(data.get("message")))


def step_labels(repo: str, dry: bool) -> None:
    ok_all = True
    for name, color, description in LABELS:
        status, data = call("POST", "/repos/%s/labels" % repo, {"name": name, "color": color, "description": description}, dry=dry)
        if good(status):
            continue
        if status == 422:
            status, data = call("PATCH", "/repos/%s/labels/%s" % (repo, urllib.parse.quote(name)), {"color": color, "description": description}, dry=dry)
        if not good(status):
            ok_all = False
    record("labels", ok_all, "%d labels ensured" % len(LABELS))


def step_protection(repo: str, dry: bool) -> None:
    body = {
        "required_status_checks": {"strict": True, "contexts": ["validate"]},
        "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 0},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }
    status, data = call("PUT", "/repos/%s/branches/main/protection" % repo, body, dry=dry)
    record("protection", good(status), "main: PR + validate check, no force push" if good(status) else str(data.get("message")))


def step_prs(repo: str, dry: bool) -> None:
    """Close the bogus dependabot majors (checkout@v7 etc. do not exist)."""
    status, data = call("GET", "/repos/%s/pulls?state=open&per_page=100" % repo, dry=dry)
    if dry:
        record("prs", True, "would close dependabot PRs bumping actions to non-existent majors")
        return
    if status != 200 or not isinstance(data, list):
        record("prs", False, "cannot list pull requests: %s" % str(data)[:120])
        return
    closed = 0
    for pr in data:
        head = (pr.get("head") or {}).get("ref", "")
        if head.startswith("dependabot/github_actions/") and head.endswith("-7"):
            call("POST", "/repos/%s/issues/%d/comments" % (repo, pr["number"]),
                 {"body": "Closing: this bump targets a major version that does not exist for this action. "
                          "Actions are pinned deliberately; see `.github/dependabot.yml`."})
            call("PATCH", "/repos/%s/pulls/%d" % (repo, pr["number"]), {"state": "closed"})
            closed += 1
    record("prs", True, "%d bogus dependabot PR(s) closed" % closed)


def step_release(repo: str, tag: str, dry: bool) -> None:
    notes_path = os.path.join("docs", "release-notes", tag + ".md")
    body_text = ""
    if os.path.exists(notes_path):
        with open(notes_path, "r", encoding="utf-8") as handle:
            body_text = handle.read()
    status, data = call("GET", "/repos/%s/releases/tags/%s" % (repo, tag), dry=dry)
    if not dry and status == 200:
        record("release", True, "%s already published" % tag)
        return
    payload = {"tag_name": tag, "name": tag, "body": body_text or None, "draft": False, "prerelease": False}
    status, data = call("POST", "/repos/%s/releases" % repo, payload, dry=dry)
    record("release", good(status), "%s release" % tag if good(status) else str(data.get("message")))


def main(argv: List[str]) -> int:
    global TOKEN
    parser = argparse.ArgumentParser(description="Apply GitHub repository settings for this project.")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--tag", default="v2.0.0")
    parser.add_argument("--only", default="", help="comma list: " + ",".join(ALL_STEPS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not TOKEN and not args.dry_run:
        print("error: set GITHUB_TOKEN (repo scope + admin on the repository)", file=sys.stderr)
        return 2

    wanted = [s.strip() for s in args.only.split(",") if s.strip()] or ALL_STEPS
    unknown = [s for s in wanted if s not in ALL_STEPS]
    if unknown:
        print("error: unknown step(s): %s" % ", ".join(unknown), file=sys.stderr)
        return 2

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("repository: %s%s" % (args.repo, "  (dry run)" if args.dry_run else ""))
    for step in wanted:
        try:
            if step == "visibility":
                step_visibility(args.repo, args.dry_run)
            elif step == "about":
                step_about(args.repo, args.dry_run)
            elif step == "topics":
                step_topics(args.repo, args.dry_run)
            elif step == "features":
                step_features(args.repo, args.dry_run)
            elif step == "vuln":
                step_vuln(args.repo, args.dry_run)
            elif step == "labels":
                step_labels(args.repo, args.dry_run)
            elif step == "protection":
                step_protection(args.repo, args.dry_run)
            elif step == "prs":
                step_prs(args.repo, args.dry_run)
            elif step == "release":
                step_release(args.repo, args.tag, args.dry_run)
        except Exception as exc:  # noqa: BLE001 - report and continue
            record(step, False, "unexpected: %s" % exc)

    failed = [row for row in results if row[1] == "FAIL"]
    print("\n%d step(s), %d failed" % (len(results), len(failed)))
    if failed:
        print("hint: 404/403 usually means the token lacks repo admin (or the repo is private "
              "and the token belongs to another account).")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
