#!/usr/bin/env python3
"""smoke_test.py - read-only live check against a Datahub MCP endpoint.

Verifies the wiring this skill depends on: handshake, auth, tool visibility and a
few read calls. Never calls a tool that can change state (no dispatch, no run, no
update, no clean).

Usage
    export DH_MCP_URL=... DH_MCP_KEY=...
    python scripts/smoke_test.py
    python scripts/smoke_test.py --strategy-id <SID> --expect-tools 46

Exit code 0 = all checks passed.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dh import Client, McpError  # noqa: E402
from dh import _env  # noqa: E402  (accepts DH_MCP_* and legacy DATAHUB_MCP_*)

PASS = "  ok  "
FAIL = " fail "


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=_env("DH_MCP_URL", "DATAHUB_MCP_URL"))
    parser.add_argument("--key", default=_env("DH_MCP_KEY", "DATAHUB_MCP_TOKEN", "DATAHUB_MCP_KEY"))
    parser.add_argument("--strategy-id", default="", help="optional: also read one strategy")
    parser.add_argument("--expect-tools", type=int, default=0, help="assert the tool count")
    args = parser.parse_args()

    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        print("[%s] %s%s" % (PASS if ok else FAIL, label, (" :: " + detail) if detail else ""))
        if not ok:
            failures += 1

    try:
        client = Client(args.url, args.key)
    except McpError as exc:
        print("config error: %s" % exc)
        return 2

    # 1. handshake
    try:
        client.initialize()
        check("handshake", True, "%s %s" % (
            (client.server_info or {}).get("name"),
            (client.server_info or {}).get("version"),
        ))
    except McpError as exc:
        print("[%s] handshake :: %s" % (FAIL, exc))
        print("\nhint: 401 -> key missing/revoked; URL must end with /api/mcp")
        return 1

    # 2. tools visible
    try:
        tools = client.tools()
        names = {tool.get("name") for tool in tools}
        check("tools/list", bool(tools), "%d tools" % len(tools))
        if args.expect_tools:
            check("tool count == %d" % args.expect_tools, len(tools) == args.expect_tools,
                  "got %d" % len(tools))
        check("core read tools visible",
              {"meta.whoami", "strategy.list", "strategy.dbInfo"} <= names,
              "missing: %s" % sorted({"meta.whoami", "strategy.list", "strategy.dbInfo"} - names))
    except McpError as exc:
        check("tools/list", False, str(exc))
        return 1

    # 3. identity
    try:
        result = client.call("meta.whoami")
        data = result.get("structuredContent") or {}
        check("meta.whoami", not result.get("isError"), "user=%s trust=%s" % (
            (data.get("user") or {}).get("name"),
            (data.get("grant") or {}).get("trust"),
        ))
    except McpError as exc:
        check("meta.whoami", False, str(exc))

    # 4. capabilities
    try:
        result = client.call("meta.capabilities")
        data = result.get("structuredContent") or {}
        check("meta.capabilities", (data.get("tool_count") or 0) >= len(tools),
              "tool_count=%s" % data.get("tool_count"))
    except McpError as exc:
        check("meta.capabilities", False, str(exc))

    # 5. list one strategy
    try:
        result = client.call("strategy.list", {"pageSize": 1})
        data = result.get("structuredContent") or {}
        rows = data.get("rows") or []
        check("strategy.list", not result.get("isError"),
              "total=%s sample=%s" % (data.get("total"), (rows[0] or {}).get("name") if rows else "-"))
    except McpError as exc:
        check("strategy.list", False, str(exc))

    # 6. optional: dbInfo
    if args.strategy_id:
        try:
            result = client.call("strategy.dbInfo", {"strategyId": args.strategy_id})
            data = result.get("structuredContent") or {}
            check("strategy.dbInfo", not result.get("isError"),
                  "data=%s log=%s" % (data.get("data"), data.get("log")))
        except McpError as exc:
            check("strategy.dbInfo", False, str(exc))

    print()
    if failures:
        print("FAILED: %d check(s)" % failures)
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
