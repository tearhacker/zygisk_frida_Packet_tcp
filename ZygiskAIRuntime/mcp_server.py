#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zygisk AI Runtime —— MCP Server 单文件入口。

客户端 mcp.json 就用这个文件的**绝对路径**拉起服务，端口/adb 都能省略：:

    {
      "mcpServers": {
        "zy_packet_tearhacker": {
          "command": "C:/Users/52334/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe",
          "args": [
            "D:/泪心安卓领域基本盘技术/zygisk_frida_PackerGetPrivateTool/ZygiskAIRuntime/mcp_server.py",
            "--port", "27184",
            "--adb", "C:/Program Files/platform-tools/adb.exe"
          ]
        }
      }
    }

最少写法（端口、adb 全用默认值）：:

    {"mcpServers": {"zy_packet_tearhacker": {
        "command": "<python.exe>",
        "args": ["<...>/ZygiskAIRuntime/mcp_server.py"]}}}

默认值
------
    --adb           C:/Program Files/platform-tools/adb.exe
                    （Windows；不存在时退回 PATH 里的 adb。非 Windows 走 PATH）
    --port          60501  MCP 客户端 ↔ 本服务（只有 --transport sse 时才监听）
    --device-port   60500  PC ↔ 手机 Runtime IPC（adb forward 两端都用它）
    --transport     stdio  客户端 spawn 本进程、走 stdin/stdout

行为要点
--------
* 非 mock 且未给 --endpoint 时，启动会自动执行
  `adb forward tcp:60500 tcp:60500`，并用 `adb forward --list` 复核。
  这不是可选项：忘了建 forward 的现象和"Runtime 挂了"一模一样
  （2026-09-19 真机事故：重连计数涨到 70+，根因只是没人建 forward）。
* adb 不在 / 设备 offline / Runtime 没起来，服务**照常启动**，
  工具如实返回 E_NOT_READY。禁止把失败伪装成成功。

全部参数见：python mcp_server.py --help
"""

from __future__ import annotations

import os
import sys

# 把本文件所在目录（ZygiskAIRuntime/）顶到 sys.path 最前面。
# 客户端 spawn 进程时 cwd 可能是任何地方，不显式加的话 `import ai_analyzer` 会失败。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from ai_analyzer.host.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
