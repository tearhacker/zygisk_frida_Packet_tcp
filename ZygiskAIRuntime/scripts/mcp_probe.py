# -*- coding: utf-8 -*-
"""直连 MCP Server（SSE）并调用工具 —— 不依赖 GUI 客户端的会话。

用途
----
MCP 客户端（WorkBuddy / Claude Desktop 等）与 SSE 服务之间是**有状态会话**：
服务端一重启，客户端握着的旧 session_id 就失效，会持续报

    {"code":-32001,"message":"MCP session not found"}

而客户端往往不会立刻重连。本脚本自己开一条 SSE + 走完 initialize 握手，
用来在「服务端刚重启 / 客户端连不上」时确认服务与底层 Runtime 是否真的可用。

用法
----
    python scripts/mcp_probe.py session.info
    python scripts/mcp_probe.py process.list '{}'
    python scripts/mcp_probe.py memory.read '{"address":"0x7a00000000","length":16}'
    python scripts/mcp_probe.py --list        # 只列出工具
"""

from __future__ import annotations

import json
import sys
import threading
import time
from queue import Empty, Queue

import httpx

BASE = "http://127.0.0.1:60501"
PROTOCOL_VERSION = "2024-11-05"


def _pump(q: Queue, stop: threading.Event) -> None:
    """把 SSE 流解析成事件塞进队列。"""
    try:
        with httpx.stream(
            "GET", BASE + "/sse", headers={"Accept": "text/event-stream"}, timeout=None
        ) as resp:
            buf: dict[str, str] = {}
            for raw in resp.iter_lines():
                if stop.is_set():
                    return
                line = raw.rstrip("\r\n")
                if line == "":
                    if buf:
                        q.put(buf)
                        buf = {}
                    continue
                if line.startswith("data:"):
                    buf["data"] = buf.get("data", "") + line[5:].strip()
                elif line.startswith("event:"):
                    buf["event"] = line[6:].strip()
                elif line.startswith("id:"):
                    buf["id"] = line[3:].strip()
    except Exception as exc:  # noqa: BLE001
        q.put({"event": "__error__", "data": repr(exc)})


def _wait_id(q: Queue, req_id: int, timeout: float = 30.0) -> dict:
    """等待与 req_id 对应的响应。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ev = q.get(timeout=0.5)
        except Empty:
            continue
        if ev.get("event") == "__error__":
            raise RuntimeError("SSE 连接出错: " + ev["data"])
        data = ev.get("data") or ""
        if not data or not data.startswith("{"):
            continue
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and msg.get("id") == req_id:
            return msg
    raise TimeoutError(f"等待 id={req_id} 的响应超时")


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:]]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    q: Queue = Queue()
    stop = threading.Event()
    t = threading.Thread(target=_pump, args=(q, stop), daemon=True)
    t.start()

    # 1) 等 endpoint 事件，拿到回话专属的 POST 端点
    endpoint = None
    deadline = time.time() + 15
    while time.time() < deadline and endpoint is None:
        try:
            ev = q.get(timeout=0.5)
        except Empty:
            continue
        if ev.get("event") == "endpoint":
            endpoint = ev["data"]
    if not endpoint:
        print("未能从 /sse 拿到 endpoint 事件，服务没起？", file=sys.stderr)
        return 2
    post_url = BASE + endpoint if endpoint.startswith("/") else endpoint
    print(f"[sse] endpoint = {endpoint}", file=sys.stderr)

    client = httpx.Client(timeout=30)

    def rpc(method: str, params: dict | None = None, *, notify: bool = False) -> dict | None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            payload["id"] = rpc.counter
            rpc.counter += 1
        r = client.post(post_url, json=payload)
        if r.status_code >= 400:
            # 通知（notification）本就没有响应体，个别实现会回 404/202；
            # 这里只要包发出去就算数，不要因此中断后续调用。
            if notify:
                print(f"[warn] {method} -> HTTP {r.status_code}（已忽略）", file=sys.stderr)
                return None
            raise RuntimeError(f"POST {method} -> HTTP {r.status_code}: {r.text[:200]}")
        if notify:
            return None
        return _wait_id(q, payload["id"])

    rpc.counter = 1  # type: ignore[attr-defined]

    init = rpc(
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-probe", "version": "0.1"},
        },
    )
    print(f"[mcp] 已握手: {init['result']['serverInfo']}", file=sys.stderr)
    rpc("notifications/initialized", notify=True)

    if args[0] == "--list":
        res = rpc("tools/list")
        names = [x["name"] for x in res["result"]["tools"]]
        print(json.dumps({"count": len(names), "tools": names}, ensure_ascii=False, indent=2))
        return 0

    tool = args[0]
    raw = args[1] if len(args) > 1 else "{}"
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"参数不是合法 JSON: {exc}", file=sys.stderr)
        return 2

    res = rpc("tools/call", {"name": tool, "arguments": arguments})
    if "error" in res:
        print(json.dumps(res["error"], ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(res["result"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except KeyboardInterrupt:
        raise SystemExit(130)
