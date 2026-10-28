#!/usr/bin/env python3
"""dh.py - zero-dependency CLI for the Datahub MCP endpoint.

Why this exists: an agent that has to hand-roll JSON-RPC, session headers and SSE
parsing wastes turns. This is a 30-second path from "I have a key" to "I have data".

Usage
    export DH_MCP_URL="http://127.0.0.1:5200/api/mcp"
    export DH_MCP_KEY="sh-..."          # or pass --key

    python dh.py doctor                 # endpoint + key + protocol + tool count
    python dh.py tools                  # grouped tool list (name/risk/scope)
    python dh.py call meta.whoami
    python dh.py call strategy.dbInfo --param strategyId=<SID>
    python dh.py call strategy.get --args @args.json
    python dh.py manifest               # machine-readable manifest (for CI/docs)
    python dh.py raw tools/list         # raw JSON-RPC for anything not covered

Exit codes: 0 ok - 1 tool/server error - 2 configuration/usage error.
No third-party packages. Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "datahub-mcp-ops-skill", "version": "2.0.0"}
DEFAULT_TIMEOUT = 60.0
ELLIPSIS = "\u2026"


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
class McpError(RuntimeError):
    """A JSON-RPC or transport level failure."""

    def __init__(self, message: str, code: Any = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class Client:
    """Minimal stateful Streamable-HTTP MCP client."""

    def __init__(self, url: str, key: str, timeout: float = DEFAULT_TIMEOUT):
        if not url:
            raise McpError("missing MCP URL (set DH_MCP_URL)")
        if not key:
            raise McpError("missing MCP key (set DH_MCP_KEY)")
        self.url = url
        self.key = key
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self.server_info: Dict[str, Any] = {}
        self.capabilities: Dict[str, Any] = {}
        self._initialized = False
        self._ssl = ssl.create_default_context()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.key,
            "User-Agent": "dh.py/2.0.0",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    @staticmethod
    def _parse_body(content_type: str, raw: str) -> Dict[str, Any]:
        """Accept both plain JSON and SSE ("data: {...}") responses."""
        if "text/event-stream" in (content_type or ""):
            payloads = [
                line[5:].strip() for line in raw.splitlines() if line.startswith("data:")
            ]
            for payload in reversed(payloads):
                if payload and payload != "[DONE]":
                    return json.loads(payload)
            raise McpError("empty SSE response")
        return json.loads(raw) if raw.strip() else {}

    def post(self, payload: Dict[str, Any], retries: int = 2) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        attempt = 0
        while True:
            request = urllib.request.Request(
                self.url, data=data, headers=self._headers(), method="POST"
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout, context=self._ssl
                ) as response:
                    session = response.headers.get("Mcp-Session-Id")
                    if session:
                        self.session_id = session.strip()
                    body = self._parse_body(
                        response.headers.get("Content-Type", ""),
                        response.read().decode("utf-8", "replace"),
                    )
                    return body or {}
            except urllib.error.HTTPError as exc:
                body_text = exc.read().decode("utf-8", "replace")
                if exc.code == 429 and attempt < retries:
                    wait = _retry_after(exc.headers.get("Retry-After"), default=5.0)
                    time.sleep(min(wait, 30.0))
                    attempt += 1
                    continue
                raise McpError(
                    "HTTP %d: %s" % (exc.code, _short(body_text)),
                    code=exc.code,
                    data=_maybe_json(body_text),
                )
            except urllib.error.URLError as exc:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    attempt += 1
                    continue
                raise McpError("cannot reach %s (%s)" % (self.url, exc.reason))

    def initialize(self) -> Dict[str, Any]:
        if self._initialized:
            return {"serverInfo": self.server_info}
        body = self.post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            }
        )
        if "error" in body:
            error = body["error"] or {}
            raise McpError(
                error.get("message", "initialize failed"),
                code=error.get("code"),
                data=error.get("data"),
            )
        result = body.get("result") or {}
        self.server_info = result.get("serverInfo") or {}
        self.capabilities = result.get("capabilities") or {}
        self._initialized = True
        try:
            self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except McpError:
            pass
        return result

    def rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.initialize()
        body = self.post(
            {"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}}
        )
        if "error" in body:
            error = body["error"] or {}
            raise McpError(
                error.get("message", "rpc failed"),
                code=error.get("code"),
                data=error.get("data"),
            )
        return body.get("result") or {}

    def tools(self) -> List[Dict[str, Any]]:
        return self.rpc("tools/list").get("tools") or []

    def call(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.initialize()
        body = self.post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        if "error" in body:
            error = body["error"] or {}
            raise McpError(
                error.get("message", "tool call failed"),
                code=error.get("code"),
                data=error.get("data"),
            )
        return body.get("result") or {}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _retry_after(value: Optional[str], default: float = 5.0) -> float:
    try:
        return float(value) if value else default
    except (TypeError, ValueError):
        return default


def _short(text: str, limit: int = 300) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:limit] + (ELLIPSIS if len(text) > limit else "")


def _maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _tool_text(result: Dict[str, Any]) -> str:
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text") or "")
    return "\n".join(parts)


def _mask(key: str) -> str:
    if not key:
        return "(none)"
    if len(key) <= 14:
        return key[:4] + ELLIPSIS
    return key[:8] + ELLIPSIS + key[-4:]


def _print_json(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows consoles may be GBK/CP1252; prefer readability loss over crash.
        print(json.dumps(value, ensure_ascii=True, indent=2))


def _configure_streams() -> None:
    """Force UTF-8 output so Chinese text and symbols survive any console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def _coerce(raw: str) -> Any:
    text = raw.strip()
    if text in ("true", "false"):
        return text == "true"
    if text == "null":
        return None
    if text[:1] in ("[", "{", '"'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return raw
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return raw


def _load_args(raw: Optional[str], params: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build arguments from --args (JSON or @file) and/or repeated --param k=v.

    --param exists because Windows shells mangle inline JSON quotes; it keeps the
    common case copy-pasteable on every platform.
    """
    payload: Dict[str, Any] = {}
    if raw:
        if raw.startswith("@"):
            with open(raw[1:], "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    "--args is not valid JSON: %s\n"
                    "hint: use --param key=value, or --args @args.json" % exc
                )
        if not isinstance(payload, dict):
            raise SystemExit("--args must be a JSON object")
    for item in params or []:
        if "=" not in item:
            raise SystemExit("--param expects key=value, got %r" % item)
        key, value = item.split("=", 1)
        payload[key.strip()] = _coerce(value)
    return payload


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_doctor(client: Client, args: argparse.Namespace) -> int:
    print("endpoint : %s" % client.url)
    print("key      : %s" % _mask(client.key))
    started = time.time()
    try:
        init = client.initialize()
    except McpError as exc:
        print("status   : FAILED - %s" % exc)
        print("\nhint: 401 -> key missing/revoked; URL must end with /api/mcp")
        return 1
    elapsed = (time.time() - started) * 1000
    info = init.get("serverInfo") or client.server_info or {}
    print("server   : %s %s" % (info.get("name", "?"), info.get("version", "")))
    caps = init.get("capabilities") or client.capabilities or {}
    print("protocol : %s" % (caps.get("protocolVersion") or PROTOCOL_VERSION))
    print("session  : %s" % (client.session_id or "(stateless)"))
    print("latency  : %.0f ms" % elapsed)
    try:
        tools = client.tools()
    except McpError as exc:
        print("tools    : FAILED - %s" % exc)
        return 1
    print("tools    : %d visible" % len(tools))
    if args.verbose:
        for tool in tools:
            print("  - %s" % tool.get("name"))
    return 0


def cmd_tools(client: Client, args: argparse.Namespace) -> int:
    tools = client.tools()
    if args.json:
        _print_json(tools)
        return 0
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for tool in tools:
        name = tool.get("name", "")
        domain = name.split(".")[0] if "." in name else "meta"
        groups.setdefault(domain, []).append(tool)
    for domain in sorted(groups):
        print("\n[%s]" % domain)
        for tool in sorted(groups[domain], key=lambda item: item.get("name", "")):
            risk = (tool.get("annotations") or {}).get("risk", "?")
            first = (tool.get("description") or "").strip().splitlines()
            print(
                "  %-28s %-12s %s"
                % (tool.get("name"), risk, _short(first[0] if first else "", 90))
            )
    print("\ntotal: %d tools" % len(tools))
    return 0


def cmd_call(client: Client, args: argparse.Namespace) -> int:
    payload = _load_args(args.args, getattr(args, "param", None))
    try:
        result = client.call(args.tool, payload)
    except McpError as exc:
        if args.json:
            _print_json({"error": str(exc), "code": exc.code, "data": exc.data})
        else:
            print("[error] %s" % exc)
            if isinstance(exc.data, dict):
                _print_json(exc.data)
        return 1
    is_error = bool(result.get("isError"))
    structured = result.get("structuredContent")
    text = _tool_text(result)
    if args.json:
        _print_json({"isError": is_error, "text": text, "structuredContent": structured})
    elif args.quiet:
        print(text)
    else:
        print("[%s] %s" % ("error" if is_error else "ok", text or "(no text)"))
        if structured is not None:
            print()
            _print_json(structured)
    return 1 if is_error else 0


def cmd_manifest(client: Client, args: argparse.Namespace) -> int:
    """Regenerate tools/manifest.json from the live server (docs are CI-checked)."""
    tools = client.tools()
    entries = []
    for tool in sorted(tools, key=lambda item: item.get("name", "")):
        schema = tool.get("inputSchema") or {}
        annotations = tool.get("annotations") or {}
        entries.append(
            {
                "name": tool.get("name"),
                "title": annotations.get("title") or tool.get("title"),
                "scope": annotations.get("required_scope"),
                "risk": annotations.get("risk"),
                "requires_confirmation": annotations.get("requires_confirmation"),
                "description": tool.get("description"),
                "required": schema.get("required") or [],
                "properties": sorted((schema.get("properties") or {}).keys()),
            }
        )
    experimental = (client.capabilities or {}).get("experimental") or {}
    manifest = {
        "schema_version": "1.0.0",
        "server": (client.server_info or {}).get("name"),
        "server_version": (client.server_info or {}).get("version"),
        "capability_version": experimental.get("x-capability-version"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool_count": len(entries),
        "business_tool_count": len(
            [entry for entry in entries if not (entry["name"] or "").startswith("meta.")]
        ),
        "tools": entries,
    }
    _print_json(manifest)
    return 0


def cmd_raw(client: Client, args: argparse.Namespace) -> int:
    params = _load_args(args.args, getattr(args, "param", None))
    try:
        result = client.rpc(args.method, params)
    except McpError as exc:
        _print_json({"error": str(exc), "code": exc.code, "data": exc.data})
        return 1
    _print_json(result)
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def _env(*names: str, default: str = "") -> str:
    """First non-empty environment variable from names (portable across skill versions).

    v1.x of this skill used DATAHUB_MCP_URL / DATAHUB_MCP_TOKEN; v2 uses DH_MCP_*.
    Accept both so an existing shell profile keeps working after an upgrade.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dh.py",
        description="CLI for the Datahub MCP endpoint (zero dependencies).",
        epilog="env: DH_MCP_URL, DH_MCP_KEY, DH_MCP_TIMEOUT (legacy: DATAHUB_MCP_URL, DATAHUB_MCP_TOKEN)",
    )
    parser.add_argument("--url", default=_env("DH_MCP_URL", "DATAHUB_MCP_URL"))
    parser.add_argument("--key", default=_env("DH_MCP_KEY", "DATAHUB_MCP_TOKEN", "DATAHUB_MCP_KEY"))
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(_env("DH_MCP_TIMEOUT", "DATAHUB_MCP_TIMEOUT", default=str(DEFAULT_TIMEOUT))),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check endpoint, key, protocol, tool count")
    doctor.add_argument("-v", "--verbose", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    tools = sub.add_parser("tools", help="list tools grouped by domain")
    tools.add_argument("--json", action="store_true")
    tools.set_defaults(func=cmd_tools)

    call = sub.add_parser("call", help="call one tool")
    call.add_argument("tool")
    call.add_argument("--args", default="", help="JSON object, or @file.json")
    call.add_argument(
        "--param",
        action="append",
        metavar="K=V",
        help="repeatable; avoids shell quoting issues",
    )
    call.add_argument("--json", action="store_true", help="print raw result envelope")
    call.add_argument("-q", "--quiet", action="store_true", help="print human text only")
    call.set_defaults(func=cmd_call)

    manifest = sub.add_parser("manifest", help="emit tools manifest JSON")
    manifest.set_defaults(func=cmd_manifest)

    raw = sub.add_parser("raw", help="raw JSON-RPC method")
    raw.add_argument("method")
    raw.add_argument("--args", default="")
    raw.add_argument("--param", action="append", metavar="K=V")
    raw.set_defaults(func=cmd_raw)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _configure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        client = Client(args.url, args.key, args.timeout)
    except McpError as exc:
        print("config error: %s" % exc, file=sys.stderr)
        print("set DH_MCP_URL / DH_MCP_KEY, or pass --url / --key", file=sys.stderr)
        return 2
    try:
        return args.func(client, args)
    except McpError as exc:
        print("[error] %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
