# -*- coding: utf-8 -*-
"""`python -m ai_analyzer.host` 入口。

参数定义全部在 `ai_analyzer/host/cli.py`（唯一来源），本文件只是薄壳：
两种启动方式（模块入口 / 顶层 mcp_server.py）必须行为一致。

用法
----
    # 用 Mock 后端跑通全链路（无真机）
    python -m ai_analyzer.host --mock

    # 连真机：自动 adb forward tcp:60500 tcp:60500
    python -m ai_analyzer.host
    python -m ai_analyzer.host --adb "C:/Program Files/platform-tools/adb.exe"

    # 只做装配自检并打印可见工具，不启动服务
    python -m ai_analyzer.host --mock --check

    # 打印可粘贴的客户端配置（stdio 形态）
    python -m ai_analyzer.host --print-config

    # 常驻 HTTP 服务（客户端只填 URL）
    python -m ai_analyzer.host --mock --transport sse --port 60501
"""

from __future__ import annotations

# 常量也从 cli 转出：历史上有脚本引用过 host.__main__.DEFAULT_HTTP_PORT，
# 保留 re-export 免得旧入口静默失效。
from .cli import (
    CLIENT_TYPE_BY_TRANSPORT,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    SSE_PATH,
    STREAMABLE_HTTP_PATH,
    client_config,
    main,
)

__all__ = [
    "main",
    "client_config",
    "DEFAULT_HTTP_HOST",
    "DEFAULT_HTTP_PORT",
    "SSE_PATH",
    "STREAMABLE_HTTP_PATH",
    "CLIENT_TYPE_BY_TRANSPORT",
]


if __name__ == "__main__":
    raise SystemExit(main())
